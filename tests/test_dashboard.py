"""Dashboard tests: no real models, browsers, broker or network services."""

import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService, PlanInput
from agentic_web_demo.portal.app import PortalSettings

SETTINGS = PortalSettings("demo", "synthetic-password-only", "synthetic-secret-" * 4)


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


@pytest.fixture
def client(service):
    with TestClient(create_app(SETTINGS, service), base_url="http://localhost") as client:
        client.app.state.accounts.register("demo", SETTINGS.password)
        yield client


def login(client):
    token = client.get("/api/session").json()["csrf"]
    response = client.post(
        "/api/login",
        json={"username": "demo", "password": SETTINGS.password},
        headers={"Origin": "http://localhost", "X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return {"Origin": "http://localhost", "X-CSRF-Token": response.json()["csrf"]}


def fields():
    return dict(
        framework="langgraph",
        mode="structured",
        city="New York",
        check_in=(date.today() + timedelta(days=7)).isoformat(),
        check_out=(date.today() + timedelta(days=9)).isoformat(),
        max_price="200",
        min_rating="4",
    )


def finished(service, job_id, timeout=30):
    # Standalone dashboard tests import CrewAI lazily in the worker. Its first
    # import can exceed two seconds; the full suite often already has it loaded.
    # This is a completion deadline, not a fixed delay or relaxed result assertion.
    deadline = time.monotonic() + timeout
    job = {}
    while time.monotonic() < deadline:
        job = service.read(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError(
        f"Offline job did not finish within {timeout}s: "
        f"kind={job.get('kind')}, framework={job.get('framework')}, "
        f"status={job.get('status')}, stages={job.get('stages', [])}"
    )


def test_auth_csrf_and_no_secret_echo(client):
    assert client.get("/api/jobs").status_code == 401
    assert (
        client.post(
            "/api/login", json={"username": "demo", "password": SETTINGS.password}
        ).status_code
        == 403
    )
    headers = login(client)
    assert client.get("/api/jobs").status_code == 200
    assert client.post("/api/plans", json=fields()).status_code == 403
    assert (
        client.post(
            "/api/plans", json=fields(), headers={**headers, "Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    response = client.post(
        "/api/plans", json={**fields(), "password": "secret-sentinel"}, headers=headers
    )
    assert response.status_code == 422
    assert "secret-sentinel" not in response.text
    assert client.post("/api/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/jobs").status_code == 401


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_structured_proposal_requires_review(client, service, framework):
    headers = login(client)
    user_id = client.app.state.accounts.authenticate("demo", SETTINGS.password)
    service = client.app.state.accounts.service_for(user_id)
    response = client.post("/api/plans", json={**fields(), "framework": framework}, headers=headers)
    assert response.status_code == 202
    job = finished(service, response.json()["job_id"])
    assert job["status"] == "awaiting_review"
    assert job["result"]["proposal"]["framework"] == framework
    assert job["result"]["proposal"]["model"] == {}
    assert not list((service.data_dir / "plans").glob("*.attempt.json"))
    assert (
        client.post(
            f"/api/plans/{job['plan_id']}/execute", json={"revision": "0" * 64}, headers=headers
        ).status_code
        == 409
    )


def test_paid_permission_and_mode_validation(client):
    headers = login(client)
    payload = dict(framework="crewai", mode="model-assisted", request="synthetic request")
    assert client.post("/api/plans", json=payload, headers=headers).status_code == 422
    assert (
        client.post(
            "/api/plans",
            json={**payload, "allow_model_api": True, "city": "Boston"},
            headers=headers,
        ).status_code
        == 422
    )


def test_single_worker_and_sanitized_failure(service):
    release = threading.Event()

    def operation(progress):
        progress("extract")
        release.wait(timeout=3)
        raise ValueError("secret-sentinel")

    first = service.submit("execute", "langgraph", operation)
    try:
        with pytest.raises(RuntimeError):
            service.submit("plan", "crewai", operation)
    finally:
        release.set()
    job = finished(service, first)
    assert job["status"] == "failed"
    assert "secret-sentinel" not in json.dumps(job)
    assert job["stages"][0]["stage"] == "extract"


def test_restart_does_not_replay(service):
    job_id = str(uuid4())
    service.write(dict(job_id=job_id, status="running", kind="execute"))
    second = DashboardService(service.data_dir, service.policy_path, service.target)
    try:
        assert second.read(job_id)["status"] == "interrupted"
    finally:
        second.close()


def test_export_boundaries_and_csv_formula(client, service):
    login(client)
    user_id = client.app.state.accounts.authenticate("demo", SETTINGS.password)
    service = client.app.state.accounts.service_for(user_id)
    job_id, run_id = str(uuid4()), str(uuid4())
    service.write(dict(job_id=job_id, status="completed", result={"run_id": run_id}))
    directory = service.data_dir / "exports"
    directory.mkdir()
    (directory / f"{run_id}.json").write_text(
        json.dumps({"listings": [{"title": "=BAD()", "city": "Boston", "listing_id": "BOS-1"}]}),
        encoding="utf-8",
    )
    response = client.get(f"/api/jobs/{job_id}/download/csv")
    assert response.status_code == 200 and "'=BAD()" in response.text
    for format in ("xlsx", "json", "jsonl"):
        response = client.get(f"/api/jobs/{job_id}/download/{format}")
        assert response.status_code == 200
        assert run_id in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store"
    response = client.get(f"/api/jobs/{job_id}/download/json?scope=filtered&search=missing")
    assert response.json()["listings"] == []
    assert client.get(f"/api/jobs/{job_id}/download/csv?scope=invalid").status_code == 422
    assert client.get("/api/jobs/not-a-uuid/records").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/download/exe").status_code == 404


def test_large_body_and_security_headers(client):
    headers = login(client)
    response = client.post("/api/plans", json={"request": "x" * 17000}, headers=headers)
    assert response.status_code == 413
    page = client.get("/")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-store"


def test_unknown_target_cannot_be_selected(client):
    headers = login(client)
    assert (
        client.post(
            "/api/plans", json={**fields(), "base_url": "https://example.org"}, headers=headers
        ).status_code
        == 422
    )
    with pytest.raises(ValueError):
        PlanInput(**{**fields(), "city": ""})


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_approved_execution_uses_shared_guards_and_prevents_replay(service, monkeypatch, framework):
    from test_langgraph import FakeTools

    tools = FakeTools()
    tools.base_url = service.target
    monkeypatch.setattr("agentic_web_demo.dashboard.service.DemoTools", lambda *a, **k: tools)
    planned = finished(service, service.plan(PlanInput(**{**fields(), "framework": framework})))
    approval = planned["result"]["revision"]
    plan_id = planned["plan_id"]
    executed = finished(service, service.execute(plan_id, approval))
    assert executed["status"] == "completed"
    assert executed["result"]["receipts_verified"] == 2
    assert executed["result"]["model_api_attempted"] is False
    calls = list(tools.calls)
    repeated = finished(service, service.execute(plan_id, approval))
    assert repeated["status"] == "failed"
    assert tools.calls == calls


def test_model_plan_saves_without_tools(service, monkeypatch):
    from agentic_web_demo.agents.openai_planner import OpenAIPlanner
    from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner

    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("AGENTIC_MODEL_NAME", "fixture-model")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")

    def fake_plan(self, request, today):
        self.metadata = {"provider": "openai", "response_received": True}
        return SimulatedPlanner().plan(SCENARIOS["new-york"], today)

    monkeypatch.setattr(OpenAIPlanner, "plan", fake_plan)
    payload = PlanInput(
        framework="langgraph", mode="model-assisted", request="synthetic", allow_model_api=True
    )
    from agentic_web_demo.agents.openai_planner import ModelSettings

    job = finished(service, service.plan(payload, ModelSettings("fixture-model", "fixture-only")))
    assert job["status"] == "awaiting_review"
    assert job["result"]["proposal"]["source"] == "model-assisted"
    assert not list((service.data_dir / "plans").glob("*.attempt.json"))
