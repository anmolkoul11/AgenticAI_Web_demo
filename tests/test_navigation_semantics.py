"""Purpose-aware search regressions; models are mocked and browser fixtures opt-in."""

import json
from types import SimpleNamespace

import pytest
from test_browser_navigation import FakeLocator, FakePage, plan
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo import browser_navigation
from agentic_web_demo.browser_navigation import (
    CONTROL_STATE,
    NavigationPlan,
    control_purpose,
    destination_partial_fallback,
    execute_navigation,
    inspect_search_controls,
    propose_navigation,
    requested_dates,
    text_discovery_fallback,
    validate_navigation,
)
from agentic_web_demo.custom_fetch import WebsiteError

HOTEL_REQUEST = (
    "Find hotels in Boston from 2026-11-02 to 2026-11-04, "
    "priced between 150 and 250 USD per night with rating at least 4 out of 5."
)


def destination_control(**changes):
    return {
        "id": 0,
        "kind": "input",
        "type": "search",
        "label": "Search",
        "name": "ss",
        "placeholder": "Where are you going?",
        "purpose": "destination",
        "form_kind": "hotel_search",
        "context": "destination-search",
        "current_value": "",
        **changes,
    }


def date_range_control(**changes):
    return {
        "id": 1,
        "kind": "opener",
        "type": "button",
        "label": "Check-in date — Check-out date",
        "name": "",
        "placeholder": "",
        "purpose": "date_range",
        "form_kind": "hotel_search",
        "context": "Hotel search. Check-in. Check-out.",
        "current_value": "",
        "date_values": {},
        **changes,
    }


def submit_control(**changes):
    return {
        "id": 2,
        "kind": "button",
        "type": "submit",
        "label": "Search",
        **changes,
    }


class SemanticLocator(FakeLocator):
    """Preserve the legacy readback fake while supplying current semantic identity."""

    def evaluate(self, script):
        state = super().evaluate(script)
        control_id = int(self.control.split("ag-nav-")[1].split('"')[0])
        control = next(item for item in self.known if item["id"] == control_id)
        for key in (
            "name",
            "placeholder",
            "context",
            "form_kind",
            "purpose",
            "role",
            "autocomplete",
            "date_values",
        ):
            if key in control:
                state[key] = control[key]
        return state


class SemanticPage(FakePage):
    def __init__(self, controls):
        super().__init__()
        self.controls = controls

    def locator(self, selector):
        return SemanticLocator(self.events, selector, self.controls)


