"""Focused regression fixtures for the reported article capture and topic query."""

from pathlib import Path

import pytest
from test_custom_website import source
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import (
    Cell,
    Column,
    Extraction,
    prepare_extraction,
    source_quote,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.custom_service import capture_summary
from agentic_web_demo.dashboard.service import DashboardService

ARTICLE_TEXT = (
    "Local Football Team Wins Its Season Opener. "
    "How China's Leader Plans to Win the Future With A.I. "
    "Scientists Discover a New Material for Solar Panels. "
    "Research reveals a breakthrough in energy storage."
)
QUERY = "get the articles or headlines related to new technology or research"


def article_candidate():
    titles = [
        ("How China's Leader Plans to Win the Future With A.I.", "relevant"),
        ("Local Football Team Wins Its Season Opener", "not_relevant"),
        ("Scientists Discover a New Material for Solar Panels", "relevant"),
    ]
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review article headlines",
            "content_type": "articles",
            "interpretation": "Technology or research headlines",
            "columns": [
                {"name": "article_title", "description": "Headline", "kind": "text", "unit": ""}
            ],
            "filters": [],
            "query_rules": [],
            "semantic_selection": {
                "request_quote": "related to new technology or research",
                "topic": "new technology or research",
            },
            "rows": [
                {
                    "page_index": 0,
                    "cells": [{"field": "article_title", "value": title, "evidence": f'"{title}"'}],
                    "relevance": relevance,
                    "relevance_reason": "Research or technology context"
                    if relevance == "relevant"
                    else "No research topic in captured headline",
                    "relevance_evidence": f'"{title}"',
                }
                for title, relevance in titles
            ],
            "warnings": [],
            "more_records_available": False,
        }
    )


def test_only_display_quote_wrapper_is_removed():
    headline = "How China's Leader Plans to Win the Future With A.I."
    assert source_quote(f'"{headline}"', ARTICLE_TEXT) == headline
    assert source_quote(f"“{headline}”", ARTICLE_TEXT) == headline
    assert source_quote('"Invented headline"', ARTICLE_TEXT) is None
    assert source_quote('"Scientists Discover a New Material"', ARTICLE_TEXT) == (
        "Scientists Discover a New Material"
    )


def test_semantic_topic_selects_meaning_and_preserves_evidence():
    values = source(instructions=QUERY, page_text=ARTICLE_TEXT)
    candidate, effective, _ = prepare_extraction(article_candidate(), values)
    rejected = []
    records, excluded = validate_extraction(
        candidate,
        effective,
        [{"url": values.urls[0], "text": ARTICLE_TEXT}],
        rejected=rejected,
    )
    assert len(records) == 2 and excluded == 1 and not rejected
    assert all(r["topic_relevance"] == "relevant" for r in records)
    assert records[0]["evidence"]["article_title"] == (
        "How China's Leader Plans to Win the Future With A.I."
    )
    assert records[1]["article_title"].startswith("Scientists Discover")


def test_repeated_relevance_cell_does_not_discard_article_rows():
    candidate = article_candidate()
    for row in candidate.rows:
        row.cells.append(
            Cell(
                field="relevance",
                value=row.relevance,
                evidence=row.cells[0].evidence,
            )
        )
    values = source(instructions=QUERY, page_text=ARTICLE_TEXT)
    candidate, effective, notes = prepare_extraction(candidate, values)
    rejected = []
    records, excluded = validate_extraction(
        candidate,
        effective,
        [{"url": values.urls[0], "text": ARTICLE_TEXT}],
        rejected=rejected,
    )
    assert len(records) == 2 and excluded == 1 and not rejected
    assert any("repeated relevance cell" in note for note in notes)
    assert all("relevance" not in row for row in records)


def test_conflicting_relevance_cell_still_rejects_record():
    candidate = article_candidate()
    candidate.rows[0].cells.append(
        Cell(field="relevance", value="not_relevant", evidence="Local Football Team")
    )
    values = source(instructions=QUERY, page_text=ARTICLE_TEXT)
    schema_issues = {}
    candidate, effective, _ = prepare_extraction(
        candidate, values, schema_issues=schema_issues
    )
    rejected = []
    records, _ = validate_extraction(
        candidate,
        effective,
        [{"url": values.urls[0], "text": ARTICLE_TEXT}],
        rejected=rejected,
        schema_issues=schema_issues,
    )
    assert len(records) == 1
    assert rejected[0]["issues"][0]["reason"] == "conflicting_relevance_classification"


