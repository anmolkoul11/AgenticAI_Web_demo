"""Offline current-page handoff regressions; no browser or paid API calls."""

import pytest

from agentic_web_demo.browser_agent import BrowserAgent, BrowserDecision
from agentic_web_demo.source_fields import article_priority_terms


REQUEST = "Find me articles related to sports"
PAGE_URL = "https://news.example.org/"


class ArticleTools:
    def __init__(self, interruption=None):
        self.pages, self.references, self.events = [], {}, []
        self.secrets = ()
        self.document = "starting-document"
        self.interruption = interruption

    def guard(self):
        pass

    def observe(self):
        self.events.append("observe")
        return {
            "url": PAGE_URL, "document_id": self.document,
            "results": {"record_count": 1,
                        "busy": bool(self.pages and self.interruption == "busy")},
            "frames": [{"controls": [], "text": "Visible sports headlines",
                        "password_or_code_visible": False}],
        }

    def capture(self, kind="page"):
        self.events.append("capture")
        if self.pages:
            return {"status": "already_captured", "url": PAGE_URL}
        blocks = [{"id": "b1", "kind": "heading", "text": "Team wins championship",
                   "href": PAGE_URL + "sport/team-wins", "association": "record",
                   "group_id": "g1"}]
        self.pages.append({
            "url": PAGE_URL, "text": "Team wins championship", "source_kind": kind,
            "blocks": [] if self.interruption == "missing_record_evidence" else blocks,
        })
        if self.interruption == "different_document":
            self.document = "replacement-document"
        return {"status": "captured", "url": PAGE_URL, "text_chars": 23}

    def execute(self, decision):
        assert decision.action == "capture", "No section navigation is needed"
        return self.capture(decision.value)


class ArticleDecider:
    usage = {}

    def __init__(self):
        self.calls = 0

    def decide(self, payload, timeout):
        self.calls += 1
        if self.calls == 1:
            return BrowserDecision(
                action="capture", value="page", explanation="Retain visible article records.",
                evidence="The starting page shows sports article headlines and links.",
                collection_goal={"mode": "current_page", "request_quote": REQUEST,
                                 "reason": "Extract relevant starting-page articles."},
            )
        return BrowserDecision(
            action="pause", explanation="Inspect the changed or incomplete page.",
            evidence="Another observation is needed before choosing the source.",
        )


def test_captured_current_page_records_finish_without_another_paid_decision():
    tools, decider = ArticleTools(), ArticleDecider()
    agent = BrowserAgent(tools, decider, REQUEST, collection_goal_required=True)

    report = agent.run()

    assert report["status"] == "ready"
    assert report["calls"] == decider.calls == 1
    assert [action["action"] for action in report["actions"]] == ["capture", "finish"]
    assert report["actions"][-1]["decision_origin"] == "runtime"
    assert report["actions"][-1]["status"] == "source_collection_ready"
    assert agent.captured_sources()[0]["blocks"][0]["href"] == PAGE_URL + "sport/team-wins"


@pytest.mark.parametrize("interruption", [
    "different_document", "missing_record_evidence", "busy",
])
def test_handoff_requires_same_document_grounded_records_and_settled_page(interruption):
    tools, decider = ArticleTools(interruption), ArticleDecider()
    agent = BrowserAgent(tools, decider, REQUEST, collection_goal_required=True)

    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == decider.calls == 2
    assert not any(action["action"] == "finish" for action in report["actions"])


def test_hotel_workflows_do_not_get_article_capture_options_or_shortcuts():
    tools = ArticleTools()
    BrowserAgent(tools, ArticleDecider(),
                 "Find hotels in Edison from November 28-30, 2026 for 6 adults and 4 rooms",
                 collection_goal_required=True)
    assert not getattr(tools, "article_records", False)
    assert not getattr(tools, "record_priority_terms", [])
    assert not getattr(tools, "capture_options", {})


def test_priority_terms_are_bounded_request_cues_not_an_acceptance_filter():
    assert article_priority_terms("Find me articles related to sports") == ["sports"]
    assert article_priority_terms("Get world politics articles from this page") == ["world", "politics"]
    assert article_priority_terms("Find hotels in Edison for 6 adults and 4 rooms") == []
    tools = ArticleTools()
    BrowserAgent(tools, ArticleDecider(), REQUEST, collection_goal_required=True)
    assert tools.capture_options == {"article_records": True, "record_priority_terms": ["sports"]}

