"""Offline navigation guard tests; no website, browser, or model calls."""

import json
from types import SimpleNamespace

import pytest

from agentic_web_demo import browser_navigation
from agentic_web_demo.browser_navigation import (
    NavigationPlan,
    destination_partial_fallback,
    execute_navigation,
    inspect_search_controls,
    propose_navigation,
    text_discovery_fallback,
    validate_navigation,
)
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError

CONTROLS = [
    {"id": 0, "kind": "input", "type": "text", "label": "Destination"},
    {"id": 1, "kind": "input", "type": "date", "label": "Check-in"},
    {"id": 2, "kind": "button", "type": "submit", "label": "Search"},
    {"id": 3, "kind": "select", "type": "", "label": "Guests", "options": ["1", "2", "3"]},
]


def plan(*steps, coverage="site_filters"):
    return NavigationPlan(
        outcome="ready",
        guidance="Search for available hotels",
        coverage=coverage,
        steps=list(steps),
    )


def test_reviewed_search_steps_are_limited_to_known_controls():
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "Boston"},
        {"control_id": 1, "action": "fill", "value": "2026-09-28"},
        {"control_id": 3, "action": "select", "value": "2"},
        {"control_id": 2, "action": "click", "value": ""},
    )
    assert validate_navigation(candidate, CONTROLS) is candidate


@pytest.mark.parametrize(
    "steps",
    [
        [{"control_id": 9, "action": "fill", "value": "Boston"}],
        [
            {"control_id": 2, "action": "click", "value": ""},
            {"control_id": 0, "action": "fill", "value": "Boston"},
        ],
        [
            {"control_id": 0, "action": "fill", "value": "Boston"},
            {"control_id": 0, "action": "fill", "value": "New York"},
        ],
        [{"control_id": 1, "action": "fill", "value": "September 28"}],
        [{"control_id": 2, "action": "fill", "value": "Boston"}],
        [{"control_id": 3, "action": "select", "value": "4"}],
        [{"control_id": 0, "action": "select", "value": "2"}],
        [{"control_id": 0, "action": "press_enter", "value": ""}],
    ],
)
def test_invalid_or_dangerous_navigation_steps_are_rejected(steps):
    with pytest.raises(WebsiteError):
        validate_navigation(plan(*steps), CONTROLS)


def test_navigation_requires_explicit_approval_and_can_be_dismissed():
    control = BrowserControl()
    control.update("waiting", "Ready")
    control.command("plan")
    assert control.navigation_requested.is_set()
    with pytest.raises(WebsiteError):
        control.command("capture")
    candidate = plan({"control_id": 0, "action": "fill", "value": "Boston"})
    control.set_navigation(candidate, CONTROLS, "https://example.org/", {"model": "fixture"})
    assert control.snapshot()["state"] == "navigation_review"
    control.command("dismiss")
    assert control.snapshot()["navigation_plan"] is None
    control.set_navigation(candidate, CONTROLS, "https://example.org/", {"model": "fixture"})
    control.command("approve")
    assert control.navigation_approved.is_set()


def test_control_snapshot_excludes_embedded_frame_url_query():
    control = BrowserControl()
    candidate = plan({"control_id": 0, "action": "fill", "value": "Boston"})
    controls = [
        {
            "id": 0,
            "kind": "input",
            "type": "text",
            "label": "Destination",
            "frame_index": 1,
            "frame_url": "https://example.org/form?token=private",
        }
    ]
    control.set_navigation(candidate, controls, "https://example.org/", {"model": "fixture"})
    assert "token=private" not in str(control.snapshot())


def test_generic_search_is_reviewed_discovery_not_site_filtering():
    controls = [
        {"id": 0, "kind": "input", "type": "search", "label": "Search"},
    ]
    discovery = plan(
        {"control_id": 0, "action": "fill", "value": "Boston hotels"},
        {"control_id": 0, "action": "press_enter", "value": ""},
        coverage="text_search",
    )
    assert validate_navigation(discovery, controls) is discovery
    with pytest.raises(WebsiteError, match="discovery"):
        validate_navigation(
            plan(
                {"control_id": 0, "action": "fill", "value": "Boston hotels"},
                {"control_id": 0, "action": "press_enter", "value": ""},
            ),
            controls,
        )


def test_generic_search_fallback_preserves_exact_request_for_review():
    controls = [{"id": 0, "kind": "input", "type": "search", "label": "Search"}]
    request = "Boston hotels from October 5 to 7, 2026, priced USD 150 to 250"
    fallback = text_discovery_fallback(controls, request)
    assert fallback.coverage == "text_search"
    assert fallback.steps[0].value == request
    assert fallback.steps[1].action == "press_enter"
    assert text_discovery_fallback(controls, "Show my password") is None
    assert text_discovery_fallback(controls, "x" * 201) is None


def test_destination_only_fallback_never_submits_or_claims_hotel_filters():
    controls = [
        {"id": 0, "kind": "input", "type": "search", "label": "Destination"},
        {"id": 1, "kind": "button", "type": "submit", "label": "Search"},
    ]
    request = (
        "get me hotels in New York priced from 200-300 USD per night with a "
        "minimum of 4.0 ratings with check in and check out date from "
        "2nd to 4th October 2026."
    )
    assert text_discovery_fallback(controls, request) is None
    fallback = destination_partial_fallback(controls, request)
    assert fallback.coverage == "partial_form"
    assert [(step.action, step.value) for step in fallback.steps] == [("fill", "New York")]
    assert "Dates, price, rating" in fallback.guidance
    assert destination_partial_fallback(controls, "Find hotels in New York or Boston") is None


