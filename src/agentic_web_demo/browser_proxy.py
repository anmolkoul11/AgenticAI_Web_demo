"""Ephemeral HTTPS CONNECT proxy with explicit hosts and public-IP pinning.

TLS remains end-to-end between Chromium and the website. No TLS interception,
request-body logging, cookies, credentials or upstream proxies are used here.
"""

import base64
import secrets
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agentic_web_demo.custom_fetch import public_addresses


class GuardedProxy:
    def __init__(self, hosts):
        self.hosts = frozenset(hosts)
        self.username, self.password = secrets.token_hex(16), secrets.token_hex(24)
        self.auth = (
            "Basic " + base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        )
        self.stopped = threading.Event()
        self.slots = threading.BoundedSemaphore(48)
        self.lock = threading.Lock()
        self.sockets = set()
        self.transferred = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(30)

            def reject(self, status):
                self.send_response(status)
                if status == 407:
                    self.send_header("Proxy-Authenticate", 'Basic realm="local-browser"')
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def do_CONNECT(self):  # noqa: N802 - HTTP handler method name
                if not secrets.compare_digest(
                    self.headers.get("Proxy-Authorization", ""), owner.auth
                ):
                    self.reject(407)
                    return
                # Only approved DNS names/IPs over 443, not arbitrary tunnelling destinations.
                host, separator, port = self.path.rpartition(":")
                host = host.strip("[]").lower()
                if (
                    not separator
                    or port != "443"
                    or host not in owner.hosts
                    or owner.stopped.is_set()
                ):
                    self.reject(403)
                    return
                if not owner.slots.acquire(blocking=False):
                    self.reject(503)
                    return
                upstream = None
                try:
                    ip = public_addresses(host, 443)[0]
                    upstream = socket.create_connection((ip, 443), timeout=30)
                    upstream.settimeout(30)
                    with owner.lock:
                        owner.sockets.update((upstream, self.connection))
                    self.send_response(200, "Connection established")
                    self.end_headers()
                    self.wfile.flush()
                    deadline = time.monotonic() + 600
                    while not owner.stopped.is_set() and time.monotonic() < deadline:
                        readable, _, _ = select.select([self.connection, upstream], [], [], 0.5)
                        for source in readable:
                            chunk = source.recv(65536)
                            if not chunk:
                                return
                            with owner.lock:
                                owner.transferred += len(chunk)
                                if owner.transferred > 100_000_000:
                                    owner.stopped.set()
                                    return
                            target = upstream if source is self.connection else self.connection
                            target.sendall(chunk)
                except Exception:
                    # Never expose proxy destinations or exception payloads in logs.
                    pass
                finally:
                    with owner.lock:
                        owner.sockets.discard(upstream)
                        owner.sockets.discard(self.connection)
                    if upstream is not None:
                        upstream.close()
                    self.close_connection = True
                    owner.slots.release()

            def do_GET(self):  # noqa: N802
                self.reject(403)

            do_POST = do_GET
            do_PUT = do_GET
            do_DELETE = do_GET
            do_OPTIONS = do_GET
            do_HEAD = do_GET

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    @property
    def settings(self):
        return {
            "server": f"http://127.0.0.1:{self.server.server_port}",
            "username": self.username,
            "password": self.password,
            "bypass": "<-loopback>",
        }

    def __exit__(self, *_args):
        self.stopped.set()
        with self.lock:
            for sock in list(self.sockets):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
