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
from agentic_web_demo.source_fields import article_record_issue

ARTICLE_TEXT = (
    "Local Football Team Wins Its Season Opener. "
    "How China's Leader Plans to Win the Future With A.I. "
    "Scientists Discover a New Material for Solar Panels. "
    "Research reveals a breakthrough in energy storage."
)
QUERY = "get the articles or headlines related to new technology or research"


def test_explicit_primary_headline_is_not_navigation_without_a_record_group():
    from agentic_web_demo.source_fields import article_record_issue

    page = {"source_kind": "page", "blocks": [
        {"kind": "heading", "heading_level": 1, "content_role": "headline",
         "association": "page", "text": "Science"}
    ]}
    assert article_record_issue("Science", page) is None
    page["blocks"][0].pop("content_role")
    assert article_record_issue("Science", page) == "non_article_navigation"


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


@pytest.mark.parametrize("source_kind", ["page", "index"])
def test_homepage_cards_keep_verified_headlines_and_clear_inferred_source_type(source_kind):
    entries = [
        ("Local football team wins the season opener", "https://example.org/sports/football"),
        ("Tennis champion wins the final", "https://example.org/sports/tennis"),
    ]
    text = "Latest news\n" + "\n".join(title for title, _ in entries)
    values = source(instructions="Find articles related to sports", page_text=text)
    candidate = Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": "articles",
        "interpretation": "Sports headlines captured on the supplied homepage",
        "columns": [
            {"name": "article_title", "kind": "text", "unit": "", "description": "Headline"},
            {"name": "article_url", "kind": "text", "unit": "", "description": "Captured URL"},
            {"name": "source_type", "kind": "text", "unit": "", "description": "Record type"},
        ],
        "filters": [], "query_rules": [], "warnings": [], "more_records_available": False,
        "semantic_selection": {"request_quote": "related to sports", "topic": "sports"},
        "rows": [
            {"page_index": 0, "relevance": "relevant", "relevance_reason": "A sports headline",
             "relevance_evidence": title, "cells": [
                 {"field": "article_title", "value": title, "evidence": title},
                 {"field": "article_url", "value": url, "evidence": url},
                 {"field": "source_type", "value": "article link", "evidence": title},
             ]} for title, url in entries
        ],
    })
    page = {"url": values.urls[0], "source_kind": source_kind, "text": text, "blocks": [
        {"id": "site-title", "kind": "heading", "heading_level": 1, "text": "Latest news",
         "association": "page"},
        *[{"id": f"h{index}", "kind": "heading", "heading_level": 2, "text": title,
           "href": url, "group_id": f"g{index}", "association": "record"}
          for index, (title, url) in enumerate(entries)],
    ]}
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected, field_issues = [], []
    records, excluded = validate_extraction(
        candidate, effective, [page], rejected=rejected, field_issues=field_issues
    )
    assert excluded == 0 and not rejected
    assert [record["article_title"] for record in records] == [title for title, _ in entries]
    assert [record["article_url"] for record in records] == [url for _, url in entries]
    assert all(record["source_type"] is None for record in records)
    assert len(field_issues) == 2
    assert all(issue["issues"][0]["field"] == "source_type" for issue in field_issues)
    assert all(issue["issues"][0]["reason"] == "value_missing_from_quote" for issue in field_issues)


@pytest.mark.parametrize("source_kind", ["page", "detail"])
@pytest.mark.parametrize("title_source", ["headline", "body", "related"])
def test_explicit_article_headline_role_remains_strict_on_direct_page(source_kind, title_source):
    content = {
        "headline": "Local football team wins the season opener",
        "body": "Players said their season was unforgettable.",
        "related": "Tennis champion wins the final",
    }
    text = "\n".join(content.values())
    values = source(instructions="Get the article headline from this page", page_text=text)
    candidate = Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": "articles",
        "interpretation": "Headline from the supplied article", "filters": [],
        "query_rules": [], "warnings": [], "more_records_available": False,
        "columns": [{"name": "article_title", "kind": "text", "unit": "", "description": "Headline"}],
        "rows": [{"page_index": 0, "cells": [
            {"field": "article_title", "value": content[title_source], "evidence": content[title_source]}
        ]}],
    })
    page = {"url": values.urls[0], "source_kind": source_kind, "text": text, "blocks": [
        {"id": "headline", "kind": "heading", "heading_level": 1, "content_role": "headline",
         "text": content["headline"], "group_id": "article", "association": "record"},
        {"id": "body", "kind": "paragraph", "content_role": "body", "text": content["body"],
         "group_id": "article", "association": "record"},
        {"id": "related", "kind": "heading", "heading_level": 2, "text": content["related"],
         "href": "https://example.org/sports/tennis", "group_id": "related", "association": "record"},
    ]}
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected = []
    records, _ = validate_extraction(candidate, effective, [page], rejected=rejected)
    if title_source == "headline":
        assert len(records) == 1 and not rejected
        assert records[0]["article_title"] == content["headline"]
    else:
        assert not records
        assert rejected[0]["issues"][0]["reason"] == "not_primary_headline"


