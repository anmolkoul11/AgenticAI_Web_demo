"""Search/capture regressions: offline plus opt-in isolated local browser fixtures."""

from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PlaywrightError
from test_browser_navigation import CONTROLS, FakeLocator, FakePage, plan

from agentic_web_demo.browser_navigation import (
    CONTROL_SNAPSHOT,
    NavigationPlan,
    execute_navigation,
    inspect_search_controls,
    observe_navigation_result,
    validate_navigation,
)
from agentic_web_demo.custom_browser import BrowserControl, browser_error_message
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.custom_service import browser_diagnostics


def test_fill_readback_is_verified_without_claiming_results():
    page = FakePage()
    result = execute_navigation(
        page,
        plan({"control_id": 0, "action": "fill", "value": "Boston"}, coverage="partial_form"),
        CONTROLS,
        "https://example.org",
    )
    assert result["actions"][0]["status"] == "value_verified"
    assert result["actions"][0]["observed"] == "Boston"
    assert result["submitted"] is False
    assert result["results_verified"] is False


def test_failed_value_readback_stops_before_search_click():
    class RevertingLocator(FakeLocator):
        def evaluate(self, script):
            return {**super().evaluate(script), "current_value": ""}

    page = FakePage()
    page.locator = lambda selector: RevertingLocator(page.events, selector)
    with pytest.raises(WebsiteError, match="did not retain") as failed:
        execute_navigation(
            page,
            plan(
                {"control_id": 0, "action": "fill", "value": "Boston"},
                {"control_id": 2, "action": "click", "value": ""},
            ),
            CONTROLS,
            "https://example.org",
        )
    assert failed.value.navigation_result["actions"][0]["status"] == "value_mismatch"
    assert not any(event[0] == "click" for event in page.events)


def test_missing_requested_date_prevents_submission():
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="site_filters",
        steps=[
            {"control_id": 0, "action": "fill", "value": "Boston"},
            {"control_id": 2, "action": "click", "value": ""},
        ],
        requirements=[
            {"field": "destination", "value": "Boston", "application": "site"},
            {"field": "check_out", "value": "2026-11-04", "application": "site"},
        ],
    )
    page = FakePage()
    with pytest.raises(WebsiteError, match="not submitted") as failed:
        execute_navigation(page, candidate, CONTROLS, "https://example.org")
    checks = failed.value.navigation_result["requirements"]
    assert [item["status"] for item in checks] == ["will_set_in_form", "unconfirmed"]
    assert failed.value.navigation_result["preflight"] == checks
    assert page.events == []


def test_extraction_only_price_does_not_block_a_verified_destination():
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="site_filters",
        steps=[
            {"control_id": 0, "action": "fill", "value": "Boston"},
            {"control_id": 2, "action": "click", "value": ""},
        ],
        requirements=[
            {"field": "destination", "value": "Boston", "application": "site"},
            {"field": "max_price", "value": "250", "application": "extraction"},
        ],
    )
    result = execute_navigation(FakePage(), candidate, CONTROLS, "https://example.org")
    assert result["submitted"] is True
    assert result["requirements"][1]["status"] == "deferred_to_extraction"
    assert result["results_verified"] is False


def test_changed_control_label_rejects_before_any_action():
    page = FakePage()
    page.controls = [{**item, "label": "Account"} for item in CONTROLS]
    with pytest.raises(WebsiteError, match="changed identity"):
        execute_navigation(
            page,
            plan({"control_id": 0, "action": "fill", "value": "Boston"}),
            CONTROLS,
            "https://example.org",
        )
    assert page.events == []


def test_open_search_or_calendar_is_only_a_partial_transition():
    controls = [{"id": 0, "kind": "opener", "type": "button", "label": "Check-in"}]
    candidate = plan(
        {"control_id": 0, "action": "open_control", "value": ""}, coverage="partial_form"
    )
    assert validate_navigation(candidate, controls) is candidate
    with pytest.raises(WebsiteError, match="Open only"):
        validate_navigation(candidate.model_copy(update={"coverage": "site_filters"}), controls)
    page = FakePage()
    page.controls = controls
    result = execute_navigation(page, candidate, controls, "https://example.org")
    assert result["status"] == "partial_form"
    assert result["actions"][0]["status"] == "action_completed_unverified"


def test_calendar_option_requires_matching_full_requested_date():
    controls = [
        {
            "id": 0,
            "kind": "option",
            "type": "button",
            "label": "4 November 2026",
            "date_value": "2026-11-04",
        }
    ]
    candidate = plan(
        {"control_id": 0, "action": "choose_option", "value": "4 November 2026"},
        coverage="partial_form",
    )
    with pytest.raises(WebsiteError, match="requested full date"):
        validate_navigation(candidate, controls)
    candidate.requirements = [SimpleNamespace(field="check_out", value="2026-11-04")]
    assert validate_navigation(candidate, controls) is candidate
    controls[0]["date_value"] = "2026-11-31"
    with pytest.raises(WebsiteError, match="valid full date"):
        validate_navigation(candidate, controls)


