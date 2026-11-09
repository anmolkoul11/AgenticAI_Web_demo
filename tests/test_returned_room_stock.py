"""Property inventory is source context, not the applied stay room count."""

import pytest

from agentic_web_demo.stay_scope import observed_result_scope, requested_stay


REQUEST = "Find hotels in New Jersey from 28-30 November 2026 for 5 adults and 3 rooms."


def returned_page(stock):
    return {
        "url": "https://www.booking.com/searchresults.html?checkin=2026-11-28&checkout=2026-11-30&group_adults=5&no_rooms=3",
        "document_id": "returned-document",
        "results": {"record_count": 16, "headings": [{"level": 1, "text": "New Jersey: 16 properties found"}],
                    "price_contexts": [stock]},
        "frames": [{"controls": [
            {"id": "0:guests", "tag": "BUTTON", "type": "button", "label": "5 adults, 3 rooms", "value": ""},
            {"id": "0:stock", "tag": "BUTTON", "type": "button", "label": stock, "value": ""},
        ]}],
    }


@pytest.mark.parametrize("stock", ["Only 1 room left", "2 rooms remaining", "1 room available", "Some options have fewer than 3 rooms"])
def test_remaining_inventory_does_not_conflict_with_actual_room_selection(stock):
    scope = observed_result_scope(requested_stay(REQUEST), returned_page(stock))
    rooms = next(field for field in scope["fields"] if field["field"] == "rooms")
    assert rooms["status"] == "verified" and rooms["observed"] == "3"
    assert not any(issue["code"] == "price_context_occupancy_mismatch" for issue in scope["contradictions"])


def test_real_returned_room_conflict_is_still_a_mismatch():
    page = returned_page("Only 1 room left")
    page["url"] = page["url"].replace("no_rooms=3", "no_rooms=2")
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert next(field for field in scope["fields"] if field["field"] == "rooms")["status"] == "mismatch"


def test_separate_actual_guest_counter_still_contributes_returned_evidence():
    page = returned_page("Only 1 room left")
    page["frames"][0]["controls"].append({
        "id": "0:rooms", "tag": "BUTTON", "label": "increase Rooms", "type": "button",
        "counter": {"label": "Rooms", "value": 2, "direction": "increase", "evidence": "Rooms 2"},
    })
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert next(field for field in scope["fields"] if field["field"] == "rooms")["status"] == "mismatch"
