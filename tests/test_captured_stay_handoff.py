"""Capture handoff fixtures; fake pages/tools only, no execution during authoring."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_browser_agent import FakeDecider, FakeTools
from test_captured_stay_pricing import PROMPT
from test_captured_stay_scope import heading, returned_scope

from agentic_web_demo.browser_agent import BrowserAgent, DOMBrowserTools
from playwright.sync_api import Error as PlaywrightError
from agentic_web_demo.stay_scope import reconcile_captured_result_scope


URL = "https://example.org/searchresults.html"
RAW_URL = URL + "?checkin=2026-10-28&checkout=2026-10-30&group_adults=4&no_rooms=2"
DOCUMENT = hashlib.sha256(RAW_URL.encode()).hexdigest()


def context():
    scope = returned_scope()
    scope["document_id"] = DOCUMENT
    return {"status": "form_verified_search_submitted", "result_document_id": DOCUMENT,
            "result_url": URL, "result_scope": scope, "source_preview_only": True}


def fresh_observation(rooms=2):
    return {"url": URL, "document_id": DOCUMENT, "stay_url_values": {
        "check_in": ["2026-10-28"], "check_out": ["2026-10-30"],
        "adults": [4], "rooms": [2],
    }, "frames": [{"controls": [{"tag": "BUTTON", "label": f"4 adults · {rooms} rooms"}]}],
        "results": {"record_count": 20, "busy": False}}


def test_dom_capture_uses_prepared_same_document_heading_and_keeps_old_context_immutable():
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)
    snapshot = {"url": URL, "text": "New York: 372 properties found", "blocks": [heading()]}
    tools = DOMBrowserTools(page, "https://example.org", lambda: deepcopy(snapshot),
                            lambda: True, lambda: False)
    tools.observe = fresh_observation
    original = context()
    tools.collection_context = deepcopy(original)
    outcome = tools.capture()
    retained = tools.pages[0]["browser_task_context"]
    assert outcome["status"] == "captured"
    assert retained["result_scope"]["status"] == "verified"
    assert retained["result_scope"]["observed"]["destination"] == "New York"
    assert retained["requested_stay_verified"] and not retained["source_preview_only"]
    assert tools.collection_context == retained
    assert original["result_scope"]["observed"]["destination"] is None


def test_same_url_occupancy_change_during_preparation_cannot_reuse_old_room_proof():
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)
    tools = DOMBrowserTools(page, "https://example.org", lambda: {
        "url": URL, "text": "New York: 372 properties found", "blocks": [heading()],
    }, lambda: True, lambda: False)
    tools.collection_context = context()
    tools.observe = lambda: fresh_observation(rooms=1)
    tools.capture()
    retained = tools.pages[0]["browser_task_context"]
    assert retained["result_scope"]["status"] == "mismatch"
    assert retained["source_preview_only"] and not retained["requested_stay_verified"]
    rooms = next(item for item in retained["result_scope"]["fields"] if item["field"] == "rooms")
    assert rooms["status"] == "mismatch"


def test_unavailable_final_observation_keeps_content_readonly_without_promoting_scope():
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)
    tools = DOMBrowserTools(page, "https://example.org", lambda: {
        "url": URL, "text": "New York: 372 properties found", "blocks": [heading()],
    }, lambda: True, lambda: False)
    tools.collection_context = context()

    def unavailable():
        raise PlaywrightError("DOM unavailable")

    tools.observe = unavailable
    tools.capture()
    retained = tools.pages[0]["browser_task_context"]
    assert retained["result_scope"]["status"] == "unverified"
    assert retained["result_scope"]["capture_refresh"] == "unavailable"
    assert retained["source_preview_only"]


def test_old_catalog_contradiction_stays_blocking_without_a_captured_heading():
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)
    tools = DOMBrowserTools(page, "https://example.org", lambda: {
        "url": URL, "text": "Returned hotel records without a captured heading", "blocks": [],
    }, lambda: True, lambda: False)
    tools.collection_context = context()
    tools.collection_context["result_scope"]["contradictions"] = [
        {"code": "catalog_starting_price", "evidence": "Starting from $200"}
    ]

    def fresh():
        observation = fresh_observation()
        observation["frames"][0]["controls"].append({
            "tag": "INPUT", "type": "text", "label": "Destination", "value": "New York",
        })
        return observation

    tools.observe = fresh
    tools.capture()
    scope = tools.pages[0]["browser_task_context"]["result_scope"]
    assert scope["observed"]["destination"] == "New York"
    assert scope["status"] == "unverified"
    assert scope["contradictions"][0]["code"] == "catalog_starting_price"


@pytest.mark.parametrize("change", ["live_document", "captured_url"])
def test_capture_cannot_attach_or_reconcile_context_from_a_different_document(change):
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)

    def capture():
        if change == "live_document":
            page.url = URL + "?checkin=2026-11-01"
        return {"url": URL if change == "live_document" else "https://example.org/other",
                "text": "New York: 372 properties found", "blocks": [heading()]}

    tools = DOMBrowserTools(page, "https://example.org", capture, lambda: True, lambda: False)
    tools.collection_context = context()
    tools.capture()
    assert "browser_task_context" not in tools.pages[0]
    assert tools.collection_context["result_scope"]["status"] == "unverified"


def test_non_stay_search_capture_is_not_mislabeled_as_a_stay_preview():
    page = SimpleNamespace(url=RAW_URL, is_closed=lambda: False)
    tools = DOMBrowserTools(page, "https://example.org", lambda: {
        "url": URL, "text": "Search records", "blocks": [],
    }, lambda: True, lambda: False)
    tools.collection_context = {"result_document_id": DOCUMENT, "result_scope": {
        "source": "returned_page", "document_id": DOCUMENT, "status": "not_requested",
        "requested": {}, "observed": {}, "fields": [], "contradictions": [],
    }}
    tools.capture()
    assert not tools.pages[0]["browser_task_context"]["source_preview_only"]


class PreparedCaptureTools(FakeTools):
    def observe(self):
        self.events.append("observe")
        return {"url": URL, "document_id": DOCUMENT, "stay_url_values": {
            "check_in": ["2026-10-28"], "check_out": ["2026-10-30"],
            "adults": [4], "rooms": [2],
        }, "frames": [{"controls": [], "text": "Available hotel search records for this stay."}],
            "results": {"record_count": 20, "busy": False, "no_results": False}}

    def capture(self, kind="page"):
        self.events.append("capture")
        self.collection_context["result_scope"] = reconcile_captured_result_scope(
            self.collection_context["result_scope"], [heading()], document_id=DOCUMENT,
        )
        self.pages = [{"url": URL, "source_kind": kind, "text": "New York: 372 properties found",
                       "blocks": [heading()], "browser_task_context": deepcopy(self.collection_context)}]


def test_finish_report_adopts_captured_scope_without_an_extra_model_decision():
    tools = PreparedCaptureTools()
    model = FakeDecider([])
    agent = BrowserAgent(tools, model, PROMPT.split(", around", 1)[0] + ".")
    agent.task.submission = {"result_document_id": DOCUMENT, "result_url": URL,
                             "result_state": "observed", "requirements": [],
                             "dispatch_status": "action_completed"}
    report = agent.run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events.count("capture") == 1
    assert report.get("collection_outcome") != "stay_scope_unverified"
    assert report["task_checklist"]["result_scope"]["status"] == "verified"
    assert report["actions"][-1]["status"] == "source_collection_ready"
