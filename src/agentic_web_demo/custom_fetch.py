"""Bounded public-page reader: pinned public IPs, no cookies, scripts or credentials."""

import http.client
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "AgenticDemoReader/1.0"
MAX_BYTES = 2_000_000
MAX_TEXT = 24_000


class WebsiteError(ValueError):
    """Only fixed, safe messages are surfaced to the dashboard."""


def public_url(value):
    try:
        if len(value) > 2048:
            raise ValueError()
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 80 if parsed.scheme == "http" else 443}
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError()
        netloc = f"[{host}]" if ":" in host else host
        return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError):
        raise WebsiteError(
            "Use a public HTTP/HTTPS URL without credentials or custom ports."
        ) from None


def origin(url):
    parts = urlsplit(public_url(url))
    return f"{parts.scheme}://{parts.netloc}"


def public_addresses(host, port):
    try:
        addresses = list(
            dict.fromkeys(
                item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            )
        )
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError()
        return addresses
    except (OSError, ValueError):
        raise WebsiteError(
            "Website DNS could not be verified as public. No request was sent."
        ) from None


def fetch(url, *, redirects=3):
    """Resolve once, validate every address, and connect to that exact IP (no rebinding)."""
    url = public_url(url)
    allowed_origin = origin(url)
    for _ in range(redirects + 1):
        parts = urlsplit(url)
        port = 443 if parts.scheme == "https" else 80
        ip = public_addresses(parts.hostname, port)[0]
        conn = http.client.HTTPConnection(parts.hostname, port, timeout=12)
        try:
            sock = socket.create_connection((ip, port), timeout=12)
            conn.sock = sock
            if parts.scheme == "https":
                conn.sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=parts.hostname
                )
            path = parts.path + ("?" + parts.query if parts.query else "")
            conn.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                target = public_url(urljoin(url, response.getheader("Location", "")))
                if origin(target) != allowed_origin:
                    raise WebsiteError(
                        "The page redirects to another origin. Submit that URL explicitly."
                    )
                url = target
                continue
            if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
                raise WebsiteError("Compressed page delivery is unsupported. Use pasted page text.")
            deadline = time.monotonic() + 20
            chunks, size = [], 0
            while True:
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() > deadline:
                    raise WebsiteError("Page exceeds the download size or time limit.")
                if not chunk:
                    break
                chunks.append(chunk)
            return url, response.status, response.getheader("Content-Type", ""), b"".join(chunks)
        except WebsiteError:
            raise
        except (OSError, http.client.HTTPException):
            raise WebsiteError(
                "Website connection failed. Check the URL or use pasted page text."
            ) from None
        finally:
            conn.close()
    raise WebsiteError("Too many redirects. Submit the final page URL explicitly.")


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "template", "svg", "form"}:
            self.blocked.append(tag)
        if not self.blocked and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "article", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.blocked and tag == self.blocked[-1]:
            self.blocked.pop()
        if not self.blocked:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def read_pages(urls):
    root = origin(urls[0])
    if any(origin(url) != root for url in urls):
        raise WebsiteError("All submitted pages must use the same origin.")
    _, status, _, body = fetch(root + "/robots.txt")
    robot = RobotFileParser()
    if status == 404:
        robot.parse([])
    elif status == 200:
        robot.parse(body.decode("utf-8", errors="replace").splitlines())
    else:
        raise WebsiteError(
            "Could not verify robots.txt. Use an authorized pasted-page-text source."
        )
    delay = robot.crawl_delay(USER_AGENT) or 1
    if delay > 10:
        raise WebsiteError(
            "This site's crawl delay exceeds this demo's limit. Use pasted page text."
        )
    pages = []
    for url in urls:
        if not robot.can_fetch(USER_AGENT, url):
            raise WebsiteError("robots.txt disallows this reader on the requested page.")
        time.sleep(delay)
        # Reject redirects here: each final path must have its own robots check.
        final, status, content_type, body = fetch(url, redirects=0)
        if status in {401, 403, 429}:
            raise WebsiteError(
                "Website requires access or is rate limiting. No bypass was attempted."
            )
        if status != 200:
            raise WebsiteError("Website did not return a successful page.")
        media = content_type.split(";")[0].strip().lower()
        if media not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise WebsiteError(
                "Only HTML and plain-text pages are supported; not PDF or binary files."
            )
        # Deliberately no JS execution, login form values, cookies or hidden browser storage.
        text = body.decode("utf-8", errors="replace")
        if media != "text/plain":
            parser = PageText()
            parser.feed(text)
            text = "".join(parser.parts)
        text = "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())
        if len(text) < 80:
            raise WebsiteError(
                "Too little page text. It may need login or JavaScript; use pasted text."
            )
        pages.append({"url": final, "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT})
    return pages
