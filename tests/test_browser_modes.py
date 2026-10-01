"""Browser-mode contracts; no browser launch, model calls or external requests."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agentic_web_demo.custom_browser import (
    BrowserControl,
    automatic_login,
    browser_context_options,
    browser_launch_options,
    capture_url,
    install_browser_guards,
)
from agentic_web_demo.custom_extract import BrowserLogin, WebsiteInput
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.custom_service import browser_diagnostics


def inputs(**changes):
    return WebsiteInput(
        **{
            "source": "browser",
            "urls": ["https://example.org/"],
            "authorized": True,
            "allow_model_api": True,
            **changes,
        }
    )


def test_restricted_mode_remains_default():
    values = inputs()
    assert values.browser_mode == "restricted"
    assert values.browser_channel == "chromium"
    assert not values.normal_browser_confirmed


def test_normal_mode_requires_separate_confirmation():
    with pytest.raises(ValidationError, match="explicit confirmation"):
        inputs(browser_mode="normal")
    assert inputs(browser_mode="normal", normal_browser_confirmed=True).browser_mode == "normal"


@pytest.mark.parametrize(
    "change",
    [
        {"normal_browser_confirmed": True},
        {"browser_mode": "unknown"},
        {"browser_channel": "firefox"},
        {
            "source": "public",
            "browser_mode": "normal",
            "normal_browser_confirmed": True,
        },
        {"source": "public", "browser_channel": "chrome"},
        {
            "browser_mode": "normal",
            "normal_browser_confirmed": True,
            "resource_origins": ["https://cdn.example.org"],
        },
        {
            "browser_mode": "normal",
            "normal_browser_confirmed": True,
            "verification_origins": ["https://verify.example.org"],
        },
    ],
)
def test_ambiguous_or_invalid_browser_settings_are_rejected(change):
    with pytest.raises(ValidationError):
        inputs(**change)


@pytest.mark.parametrize("channel", ["chromium", "chrome", "msedge"])
def test_normal_browser_launch_has_no_proxy_or_network_flags(channel):
    values = inputs(browser_mode="normal", normal_browser_confirmed=True, browser_channel=channel)
    options = browser_launch_options(values)
    assert options["headless"] is False
    assert options["chromium_sandbox"] is True
    assert "proxy" not in options
    assert "args" not in options
    assert options.get("channel") == (None if channel == "chromium" else channel)
    context = browser_context_options(values)
    assert context["java_script_enabled"] is True
    assert context["service_workers"] == "allow"
    assert context["accept_downloads"] is True
    assert context["ignore_https_errors"] is False


def test_restricted_launch_still_requires_proxy_and_blocks_service_workers_downloads():
    with pytest.raises(WebsiteError, match="requires its network proxy"):
        browser_launch_options(inputs())
    proxy = SimpleNamespace(settings={"server": "http://127.0.0.1:12345"})
    options = browser_launch_options(inputs(), proxy)
    assert options["proxy"] == proxy.settings
    assert "--disable-quic" in options["args"]
    context = browser_context_options(inputs())
    assert context["service_workers"] == "block"
    assert context["accept_downloads"] is False


class Recorder:
    def __init__(self):
        self.calls = []

    def route(self, *args):
        self.calls.append(("route", args))

    def route_web_socket(self, *args):
        self.calls.append(("websocket", args))

    def on(self, *args):
        self.calls.append(("event", args))


def test_normal_mode_does_not_install_request_websocket_popup_or_dialog_handlers():
    context, page = Recorder(), Recorder()
    install_browser_guards(context, page, lambda route: None, "normal")
    assert context.calls == page.calls == []


def test_restricted_mode_still_installs_all_handlers():
    context, page = Recorder(), Recorder()
    install_browser_guards(context, page, lambda route: None, "restricted")
    assert [kind for kind, _ in context.calls] == ["route", "websocket", "event"]
    assert context.calls[-1][1][0] == "page"
    assert page.calls[0][1][0] == "dialog"


def test_capture_can_use_a_redirected_public_page_without_an_origin_lock():
    assert capture_url("https://other.example.org/content", None) == (
        "https://other.example.org/content"
    )
    with pytest.raises(WebsiteError, match="approved website"):
        capture_url("https://other.example.org/content", "https://example.org")


def test_normal_login_accepts_external_https_identity_without_allowlisting_and_hides_secrets():
    values = inputs(
        browser_mode="normal",
        normal_browser_confirmed=True,
        login_mode="automatic",
        login={
            "url": "https://identity.example.org/login",
            "username": "fixture@example.org",
            "password": "fixture-secret-not-a-real-password",
        },
    )
    assert values.login.url == "https://identity.example.org/login"
    assert "login" not in values.model_dump()
    assert "fixture-secret" not in values.model_dump_json()


def test_normal_login_does_not_allow_http_credentials():
    with pytest.raises(ValidationError, match="HTTPS login URL"):
        inputs(
            browser_mode="normal",
            normal_browser_confirmed=True,
            login_mode="automatic",
            login={
                "url": "http://identity.example.org/login",
                "username": "demo",
                "password": "demo",
            },
        )


def test_mode_is_visible_in_live_and_saved_diagnostics():
    control = BrowserControl()
    control.browser_mode = "normal"
    control.browser_channel = "chrome"
    assert control.snapshot()["browser_mode"] == "normal"
    diagnostics = browser_diagnostics(control)
    assert diagnostics["browser_mode"] == "normal"
    assert diagnostics["browser_channel"] == "chrome"


@pytest.mark.parametrize("normal", [False, True], ids=["restricted", "normal"])
def test_external_sign_in_entry_and_return_redirect(request, normal):
    """Optional browser fixture: locally fulfilled pages, no external website or model."""
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser after installing Chromium")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            submitted = []

            def respond(route):
                req = route.request
                if req.method == "POST":
                    submitted.append(req.url)
                    route.fulfill(
                        status=302,
                        headers={"Location": "https://example.org/signed-in"},
                    )
                elif req.url == "https://identity.example.org/login":
                    route.fulfill(
                        content_type="text/html",
                        body='<form method="post" action="https://identity.example.org/session">'
                        '<input name="email" type="email"><input name="password" type="password">'
                        '<button type="submit">Log in</button></form>',
                    )
                elif req.url.endswith("/signed-in"):
                    route.fulfill(content_type="text/html", body='<h1 id="signed-in">Account</h1>')
                else:
                    route.fulfill(
                        content_type="text/html",
                        body='<a href="https://identity.example.org/login">Log in</a>',
                    )

            page.route("https://**/*", respond)
            page.goto("https://example.org/")
            login = BrowserLogin(
                username="fixture@example.org",
                password="fixture-only-secret",
                success_selector="#signed-in",
            )
            if normal:
                assert automatic_login(page, login, "https://example.org", normal_network=True)
                assert submitted == ["https://identity.example.org/session"]
                assert page.url == "https://example.org/signed-in"
            else:
                with pytest.raises(WebsiteError, match="trusted sign-in entry"):
                    automatic_login(page, login, "https://example.org")
                assert submitted == []
        finally:
            browser.close()
