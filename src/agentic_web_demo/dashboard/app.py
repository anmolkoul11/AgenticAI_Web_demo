"""Loopback-only local accounts. Not an enterprise identity service."""

import asyncio
import os
import secrets
import socket
import threading
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agentic_web_demo import custom_service
from agentic_web_demo.capture import Capture
from agentic_web_demo.config import Settings
from agentic_web_demo.custom_extract import WebsiteInput
from agentic_web_demo.dashboard.accounts import Accounts
from agentic_web_demo.dashboard.credential_store import CredentialUnavailable
from agentic_web_demo.dashboard.service import Approval, PlanInput
from agentic_web_demo.exports import CONTENT_TYPES, ExportError, build_export
from agentic_web_demo.portal.app import PortalSettings

ASSETS = Path(__file__).parent / "static"
UI_VERSION = "2026-10-01.2"


class CustomApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    accept_partial: bool = False


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_ids: list[int] = Field(default_factory=list, max_length=5)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    password: SecretStr = Field(min_length=12, max_length=128)


class ModelKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=1024)
    model: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,100}$")
    remember: bool = False
    authorized: Literal[True]


class AdminAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable", "disable", "promote", "demote", "revoke_sessions"]
    password: SecretStr = Field(min_length=12, max_length=128)


def create_app(settings=None, service=None):
    instance_id = secrets.token_hex(16)
    settings = settings or PortalSettings.from_env()
    accounts = Accounts(
        service.data_dir if service else Settings.from_env().data_dir,
        service.policy_path if service else Path("config/rules.yaml"),
        service.target
        if service
        else os.environ.get("AGENTIC_DASHBOARD_PORTAL_URL", "http://127.0.0.1:8000"),
    )

    @asynccontextmanager
    async def lifespan(app):
        async def expire_sessions():
            while True:
                await asyncio.sleep(30)
                accounts.prune()
                with capture_lock:
                    for key, item in list(captures.items()):
                        if item[0] < time.monotonic() or accounts.get(item[1]) is None:
                            captures.pop(key, None)

        reaper = asyncio.create_task(expire_sessions())
        try:
            yield
        finally:
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper
            accounts.close()

    app = FastAPI(
        title="Agentic Demo Studio",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_urlsafe(48),
        session_cookie="dashboard_session",
        same_site="strict",
        max_age=3600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.state.accounts = accounts
    failures = []
    export_gate = threading.BoundedSemaphore(2)
    captures = {}
    capture_lock = threading.Lock()

    def active(request):
        return accounts.get(request.session.get("sid"))

    def user_service(request):
        session = active(request)
        if session is None:
            raise HTTPException(401, "Sign in again.")
        return accounts.service_for(session.user_id)

    def check_csrf(request):
        expected = request.session.get("csrf", "")
        supplied = request.headers.get("x-csrf-token", "")
        if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
            raise HTTPException(403, "Session expired; reload the dashboard.")
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Same-origin requests only.")

    @app.middleware("http")
    async def headers(request, call_next):
        supplied_version = request.headers.get("x-dashboard-version")
        if request.method == "POST" and supplied_version and supplied_version != UI_VERSION:
            return JSONResponse(
                {
                    "detail": "Application updated. Refresh before continuing.",
                    "code": "ui_outdated",
                },
                status_code=409,
                headers={"Cache-Control": "no-store"},
            )
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                "form-action 'self'; base-uri 'none'",
            }
        )
        return response

    @app.middleware("http")
    async def limit_body(request, call_next):
        if request.method == "POST":
            body = bytearray()
            limit = (
                160000
                if request.url.path in {"/api/custom/plans", "/api/custom/captures"}
                else 16000
            )
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > limit:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            # Starlette's cached middleware Request forwards this body downstream.
            request._body = bytes(body)
        return await call_next(request)

    # API guard is a dependency so session middleware has already populated scope.
    from fastapi import Depends

    def guard(request: Request):
        if not active(request):
            raise HTTPException(401, "Sign in to the local dashboard.")
        if request.method == "POST":
            check_csrf(request)

    def admin_guard(request: Request):
        guard(request)
        current = active(request)
        if current is None or accounts.profile(current.user_id)["role"] != "admin":
            raise HTTPException(403, "Administrator access required.")

    @app.exception_handler(CredentialUnavailable)
    async def credential_unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        if request.url.path == "/api/custom/plans":
            return JSONResponse(
                {
                    "detail": "Check URLs (browser: one HTTPS URL; static: 1-3 public URLs), "
                    "record limit (1-50), and both permission checkboxes. Pasted text needs one "
                    "source URL and 80-24,000 characters; instructions are optional. "
                    "Automatic sign-in needs website credentials; the HTTPS login URL is optional. "
                    "Normal browser mode requires its separate confirmation checkbox. "
                    "Business-rule fields use lowercase snake_case and require a value."
                },
                status_code=422,
            )
        if request.url.path in {"/api/register", "/api/login"}:
            return JSONResponse(
                {
                    "detail": "Use a username of 3–32 letters, numbers, dots, underscores or "
                    "hyphens and an account password of 12–128 characters. "
                    "If these are correct, refresh the application and try again."
                },
                status_code=422,
            )
        if request.url.path == "/api/model-key":
            return JSONResponse(
                {
                    "detail": "Enter a key and model ID, and confirm you are "
                    "authorized to use this key and its billing account."
                },
                status_code=422,
            )
        return JSONResponse(
            {
                "detail": "Invalid fields. Check the selected mode, required "
                "criteria and explicit API permission."
            },
            status_code=422,
        )

    @app.get("/")
    def index():
        return FileResponse(ASSETS / "index.html")

    @app.get("/api/session")
    def session(request: Request):
        if "csrf" not in request.session:
            request.session["csrf"] = secrets.token_urlsafe(32)
        current = active(request)
        return {
            "authenticated": current is not None,
            "csrf": request.session["csrf"],
            "username": current.username if current else None,
            "ui_version": UI_VERSION,
            "instance_id": instance_id,
        }

    def rate_limit():
        with accounts.lock:
            stamp = time.monotonic()
            failures[:] = [entry for entry in failures if entry > stamp - 60]
            if len(failures) >= 10:
                raise HTTPException(429, "Too many attempts. Wait one minute.")
            failures.append(stamp)

    @app.post("/api/register", status_code=201)
    def register(request: Request, values: Login):
        check_csrf(request)
        rate_limit()
        try:
            accounts.register(values.username, values.password.get_secret_value())
        except ValueError:
            raise HTTPException(409, "Account unavailable or account limit reached.") from None
        return {"status": "created"}

    @app.post("/api/login")
    def login(request: Request, values: Login):
        check_csrf(request)
        rate_limit()
        user_id = accounts.authenticate(values.username, values.password.get_secret_value())
        if user_id is None:
            raise HTTPException(401, "Incorrect username or password.")
        accounts.sign_out(request.session.get("sid"))
        request.session.clear()
        try:
            sid = accounts.sign_in(user_id, values.username)
        except ValueError:
            raise HTTPException(503, "Session capacity reached.") from None
        request.session.update(sid=sid, csrf=secrets.token_urlsafe(32))
        return {"csrf": request.session["csrf"]}

    @app.post("/api/logout", dependencies=[Depends(guard)])
    def logout(request: Request):
        accounts.sign_out(request.session.get("sid"))
        request.session.clear()
        return {"status": "signed_out"}

    @app.get("/api/admin/users", dependencies=[Depends(admin_guard)])
    def admin_users():
        return accounts.list_users()

    @app.get("/api/admin/audit", dependencies=[Depends(admin_guard)])
    def admin_audit():
        return accounts.audit_history()

    @app.post("/api/admin/users/{user_id}", dependencies=[Depends(admin_guard)])
    def admin_action(request: Request, user_id: str, values: AdminAction):
        rate_limit()
        current = active(request)
        if (
            current is None
            or accounts.authenticate(current.username, values.password.get_secret_value())
            != current.user_id
        ):
            raise HTTPException(403, "Confirm your administrator password.")
        try:
            accounts.manage(current.user_id, user_id, values.action)
        except PermissionError:
            raise HTTPException(403, "Administrator access required.") from None
        except ValueError as exc:
            raise HTTPException(
                409,
                "Action rejected: account unavailable, invalid ID, "
                "or administrator lockout protection.",
            ) from exc
        return {
            "status": "updated",
            "guidance": "Sessions revoked. Already-started jobs "
            "may finish; this does not revoke keys at OpenAI.",
        }

    @app.get("/api/config", dependencies=[Depends(guard)])
    def config(request: Request):
        from agentic_web_demo.rules import load_rules

        current = active(request)
        if current is None:
            raise HTTPException(401, "Sign in again.")
        service = user_service(request)
        from agentic_web_demo.portal.seed import CITIES

        return {
            "username": current.username,
            "role": accounts.profile(current.user_id)["role"],
            "credential_saved": bool(accounts.profile(current.user_id)["credential_saved"]),
            "secure_storage_available": accounts.credentials.available,
            "secure_storage_label": accounts.credentials.label,
            "credential_notice": current.credential_notice,
            "cities": [city for _, city in CITIES],
            "target": service.target,
            "adapter": "demo-hotels",
            "model": current.model_settings.model if current.model_settings else "Not configured",
            "model_configured": current.model_settings is not None,
            "policy": load_rules(service.policy_path).model_dump(mode="json"),
        }

    @app.post("/api/model-key", dependencies=[Depends(guard)])
    def model_key(request: Request, values: ModelKey):
        from agentic_web_demo.agents.openai_planner import ModelSettings

        try:
            model_settings = ModelSettings(
                model=values.model,
                api_key=values.api_key.get_secret_value().strip(),
                timeout_seconds=60,
                max_retries=0,
            )
            accounts.save_credential(request.session.get("sid"), model_settings, values.remember)
        except ValueError:
            raise HTTPException(400, "Invalid settings or expired session.") from None
        return {
            "status": "configured",
            "guidance": (
                "Saved in the OS credential store for this account."
                if values.remember
                else "Session only. Any previously saved key is unchanged."
            )
            + " Access and ownership are not verified; no API call was made.",
        }

    @app.post("/api/model-key/forget", dependencies=[Depends(guard)])
    def forget_key(request: Request):
        try:
            accounts.forget_credential(request.session.get("sid"))
        except ValueError:
            raise HTTPException(401, "Sign in again.") from None
        return {
            "status": "forgotten",
            "guidance": "Saved key removed and account sessions "
            "cleared of keys. Already-started work may finish.",
        }

    @app.post("/api/model-key/clear", dependencies=[Depends(guard)])
    def clear_key(request: Request):
        try:
            accounts.configure(request.session.get("sid"), None)
        except ValueError:
            raise HTTPException(401, "Sign in again.") from None
        return {"status": "cleared"}

    @app.get("/api/readiness", dependencies=[Depends(guard)])
    def readiness(request: Request):
        def reachable(address):
            try:
                with socket.create_connection(address, timeout=0.5):
                    return True
            except OSError:
                return False

        portal = urlsplit(accounts.target)
        broker = urlsplit(os.environ.get("NATS_URL", "nats://127.0.0.1:4222"))
        return {
            "portal_port_open": reachable((portal.hostname, portal.port or 80)),
            "nats_port_open": reachable((broker.hostname, broker.port or 4222)),
            "note": "TCP reachability only, not login, Chromium or JetStream verification.",
        }

    @app.post("/api/custom/captures", dependencies=[Depends(guard)], status_code=201)
    def receive_capture(request: Request, values: Capture):
        # No model call. Short-lived handoff tied to this exact signed-in session.
        stamp = time.monotonic()
        sid = request.session.get("sid")
        with capture_lock:
            for key, item in list(captures.items()):
                if item[0] < stamp or accounts.get(item[1]) is None:
                    captures.pop(key, None)
            if len(captures) >= 20:
                raise HTTPException(429, "Capture inbox full. Wait ten minutes.")
            capture_id = str(uuid4())
            captures[capture_id] = (stamp + 600, sid, values)
        return {"capture_id": capture_id}

    @app.post("/api/custom/captures/{capture_id}/claim", dependencies=[Depends(guard)])
    def claim_capture(request: Request, capture_id: str):
        with capture_lock:
            item = captures.get(capture_id)
            if not item or item[0] < time.monotonic() or item[1] != request.session.get("sid"):
                raise HTTPException(404, "Capture expired or belongs to another session.")
            captures.pop(capture_id)
        return item[2].model_dump(mode="json")

    @app.post("/api/custom/plans", dependencies=[Depends(guard)], status_code=202)
    def custom_plan(request: Request, values: WebsiteInput):
        current = active(request)
        if current is None:
            raise HTTPException(401, "Sign in again.")
        try:
            return {
                "job_id": custom_service.plan(
                    user_service(request),
                    values,
                    current.model_settings,
                    session_alive=lambda: accounts.get(request.session.get("sid")) is current,
                )
            }
        except RuntimeError:
            raise HTTPException(409, "Another job is active. Wait for it to finish.") from None
        except ValueError:
            raise HTTPException(
                400, "Configure your API key and check the custom source fields."
            ) from None

    @app.get("/api/custom/jobs/{job_id}/browser", dependencies=[Depends(guard)])
    def browser_status(request: Request, job_id: str):
        service = user_service(request)
        try:
            service.read(job_id)
        except (ValueError, OSError):
            raise HTTPException(404, "Job not found.") from None
        with service.lock:
            control = service.browser_controls.get(job_id)
        return (
            control.snapshot() if control else {"state": "closed", "guidance": "No active browser."}
        )

    @app.post("/api/custom/jobs/{job_id}/browser/{action}", dependencies=[Depends(guard)])
    def browser_action(
        request: Request,
        job_id: str,
        action: Literal[
            "capture",
            "cancel",
            "plan",
            "approve",
            "dismiss",
            "discover",
            "approve_links",
            "dismiss_links",
        ],
        values: BrowserAction,
    ):
        service = user_service(request)
        with service.lock:
            control = service.browser_controls.get(job_id)
        if control is None:
            raise HTTPException(404, "No active browser for this account and job.")
        try:
            control.command(action, values.selected_ids)
        except ValueError:
            raise HTTPException(409, "Browser is not ready. Refresh its status.") from None
        return {"status": "requested"}

    @app.post("/api/custom/plans/{plan_id}/execute", dependencies=[Depends(guard)], status_code=202)
    def custom_execute(request: Request, plan_id: str, values: CustomApproval):
        try:
            return {
                "job_id": custom_service.execute(
                    user_service(request),
                    plan_id,
                    values.revision,
                    accept_partial=values.accept_partial,
                )
            }
        except RuntimeError:
            raise HTTPException(409, "Another job is active. Wait for it to finish.") from None
        except (ValueError, OSError, KeyError):
            raise HTTPException(
                409, "Proposal unavailable or changed. Review a new preview."
            ) from None

    @app.post("/api/plans", dependencies=[Depends(guard)], status_code=202)
    def plan(request: Request, values: PlanInput):
        current = active(request)
        if current is None:
            raise HTTPException(401, "Sign in again.")
        try:
            return {"job_id": user_service(request).plan(values, current.model_settings)}
        except RuntimeError:
            raise HTTPException(409, "Another job is active; wait for it to finish.") from None
        except ValueError:
            raise HTTPException(
                400, "Add your API key for this session before model planning."
            ) from None

    @app.post("/api/plans/{plan_id}/execute", dependencies=[Depends(guard)], status_code=202)
    def execute(request: Request, plan_id: str, values: Approval):
        try:
            return {"job_id": user_service(request).execute(plan_id, values.revision)}
        except RuntimeError:
            raise HTTPException(409, "Another job is active; wait for it to finish.") from None
        except (ValueError, OSError):
            raise HTTPException(
                409, "Plan unavailable or changed. Create and review a new plan."
            ) from None

    @app.get("/api/jobs", dependencies=[Depends(guard)])
    def history(request: Request):
        return user_service(request).history()

    @app.get("/api/jobs/{job_id}", dependencies=[Depends(guard)])
    def job(request: Request, job_id: str):
        try:
            return user_service(request).read(job_id)
        except (ValueError, OSError):
            raise HTTPException(404, "Job not found") from None

    @app.get("/api/jobs/{job_id}/records", dependencies=[Depends(guard)])
    def records(request: Request, job_id: str):
        try:
            return user_service(request).records(job_id)
        except (ValueError, OSError):
            raise HTTPException(404, "No saved export available for this job") from None

    @app.get("/api/jobs/{job_id}/download/{format}", dependencies=[Depends(guard)])
    def download(
        request: Request,
        job_id: str,
        format: str,
        scope: Literal["all", "filtered"] = "all",
        search: str = Query(default="", max_length=200),
        outcome: Literal["all", "matched", "unmatched"] = "all",
    ):
        if format not in CONTENT_TYPES:
            raise HTTPException(404, "Unsupported export format")
        if not export_gate.acquire(blocking=False):
            raise HTTPException(429, "Another download is being prepared. Try again shortly.")
        try:
            payload = records(request, job_id)
            evidence = job(request, job_id)
            result = evidence.get("result", {})
            run_id = str(UUID(result["run_id"]))
            content, mime = build_export(
                payload,
                format,
                run_id=run_id,
                framework=evidence.get("framework", ""),
                decisions=(result.get("evaluation") or {}).get("decisions", []),
                scope=scope,
                search=search,
                outcome=outcome,
            )
            return Response(
                content,
                media_type=mime,
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="records-{run_id}-{scope}.{format}"'
                    ),
                    "Cache-Control": "no-store",
                },
            )
        except ExportError as exc:
            raise HTTPException(422, str(exc)) from None
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "Saved records could not be exported.") from None
        finally:
            export_gate.release()

    app.mount("/static", StaticFiles(directory=ASSETS), name="static")
    return app
