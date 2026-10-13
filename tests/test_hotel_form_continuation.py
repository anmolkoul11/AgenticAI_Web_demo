"""Request grounding and incremental travel forms; no live sites or paid calls."""

import json

import pytest
from test_browser_navigation import plan
from test_navigation_semantics import (
    SemanticPage,
    date_range_control,
    destination_control,
    mocked_model,
    submit_control,
)
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo.browser_navigation import (
    NavigationPlan,
    check_requirements,
    destination_partial_fallback,
    execute_navigation,
    ground_requirements,
    guest_counts,
    inspect_search_controls,
    propose_navigation,
    requested_dates,
    requested_guests,
    validate_navigation,
)
from agentic_web_demo.custom_fetch import WebsiteError

NY_REQUEST = (
    "give me hotels in New York with price ranging from 250-350 USD per night, "
    "with checking in and checking out date as 28-30 October 2026 for 2 adults, 1 room"
)


def occupancy_control(**changes):
    return {
        "id": 3,
        "kind": "opener",
        "type": "button",
        "purpose": "guests",
        "label": "Number of travelers and rooms. Currently selected: "
        "2 adults · 0 children · 1 room",
        "current_value": "2 adults · 0 children · 1 room",
        **changes,
    }


def controls_after_destination():
    return [
        destination_control(current_value="New York"),
        date_range_control(),
        submit_control(),
        occupancy_control(),
    ]


def test_exact_reported_prompt_has_complete_dates_and_named_occupancy():
    assert requested_dates(NY_REQUEST) == ["2026-10-28", "2026-10-30"]
    assert requested_guests(NY_REQUEST) == "2 adults, 1 room"
    assert guest_counts(NY_REQUEST) == {"adults": 2, "rooms": 1}


def test_model_missing_flags_do_not_erase_known_dates_guests_or_invent_other():
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "New York"}, coverage="partial_form"
    )
    candidate.missing_fields = ["check_in", "check_out", "guests", "other"]
    grounded = ground_requirements(candidate, NY_REQUEST)
    assert grounded.missing_fields == []
    assert {item.field: item.value for item in grounded.requirements} == {
        "destination": "New York",
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "guests": "2 adults, 1 room",
    }


def test_matching_default_occupancy_does_not_need_an_unnecessary_widget_action():
    controls = controls_after_destination()
    candidate = destination_partial_fallback(controls, NY_REQUEST)
    assert [(item.action, item.control_id) for item in candidate.steps] == [("open_control", 1)]
    page = SemanticPage(controls)
    report = execute_navigation(
        page, candidate, controls, "https://example.org", instructions=NY_REQUEST
    )
    assert report["missing_fields"] == []
    assert report["pending_fields"] == ["check_in", "check_out"]
    assert (
        next(item for item in report["requirements"] if item["field"] == "guests")["status"]
        == "verified_in_form"
    )
    assert report["submitted"] is False
    assert page.events == [("click", '[data-agentic-nav-id="ag-nav-1"]')]


def test_grounding_restores_room_count_omitted_by_model_without_guessing():
    candidate = plan(
        {"control_id": 1, "action": "open_control", "value": ""}, coverage="partial_form"
    )
    candidate = NavigationPlan.model_validate(
        {
            **candidate.model_dump(),
            "requirements": [
                {"field": "guests", "value": "2 adults", "application": "site"},
            ],
        }
    )
    grounded = ground_requirements(candidate, NY_REQUEST)
    assert (
        next(item for item in grounded.requirements if item.field == "guests").value
        == "2 adults, 1 room"
    )


def test_repeated_model_destination_fill_advances_to_calendar_instead(monkeypatch):
    sent, settings = mocked_model(
        monkeypatch,
        plan({"control_id": 0, "action": "fill", "value": "New York"}, coverage="partial_form"),
    )
    proposal, metadata = propose_navigation(controls_after_destination(), NY_REQUEST, settings)
    assert [(item.action, item.control_id) for item in proposal.steps] == [("open_control", 1)]
    assert proposal.missing_fields == []
    assert len(sent) == 1
    facts = json.loads(sent[0]["input"][1]["content"])["request_facts"]
    assert facts["missing_fields"] == []
    assert any(item["field"] == "guests" for item in facts["requirements"])
    assert metadata["prompt_version"] == "site-search-navigation-v5"


def test_false_model_missing_year_message_is_not_preserved_for_full_request(monkeypatch):
    _, settings = mocked_model(
        monkeypatch,
        NavigationPlan(
            outcome="needs_input",
            coverage="partial_form",
            steps=[],
            guidance="Provide a missing year and guest information.",
            missing_fields=["check_in", "check_out", "guests", "other"],
        ),
    )
    proposal, _ = propose_navigation(controls_after_destination(), NY_REQUEST, settings)
    assert proposal.missing_fields == []
    assert "missing year" not in proposal.guidance
    assert proposal.steps[0].action == "open_control"


def test_partial_plan_removes_redundant_fill_but_keeps_reviewed_calendar_opener():
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "New York"},
        {"control_id": 1, "action": "open_control", "value": ""},
        coverage="partial_form",
    )
    result = validate_navigation(candidate, controls_after_destination(), instructions=NY_REQUEST)
    assert [(step.action, step.control_id) for step in result.steps] == [("open_control", 1)]


