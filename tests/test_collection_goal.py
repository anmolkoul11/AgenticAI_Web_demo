"""Request-grounded collection depth and pause regressions; no browser/API calls."""

import copy
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserCollectionGoal,
    BrowserDecision,
    BrowserRequirement,
    DOMBrowserTools,
)
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_fetch import WebsiteError


def goal(mode, quote):
    return BrowserCollectionGoal(mode=mode, request_quote=quote, reason="Requested data depth.")


def decide(action, control_id=None, value="", **changes):
    return BrowserDecision(
        action=action,
        control_id=control_id,
        value=value,
        explanation="Collect the requested information.",
        evidence="Visible requested source content.",
        **changes,
    )


class Sources:
    def __init__(self, *, search=False):
        self.url = "https://example.org/index"
        self.pages, self.references, self.events = [], {}, []
        self.secrets, self.collection_context = (), None
        self.search, self.value, self.submitted, self.paused = search, "", False, False
        self.user_pause = lambda: self.paused

    def guard(self):
        if self.paused:
            raise WebsiteError("You paused the browser agent.")

    def observe(self):
        self.events.append("observe")
        fields = []
        if self.search and not self.submitted:
            fields = [
                {
                    "id": "0:query",
                    "tag": "INPUT",
                    "type": "text",
                    "name": "query",
                    "label": "Query",
                    "value": self.value,
                    "form_scope": "catalog",
                },
                {
                    "id": "0:search",
                    "tag": "BUTTON",
                    "type": "submit",
                    "label": "Search",
                    "submits_form": True,
                    "form_scope": "catalog",
                },
            ]
        elif self.url.endswith("index"):
            fields = [
                {
                    "id": "0:link",
                    "tag": "A",
                    "label": "Relevant source",
                    "href": "https://example.org/detail",
                }
            ]
        self.references = {item["id"]: (None, None, item) for item in fields}
        observation = {
            "url": self.url,
            "document_id": self.url,
            "frames": [{"text": "Requested source data at " + self.url, "controls": fields}],
        }
        if self.submitted:
            observation["results"] = {"record_count": 2, "busy": False}
        return observation

    def execute(self, decision):
        self.events.append(decision.action)
        if decision.action == "capture":
            return self.capture(decision.value)
        if decision.action == "fill":
            self.value = decision.value
            return {"status": "value_verified", "expected": self.value, "observed": self.value}
        if decision.control_id == "0:search":
            self.url, self.submitted = "https://example.org/results", True
        elif decision.action == "click":
            self.url = "https://example.org/detail"
        return {"status": "action_performed"}

    def capture(self, kind="page"):
        self.events.append("capture")
        blocks = [
            {"id": "b1", "kind": "heading", "text": "Relevant source",
             "href": "https://example.org/detail", "association": "record", "group_id": "g1"},
        ]
        if self.url.endswith("detail"):
            blocks += [
                {"id": "b2", "kind": "paragraph", "text": "Full source content. " * 20,
                 "content_role": "body", "association": "record", "group_id": "g1"},
                {"id": "b3", "kind": "text", "text": "Specifications: visible product details. Facilities: visible accommodation details.",
                 "association": "record", "group_id": "g1"},
            ]
        page = {"url": self.url, "text": "Full source content. " * 600,
                "source_kind": kind, "blocks": blocks}
        if self.collection_context:
            page["browser_task_context"] = copy.deepcopy(self.collection_context)
        if not any(item["url"] == self.url for item in self.pages):
            self.pages.append(page)
        return {"status": "captured", "url": self.url}


class Decisions:
    def __init__(self, *items, callback=lambda: None):
        self.items, self.payloads, self.callback = iter(items), [], callback

    def decide(self, payload, timeout):
        self.payloads.append(payload)
        self.callback()
        return next(self.items)


