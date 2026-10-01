"""Security regressions; only fake credentials, no OS-store writes or API calls."""

import sqlite3
from pathlib import Path

import pytest
from agentic_web_demo.agents.openai_planner import ModelSettings
from agentic_web_demo.dashboard.accounts import Accounts
from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.credential_store import CredentialStore, CredentialUnavailable
from agentic_web_demo.dashboard.service import DashboardService
from fastapi.testclient import TestClient
from test_dashboard import SETTINGS

PASSWORD = "test-password-not-a-real-secret"


class FakeStore:
    available = True
    label = "Fake test-only store"

    def __init__(self):
        self.values = {}

    def save(self, user_id, settings):
        if not self.available:
            raise CredentialUnavailable("Locked test store")
        self.values[user_id] = settings

    def load(self, user_id):
        if not self.available:
            raise CredentialUnavailable("Locked test store")
        return self.values[user_id]

    def forget(self, user_id):
        if not self.available:
            raise CredentialUnavailable("Locked test store")
        self.values.pop(user_id, None)


def login(client, username):
    csrf = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost", "X-CSRF-Token": csrf}
    response = client.post(
        "/api/login", json={"username": username, "password": PASSWORD}, headers=headers
    )
    assert response.status_code == 200
    return {**headers, "X-CSRF-Token": response.json()["csrf"]}


def test_migration_and_explicit_first_admin(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE accounts (user_id TEXT PRIMARY KEY, username TEXT UNIQUE, "
            "salt BLOB, digest BLOB)"
        )
        db.execute("INSERT INTO accounts VALUES ('legacy', 'legacy', X'00', X'00')")
    accounts = Accounts(
        tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000", credential_store=FakeStore()
    )
    try:
        assert accounts.profile("legacy")["role"] == "user"
        assert accounts.profile("legacy")["enabled"] == 1
        admin = accounts.register("operator", PASSWORD, bootstrap=True)
        assert accounts.profile(admin)["role"] == "admin"
        with pytest.raises(ValueError):
            accounts.register("another-admin", PASSWORD, bootstrap=True)
        with pytest.raises(ValueError):
            accounts.manage(admin, admin, "disable")
        with pytest.raises(ValueError):
            accounts.manage(admin, admin, "demote")
    finally:
        accounts.close()


def test_remembered_keys_are_private_and_forget_clears_all_sessions(tmp_path):
    store = FakeStore()
    accounts = Accounts(
        tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000", credential_store=store
    )
    alice = accounts.register("alice", PASSWORD)
    bob = accounts.register("bob", PASSWORD)
    sid = accounts.sign_in(alice, "alice")
    accounts.save_credential(sid, ModelSettings("fixture", "alice-sentinel"), True)
    accounts.close()
    restarted = Accounts(
        tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000", credential_store=store
    )
    try:
        a = restarted.sign_in(alice, "alice")
        second = restarted.sign_in(alice, "alice")
        b = restarted.sign_in(bob, "bob")
        assert restarted.get(a).model_settings.api_key == "alice-sentinel"
        assert restarted.get(b).model_settings is None
        restarted.forget_credential(a)
        assert not store.values
        assert restarted.get(second).model_settings is None
        assert restarted.profile(alice)["credential_saved"] == 0
        assert b"alice-sentinel" not in restarted.database.read_bytes()
    finally:
        restarted.close()


def test_locked_store_fails_closed_and_session_only_still_works(tmp_path):
    store = FakeStore()
    accounts = Accounts(
        tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000", credential_store=store
    )
    try:
        user = accounts.register("alice", PASSWORD)
        sid = accounts.sign_in(user, "alice")
        key = ModelSettings("fixture", "secret-sentinel")
        accounts.save_credential(sid, key, True)
        store.available = False
        with pytest.raises(CredentialUnavailable):
            accounts.forget_credential(sid)
        assert accounts.profile(user)["credential_saved"] == 1
        new = accounts.sign_in(user, "alice")
        assert accounts.get(new).model_settings is None
        assert accounts.get(new).credential_notice
        with pytest.raises(CredentialUnavailable):
            accounts.save_credential(new, key, True)
        accounts.save_credential(new, key, False)
        assert accounts.get(new).model_settings is key
    finally:
        accounts.close()


def test_unavailable_store_does_not_fall_back(tmp_path):
    store = CredentialStore.__new__(CredentialStore)
    store.backend = None
    store.service = "fixture"
    with pytest.raises(CredentialUnavailable):
        store.save("00000000-0000-0000-0000-000000000001", ModelSettings("fixture", "secret"))


def test_admin_authorization_step_up_and_user_key_ownership(tmp_path):
    template = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    app = create_app(SETTINGS, template)
    accounts = app.state.accounts
    accounts.credentials = FakeStore()
    admin = accounts.register("operator", PASSWORD, bootstrap=True)
    alice = accounts.register("alice", PASSWORD)
    try:
        with TestClient(app, base_url="http://localhost") as client:
            assert client.get("/api/admin/users").status_code == 401
            headers = login(client, "alice")
            assert client.get("/api/admin/users").status_code == 403
            action = {"action": "promote", "password": PASSWORD}
            assert (
                client.post(f"/api/admin/users/{alice}", json=action, headers=headers).status_code
                == 403
            )
            payload = {
                "api_key": "alice-key",
                "model": "fixture",
                "remember": True,
                "authorized": True,
            }
            assert (
                client.post(
                    "/api/model-key", json={**payload, "user_id": admin}, headers=headers
                ).status_code
                == 422
            )
            assert (
                client.post(
                    "/api/model-key", json={**payload, "authorized": False}, headers=headers
                ).status_code
                == 422
            )
            assert client.post("/api/model-key", json=payload, headers=headers).status_code == 200
            assert set(accounts.credentials.values) == {alice}
            alice_sid = next(
                sid for sid, session in accounts.sessions.items() if session.user_id == alice
            )
            headers = login(client, "operator")
            assert client.get("/api/admin/users").status_code == 200
            assert client.get("/api/config").json()["model_configured"] is False
            assert "alice-key" not in client.get("/api/admin/audit").text
            assert (
                client.post(
                    f"/api/admin/users/{alice}",
                    json={"action": "disable", "password": "incorrect-password"},
                    headers=headers,
                ).status_code
                == 403
            )
            assert accounts.profile(alice)["enabled"] == 1
            assert (
                client.post(
                    f"/api/admin/users/{alice}",
                    json={"action": "disable", "password": PASSWORD},
                    headers=headers,
                ).status_code
                == 200
            )
            assert accounts.get(alice_sid) is None
            assert accounts.authenticate("alice", PASSWORD) is None
            assert alice in accounts.credentials.values  # Disable is not delete.
    finally:
        template.close()
