"""Single-process demo portal; not a production identity service."""

import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agentic_web_demo.portal.seed import LISTINGS

SESSION_SECONDS = 3600
ASSETS = Path(__file__).parent


@dataclass(frozen=True)
class PortalSettings:
    username: str
    password: str = field(repr=False)
    session_secret: str = field(repr=False)

    def __post_init__(self):
        if not self.username.strip():
            raise ValueError("DEMO_USERNAME must not be empty")
        if len(self.password) < 12:
            raise ValueError("DEMO_PASSWORD must contain at least 12 characters")
        if len(self.session_secret) < 32:
            raise ValueError("DEMO_SESSION_SECRET must contain at least 32 characters")

    @classmethod
    def from_env(cls):
        return cls(
            username=os.environ.get("DEMO_USERNAME", "demo"),
            password=os.environ.get("DEMO_PASSWORD", ""),
            session_secret=os.environ.get("DEMO_SESSION_SECRET", ""),
        )


def create_app(settings: PortalSettings | None = None) -> FastAPI:
    settings = settings or PortalSettings.from_env()
    app = FastAPI(title="Agentic Demo Stays", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="demo_session",
        max_age=SESSION_SECONDS,
        same_site="strict",
        https_only=False,  # Only for the documented loopback HTTP development server.
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    templates = Jinja2Templates(directory=ASSETS / "templates")
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")
    # Opaque IDs permit logout revocation. Restarting this one-worker demo logs everyone out.
    sessions: dict[str, float] = {}

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        return response

    def authenticated(request: Request) -> bool:
        now = time.monotonic()
        for sid in list(sessions):
            if sessions[sid] <= now:
                del sessions[sid]
        return request.session.get("sid") in sessions

    def csrf(request: Request) -> str:
        if "csrf" not in request.session:
            request.session["csrf"] = secrets.token_urlsafe(32)
        return request.session["csrf"]

    def verify_csrf(request: Request, token: str):
        expected = request.session.get("csrf", "")
        if not expected or not secrets.compare_digest(expected.encode(), token.encode()):
            raise HTTPException(403, "Form expired or invalid. Reload the page and try again.")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "demo-portal"}

    @app.get("/")
    async def index(request: Request):
        return RedirectResponse("/listings" if authenticated(request) else "/login", 303)

    @app.get("/login")
    async def login_page(request: Request):
        if authenticated(request):
            return RedirectResponse("/listings", 303)
        return templates.TemplateResponse(
            request=request, name="login.html", context={"csrf": csrf(request), "error": None}
        )

    @app.post("/login")
    async def login(
        request: Request,
        username: Annotated[str, Form(max_length=128)],
        password: Annotated[str, Form(max_length=1024)],
        csrf_token: Annotated[str, Form(max_length=256)] = "",
    ):
        verify_csrf(request, csrf_token)
        user_ok = secrets.compare_digest(username.encode(), settings.username.encode())
        password_ok = secrets.compare_digest(password.encode(), settings.password.encode())
        if not (user_ok and password_ok):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                status_code=401,
                context={"csrf": csrf(request), "error": "Invalid username or password."},
            )
        authenticated(request)  # Prune expired entries before creating a session.
        sessions.pop(request.session.get("sid", ""), None)
        if len(sessions) >= 1000:
            raise HTTPException(503, "Demo session capacity reached. Restart the local portal.")
        request.session.clear()
        sid = secrets.token_urlsafe(32)
        sessions[sid] = time.monotonic() + SESSION_SECONDS
        request.session["sid"] = sid
        csrf(request)
        return RedirectResponse("/listings", 303)

    @app.post("/logout")
    async def logout(request: Request, csrf_token: Annotated[str, Form()] = ""):
        verify_csrf(request, csrf_token)
        sessions.pop(request.session.get("sid", ""), None)
        request.session.clear()
        return RedirectResponse("/login", 303)

    @app.get("/listings")
    async def listings(request: Request):
        # Authenticate before parsing filters or exposing seeded content.
        if not authenticated(request):
            return RedirectResponse("/login", 303)
        city = request.query_params.get("city", "").strip()
        tomorrow = date.today() + timedelta(days=1)
        check_in = request.query_params.get("check_in", tomorrow.isoformat())
        check_out = request.query_params.get(
            "check_out", (tomorrow + timedelta(days=1)).isoformat()
        )
        error = None
        try:
            start, end = date.fromisoformat(check_in), date.fromisoformat(check_out)
            if start < date.today() or end <= start or (end - start).days > 30:
                raise ValueError
        except ValueError:
            error = "Choose today or a future check-in, and a later check-out within 30 nights."
        if len(city) > 100:
            error = "City must contain no more than 100 characters."
        matches = (
            []
            if error
            else [x for x in LISTINGS if not city or x.city.casefold() == city.casefold()]
        )
        return templates.TemplateResponse(
            request=request,
            name="listings.html",
            status_code=400 if error else 200,
            context={
                "listings": matches,
                "city": city[:100],
                "check_in": check_in,
                "check_out": check_out,
                "error": error,
                "csrf": csrf(request),
            },
        )

    return app
