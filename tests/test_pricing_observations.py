"""Multi-price source evidence regressions; authored without running browser/API/tests."""

from copy import deepcopy
from types import SimpleNamespace

from agentic_web_demo.pricing import assess_pricing, pricing_comparison_record


URL = "https://example.org/search"
PROMPT = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms, around 250-350 USD nightly."
)
STAY = {
    "destination": "New York", "check_in": "2026-10-28", "check_out": "2026-10-30",
    "adults": 4, "rooms": 2,
}


def price_block(identifier, text, quote, label="", original=False):
    return {
        "id": identifier, "kind": "text", "text": text,
        "group_id": "g1", "association": "record",
        "value_context": {
            "quote": quote, "label": label, "relation": "local_container",
            "struck_through": original,
        },
    }


def fixture():
    row = {
        "listing_id": "record-1", "hotel_name": "Example Hotel", "price": "559",
        "source_url": URL, "evidence": {"hotel_name": "Example Hotel", "price": "$559"},
    }
    page = {
        "url": URL,
        "blocks": [
            {"id": "title", "kind": "heading", "text": "Example Hotel", "group_id": "g1", "association": "record"},
            price_block("nightly", "$259", "Per night $259", "Per night"),
            price_block("original", "$665", "$665", original=True),
            price_block("total", "$559", "$559 2 nights, 4 adults", "2 nights, 4 adults"),
            {"id": "currency", "kind": "text", "text": "Prices in U.S. Dollar USD", "association": "page", "content_role": "currency_setting"},
        ],
        "browser_task_context": {"result_scope": {
            "source": "returned_page", "status": "verified", "observed": deepcopy(STAY),
        }},
    }
    columns = [SimpleNamespace(name="hotel_name", kind="text"), SimpleNamespace(name="price", kind="number")]
    return row, page, columns


def test_bound_nightly_total_and_crossed_out_prices_are_preserved_without_reconciling():
    original, page, columns = fixture()
    row = assess_pricing([original], [page], PROMPT, columns)["records"][0]
    pricing = row["pricing"]
    assert row["price"] == "559"
    assert original["price"] == "559"
    assert pricing["status"] == "verified"
    assert pricing["displayed_amount"] == "259"
    assert pricing["comparison_amount"] == "259"
    assert pricing["calculation"] is None
    assert pricing["budget_status"] == "within_target"
    assert pricing["taxes"] == "unknown"
    assert pricing["fees_status"] == "unknown"
    observations = {item["amount"]: item for item in pricing["observations"]}
    assert observations["259"]["kind"] == "all_rooms_per_night"
    assert observations["259"]["selected"] is True
    assert observations["259"]["quote"] == "Per night $259"
    assert observations["559"]["kind"] == "stay_total_all_rooms"
    assert observations["559"]["selected"] is False
    assert observations["665"]["role"] == "original"
    assert observations["665"]["selected"] is False
    assert pricing_comparison_record(row)["price"] == "259"


def test_multiple_model_price_aliases_do_not_block_independently_bound_nightly_quote():
    original, page, columns = fixture()
    original.update({"nightly_price": "259", "stay_total_price": "559", "original_price": "665"})
    original["evidence"].update({"nightly_price": "Per night $259", "stay_total_price": "$559", "original_price": "$665"})
    columns.extend(SimpleNamespace(name=name, kind="number") for name in (
        "nightly_price", "stay_total_price", "original_price",
    ))
    row = assess_pricing([original], [page], PROMPT, columns)["records"][0]
    assert row["pricing"]["status"] == "verified"
    comparison = pricing_comparison_record(row)
    assert comparison["price"] == "259"
    assert comparison["nightly_price"] == "259"
    assert comparison["stay_total_price"] == "559"
    assert comparison["original_price"] == "665"


def test_unclassified_additional_price_does_not_invalidate_explicit_nightly_quote():
    original, page, columns = fixture()
    page["blocks"].append({"id": "additional", "kind": "text", "text": "$777", "group_id": "g1", "association": "record"})
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "verified"
    assert pricing["comparison_amount"] == "259"
    assert any(item["amount"] == "777" and item["kind"] == "unknown" for item in pricing["observations"])


def test_own_literal_nightly_source_quote_survives_an_empty_model_scalar():
    original, page, columns = fixture()
    original["price"] = None
    original["evidence"]["price"] = ""
    page["blocks"] = [page["blocks"][0], {
        "id": "literal", "kind": "text", "text": "US$259 per night",
        "group_id": "g1", "association": "record",
    }]
    row = assess_pricing([original], [page], PROMPT, columns)["records"][0]
    assert row["price"] is None
    assert row["pricing"]["status"] == "verified"
    assert row["pricing"]["comparison_amount"] == "259"
    assert row["pricing"]["observations"][0]["evidence_method"] == "literal_quote"
    assert pricing_comparison_record(row)["price"] == "259"


def test_two_different_current_nightly_amounts_remain_ambiguous_and_visible():
    original, page, columns = fixture()
    page["blocks"].append(price_block("other-nightly", "$299", "Per night $299", "Per night"))
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert "price_observation_ambiguous" in pricing["issues"]
    assert pricing["comparison_amount"] is None
    assert {item["amount"] for item in pricing["observations"]} == {"259", "299", "559", "665"}
    assert not any(item["selected"] for item in pricing["observations"])


