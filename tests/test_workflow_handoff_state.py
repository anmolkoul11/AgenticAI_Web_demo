"""Authored offline regressions; implementation did not execute these fixtures."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_custom_website import service

from agentic_web_demo import custom_service
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.extension_channel import ExtensionChannel, ExtensionRuns


def job(service, *, plan_id, kind="custom-execute", status="completed", created="2026-11-09T10:00:00+00:00", run_id=None):
    value = {"job_id": str(uuid4()), "kind": kind, "framework": "langgraph",
             "plan_id": plan_id, "status": status, "created_at": created,
             "result": {"guidance": status, **({"run_id": run_id} if run_id else {})}}
    service.write(value)
    return value


def proposal(service):
    value = {"plan_id": str(uuid4()), "expires_at": "2020-01-01T00:00:00+00:00"}
    custom_service.write_json(service.data_dir / "website-plans" / f"{value['plan_id']}.json", value)
    return value, custom_service.digest(value)


def test_existing_saved_attempt_wins_later_duplicate_failure(service, monkeypatch):
    value, revision = proposal(service)
    original = job(service, plan_id=value["plan_id"], run_id=str(uuid4()))
    job(service, plan_id=value["plan_id"], status="failed", created="2026-11-09T10:01:00+00:00")
    monkeypatch.setattr(custom_service, "_execute_new", lambda *_a, **_k: pytest.fail("Approval replayed"))
    assert custom_service.execute(service, value["plan_id"], revision) == original["job_id"]
    with pytest.raises(WebsiteError, match="changed"):
        custom_service.execute(service, value["plan_id"], "0" * 64)


@pytest.mark.parametrize("state", ["queued", "running", "failed", "interrupted", "completed"])
def test_original_attempt_is_followed_in_every_state(service, monkeypatch, state):
    value, revision = proposal(service)
    original = job(service, plan_id=value["plan_id"], status=state)
    monkeypatch.setattr(custom_service, "_execute_new", lambda *_a, **_k: pytest.fail("Approval replayed"))
    assert custom_service.execute(service, value["plan_id"], revision) == original["job_id"]


def test_two_approval_requests_share_one_submission(service, monkeypatch):
    value, revision = proposal(service)
    submissions = []

    def submit(*_args, **_kwargs):
        submitted = job(service, plan_id=value["plan_id"], status="queued")
        submissions.append(submitted["job_id"])
        return submitted["job_id"]

    monkeypatch.setattr(custom_service, "_execute_new", submit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: custom_service.execute(service, value["plan_id"], revision), range(2)))
    assert len(submissions) == 1
    assert ids == submissions * 2


def test_review_job_resolves_saved_execution_and_channel_reports_same_state(service):
    plan_id, saved_run = str(uuid4()), str(uuid4())
    review = job(service, plan_id=plan_id, kind="custom-plan", status="awaiting_review")
    saved = job(service, plan_id=plan_id, run_id=saved_run)
    control = BrowserControl()
    control.update("captured", "Collection finished")
    channel = ExtensionChannel(tab_id=7, url="https://example.org/", control=control, alive=lambda: True)
    manager = ExtensionRuns("fixture")
    account = object()
    item = manager.add(sid="session", current=account, service=service, channel=channel)
    item["job_id"] = review["job_id"]
    snapshot = manager.snapshot(item)
    resolved = custom_service.workflow_job(service, review["job_id"])
    assert snapshot["state"] == resolved["status"] == "completed"
    assert snapshot["job_id"] == resolved["job_id"] == saved["job_id"]
    assert snapshot["plan_job_id"] == review["job_id"]
    assert snapshot["saved_run_id"] == saved_run
    assert resolved["workflow"]["execution_job_id"] == saved["job_id"]


def test_extraction_is_reviewing_until_plan_job_finishes(service):
    preparing = job(service, plan_id=None, kind="custom-plan", status="running")
    control = BrowserControl()
    control.update("captured", "Collection finished")
    channel = ExtensionChannel(tab_id=7, url="https://example.org/", control=control, alive=lambda: True)
    manager = ExtensionRuns("fixture")
    item = manager.add(sid="session", current=object(), service=service, channel=channel)
    item["job_id"] = preparing["job_id"]
    assert manager.snapshot(item)["state"] == "reviewing"


def test_allocated_run_identity_is_not_proof_of_saved_results(service):
    plan_id, allocated_run = str(uuid4()), str(uuid4())
    failed = job(service, plan_id=plan_id, status="failed", run_id=allocated_run)
    assert custom_service.workflow_job(service, failed["job_id"])["workflow"]["saved_run_id"] is None
    failed["result"]["trace"] = ["validate_plan:ok", "save:ok", "publish:failed"]
    service.write(failed)
    assert custom_service.workflow_job(service, failed["job_id"])["workflow"]["saved_run_id"] == allocated_run


def test_status_only_ownership_does_not_restore_browser_authority(service):
    channel = ExtensionChannel(tab_id=7, url="https://example.org/", control=BrowserControl(),
                               alive=lambda: True, clock=lambda: 0)
    manager, account = ExtensionRuns("fixture"), object()
    item = manager.add(sid="session", current=account, service=service, channel=channel)
    channel.clock = lambda: 1000
    assert manager.owned(channel.run_id, "session", account, check_channel=False) is item
    with pytest.raises(WebsiteError):
        manager.owned(channel.run_id, "session", account)
    with pytest.raises(KeyError):
        manager.owned(channel.run_id, "other-session", account, check_channel=False)
