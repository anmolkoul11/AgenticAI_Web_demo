"""Desktop entry point: one owned loopback backend and the normal browser dashboard."""

import ctypes
import json
import logging
import os
import queue
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


HOST = "127.0.0.1"
PORT = 8120
DASHBOARD_URL = f"http://{HOST}:{PORT}"
SERVICE_NAME = "agentic-studio-desktop"


def resource_root():
    """PyInstaller resources are read-only; user data never belongs here."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def companion_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "BrowserCompanion"
    return resource_root() / "extensions" / "page-capture"


def user_data_dir(environ=None):
    values = os.environ if environ is None else environ
    override = values.get("AGENTIC_DEMO_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = values.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "AgenticStudio" / "data"


def configure_environment():
    data = user_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["AGENTIC_DEMO_DATA_DIR"] = str(data)
    os.environ["AGENTIC_DASHBOARD_DESKTOP"] = "1"
    os.environ["AGENTIC_DASHBOARD_POLICY_PATH"] = str(resource_root() / "config" / "rules.yaml")
    browsers = resource_root() / "browsers"
    if browsers.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    return data


def lifecycle_logger(data):
    """Only explicit lifecycle codes are logged; no request bodies or provider errors."""
    logs = data.parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("agentic_studio.desktop")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(logs / "desktop.log", maxBytes=200_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


class SingleInstance:
    """A named Windows handle lives only as long as its owning application."""

    def __init__(self):
        self.handle = None
        self.already_running = False
        if os.name == "nt":
            from ctypes import wintypes

            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            ctypes.set_last_error(0)
            self.handle = self.kernel.CreateMutexW(None, False, r"Local\AgenticStudio.Desktop")
            if not self.handle:
                raise OSError("Desktop instance handle unavailable")
            self.already_running = ctypes.get_last_error() == 183

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def existing_dashboard_ready():
    """Only reopen a backend identifying itself as this desktop application."""
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with opener.open(f"{DASHBOARD_URL}/api/desktop/health", timeout=0.5) as response:
                body = json.loads(response.read(1024))
            if isinstance(body, dict) and body.get("service") == SERVICE_NAME \
                    and body.get("status") == "ready":
                return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    return False


class Backend:
    def __init__(self, logger):
        self.logger = logger
        self.events = queue.Queue()
        self.thread = None
        self.server = None
        self.stopping = False

    @property
    def alive(self):
        return bool(self.thread and self.thread.is_alive())

    def start(self):
        if self.alive:
            return
        self.server = None
        self.stopping = False
        self.thread = threading.Thread(target=self._run, name="AgenticStudioBackend", daemon=True)
        self.thread.start()

    def _run(self):
        listener = None
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if os.name == "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind((HOST, PORT))
                listener.listen(128)
                listener.setblocking(False)
            except OSError:
                self.logger.error("start_failed port_unavailable")
                self.events.put("port_unavailable")
                return
            if not (resource_root() / "config" / "rules.yaml").is_file():
                self.logger.error("start_failed bundled_configuration_missing")
                self.events.put("configuration_missing")
                return
            # Imports and app construction happen after writable paths are configured.
            import uvicorn

            from agentic_web_demo.dashboard.app import create_app

            config = uvicorn.Config(
                create_app(), host=HOST, port=PORT, workers=1, loop="asyncio",
                access_log=False, log_config=None, log_level="critical",
                timeout_graceful_shutdown=10,
            )
            self.server = uvicorn.Server(config)
            if self.stopping:
                self.server.should_exit = True
            self.logger.info("backend_starting")
            self.server.run(sockets=[listener])
            self.events.put("stopped" if self.stopping else "backend_exited")
            self.logger.info("backend_stopped")
        except (Exception, SystemExit) as exc:
            self.logger.error("start_failed %s", type(exc).__name__)
            self.events.put("startup_failed")
        finally:
            if listener:
                listener.close()

    def stop(self):
        self.stopping = True
        if self.server:
            self.server.should_exit = True


class DesktopWindow:
    def __init__(self, window, data, logger):
        from tkinter import ttk

        self.window, self.data = window, data
        self.backend = Backend(logger)
        self.closing = False
        self.opened = False
        window.title("Agentic Studio")
        window.geometry("570x410")
        window.minsize(530, 410)
        icon = resource_root() / "app.ico"
        if icon.is_file():
            window.iconbitmap(default=str(icon))
        style = ttk.Style(window)
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        body = ttk.Frame(window, padding=26)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Agentic Studio", style="Title.TLabel").pack(anchor="w")
        self.status = ttk.Label(body, text="Starting your workspace…", wraplength=500)
        self.status.pack(anchor="w", pady=(20, 12))
        ttk.Label(body, text="Keep this app and your dashboard tab open while tasks run.\n"
                  "AI requests need an internet connection. Saved results stay on this computer.",
                  wraplength=500).pack(anchor="w")
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(24, 16))
        self.open_button = ttk.Button(controls, text="Open dashboard", command=self.open_dashboard,
                                      state="disabled")
        self.open_button.pack(side="left")
        self.start_button = ttk.Button(controls, text="Retry startup", command=self.start,
                                       state="disabled")
        self.start_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Saved data", command=self.open_data).pack(side="left")
        ttk.Button(controls, text="Extension setup", command=self.open_companion).pack(side="left", padx=8)
        ttk.Label(body, text="Closing this app stops the backend and any task still running.",
                  wraplength=500).pack(anchor="w")
        self.close_button = ttk.Button(body, text="Stop and close", command=self.close)
        self.close_button.pack(anchor="e", pady=(12, 0))
        window.protocol("WM_DELETE_WINDOW", self.close)
        self.start()
        window.after(150, self.poll)

    def start(self):
        self.status.configure(text="Starting your workspace…")
        self.start_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.opened = False
        self.backend.start()

    def open_dashboard(self):
        if not webbrowser.open(DASHBOARD_URL):
            self.status.configure(text=f"Open {DASHBOARD_URL} in Chrome or Edge to continue.")

    def open_data(self):
        if os.name == "nt":
            os.startfile(self.data)
        else:
            webbrowser.open(self.data.as_uri())

    def open_companion(self):
        from tkinter import messagebox

        folder = companion_dir()
        if not folder.is_dir():
            messagebox.showerror("Browser Companion", "The companion folder is missing. Reinstall "
                                 "Agentic Studio; your saved data is kept separately.")
            return
        if os.name == "nt":
            os.startfile(folder)
        else:
            webbrowser.open(folder.as_uri())
        messagebox.showinfo("Browser Companion setup", "For this pilot release, open Extensions in "
                            "Chrome or Edge, enable Developer mode, choose Load unpacked and select "
                            "the BrowserCompanion folder just opened. Then open the companion on "
                            "your website tab. Keep the dashboard tab open and signed in.")

    def close(self):
        self.closing = True
        self.status.configure(text="Stopping your workspace. Please wait…")
        self.open_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.close_button.configure(state="disabled")
        self.backend.stop()

    def poll(self):
        if self.closing and not self.backend.alive:
            self.window.destroy()
            return
        while True:
            try:
                event = self.backend.events.get_nowait()
            except queue.Empty:
                break
            messages = {
                "port_unavailable": "Another application is using the dashboard address. Close your "
                                    "earlier development dashboard, then choose Retry startup.",
                "configuration_missing": "The installation is incomplete. Reinstall Agentic Studio. "
                                         "Your saved data is kept separately.",
                "startup_failed": "The workspace could not start. Try again or contact support. "
                                  "Startup details are in the logs folder next to your data folder.",
                "backend_exited": "The workspace stopped. Choose Retry startup to reopen it.",
                "stopped": "The workspace is stopped.",
            }
            if not self.closing:
                self.status.configure(text=messages[event])
                self.start_button.configure(state="normal")
                self.open_button.configure(state="disabled")
        server = self.backend.server
        if not self.closing and self.backend.alive and server and server.started and not self.opened:
            self.opened = True
            self.status.configure(text="Your workspace is running. Continue in the dashboard.")
            self.open_button.configure(state="normal")
            self.open_dashboard()
        self.window.after(150, self.poll)


def main():
    instance = None
    window = None
    desktop = None
    try:
        instance = SingleInstance()
        if instance.already_running:
            if existing_dashboard_ready():
                webbrowser.open(DASHBOARD_URL)
                return 0
            raise RuntimeError("An existing Agentic Studio window is still starting or stopping.")
        data = configure_environment()
        logger = lifecycle_logger(data)
        logger.info("desktop_started")
        import tkinter as tk

        window = tk.Tk()
        desktop = DesktopWindow(window, data, logger)
        window.mainloop()
        logger.info("desktop_closed")
        return 0
    except Exception:
        text = "Agentic Studio could not open. Check that another copy is not already starting " \
               "and that your Windows account can access its local application-data folder."
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, text, "Agentic Studio", 0x10)
        else:
            from tkinter import messagebox

            messagebox.showerror("Agentic Studio", text)
        return 2
    finally:
        if desktop and desktop.backend.alive:
            desktop.backend.stop()
            desktop.backend.thread.join(timeout=12)
        if instance:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
