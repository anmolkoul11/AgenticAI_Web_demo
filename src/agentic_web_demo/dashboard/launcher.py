"""Start only owned local services; never stop an existing process by port."""

import os
import argparse
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn

from agentic_web_demo.portal.app import PortalSettings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="Reload dashboard Python code on edits")
    args = parser.parse_args()
    os.environ.setdefault("DEMO_SESSION_SECRET", secrets.token_urlsafe(48))
    PortalSettings.from_env()  # Fail before launching children if setup is incomplete.
    for port in (8110, 8120):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                print(f"Port {port} is unavailable. Stop your earlier demo or use manual setup.")
                return 2
    os.environ["AGENTIC_DASHBOARD_PORTAL_URL"] = "http://127.0.0.1:8110"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    portal_env = dict(os.environ)
    portal_env.pop("OPENAI_API_KEY", None)
    portal = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agentic_web_demo.portal.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8110",
            "--no-access-log",
        ],
        creationflags=flags,
        env=portal_env,
    )
    try:
        for _ in range(50):
            if portal.poll() is not None:
                print("Portal could not start. Check configuration and port availability.")
                return 2
            try:
                with socket.create_connection(("127.0.0.1", 8110), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            print("Portal startup timed out.")
            return 2
        print(
            "Dashboard: http://127.0.0.1:8120 — create/sign in to a local account. Ctrl+C stops it."
        )
        browser = threading.Timer(1.5, webbrowser.open, args=("http://127.0.0.1:8120",))
        browser.daemon = True
        browser.start()
        uvicorn.run(
            "agentic_web_demo.dashboard.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=8120,
            workers=1,
            access_log=False,
            reload=args.dev,
            reload_dirs=["src/agentic_web_demo/dashboard"] if args.dev else None,
        )
    finally:
        portal.terminate()
        try:
            portal.wait(timeout=5)
        except subprocess.TimeoutExpired:
            portal.kill()
            portal.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
