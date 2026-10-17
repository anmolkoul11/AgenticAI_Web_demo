"""Source-only fixtures for inferred schemas, explicit nulls and bounded evidence."""

import pytest

from agentic_web_demo.custom_extract import (
    INSTRUCTIONS,
    Cell,
    Column,
    Extraction,
    WebsiteInput,
    prepare_extraction,
    validate_extraction,
    value_supported,
)
from agentic_web_demo.custom_service import output_field_statuses


def inputs(**changes):
    return WebsiteInput(**{
        "source": "paste", "urls": ["https://example.org/records"],
        "page_text": "Visible source content retained for the selected records. " * 3,
        "authorized": True, "allow_model_api": True,
        "instructions": "Get the available records", **changes,
    })


def candidate(fields, rows, *, kind="records", requested=(), numeric=()):
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": kind,
        "interpretation": "Useful available source fields",
        "requested_fields": list(requested),
        "columns": [
            {"name": name, "kind": "number" if name in numeric else "text",
             "unit": "", "description": name}
            for name in fields
        ],
        "filters": [], "warnings": [], "more_records_available": False,
        "rows": [
            {"page_index": 0, "cells": [
                {"field": name, "value": row.get(name), "evidence": row.get(name) or ""}
                for name in fields
            ]}
            for row in rows
        ],
    })


@pytest.mark.parametrize("kind,fields", [
    ("articles", ["title", "url", "teaser"]),
    ("hotels", ["name", "room_description", "cancellation"]),
    ("products", ["name", "sku", "description", "warranty"]),
])
def test_inferred_schema_remains_domain_dynamic_without_template_padding(kind, fields):
    raw = candidate(fields, [{fields[0]: "Source record"}], kind=kind)
    fixed, _, _ = prepare_extraction(raw, inputs())
    assert [column.name for column in fixed.columns] == fields
    assert fixed._explicit_output_fields == set()
    assert fixed._contract_added_fields == set()
    assert "article_excerpt" not in {column.name for column in fixed.columns}


def test_explicit_missing_fields_are_kept_null_with_a_reason_not_optional_inference():
    raw = candidate(["name"], [{"name": "North Hotel"}], requested=["capacity"])
    fixed, values, _ = prepare_extraction(raw, inputs(instructions="Include name and capacity"))
    assert fixed._explicit_output_fields == {"capacity"}
    assert fixed._contract_added_fields == {"capacity"}
    assert [column.name for column in fixed.columns] == ["capacity", "name"]
    rows, _ = validate_extraction(fixed, values, [{
        "url": values.urls[0], "text": "North Hotel has an available room listing."
    }])
    assert rows[0]["name"] == "North Hotel"
    assert rows[0]["capacity"] is None
    report = output_field_statuses(rows, fixed.columns, {"name"}, [])[0]
    assert report["fields"]["capacity"]["status"] == "model_not_returned"


def test_pinned_generic_fields_are_explicit_without_needing_a_genre_template():
    raw = candidate(["name"], [{"name": "Handmade lamp"}], kind="products")
    fixed, _, _ = prepare_extraction(raw, inputs(output_fields=["name", "material"]))
    assert fixed._explicit_output_fields == {"name", "material"}
    assert [column.name for column in fixed.columns] == ["name", "material"]
    assert fixed.rows[0].cells[1].value is None


def test_partially_populated_inferred_field_is_not_relabelled_as_explicit():
    raw = candidate(
        ["name", "description"],
        [{"name": "Lamp", "description": "Solid brass"}, {"name": "Chair"}],
        kind="products",
    )
    fixed, values, _ = prepare_extraction(raw, inputs())
    rows, _ = validate_extraction(fixed, values, [{
        "url": values.urls[0], "text": "Lamp Solid brass Chair"
    }])
    assert [row["description"] for row in rows] == ["Solid brass", None]
    assert "description" not in fixed._explicit_output_fields


@pytest.mark.parametrize("field,value,quote", [
    ("location_rating", "9.4", "Location9.4"),
    ("review_count", "14058", "score14,058 reviews"),
    ("review_count", "14058", "score14,058reviews"),
    ("guest_score", "4.8", "Score4.8"),
    ("price", "300", "Price300USD"),
    ("nightly_price", "300", "USD300 per night"),
    ("price", "300", "300pernight"),
    ("room_count", "2", "Rooms2"),
])
def test_legacy_fused_numeric_labels_use_bounded_semantic_tokens(field, value, quote):
    assert value_supported(
        Cell(field=field, value=value, evidence=quote),
        Column(name=field, kind="number", unit="", description=field),
    )


@pytest.mark.parametrize("field,value,quote", [
    ("rating", "4", "rating4.8"),
    ("rating", "4", "score40"),
    ("price", "31", "Hotel31"),
    ("price", "31", "Hotel31USD"),
    ("price", "100", "X100"),
    ("rating", "14058", "score14,058 reviews"),
    ("guest_rating", "9.4", "Location9.4"),
    ("price", "4", "Price4,000USD"),
    ("price", "300", "Price300.50USD"),
])
def test_numeric_recovery_does_not_turn_names_partial_numbers_or_subscores_into_prices(
    field, value, quote
):
    assert not value_supported(
        Cell(field=field, value=value, evidence=quote),
        Column(name=field, kind="number", unit="", description=field),
    )


