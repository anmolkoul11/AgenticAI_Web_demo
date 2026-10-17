"""Offline service contracts for returned stay pricing; authored, not live-site tests."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import (
    Condition,
    Extraction,
    QueryRule,
    WebsiteInput,
    prepare_extraction,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.service import DashboardService


BASE_REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms. "
)


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


def source(*, soft=False, price="600", framework="langgraph"):
    return WebsiteInput(
        framework=framework,
        source="paste",
        urls=["https://example.org/results"],
        page_text=(
            "North Hotel has rooms shown in the result. "
            f"{price} USD total for 2 nights, 4 adults and 2 rooms; taxes included."
        ),
        instructions=BASE_REQUEST + (
            "Try to find the price around 250-350 USD nightly."
            if soft else "Keep hotels priced between 250 and 350 USD nightly."
        ),
        authorized=True,
        allow_model_api=True,
    )


def candidate(price="600"):
    values = {
        "hotel_name": ("North Hotel", "North Hotel"),
        "price": (price, f"{price} USD"),
        "currency": ("USD", "USD"),
        "price_basis": ("total for 2 nights", "total for 2 nights"),
    }
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review the source records",
            "content_type": "hotels",
            "interpretation": "Hotel source prices",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {
                    "name": name,
                    "kind": "number" if name == "price" else "text",
                    "unit": "USD" if name == "price" else "",
                    "description": name,
                }
                for name in values
            ],
            # Deliberately present even in the soft-target fixture. Preparation
            # must not preserve a model-created hard exclusion for 'around'.
            "filters": [
                {"field": "price", "operator": "gte", "value": "250"},
                {"field": "price", "operator": "lte", "value": "350"},
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": name, "value": value, "evidence": quote}
                        for name, (value, quote) in values.items()
                    ],
                }
            ],
        }
    )


def assessment(*, amount="300", status="verified", budget="within_target"):
    """Isolate service gating from the independent source-assessment unit fixtures."""
    def assess(records, pages, instructions, columns):
        rows = deepcopy(records)
        for row in rows:
            row["pricing"] = {
                "status": status,
                "scope_status": "verified" if status == "verified" else "mismatch",
                "price_field": "price",
                "displayed_amount": row["price"],
                "currency": "USD",
                "kind": "stay_total",
                "source_basis": "stay_total",
                "basis_label": "Average per night, all requested rooms",
                "comparison_amount": amount if status == "verified" else None,
                "comparison_scope": "all_rooms",
                "combined_nightly": amount if status == "verified" else None,
                "calculation": {"operation": "stay_total / nights", "nights": 2},
                "taxes": "included",
                "taxes_status": "included",
                "budget_status": budget if status == "verified" else "unverified",
                "issues": [] if status == "verified" else ["price_context_occupancy_mismatch"],
                "evidence": {"source_url": row["source_url"], "block_ids": [], "quote": ""},
            }
            row.update(
                pricing_combined_nightly=amount if status == "verified" else None,
                pricing_basis="Average per night, all requested rooms",
                pricing_taxes="included",
                pricing_budget_status=budget if status == "verified" else "unverified",
            )
        return {
            "records": rows,
            "assessments": [],
            "stay_scope": {"status": "verified" if status == "verified" else "mismatch"},
            "summary": {
                "contract_version": custom_service.PRICING_CONTRACT_VERSION,
                "applicable": True,
                "applicable_count": len(rows),
                "verified": len(rows) if status == "verified" else 0,
                "unverified": len(rows) if status != "verified" else 0,
                "within_target": len(rows) if budget == "within_target" else 0,
                "outside_target": len(rows) if budget == "outside_target" else 0,
            },
        }
    return assess


def run_plan(service, monkeypatch, values, *, amount="300", status="verified", budget="within_target"):
    monkeypatch.setattr(
        custom_service, "interpret",
        lambda *_: (candidate("900" if amount == "450" else "600"), {"model": "fixture"}),
    )
    monkeypatch.setattr(custom_service, "assess_pricing", assessment(
        amount=amount, status=status, budget=budget
    ))
    return finished(service, custom_service.plan(service, values, object()))


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_combined_average_is_used_for_hard_filters_but_source_total_is_preserved(
    service, monkeypatch, framework
):
    job = run_plan(service, monkeypatch, source(framework=framework))
    assert job["status"] == "awaiting_review"
    proposal = job["result"]["proposal"]
    record = proposal["records"][0]
    assert record["price"] == "600"
    assert record["pricing_combined_nightly"] == "300"
    assert proposal["review_counts"]["filtered_out"] == 0
    assert any(
        column["name"] == "pricing_combined_nightly" and column["computed"]
        for column in proposal["columns"]
    )
    fields = proposal["field_statuses"][0]["fields"]
    assert fields["price"]["status"] == "source_verified"
    assert fields["pricing_combined_nightly"]["status"] == "computed"
    assert "pricing_combined_nightly" not in record["evidence"]


def test_soft_target_is_persisted_and_outside_alternative_is_not_hard_excluded(service, monkeypatch):
    job = run_plan(
        service, monkeypatch, source(soft=True, price="900"), amount="450", budget="outside_target"
    )
    assert job["status"] == "awaiting_review"
    proposal = job["result"]["proposal"]
    assert proposal["filters"] == []
    assert proposal["request_preferences"]
    assert proposal["request_preferences"][0]["enforcement"] == "preference"
    assert proposal["records"][0]["price"] == "900"
    assert proposal["records"][0]["pricing_budget_status"] == "outside_target"
    assert proposal["pricing_summary"]["within_target_ready"] == 0
    assert proposal["pricing_summary"]["outside_target_ready"] == 1
    assert any("not labelled budget matches" in warning for warning in proposal["warnings"])


def test_mismatched_stay_price_is_readonly_not_a_saved_match(service, monkeypatch):
    job = run_plan(service, monkeypatch, source(soft=True), status="unverified")
    assert job["status"] == "needs_input"
    result = job["result"]
    assert "proposal" not in result
    assert result["review_counts"]["matched"] == 0
    assert result["review_counts"]["constraint_unverified"] == 1
    assert result["unverified_preview"][0]["price"] == "600"
    assert result["unverified_preview"][0]["pricing"]["scope_status"] == "mismatch"
    assert not list((service.data_dir / "exports").glob("*.json"))


def test_rule_comparisons_use_combined_average_without_overwriting_displayed_total():
    row = assessment()(
        [{
            "listing_id": "record-0001", "source_url": "https://example.org", "price": "600",
            "evidence": {"price": "600 USD"},
        }],
        [], BASE_REQUEST, [],
    )["records"][0]
    rule = QueryRule(
        name="budget", description="Flag under 350", request_quote="flag under 350",
        combination="all", conditions=[Condition(field="price", operator="lt", value="350")],
    )
    compared = custom_service.apply_pricing_rules([row], [rule])[0]
    assert compared["rule_budget"] == "matched"
    assert compared["price"] == "600"
    assert compared["evidence"] == row["evidence"]


def test_model_cannot_supply_server_owned_pricing_fields():
    model = candidate()
    model.columns[0].name = "pricing_basis"
    model.rows[0].cells[0].field = "pricing_basis"
    with pytest.raises(WebsiteError, match="reserved"):
        model, values, _ = prepare_extraction(model, source())
        validate_extraction(model, values, [{
            "url": values.urls[0], "text": values.page_text, "truncated": False
        }])


def test_pending_legacy_pricing_proposal_cannot_bypass_returned_scope_check(service, monkeypatch):
    job = run_plan(service, monkeypatch, source())
    proposal = job["result"]["proposal"]
    proposal.pop("pricing_summary")
    custom_service.write_json(
        service.data_dir / "website-plans" / f"{proposal['plan_id']}.json", proposal
    )
    with pytest.raises(WebsiteError, match="returned stay"):
        custom_service.execute(
            service, proposal["plan_id"], custom_service.digest(proposal), accept_partial=True
        )
    assert not list((service.data_dir / "exports").glob("*.json"))


def test_save_reassesses_source_inputs_instead_of_trusting_stored_pricing(service, monkeypatch):
    job = run_plan(service, monkeypatch, source())
    proposal = job["result"]["proposal"]
    monkeypatch.setattr(custom_service, "assess_pricing", assessment(status="unverified"))
    with pytest.raises(WebsiteError, match="returned stay"):
        custom_service.execute(
            service, proposal["plan_id"], job["result"]["revision"], accept_partial=True
        )
    assert not list((service.data_dir / "exports").glob("*.json"))


def test_source_pricing_inputs_are_roundtripped_without_duplicating_block_text():
    blocks = [{"id": "b1", "kind": "paragraph", "text": "600 USD total", "href": None}]
    pages = [{
        "url": "https://example.org/results", "text": "600 USD total", "blocks": blocks,
        "browser_task_context": {"result_scope": {"status": "verified"}},
    }]
    stored = custom_service.pricing_source_pages(pages)
    assert "text" not in stored[0]
    restored = custom_service.saved_pricing_pages({"pricing_sources": stored})
    assert restored[0]["text"] == "600 USD total"
    assert restored[0]["browser_task_context"] == pages[0]["browser_task_context"]


def real_pricing_fixture(*, wrong_stay=False, framework="langgraph"):
    """Source inputs for the real engine, not a substituted assessment result."""
    amount = "300" if wrong_stay else "600"
    text = (
        "Price from 300 USD; 1 night, 2 adults"
        if wrong_stay
        else "600 USD total for 2 nights, 4 adults and 2 rooms; taxes included."
    )
    model = candidate(amount)
    if wrong_stay:
        basis_cell = next(cell for cell in model.rows[0].cells if cell.field == "price_basis")
        basis_cell.value = "1 night, 2 adults"
        basis_cell.evidence = "1 night, 2 adults"
    stay = {
        "destination": "New York",
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "adults": 4,
        "rooms": 2,
    }
    page = {
        "url": "https://example.org/results",
        "text": "North Hotel\n" + text,
        "truncated": False,
        "blocks": [
            {
                "id": "b1", "kind": "heading", "text": "North Hotel", "href": None,
                "group_id": "g1", "association": "record",
            },
            {
                "id": "b2", "kind": "paragraph", "text": text, "href": None,
                "group_id": "g1", "association": "record",
            },
        ],
        "browser_task_context": {
            "result_scope": {
                "status": "verified",
                "requested": deepcopy(stay),
                "observed": deepcopy(stay),
                "source": "returned_page",
                "availability_verified": False,
            }
        },
    }
    values = WebsiteInput(
        source="public", framework=framework, urls=[page["url"]],
        instructions=BASE_REQUEST + "Keep hotels priced between 250 and 350 USD nightly.",
        authorized=True, allow_model_api=True,
    )
    return values, model, page


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_real_source_assessment_roundtrips_plan_to_save_without_a_pricing_stub(
    service, monkeypatch, framework
):
    values, model, page = real_pricing_fixture(framework=framework)
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [deepcopy(page)])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model, {"model": "fixture"}))
    planned = finished(service, custom_service.plan(service, values, object()))
    assert planned["status"] == "awaiting_review"
    proposal = planned["result"]["proposal"]
    row = proposal["records"][0]
    assert row["price"] == "600"
    assert row["pricing_combined_nightly"] == "300"
    assert row["pricing"]["kind"] == "stay_total_all_rooms"
    assert row["pricing"]["calculation"]["nights"] == 2
    assert row["pricing"]["taxes"] == "included"
    assert row["pricing_budget_status"] == "within_target"
    assert proposal["stay_scope"]["status"] == "verified"
    assert proposal["review_counts"]["filtered_out"] == 0
    assert "text" not in proposal["pricing_sources"][0]
    saved = finished(service, custom_service.execute(
        service, proposal["plan_id"], planned["result"]["revision"], accept_partial=True
    ))
    assert saved["status"] == "completed"
    snapshot = json.loads(
        (service.data_dir / "exports" / f"{saved['result']['run_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["records"][0]["price"] == "600"
    assert snapshot["records"][0]["pricing_combined_nightly"] == "300"
    assert snapshot["records"][0]["pricing"] == row["pricing"]
    assert snapshot["computed_columns"][0]["name"] == "pricing_combined_nightly"
    assert snapshot["computed_columns"][0]["computed"] is True


def test_real_wrong_stay_card_remains_readonly_despite_a_correct_returned_header(
    service, monkeypatch
):
    values, model, page = real_pricing_fixture(wrong_stay=True)
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [deepcopy(page)])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model, {"model": "fixture"}))
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "needs_input"
    result = job["result"]
    assert "proposal" not in result
    assert result["review_counts"]["matched"] == 0
    row = result["unverified_preview"][0]
    assert row["price"] == "300"
    assert row["pricing"]["scope_status"] == "mismatch"
    assert "requested_stay_mismatch" in row["pricing"]["issues"]
    assert "starting_price_not_requested_stay_quote" in row["pricing"]["issues"]
    assert row["pricing_budget_status"] == "unverified"
    assert not list((service.data_dir / "exports").glob("*.json"))
