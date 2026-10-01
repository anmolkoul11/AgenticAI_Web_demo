"""Local account and credential isolation; all provider calls are mocked."""

import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_dashboard import SETTINGS, fields, finished

from agentic_web_demo.dashboard.accounts import Accounts
from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService


def sign_in(client, username):
    csrf = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost", "X-CSRF-Token": csrf}
    result = client.post(
        "/api/login",
        json={"username": username, "password": "account-test-password"},
        headers=headers,
    )
    assert result.status_code == 200
    return {**headers, "X-CSRF-Token": result.json()["csrf"]}


@pytest.fixture
def site(tmp_path):
    template = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    app = create_app(SETTINGS, template)
    accounts = app.state.accounts
    accounts.register("alice", "account-test-password")
    accounts.register("bob", "account-test-password")
    with TestClient(app, base_url="http://localhost") as client:
        yield client, accounts
    template.close()


def test_registration_without_code_and_passwords_are_hashed(site):
    client, accounts = site
    token = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost", "X-CSRF-Token": token}
    payload = {
        "username": "carol",
        "password": "account-test-password",
    }
    response = client.post("/api/register", json=payload)
    assert response.status_code == 403 and payload["password"] not in response.text
    assert client.post("/api/register", json=payload, headers=headers).status_code == 201
    assert client.post("/api/register", json=payload, headers=headers).status_code == 409
    assert accounts.authenticate("CAROL", payload["password"])
    assert accounts.authenticate("carol", "incorrect-password") is None
    with sqlite3.connect(accounts.database) as db:
        rows = db.execute("SELECT salt, digest FROM accounts").fetchall()
    assert len({row[1] for row in rows}) == 3  # Same password, independently salted.
    assert b"account-test-password" not in accounts.database.read_bytes()


def test_cross_user_jobs_approval_and_exports_are_blocked(site):
    client, accounts = site
    alice_headers = sign_in(client, "alice")
    user_id = accounts.authenticate("alice", "account-test-password")
    alice = accounts.service_for(user_id)
    response = client.post("/api/plans", json=fields(), headers=alice_headers)
    job = finished(alice, response.json()["job_id"])
    job_id = job["job_id"]
    client.post("/api/logout", json={}, headers=alice_headers)
    bob_headers = sign_in(client, "bob")
    assert client.get("/api/jobs").json() == []
    for suffix in (
        "",
        "/records",
        "/download/json",
        "/download/csv",
        "/download/xlsx",
        "/download/jsonl",
    ):
        assert client.get(f"/api/jobs/{job_id}{suffix}").status_code == 404
    assert (
        client.post(
            f"/api/plans/{job['plan_id']}/execute",
            json={"revision": job["result"]["revision"]},
            headers=bob_headers,
        ).status_code
        == 409
    )
    bob = accounts.service_for(accounts.authenticate("bob", "account-test-password"))
    assert alice.data_dir != bob.data_dir and alice.broker_stream != bob.broker_stream
    assert alice.gate is bob.gate


def test_keys_are_session_only_and_no_environment_fallback(site, monkeypatch):
    client, accounts = site
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-must-not-be-used")
    headers = sign_in(client, "alice")
    request = {
        "framework": "langgraph",
        "mode": "model-assisted",
        "request": "synthetic",
        "allow_model_api": True,
    }
    assert client.post("/api/plans", json=request, headers=headers).status_code == 400
    key = "session-key-sentinel"
    response = client.post(
        "/api/model-key",
        json={"api_key": key, "model": "fixture-model", "authorized": True},
        headers=headers,
    )
    assert response.status_code == 200 and key not in response.text
    assert client.get("/api/config").json()["model_configured"] is True
    assert key not in client.get("/api/config").text
    assert key not in str(client.cookies)
    client.post("/api/logout", json={}, headers=headers)
    assert not accounts.sessions
    headers = sign_in(client, "alice")
    assert client.get("/api/config").json()["model_configured"] is False
    client.post(
        "/api/model-key",
        json={"api_key": key, "model": "fixture-model", "authorized": True},
        headers=headers,
    )
    client.post("/api/model-key/clear", json={}, headers=headers)
    assert client.get("/api/config").json()["model_configured"] is False
    for path in accounts.root.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes()


def test_expiry_and_restart_clear_keys_but_preserve_accounts(site):
    client, accounts = site
    headers = sign_in(client, "alice")
    client.post(
        "/api/model-key",
        json={"api_key": "fixture-only", "model": "fixture-model", "authorized": True},
        headers=headers,
    )
    for session in accounts.sessions.values():
        session.expires = time.monotonic() - 1
    accounts.prune()
    assert not accounts.sessions
    assert client.get("/api/jobs").status_code == 401
    restarted = Accounts(accounts.root, accounts.policy_path, accounts.target)
    try:
        assert restarted.authenticate("alice", "account-test-password")
        assert not restarted.sessions
    finally:
        restarted.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_each_user_model_job_uses_only_its_session_key(site, monkeypatch, framework):
    from agentic_web_demo.agents.openai_planner import OpenAIPlanner
    from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner

    client, accounts = site
    used = []

    def fake(self, request, today):
        used.append(self.settings.api_key)
        self.metadata = {"provider": "openai", "response_received": True}
        return {
            **SimulatedPlanner().plan(SCENARIOS["new-york"], today),
            "outcome": "ready",
            "reason": "none",
            "clarification_fields": [],
        }

    monkeypatch.setattr(OpenAIPlanner, "plan", fake)
    monkeypatch.setattr(OpenAIPlanner, "plan_messages", fake)
    for username in ("alice", "bob"):
        headers = sign_in(client, username)
        key = f"{username}-secret-sentinel"
        client.post(
            "/api/model-key",
            json={"api_key": key, "model": "fixture-model", "authorized": True},
            headers=headers,
        )
        result = client.post(
            "/api/plans",
            json={
                "framework": framework,
                "mode": "model-assisted",
                "request": "synthetic",
                "allow_model_api": True,
            },
            headers=headers,
        )
        service = accounts.service_for(accounts.authenticate(username, "account-test-password"))
        job = finished(service, result.json()["job_id"])
        assert job["status"] == "awaiting_review"
        assert key not in json.dumps(job)
        assert key.encode() not in next(service.directory.glob("*.json")).read_bytes()
        client.post("/api/logout", json={}, headers=headers)
    assert used == ["alice-secret-sentinel", "bob-secret-sentinel"]
