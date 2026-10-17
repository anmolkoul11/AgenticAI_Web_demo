"""Shared submission/scope regressions: synthetic DOM, no paid or live calls."""

import copy

import pytest

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserCollectionGoal,
    BrowserDecision,
    BrowserRequirement,
)
from agentic_web_demo.browser_context import build_navigation_context
from agentic_web_demo.browser_task import TaskLedger, request_collection_scope
from agentic_web_demo.custom_fetch import WebsiteError


def decision(action, control_id=None, value="", **changes):
    return BrowserDecision(
        action=action,
        control_id=control_id,
        value=value,
        explanation="Use the actual visible control.",
        evidence="Visible source evidence.",
        **changes,
    )


def goal(mode, quote):
    return BrowserCollectionGoal(mode=mode, request_quote=quote, reason="Requested depth.")


@pytest.mark.parametrize(
    "facts",
    [
        {"tag": "BUTTON", "type": "button", "label": "Done", "text": "Done"},
        {"tag": "BUTTON", "type": "submit", "label": "Done", "submits_form": True},
        {"tag": "BUTTON", "label": "Select dates", "expanded": "true"},
        {"tag": "SPAN", "role": "checkbox", "label": "October 28, 2026"},
        {"tag": "BUTTON", "label": "increase Adults", "counter": {"value": 2}},
        {"tag": "A", "label": "SEARCH", "href": "https://example.org/search"},
    ],
)
def test_model_submit_purpose_does_not_turn_widgets_or_links_into_search(facts):
    ledger = TaskLedger("Search for soccer")
    ledger.declare_collection_goal(goal("search_results", "Search for soccer"))
    assert not ledger.is_submit(decision("click", "0:widget", purpose="submit_search"), facts)
    assert ledger.pending_submission is None


def test_generic_fill_and_arbitrary_enter_are_not_search_submission():
    ledger = TaskLedger("Search for soccer")
    ledger.declare_collection_goal(goal("search_results", "Search for soccer"))
    field = {"tag": "INPUT", "type": "search", "label": "Query", "form_scope": "search"}
    assert not ledger.is_submit(
        decision("fill", "0:query", "soccer", purpose="submit_search"), field
    )
    assert ledger.is_submit(decision("press", "0:query", "Enter", purpose="other"), field)
    assert not ledger.is_submit(decision("press", "0:other", "Enter", purpose="submit_search"), {})
    assert not ledger.is_submit(
        decision("press", "0:query", "Enter", purpose="submit_search"),
        {**field, "selection_required": True, "expanded": "true"},
    )


@pytest.mark.parametrize("label", ["Apply", "Confirm", "OK"])
def test_actual_native_submit_overrides_ambiguous_label_but_not_observed_widget_scope(label):
    task = TaskLedger("Search for soccer")
    task.declare_collection_goal(goal("search_results", "Search for soccer"))
    control = {
        "tag": "BUTTON",
        "type": "submit",
        "label": label,
        "submits_form": True,
        "form_scope": "retrieval",
    }
    assert task.is_submit(decision("click", "0:submit", purpose="other"), control)
    assert not task.is_submit(
        decision("click", "0:widget", purpose="submit_search"),
        {**control, "widget_scope": "counter"},
    )


class FormTools:
    def __init__(self, *, empty=False, capture_error=None):
        self.url, self.closed, self.searched = "https://example.org/", False, False
        self.pages, self.references, self.events = [], {}, []
        self.secrets, self.collection_context = (), None
        self.empty, self.capture_error = empty, capture_error

    def guard(self):
        pass

    def observe(self):
        fields = (
            []
            if self.searched
            else [
                {
                    "id": "0:query",
                    "tag": "INPUT",
                    "type": "search",
                    "label": "Query",
                    "name": "query",
                    "value": "soccer",
                    "form_scope": "retrieval",
                },
                {
                    "id": "0:search",
                    "tag": "BUTTON",
                    "type": "submit",
                    "label": "Search",
                    "submits_form": True,
                    "form_scope": "retrieval",
                },
            ]
        )
        if not self.closed and not self.searched:
            fields.append({"id": "0:done", "tag": "BUTTON", "type": "button", "label": "Done"})
        self.references = {item["id"]: (None, None, item) for item in fields}
        observation = {
            "url": self.url,
            "document_id": self.url,
            "frames": [
                {
                    "text": "No search results."
                    if self.empty and self.searched
                    else "Visible relevant source content. " * 5,
                    "controls": fields,
                }
            ],
        }
        if self.searched:
            observation["results"] = {
                "no_results": self.empty,
                "record_count": 0 if self.empty else 2,
                "busy": False,
            }
        return observation

    def execute(self, item):
        if item.action == "capture":
            return self.capture(item.value)
        self.events.append(item.control_id)
        if item.control_id == "0:done":
            self.closed = True
        elif item.control_id == "0:search":
            self.searched, self.url = True, "https://example.org/results"
        return {"status": "action_performed"}

    def capture(self, kind="page"):
        self.events.append("capture")
        if self.capture_error:
            raise self.capture_error
        self.pages.append(
            {"url": self.url, "text": "Complete rendered source. " * 10, "source_kind": kind}
        )
        return {"status": "captured", "url": self.url}


class Model:
    def __init__(self, *decisions):
        self.decisions, self.payloads = iter(decisions), []

    def decide(self, payload, timeout):
        self.payloads.append(copy.deepcopy(payload))
        return next(self.decisions)


