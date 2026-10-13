"""Topic review regressions: local fixtures only, no website, model or browser calls."""

from pathlib import Path

import pytest
from test_custom_website import source
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import (
    Condition,
    Extraction,
    prepare_extraction,
    validate_extraction,
)
from agentic_web_demo.dashboard.service import DashboardService
from agentic_web_demo.enrichment import record_target
from agentic_web_demo.record_identity import identity_field

QUERY = "find articles related to Soccer"
TITLE = "Soccer club wins the cup final"
OTHER = "Cooking show announces a new season"
UNCERTAIN = "The latest updates from the weekend"
TEXT = f"{TITLE}. {OTHER}. {UNCERTAIN}. More page content and source headlines."


def candidate(labels=("relevant", "not_relevant", "uncertain"), *, title_field="article_headline"):
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Soccer headlines in the captured page",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": "article_type", "kind": "text", "unit": "", "description": "Type"},
                {"name": title_field, "kind": "text", "unit": "", "description": "Headline"},
            ],
            "filters": [],
            "query_rules": [],
            "semantic_selection": {"request_quote": "related to Soccer", "topic": "Soccer"},
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": "article_type", "value": "link", "evidence": title},
                        {"field": title_field, "value": title, "evidence": title},
                    ],
                    "relevance": label,
                    "relevance_reason": "Topic assessment for this headline",
                    "relevance_evidence": title,
                }
                for title, label in zip((TITLE, OTHER, UNCERTAIN), labels, strict=True)
            ],
        }
    )


def validated(result):
    values = source(instructions=QUERY, page_text=TEXT)
    schema_issues = {}
    result, effective, _ = prepare_extraction(result, values, schema_issues=schema_issues)
    rejected, fields, counts = [], [], {}
    rows, excluded = validate_extraction(
        result,
        effective,
        [{"url": values.urls[0], "text": TEXT}],
        rejected=rejected,
        field_issues=fields,
        schema_issues=schema_issues,
        review_counts=counts,
    )
    return rows, excluded, rejected, fields, counts


def test_unrelated_rows_are_excluded_before_unused_optional_value_checks():
    rows, excluded, rejected, fields, counts = validated(candidate())
    assert len(rows) == 1 and excluded == 1
    assert rows[0]["article_headline"] == TITLE and rows[0]["article_type"] is None
    assert fields[0]["issues"][0]["reason"] == "value_missing_from_quote"
    assert len(rejected) == 1
    assert rejected[0]["issues"][0]["reason"] == "uncertain_relevance"
    assert counts == {
        "candidates": 3,
        "matched": 1,
        "unrelated": 1,
        "uncertain": 1,
        "invalid": 0,
        "filtered_out": 0,
        "duplicates": 0,
        "optional_fields_cleared": 1,
    }


def test_twenty_unrelated_rows_do_not_become_twenty_validation_failures():
    result = candidate(("not_relevant",) * 3)
    result.rows = [result.rows[index % 3].model_copy(deep=True) for index in range(20)]
    rows, excluded, rejected, fields, counts = validated(result)
    assert not rows and not rejected and not fields
    assert excluded == counts["unrelated"] == 20
    assert counts["invalid"] == counts["uncertain"] == 0


@pytest.mark.parametrize(
    "name", ["article_headline", "listing_title", "property_name", "product_name"]
)
def test_optional_type_column_is_not_selected_as_identity(name):
    assert identity_field(["article_type", name]) == name
    assert identity_field(["price"]) == "price"


def test_detail_link_lookup_uses_the_same_headline_alias_as_validation():
    url = "https://example.org/soccer-final"
    page = {
        "blocks": [
            {"text": TITLE, "group_id": "story-1", "href": url},
            {"text": OTHER, "group_id": "story-2", "href": "https://example.org/cooking"},
        ]
    }
    row = {
        "article_type": None,
        "article_headline": TITLE,
        "evidence": {"article_type": "", "article_headline": TITLE},
    }
    assert record_target(row, page, ["article_type", "article_headline"]) == url


def test_bad_identity_still_rejects_a_relevant_record():
    result = candidate(("relevant", "not_relevant", "not_relevant"))
    result.rows[0].cells[1].value = "Invented Soccer headline"
    rows, _, rejected, _, counts = validated(result)
    assert not rows and counts["invalid"] == 1
    assert any(issue["field"] == "article_headline" for issue in rejected[0]["issues"])


def test_missing_identity_cannot_be_repaired_as_optional_metadata():
    result = candidate(("relevant", "not_relevant", "not_relevant"))
    result.rows[0].cells[1].value = None
    rows, _, rejected, _, counts = validated(result)
    assert not rows and counts["invalid"] == 1
    assert any(issue["reason"] == "missing_record_identity" for issue in rejected[0]["issues"])


