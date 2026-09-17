"""Local review artifacts, revision-bound approval and single-attempt execution.

Not a multi-user authorization system. A digest detects changes relative to the
reviewed revision, not malicious writers with access to the local account.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from agentic_web_demo.agents.planning import Plan, validate_candidate
from agentic_web_demo.browser import portal_origin
from agentic_web_demo.rules import Rules


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1, 2] = 1
    framework: Literal["langgraph", "crewai"] = "langgraph"
    plan_id: UUID
    adapter: Literal["demo-hotels"] = "demo-hotels"
    use_case: Literal["hotel-search-v1"] = "hotel-search-v1"
    source: Literal["structured", "model-assisted"]
    request: str | None = None
    plan: Plan
    policy: Rules
    base_url: str
    created_at: datetime
    expires_at: datetime
    model: dict


def revision(proposal: Proposal) -> str:
    payload = proposal.model_dump(mode="json")
    if proposal.version == 1:
        if proposal.framework != "langgraph":
            raise ValueError("Version 1 supports LangGraph only")
        payload.pop("framework")  # Preserve existing v1 review hashes.
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def plan_path(data_dir: Path, plan_id: str) -> Path:
    return data_dir / "plans" / (str(UUID(str(plan_id))) + ".json")


def save_proposal(
    data_dir, plan, policy, base_url, *, source, request=None, model=None, framework="langgraph"
):
    checked = validate_candidate(plan, date.today(), policy)
    if checked["status"] != "running":
        raise ValueError("Only complete policy-compliant plans can be proposed.")
    now = datetime.now(UTC)
    proposal = Proposal(
        version=2,
        framework=framework,
        plan_id=uuid4(),
        source=source,
        request=request,
        plan=Plan.model_validate(checked["plan"]),
        policy=policy,
        base_url=portal_origin(base_url),
        created_at=now,
        expires_at=now + timedelta(hours=24),
        model=model or {},
    )
    path = plan_path(data_dir, str(proposal.plan_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(proposal.model_dump_json(indent=2))
    return proposal


def load_proposal(data_dir, plan_id):
    path = plan_path(data_dir, plan_id)
    if path.stat().st_size > 65536:
        raise ValueError("Oversized plan artifact.")
    proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
    if str(proposal.plan_id) != str(UUID(plan_id)):
        raise ValueError("Plan ID mismatch.")
    portal_origin(proposal.base_url)
    return proposal


class NoModel:
    mode = "approved-plan"

    def plan(self, *args):
        raise AssertionError("Approved execution must never call a planner.")


def execute_proposal(
    data_dir, plan_id, approval, policy, tools, *, progress=None, framework="langgraph"
):
    from agentic_web_demo.agents.runners import get_runner

    proposal = load_proposal(data_dir, plan_id)
    if proposal.framework != framework or (proposal.version == 1 and framework != "langgraph"):
        raise ValueError("Framework differs from reviewed proposal")
    run_workflow = get_runner(framework)
    if approval != revision(proposal):
        raise ValueError("Approval must match the reviewed revision.")
    if proposal.expires_at <= datetime.now(UTC):
        raise ValueError("Plan expired; create and review a new proposal.")
    if proposal.policy.fingerprint() != policy.fingerprint():
        raise ValueError("Policy changed; create and review a new proposal.")
    if portal_origin(tools.base_url) != proposal.base_url:
        raise ValueError("Execution target differs from the reviewed target.")
    candidate = proposal.plan.model_dump(mode="json")
    if validate_candidate(candidate, date.today(), policy)["status"] != "running":
        raise ValueError("Plan no longer valid.")
    claim = plan_path(data_dir, plan_id).with_suffix(".attempt.json")
    # Exclusive creation prevents concurrent/repeated execution under this plan ID.
    # Keep the claim after crashes/failures: replaying side effects is not safe.
    with claim.open("x", encoding="utf-8") as handle:
        json.dump({"revision": approval, "started_at": datetime.now(UTC).isoformat()}, handle)
    result = run_workflow(
        "", NoModel(), tools, policy=policy, saved_plan=candidate, progress=progress
    )
    result.update(
        plan_id=str(proposal.plan_id),
        approved_revision=approval,
        planning_source=proposal.source,
        planning_model=proposal.model,
    )
    report = plan_path(data_dir, plan_id).with_suffix(".result.json")
    with report.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result