def search_step():
    return decision(
        "click",
        "0:done",
        purpose="submit_search",
        collection_goal=goal("search_results", "Search for soccer"),
        requirements=[
            BrowserRequirement(
                name="query",
                expected="soccer",
                application="form",
                request_quote="soccer",
                control_id="0:query",
            )
        ],
    )


def test_mislabelled_done_closes_widget_then_real_search_runs_automatically():
    tools = FormTools()
    report = BrowserAgent(tools, Model(search_step()), "Search for soccer").run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert tools.events == ["0:done", "0:search", "capture"]
    assert report["actions"][0]["submission_semantics"] == {
        "is_actual_submit": False,
        "model_purpose_ignored": True,
    }
    proof = report["task_checklist"]["search_transition"]
    assert proof["confirmed"] is True
    assert report["task_checklist"]["search_response_pending"] is False


def test_verified_empty_search_stops_without_extracting_page_chrome():
    tools = FormTools(empty=True)
    report = BrowserAgent(tools, Model(search_step()), "Search for soccer").run()
    assert report["status"] == "ready"
    assert report["collection_outcome"] == "empty_results"
    assert report["task_checklist"]["search_submitted"] is True
    assert not report["task_checklist"]["search_response_pending"]
    assert "capture" not in tools.events and not tools.pages


@pytest.mark.parametrize("action", ["capture", "finish"])
def test_safe_capture_failure_pauses_once_without_more_model_calls(action):
    error = WebsiteError("Capture text was unavailable; review the page before resuming.")
    error.code = "capture_text_unavailable"
    error.capture_diagnostics = {"visible_text_chars": 0, "captured_text_chars": 0}
    tools = FormTools(capture_error=error)
    model = Model(decision(action, value="page"))
    report = BrowserAgent(tools, model, "Collect visible records").run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events.count("capture") == 1
    assert report["actions"][-1]["status"] == "capture_failed"
    assert report["actions"][-1]["capture_diagnostics"]["captured_text_chars"] == 0
    assert report["failure"]["code"] == "capture_text_unavailable"
    assert report["failure"]["capture_diagnostics"]["captured_text_chars"] == 0


@pytest.mark.parametrize(
    "prompt",
    [
        "Find articles related to soccer",
        "Get relevant sports headlines",
        "List wireless headphones and displayed prices",
        "Get visible hotel names and ratings",
        "Collect headline titles and their destination URLs",
    ],
)
def test_unspecified_record_requests_start_at_main_page_not_sections_or_search(prompt):
    scope = request_collection_scope(prompt)
    assert scope["allowed_modes"] == ["current_page"]
    ledger = TaskLedger(prompt)
    with pytest.raises(WebsiteError, match="quote alone"):
        ledger.declare_collection_goal(goal("search_results", prompt))
    assert ledger.scope_problem(
        decision("click", "0:section", purpose="navigate"),
        {"tag": "A", "href": "https://example.org/section"},
    )


def test_explicit_search_and_detail_requests_keep_dynamic_depth_without_genre_routing():
    assert request_collection_scope("Search this website for electric bikes")["allowed_modes"] == [
        "search_results"
    ]
    assert request_collection_scope("Find products; open their links for specifications")[
        "allowed_modes"
    ] == ["linked_details"]
    assert request_collection_scope("Collect records", ["record_context"])["allowed_modes"] == [
        "linked_details"
    ]
    assert request_collection_scope("Collect from this page only; do not open linked pages")[
        "allowed_modes"
    ] == ["current_page"]


def test_scope_contract_survives_navigation_context_compaction():
    task = TaskLedger("Find relevant sports headlines")
    result = build_navigation_context(
        {
            "task": task.instructions,
            "task_checklist": task.snapshot(),
            "observation": {"url": "https://example.org/", "frames": []},
            "budget": {},
        }
    )
    assert result["task_checklist"]["collection_scope"]["allowed_modes"] == ["current_page"]
    assert result["interaction_focus"]["phase"] == "collect_starting_page"


def test_current_page_scope_rejects_search_buttons_but_preserves_dismiss_and_expand():
    task = TaskLedger("Find relevant sports headlines")
    assert task.scope_problem(
        decision("click", "0:search"),
        {"tag": "BUTTON", "type": "submit", "label": "Search", "submits_form": True},
    )
    assert (
        task.scope_problem(
            decision("click", "0:expand"),
            {
                "tag": "BUTTON",
                "type": "button",
                "label": "Show more headlines",
                "expanded": "false",
            },
        )
        is None
    )
    assert (
        task.scope_problem(
            decision("click", "0:done", purpose="submit_search"),
            {"tag": "BUTTON", "type": "submit", "label": "Done"},
        )
        is None
    )
    assert task.scope_problem(decision("press", "0:modal", "Escape"), {}) is None


def test_submission_provenance_is_actual_agent_action_not_model_assertion_or_manual_click():
    task = TaskLedger("Search for soccer")
    before = {"url": "https://example.org/", "document_id": "before", "frames": [{"text": "Form"}]}
    after = {
        "url": "https://example.org/results",
        "document_id": "after",
        "frames": [{"text": "Results"}],
        "results": {"record_count": 2},
    }
    control = {"id": "0:search", "tag": "BUTTON", "label": "Search", "form_scope": "query"}
    assert task.submitted(
        before, after, before["url"], control=control, action="click", decision_origin="runtime"
    )
    assert task.submission["submission_provenance"] == {
        "actor": "agent",
        "action": "click",
        "decision_origin": "runtime",
        "control": control,
    }
    unrelated = TaskLedger("Search for soccer")
    unrelated.observe(after)
    assert unrelated.submission is None  # A manual page change is not an agent submission.