def test_original_nightly_price_is_not_selected_as_a_current_price():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0], price_block("old", "$300", "Per night $300", "Per night", original=True), page["blocks"][-1]]
    original["price"] = "300"
    original["evidence"]["price"] = "Per night $300"
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert pricing["comparison_amount"] is None
    assert "original_price_not_current_quote" in pricing["issues"]
    assert pricing["observations"][0]["role"] == "original"


def test_current_amount_equal_to_a_separate_original_amount_is_not_removed():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0],
        price_block("nightly", "$665", "Per night $665", "Per night"),
        price_block("original", "$665", "$665", original=True), page["blocks"][-1]]
    original["price"] = "665"
    original["evidence"]["price"] = "Per night $665"
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "verified"
    assert pricing["comparison_amount"] == "665"
    assert any(item["role"] == "original" and not item["selected"] for item in pricing["observations"])


def test_currencyless_struck_price_keeps_original_role_with_selected_usd():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0],
        price_block("old", "665 per night", "665 per night", original=True), page["blocks"][-1]]
    original["price"] = "665"
    original["evidence"]["price"] = "665 per night"
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["currency"] == "USD"
    assert pricing["status"] == "unverified"
    assert pricing["comparison_amount"] is None
    assert pricing["observations"][0]["role"] == "original"
    assert not pricing["observations"][0]["selected"]


def test_currencyless_scalar_has_its_own_bound_nightly_label_and_selected_currency():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0],
        price_block("nightly", "259", "Per night 259", "Per night"), page["blocks"][-1]]
    original["price"] = None
    original["evidence"]["price"] = ""
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "verified"
    assert pricing["currency"] == "USD"
    assert pricing["comparison_amount"] == "259"
    assert pricing["observations"][0]["quote"] == "Per night 259"


def test_currencyless_numeric_rating_is_not_a_price_from_page_currency_alone():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0],
        price_block("rating", "6.6", "6.6", original=True), page["blocks"][-1]]
    original["price"] = None
    original["evidence"]["price"] = ""
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert pricing["observations"] == []
    assert pricing["comparison_amount"] is None


def test_currencyless_price_must_not_extract_stay_counts_as_additional_amounts():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0],
        price_block("total", "559", "559 2 nights, 4 adults", "2 nights, 4 adults"), page["blocks"][-1]]
    original["price"] = None
    original["evidence"]["price"] = ""
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "verified"
    assert pricing["comparison_amount"] == "279.5"
    assert [item["amount"] for item in pricing["observations"]] == ["559"]


def test_outer_quote_with_multiple_current_amounts_cannot_borrow_one_label():
    original, page, columns = fixture()
    for block in page["blocks"]:
        if block["id"] == "total":
            block["value_context"]["quote"] = "$259 $559 2 nights, 4 adults"
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["comparison_amount"] == "259"
    assert next(item for item in pricing["observations"] if item["amount"] == "559")["kind"] == "unknown"


def test_old_capture_cannot_attach_card_wide_nightly_label_to_one_of_many_amounts():
    original, page, columns = fixture()
    for block in page["blocks"]:
        block.pop("value_context", None)
    page["blocks"].append({"id": "basis", "kind": "text", "text": "Per night", "group_id": "g1", "association": "record"})
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert pricing["kind"] == "unknown"
    assert pricing["comparison_amount"] is None
    assert {item["amount"] for item in pricing["observations"]} == {"259", "559", "665"}


def test_local_basis_metadata_cannot_borrow_a_neighboring_records_amount():
    original, page, columns = fixture()
    for block in page["blocks"]:
        if block.get("id") == "nightly":
            block["group_id"] = "neighbor"
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert all(item["amount"] != "259" for item in pricing["observations"])
    assert pricing["comparison_amount"] == "279.5"
    assert pricing["calculation"]["source_amount"] == "559"


def test_unbacked_or_invented_local_basis_label_does_not_verify_a_price():
    original, page, columns = fixture()
    page["blocks"] = [page["blocks"][0], price_block("amount", "$559", "$559", "Per night"), page["blocks"][-1]]
    pricing = assess_pricing([original], [page], PROMPT, columns)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert pricing["kind"] == "unknown"
    assert pricing["comparison_amount"] is None


def test_total_field_is_never_rewritten_to_nightly_in_query_projection():
    original, page, columns = fixture()
    original["stay_total_price"] = original.pop("price")
    original["evidence"]["stay_total_price"] = original["evidence"].pop("price")
    columns[1].name = "stay_total_price"
    row = assess_pricing([original], [page], PROMPT, columns)["records"][0]
    assert row["pricing"]["comparison_amount"] == "259"
    assert pricing_comparison_record(row)["stay_total_price"] == "559"


def test_total_budget_uses_selected_total_without_rewriting_original_nightly_value():
    original, page, columns = fixture()
    original["price"] = "259"
    original["evidence"]["price"] = "Per night $259"
    prompt = PROMPT.replace("around 250-350 USD nightly", "around 550-600 USD total")
    row = assess_pricing([original], [page], prompt, columns)["records"][0]
    assert row["price"] == "259"
    assert row["pricing"]["displayed_amount"] == "559"
    assert row["pricing"]["budget_status"] == "within_target"
    assert pricing_comparison_record(row)["price"] == "559"


def test_non_hotel_product_prices_are_not_converted_to_stay_pricing():
    original, page, columns = fixture()
    original["product_name"] = original.pop("hotel_name")
    columns[0].name = "product_name"
    result = assess_pricing([original], [page], "Get products with current and original prices", columns)
    assert result["summary"]["applicable"] is False
    assert result["records"] == [original]