def test_capture_summary_reports_article_coverage_without_body_text():
    pages = [
        {
            "url": "https://example.org/article?private=1",
            "text": "Headline and body text",
            "blocks": [
                {"kind": "heading", "text": "Headline"},
                {"kind": "paragraph", "text": "Body text"},
            ],
            "truncated": False,
        }
    ]
    summary = capture_summary(pages)
    assert summary == [
        {
            "source_url": "https://example.org/article",
            "visible_text_chars": len(pages[0]["text"]),
            "blocks": 2,
            "paragraph_blocks": 1,
            "truncated": False,
        }
    ]


def test_missing_topic_classification_cannot_leak_unfiltered_records():
    result = article_candidate()
    result.semantic_selection = None
    with pytest.raises(WebsiteError, match="omitted the requested topic"):
        prepare_extraction(result, source(instructions=QUERY, page_text=ARTICLE_TEXT))
    result = article_candidate()
    result.rows[0].relevance = None
    values = source(instructions=QUERY, page_text=ARTICLE_TEXT)
    result, effective, _ = prepare_extraction(result, values)
    rejected = []
    records, _ = validate_extraction(
        result, effective, [{"url": values.urls[0], "text": ARTICLE_TEXT}], rejected=rejected
    )
    assert len(records) == 1 and rejected[0]["issues"][0]["reason"] == (
        "missing_relevance_classification"
    )


def test_unrelated_or_unsupported_quotes_are_rejected():
    result = article_candidate()
    result.rows[0].relevance_evidence = '"A made-up technology story"'
    values = source(instructions=QUERY, page_text=ARTICLE_TEXT)
    result, effective, _ = prepare_extraction(result, values)
    rejected = []
    records, _ = validate_extraction(
        result, effective, [{"url": values.urls[0], "text": ARTICLE_TEXT}], rejected=rejected
    )
    assert len(records) == 1 and rejected[0]["issues"][0]["reason"] == "missing_source_support"


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_topic_preview_and_download_snapshot_for_both_frameworks(tmp_path, monkeypatch, framework):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    monkeypatch.setattr(
        custom_service, "interpret", lambda *args: (article_candidate(), {"model": "fixture"})
    )
    try:
        values = source(framework=framework, instructions=QUERY, page_text=ARTICLE_TEXT)
        job = finished(service, custom_service.plan(service, values, object()))
        assert job["status"] == "awaiting_review", job
        proposal = job["result"]["proposal"]
        assert len(proposal["records"]) == 2
        assert proposal["semantic_selection"]["topic"] == "new technology or research"
        assert proposal["excluded_by_filters"] == 1
        execution = finished(
            service, custom_service.execute(service, proposal["plan_id"], job["result"]["revision"])
        )
        assert execution["status"] == "completed", execution
        snapshot = service.records(execution["job_id"])
        assert len(snapshot["records"]) == 2
        assert "topic_relevance" in snapshot["columns"]
        assert snapshot["semantic_selection"]["topic"] == "new technology or research"
    finally:
        service.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_optional_topic_tags_do_not_erase_verified_articles(tmp_path, monkeypatch, framework):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    result = article_candidate()
    result.columns.append(
        Column(name="topic_tags", description="Related topics", kind="text", unit="")
    )
    for row in result.rows:
        row.cells.append(
            Cell(
                field="topic_tags",
                value="Research; Technology" if row.relevance == "relevant" else None,
                evidence='"Related topics" ... "Research" ... "Technology"'
                if row.relevance == "relevant"
                else "",
            )
        )
    monkeypatch.setattr(custom_service, "interpret", lambda *args: (result, {"model": "fixture"}))
    try:
        values = source(framework=framework, instructions=QUERY, page_text=ARTICLE_TEXT)
        job = finished(service, custom_service.plan(service, values, object()))
        assert job["status"] == "awaiting_review", job
        proposal = job["result"]["proposal"]
        assert proposal["partial"] and len(proposal["records"]) == 2
        assert len(proposal["field_issues"]) == 2 and not proposal["rejected_records"]
        assert all(record["topic_tags"] is None for record in proposal["records"])
        execution = finished(
            service,
            custom_service.execute(
                service, proposal["plan_id"], job["result"]["revision"], accept_partial=True
            ),
        )
        snapshot = service.records(execution["job_id"])
        assert len(snapshot["records"]) == 2
        assert len(snapshot["field_issues"]) == 2
    finally:
        service.close()
