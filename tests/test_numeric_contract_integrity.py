"""Source-only regressions: schema correction is not permission to invent a value."""

import pytest

from agentic_web_demo.custom_extract import (
    Column,
    Extraction,
    WebsiteInput,
    prepare_extraction,
    validate_extraction,
)


def extraction(field="price", value="3140", quote="Price $3,140", *, filters=()):
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": "records",
        "interpretation": "Captured records", "warnings": [],
        "more_records_available": False, "filters": list(filters),
        "columns": [
            {"name": name, "kind": "text", "unit": "", "description": name}
            for name in ("name", field)
        ],
        "rows": [{"page_index": 0, "cells": [
            {"field": "name", "value": "Source record", "evidence": "Source record"},
            {"field": field, "value": value, "evidence": quote},
        ]}],
    })


def inputs(instructions="Find records with price around 250-350 USD", **changes):
    return WebsiteInput(
        source="paste", urls=["https://example.org/results"],
        page_text="Captured source records with their displayed details. " * 3,
        instructions=instructions, authorized=True, allow_model_api=True, **changes,
    )


def page(quote, *, other_group=False):
    return {
        "url": "https://example.org/results", "text": "Source record\n" + quote,
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "Source record", "group_id": "g1"},
            {"id": "b2", "kind": "text", "text": quote,
             "group_id": "g2" if other_group else "g1"},
        ],
    }


@pytest.mark.parametrize("field", ["price", "displayed_price", "product_cost"])
def test_price_dependency_reconciles_existing_text_alias_without_blank_shadow_column(field):
    raw = extraction(field)
    fixed, values, notes = prepare_extraction(raw, inputs())
    assert next(column for column in fixed.columns if column.name == field).kind == "number"
    if field != "price":
        assert not any(column.name == "price" for column in fixed.columns)
    issues = []
    rows, _ = validate_extraction(
        fixed, values, [page("Price $3,140")], rejected=[], field_issues=issues,
    )
    assert rows[0][field] == "3140"
    assert rows[0]["evidence"][field] == "Price $3,140"
    assert not issues
    assert any("typed as numbers" in note for note in notes)
    assert raw.columns[1].kind == "text"  # no mutation of raw model output


def test_price_qualifications_are_not_competing_amount_aliases():
    raw = extraction("displayed_price")
    for name in ("price_basis", "price_currency", "price_context", "price_id"):
        raw.columns.append(Column(name=name, kind="text", unit="", description=name))
    fixed, _, _ = prepare_extraction(raw, inputs())
    kinds = {column.name: column.kind for column in fixed.columns}
    assert kinds["displayed_price"] == "number"
    assert "price" not in kinds
    assert all(kinds[name] == "text" for name in (
        "price_basis", "price_currency", "price_context", "price_id"
    ))


def test_approximate_filters_are_removed_after_numeric_schema_is_reconciled():
    raw = extraction(filters=[
        {"field": "price", "operator": "gte", "value": "250"},
        {"field": "price", "operator": "lte", "value": "350"},
    ])
    fixed, _, _ = prepare_extraction(raw, inputs())
    assert fixed.filters == []
    assert fixed.columns[1].kind == "number"


@pytest.mark.parametrize("field,kind", [("stock_count", "products"), ("capacity", "venues")])
def test_numeric_comparisons_reconcile_fields_across_domains(field, kind):
    raw = extraction(field, "1234", "Available 1,234 units", filters=[
        {"field": field, "operator": "gte", "value": "1000"},
    ])
    raw.content_type = kind
    fixed, values, _ = prepare_extraction(raw, inputs("Get source records with at least 1000 units"))
    rows, _ = validate_extraction(fixed, values, [page("Available 1,234 units")])
    assert rows[0][field] == "1234"
    assert rows[0]["evidence"][field] == "Available 1,234 units"


def test_grouped_numeric_model_value_is_normalized_but_literal_quote_is_retained():
    fixed, values, _ = prepare_extraction(extraction(value="3,140"), inputs())
    repairs = []
    rows, _ = validate_extraction(fixed, values, [page("Price $3,140")], field_repairs=repairs)
    assert rows[0]["price"] == "3140"
    assert rows[0]["evidence"]["price"] == "Price $3,140"
    assert repairs[0]["issues"][0]["reason"] == "numeric_display_format_normalized"
    assert repairs[0]["issues"][0]["old_value"] == "3,140"


@pytest.mark.parametrize("value,quote", [
    ("314", "Price $3,140"), ("3140", "Price $3,140.50"),
    ("3,14", "Price $314"), ("3140", "Price $4,140"),
])
def test_type_correction_never_approves_wrong_partial_or_malformed_numbers(value, quote):
    fixed, values, _ = prepare_extraction(extraction(value=value, quote=quote), inputs())
    issues = []
    rows, _ = validate_extraction(fixed, values, [page(quote)], rejected=[], field_issues=issues)
    assert rows[0]["price"] is None
    assert issues[0]["issues"][0]["field"] == "price"


def test_numeric_format_equivalence_cannot_borrow_another_record_price():
    fixed, values, _ = prepare_extraction(extraction(), inputs())
    issues = []
    rows, _ = validate_extraction(
        fixed, values, [page("Price $3,140", other_group=True)], rejected=[], field_issues=issues,
    )
    assert rows[0]["price"] is None
    assert any(issue["reason"] == "values_from_different_source_groups"
               for issue in issues[0]["issues"])


def test_identifier_and_range_text_are_not_retyped_without_numeric_request_semantics():
    raw = extraction("sku", "003140", "SKU 003140")
    fixed, _, _ = prepare_extraction(raw, inputs("Get names and identifiers"))
    assert fixed.columns[1].kind == "text"
    assert fixed.rows[0].cells[1].value == "003140"
    raw = extraction("price_range", "250-350 USD", "250-350 USD")
    fixed, _, _ = prepare_extraction(raw, inputs("Get all visible price descriptions"))
    assert fixed.columns[1].kind == "text"