def mocked_model(monkeypatch, candidate):
    sent = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.http_client = kwargs["http_client"]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.http_client.close()

        @property
        def responses(self):
            return self

        def parse(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(status="completed", output_parsed=candidate, usage=None)

    monkeypatch.setattr(browser_navigation, "OpenAI", FakeClient)
    return sent, SimpleNamespace(api_key="fixture", model="fixture", timeout_seconds=2)


@pytest.mark.parametrize(
    ("control", "expected"),
    [
        (destination_control(), "destination"),
        (
            destination_control(purpose="", name="destination", placeholder="", context=""),
            "destination",
        ),
        (
            destination_control(purpose="", name="", placeholder="Destination", context=""),
            "destination",
        ),
        (date_range_control(), "date_range"),
        (
            {"id": 0, "kind": "input", "type": "search", "label": "Search topics"},
            "query",
        ),
    ],
)
def test_search_purpose_uses_semantics_not_generic_visible_label(control, expected):
    assert control_purpose(control) == expected


@pytest.mark.parametrize(
    "controls",
    [
        [destination_control(), submit_control()],
        [
            {"id": 0, "kind": "input", "type": "search", "label": "Search"},
            date_range_control(),
            submit_control(),
        ],
        [{"id": 0, "kind": "input", "type": "search", "label": "Search"}],
    ],
)
def test_complete_hotel_prompt_is_never_exact_text_discovery_fallback(controls):
    assert text_discovery_fallback(controls, HOTEL_REQUEST) is None


def test_actual_keyword_search_still_has_reviewed_discovery_fallback():
    controls = [{"id": 0, "kind": "input", "type": "search", "label": "Search topics"}]
    candidate = text_discovery_fallback(controls, "battery research")
    assert candidate.coverage == "text_search"
    assert candidate.steps[0].value == "battery research"
    assert candidate.steps[1].action == "press_enter"


@pytest.mark.parametrize(
    "search_request",
    [
        "Hotels in Boston from October 28-30, 2026",
        "Hotels in Boston from October 28 to October 30, 2026",
        "Hotels in Boston: check-out October 30, 2026; check-in October 28, 2026",
        "Hotels in Boston: check-out 2026-10-30; check-in 2026-10-28",
    ],
)
def test_full_requested_dates_cover_shared_year_and_explicit_endpoint_labels(search_request):
    assert requested_dates(search_request) == ["2026-10-28", "2026-10-30"]


def test_repeated_month_range_preserves_distinct_checkout_month():
    assert requested_dates("October 28 to November 2, 2026") == [
        "2026-10-28",
        "2026-11-02",
    ]


@pytest.mark.parametrize("action", ["fill", "choose_option"])
@pytest.mark.parametrize("declare_checkout", [True, False])
def test_one_explicit_date_does_not_authorize_an_invented_second_date(action, declare_checkout):
    request = "Find hotels in Boston with check-in 2026-11-02."
    control = (
        {
            "id": 0,
            "kind": "input",
            "type": "date",
            "label": "Check-out",
            "purpose": "check_out",
        }
        if action == "fill"
        else {
            "id": 0,
            "kind": "option",
            "type": "button",
            "label": "4 November 2026",
            "date_value": "2026-11-04",
        }
    )
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review the checkout date",
        coverage="partial_form",
        steps=[
            {
                "control_id": 0,
                "action": action,
                "value": "2026-11-04" if action == "fill" else "4 November 2026",
            }
        ],
        requirements=[{"field": "check_in", "value": "2026-11-02", "application": "site"}]
        + (
            [{"field": "check_out", "value": "2026-11-04", "application": "site"}]
            if declare_checkout
            else []
        ),
    )
    with pytest.raises(WebsiteError):
        validate_navigation(candidate, [control], instructions=request)


def test_month_named_destination_does_not_invent_a_stay_date_requirement():
    request = "Find hotels in June Lake priced below 250 USD per night."
    candidate = destination_partial_fallback([destination_control()], request)
    assert candidate.steps[0].value == "June Lake"
    assert candidate.missing_fields == []
    assert not any(item.field in {"check_in", "check_out"} for item in candidate.requirements)
    assert requested_dates(request) == []


def test_numeric_budget_does_not_supply_an_unstated_calendar_year():
    request = (
        "Find hotels in Boston with check-in October 28 and check-out October 30, "
        "with a total budget of 2000 USD."
    )
    candidate = destination_partial_fallback([destination_control()], request)
    assert requested_dates(request) == []
    assert {"check_in", "check_out"} <= set(candidate.missing_fields)
    assert [(step.action, step.value) for step in candidate.steps] == [("fill", "Boston")]


def test_calendar_opener_prevents_even_short_text_fallback():
    controls = [
        {"id": 0, "kind": "input", "type": "search", "label": "Search"},
        date_range_control(),
    ]
    assert text_discovery_fallback(controls, "Boston hotels") is None


def test_destination_fallback_fills_only_city_despite_generic_search_label():
    candidate = destination_partial_fallback(
        [destination_control(), date_range_control(), submit_control()], HOTEL_REQUEST
    )
    assert candidate.coverage == "partial_form"
    assert [(step.action, step.value) for step in candidate.steps] == [("fill", "Boston")]


def test_destination_does_not_accept_whole_request_even_without_original_request():
    controls = [destination_control(), submit_control()]
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": HOTEL_REQUEST},
        coverage="partial_form",
    )
    with pytest.raises(WebsiteError):
        validate_navigation(candidate, controls)


def test_structured_form_cannot_be_relabelled_as_keyword_discovery():
    controls = [destination_control(), date_range_control(), submit_control()]
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "Boston hotels"},
        {"control_id": 2, "action": "click", "value": ""},
        coverage="text_search",
    )
    with pytest.raises(WebsiteError):
        validate_navigation(candidate, controls, instructions=HOTEL_REQUEST)


