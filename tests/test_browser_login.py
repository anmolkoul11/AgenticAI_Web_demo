"""Offline browser contract tests. No Chromium, public websites or paid model calls."""

import http.client
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from pydantic import ValidationError
from test_dashboard import SETTINGS, finished, login

from agentic_web_demo import custom_service
from agentic_web_demo.browser_proxy import GuardedProxy
from agentic_web_demo.custom_browser import (
    BrowserControl,
    access_challenge,
    automatic_login,
    capture_url,
    request_allowed,
    safe_source_url,
)
from agentic_web_demo.custom_extract import BrowserLogin, WebsiteInput
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService


def inputs(**changes):
    return WebsiteInput(
        **{
            "source": "browser",
            "urls": ["https://example.org/listings"],
            "authorized": True,
            "allow_model_api": True,
            **changes,
        }
    )


def login_fields(**changes):
    return {
        "url": "https://example.org/login",
        "username": "fixture-user-only",
        "password": "fixture-secret-never-serialize",
        **changes,
    }


def test_login_credentials_never_serialize():
    values = inputs(login_mode="automatic", login=login_fields())
    assert "login" not in values.model_dump()
    for secret in ("fixture-user-only", "fixture-secret-never-serialize"):
        assert secret not in values.model_dump_json()
        assert secret not in repr(values)


def test_browser_can_open_without_website_login():
    values = inputs(login_mode="none")
    assert values.login_mode == "none"
    assert values.login is None


@pytest.fixture
def login_browser(request):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser after installing Chromium")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            yield page
        finally:
            browser.close()


def test_automatic_login_submits_post_form(login_browser):
    page = login_browser

    def respond(route):
        if route.request.method == "POST":
            route.fulfill(status=200, content_type="text/html", body="<h1>Signed in</h1>")
        else:
            route.fulfill(
                status=200,
                content_type="text/html",
                body=(
                    '<form method="post" action="/session">'
                    '<input name="username" type="text">'
                    '<input type="password" name="password">'
                    '<button type="submit">Sign in</button></form>'
                ),
            )

    page.route("https://login.example.test/**", respond)
    page.goto("https://login.example.test/login")
    verified = automatic_login(
        page,
        BrowserLogin(**login_fields(url="https://login.example.test/login", success_selector="h1")),
        "https://login.example.test",
    )
    assert verified
    assert page.locator("h1").inner_text() == "Signed in"


