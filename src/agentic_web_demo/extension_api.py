"""Authenticated dashboard relay for the opt-in current-tab execution mode."""

from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from agentic_web_demo import custom_service
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_extract import Condition, WebsiteInput
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.extension_channel import ERROR_CODES, ExtensionChannel


class ExtensionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    tab_id: StrictInt = Field(ge=0, le=2_147_483_647)
    instructions: str = Field(min_length=1, max_length=2000)
    record_limit: StrictInt = Field(default=25, ge=1, le=50)
    output_fields: list[str] = Field(default_factory=list, max_length=16)
    business_rules: list[Condition] = Field(default_factory=list, max_length=5)
    publish_event: StrictBool = False
    agent_confirmed: StrictBool
    agent_visual_confirmed: StrictBool = False
    authorized: StrictBool
    allow_model_api: StrictBool

    @model_validator(mode="after")
    def consent(self):
        if not all((self.agent_confirmed, self.authorized, self.allow_model_api)):
            raise ValueError("Explicit workflow and paid-model consent required")
        if self.agent_visual_confirmed:
            raise ValueError("This extension version supports DOM observations only")
        return self


class ExtensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    ok: StrictBool
    result: dict | None = None
    error: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def outcome(self):
        if self.ok:
            if self.result is None or self.error is not None:
                raise ValueError("Successful command requires a result and no error")
        elif self.error not in ERROR_CODES or self.result is not None:
            raise ValueError("Failed command requires a known error and no result")
        return self


class ExtensionControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "collect", "cancel"]


def register_extension_routes(app, *, manager, accounts, active, user_service, guard):
    def extension_guard(request: Request):
        guard(request)
        if request.headers.get("x-dashboard-instance") != manager.instance_id:
            raise HTTPException(409, "Dashboard changed. Reconnect the extension to this dashboard.")

    def owned(request, run_id):
        try:
            return manager.owned(run_id, request.session.get("sid"), active(request))
        except KeyError:
            raise HTTPException(404, "Extension run unavailable for this signed-in session.") from None
        except WebsiteError:
            raise HTTPException(410, "Extension run expired or was cancelled. The website tab stays open.") from None

    dependency = [Depends(extension_guard)]

    @app.post("/api/extension/runs", dependencies=dependency, status_code=202)
    def start(request: Request, values: ExtensionStart):
        from agentic_web_demo.extension_browser import read_extension

        current = active(request)
        if current is None:
            raise HTTPException(401, "Sign in again.")
        if current.model_settings is None:
            raise HTTPException(400, "Configure your API connection in the dashboard first.")
        try:
            task = WebsiteInput(
                source="extension", framework="langgraph", workflow_mode="automatic",
                urls=[values.url], instructions=values.instructions,
                record_limit=values.record_limit, output_fields=values.output_fields,
                business_rules=values.business_rules, publish_event=values.publish_event,
                authorized=True, allow_model_api=True, agent_confirmed=True,
            )
        except ValueError:
            raise HTTPException(422, "Use one public HTTPS tab, a task and valid source fields/rules.") from None
        sid = request.session.get("sid")
        alive = lambda: accounts.get(sid) is current
        control = BrowserControl(alive)
        control.browser_mode, control.browser_channel = "normal", "extension"
        control.configure_workflow(task)
        control.update("agent_running", "Working in your selected browser tab. You can pause or cancel here.")
        channel = ExtensionChannel(tab_id=values.tab_id, url=task.urls[0], control=control, alive=alive)
        service = user_service(request)
        try:
            item = manager.add(sid=sid, current=current, service=service, channel=channel)
        except ValueError:
            raise HTTPException(429, "Extension session capacity reached. Try again later.") from None
        try:
            job_id = custom_service.plan(
                service, task, current.model_settings, session_alive=alive,
                extension_reader=lambda task, control, settings: read_extension(task, control, settings, channel),
                browser_control=control,
            )
        except (RuntimeError, ValueError):
            channel.stop()
            with manager.lock:
                manager.runs.pop(channel.run_id, None)
            raise HTTPException(409, "Another job is active or the extension task cannot start.") from None
        item["job_id"] = job_id
        return {"run_id": channel.run_id, "job_id": job_id, "instance_id": manager.instance_id}

    @app.get("/api/extension/runs/{run_id}", dependencies=dependency)
    def status(request: Request, run_id: str):
        try:
            return manager.snapshot(owned(request, run_id))
        except (ValueError, OSError):
            raise HTTPException(404, "Extension job unavailable.") from None

    @app.post("/api/extension/runs/{run_id}/next", dependencies=dependency)
    def next_command(request: Request, run_id: str):
        return {"command": owned(request, run_id)["channel"].claim()}

    @app.post("/api/extension/runs/{run_id}/result", dependencies=dependency)
    def acknowledge(request: Request, run_id: str, values: ExtensionResult):
        channel = owned(request, run_id)["channel"]
        try:
            result = channel.acknowledge(
                values.request_id, ok=values.ok, result=values.result, error=values.error,
            )
        except ValueError:
            raise HTTPException(409, "Command acknowledgement is invalid, stale or conflicts with an earlier result.") from None
        return {"status": result}

    @app.post("/api/extension/runs/{run_id}/control", dependencies=dependency)
    def control(request: Request, run_id: str, values: ExtensionControl):
        item = owned(request, run_id)
        channel = item["channel"]
        try:
            channel.request_control(values.action)
        except ValueError:
            raise HTTPException(409, "That action is unavailable in the current extension state.") from None
        return {"status": "requested", **manager.snapshot(item)}