@pytest.mark.parametrize(
    ("controls", "step"),
    [
        ([destination_control()], {"control_id": 0, "action": "fill", "value": "New York"}),
        (
            [
                {
                    "id": 0,
                    "kind": "input",
                    "type": "date",
                    "label": "Check-in",
                    "purpose": "check_in",
                }
            ],
            {"control_id": 0, "action": "fill", "value": "2026-11-03"},
        ),
    ],
)
def test_values_cannot_contradict_explicit_requested_site_fields(controls, step):
    with pytest.raises(WebsiteError):
        validate_navigation(
            plan(step, coverage="partial_form"), controls, instructions=HOTEL_REQUEST
        )


def test_submission_preflight_stops_before_mutating_an_unrepresentable_form():
    controls = [destination_control(), submit_control()]
    page = SemanticPage(controls)
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review the search",
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
    with pytest.raises(WebsiteError) as failed:
        execute_navigation(
            page, candidate, controls, "https://example.org", instructions=HOTEL_REQUEST
        )
    assert page.events == []
    assert failed.value.navigation_result["preflight"]
    assert failed.value.navigation_result["submitted"] is False


def test_combined_calendar_range_confirms_both_independent_requested_dates():
    controls = [
        destination_control(current_value="Boston"),
        date_range_control(date_values={"check_in": "2026-11-02", "check_out": "2026-11-04"}),
        submit_control(),
    ]
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Search the reviewed dates",
        coverage="site_filters",
        steps=[{"control_id": 2, "action": "click", "value": ""}],
        requirements=[
            {"field": "destination", "value": "Boston", "application": "site"},
            {"field": "check_in", "value": "2026-11-02", "application": "site"},
            {"field": "check_out", "value": "2026-11-04", "application": "site"},
        ],
    )
    page = SemanticPage(controls)
    report = execute_navigation(page, candidate, controls, "https://example.org")
    assert report["submitted"] is True
    assert all(item["status"] == "verified_in_form" for item in report["requirements"])
    assert page.events == [("click", '[data-agentic-nav-id="ag-nav-2"]')]
    assert report["results_verified"] is False


def test_incomplete_combined_calendar_cannot_confirm_checkout():
    controls = [
        destination_control(current_value="Boston"),
        date_range_control(date_values={"check_in": "2026-11-02"}),
        submit_control(),
    ]
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="site_filters",
        steps=[{"control_id": 2, "action": "click", "value": ""}],
        requirements=[
            {"field": "check_in", "value": "2026-11-02", "application": "site"},
            {"field": "check_out", "value": "2026-11-04", "application": "site"},
        ],
    )
    page = SemanticPage(controls)
    with pytest.raises(WebsiteError) as failed:
        execute_navigation(page, candidate, controls, "https://example.org")
    assert page.events == []
    assert failed.value.navigation_result["submitted"] is False


def test_impossible_date_in_combined_widget_never_verifies_or_submits():
    controls = [
        destination_control(current_value="Boston"),
        date_range_control(date_values={"check_in": "2026-11-31", "check_out": "2026-12-04"}),
        submit_control(),
    ]
    candidate = NavigationPlan(
        outcome="ready",
        guidance="Review",
        coverage="site_filters",
        steps=[{"control_id": 2, "action": "click", "value": ""}],
        requirements=[
            {"field": "check_in", "value": "2026-11-30", "application": "site"},
            {"field": "check_out", "value": "2026-12-04", "application": "site"},
        ],
    )
    page = SemanticPage(controls)
    with pytest.raises(WebsiteError):
        execute_navigation(page, candidate, controls, "https://example.org")
    assert page.events == []


def test_same_label_different_field_identity_stops_before_fill():
    reviewed = [destination_control()]
    page = SemanticPage([destination_control(name="site_keyword_query")])
    with pytest.raises(WebsiteError):
        execute_navigation(
            page,
            plan({"control_id": 0, "action": "fill", "value": "Boston"}, coverage="partial_form"),
            reviewed,
            "https://example.org",
        )
    assert page.events == []


