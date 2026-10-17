"""Offline regressions for source-bound stay pricing; run only on user request."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.custom_constraints import constraint_coverage, requested_constraints
from agentic_web_demo.pricing import assess_pricing, pricing_comparison_record

URL = "https://example.org/search"
PROMPT = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms. Try to find the price around 250-350 USD nightly."
)
COLUMNS = [
    SimpleNamespace(name="hotel_name", kind="text"),
    SimpleNamespace(name="price", kind="number"),
]
STAY = {
    "destination": "New York",
    "check_in": "2026-10-28",
    "check_out": "2026-10-30",
    "adults": 4,
    "rooms": 2,
}


def fixture(text="US$300 per night, all requested rooms, including taxes", amount="300"):
    record = {
        "listing_id": "record-0001",
        "hotel_name": "Example Hotel",
        "price": amount,
        "source_url": URL,
        "evidence": {"hotel_name": "Example Hotel", "price": text},
    }
    page = {
        "url": URL,
        "blocks": [
            {
                "id": "b1",
                "kind": "heading",
                "text": "Example Hotel",
                "group_id": "g1",
                "association": "record",
            },
            {
                "id": "b2",
                "kind": "text",
                "text": text,
                "group_id": "g1",
                "association": "record",
            },
        ],
        "browser_task_context": {
            "result_scope": {
                "status": "verified",
                "requested": deepcopy(STAY),
                "observed": deepcopy(STAY),
                "source": "returned_page",
                "availability_verified": False,
            }
        },
    }
    return record, page


def assess(
    text="US$300 per night, all requested rooms, including taxes", amount="300", prompt=PROMPT
):
    row, page = fixture(text, amount)
    return assess_pricing([row], [page], prompt, COLUMNS)


@pytest.mark.parametrize(
    "wording",
    [
        "Try to find the price around 250-350 USD nightly",
        "Prefer 250-350 USD per night",
        "Price about 250 to 350 USD nightly",
        "Try price between 250 and 350 USD per night",
    ],
)
def test_casual_budget_is_retained_as_combined_nightly_preference(wording):
    constraints = requested_constraints(wording)
    assert len(constraints) == 1
    assert constraints[0]["enforcement"] == "preference"
    assert constraints[0]["room_scope"] == "all_rooms"
    assert constraints[0]["currency"] == "USD"
    assert constraints[0]["conditions"] == [
        {"operator": "gte", "value": "250"},
        {"operator": "lte", "value": "350"},
    ]
    assert constraint_coverage(constraints, COLUMNS, [])["issues"] == []


def test_explicit_required_bounds_remain_hard_and_per_room_is_explicit():
    constraints = requested_constraints("Keep price between 250 and 350 USD per night per room")
    assert constraints[0]["enforcement"] == "hard"
    assert constraints[0]["room_scope"] == "per_room"
    assert len(constraint_coverage(constraints, COLUMNS, [])["issues"]) == 2


def test_verified_stay_total_uses_nights_not_room_count_and_keeps_raw_value():
    result = assess("Full-stay total US$600, including taxes", "600")
    row = result["records"][0]
    pricing = row["pricing"]
    assert row["price"] == "600"
    assert pricing["status"] == "verified"
    assert pricing["kind"] == "stay_total_all_rooms"
    assert pricing["combined_nightly"] == "300"
    assert pricing["calculation"]["nights"] == 2
    assert pricing["calculation"]["label"] == "Average per night"
    assert pricing["budget_status"] == "within_target"
    assert pricing["taxes"] == "included"
    comparison = pricing_comparison_record(row)
    assert comparison["price"] == "300"
    assert row["price"] == "600"
    assert result["stay_scope"]["availability_verified"] is False


def test_soft_outside_target_stays_verified_but_is_not_a_budget_match():
    row = assess("US$419 per night, all requested rooms", "419")["records"][0]
    assert row["pricing"]["status"] == "verified"
    assert row["pricing"]["budget_status"] == "outside_target"
    assert row["pricing"]["taxes"] == "unknown"


def test_per_room_price_is_never_multiplied_into_combined_room_price():
    row = assess("US$150 per room, per night", "150")["records"][0]
    assert row["price"] == "150"
    assert row["pricing"]["status"] == "unverified"
    assert row["pricing"]["kind"] == "per_room_per_night"
    assert row["pricing"]["combined_nightly"] is None
    assert "combined_room_price_unverified" in row["pricing"]["issues"]
    assert pricing_comparison_record(row)["price"] == "150"


def test_explicit_per_room_request_can_compare_literal_per_room_price():
    prompt = PROMPT.replace("250-350 USD nightly", "100-200 USD per room per night")
    row = assess("US$150 per room, per night", "150", prompt)["records"][0]
    assert row["pricing"]["status"] == "verified"
    assert row["pricing"]["comparison_scope"] == "per_room"
    assert row["pricing"]["comparison_amount"] == "150"
    assert row["pricing"]["combined_nightly"] is None


def test_starting_card_scope_overrides_independently_correct_header():
    row = assess("Price from US$300; 1 night, 2 adults", "300")["records"][0]
    assert row["pricing"]["scope_status"] == "mismatch"
    assert row["pricing"]["status"] == "unverified"
    assert "requested_stay_mismatch" in row["pricing"]["issues"]
    assert "starting_price_not_requested_stay_quote" in row["pricing"]["issues"]
    assert row["pricing"]["budget_status"] == "unverified"


def test_pre_search_form_context_cannot_verify_returned_stay():
    record, page = fixture()
    page["browser_task_context"] = {"form_scope_verified": True, "requested": STAY}
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["status"] == "unverified"
    assert "requested_stay_scope_unverified" in row["pricing"]["issues"]


def test_complete_literal_record_stay_can_verify_without_browser_metadata():
    text = (
        "New York; check-in 2026-10-28; check-out 2026-10-30; 4 adults; 2 rooms. "
        "US$300 per night, all requested rooms"
    )
    record, page = fixture(text)
    page.pop("browser_task_context")
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["status"] == "verified"


def test_bare_dollar_requires_explicit_selected_currency_source_evidence():
    record, page = fixture("$300 per night, all requested rooms")
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["currency"] is None
    assert row["pricing"]["status"] == "unverified"
    page["blocks"].append(
        {
            "id": "b3",
            "kind": "text",
            "text": "Prices in U.S. Dollar USD",
            "association": "page",
            "content_role": "currency_setting",
        }
    )
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["status"] == "verified"
    assert row["pricing"]["currency_evidence"]["block_ids"] == ["b3"]


def test_unrelated_page_currency_or_basis_cannot_relabel_record_price():
    record, page = fixture("$300")
    page["blocks"].append(
        {"id": "b3", "kind": "text", "text": "USD prices per night", "association": "page"}
    )
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["currency"] is None
    assert row["pricing"]["kind"] == "unknown"


@pytest.mark.parametrize("change", ["ungrouped", "duplicate_identity", "different_price_group"])
def test_source_binding_must_be_unique_and_same_group(change):
    record, page = fixture()
    if change == "ungrouped":
        for block in page["blocks"]:
            block.pop("group_id")
    elif change == "duplicate_identity":
        page["blocks"].append({**page["blocks"][0], "id": "b3", "group_id": "g2"})
    else:
        page["blocks"][1]["group_id"] = "g2"
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["status"] == "unverified"
    assert "price_record_binding_unverified" in row["pricing"]["issues"]


def test_tax_inclusion_does_not_claim_fees_are_included():
    row = assess("US$300 per night; taxes included, fees excluded")["records"][0]
    assert row["pricing"]["taxes_status"] == "included"
    assert row["pricing"]["fees_status"] == "excluded"


def test_soft_inclusive_budget_is_unverified_when_source_excludes_taxes():
    prompt = PROMPT.replace("USD nightly", "USD nightly including taxes")
    row = assess("US$300 per night, excluding taxes", prompt=prompt)["records"][0]
    assert row["pricing"]["taxes_status"] == "excluded"
    assert row["pricing"]["budget_status"] == "unverified"
    assert "requested_taxes_unverified" in row["pricing"]["issues"]


def test_reassessment_discards_stored_server_pricing_even_when_not_applicable():
    record = {
        "hotel_name": "Example Hotel",
        "pricing": {"status": "verified", "comparison_amount": "300"},
        "pricing_combined_nightly": "300",
    }
    result = assess_pricing([record], [], "Get hotel names", COLUMNS)
    assert result["records"] == [{"hotel_name": "Example Hotel"}]
    assert result["summary"]["applicable"] is False


def test_nightly_catalog_without_stay_does_not_claim_requested_availability():
    record, page = fixture()
    page.pop("browser_task_context")
    prompt = "Hotels priced around 250-350 USD nightly"
    result = assess_pricing([record], [page], prompt, COLUMNS)
    pricing = result["records"][0]["pricing"]
    assert pricing["status"] == "verified"
    assert pricing["scope_status"] == "not_requested"
    assert pricing["basis_label"] == "Per night; room count not specified"
    assert result["stay_scope"]["status"] == "not_requested"


def test_total_budget_does_not_filter_on_derived_nightly_average():
    prompt = PROMPT.replace("around 250-350 USD nightly", "between 550-650 USD total")
    row = assess("Full-stay total US$600", "600", prompt)["records"][0]
    assert row["pricing"]["combined_nightly"] == "300"
    assert row["pricing"]["budget_status"] == "within_target"
    assert pricing_comparison_record(row)["price"] == "600"


def test_names_only_for_a_stay_does_not_add_a_mandatory_price():
    record = {"hotel_name": "Example Hotel"}
    prompt = "Find hotel names in New York for 4 adults and 2 rooms, October 28-30, 2026"
    columns = [SimpleNamespace(name="hotel_name", kind="text")]
    result = assess_pricing([record], [], prompt, columns)
    assert result["records"] == [record]
    assert result["summary"]["applicable"] is False


def test_compact_verified_pricing_summary_can_establish_full_stay_total():
    record, page = fixture("US$600", "600")
    page["blocks"].append({
        "id": "b3", "kind": "text", "text": "2 nights, 4 adults",
        "group_id": "g1", "association": "record",
    })
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["kind"] == "stay_total_all_rooms"
    assert row["pricing"]["combined_nightly"] == "300"


def test_trip_description_is_not_a_price_basis_even_in_same_record_group():
    record, page = fixture("US$600", "600")
    page["blocks"].append({
        "id": "b3", "kind": "paragraph",
        "text": "Spend 2 nights here with 4 adults and enjoy the city.",
        "group_id": "g1", "association": "record",
    })
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["kind"] == "unknown"
    assert row["pricing"]["combined_nightly"] is None


def test_different_amounts_cannot_borrow_each_others_basis():
    record, page = fixture("US$600", "600")
    page["blocks"].extend([
        {
            "id": "b3", "kind": "text", "text": "Original total US$800",
            "group_id": "g1", "association": "record",
        },
        {
            "id": "b4", "kind": "text", "text": "2 nights, 4 adults",
            "group_id": "g1", "association": "record",
        },
    ])
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["kind"] == "unknown"


def test_own_nightly_quote_is_not_relabelled_by_an_original_stay_total():
    record, page = fixture("US$300 per night", "300")
    page["blocks"].append({
        "id": "b3", "kind": "text", "text": "Original total US$800",
        "group_id": "g1", "association": "record",
    })
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["kind"] == "all_rooms_per_night"
    assert row["pricing"]["combined_nightly"] == "300"


def test_additional_tax_amount_is_not_reported_as_included():
    row = assess("US$300 per night + $40 taxes and charges")["records"][0]
    assert row["pricing"]["taxes_status"] == "excluded"
    assert row["pricing"]["fees_status"] == "excluded"


def test_tax_only_disclosure_leaves_fees_unknown():
    row = assess("US$300 per night including taxes")["records"][0]
    assert row["pricing"]["taxes_status"] == "included"
    assert row["pricing"]["fees_status"] == "unknown"


def test_literal_scalar_nightly_basis_can_use_separately_selected_currency():
    record, page = fixture("300 per night, all requested rooms", "300")
    page["blocks"].append({
        "id": "b3", "kind": "text", "text": "Currency: USD",
        "group_id": None, "association": "page", "content_role": "currency_setting",
    })
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    assert row["pricing"]["status"] == "verified"
    assert row["pricing"]["combined_nightly"] == "300"
    assert row["pricing_currency"] == "USD"
    assert row["pricing_fees"] == "unknown"
    assert row["pricing"]["currency_evidence"]["block_ids"] == ["b3"]


def test_inclusive_tax_and_fee_preference_requires_both_disclosures():
    prompt = PROMPT.replace("USD nightly", "USD nightly including taxes and fees")
    row = assess("US$300 per night including taxes", prompt=prompt)["records"][0]
    assert row["pricing"]["status"] == "unverified"
    assert "requested_fees_unverified" in row["pricing"]["issues"]


def test_non_stay_non_nightly_catalog_budget_keeps_legacy_displayed_price_records():
    record = {
        "hotel_name": "Example Hotel", "price": "200",
        "evidence": {"hotel_name": "Example Hotel", "price": "200 USD"},
    }
    result = assess_pricing(
        [record], [], "Boston hotels between 150 and 250 USD", COLUMNS
    )
    assert result["records"] == [record]
    assert result["summary"]["applicable"] is False


def test_news_and_non_stay_product_records_remain_unchanged():
    record = {"listing_id": "record-0001", "price": "300", "evidence": {"price": "USD300"}}
    columns = [SimpleNamespace(name="price", kind="number")]
    result = assess_pricing([record], [], "Get products priced between 250 and 350 USD", columns)
    assert result["records"] == [record]
    assert result["summary"]["applicable"] is False


def selected_usd(page):
    page["blocks"].append({
        "id": "currency", "kind": "text", "text": "Prices in U.S. Dollar USD",
        "association": "page", "content_role": "currency_setting",
    })


@pytest.mark.parametrize("missing", ["numeric_schema", "value", "quote"])
def test_missing_price_dependency_does_not_erase_known_source_context(missing):
    record, page = fixture("Price $3,140", "3140")
    selected_usd(page)
    columns = deepcopy(COLUMNS)
    if missing == "numeric_schema":
        columns[1].kind = "text"
        expected_issue = "missing_or_ambiguous_price_field"
    elif missing == "value":
        record["price"] = None
        expected_issue = "price_amount_quote_unverified"
    else:
        record["evidence"]["price"] = ""
        expected_issue = "price_quote_unavailable"
    before = deepcopy(record)
    row = assess_pricing([record], [page], PROMPT, columns)["records"][0]
    pricing = row["pricing"]
    assert pricing["status"] == "unverified"
    assert expected_issue in pricing["issues"]
    assert pricing["currency"] == "USD"
    assert pricing["currency_evidence"]["block_ids"] == ["currency"]
    assert pricing["scope_status"] == "verified"
    assert "requested_stay_scope_unverified" not in pricing["issues"]
    assert "requested_currency_unverified" not in pricing["issues"]
    assert "price_currency_unverified" not in pricing["issues"]
    assert pricing["kind"] == "unknown"
    assert pricing["comparison_amount"] is None
    assert pricing["combined_nightly"] is None
    assert pricing["budget_status"] == "unverified"
    assert pricing["source_context"]["record_group_verified"] is True
    assert pricing["source_context"]["price_candidates"] == [
        {"block_id": "b2", "quote": "Price $3,140"}
    ]
    assert row["price"] == before["price"]
    assert row["evidence"] == before["evidence"]
    assert record == before


def test_missing_captured_amount_retains_currency_and_stay_without_inventing_price():
    record, page = fixture("Per night", None)
    record["evidence"]["price"] = ""
    selected_usd(page)
    pricing = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]["pricing"]
    assert pricing["displayed_amount"] is None
    assert pricing["currency"] == "USD"
    assert pricing["scope_status"] == "verified"
    assert pricing["kind"] == "unknown"
    assert pricing["comparison_amount"] is None
    assert pricing["source_context"]["price_candidates"] == []
    assert "price_quote_unavailable" in pricing["issues"]


def test_wrong_record_quote_cannot_borrow_an_amount_or_basis_from_neighbor():
    record, page = fixture("US$300 per night, all requested rooms", "300")
    record["evidence"]["price"] = "US$200 full-stay total, all requested rooms"
    page["blocks"].append({
        "id": "neighbor", "kind": "text", "text": record["evidence"]["price"],
        "group_id": "g2", "association": "record",
    })
    row = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]
    pricing = row["pricing"]
    assert "price_record_binding_unverified" in pricing["issues"]
    assert pricing["kind"] == "unknown"
    assert pricing["comparison_amount"] is None
    assert pricing["source_context"]["price_candidates"] == [
        {"block_id": "b2", "quote": "US$300 per night, all requested rooms"}
    ]
    assert row["price"] == "300"


@pytest.mark.parametrize("with_selected_currency", [False, True])
def test_ambiguous_record_context_retains_only_explicit_page_currency_and_stay(
    with_selected_currency,
):
    record, page = fixture()
    page["blocks"].append({**page["blocks"][0], "id": "duplicate", "group_id": "g2"})
    if with_selected_currency:
        selected_usd(page)
    pricing = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]["pricing"]
    assert pricing["status"] == "unverified"
    assert pricing["scope_status"] == "verified"
    assert pricing["currency"] == ("USD" if with_selected_currency else None)
    assert pricing["currency_evidence"]["block_ids"] == (
        ["currency"] if with_selected_currency else []
    )
    assert pricing["source_context"]["record_group_verified"] is False
    assert pricing["source_context"]["price_candidates"] == []
    assert pricing["kind"] == "unknown"


def test_absent_source_page_cannot_borrow_another_pages_currency_or_scope():
    record, page = fixture()
    record["source_url"] = "https://example.org/other"
    selected_usd(page)
    pricing = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]["pricing"]
    assert pricing["scope_status"] == "unverified"
    assert pricing["currency"] is None
    assert pricing["source_context"]["record_group_verified"] is False
    assert "price_source_unavailable" in pricing["issues"]


def test_partial_returned_stay_observations_are_retained_but_not_combined_to_pass():
    record, page = fixture("New York; US$300 per night, all requested rooms")
    returned = page["browser_task_context"]["result_scope"]
    returned["status"] = "unverified"
    returned["observed"].pop("destination")
    pricing = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]["pricing"]
    scope = pricing["source_context"]["stay_scope"]
    assert scope["status"] == "unverified"
    assert scope["observed"] == STAY
    assert "requested_stay_scope_unverified" in pricing["issues"]
    assert pricing["comparison_amount"] is None


def test_pre_search_partial_values_are_not_presented_as_returned_stay_evidence():
    record, page = fixture("US$300 per night, all requested rooms")
    returned = page["browser_task_context"]["result_scope"]
    returned["status"] = "unverified"
    returned["source"] = "pre_search_form"
    pricing = assess_pricing([record], [page], PROMPT, COLUMNS)["records"][0]["pricing"]
    assert pricing["source_context"]["stay_scope"]["observed"] == {}
    assert pricing["scope_status"] == "unverified"