def test_optional_type_used_in_an_explicit_filter_still_requires_evidence():
    result = candidate(("relevant", "not_relevant", "not_relevant"))
    result.filters = [Condition(field="article_type", operator="eq", value="link")]
    rows, _, rejected, _, counts = validated(result)
    assert not rows and counts["invalid"] == 1
    assert rejected[0]["issues"][0]["field"] == "article_type"


def test_missing_topic_classification_still_rejects_instead_of_returning_unfiltered_data():
    result = candidate((None, "not_relevant", "not_relevant"))
    rows, _, rejected, _, counts = validated(result)
    assert not rows and counts["invalid"] == 1
    assert any(
        issue["reason"] == "missing_relevance_classification" for issue in rejected[0]["issues"]
    )


def test_schema_conflict_is_not_hidden_by_an_unrelated_label():
    result = candidate(("not_relevant",) * 3)
    result.rows[0].cells.append(result.rows[0].cells[1].model_copy(update={"value": "Conflict"}))
    rows, excluded, rejected, _, counts = validated(result)
    assert not rows and excluded == 2 and counts["invalid"] == 1
    assert rejected[0]["issues"][0]["reason"] == "conflicting_duplicate_field"


def test_general_hotel_range_still_uses_source_prices_without_a_fixed_ceiling():
    text = (
        "North Stay costs 250 USD per night. South Stay costs 350 USD per night. "
        "Prices shown include taxes for this fixture."
    )
    values = source(instructions="Hotels from 200 to 300 USD", page_text=text)
    result = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "hotels",
            "interpretation": "Hotel price range",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": "record_type", "description": "Type", "kind": "text", "unit": ""},
                {"name": "property_name", "description": "Name", "kind": "text", "unit": ""},
                {"name": "price", "description": "Nightly price", "kind": "number", "unit": "USD"},
            ],
            "filters": [
                {"field": "price", "operator": "gte", "value": "200"},
                {"field": "price", "operator": "lte", "value": "300"},
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": "record_type", "value": "listing", "evidence": name},
                        {"field": "property_name", "value": name, "evidence": name},
                        {"field": "price", "value": price, "evidence": price + " USD"},
                    ],
                }
                for name, price in [("North Stay", "250"), ("South Stay", "350")]
            ],
        }
    )
    result, effective, _ = prepare_extraction(result, values)
    rejected, fields, counts = [], [], {}
    rows, excluded = validate_extraction(
        result,
        effective,
        [{"url": values.urls[0], "text": text}],
        rejected=rejected,
        field_issues=fields,
        review_counts=counts,
    )
    assert len(rows) == 1 and rows[0]["price"] == "250" and excluded == 1
    assert rows[0]["record_type"] is None and not rejected
    assert counts["filtered_out"] == 1 and counts["unrelated"] == 0


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
@pytest.mark.parametrize(
    "labels,outcome",
    [
        (("not_relevant",) * 3, "no_matches"),
        (("uncertain", "not_relevant", "not_relevant"), "needs_attention"),
    ],
)
def test_no_preview_distinguishes_no_matches_from_uncertain_content(
    tmp_path,
    monkeypatch,
    framework,
    labels,
    outcome,
):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    monkeypatch.setattr(
        custom_service, "interpret", lambda *_: (candidate(labels), {"model": "fixture"})
    )
    try:
        values = source(framework=framework, instructions=QUERY, page_text=TEXT)
        job = finished(service, custom_service.plan(service, values, object()))
        result = job["result"]
        assert job["status"] == "needs_input" and result["review_outcome"] == outcome
        assert "proposal" not in result and result["review_counts"]["invalid"] == 0
        assert result["next_step"] == "open_browser_for_links" and result["request"] == QUERY
        if outcome == "no_matches":
            assert "No Soccer matches" in result["guidance"]
            assert "Find relevant links" in result["guidance"]
            assert not result["rejected_records"]
        else:
            assert "uncertain topic relevance" in result["guidance"]
        assert not list(tmp_path.glob("website-plans/*.json"))
        assert not list(tmp_path.glob("exports/*.json"))
    finally:
        service.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_verified_soccer_preview_and_saved_counts_with_optional_type_cleared(
    tmp_path,
    monkeypatch,
    framework,
):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(), {"model": "fixture"}))
    try:
        values = source(framework=framework, instructions=QUERY, page_text=TEXT)
        job = finished(service, custom_service.plan(service, values, object()))
        assert job["status"] == "awaiting_review", job
        result, proposal = job["result"], job["result"]["proposal"]
        assert proposal["review_counts"]["matched"] == 1
        assert proposal["records"][0]["article_type"] is None and proposal["partial"]
        execution = finished(
            service,
            custom_service.execute(
                service,
                proposal["plan_id"],
                result["revision"],
                accept_partial=True,
            ),
        )
        assert execution["status"] == "completed", execution
        snapshot = service.records(execution["job_id"])
        assert snapshot["review_counts"] == proposal["review_counts"]
        assert len(snapshot["records"]) == 1
        assert snapshot["records"][0]["article_type"] is None
    finally:
        service.close()