def article_kind_candidate(entries, *, content_type="articles", headline_field="article_title"):
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": content_type,
        "interpretation": "Captured article records", "filters": [], "query_rules": [],
        "warnings": [], "more_records_available": False,
        "columns": [
            {"name": headline_field, "kind": "text", "unit": "", "description": "Headline"},
            {"name": "article_url", "kind": "text", "unit": "", "description": "Captured URL"},
        ],
        "rows": [{"page_index": 0, "cells": [
            {"field": headline_field, "value": title, "evidence": title or ""},
            {"field": "article_url", "value": url, "evidence": url},
        ]} for title, url in entries],
    })


@pytest.mark.parametrize("source_kind", ["page", "index"])
@pytest.mark.parametrize("content_type", ["articles", "links"])
@pytest.mark.parametrize("block_kind", ["heading", "link"])
def test_article_request_rejects_game_section_and_navigation_cards(source_kind, content_type, block_kind):
    entries = [
        ("A game that changed baseball", "https://example.org/story"),
        ("Game", "https://example.org/sections/baseball"),
        ("Play Connections: Sports Edition", "https://example.org/athletic/connections-sports-edition"),
        ("Sports coverage", "https://example.org/athletic/"),
        ("Sports", "https://example.org/sports"),
    ]
    text = "\n".join(title for title, _ in entries)
    values = source(instructions="Get articles from the captured page", page_text=text)
    candidate = article_kind_candidate(entries, content_type=content_type)
    page = {"url": values.urls[0], "source_kind": source_kind, "text": text, "blocks": [
        {"id": f"h{index}", "kind": block_kind, "heading_level": 2, "text": title,
         "href": url, "group_id": f"g{index}",
         "association": "page" if title == "Sports" else "record"}
        for index, (title, url) in enumerate(entries)
    ]}
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected, field_issues = [], []
    records, excluded = validate_extraction(
        candidate, effective, [page], rejected=rejected, field_issues=field_issues
    )
    assert [record["article_title"] for record in records] == [title for title, _ in entries[:2]]
    assert excluded == 0 and not field_issues
    assert len(rejected) == 3
    assert {issue["reason"] for row in rejected for issue in row["issues"]} == {
        "non_article_game", "non_article_section", "non_article_navigation",
    }


@pytest.mark.parametrize("headline", [None, "", "   "])
def test_article_url_cannot_replace_missing_captured_headline(headline):
    values = source(instructions="Get articles from the captured page", page_text="Read more")
    candidate = article_kind_candidate([(headline, values.urls[0])])
    page = {"url": values.urls[0], "source_kind": "page", "text": "Read more", "blocks": [
        {"id": "footer", "kind": "paragraph", "text": "Read more", "association": "page"},
    ]}
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected, field_issues = [], []
    records, _ = validate_extraction(
        candidate, effective, [page], rejected=rejected, field_issues=field_issues
    )
    assert not records and not field_issues
    assert any(issue["reason"] == "article_headline_missing" for issue in rejected[0]["issues"])


def test_article_request_without_a_headline_column_is_rejected():
    values = source(instructions="Get articles from the captured page", page_text="Read more")
    candidate = article_kind_candidate([(None, values.urls[0])])
    candidate.columns = candidate.columns[1:]
    candidate.rows[0].cells = candidate.rows[0].cells[1:]
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected = []
    records, _ = validate_extraction(
        candidate, effective, [{"url": values.urls[0], "text": "Read more"}], rejected=rejected
    )
    assert not records
    assert rejected[0]["issues"][0]["reason"] == "article_headline_missing"


def test_request_for_articles_requires_a_heading_even_if_model_calls_them_links():
    title = "Players reflect on the season"
    values = source(instructions="Get articles from the captured page", page_text=title)
    candidate = article_kind_candidate([(title, values.urls[0])], content_type="links", headline_field="title")
    page = {"url": values.urls[0], "source_kind": "page", "text": title, "blocks": [
        {"id": "body", "kind": "paragraph", "text": title,
         "association": "record", "group_id": "g1"},
    ]}
    candidate, effective, _ = prepare_extraction(candidate, values)
    rejected, field_issues = [], []
    records, _ = validate_extraction(
        candidate, effective, [page], rejected=rejected, field_issues=field_issues
    )
    assert not records and not field_issues
    assert any(issue["reason"] == "article_headline_not_captured" for issue in rejected[0]["issues"])


@pytest.mark.parametrize("title", ["Game", "Science", "Explore new worlds", "The game is changing"])
def test_article_kind_keeps_short_and_game_related_record_headlines(title):
    assert article_record_issue(title, {"source_kind": "index", "blocks": [
        {"kind": "heading", "heading_level": 2, "text": title, "association": "record",
         "href": "https://example.org/categories/sports", "group_id": "story"},
    ]}) is None


def test_explicit_primary_headline_is_not_reclassified_from_short_section_wording():
    title = "Sports coverage"
    assert article_record_issue(title, {"source_kind": "page", "blocks": [
        {"kind": "heading", "heading_level": 1, "content_role": "headline", "text": title,
         "association": "record", "group_id": "story"},
    ]}) is None


@pytest.mark.parametrize("title", ["Play Connections: Sports Edition", "Sports coverage"])
def test_non_article_labels_are_rejected_in_plain_source_text(title):
    assert article_record_issue(title, {"text": title}) in {"non_article_game", "non_article_section"}