def test_automatic_login_handles_email_then_password(login_browser):
    page = login_browser
    page.route(
        "https://login.example.test/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="""
                <form method="post" id="step">
                  <input type="email" name="email">
                  <button type="submit">Continue</button>
                </form>
                <script>
                  document.querySelector('#step').addEventListener('submit', event => {
                    event.preventDefault();
                    if (document.querySelector('[name=email]')) {
                      document.body.innerHTML = `<form method="post" id="step">
                        <input type="password" name="password">
                        <button type="submit">Sign in</button></form>`;
                      document.querySelector('#step').addEventListener('submit', next => {
                        next.preventDefault();
                        document.body.innerHTML = '<h1>Signed in</h1>';
                      });
                    }
                  });
                </script>
            """,
        ),
    )
    page.goto("https://login.example.test/login")
    automatic_login(
        page,
        BrowserLogin(
            **login_fields(
                url="https://login.example.test/login",
                username="fixture@example.org",
            )
        ),
        "https://login.example.test",
    )
    assert page.locator("h1").inner_text() == "Signed in"


def test_automatic_login_finds_visible_sign_in_link(login_browser):
    page = login_browser

    def respond(route):
        if route.request.method == "POST":
            body = "<h1>Signed in</h1>"
        elif route.request.url.endswith("/login"):
            body = (
                '<form method="post" action="/session">'
                '<input type="email" name="email">'
                '<input type="password" name="password">'
                '<button type="submit">Sign in</button></form>'
            )
        else:
            body = '<a href="/login">Sign in</a>'
        route.fulfill(status=200, content_type="text/html", body=body)

    page.route("https://login.example.test/**", respond)
    page.goto("https://login.example.test/")
    automatic_login(
        page,
        BrowserLogin(**login_fields(url="", username="fixture@example.org")),
        "https://login.example.test",
    )
    assert page.locator("h1").inner_text() == "Signed in"


def test_automatic_login_reports_invalid_email_format(login_browser):
    page = login_browser
    page.route(
        "https://login.example.test/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                '<form method="post" action="/session">'
                '<input type="email" name="email">'
                '<input type="password" name="password">'
                '<button type="submit">Sign in</button></form>'
            ),
        ),
    )
    page.goto("https://login.example.test/login")
    with pytest.raises(WebsiteError, match="username/email field format"):
        automatic_login(
            page,
            BrowserLogin(**login_fields(url="https://login.example.test/login")),
            "https://login.example.test",
        )


def test_automatic_login_supports_javascript_button(login_browser):
    page = login_browser
    page.route(
        "https://login.example.test/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                '<input type="text" name="username">'
                '<input type="password" name="password">'
                '<button type="button" id="sign-in" '
                "onclick=\"document.body.innerHTML='<h1>Signed in</h1>'\">Sign in</button>"
            ),
        ),
    )
    page.goto("https://login.example.test/login")
    automatic_login(
        page,
        BrowserLogin(
            **login_fields(
                url="https://login.example.test/login",
                submit_selector="#sign-in",
            )
        ),
        "https://login.example.test",
    )
    assert page.locator("h1").inner_text() == "Signed in"


def test_automatic_login_rejects_native_get_form(login_browser):
    page = login_browser
    page.route(
        "https://login.example.test/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                '<form method="get"><input name="username" type="text">'
                '<input type="password" name="password">'
                '<button type="submit">Sign in</button></form>'
            ),
        ),
    )
    page.goto("https://login.example.test/login")
    with pytest.raises(WebsiteError, match="trusted-origin POST"):
        automatic_login(
            page,
            BrowserLogin(**login_fields(url="https://login.example.test/login")),
            "https://login.example.test",
        )


def test_automatic_login_does_not_claim_unverified_success(login_browser):
    page = login_browser
    page.route(
        "https://login.example.test/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                '<form method="post"><input name="username" type="text">'
                '<input name="password" type="password">'
                '<button type="submit">Sign in</button></form>'
            ),
        ),
    )
    page.goto("https://login.example.test/login")
    assert not automatic_login(
        page,
        BrowserLogin(**login_fields(url="https://login.example.test/login")),
        "https://login.example.test",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"urls": ["http://example.org"]},
        {"urls": ["https://example.org", "https://example.org/other"]},
        {"login_mode": "automatic"},
        {"login": login_fields()},
        {"login_mode": "none", "login": login_fields()},
        {"login_mode": "none", "verification_origins": ["https://verify.example.org"]},
        {"login_mode": "automatic", "login": login_fields(url="https://different.example/login")},
        {
            "login_mode": "automatic",
            "login": login_fields(auth_origins=["http://auth.example.org"]),
        },
        {"resource_origins": ["http://cdn.example.org"]},
        {"resource_origins": ["https://127.0.0.1"]},
        {"verification_origins": ["https://127.0.0.1"]},
        {"verification_origins": ["http://verify.example.org"]},
        {"verification_origins": ["https://verify.example.org"], "source": "public"},
        {
            "verification_origins": ["https://verify.example.org"],
            "login_mode": "automatic",
            "login": login_fields(),
        },
        {"verification_origins": [f"https://v{i}.example.org" for i in range(5)]},
        {"source": "public", "login_mode": "automatic", "login": login_fields()},
    ],
)
def test_browser_contract_rejects_unsafe_or_ambiguous_inputs(change):
    with pytest.raises((ValidationError, WebsiteError)):
        inputs(**change)


def test_capture_origin_and_url_redaction():
    assert (
        safe_source_url("https://example.org/content?code=sensitive#token")
        == "https://example.org/content"
    )
    with pytest.raises(WebsiteError):
        capture_url("https://different.example/content", "https://example.org")


def test_control_requires_waiting_and_can_cancel():
    control = BrowserControl()
    control.set_page_health({"ready_state": "loading", "visible_text_chars": 0, "main_status": 200})
    assert control.snapshot()["page_health"]["ready_state"] == "loading"
    with pytest.raises(WebsiteError):
        control.command("capture")
    control.update("waiting", "Ready")
    control.command("capture")
    assert control.capture.is_set() and control.snapshot()["state"] == "capturing"
    control.command("cancel")
    assert control.cancel.is_set()


def test_verification_pause_disables_capture_but_allows_cancel():
    control = BrowserControl()
    control.update("verification_required", "Waiting for user")
    with pytest.raises(WebsiteError):
        control.command("capture")
    assert not control.capture.is_set()
    control.command("cancel")
    assert control.cancel.is_set()


@pytest.mark.parametrize(
    "text",
    [
        "Please enable JS and disable any ad blocker",
        "PLEASE ENABLE JAVASCRIPT AND DISABLE ANY AD BLOCKER",
        "Verify you are human",
        "Checking your browser",
    ],
)
def test_challenge_text_detected(text):
    assert access_challenge(text)


def test_ordinary_content_is_not_challenge():
    assert not access_challenge("Boston hotels. Harbour hotel, USD 190, rated 4.5.")


@pytest.mark.parametrize(
    "remote,navigation,main_frame,method,locked,expected",
    [
        ("https://example.org", True, True, "GET", False, True),
        ("https://example.org", True, False, "GET", False, True),
        ("https://cdn.example.org", False, False, "GET", False, True),
        ("https://cdn.example.org", True, False, "GET", False, False),
        ("https://cdn.example.org", False, False, "POST", False, False),
        ("https://verify.example.org", True, False, "GET", False, True),
        ("https://verify.example.org", True, True, "GET", False, False),
        ("https://verify.example.org", False, False, "POST", False, True),
        ("https://verify.example.org", False, False, "DELETE", False, False),
        ("https://verify.example.org", False, False, "POST", True, False),
        ("https://unapproved.example.org", False, False, "GET", False, False),
        ("http://verify.example.org", True, False, "GET", False, False),
    ],
)
def test_scoped_verification_network_policy(
    remote, navigation, main_frame, method, locked, expected
):
    assert (
        request_allowed(
            remote,
            "https://example.org",
            {"https://cdn.example.org"},
            {"https://verify.example.org"},
            navigation=navigation,
            main_frame=main_frame,
            method=method,
            locked_login=locked,
        )
        is expected
    )


def test_verification_never_implicitly_enabled():
    assert inputs().verification_origins == []
    assert not request_allowed(
        "https://verify.example.org",
        "https://example.org",
        set(),
        set(),
        navigation=True,
        main_frame=False,
        method="GET",
    )


def test_trusted_identity_origin_requires_explicit_login_configuration():
    values = inputs(
        login_mode="automatic",
        login=login_fields(
            url="https://auth.example.org/login",
            auth_origins=["https://auth.example.org"],
        ),
    )
    assert values.login.auth_origins == ["https://auth.example.org"]
    assert request_allowed(
        "https://auth.example.org",
        "https://example.org",
        set(),
        set(),
        navigation=True,
        main_frame=True,
        method="GET",
        auth_origins=set(values.login.auth_origins),
    )
    assert request_allowed(
        "https://auth.example.org",
        "https://example.org",
        set(),
        set(),
        navigation=False,
        main_frame=False,
        method="POST",
        locked_login=True,
        auth_origins=set(values.login.auth_origins),
    )
    assert not request_allowed(
        "https://other.example.org",
        "https://example.org",
        set(),
        set(),
        navigation=True,
        main_frame=True,
        method="GET",
        auth_origins=set(values.login.auth_origins),
    )


def test_missing_login_url_starts_at_requested_website():
    values = inputs(login_mode="automatic", login=login_fields(url=""))
    assert values.login.url == "https://example.org/listings"


def test_proxy_authentication_and_destination_rejection():
    # Loopback-only test: all requests rejected before DNS/upstream traffic.
    with GuardedProxy({"example.org"}) as proxy:
        for headers, destination, expected in [
            ({}, "example.org:443", 407),
            ({"Proxy-Authorization": proxy.auth}, "127.0.0.1:443", 403),
            ({"Proxy-Authorization": proxy.auth}, "example.org:80", 403),
        ]:
            connection = http.client.HTTPConnection(
                "127.0.0.1", proxy.server.server_port, timeout=3
            )
            try:
                connection.request("CONNECT", destination, headers=headers)
                response = connection.getresponse()
                assert response.status == expected
                response.read()
            finally:
                connection.close()


@pytest.fixture
def service(tmp_path):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield service
    service.close()


def test_cancel_before_model_removes_browser_control(service, monkeypatch):
    ready = threading.Event()

    def fake_browser(values, control, model_settings):
        assert model_settings is not None
        control.update("waiting", "Fixture waiting")
        ready.set()
        assert control.cancel.wait(3)
        raise WebsiteError("Cancelled before model")

    monkeypatch.setattr(custom_service, "read_browser", fake_browser)
    monkeypatch.setattr(
        custom_service, "interpret", lambda *args: pytest.fail("Model must not run")
    )
    job_id = custom_service.plan(service, inputs(), object())
    assert ready.wait(3)
    service.browser_controls[job_id].command("cancel")
    result = finished(service, job_id)
    assert result["status"] == "needs_input"
    assert job_id not in service.browser_controls


def test_browser_controls_are_account_private(service):
    with TestClient(create_app(SETTINGS, service), base_url="http://localhost") as client:
        accounts = client.app.state.accounts
        owner = accounts.register("demo", SETTINGS.password)
        accounts.register("other-user", SETTINGS.password)
        headers = login(client)
        owner_service = accounts.service_for(owner)
        from uuid import uuid4

        job_id = str(uuid4())
        owner_service.write({"job_id": job_id, "status": "running"})
        control = BrowserControl()
        owner_service.browser_controls[job_id] = control
        client.post("/api/logout", json={}, headers=headers)
        token = client.get("/api/session").json()["csrf"]
        response = client.post(
            "/api/login",
            json={"username": "other-user", "password": SETTINGS.password},
            headers={"Origin": "http://localhost", "X-CSRF-Token": token},
        )
        headers["X-CSRF-Token"] = response.json()["csrf"]
        assert client.get(f"/api/custom/jobs/{job_id}/browser").status_code == 404
        assert (
            client.post(
                f"/api/custom/jobs/{job_id}/browser/cancel", json={}, headers=headers
            ).status_code
            == 404
        )
        assert not control.cancel.is_set()