def test_missing_year_partial_destination_keeps_original_clarification(monkeypatch):
    request = "Find hotels in Boston with check-in October 28 and check-out October 30."
    sent, settings = mocked_model(
        monkeypatch,
        NavigationPlan(
            outcome="needs_input",
            guidance="Provide the exact year for October 28 and October 30.",
            coverage="partial_form",
            steps=[],
        ),
    )
    controls = [destination_control(), date_range_control(), submit_control()]
    candidate, metadata = propose_navigation(controls, request, settings)
    assert candidate.coverage == "partial_form"
    assert [(step.action, step.value) for step in candidate.steps] == [("fill", "Boston")]
    assert "year" in candidate.guidance.casefold()
    assert metadata["prompt_version"] == "site-search-navigation-v5"
    assert metadata["plan_source"]
    page = SemanticPage(controls)
    report = execute_navigation(
        page, candidate, controls, "https://example.org", instructions=request
    )
    assert report["submitted"] is False
    assert not any(event[0] in {"click", "press"} for event in page.events)
    assert len(sent) == 1


def test_bad_model_full_prompt_is_replaced_only_by_destination_partial(monkeypatch):
    sent, settings = mocked_model(
        monkeypatch,
        plan(
            {"control_id": 0, "action": "fill", "value": HOTEL_REQUEST},
            {"control_id": 2, "action": "click", "value": ""},
            coverage="text_search",
        ),
    )
    candidate, metadata = propose_navigation(
        [destination_control(), date_range_control(), submit_control()], HOTEL_REQUEST, settings
    )
    assert candidate.coverage == "partial_form"
    assert [(step.action, step.value) for step in candidate.steps] == [("fill", "Boston")]
    assert metadata["plan_source"]
    assert len(sent) == 1


@pytest.mark.parametrize(
    ("outcome", "date_requirements"),
    [
        ("needs_input", []),
        (
            "needs_input",
            [
                {"field": "check_in", "value": "October 28", "application": "site"},
                {"field": "check_out", "value": "October 30", "application": "site"},
            ],
        ),
        (
            "ready",
            [
                {"field": "check_in", "value": "October 28", "application": "site"},
                {"field": "check_out", "value": "October 30", "application": "site"},
            ],
        ),
    ],
)
def test_model_unresolved_dates_can_only_prepare_explicit_destination(
    monkeypatch, outcome, date_requirements
):
    request = "Find hotels in Boston with check-in October 28 and check-out October 30."
    candidate = NavigationPlan(
        outcome=outcome,
        guidance="Provide full dates including year before the hotel search.",
        coverage="partial_form",
        steps=(
            [{"control_id": 0, "action": "fill", "value": "Boston"}] if outcome == "ready" else []
        ),
        requirements=date_requirements,
        missing_fields=["check_in", "check_out"],
    )
    sent, settings = mocked_model(monkeypatch, candidate)
    controls = [destination_control(), date_range_control(), submit_control()]
    proposal, _metadata = propose_navigation(controls, request, settings)
    assert proposal.coverage == "partial_form"
    assert {"check_in", "check_out"} <= set(proposal.missing_fields)
    assert [(step.action, step.value) for step in proposal.steps] == [("fill", "Boston")]
    assert not any(item.field in {"check_in", "check_out"} for item in proposal.requirements)
    assert len(sent) == 1
    page = SemanticPage(controls)
    report = execute_navigation(
        page, proposal, controls, "https://example.org", instructions=request
    )
    assert report["submitted"] is False
    assert not any(event[0] in {"click", "press"} for event in page.events)


def test_planner_receives_current_context_but_not_private_frame_url(monkeypatch):
    candidate = plan(
        {"control_id": 1, "action": "open_control", "value": ""}, coverage="partial_form"
    )
    sent, settings = mocked_model(monkeypatch, candidate)
    controls = [
        destination_control(
            current_value="Boston", frame_index=0, frame_url="https://example.org/?token=private"
        ),
        date_range_control(),
        submit_control(),
    ]
    proposal, _metadata = propose_navigation(controls, HOTEL_REQUEST, settings)
    assert [(step.action, step.control_id) for step in proposal.steps] == [("open_control", 1)]
    payload = json.loads(sent[0]["input"][1]["content"])
    destination = payload["visible_controls"][0]
    assert destination["current_value"] == "Boston"
    assert destination["context"] == controls[0]["context"]
    assert destination["purpose"] == "destination"
    assert "token=private" not in json.dumps(sent[0]["input"])


@pytest.fixture
def semantics_page(request):
    yield from shared_local_page.__wrapped__(request)