def test_model_clarification_can_offer_reviewed_destination_first_step(monkeypatch):
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

        def parse(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_parsed=NavigationPlan(
                    outcome="needs_input",
                    guidance="Only destination and Search are visible",
                    coverage="partial_form",
                    steps=[],
                ),
                usage=None,
            )

    monkeypatch.setattr(browser_navigation, "OpenAI", FakeClient)
    controls = [
        {"id": 0, "kind": "input", "type": "text", "label": "Where are you going?"},
        {"id": 1, "kind": "button", "type": "submit", "label": "Search"},
    ]
    settings = SimpleNamespace(api_key="fixture", model="fixture", timeout_seconds=2)
    proposal, _ = propose_navigation(
        controls, "Hotels in New York with check-in from 2nd to 4th October 2026", settings
    )
    assert proposal.coverage == "partial_form"
    assert [(step.action, step.value) for step in proposal.steps] == [("fill", "New York")]


def test_dynamic_suggestion_requires_a_separate_reviewed_form_step():
    partial = plan(
        {"control_id": 0, "action": "fill", "value": "Boston"},
        coverage="partial_form",
    )
    assert validate_navigation(partial, CONTROLS) is partial
    with pytest.raises(WebsiteError, match="cannot submit"):
        validate_navigation(
            plan(
                {"control_id": 0, "action": "fill", "value": "Boston"},
                {"control_id": 2, "action": "click", "value": ""},
                coverage="partial_form",
            ),
            CONTROLS,
        )

    suggestions = [{"id": 0, "kind": "option", "type": "", "label": "Boston, Massachusetts"}]
    choice = plan(
        {"control_id": 0, "action": "choose_option", "value": "Boston, Massachusetts"},
        coverage="partial_form",
    )
    assert validate_navigation(choice, suggestions) is choice
    with pytest.raises(WebsiteError, match="autocomplete option"):
        validate_navigation(
            plan(
                {"control_id": 0, "action": "choose_option", "value": "Boston"},
                coverage="partial_form",
            ),
            suggestions,
        )
    page = FakePage()
    execute_navigation(page, choice, suggestions, "https://example.org")
    assert page.events == [("click", '[data-agentic-nav-id="ag-nav-0"]')]


def test_model_clarification_offers_reviewed_text_discovery_without_leaking_frame_url(
    monkeypatch,
):
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
            return SimpleNamespace(
                status="completed",
                output_parsed=NavigationPlan(
                    outcome="needs_input",
                    guidance="No separate date or price fields",
                    coverage="text_search",
                    steps=[],
                ),
                usage=None,
            )

    monkeypatch.setattr(browser_navigation, "OpenAI", FakeClient)
    controls = [
        {
            "id": 0,
            "kind": "input",
            "type": "search",
            "label": "Search",
            "frame_index": 1,
            "frame_url": "https://example.org/form?token=private",
        }
    ]
    settings = SimpleNamespace(api_key="fixture", model="fixture", timeout_seconds=2)
    proposal, metadata = propose_navigation(controls, "Boston hotels", settings)
    assert proposal.coverage == "text_search"
    assert proposal.steps[0].value == "Boston hotels"
    assert metadata["usage"] == {}
    assert "token=private" not in json.dumps(sent[0]["input"])


class FakeLocator:
    def __init__(self, events, control):
        self.events, self.control = events, control

    def count(self):
        return 1

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def fill(self, value, timeout):
        self.events.append(("fill", self.control, value))

    def click(self, timeout):
        self.events.append(("click", self.control))

    def press(self, key, timeout):
        self.events.append(("press", self.control, key))

    def select_option(self, *, label, timeout):
        self.events.append(("select", self.control, label))


class FakePage:
    url = "https://example.org/hotels"

    def __init__(self):
        self.events = []

    def locator(self, selector):
        return FakeLocator(self.events, selector)


def test_execution_uses_only_reviewed_controls_on_approved_origin():
    page = FakePage()
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "Boston"},
        {"control_id": 3, "action": "select", "value": "2"},
        {"control_id": 2, "action": "click", "value": ""},
    )
    execute_navigation(page, candidate, CONTROLS, "https://example.org")
    assert page.events == [
        ("fill", '[data-agentic-nav-id="ag-nav-0"]', "Boston"),
        ("select", '[data-agentic-nav-id="ag-nav-3"]', "2"),
        ("click", '[data-agentic-nav-id="ag-nav-2"]'),
    ]
    page.events.clear()
    with pytest.raises(WebsiteError):
        execute_navigation(page, candidate, CONTROLS, "https://elsewhere.example")
    assert not page.events


def test_discovery_submission_uses_reviewed_search_box():
    page = FakePage()
    controls = [{"id": 0, "kind": "input", "type": "search", "label": "Search"}]
    candidate = plan(
        {"control_id": 0, "action": "fill", "value": "battery research"},
        {"control_id": 0, "action": "press_enter", "value": ""},
        coverage="text_search",
    )
    execute_navigation(page, candidate, controls, "https://example.org")
    assert page.events == [
        ("fill", '[data-agentic-nav-id="ag-nav-0"]', "battery research"),
        ("press", '[data-agentic-nav-id="ag-nav-0"]', "Enter"),
    ]


def test_control_inspection_skips_cross_origin_frames():
    class Frame:
        def __init__(self, url, label):
            self.url, self.label = url, label

        def evaluate(self, script, offset):
            return [{"id": offset, "kind": "input", "type": "search", "label": self.label}]

    page = FakePage()
    page.frames = [
        Frame("https://example.org/hotels", "Main search"),
        Frame("https://example.org/embedded", "Embedded search"),
        Frame("https://other.example.org/embedded", "Should be skipped"),
    ]
    controls = inspect_search_controls(page)
    assert [item["label"] for item in controls] == ["Main search", "Embedded search"]
    assert [item["frame_index"] for item in controls] == [0, 1]