@pytest.mark.parametrize(
    "prompt",
    [
        "Extract the product names and displayed prices already visible here",
        "Get the headlines visible on this page",
        "Get hotel names and displayed ratings from this current page",
    ],
)
def test_current_page_goal_is_generic_and_needs_no_separate_planning_call(prompt):
    tools = Sources()
    model = Decisions(decide("finish", collection_goal=goal("current_page", prompt)))
    report = BrowserAgent(tools, model, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["task_checklist"]["collection_goal"]["mode"] == "current_page"
    assert report["task_checklist"]["collection_progress"]["captured_pages"] == 1
    assert len(tools.pages[0]["text"]) > 8000  # Navigation projection never edits captures.


@pytest.mark.parametrize(
    "prompt",
    [
        "Find sports stories and open relevant links for their full context",
        "Follow product links and collect their specifications",
        "Open the linked accommodation pages to collect their facilities",
    ],
)
def test_linked_details_visit_actual_sources_with_the_same_agent(prompt):
    tools = Sources()
    model = Decisions(
        decide("capture", value="index", collection_goal=goal("linked_details", prompt)),
        decide("click", control_id="0:link", purpose="navigate"),
        decide("finish", value="detail"),
    )
    report = BrowserAgent(tools, model, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 3
    assert [(page["url"], page["source_kind"]) for page in tools.pages] == [
        ("https://example.org/index", "index"),
        ("https://example.org/detail", "detail"),
    ]
    assert report["task_checklist"]["collection_progress"]["detail_pages"] == 1


def test_generic_product_search_uses_one_decision_then_verified_runtime_handoff():
    prompt = "Search this website for wireless headphones and include their prices and product URLs"
    tools = Sources(search=True)
    model = Decisions(
        decide(
            "fill",
            control_id="0:query",
            value="wireless headphones",
            purpose="set_field",
            collection_goal=goal("search_results", "Search this website for wireless headphones"),
            requirements=[
                BrowserRequirement(
                    name="query",
                    expected="wireless headphones",
                    application="form",
                    request_quote="wireless headphones",
                    control_id="0:query",
                )
            ],
        )
    )
    report = BrowserAgent(tools, model, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["task_checklist"]["search_submitted"] is True
    assert tools.pages[0]["url"] == "https://example.org/results"


def test_linked_goal_cannot_finish_with_only_index_headlines():
    prompt = "Open relevant links to get their context"
    tools = Sources()
    model = Decisions(
        decide("capture", value="index", collection_goal=goal("linked_details", prompt)),
        decide("finish", value="page"),
        decide("finish", value="page"),
    )
    report = BrowserAgent(tools, model, prompt).run()
    assert report["status"] == "paused"
    assert "no distinct detail page" in report["guidance"]
    assert len(tools.pages) == 1


def test_search_results_goal_cannot_finish_without_a_confirmed_search_transition():
    prompt = "Search for wireless headphones"
    tools = Sources()
    model = Decisions(
        decide("finish", collection_goal=goal("search_results", prompt)),
        decide("finish"),
    )
    report = BrowserAgent(tools, model, prompt, collection_goal_required=True).run()
    assert report["status"] == "paused"
    assert "confirmed Search transition" in report["guidance"]
    assert not report["task_checklist"]["search_submitted"]
    assert not tools.pages


def test_automatic_finish_requests_missing_goal_then_continues_without_human_input():
    prompt = "Collect the visible product names"
    tools = Sources()
    model = Decisions(
        decide("finish"),
        decide("finish", collection_goal=goal("current_page", prompt)),
    )
    report = BrowserAgent(tools, model, prompt, collection_goal_required=True).run()
    assert report["status"] == "ready" and report["calls"] == 2
    assert report["actions"][0]["status"] == "completion_rejected"
    assert "Declare collection_goal" in report["actions"][0]["guidance"]
    assert len(tools.pages) == 1


def test_goals_require_request_evidence_and_cannot_downgrade_linked_depth():
    ledger = TaskLedger("Follow relevant links for full context")
    with pytest.raises(WebsiteError, match="quote"):
        ledger.declare_collection_goal(goal("linked_details", "Invented request"))
    ledger.declare_collection_goal(goal("linked_details", "Follow relevant links"))
    with pytest.raises(WebsiteError, match="cannot be replaced"):
        ledger.declare_collection_goal(goal("current_page", "full context"))


def test_requested_output_fields_are_available_without_changing_request_grounding():
    tools = Sources()
    model = Decisions(decide("pause", pause_reason="user_input"))
    BrowserAgent(tools, model, "Collect sports content", output_fields=["title", "context"]).run()
    assert model.payloads[0]["task"] == "Collect sports content"
    assert model.payloads[0]["requested_output_fields"] == ["title", "context"]


def test_captured_search_context_survives_detail_navigation_without_availability_claim():
    ledger = TaskLedger(
        "Find hotels in Boston with check-in 2026-10-28 and check-out 2026-10-30; "
        "open their links for full context"
    )
    ledger.declare_collection_goal(goal("linked_details", "Find hotels in Boston"))
    proof = {
        "status": "form_verified_search_submitted",
        "result_document_id": "results",
        "result_url": "https://example.org/results",
        "availability_verified": False,
        "result_scope": {
            "status": "verified", "source": "returned_page", "availability_verified": False,
            "fields": [
                {"field": name, "expected": item["expected"], "observed": item["expected"],
                 "status": "verified", "method": "returned_control", "evidence": item["expected"]}
                for name, item in ledger.requirements.items()
            ],
            "contradictions": [],
        },
        "requirements": [
            {
                "field": name,
                "expected": item["expected"],
                "application": "form",
                "status": "verified",
                "observed": item["expected"],
            }
            for name, item in ledger.requirements.items()
        ],
    }
    ledger.note_sources(
        [{"url": proof["result_url"], "source_kind": "index", "browser_task_context": proof}]
    )
    ledger.observe(
        {
            "url": "https://example.org/detail",
            "document_id": "detail",
            "frames": [{"text": "Hotel information", "controls": []}],
        }
    )
    assert not ledger.pending()
    assert ledger.completion_problem() is None
    assert ledger.snapshot()["search_submitted"] is True
    assert (
        ledger.capture_context({"url": "https://example.org/detail", "document_id": "detail"})
        is None
    )
    assert all(check["method"] == "retained_search_context" for check in ledger.checks)
    assert ledger.collection_search["availability_verified"] is False


def test_pause_during_model_call_prevents_returned_action_and_source_capture():
    tools = Sources()
    model = Decisions(
        decide("click", control_id="0:link"), callback=lambda: setattr(tools, "paused", True)
    )
    report = BrowserAgent(tools, model, "Read the relevant source").run()
    assert report["status"] == "paused"
    assert "You paused" in report["guidance"]
    assert report["calls"] == 1
    assert "click" not in tools.events and not tools.pages


def test_dom_pause_guard_does_not_access_or_act_on_the_page():
    page = SimpleNamespace(url="https://example.org/", is_closed=lambda: False)
    tools = DOMBrowserTools(
        page,
        "https://example.org",
        lambda: {},
        lambda: True,
        lambda: False,
        user_pause=lambda: True,
    )
    with pytest.raises(WebsiteError, match="You paused"):
        tools.guard()


def test_existing_source_can_be_reclassified_as_detail_without_recapture():
    page = SimpleNamespace(url="https://example.org/detail", is_closed=lambda: False)
    tools = DOMBrowserTools(
        page,
        "https://example.org",
        lambda: pytest.fail("No recapture"),
        lambda: True,
        lambda: False,
    )
    tools.pages = [
        {"url": "https://example.org/index", "text": "Index", "source_kind": "index"},
        {"url": page.url, "text": "Full detail", "source_kind": "page"},
    ]
    assert tools.capture("detail")["status"] == "already_captured"
    assert tools.pages[1]["source_kind"] == "detail"
    assert tools.pages[1]["parent_url"] == "https://example.org/index"
