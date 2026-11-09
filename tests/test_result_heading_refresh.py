"""Fresh captured result headings can bridge a narrower control inventory."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.capture import clean_url
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.result_collection import ResultCollector
from agentic_web_demo.stay_scope import observed_result_scope, reconcile_captured_result_scope, requested_stay
from test_all_result_collection import ResultTools


REQUEST = "Find hotels in New York from December 28-30 2026 for 4 adults and 2 rooms."
RESULT_URL = "https://example.org/results?checkin=2026-12-28&checkout=2026-12-30&group_adults=4&no_rooms=2"


class HeadingTools(ResultTools):
    def __init__(self):
        super().__init__([list(range(16))])
        self.heading = "New York: 16 properties found"
        observed = self.observe()
        scope = reconcile_captured_result_scope(
            observed_result_scope(requested_stay(REQUEST), observed), self.heading_blocks(),
            document_id=observed["document_id"],
        )
        self.collection_context = {
            "status": "form_verified_search_submitted", "scope": "form_values_and_submission_only",
            "result_state": "observed", "result_document_id": observed["document_id"],
            "result_url": RESULT_URL, "requested_stay_verified": True, "source_preview_only": False,
            "result_scope": scope,
        }

    def observe(self):
        page = super().observe()
        page["url"] = RESULT_URL
        return page  # All non-destination values remain literal URL evidence.

    def heading_blocks(self):
        return [{"id": "b1", "kind": "heading", "heading_level": 1,
                 "text": self.heading, "association": "page", "group_id": None}] if self.heading else []

    def capture_records(self, offset):
        page = super().capture_records(offset)
        page["url"] = clean_url(RESULT_URL)
        page["blocks"] = self.heading_blocks() + page["blocks"][1:]
        scope = reconcile_captured_result_scope(
            observed_result_scope(requested_stay(REQUEST), self.observe()), page["blocks"],
            document_id=self.observe()["document_id"],
        )
        context = {**deepcopy(self.collection_context), "result_scope": scope,
                   "requested_stay_verified": scope["status"] == "verified",
                   "source_preview_only": scope["status"] != "verified"}
        page["browser_task_context"] = context
        self.collection_context = deepcopy(context)
        return page


def collector(tools):
    return ResultCollector(tools, SimpleNamespace(instructions=REQUEST, record_limit=5000), [], lambda _: None)


def test_destination_heading_is_re_read_and_first_window_is_reused_for_collection():
    tools = HeadingTools()
    assert observed_result_scope(requested_stay(REQUEST), tools.observe())["status"] == "unverified"
    result = collector(tools)
    pages = result.run()
    assert result.complete and len(result.seen) == 16
    captures = [event[2] for event in tools.events if event[0] == "capture"]
    assert captures[:2] == [0, 10]  # No duplicate first-window capture in one pass.
    assert all(page["browser_task_context"]["requested_stay_verified"] for page in pages)


@pytest.mark.parametrize("heading", [None, "Boston: 16 properties found"])
def test_previous_heading_quote_cannot_verify_a_missing_or_changed_current_heading(heading):
    tools = HeadingTools()
    tools.heading = heading
    result = collector(tools)
    with pytest.raises(WebsiteError, match="current captured result heading"):
        result.run()
    assert not result.pages and not result.seen


@pytest.mark.parametrize("change", ["document", "url", "proof_method"])
def test_heading_refresh_requires_its_current_verified_capture_context(change):
    tools = HeadingTools()
    observed = tools.observe()
    if change == "document":
        observed["document_id"] = "different-document"
    elif change == "url":
        observed["url"] += "&page=2"
    else:
        destination = next(item for item in tools.collection_context["result_scope"]["fields"]
                           if item["field"] == "destination")
        destination["method"] = "verified_pre_submit_form"
    with pytest.raises(WebsiteError):
        collector(tools).verify_scope(observed)
    assert not any(event[0] == "capture" for event in tools.events)
