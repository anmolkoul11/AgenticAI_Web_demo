"""Offline dynamic-field projection and approval fixtures; no model/network calls."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import Column, Condition, Extraction, WebsiteInput
from agentic_web_demo.dashboard.service import DashboardService
from agentic_web_demo.output_contract import project_output_records, select_output_contract


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


def model(*, explicit=False):
    fields = ["product_name", "sku", "manufacturer", "warranty"]
    rows = []
    for name, sku in (("Product One", "ABC1"), ("Product Two", None)):
        values = dict(zip(fields, (name, sku, None, None), strict=True))
        rows.append({
            "page_index": 0,
            "cells": [{"field": field, "value": value, "evidence": value or ""}
                      for field, value in values.items()],
        })
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review source product records",
        "content_type": "product_catalog", "interpretation": "Available captured products",
        "requested_fields": ["warranty"] if explicit else [],
        "columns": [{"name": name, "kind": "text", "unit": "", "description": name}
                    for name in fields],
        "filters": [], "rows": rows, "warnings": [], "more_records_available": False,
    })


def source(*, explicit=False, framework="langgraph"):
    return WebsiteInput(
        framework=framework, source="paste", urls=["https://example.org/catalog"],
        page_text="Product One, SKU ABC1. Product Two. These are literal product names "
        "from the captured catalogue with no manufacturer or warranty values supplied.",
        instructions="Extract the product records" + (" and include warranty." if explicit else "."),
        authorized=True, allow_model_api=True,
    )


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_dynamic_schema_keeps_partial_fields_and_omits_only_empty_inferred_columns(
    service, monkeypatch, framework
):
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model(), {"model": "fixture"}))
    planned = finished(service, custom_service.plan(service, source(framework=framework), object()))
    assert planned["status"] == "awaiting_review"
    proposal = planned["result"]["proposal"]
    assert [column["name"] for column in proposal["columns"]] == ["product_name", "sku"]
    assert proposal["output_contract"]["omitted_inferred_fields"] == ["manufacturer", "warranty"]
    assert proposal["output_contract"]["identity_field"] == "product_name"
    assert proposal["records"][1]["sku"] is None
    assert "manufacturer" not in proposal["records"][0]
    assert len(proposal["source_columns"]) == 4
    saved = finished(service, custom_service.execute(
        service, proposal["plan_id"], planned["result"]["revision"], accept_partial=True
    ))
    assert saved["status"] == "completed"
    snapshot = json.loads((service.data_dir / "exports" / f"{saved['result']['run_id']}.json").read_text(
        encoding="utf-8"
    ))
    assert snapshot["output_contract"] == proposal["output_contract"]
    assert "manufacturer" not in snapshot["columns"]
    assert "manufacturer" not in snapshot["records"][0]
    assert snapshot["records"][1]["sku"] is None


def test_explicit_missing_field_is_retained_with_per_record_reason(service, monkeypatch):
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model(explicit=True), {}))
    planned = finished(service, custom_service.plan(service, source(explicit=True), object()))
    proposal = planned["result"]["proposal"]
    assert "warranty" in [column["name"] for column in proposal["columns"]]
    assert "manufacturer" not in [column["name"] for column in proposal["columns"]]
    assert proposal["output_contract"]["missing_requested_fields"] == ["warranty"]
    assert proposal["partial"] is True
    assert proposal["field_statuses"][0]["fields"]["warranty"]["reason"]
    assert proposal["records"][0]["warranty"] is None


def test_empty_rule_dependencies_are_never_pruned():
    candidate = model()
    rules = [Condition(field="manufacturer", operator="contains", value="Acme")]
    columns, contract = select_output_contract(candidate, rules, [
        {"product_name": "Product One", "sku": "ABC1", "manufacturer": None, "warranty": None}
    ])
    assert "manufacturer" in [column.name for column in columns]
    assert contract["dependency_fields"] == ["manufacturer"]
    assert contract["omitted_inferred_fields"] == ["warranty"]


def test_projection_preserves_server_metadata_but_removes_empty_source_slots():
    columns = [Column(name=name, description=name, kind="text", unit="")
               for name in ("product_name", "manufacturer")]
    original = [{"product_name": "Product One", "manufacturer": None,
                 "source_url": "https://example.org/catalog", "listing_id": "record-1",
                 "evidence": {"product_name": "Product One", "manufacturer": ""},
                 "pricing": {"status": "not_applicable"}}]
    before = deepcopy(original)
    projected = project_output_records(original, columns, columns[:1])
    assert original == before
    assert "manufacturer" not in projected[0]
    assert "manufacturer" not in projected[0]["evidence"]
    assert projected[0]["pricing"] == original[0]["pricing"]


def test_declared_information_fields_are_not_site_templates():
    candidate = model()
    candidate.columns = [Column(name=name, description=name, kind="text", unit="") for name in (
        "company_name", "profile_overview", "url"
    )]
    _, contract = select_output_contract(candidate, [], [{
        "company_name": "Example", "profile_overview": "Literal profile", "url": "https://example.org/company"
    }])
    assert contract["identity_field"] == "company_name"
    assert contract["description_field"] == "profile_overview"
    assert contract["url_field"] == "url"


def test_one_custom_url_field_is_available_as_primary_card_link():
    candidate = model()
    candidate.columns = [Column(name=name, description=name, kind="text", unit="")
                         for name in ("company_name", "profile_url")]
    _, contract = select_output_contract(candidate, [], [{
        "company_name": "Example", "profile_url": "https://example.org/company"
    }])
    assert contract["url_field"] == "profile_url"


def test_multiple_custom_url_fields_do_not_guess_primary_record_link():
    candidate = model()
    candidate.columns = [Column(name=name, description=name, kind="text", unit="")
                         for name in ("company_name", "profile_url", "support_url")]
    _, contract = select_output_contract(candidate, [], [{
        "company_name": "Example", "profile_url": "https://example.org/company",
        "support_url": "https://example.org/support"
    }])
    assert contract["url_field"] is None
