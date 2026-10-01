"""Query-first extraction regressions; fixtures only, no provider/browser calls."""

from pathlib import Path

import pytest
from test_custom_website import candidate, source
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import (
    Cell,
    Column,
    Condition,
    QueryRule,
    apply_query_rules,
    prepare_extraction,
    rule_outcome,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.service import DashboardService


def preferred():
    return QueryRule(
        name="preferred",
        description="Price below 180 USD",
        request_quote="flag below 180",
        combination="all",
        conditions=[Condition(field="price", operator="lt", value="180")],
    )


def test_reserved_name_repaired_across_records_filters_and_rules():
    result, values = candidate(), source(instructions="flag below 180")
    result.columns[0].name = "source_url"
    for row in result.rows:
        row.cells[0].field = "source_url"
    for condition in result.filters:
        condition.field = "source_url"
    rule = preferred()
    rule.conditions[0].field = "source_url"
    result.query_rules = [rule]
    values.business_rules = [Condition(field="source_url", operator="lt", value="200")]
    fixed, effective, notes = prepare_extraction(result, values)
    assert fixed.columns[0].name == "content_source_url"
    assert fixed.rows[0].cells[0].field == "content_source_url"
    assert fixed.filters[0].field == "content_source_url"
    assert fixed.query_rules[0].conditions[0].field == "content_source_url"
    assert effective.business_rules[0].field == "content_source_url"
    assert result.columns[0].name == "source_url"  # input not mutated
    assert notes
    records, _ = validate_extraction(
        fixed, effective, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert records[0]["source_url"] == values.urls[0]
    assert records[0]["content_source_url"] == "150"


def test_reserved_repair_does_not_collide_with_existing_field():
    result = candidate()
    result.columns[0].name = "source_url"
    result.columns.append(
        Column(name="content_source_url", description="Other", kind="text", unit="")
    )
    for row in result.rows:
        row.cells[0].field = "source_url"
        row.cells.append(Cell(field="content_source_url", value=None, evidence=""))
    fixed, _, _ = prepare_extraction(result, source())
    assert [c.name for c in fixed.columns] == ["content_source_url_2", "content_source_url"]


def test_identical_duplicates_merge_but_conflicts_do_not():
    result = candidate()
    result.columns.append(result.columns[0].model_copy(deep=True))
    for row in result.rows:
        row.cells.append(row.cells[0].model_copy(deep=True))
    fixed, _, notes = prepare_extraction(result, source())
    assert len(fixed.columns) == 1 and len(fixed.rows[0].cells) == 1 and notes
    result.rows[0].cells[1].value = "999"
    with pytest.raises(WebsiteError, match="Conflicting values"):
        prepare_extraction(result, source())


def test_omitted_optional_cells_are_explicit_nulls_not_invented():
    result, values = candidate(), source()
    result.columns.append(
        Column(name="hotel_note", description="Optional note", kind="text", unit="")
    )
    fixed, effective, notes = prepare_extraction(result, values)
    assert all(
        row.cells[1] == Cell(field="hotel_note", value=None, evidence="") for row in fixed.rows
    )
    assert any("marked unavailable (null)" in note for note in notes)
    records, excluded = validate_extraction(
        fixed, effective, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert len(records) == 2 and excluded == 1
    assert all(record["hotel_note"] is None for record in records)


def test_unexpected_row_field_is_quarantined_without_discarding_valid_rows():
    result, values = candidate(), source()
    result.rows[0].cells.append(Cell(field="invented", value="x", evidence="x"))
    schema_issues, rejected = {}, []
    fixed, effective, _ = prepare_extraction(result, values, schema_issues=schema_issues)
    records, excluded = validate_extraction(
        fixed,
        effective,
        [{"url": values.urls[0], "text": values.page_text}],
        rejected=rejected,
        schema_issues=schema_issues,
    )
    assert [record["price"] for record in records] == ["250"]
    assert excluded == 1
    assert rejected == [
        {
            "record_id": "record-0001",
            "source_url": values.urls[0],
            "issues": [{"field": "invented", "reason": "undeclared_field"}],
        }
    ]


def test_conflicting_row_cells_are_quarantined_not_auto_selected():
    result, values = candidate(), source()
    result.rows[0].cells.append(Cell(field="price", value="200", evidence="200 USD"))
    schema_issues, rejected = {}, []
    fixed, effective, _ = prepare_extraction(result, values, schema_issues=schema_issues)
    records, _ = validate_extraction(
        fixed,
        effective,
        [{"url": values.urls[0], "text": values.page_text}],
        rejected=rejected,
        schema_issues=schema_issues,
    )
    assert [record["price"] for record in records] == ["250"]
    assert rejected[0]["issues"] == [{"field": "price", "reason": "conflicting_duplicate_field"}]


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_review_keeps_source_verified_rows_when_one_row_has_extra_field(
    tmp_path, monkeypatch, framework
):
    result = candidate()
    result.rows[0].cells.append(Cell(field="invented", value="x", evidence="x"))
    monkeypatch.setattr(custom_service, "interpret", lambda *a: (result, {"model": "fixture"}))
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        job = finished(service, custom_service.plan(service, source(framework=framework), object()))
        assert job["status"] == "awaiting_review"
        proposal = job["result"]["proposal"]
        assert proposal["partial"] is True
        assert [record["price"] for record in proposal["records"]] == ["250"]
        assert proposal["rejected_records"][0]["issues"][0]["reason"] == "undeclared_field"
    finally:
        service.close()


def test_no_query_removes_invented_filters_and_rules():
    result = candidate()
    result.query_rules = [preferred()]
    fixed, values, notes = prepare_extraction(result, source(instructions=""))
    assert fixed.filters == [] and fixed.query_rules == [] and notes
    rows, excluded = validate_extraction(
        fixed, values, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert len(rows) == 3 and excluded == 0


def test_rule_must_have_support_in_query_not_source_text():
    result = candidate()
    result.query_rules = [preferred()]
    with pytest.raises(WebsiteError, match="not supported by the user query"):
        prepare_extraction(result, source(instructions="Extract all hotels"))


@pytest.mark.parametrize(
    "value,outcome", [("150", "matched"), ("180", "not_matched"), (None, "unknown")]
)
def test_query_rules_are_computed_without_inventing_missing_values(value, outcome):
    assert rule_outcome({"price": value}, preferred()) == outcome
    assert apply_query_rules([{"price": value}], [preferred()])[0]["rule_preferred"] == outcome


def test_rule_any_all_with_missing_values():
    rule = preferred()
    rule.conditions.append(Condition(field="rating", operator="gte", value="4"))
    assert rule_outcome({"price": "150", "rating": None}, rule) == "unknown"
    rule.combination = "any"
    assert rule_outcome({"price": "150", "rating": None}, rule) == "matched"
    assert rule_outcome({"price": "200", "rating": None}, rule) == "unknown"


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_query_rule_flags_saved_and_only_matching_ids_published(tmp_path, monkeypatch, framework):
    result = candidate()
    result.query_rules = [preferred()]
    monkeypatch.setattr(custom_service, "interpret", lambda *a: (result, {"model": "fixture"}))
    events = []

    async def fake_publish(service, event):
        events.append(event)
        return {"published": 1, "broker_acknowledged": True, "consumer_receipt_verified": False}

    monkeypatch.setattr(custom_service, "publish_summary", fake_publish)
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        values = source(
            framework=framework,
            instructions="Hotels 150-250 USD; flag below 180",
            publish_event=True,
        )
        job = finished(service, custom_service.plan(service, values, object()))
        preview = job["result"]["proposal"]
        assert [r["rule_preferred"] for r in preview["records"]] == ["matched", "not_matched"]
        saved = finished(
            service, custom_service.execute(service, preview["plan_id"], job["result"]["revision"])
        )
        assert saved["status"] == "completed"
        records = service.records(saved["job_id"])
        assert "rule_preferred" in records["columns"]
        assert len(records["records"]) == 2
        assert records["records"][0]["rule_preferred"] == "matched"
        assert saved["result"]["evaluation"]["matched"] == 1
        assert events[0]["record_ids"] == [records["records"][0]["listing_id"]]
    finally:
        service.close()
