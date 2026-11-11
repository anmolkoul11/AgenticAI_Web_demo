"""Desktop startup contract; local fixtures only, no paid calls or real browser."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_dashboard import SETTINGS, login

from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService


def test_desktop_dashboard_needs_no_demo_password_and_uses_absolute_policy(tmp_path, monkeypatch):
    policy = Path("config/rules.yaml").resolve()
    monkeypatch.setenv("AGENTIC_DASHBOARD_DESKTOP", "1")
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "records"))
    monkeypatch.setenv("AGENTIC_DASHBOARD_POLICY_PATH", str(policy))
    monkeypatch.delenv("AGENTIC_DESKTOP_ENABLE_EVENTS", raising=False)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_SESSION_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(), base_url="http://localhost") as client:
        health = client.get("/api/desktop/health")
        assert health.status_code == 200
        assert health.json()["service"] == "agentic-studio-desktop"
        assert health.json()["status"] == "ready"
        session = client.get("/api/session").json()
        assert session["desktop"] is True
        assert session["capabilities"] == {"hotel_demo": False, "event_publishing": False}
        assert session["authenticated"] is False
        client.app.state.accounts.register("demo", SETTINGS.password)
        headers = login(client)
        config = client.get("/api/config", headers=headers).json()
        assert config["desktop"] is True
        assert config["capabilities"] == session["capabilities"]
        assert config["model_configured"] is False
        assert (tmp_path / "records" / "accounts.sqlite3").is_file()


def test_developer_dashboard_keeps_demo_capabilities(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTIC_DASHBOARD_DESKTOP", raising=False)
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    with TestClient(create_app(SETTINGS, service), base_url="http://localhost") as client:
        assert client.get("/api/desktop/health").status_code == 404
        session = client.get("/api/session").json()
        assert session["desktop"] is False
        assert session["capabilities"] == {"hotel_demo": True, "event_publishing": True}


def test_desktop_event_integration_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_DASHBOARD_DESKTOP", "1")
    monkeypatch.setenv("AGENTIC_DESKTOP_ENABLE_EVENTS", "1")
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    with TestClient(create_app(service=service), base_url="http://localhost") as client:
        session = client.get("/api/session").json()
        assert session["capabilities"] == {"hotel_demo": False, "event_publishing": True}
