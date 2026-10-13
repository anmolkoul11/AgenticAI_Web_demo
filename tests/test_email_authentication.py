"""Human-completed email authentication; offline and opt-in locally fulfilled pages."""

import pytest
from pydantic import ValidationError
from test_browser_login import login_browser as shared_login_browser

from agentic_web_demo.authentication import assess_authentication, authentication_expired
from agentic_web_demo.custom_browser import BrowserControl, automatic_login
from agentic_web_demo.custom_extract import BrowserLogin, WebsiteInput
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.custom_service import browser_diagnostics


@pytest.fixture
def login_browser(request):
    yield from shared_login_browser.__wrapped__(request)


def email_login(**changes):
    return BrowserLogin(method="email_verification", username="fixture@example.org", **changes)


def test_email_only_needs_no_password_and_does_not_serialize_credentials():
    values = WebsiteInput(
        source="browser",
        urls=["https://example.org/"],
        login_mode="automatic",
        login=email_login(),
        authorized=True,
        allow_model_api=True,
    )
    assert values.login.password is None
    assert values.login.url == "https://example.org/"
    assert "login" not in values.model_dump()
    assert "fixture@example.org" not in values.model_dump_json() + repr(values)


def test_password_method_remains_required_and_email_method_rejects_password():
    with pytest.raises(ValidationError, match="requires a password"):
        BrowserLogin(username="fixture@example.org")
    with pytest.raises(ValidationError, match="must not include"):
        email_login(password="fixture-password")
    with pytest.raises(ValidationError, match="valid email"):
        BrowserLogin(method="email_verification", username="not-an-email")


def test_authentication_handoff_blocks_capture_and_planning():
    control = BrowserControl()
    control.require_authentication("Complete code in browser")
    for action in ("capture", "plan", "discover", "approve", "approve_links"):
        with pytest.raises(WebsiteError):
            control.command(action)
    control.command("resume_login")
    assert control.resume_login_requested.is_set()
    assert control.snapshot()["state"] == "checking_authentication"
    with pytest.raises(WebsiteError):
        control.command("resume_login")
    control.command("cancel")
    assert control.cancel.is_set()


def test_expiry_clears_pending_commands_and_verified_claim():
    control = BrowserControl()
    control.authentication.update(status="authenticated", verified=True)
    control.capture.set()
    control.navigation_requested.set()
    control.link_requested.set()
    control.require_authentication("Expired", expired=True)
    assert not control.capture.is_set()
    assert not control.navigation_requested.is_set()
    assert not control.link_requested.is_set()
    assert browser_diagnostics(control)["authentication"]["verified"] is False
    assert control.authentication["status"] == "reauthentication_required"


class FakePage:
    url = "https://example.org/"

    def __init__(self, **changes):
        self.state = {
            "https": True,
            "password_form": False,
            "code_form": False,
            "email_notice": False,
            "access_restriction": False,
            "success_count": 0,
            **changes,
        }

    def evaluate(self, _script, _argument):
        return self.state


@pytest.mark.parametrize(
    "condition", ["password_form", "code_form", "email_notice", "access_restriction"]
)
def test_verification_or_access_checks_cannot_be_confirmed_away(condition):
    with pytest.raises(WebsiteError):
        assess_authentication(FakePage(**{condition: True}), "https://example.org")


def test_missing_indicator_does_not_become_automatic_success():
    with pytest.raises(WebsiteError, match="indicator"):
        assess_authentication(FakePage(), "https://example.org", "#signed-in")
    assert assess_authentication(FakePage(), "https://example.org") == {
        "status": "operator_confirmed",
        "verified": False,
        "verification": "operator_attestation",
    }
    assert (
        assess_authentication(FakePage(success_count=1), "https://example.org", "#signed-in")[
            "verified"
        ]
        is True
    )


def test_identity_origin_or_callback_is_not_a_successful_return():
    page = FakePage(success_count=1)
    page.url = "https://identity.example.org/"
    with pytest.raises(WebsiteError, match="return to the selected"):
        assess_authentication(page, "https://example.org", "#signed-in")
    page.url = "https://example.org/callback?code=fixture-secret"
    with pytest.raises(WebsiteError, match="authentication page") as rejected:
        assess_authentication(page, "https://example.org", "#signed-in")
    assert "fixture-secret" not in str(rejected.value)


def test_password_or_code_challenge_invalidates_the_previous_session():
    assert authentication_expired(FakePage(code_form=True), "https://example.org")
    assert not authentication_expired(FakePage(), "https://example.org")


def test_email_request_is_once_then_human_code_and_confirmed_resume(login_browser):
    page = login_browser
    posts = []

    def respond(route):
        if route.request.method == "POST":
            posts.append(route.request.post_data)
            route.fulfill(
                content_type="text/html",
                body="""<h1>Enter your code</h1>
              <input autocomplete="one-time-code" aria-label="Verification code">
              <button onclick="if(document.querySelector('input').value==='123456') {
                history.replaceState({},'', '/');
                document.body.innerHTML='<button id=signed-in>Account</button>'}">
                Verify</button>""",
            )
        else:
            route.fulfill(
                content_type="text/html",
                body="""<form method="post" action="/email">
              <input type="email" name="email"><button type="submit">Continue</button></form>""",
            )

    page.route("https://example.org/**", respond)
    page.goto("https://example.org/login")
    assert automatic_login(page, email_login(), "https://example.org") is False
    assert len(posts) == 1
    with pytest.raises(WebsiteError, match="code form"):
        assess_authentication(page, "https://example.org", "#signed-in")
    # Test fixture simulates the user's manual code entry; app code never submits an OTP.
    page.get_by_label("Verification code").fill("123456")
    page.get_by_text("Verify", exact=True).click()
    assert assess_authentication(page, "https://example.org", "#signed-in")["verified"]
    assert len(posts) == 1


def test_code_values_never_enter_authentication_diagnostics(login_browser):
    page = login_browser
    page.route(
        "https://example.org/**",
        lambda route: route.fulfill(
            content_type="text/html", body='<input autocomplete="one-time-code" value="654321">'
        ),
    )
    page.goto("https://example.org/")
    with pytest.raises(WebsiteError) as rejected:
        assess_authentication(page, "https://example.org")
    control = BrowserControl()
    control.require_authentication(str(rejected.value))
    assert "654321" not in str(control.snapshot()) + str(rejected.value)


def test_postal_code_search_is_not_an_authentication_challenge(login_browser):
    page = login_browser
    page.route(
        "https://example.org/**",
        lambda route: route.fulfill(
            content_type="text/html", body='<label>Postal code<input name="postal_code"></label>'
        ),
    )
    page.goto("https://example.org/")
    assert not authentication_expired(page, "https://example.org")
