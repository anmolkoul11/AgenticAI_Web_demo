"""Captured result headings supplement independent returned-page facts only."""

import copy

import pytest

from agentic_web_demo.stay_scope import reconcile_captured_result_scope


def returned_scope():
    requested = {
        "destination": "new york", "check_in": "2026-10-28",
        "check_out": "2026-10-30", "nights": 2, "adults": 4, "rooms": 2,
    }
    observed = {
        "destination": None, "check_in": "2026-10-28", "check_out": "2026-10-30",
        "adults": "4", "rooms": "2",
    }
    return {
        "status": "unverified", "source": "returned_page", "document_id": "returned-doc",
        "requested": requested, "observed": observed, "contradictions": [],
        "availability_verified": False,
        "fields": [
            {
                "field": field, "expected": requested[field], "observed": value,
                "status": "verified" if value is not None else "unverified",
                "method": "returned_url" if value is not None else "none",
                "evidence": f"{field}={value}" if value is not None else "No fresh returned-page value.",
            }
            for field, value in observed.items()
        ],
    }


def heading(text="New York: 372 properties found", **changes):
    return {
        "id": "b1", "kind": "heading", "text": text, "heading_level": 1,
        "association": "page", "group_id": None, **changes,
    }


def test_current_run_missing_destination_is_reconciled_from_captured_result_heading():
    scope = returned_scope()
    result = reconcile_captured_result_scope(scope, [heading()], document_id="returned-doc")
    assert result["status"] == "verified"
    assert result["observed"]["destination"] == "New York"
    destination = result["fields"][0]
    assert destination["status"] == "verified"
    assert destination["method"] == "captured_results_heading"
    assert destination["evidence"] == "New York: 372 properties found"
    assert destination["block_ids"] == ["b1"]
    assert destination["captured_evidence"] == [{
        "method": "captured_results_heading", "value": "New York",
        "quote": "New York: 372 properties found", "block_ids": ["b1"],
    }]
    assert result["fields"][1:] == scope["fields"][1:]
    assert result["availability_verified"] is False


@pytest.mark.parametrize("changes", [
    {"association": "record", "group_id": "g1"},
    {"association": "page", "group_id": "g1"},
    {"association": "ambiguous"},
    {"association": None},
    {"kind": "link"},
    {"kind": "paragraph"},
    {"heading_level": 3},
    {"text": "Manhattan, New York Show on map"},
    {"text": "New York hotel with 372 reviews"},
    {"id": ""},
])
def test_neighbor_navigation_and_non_result_blocks_are_not_destination_proof(changes):
    scope = returned_scope()
    result = reconcile_captured_result_scope(scope, [heading(**changes)], document_id="returned-doc")
    assert result == scope
    assert result is not scope


@pytest.mark.parametrize("source, scope_document, live_document", [
    ("pre_submit", "returned-doc", "returned-doc"),
    ("returned_page", "previous-doc", "returned-doc"),
    ("returned_page", "", ""),
    ("returned_page", None, "returned-doc"),
    ("returned_page", "returned-doc", None),
])
def test_heading_cannot_cross_source_or_document_boundaries(source, scope_document, live_document):
    scope = returned_scope()
    scope.update(source=source, document_id=scope_document)
    result = reconcile_captured_result_scope(scope, [heading()], document_id=live_document)
    assert result == scope


@pytest.mark.parametrize("missing_field", ["check_in", "check_out", "adults", "rooms"])
def test_heading_does_not_fill_missing_dates_or_occupancy(missing_field):
    scope = returned_scope()
    scope["observed"][missing_field] = None
    field = next(item for item in scope["fields"] if item["field"] == missing_field)
    field.update(status="unverified", observed=None, method="none", evidence="No fresh returned-page value.")
    blocks = [heading(), {
        "id": "b2", "kind": "paragraph", "association": "record", "group_id": "g1",
        "text": "Check-in 2026-10-28 check-out 2026-10-30, 4 adults, 2 rooms",
    }]
    result = reconcile_captured_result_scope(scope, blocks, document_id="returned-doc")
    assert result["status"] == "unverified"
    assert result["observed"][missing_field] is None
    assert next(item for item in result["fields"] if item["field"] == missing_field) == field


def test_missing_year_is_not_borrowed_from_requested_dates():
    scope = returned_scope()
    scope["observed"]["check_in"] = "Oct 28"
    field = next(item for item in scope["fields"] if item["field"] == "check_in")
    field.update(observed="Oct 28", method="returned_control")
    result = reconcile_captured_result_scope(scope, [heading()], document_id="returned-doc")
    assert result["status"] == "unverified"
    assert result["observed"]["check_in"] == "Oct 28"


def test_pre_submit_numeric_values_are_not_promoted_as_returned_proof():
    scope = returned_scope()
    for item in scope["fields"][1:]:
        item["method"] = "verified_pre_submit_form"
    result = reconcile_captured_result_scope(scope, [heading()], document_id="returned-doc")
    assert result["status"] == "unverified"


@pytest.mark.parametrize("observed, status", [("Boston", "mismatch"), ("Boston", "verified")])
def test_matching_heading_cannot_conceal_conflicting_returned_control(observed, status):
    scope = returned_scope()
    scope["observed"]["destination"] = observed
    scope["fields"][0].update(observed=observed, status=status, method="returned_control", evidence="Destination Boston")
    result = reconcile_captured_result_scope(scope, [heading()], document_id="returned-doc")
    assert result["status"] == "mismatch"
    assert result["fields"][0]["status"] == "mismatch"
    assert "Boston" in result["observed"]["destination"]
    assert "New York" in result["observed"]["destination"]
    assert "Destination Boston" in result["fields"][0]["evidence"]


def test_conflicting_count_headings_are_not_cherry_picked():
    result = reconcile_captured_result_scope(
        returned_scope(), [heading(), heading("Boston: 24 properties found", id="b2")],
        document_id="returned-doc",
    )
    assert result["status"] == "mismatch"
    assert result["fields"][0]["block_ids"] == ["b1", "b2"]


@pytest.mark.parametrize("previous_status, contradictions, expected_status", [
    ("mismatch", [], "mismatch"),
    ("unverified", [{"code": "catalog_starting_price", "evidence": "Price from $100"}], "unverified"),
    ("mismatch", [{"code": "price_context_occupancy_mismatch", "evidence": "2 adults"}], "mismatch"),
])
def test_existing_mismatch_and_contradictions_remain_blocking(previous_status, contradictions, expected_status):
    scope = returned_scope()
    scope.update(status=previous_status, contradictions=contradictions)
    result = reconcile_captured_result_scope(scope, [heading()], document_id="returned-doc")
    assert result["status"] == expected_status
    assert result["contradictions"] == contradictions


def test_reconciliation_is_immutable_and_repeated_evidence_is_not_duplicated():
    scope, blocks = returned_scope(), [heading()]
    original_scope, original_blocks = copy.deepcopy(scope), copy.deepcopy(blocks)
    result = reconcile_captured_result_scope(scope, blocks, document_id="returned-doc")
    repeated = reconcile_captured_result_scope(result, blocks, document_id="returned-doc")
    assert scope == original_scope
    assert blocks == original_blocks
    assert repeated == result
    result["fields"][0]["block_ids"].append("b99")
    assert scope == original_scope