def test_hotel_description_named_article_snippet_is_not_rejected_as_news_teaser():
    raw = candidate(
        ["name", "article_snippet"],
        [{"name": "North Hotel", "article_snippet": "Two queen beds and city views"}],
        kind="hotels",
    )
    fixed, values, _ = prepare_extraction(raw, inputs())
    text = "North Hotel\nTwo queen beds and city views"
    blocks = [
        {"id": "b1", "kind": "heading", "text": "North Hotel", "group_id": "g1"},
        {"id": "b2", "kind": "text", "text": "Two queen beds and city views", "group_id": "g1"},
    ]
    issues = []
    rows, _ = validate_extraction(
        fixed, values, [{"url": values.urls[0], "text": text, "blocks": blocks}],
        rejected=[], field_issues=issues,
    )
    assert rows[0]["article_snippet"] == "Two queen beds and city views"
    assert not issues


@pytest.mark.parametrize("field", [
    "article_excerpt", "body_excerpt", "body_text", "article_body", "full_text", "full_content",
])
def test_generic_article_body_aliases_cannot_relabel_index_teasers(field):
    raw = candidate(
        ["name", field], [{"name": "World headline", field: "Visible index teaser"}],
        kind="news_articles",
    )
    fixed, values, _ = prepare_extraction(raw, inputs())
    page = {
        "url": values.urls[0], "source_kind": "index",
        "text": "World headline\nVisible index teaser",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "World headline", "group_id": "g1"},
            {"id": "b2", "kind": "paragraph", "text": "Visible index teaser",
             "content_role": "body", "group_id": "g1"},
        ],
    }
    issues = []
    rows, _ = validate_extraction(fixed, values, [page], rejected=[], field_issues=issues)
    assert rows[0][field] is None
    assert issues[0]["issues"][0]["reason"] == "detail_body_not_captured"


def test_generic_hotel_description_keeps_source_text_without_article_body_restrictions():
    raw = candidate(
        ["name", "description"], [{"name": "North Hotel", "description": "City views"}],
        kind="hotels",
    )
    fixed, values, _ = prepare_extraction(raw, inputs())
    page = {
        "url": values.urls[0], "source_kind": "index", "text": "North Hotel\nCity views",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "North Hotel", "group_id": "g1"},
            {"id": "b2", "kind": "text", "text": "City views", "group_id": "g1"},
        ],
    }
    rows, _ = validate_extraction(fixed, values, [page], rejected=[], field_issues=[])
    assert rows[0]["description"] == "City views"


def test_generic_news_name_still_means_the_actual_headline_not_a_body_quote():
    raw = candidate(["name"], [{"name": "A sentence quoted from the body"}], kind="news")
    fixed, values, _ = prepare_extraction(raw, inputs())
    page = {
        "url": values.urls[0], "source_kind": "index",
        "text": "The actual headline\nA sentence quoted from the body",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "The actual headline", "group_id": "g1"},
            {"id": "b2", "kind": "paragraph", "text": "A sentence quoted from the body",
             "group_id": "g1"},
        ],
    }
    rejected = []
    rows, _ = validate_extraction(fixed, values, [page], rejected=rejected, field_issues=[])
    assert rows == []
    assert rejected[0]["issues"][0]["reason"] == "title_not_supported_by_heading_or_link"


def feature_fixture(*, other_group=False, fragmented=True):
    raw = candidate(
        ["name", "amenities"], [{"name": "North Hotel", "amenities": "Free WiFi; Pool"}],
        kind="hotels",
    )
    raw.rows[0].cells[1].evidence = (
        '"Free WiFi" ... "Pool"' if fragmented else "Free WiFi Pool"
    )
    fixed, values, _ = prepare_extraction(raw, inputs())
    page = {
        "url": values.urls[0], "text": "North Hotel\nFree WiFi\nPool",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "North Hotel", "group_id": "g1"},
            {"id": "b2", "kind": "text", "text": "Free WiFi", "group_id": "g1"},
            {"id": "b3", "kind": "text", "text": "Pool",
             "group_id": "g2" if other_group else "g1"},
        ],
    }
    return fixed, values, page


def test_amenity_fragments_are_repaired_only_to_an_actual_same_record_source_span():
    fixed, values, page = feature_fixture()
    repairs = []
    rows, _ = validate_extraction(
        fixed, values, [page], rejected=[], field_issues=[], field_repairs=repairs
    )
    assert rows[0]["amenities"] == "Free WiFi; Pool"
    assert rows[0]["evidence"]["amenities"] == "Free WiFi Pool"
    assert repairs[0]["issues"][0]["reason"] == "fragment_evidence_replaced_by_captured_group_span"


@pytest.mark.parametrize("fragmented", [False, True])
def test_amenity_values_cannot_borrow_another_records_features(fragmented):
    fixed, values, page = feature_fixture(other_group=True, fragmented=fragmented)
    issues = []
    rows, _ = validate_extraction(
        fixed, values, [page], rejected=[], field_issues=issues, field_repairs=[]
    )
    assert rows[0]["amenities"] is None
    assert issues


def test_prompt_preserves_topic_qualifiers_and_explicit_vs_inferred_fields():
    assert "'world politics' means international affairs/geopolitics" in INSTRUCTIONS
    assert "A domestic election" in INSTRUCTIONS
    assert "not every field inferred as useful" in INSTRUCTIONS
    assert "there is no fixed" in INSTRUCTIONS
