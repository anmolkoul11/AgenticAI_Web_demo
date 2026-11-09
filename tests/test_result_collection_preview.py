"""Confirmed Search sources remain capturable without becoming stay matches."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.result_collection import ResultCollector, record_groups
from agentic_web_demo.stay_scope import observed_result_scope, requested_stay
from test_all_result_collection import ResultTools, URL


REQUEST = "Find hotels in Edison from November 28-30 2026 for 6 adults, 4 rooms and 0 children."


class PreviewTools(ResultTools):
    def __init__(self, *, next_page=False):
        super().__init__([list(range(16))] + ([list(range(16, 26))] if next_page else []))
        observed = self.observe()
        self.collection_context = {
            "status": "form_verified_search_submitted", "source_preview_only": True,
            "requested_stay_verified": False, "availability_verified": False,
            "scope": "form_values_and_submission_only", "result_state": "observed",
            "before_document_id": "search-form", "source_url": "https://example.org/",
            "result_document_id": observed["document_id"], "result_url": URL,
            "result_scope": observed_result_scope(requested_stay(REQUEST), observed),
        }

    def capture_records(self, offset):
        page = super().capture_records(offset)
        page["browser_task_context"] = deepcopy(self.collection_context)
        return page


def collector(tools):
    return ResultCollector(tools, SimpleNamespace(instructions=REQUEST, record_limit=5000), [], lambda _: None)


def test_confirmed_search_collects_all_initial_page_records_as_unverified_sources():
    result = collector(PreviewTools())
    pages = result.run()
    assert result.complete and len(result.seen) == 16
    assert sum(len(record_groups(page)) for page in pages) == 16
    assert result.summary()["source_preview_only"]
    assert result.summary()["scope_status"] == "unverified"
    assert "rooms" in result.summary()["unverified_fields"]
    assert all(page["browser_task_context"]["source_preview_only"] for page in pages)
    assert not any(page["browser_task_context"]["requested_stay_verified"] for page in pages)


def test_unverified_sources_do_not_navigate_to_another_result_page():
    tools = PreviewTools(next_page=True)
    result = collector(tools)
    pages = result.run()
    assert len(result.seen) == 16 and not result.complete
    assert result.reason == "unverified_stay_pagination"
    assert pages and not any(event[0] == "click" for event in tools.events)


@pytest.mark.parametrize("change", ["document", "url", "unsubmitted", "busy"])
def test_preview_exception_needs_its_original_confirmed_search_document(change):
    tools = PreviewTools()
    if change == "unsubmitted":
        tools.collection_context["status"] = "observed_matching_results"
    result = collector(tools)
    observed = tools.observe()
    if change == "document":
        observed["document_id"] = "different-result"
    elif change == "url":
        observed["url"] += "?city=another"
    elif change == "busy":
        observed["results"]["busy"] = True
    scope = observed_result_scope(requested_stay(REQUEST), observed)
    assert not result.preview_allowed(observed, scope)
    if change != "busy":
        with pytest.raises(WebsiteError):
            result.verify_scope(observed)


def test_capture_retains_conflict_evidence_without_promoting_it_to_a_match():
    tools = PreviewTools()
    scope = tools.collection_context["result_scope"]
    scope.update(status="mismatch", contradictions=[{
        "code": "price_context_occupancy_mismatch", "evidence": "Only 2 rooms available",
    }])
    result = collector(tools)
    pages = result.run()
    assert len(result.seen) == 16
    assert all(page["browser_task_context"]["result_scope"]["status"] == "mismatch" for page in pages)
    assert result.summary()["contradiction_codes"] == ["price_context_occupancy_mismatch"]


def test_preview_can_lose_captured_destination_evidence_in_the_control_inventory():
    tools = PreviewTools()
    anchored = tools.collection_context["result_scope"]
    anchored["observed"]["destination"] = "Edison"
    destination = next(item for item in anchored["fields"] if item["field"] == "destination")
    destination.update(status="verified", observed="Edison", method="captured_results_heading")
    result = collector(tools)
    pages = result.run()
    assert len(result.seen) == 16 and pages
    assert result.summary()["source_preview_only"]
    assert not any(page["browser_task_context"]["requested_stay_verified"] for page in pages)


def test_reordered_or_newly_visible_room_mismatches_stay_capturable_only_as_sources():
    tools = PreviewTools()
    anchor = tools.collection_context["result_scope"]
    anchor["observed"]["rooms"] = "3; 4"
    room = next(item for item in anchor["fields"] if item["field"] == "rooms")
    room.update(status="mismatch", observed="3; 4")
    anchor["status"] = "mismatch"
    result = collector(tools)
    fresh = deepcopy(anchor)
    fresh["observed"]["rooms"] = "4; 3"
    next(item for item in fresh["fields"] if item["field"] == "rooms")["observed"] = "4; 3"
    assert result.preview_allowed(tools.observe(), fresh)
    fresh["requested"]["rooms"] = "5"
    assert not result.preview_allowed(tools.observe(), fresh)

    # A mismatch discovered after the first source snapshot is also review
    # evidence; it cannot turn capture permission into verified eligibility.
    tools = PreviewTools()
    result = collector(tools)
    observed = tools.observe()
    observed["frames"][0]["controls"] = [{"id": "0:rooms", "tag": "BUTTON",
                                            "label": "3 rooms", "enabled": True}]
    mismatch = observed_result_scope(requested_stay(REQUEST), observed)
    assert mismatch["status"] == "mismatch"
    assert result.preview_allowed(observed, mismatch)
    result.verify_scope(observed)
    assert tools.collection_context["source_preview_only"]
    assert not tools.collection_context["requested_stay_verified"]
    assert tools.collection_context["result_scope"]["status"] == "mismatch"


def test_preview_capture_cannot_lose_its_document_context_silently():
    tools = PreviewTools()
    tools.capture_records = lambda offset: ResultTools.capture_records(tools, offset)
    with pytest.raises(WebsiteError, match="lost its document-bound"):
        collector(tools).run()


def test_later_source_with_independently_verified_scope_replaces_its_preview_coherently():
    tools = PreviewTools()
    result = collector(tools)
    result.retain(tools.capture_records(0))
    later = tools.capture_records(0)
    later["browser_task_context"].update(source_preview_only=False, requested_stay_verified=True)
    later["browser_task_context"]["result_scope"]["status"] = "verified"
    result.retain(later)
    assert len(result.pages) == 1 and len(result.seen) == 10
    assert not result.summary()["source_preview_only"]
    assert result.pages[0]["browser_task_context"]["requested_stay_verified"]

