"""Shared destination detection: no paid calls, optional isolated local browser fixtures."""

from types import SimpleNamespace

import pytest
from test_dashboard_live_updates import live_ui as shared_ui
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo import hotel_search
from agentic_web_demo.browser_navigation import (
    NavigationPlan,
    destination_controls,
    destination_partial_fallback,
    inspect_search_controls,
    validate_navigation,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.hotel_search import HotelSearchDriver, prepare_hotel_search, run_hotel_search

REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30, "
    "for 3 adults, 2 rooms, priced from 250-350 USD per night."
)


def control(identifier, *, structured=False):
    return {
        "id": identifier,
        "kind": "input",
        "type": "text",
        "purpose": "destination",
        "current_value": "",
        "label": "Destination",
        "destination_context": structured,
    }


def test_paid_destination_fallback_prefers_hotel_form_over_header_field():
    controls = [control(0), control(1, structured=True)]
    assert destination_controls(controls) == [controls[1]]
    plan = destination_partial_fallback(controls, REQUEST)
    assert plan.steps[0].control_id == 1 and plan.steps[0].value == "New York"


def test_two_matching_hotel_forms_are_not_arbitrarily_selected():
    controls = [control(0, structured=True), control(1, structured=True)]
    assert len(destination_controls(controls)) == 2
    assert destination_partial_fallback(controls, REQUEST) is None


def test_model_cannot_fill_unrelated_destination_when_hotel_form_identified():
    controls = [control(0), control(1, structured=True)]
    plan = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="partial_form",
        steps=[{"control_id": 0, "action": "fill", "value": "New York"}],
        requirements=[{"field": "destination", "value": "New York", "application": "site"}],
    )
    with pytest.raises(WebsiteError, match="identified hotel form"):
        validate_navigation(plan, controls, instructions=REQUEST)


def test_delayed_destination_is_observed_before_one_literal_fill():
    events = []
    state = {
        "destination": None,
        "suggestions": [],
        "destination_diagnostics": {"matching_fields": 0, "reason": "no_match"},
    }

    def observe_delay(_):
        events.append("observe")
        state["destination"] = {"value": ""}
        state["destination_diagnostics"] = {"matching_fields": 1, "reason": "recognized"}

    driver = HotelSearchDriver(
        SimpleNamespace(url="https://example.org/", wait_for_timeout=observe_delay),
        "https://example.org",
    )
    driver.inventory = lambda: state

    def fill(field, value):
        events.append(("fill", value))
        field["value"] = value

    driver.act = fill
    assert driver.destination("New York") == "New York"
    assert events == ["observe", ("fill", "New York")]


def test_failed_detection_preserves_metadata_and_no_actions(monkeypatch):
    clock = [10]
    monkeypatch.setattr(hotel_search.time, "monotonic", lambda: clock[0])
    page = SimpleNamespace(
        url="https://example.org/", wait_for_timeout=lambda _: clock.__setitem__(0, clock[0] + 5)
    )
    driver = HotelSearchDriver(page, "https://example.org")
    diagnostics = {
        "matching_fields": 0,
        "reason": "no_match",
        "candidates": [
            {
                "name": "query",
                "label": "Search in your own words",
                "reason": "natural_language_without_destination_context",
            }
        ],
    }
    driver.inventory = lambda: {"destination": None, "destination_diagnostics": diagnostics}
    with pytest.raises(WebsiteError, match="rendered form") as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    report = caught.value.navigation_result
    assert report["destination_diagnostics"] == diagnostics
    assert report["actions"] == [] and not report["submission_attempted"]


@pytest.fixture
def destination_page(request):
    yield from shared_local_page.__wrapped__(request)


FORM = """<form>
  INPUT
  <button type=button>Select dates Check-in — Check-out</button>
  <button type=button>Number of travelers and rooms. 2 adults · 0 children · 1 room</button>
  <button type=submit>Search</button>
</form>"""


@pytest.mark.parametrize(
    "input_markup",
    [
        '<input name=ss placeholder="Search in your own words">',
        '<input data-testid=destination-input placeholder="Search in your own words">',
        "<div data-testid=destination-container>"
        '<input placeholder="Search in your own words"></div>',
        "<span id=cityLabel>Destination</span><input aria-labelledby=cityLabel>",
        '<input title="Where are you going?">',
    ],
)
def test_both_paths_recognize_form_context_and_alternative_labels(destination_page, input_markup):
    destination_page.set_content(FORM.replace("INPUT", input_markup))
    driver = HotelSearchDriver(destination_page, "https://example.org")
    state = driver.inventory()
    assert state["destination"] is not None
    assert state["destination_diagnostics"]["structured_matching_fields"] == 1
    controls = inspect_search_controls(destination_page)
    proposal = destination_partial_fallback(controls, REQUEST)
    assert proposal is not None and proposal.steps[0].value == "New York"
    assert driver.destination("New York") == "New York"
    assert destination_page.locator("input").input_value() == "New York"


