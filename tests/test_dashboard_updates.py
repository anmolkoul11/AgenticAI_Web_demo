"""Offline API coverage for update/session metadata and safe account errors."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard import SETTINGS

from agentic_web_demo.dashboard.app import UI_VERSION, create_app
from agentic_web_demo.dashboard.service import DashboardService


def test_update_metadata_validation_and_stale_client(tmp_path):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        app = create_app(SETTINGS, service)
        with TestClient(app, base_url="http://localhost") as client:
            session = client.get("/api/session").json()
            assert session["ui_version"] == UI_VERSION
            assert session["instance_id"]
            assert client.get("/api/session").json()["instance_id"] == session["instance_id"]
            headers = {"Origin": "http://localhost", "X-CSRF-Token": session["csrf"]}
            invalid = client.post(
                "/api/register", json={"username": "x", "password": "short"}, headers=headers
            )
            assert invalid.status_code == 422
            assert "username" in invalid.json()["detail"]
            assert "API permission" not in invalid.text
            stale = client.post(
                "/api/register",
                json={"username": "new-user", "password": "fixture-password-only"},
                headers={**headers, "X-Dashboard-Version": "outdated"},
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "ui_outdated"
            assert app.state.accounts.authenticate("new-user", "fixture-password-only") is None
        replacement = create_app(SETTINGS, service)
        with TestClient(replacement, base_url="http://localhost") as client:
            assert client.get("/api/session").json()["instance_id"] != session["instance_id"]
    finally:
        service.close()
