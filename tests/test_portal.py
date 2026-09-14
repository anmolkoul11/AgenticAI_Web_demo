import re

import pytest
from fastapi.testclient import TestClient

from agentic_web_demo.portal.app import PortalSettings, create_app

# Synthetic test credentials, not a configured development account.
TEST_SETTINGS = PortalSettings("test-user", "test-only-password", "test-only-secret-" * 3)


@pytest.fixture
def client():
    with TestClient(create_app(TEST_SETTINGS), base_url="http://localhost") as instance:
        yield instance


def token(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)


def login(client, password=TEST_SETTINGS.password):
    csrf = token(client.get("/login"))
    return client.post(
        "/login",
        data={
            "username": TEST_SETTINGS.username,
            "password": password,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )


def test_protected_listings_redirect_without_data(client):
    response = client.get("/listings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "Harbor House" not in response.text


def test_invalid_login(client):
    response = login(client, "wrong-password")
    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    assert "wrong-password" not in response.text
    assert client.get("/listings", follow_redirects=False).status_code == 303


def test_valid_login_and_seeded_listings(client):
    response = login(client)
    assert response.status_code == 303
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    page = client.get("/listings")
    assert page.status_code == 200
    assert page.text.count('data-testid="listing"') == 6
    assert "Harbor House" in page.text
    assert page.headers["cache-control"] == "no-store"


def test_city_filter_case_insensitive(client):
    login(client)
    page = client.get("/listings", params={"city": "  new york  "})
    assert page.text.count('data-testid="listing"') == 4
    assert "Beacon Court" not in page.text


def test_zero_matches_is_success(client):
    login(client)
    page = client.get("/listings", params={"city": "Unknown City"})
    assert page.status_code == 200
    assert 'data-testid="empty-state"' in page.text


@pytest.mark.parametrize(
    "start,end",
    [
        ("invalid", "2030-01-03"),
        ("2030-01-03", "2030-01-02"),
        ("2030-01-03", "2030-01-03"),
        ("2000-01-01", "2000-01-02"),
        ("2030-01-01", "2030-03-01"),
    ],
)
def test_invalid_dates(client, start, end):
    login(client)
    response = client.get("/listings", params={"check_in": start, "check_out": end})
    assert response.status_code == 400
    assert 'data-testid="listing"' not in response.text


def test_missing_csrf_rejected(client):
    client.get("/login")
    assert (
        client.post(
            "/login",
            data={
                "username": TEST_SETTINGS.username,
                "password": TEST_SETTINGS.password,
            },
        ).status_code
        == 403
    )


def test_cross_session_csrf_rejected(client):
    with TestClient(create_app(TEST_SETTINGS), base_url="http://localhost") as other:
        other_token = token(other.get("/login"))
    client.get("/login")
    assert (
        client.post(
            "/login",
            data={
                "username": TEST_SETTINGS.username,
                "password": TEST_SETTINGS.password,
                "csrf_token": other_token,
            },
        ).status_code
        == 403
    )


def test_logout_revokes_copied_cookie(client):
    login(client)
    cookie = client.cookies.get("demo_session")
    csrf = token(client.get("/listings"))
    assert (
        client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
    )
    client.cookies.set("demo_session", cookie, domain="localhost.local", path="/")
    assert client.get("/listings", follow_redirects=False).status_code == 303


def test_logout_requires_csrf(client):
    login(client)
    assert client.post("/logout").status_code == 403
    assert client.get("/logout").status_code == 405
    assert client.get("/listings").status_code == 200


def test_tampered_session_rejected(client):
    client.cookies.set("demo_session", "invalid-signature")
    assert client.get("/listings", follow_redirects=False).status_code == 303


def test_session_expiry(client, monkeypatch):
    login(client)
    import agentic_web_demo.portal.app as module

    now = module.time.monotonic()
    monkeypatch.setattr(module.time, "monotonic", lambda: now + 3601)
    assert client.get("/listings", follow_redirects=False).status_code == 303


def test_untrusted_host_rejected(client):
    assert client.get("/login", headers={"host": "evil.example"}).status_code == 400


def test_filter_html_is_escaped(client):
    login(client)
    page = client.get("/listings", params={"city": '<script>alert("x")</script>'})
    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_public_health_and_styles(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/static/portal.css").status_code == 200


def test_required_secrets(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="DEMO_PASSWORD"):
        create_app()


def test_short_secret_rejected():
    with pytest.raises(ValueError, match="DEMO_SESSION_SECRET"):
        PortalSettings("demo", "test-only-password", "short")


def test_settings_repr_omits_secrets():
    assert TEST_SETTINGS.password not in repr(TEST_SETTINGS)
    assert TEST_SETTINGS.session_secret not in repr(TEST_SETTINGS)