def test_hotel_form_wins_over_unrelated_visible_location_field(destination_page):
    destination_page.set_content(
        '<header><input aria-label="City" value="Do not change"></header>'
        + FORM.replace("INPUT", '<input name=ss placeholder="Search in your own words">')
    )
    driver = HotelSearchDriver(destination_page, "https://example.org")
    assert driver.inventory()["destination_diagnostics"]["matching_fields"] == 1
    assert driver.destination("New York") == "New York"
    assert destination_page.locator("header input").input_value() == "Do not change"
    controls = inspect_search_controls(destination_page)
    # Already entered: the planner must now advance to a calendar, not fill the header.
    proposal = destination_partial_fallback(controls, REQUEST)
    assert proposal.steps[0].action == "open_control"


def test_real_duplicate_hotel_forms_return_ambiguity_not_free_text_advice(destination_page):
    form = FORM.replace("INPUT", '<input name=ss placeholder="Enter destination">')
    destination_page.set_content(form + form)
    driver = HotelSearchDriver(destination_page, "https://example.org")
    with pytest.raises(WebsiteError, match="Multiple destination") as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert caught.value.navigation_result["destination_diagnostics"]["matching_fields"] == 2
    assert destination_page.locator("input").evaluate_all("es=>es.map(e=>e.value)") == ["", ""]


def test_hidden_disabled_and_readonly_duplicates_do_not_mask_usable_input(destination_page):
    destination_page.set_content(
        FORM.replace(
            "INPUT",
            """
      <input name=ss placeholder="Search in your own words">
      <input name=ss placeholder="Enter destination" hidden>
      <input name=ss placeholder="Enter destination" disabled>
      <input name=ss placeholder="Enter destination" readonly>
    """,
        )
    )
    state = HotelSearchDriver(destination_page, "https://example.org").inventory()
    assert state["destination"] is not None
    assert state["destination_diagnostics"]["matching_fields"] == 1


def test_standalone_free_text_is_not_reclassified_from_name_alone(destination_page):
    destination_page.set_content(
        '<form><input name=ss placeholder="Search in your own words"><button>Search</button></form>'
    )
    driver = HotelSearchDriver(destination_page, "https://example.org")
    assert driver.inventory()["destination"] is None
    controls = inspect_search_controls(destination_page)
    assert next(row for row in controls if row["kind"] == "input")["purpose"] == "query"
    assert destination_partial_fallback(controls, REQUEST) is None


def test_detection_diagnostics_do_not_read_password_or_input_values(destination_page):
    destination_page.set_content(
        FORM.replace(
            "INPUT",
            """
      <input name=ss placeholder="Search in your own words" value="private-entered-text">
      <input name=email type=email value="private@example.org">
      <input type=password value="not-for-diagnostics">
    """,
        )
    )
    diagnostics = HotelSearchDriver(destination_page, "https://example.org").inventory()[
        "destination_diagnostics"
    ]
    assert "private" not in str(diagnostics) and "not-for-diagnostics" not in str(diagnostics)
    assert len(diagnostics["candidates"]) == 1


@pytest.fixture
def destination_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_ui_exposes_detection_counts_and_reasons_for_earlier_failures(destination_ui):
    destination_ui.evaluate("""() => {
      const report={status:'needs_review',submitted:false,actions:[],requirements:[],
        guidance:'Multiple destination fields',destination_diagnostics:{
          matching_fields:2,structured_matching_fields:2,visible_text_fields:2,
          candidates:[{name:'ss',label:'Search in your own words',
            reason:'recognized',structured:true}]}};
      showNavigationEvidence({navigation_result:report,navigation_history:[report,report]});
      setStudioStep('work');
    }""")
    destination_ui.get_by_text("Destination field detection", exact=True).click()
    assert destination_ui.get_by_text("2 matching destination field(s)", exact=False).is_visible()
    assert destination_ui.get_by_text("Search in your own words [ss]", exact=False).is_visible()
    destination_ui.get_by_text("Earlier reviewed steps", exact=True).click()
    assert "needs review: Multiple destination fields" in destination_ui.evaluate(
        "navigationEvidence.textContent"
    )
    assert destination_ui.evaluate("window.fixtureCalls") == []
