"""Bounded background jobs; no automatic retry or replay of model/tools."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentic_web_demo.agents.planning import validate_candidate
from agentic_web_demo.agents.runners import get_runner
from agentic_web_demo.agents.saved_plans import (
    execute_proposal,
    load_proposal,
    revision,
    save_proposal,
)
from agentic_web_demo.agents.tools import DemoTools
from agentic_web_demo.browser import portal_origin
from agentic_web_demo.messaging import Broker
from agentic_web_demo.rules import load_rules

STAGES = {
    "inspect_website",
    "extract_content",
    "review_content",
    "plan_request",
    "validate_plan",
    "extract",
    "save",
    "export",
    "evaluate",
    "publish",
    "receive",
    "verify",
}


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    framework: Literal["langgraph", "crewai"]
    mode: Literal["structured", "model-assisted"]
    city: str | None = Field(default=None, max_length=100)
    all_cities: bool = False
    check_in: date | None = None
    check_out: date | None = None
    min_price: str | None = Field(default=None, max_length=30)
    max_price: str | None = Field(default=None, max_length=30)
    min_rating: str | None = Field(default=None, max_length=30)
    request: str | None = Field(default=None, max_length=2000)
    allow_model_api: bool = False

    @model_validator(mode="after")
    def exclusive_paths(self):
        fields = (
            self.city,
            self.check_in,
            self.check_out,
            self.min_price,
            self.max_price,
            self.min_rating,
        )
        if self.mode == "model-assisted":
            if not self.allow_model_api or not self.request or not self.request.strip():
                raise ValueError("Model planning needs a request and explicit API consent")
            if any(value is not None for value in fields) or self.all_cities:
                raise ValueError("Do not mix planning paths")
        elif self.request is not None or self.allow_model_api:
            raise ValueError("Structured planning cannot request a model call")
        elif self.all_cities == (self.city is not None) or (
            self.city is not None and not self.city.strip()
        ):
            raise ValueError("Choose a city or explicitly select all cities")
        return self


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")


def now():
    return datetime.now(UTC).isoformat()


class DashboardService:
    def __init__(
        self,
        data_dir: Path,
        policy_path: Path,
        target: str,
        *,
        gate=None,
        broker_stream="AGENTIC_DEMO",
    ):
        self.gate = gate or threading.Semaphore(1)
        self.broker_stream = broker_stream
        self.data_dir, self.policy_path = data_dir, policy_path
        self.target = portal_origin(target)
        self.directory = data_dir / "dashboard-jobs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.busy = False
        self.browser_controls = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="demo-dashboard")
        # A restart is not permission to repeat a model call or side effect.
        for path in self.directory.glob("*.json"):
            try:
                job = self.read(path.stem)
                if job["status"] in {"queued", "running"}:
                    job.update(
                        status="interrupted",
                        guidance="Server restarted. Inspect saved "
                        "plan/result artifacts; do not blindly repeat execution.",
                    )
                    self.write(job)
            except (ValueError, KeyError, OSError):
                continue

    def close(self):
        with self.lock:
            for control in self.browser_controls.values():
                control.cancel.set()
        self.pool.shutdown(wait=True, cancel_futures=False)

    def read(self, job_id):
        path = self.directory / f"{UUID(str(job_id))}.json"
        with self.lock:
            if path.stat().st_size > 4_000_000:
                raise ValueError("Oversized job")
            return json.loads(path.read_text(encoding="utf-8"))

    def write(self, job):
        with self.lock:
            path = self.directory / f"{UUID(job['job_id'])}.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(job, indent=2), encoding="utf-8")
            temporary.replace(path)

    def history(self):
        paths = sorted(
            self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:100]
        jobs = []
        for path in paths:
            try:
                job = self.read(path.stem)
                jobs.append(
                    {
                        key: job.get(key)
                        for key in (
                            "job_id",
                            "kind",
                            "framework",
                            "status",
                            "created_at",
                            "plan_id",
                        )
                    }
                )
            except (ValueError, OSError):
                continue
        return jobs

    def submit(self, kind, framework, operation, plan_id=None):
        with self.lock:
            if self.busy or not self.gate.acquire(blocking=False):
                raise RuntimeError("Another job is active")
            self.busy = True
            job = dict(
                job_id=str(uuid4()),
                kind=kind,
                framework=framework,
                status="queued",
                created_at=now(),
                stages=[],
                plan_id=plan_id,
            )
            try:
                self.write(job)
                self.pool.submit(self.work, job, operation)
            except Exception:
                self.busy = False
                self.gate.release()
                raise
            return job["job_id"]

    def work(self, job, operation):
        def progress(stage):
            if stage in STAGES:
                job["stages"].append({"stage": stage, "started_at": now()})
                self.write(job)

        try:
            job["status"] = "running"
            self.write(job)
            result = operation(progress)
            job.update(status=result["status"], result=result)
            if "proposal" in result:
                job["plan_id"] = result["proposal"]["plan_id"]
        except Exception:
            # Never serialize exceptions: SDK/browser errors can contain secrets.
            job.update(
                status="failed",
                guidance="Operation stopped. Check configuration, "
                "plan expiry/revision and service availability. No automatic retry. "
                "For execution, inspect data/plans before creating another attempt.",
            )
        finally:
            with self.lock:
                try:
                    job["finished_at"] = now()
                    self.write(job)
                finally:
                    self.busy = False
                    self.gate.release()

    def plan(self, values: PlanInput, model_settings=None):
        if values.mode == "model-assisted" and model_settings is None:
            raise ValueError("Configure a session API key first")

        def operation(progress):
            policy = load_rules(self.policy_path)
            metadata = {}
            if values.mode == "structured":
                progress("validate_plan")
                result = validate_candidate(
                    dict(
                        city="" if values.all_cities else values.city,
                        check_in=values.check_in,
                        check_out=values.check_out,
                        min_price=values.min_price,
                        max_price=values.max_price,
                        min_rating=values.min_rating,
                    ),
                    date.today(),
                    policy,
                )
                if result["status"] != "running":
                    return result
            else:
                from agentic_web_demo.agents.openai_planner import OpenAIPlanner

                planner = OpenAIPlanner(model_settings)
                if values.framework == "crewai":
                    from agentic_web_demo.agents.crewai_planner import CrewAIPlanner

                    planner = CrewAIPlanner(planner)
                result = get_runner(values.framework)(
                    values.request, planner, None, policy=policy, plan_only=True, progress=progress
                )
                if result["status"] != "planned":
                    return result
                metadata = result["model"]
            proposal = save_proposal(
                self.data_dir,
                result["plan"],
                policy,
                self.target,
                source=values.mode,
                request=values.request,
                model=metadata,
                framework=values.framework,
            )
            return dict(
                status="awaiting_review",
                proposal=proposal.model_dump(mode="json"),
                revision=revision(proposal),
                trace=result.get("trace", ["validate_plan:ok"]),
                guidance="Review the original request, "
                "every criterion and target. Approval does not prove semantic accuracy.",
            )

        return self.submit("plan", values.framework, operation)

    def execute(self, plan_id, approval):
        proposal = load_proposal(self.data_dir, plan_id)
        if proposal.base_url != self.target or revision(proposal) != approval:
            raise ValueError("Target or revision mismatch")

        def operation(progress):
            tools = DemoTools(
                self.data_dir,
                Broker(
                    url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
                    stream=self.broker_stream,
                ),
                base_url=self.target,
            )
            return execute_proposal(
                self.data_dir,
                plan_id,
                approval,
                load_rules(self.policy_path),
                tools,
                progress=progress,
                framework=proposal.framework,
            )

        return self.submit("execute", proposal.framework, operation, plan_id)

    def records(self, job_id):
        job = self.read(job_id)
        run_id = str(UUID(job.get("result", {}).get("run_id", "")))
        # Never use a filesystem path supplied by the browser or report.
        path = self.data_dir / "exports" / f"{run_id}.json"
        if path.stat().st_size > 4_000_000:
            raise ValueError("Oversized export")
        return json.loads(path.read_text(encoding="utf-8"))