def test_impossible_native_date_and_readonly_fill_are_rejected():
    with pytest.raises(WebsiteError, match="does not exist"):
        validate_navigation(
            plan({"control_id": 1, "action": "fill", "value": "2026-09-31"}), CONTROLS
        )
    controls = [{**CONTROLS[0], "readonly": True}]
    with pytest.raises(WebsiteError, match="read-only"):
        validate_navigation(plan({"control_id": 0, "action": "fill", "value": "Boston"}), controls)


def test_capture_error_is_not_misreported_as_browser_installation_and_hides_secrets():
    control = BrowserControl()
    message = browser_error_message(
        control,
        PlaywrightError("Page.evaluate: secret-password https://site/?token=private"),
        "capture",
    )
    assert "Page capture failed" in message
    assert "installation" not in message
    assert "secret-password" not in str(control.snapshot()) + message
    assert "private" not in str(control.snapshot()) + message
    assert browser_diagnostics(control)["browser_error"] == {
        "stage": "capture",
        "code": "collector_script",
    }


def test_navigation_history_is_bounded_and_snapshot_does_not_alias_state():
    control = BrowserControl()
    for index in range(22):
        control.set_navigation_result({"actions": [{"status": str(index)}]})
    snapshot = control.snapshot()
    assert len(snapshot["navigation_history"]) == 20
    snapshot["navigation_result"]["actions"][0]["status"] = "changed"
    assert control.snapshot()["navigation_result"]["actions"][0]["status"] == "21"


@pytest.fixture
def local_page(request):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser for isolated local search/capture fixtures")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "https://example.org/**",
                lambda route: route.fulfill(
                    content_type="text/html", body="<main>Local fixture</main>"
                ),
            )
            page.goto("https://example.org/")
            yield page
        finally:
            browser.close()


def test_collector_accepts_null_and_explicit_options(local_page):
    from test_source_inventory import COLLECTOR

    from agentic_web_demo.capture import Capture

    local_page.set_content(
        "<main><h1>Local source</h1><p>" + "Verified content " * 20 + "</p></main>"
    )
    for options in (None, {}):
        capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")", options))
        assert "Verified content" in capture.page()["text"]


def test_search_opener_reveals_new_inventory_after_review(local_page):
    local_page.set_content("""<button aria-label="Search" onclick="this.remove();
      document.querySelector('form').hidden=false">Search</button>
      <form hidden><input type="search" aria-label="Search topics"></form>""")
    controls = inspect_search_controls(local_page)
    assert [item["kind"] for item in controls] == ["opener"]
    result = execute_navigation(
        local_page,
        plan(
            {"control_id": controls[0]["id"], "action": "open_control", "value": ""},
            coverage="partial_form",
        ),
        controls,
        "https://example.org",
    )
    result = observe_navigation_result(local_page, result)
    assert result["submitted"] is False
    assert any(item["label"] == "Search topics" for item in result["available_controls"])


def test_local_form_readback_and_result_observation(local_page):
    local_page.set_content("""<form onsubmit="event.preventDefault();
      document.querySelector('main').innerHTML='<article>Boston results</article>'">
      <input aria-label="Destination"><input type="date" aria-label="Check-in">
      <button type="submit">Search</button></form><main>Ready</main>""")
    controls = inspect_search_controls(local_page)
    ids = {control["label"]: control["id"] for control in controls}
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="site_filters",
        steps=[
            {"control_id": ids["Destination"], "action": "fill", "value": "Boston"},
            {"control_id": ids["Check-in"], "action": "fill", "value": "2026-11-02"},
            {"control_id": ids["Search"], "action": "click", "value": ""},
        ],
        requirements=[
            {"field": "destination", "value": "Boston", "application": "site"},
            {"field": "check_in", "value": "2026-11-02", "application": "site"},
        ],
    )
    result = observe_navigation_result(
        local_page, execute_navigation(local_page, candidate, controls, "https://example.org")
    )
    assert all(check["status"] == "verified_in_form" for check in result["requirements"])
    assert result["result_observation"]["page_changed"] is True
    assert result["result_observation"]["criteria_verified_in_results"] is False


def test_full_date_picker_options_exclude_undated_day_guesses(local_page):
    local_page.set_content("""<div role="dialog"><button aria-label="4 November 2026">4</button>
      <button data-date="2026-11-05" aria-label="5 November 2026">5</button>
      <button>6</button><button aria-label="Next month">Next</button></div>""")
    controls = local_page.evaluate(CONTROL_SNAPSHOT, 0)
    dated = [control for control in controls if control["kind"] == "option"]
    assert {control["date_value"] for control in dated} == {"2026-11-04", "2026-11-05"}
    assert not any(control["label"] == "6" for control in controls)
    assert any(control["kind"] == "opener" for control in controls)


def test_snapshot_excludes_credentials_and_handles_aria_labelledby(local_page):
    local_page.set_content("""<label id="destination-label">Destination</label>
      <input aria-labelledby="destination-label" value="Boston">
      <input type="password" value="fixture-password">
      <input name="email" value="private@example.org">
      <button>Log in</button>""")
    controls = inspect_search_controls(local_page)
    assert len(controls) == 1
    assert controls[0]["label"] == "Destination"
    assert controls[0]["current_value"] == "Boston"
    assert "fixture-password" not in str(controls)
    assert "private@example.org" not in str(controls)