def test_visible_exact_full_date_is_next_step_not_another_destination_fill():
    controls = controls_after_destination() + [
        {
            "id": 4,
            "kind": "option",
            "type": "button",
            "label": "28 October 2026",
            "date_value": "2026-10-28",
        }
    ]
    result = destination_partial_fallback(controls, NY_REQUEST)
    assert [(step.action, step.value) for step in result.steps] == [
        ("choose_option", "28 October 2026")
    ]


def test_wrong_month_does_not_close_calendar_or_guess_a_day():
    controls = controls_after_destination() + [
        {
            "id": 4,
            "kind": "option",
            "type": "button",
            "label": "28 September 2026",
            "date_value": "2026-09-28",
        }
    ]
    assert destination_partial_fallback(controls, NY_REQUEST) is None


@pytest.mark.parametrize("summary", ["2 adults · 1 room", "2 adults · 0 children · 1 room"])
def test_occupancy_summary_confirms_named_components(summary):
    controls = [occupancy_control(current_value=summary)]
    candidate = ground_requirements(
        plan({"control_id": 3, "action": "open_control", "value": ""}, coverage="partial_form"),
        NY_REQUEST,
    )
    checks = check_requirements(SemanticPage(controls), candidate, controls)
    assert (
        next(item for item in checks if item["field"] == "guests")["status"] == "verified_in_form"
    )


@pytest.mark.parametrize("summary", ["1 adult · 1 room", "2 adults · 2 rooms", "2 adults", "2"])
def test_mismatched_or_incomplete_occupancy_is_not_verified(summary):
    controls = [occupancy_control(current_value=summary)]
    candidate = ground_requirements(
        plan({"control_id": 3, "action": "open_control", "value": ""}, coverage="partial_form"),
        NY_REQUEST,
    )
    checks = check_requirements(SemanticPage(controls), candidate, controls)
    assert next(item for item in checks if item["field"] == "guests")["status"] == "unconfirmed"


def test_separate_native_adult_and_room_fields_are_verified_together():
    controls = [
        {"id": 3, "kind": "input", "type": "number", "label": "Adults", "current_value": "2"},
        {"id": 4, "kind": "input", "type": "number", "label": "Rooms", "current_value": "1"},
    ]
    candidate = ground_requirements(
        plan({"control_id": 3, "action": "fill", "value": "2"}, coverage="partial_form"), NY_REQUEST
    )
    candidate = validate_navigation(candidate, controls, instructions=NY_REQUEST)
    checks = check_requirements(SemanticPage(controls), candidate, controls)
    assert (
        next(item for item in checks if item["field"] == "guests")["status"] == "verified_in_form"
    )


def test_room_count_fill_cannot_conflict_with_explicit_occupancy():
    controls = [
        {"id": 3, "kind": "input", "type": "number", "label": "Rooms", "current_value": "1"}
    ]
    with pytest.raises(WebsiteError, match="conflicts"):
        validate_navigation(
            plan({"control_id": 3, "action": "fill", "value": "2"}, coverage="partial_form"),
            controls,
            instructions=NY_REQUEST,
        )


def test_conflicting_named_request_counts_need_clarification():
    with pytest.raises(WebsiteError, match="conflicting counts"):
        requested_guests("Hotels in Boston for 2 adults or 3 adults, 1 room")


def test_blank_occupancy_field_is_not_hidden_by_a_convenient_summary():
    controls = [
        occupancy_control(),
        {
            "id": 4,
            "kind": "input",
            "type": "number",
            "label": "Rooms",
            "current_value": "",
        },
    ]
    candidate = ground_requirements(
        plan({"control_id": 3, "action": "open_control", "value": ""}, coverage="partial_form"),
        NY_REQUEST,
    )
    checks = check_requirements(SemanticPage(controls), candidate, controls)
    assert next(item for item in checks if item["field"] == "guests")["status"] == "unconfirmed"


@pytest.fixture
def local_page(request):
    yield from shared_local_page.__wrapped__(request)


def test_real_form_can_progress_from_destination_to_dated_options(local_page):
    local_page.set_content("""<form>
      <input name="ss" aria-label="Destination" value="New York">
      <button type="button" aria-label="Select dates Check-in — Check-out"
        onclick="document.getElementById('calendar').hidden=false;
          this.setAttribute('aria-expanded','true')">Select dates</button>
      <button type="button" aria-label="Number of travelers and rooms. Currently selected:
        2 adults · 0 children · 1 room">2 adults · 0 children · 1 room</button>
      <div id="calendar" role="dialog" hidden>
        <button type="button" data-date="2026-10-28" aria-label="28 October 2026"
          onclick="document.querySelector('[name=checkin]').value='2026-10-28'">28</button>
        <button type="button" data-date="2026-10-30" aria-label="30 October 2026"
          onclick="document.querySelector('[name=checkout]').value='2026-10-30'">30</button>
      </div>
      <input type="hidden" name="checkin"><input type="hidden" name="checkout">
      <button type="submit">Search</button></form>""")
    for expected_action, expected_value in [
        ("open_control", ""),
        ("choose_option", "28 October 2026"),
        ("choose_option", "30 October 2026"),
    ]:
        controls = inspect_search_controls(local_page)
        proposal = destination_partial_fallback(controls, NY_REQUEST)
        assert [(step.action, step.value) for step in proposal.steps] == [
            (expected_action, expected_value)
        ]
        report = execute_navigation(
            local_page, proposal, controls, "https://example.org", instructions=NY_REQUEST
        )
        assert report["submitted"] is False
        assert report["missing_fields"] == []
    assert report["pending_fields"] == []
