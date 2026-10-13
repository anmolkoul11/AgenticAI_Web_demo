"""Checkpoint 2 fixtures: no browsers, websites, models, credentials or message bus."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_custom_website import source
from test_dashboard import finished

from agentic_web_demo import custom_browser, custom_service
from agentic_web_demo.custom_browser import BrowserControl, collect_approved_details
from agentic_web_demo.custom_extract import (
    Column,
    Condition,
    ExtractedRow,
    Extraction,
    WebsiteInput,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.service import DashboardService
from agentic_web_demo.enrichment import evidence_block_ids, reconcile_records
from agentic_web_demo.exports import build_export

INDEX = "https://example.org/news"
FIRST = "https://example.org/story-one"
SECOND = "https://example.org/story-two"
TITLE = "Technology researchers publish new results"
OTHER = "Sports team wins the season opener"
BODY = "The researchers tested a new material and reported their laboratory results."


def pages():
    blocks = [
        {"id": "b1", "kind": "link", "text": TITLE, "href": FIRST, "group_id": "g1"},
        {"id": "b2", "kind": "link", "text": OTHER, "href": SECOND, "group_id": "g2"},
    ]
    details = [
        {"id": "b1", "kind": "heading", "text": TITLE, "href": None, "group_id": "g1"},
        {"id": "b2", "kind": "paragraph", "text": BODY, "href": None, "group_id": "g1"},
        {"id": "b3", "kind": "text", "text": "Jane Reporter", "href": None, "group_id": "g1"},
    ]
    return [
        {
            "url": INDEX,
            "source_kind": "index",
            "blocks": blocks,
            "truncated": False,
            "text": "\n".join(b["text"] + " " + b["href"] for b in blocks),
        },
        {
            "url": FIRST,
            "requested_url": FIRST,
            "parent_url": INDEX,
            "source_kind": "detail",
            "blocks": details,
            "truncated": False,
            "text": "\n".join(b["text"] for b in details),
        },
    ]


def coverage(*, failed=False):
    return {
        "index_url": INDEX,
        "index_retained": True,
        "approved": 1,
        "captured": 0 if failed else 1,
        "failed": int(failed),
        "links": [
            {
                "url": FIRST,
                "title": TITLE,
                "status": "failed" if failed else "captured",
                **({"reason": "Fixture denied access"} if failed else {"source_url": FIRST}),
            }
        ],
    }


def candidate():
    names = ["article_title", "article_url", "article_excerpt", "author"]
    rows = [
        (0, [TITLE, FIRST, None, None]),
        (0, [OTHER, SECOND, None, None]),
        (1, [TITLE, FIRST, BODY, "Jane Reporter"]),
    ]
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Captured records with source details",
            "filters": [],
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": name, "kind": "text", "unit": "", "description": name} for name in names
            ],
            "rows": [
                {
                    "page_index": page,
                    "cells": [
                        {"field": field, "value": value, "evidence": value or ""}
                        for field, value in zip(names, values, strict=True)
                    ],
                }
                for page, values in rows
            ],
        }
    )


def verified(candidate_value=None):
    result = candidate_value or candidate()
    values = source(instructions="Extract available records")
    rows, _ = validate_extraction(
        result,
        values,
        pages(),
        rejected=[],
        field_issues=[],
        apply_filters=False,
        enforce_limit=False,
        preserve_sources=True,
    )
    return rows


def test_starting_page_records_survive_and_detail_cells_keep_their_source():
    result = candidate()
    rows, report = reconcile_records(verified(), pages(), result.columns, coverage())
    assert len(rows) == 2
    first, second = rows
    assert first["source_url"] == INDEX  # Index provenance never replaced by detail provenance.
    assert first["article_excerpt"] == BODY
    assert first["author"] == "Jane Reporter"
    assert first["evidence_sources"]["article_title"]["source_url"] == INDEX
    assert first["evidence_sources"]["article_excerpt"]["source_url"] == FIRST
    assert first["evidence_sources"]["article_excerpt"]["block_ids"] == ["b2"]
    assert first["detail_status"] == "enriched"
    assert second["article_title"] == OTHER
    assert second["detail_status"] == "not_opened"
    assert report["verified_index_records"] == 2 and report["merged_counterparts"] == 1
    assert evidence_block_ids(rows, pages())[first["listing_id"]]["article_excerpt"] == ["b2"]


def test_missing_url_column_uses_unique_identity_group_link_not_a_title_guess():
    result = candidate()
    rows = verified()
    for row in rows:
        row["article_url"] = None
    merged, _ = reconcile_records(rows, pages(), result.columns, coverage())
    assert merged[0]["record_url"] == FIRST
    assert merged[0]["article_excerpt"] == BODY  # Detail primary heading supplies identity.


def test_failed_detail_keeps_index_and_reports_partial_coverage():
    rows, report = reconcile_records(
        verified()[:2], pages()[:1], candidate().columns, coverage(failed=True)
    )
    assert len(rows) == 2
    assert rows[0]["detail_status"] == "failed"
    assert rows[0]["article_excerpt"] is None
    assert report["failed"] == 1


def test_captured_page_without_verified_detail_record_is_not_claimed_enriched():
    rows, report = reconcile_records(verified()[:2], pages(), candidate().columns, coverage())
    assert rows[0]["detail_status"] == "not_extracted"
    assert report["links"][0]["record_status"] == "not_extracted"
    assert report["model_coverage_gap"] is True


def test_unrelated_detail_parent_cannot_attach_to_index_record():
    documents = pages()
    documents[1]["parent_url"] = "https://example.org/unrelated"
    rows, report = reconcile_records(verified(), documents, candidate().columns, coverage())
    assert len(rows) == 3
    assert rows[0]["article_excerpt"] is None
    assert rows[2]["detail_status"] == "detail_only"
    assert report["merged_counterparts"] == 0


def test_ambiguous_index_matches_remain_separate():
    rows = verified()
    duplicate = deepcopy(rows[0])
    duplicate["listing_id"] = "record-0004"
    rows.insert(1, duplicate)
    merged, report = reconcile_records(rows, pages(), candidate().columns, coverage())
    assert len(merged) == 4
    assert report["links"][0]["record_status"] == "ambiguous_index_match"
    assert report["model_coverage_gap"] is True


def test_conflicting_price_used_by_filter_remains_a_separate_source_variant():
    columns = [
        Column(name="name", description="Name", kind="text", unit=""),
        Column(name="price", description="Nightly price", kind="number", unit="USD"),
    ]
    documents = pages()
    rows = [
        {
            "listing_id": "record-0001",
            "name": TITLE,
            "price": "150",
            "source_url": INDEX,
            "evidence": {"name": TITLE, "price": "150 USD"},
        },
        {
            "listing_id": "record-0002",
            "name": TITLE,
            "price": "250",
            "source_url": FIRST,
            "evidence": {"name": TITLE, "price": "250 USD"},
        },
    ]
    merged, report = reconcile_records(
        rows, documents, columns, coverage(), protected_fields={"price"}
    )
    assert len(merged) == 2
    assert [r["price"] for r in merged] == ["150", "250"]
    assert merged[0]["enrichment_conflicts"]["price"]["detail_value"] == "250"
    assert report["conflicting_records"] == 1


def test_reconciliation_does_not_mutate_source_records():
    rows = verified()
    before = deepcopy(rows)
    reconcile_records(rows, pages(), candidate().columns, coverage())
    assert rows == before


def test_property_listings_use_url_identity_not_news_specific_logic():
    columns = [
        Column(name="hotel_name", description="Name", kind="text", unit=""),
        Column(name="property_url", description="Listing URL", kind="text", unit=""),
        Column(name="description", description="Details", kind="text", unit=""),
    ]
    documents = pages()
    documents[0]["blocks"] = [
        {"id": "b1", "kind": "link", "text": "Boston Hotel", "href": FIRST, "group_id": "g1"}
    ]
    documents[1]["blocks"] = [
        {"id": "b1", "kind": "heading", "text": "Boston Hotel", "group_id": "g1"},
        {"id": "b2", "kind": "paragraph", "text": "A hotel near the harbor.", "group_id": "g1"},
    ]
    rows = [
        {
            "listing_id": "record-0001",
            "hotel_name": "Boston Hotel",
            "property_url": FIRST,
            "description": None,
            "source_url": INDEX,
            "evidence": {"hotel_name": "Boston Hotel", "property_url": FIRST, "description": ""},
        },
        {
            "listing_id": "record-0002",
            "hotel_name": "Boston Hotel",
            "property_url": FIRST,
            "description": "A hotel near the harbor.",
            "source_url": FIRST,
            "evidence": {
                "hotel_name": "Boston Hotel",
                "property_url": FIRST,
                "description": "A hotel near the harbor.",
            },
        },
    ]
    merged, report = reconcile_records(rows, documents, columns, coverage())
    assert len(merged) == 1 and merged[0]["hotel_name"] == "Boston Hotel"
    assert merged[0]["description"] == "A hotel near the harbor."
    assert merged[0]["evidence_sources"]["description"]["source_url"] == FIRST
    assert report["enriched_records"] == 1


def test_multiple_primary_detail_rows_do_not_blend_into_one_index_record():
    rows = verified()
    second_detail = deepcopy(rows[2])
    second_detail["listing_id"] = "record-0004"
    second_detail["author"] = "Different Reporter"
    rows.append(second_detail)
    merged, report = reconcile_records(rows, pages(), candidate().columns, coverage())
    assert len(merged) == 4
    assert merged[0]["article_excerpt"] is None
    assert report["merged_counterparts"] == 0
    assert report["model_coverage_gap"] is True


def test_sixth_source_page_is_valid_but_seventh_is_not():
    assert ExtractedRow(page_index=5, cells=[]).page_index == 5
    with pytest.raises(ValueError):
        ExtractedRow(page_index=6, cells=[])


def test_unavailable_page_rejects_only_that_record_when_partial_preview_is_enabled():
    result = candidate()
    result.rows[2].page_index = 5
    rejected = []
    rows, _ = validate_extraction(
        result,
        source(instructions="Extract available records"),
        pages(),
        rejected=rejected,
        field_issues=[],
        preserve_sources=True,
    )
    assert len(rows) == 2
    assert rejected[0]["issues"][0]["reason"] == "unavailable_source_page"
    assert rejected[0]["issues"][0]["page_index"] == 5


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


def fake_collection(values, control, settings):
    control.link_coverage = coverage()
    return pages()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_framework_preview_save_and_export_preserve_enrichment(service, monkeypatch, framework):
    monkeypatch.setattr(custom_service, "read_browser", fake_collection)
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(), {"model": "fixture"}))
    values = WebsiteInput(
        source="browser",
        framework=framework,
        urls=[INDEX],
        login_mode="none",
        instructions="Extract available records",
        record_limit=2,
        authorized=True,
        allow_model_api=True,
    )
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "awaiting_review", job
    proposal = job["result"]["proposal"]
    assert len(proposal["records"]) == 2  # Three raw rows must not fail a two-record merged limit.
    assert proposal["enrichment"]["merged_counterparts"] == 1
    assert not proposal["partial"]
    saved = finished(
        service, custom_service.execute(service, proposal["plan_id"], job["result"]["revision"])
    )
    snapshot = service.records(saved["job_id"])
    assert snapshot["enrichment"]["index_retained"]
    assert snapshot["records"][0]["evidence_sources"]["author"]["source_url"] == FIRST
    # Export format helpers are pure; no local file writes or model calls.
    for format_name in ("csv", "xlsx", "json", "jsonl"):
        content, _ = build_export(
            snapshot, format_name, run_id=snapshot["run_id"], framework=framework
        )
        assert content


def test_final_merged_limit_is_not_silently_truncated(service, monkeypatch):
    monkeypatch.setattr(custom_service, "read_browser", fake_collection)
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(), {}))
    values = WebsiteInput(
        source="browser",
        urls=[INDEX],
        login_mode="none",
        record_limit=1,
        instructions="Extract available records",
        authorized=True,
        allow_model_api=True,
    )
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "needs_input"
    assert "2 merged matching records" in job["result"]["guidance"]
    assert "proposal" not in job["result"]


def test_filters_run_after_detail_fields_are_filled(service, monkeypatch):
    result = candidate()
    result.filters = [Condition(field="author", operator="eq", value="Jane Reporter")]
    monkeypatch.setattr(custom_service, "read_browser", fake_collection)
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (result, {}))
    values = WebsiteInput(
        source="browser",
        urls=[INDEX],
        login_mode="none",
        record_limit=1,
        instructions="Extract records authored by Jane Reporter",
        authorized=True,
        allow_model_api=True,
    )
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "awaiting_review", job
    proposal = job["result"]["proposal"]
    assert len(proposal["records"]) == 1
    assert proposal["records"][0]["article_title"] == TITLE
    assert proposal["records"][0]["source_url"] == INDEX
    assert proposal["excluded_by_filters"] == 1


def test_truncated_link_capture_requires_partial_review(service, monkeypatch):
    def collect(values, control, settings):
        documents = fake_collection(values, control, settings)
        documents[1]["truncated"] = True
        return documents

    monkeypatch.setattr(custom_service, "read_browser", collect)
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(), {}))
    values = WebsiteInput(
        source="browser",
        urls=[INDEX],
        login_mode="none",
        instructions="Extract available records",
        authorized=True,
        allow_model_api=True,
    )
    job = finished(service, custom_service.plan(service, values, object()))
    proposal = job["result"]["proposal"]
    assert proposal["partial"] is True
    assert proposal["enrichment"]["truncated_captures"] == 1
    with pytest.raises(WebsiteError, match="partial"):
        custom_service.execute(service, proposal["plan_id"], job["result"]["revision"])


@pytest.mark.parametrize("all_fail", [False, True])
def test_collection_retains_index_before_any_navigation_and_reports_each_link(
    monkeypatch, all_fail
):
    documents = pages()
    visits = []

    class Page:
        url = INDEX

        def goto(self, url, **kwargs):
            visits.append(url)
            self.url = url
            return SimpleNamespace(status=403 if all_fail or url == SECOND else 200)

        def wait_for_load_state(self, *args, **kwargs):
            pass

    def capture(page, *args, **kwargs):
        if page.url == INDEX:
            assert visits == []
            return {k: deepcopy(v) for k, v in documents[0].items() if k != "source_kind"}
        return {
            k: deepcopy(v)
            for k, v in documents[1].items()
            if k not in {"source_kind", "parent_url", "requested_url"}
        }

    monkeypatch.setattr(custom_browser, "prepare_browser_content", lambda *_: {})
    monkeypatch.setattr(custom_browser, "capture_rendered_page", capture)
    monkeypatch.setattr(custom_browser, "check_robots", lambda _: None)
    control = BrowserControl()
    selected = [{"url": FIRST, "title": TITLE}, {"url": SECOND, "title": OTHER}]
    collected = collect_approved_details(
        Page(), control, selected, "https://example.org", [], [200], 0
    )
    assert collected[0]["url"] == INDEX and collected[0]["source_kind"] == "index"
    assert len(collected) == (1 if all_fail else 2)
    assert len(control.snapshot()["capture_failures"]) == (2 if all_fail else 1)
    assert [a["status"] for a in control.snapshot()["link_coverage"]["links"]] == (
        ["failed", "failed"] if all_fail else ["captured", "failed"]
    )


def test_cancel_during_detail_collection_does_not_return_a_partial_success(monkeypatch):
    control = BrowserControl()
    control.cancel.set()
    monkeypatch.setattr(custom_browser, "prepare_browser_content", lambda *_: {})
    monkeypatch.setattr(custom_browser, "capture_rendered_page", lambda *_args, **_kw: pages()[0])
    with pytest.raises(WebsiteError, match="cancelled"):
        collect_approved_details(
            object(), control, [{"url": FIRST, "title": TITLE}], None, [], [200]
        )


def test_collection_never_opens_more_than_five_approved_details():
    with pytest.raises(WebsiteError, match="one to five"):
        collect_approved_details(object(), BrowserControl(), [{"url": FIRST}] * 6, None, [], [200])