def test_dom_hotel_context_identifies_destination_without_useful_aria_label(semantics_page):
    semantics_page.set_content("""<form aria-label="Hotel search">
      <h2>Find your next stay</h2>
      <input type="search" name="ss" aria-label="Search" data-testid="destination-search">
      <button type="button" aria-label="Check-in date — Check-out date">Dates</button>
      <label>Guests<input type="number" name="adults" value="2"></label>
      <button type="submit">Search</button></form>""")
    controls = inspect_search_controls(semantics_page)
    destination = next(
        control
        for control in controls
        if control["kind"] == "input" and control["type"] == "search"
    )
    assert control_purpose(destination) == "destination"
    assert destination["name"] == "ss"
    assert destination["context"]
    assert text_discovery_fallback(controls, HOTEL_REQUEST) is None


def test_dom_combined_calendar_inventory_and_live_readback_agree(semantics_page):
    semantics_page.set_content("""<form aria-label="Hotel search">
      <input aria-label="Destination" value="Boston">
      <button type="button" aria-label="Check-in date — Check-out date">
      Check-in 2 November 2026 — Check-out 4 November 2026</button>
      <button type="submit">Search</button></form>""")
    controls = inspect_search_controls(semantics_page)
    calendar = next(control for control in controls if control_purpose(control) == "date_range")
    expected = {"check_in": "2026-11-02", "check_out": "2026-11-04"}
    assert calendar["date_values"] == expected
    state = semantics_page.locator(f'[data-agentic-nav-id="ag-nav-{calendar["id"]}"]').evaluate(
        CONTROL_STATE
    )
    assert state["date_values"] == expected


def test_dom_calendar_open_refresh_preserves_destination_value(semantics_page):
    semantics_page.set_content("""<form aria-label="Hotel search">
      <input aria-label="Destination" value="Boston">
      <button type="button" aria-label="Check-in date — Check-out date"
      onclick="document.getElementById('calendar').hidden=false;
      this.setAttribute('aria-expanded','true')">Dates</button>
      <button type="submit">Search</button></form>
      <div id="calendar" role="dialog" hidden>
      <button data-date="2026-11-02" aria-label="2 November 2026">2</button>
      <button data-date="2026-11-04" aria-label="4 November 2026">4</button>
      <button>5</button></div>""")
    controls = inspect_search_controls(semantics_page)
    calendar = next(control for control in controls if control_purpose(control) == "date_range")
    report = execute_navigation(
        semantics_page,
        plan(
            {"control_id": calendar["id"], "action": "open_control", "value": ""},
            coverage="partial_form",
        ),
        controls,
        "https://example.org",
        instructions=HOTEL_REQUEST,
    )
    assert report["submitted"] is False
    refreshed = inspect_search_controls(semantics_page)
    destination = next(
        control for control in refreshed if control_purpose(control) == "destination"
    )
    assert destination["current_value"] == "Boston"
    assert {control["date_value"] for control in refreshed if control["kind"] == "option"} == {
        "2026-11-02",
        "2026-11-04",
    }
    assert not any(control["label"] == "5" for control in refreshed)


def test_dom_abbreviated_calendar_options_keep_explicit_full_dates(semantics_page):
    semantics_page.set_content("""<div role="dialog" aria-label="November calendar">
      <button aria-label="2 Nov 2026">2</button>
      <button aria-label="4 Nov 2026">4</button>
      <button>5</button></div>""")
    controls = inspect_search_controls(semantics_page)
    options = [control for control in controls if control["kind"] == "option"]
    assert {control["date_value"] for control in options} == {"2026-11-02", "2026-11-04"}
    assert not any(control["label"] == "5" for control in controls)


def test_dom_calendar_choices_are_not_lost_behind_background_control_limit(semantics_page):
    background = "".join(
        f'<input type="search" aria-label="Background search {index}">' for index in range(42)
    )
    semantics_page.set_content(
        background
        + """<div role="dialog" aria-label="November calendar">
        <button aria-label="2 November 2026">2</button>
        <button aria-label="4 November 2026">4</button></div>"""
    )
    controls = inspect_search_controls(semantics_page)
    options = [control for control in controls if control["kind"] == "option"]
    assert len(controls) == 40
    assert {control["date_value"] for control in options} == {"2026-11-02", "2026-11-04"}
