"""Cross-layer multi-price contracts; fixtures only, no live website or provider."""

import json

import pytest
from test_dashboard import finished
from test_pricing_observations import PROMPT, URL, fixture as price_fixture
from test_pricing_workflow import service

from agentic_web_demo import custom_service
from agentic_web_demo.custom_constraints import constraint_coverage, requested_constraints
from agentic_web_demo.custom_extract import (
    Condition, Extraction, WebsiteInput, prepare_extraction, validate_extraction,
)
from agentic_web_demo.enrichment import evidence_block_ids


def inputs(framework="langgraph"):
    return WebsiteInput(
        source="public", framework=framework, urls=[URL], instructions=PROMPT,
        authorized=True, allow_model_api=True,
    )


def model():
    values = {
        "hotel_name": ("Example Hotel", "Example Hotel"),
        "price": ("559", "$559"),
        "nightly_price": ("259", "Per night $259"),
        "stay_total_price": ("559", "$559"),
        "original_price": ("665", "$665"),
    }
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": "hotels",
        "interpretation": "Distinct displayed price roles", "warnings": [],
        "more_records_available": False, "filters": [],
        "columns": [{
            "name": name, "kind": "text" if name == "hotel_name" else "number",
            "description": name, "unit": "",
        } for name in values],
        "rows": [{"page_index": 0, "cells": [
            {"field": name, "value": value, "evidence": quote}
            for name, (value, quote) in values.items()
        ]}],
    })


def page():
    _, source, _ = price_fixture()
    # Deliberately do not duplicate metadata quotes in this text. Their original
    # source blocks must suffice for validation and source-block provenance.
    source["text"] = "\n".join(block["text"] for block in source["blocks"])
    source["truncated"] = False
    return source


def test_literal_context_quotes_validate_and_keep_their_source_block_ids():
    prepared, values, _ = prepare_extraction(model(), inputs())
    source = page()
    rows, _ = validate_extraction(prepared, values, [source])
    assert rows[0]["nightly_price"] == "259"
    assert rows[0]["evidence"]["nightly_price"] == "Per night $259"
    assert evidence_block_ids(rows, [source])[rows[0]["listing_id"]]["nightly_price"] == ["nightly"]


def test_multiple_price_columns_keep_one_primary_constraint_slot():
    values = inputs().model_copy(update={"instructions": PROMPT.replace("around", "between")})
    raw = model()
    raw.filters = [
        Condition(field="price", operator="gte", value="250"),
        Condition(field="price", operator="lte", value="350"),
    ]
    prepared, _, _ = prepare_extraction(raw, values)
    coverage = constraint_coverage(requested_constraints(values.instructions), prepared.columns, prepared.filters)
    assert coverage["fields"]["price"] == "price"
    assert not coverage["issues"]


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_review_save_and_export_preserve_all_prices_while_comparing_nightly(
    service, monkeypatch, framework,
):
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [page()])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model(), {"model": "fixture"}))
    job = finished(service, custom_service.plan(service, inputs(framework), object()))
    assert job["status"] == "awaiting_review"
    proposal = job["result"]["proposal"]
    row = proposal["records"][0]
    assert row["price"] == row["stay_total_price"] == "559"
    assert row["original_price"] == "665"
    assert row["nightly_price"] == row["pricing_combined_nightly"] == "259"
    assert row["pricing"]["budget_status"] == "within_target"
    assert row["pricing"]["calculation"] is None
    assert all(value in row["pricing_observed_amounts"] for value in ("$259", "$559", "$665"))
    assert "original/crossed out" in row["pricing_observed_amounts"]
    assert "pricing_observed_amounts" in {column["name"] for column in proposal["columns"]}
    saved = finished(service, custom_service.execute(
        service, proposal["plan_id"], job["result"]["revision"], accept_partial=True,
    ))
    assert saved["status"] == "completed"
    snapshot = json.loads((service.data_dir / "exports" / f"{saved['result']['run_id']}.json").read_text())
    assert snapshot["records"][0]["pricing"]["observations"] == row["pricing"]["observations"]
    assert snapshot["records"][0]["pricing_observed_amounts"] == row["pricing_observed_amounts"]


def test_blocked_review_reports_only_actual_basis_issues(service, monkeypatch):
    source = page()
    for block in source["blocks"]:
        block.pop("value_context", None)
    source["blocks"].append({"id": "basis", "kind": "text", "text": "Per night",
                             "group_id": "g1", "association": "record"})
    source["text"] += "\nPer night"
    raw = model()
    # The old capture contains no amount-local nightly evidence.
    raw.rows[0].cells[2].evidence = "$259"
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [source])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (raw, {}))
    job = finished(service, custom_service.plan(service, inputs(), object()))
    assert job["status"] == "needs_input"
    result = job["result"]
    reasons = {item["reason"] for item in result["criteria_issues_summary"]}
    assert reasons == {"price_basis_unverified", "nightly_comparison_unverified"}
    assert "requested currency" not in result["guidance"]
    assert "rating scale" not in result["guidance"]
    assert result["unverified_preview"][0]["pricing"]["scope_status"] == "verified"
    assert result["unverified_preview"][0]["pricing"]["currency"] == "USD"
