"""Selected page-wide price mode is evidence; multiple unlabelled amounts are not."""

from types import SimpleNamespace

import pytest

from agentic_web_demo.pricing import assess_pricing
from test_capture_guest_readback import captured_guest_context


URL = "https://example.org/hotels"
PROMPT = "Find hotels in New York from 28-30 December 2026 with 4 adults and 3 rooms, 0 children"


def price_fixture():
    context, _ = captured_guest_context()
    page = {"url": URL, "browser_task_context": context, "blocks": [
        {"id": "b1", "kind": "heading", "text": "Drury Inn", "group_id": "g1", "association": "record"},
        {"id": "b2", "kind": "text", "text": "$106", "group_id": "g1", "association": "record"},
        {"id": "b3", "kind": "text", "text": "Prices in U.S. Dollar USD",
         "association": "page", "content_role": "currency_setting"},
        {"id": "b4", "kind": "text", "text": "Nightly price with fees",
         "association": "page", "content_role": "price_setting"},
    ]}
    row = {"hotel_name": "Drury Inn", "price": "106", "source_url": URL,
           "evidence": {"hotel_name": "Drury Inn", "price": "$106"}}
    columns = [SimpleNamespace(name="hotel_name", kind="text"), SimpleNamespace(name="price", kind="number")]
    return row, page, columns


def test_selected_nightly_mode_supplies_basis_without_inventing_card_wording():
    row, page, columns = price_fixture()
    rows = assess_pricing([row], [page], PROMPT, columns)["records"]
    pricing = rows[0]["pricing"]
    assert pricing["status"] == "verified" and pricing["combined_nightly"] == "106"
    assert pricing["kind"] == "all_rooms_per_night"
    assert pricing["fees_status"] == "included" and pricing["taxes"] == "unknown"
    assert pricing["basis_evidence"] == {"block_ids": ["b4"], "quotes": ["Nightly price with fees"]}
    assert pricing["evidence"]["quote"] == "$106"


@pytest.mark.parametrize("change", ["no_setting", "card_setting", "conflicting_modes", "two_prices", "unverified_stay"])
def test_page_setting_does_not_resolve_missing_or_ambiguous_evidence(change):
    row, page, columns = price_fixture()
    if change == "no_setting":
        page["blocks"].pop()
    elif change == "card_setting":
        page["blocks"][-1].update(association="record", group_id="g1", content_role="other")
    elif change == "conflicting_modes":
        page["blocks"].append({"id": "b5", "kind": "text", "text": "Total price",
                               "association": "page", "content_role": "price_setting"})
    elif change == "two_prices":
        page["blocks"].append({"id": "b5", "kind": "text", "text": "$120",
                               "association": "record", "group_id": "g1"})
    else:
        page["browser_task_context"]["result_scope"]["status"] = "unverified"
    rows = assess_pricing([row], [page], PROMPT, columns)["records"]
    assert rows[0]["pricing"]["status"] == "unverified"
    assert rows[0]["pricing"]["comparison_amount"] is None


def test_original_amount_is_preserved_and_does_not_compete_with_one_current_price():
    row, page, columns = price_fixture()
    page["blocks"].append({"id": "b5", "kind": "text", "text": "$140",
                           "association": "record", "group_id": "g1", "value_context": {
                               "quote": "$140", "label": "", "relation": "local_container", "struck_through": True}})
    rows = assess_pricing([row], [page], PROMPT, columns)["records"]
    pricing = rows[0]["pricing"]
    assert pricing["status"] == "verified" and pricing["displayed_amount"] == "106"
    assert any(item["amount"] == "140" and item["role"] == "original"
               for item in pricing["observations"])

