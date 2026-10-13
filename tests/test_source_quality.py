"""Headline/body quality regressions; no real model calls or external requests.

Only the explicitly opted-in DOM fixtures launch isolated, locally fulfilled Chromium.
"""

from pathlib import Path

import pytest
from test_dashboard import finished
from test_source_inventory import (
    COLLECTOR,
)
from test_source_inventory import (
    inventory_browser as shared_inventory_browser,
)

from agentic_web_demo import custom_service
from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import (
    Condition,
    Extraction,
    WebsiteInput,
    validate_extraction,
)
from agentic_web_demo.dashboard.service import DashboardService
from agentic_web_demo.source_fields import headline_issue, primary_headline

URL = "https://news.example.org/sport/cup-final"
HEADLINE = "Soccer club wins the cup final"
BODY = "The soccer club won after Maya Silva scored in extra time, delighting the travelling fans."


def page(*, kind="detail", heading=True):
    blocks = []
    if heading:
        blocks.append(
            {
                "id": "b1",
                "kind": "heading",
                "text": HEADLINE,
                "heading_level": 1,
                "content_role": "headline",
                "group_id": "story-1",
                "association": "record",
            }
        )
    blocks.append(
        {
            "id": "b2",
            "kind": "paragraph",
            "text": BODY,
            "content_role": "body",
            "group_id": "story-1",
            "association": "record",
        }
    )
    return {
        "url": URL,
        "requested_url": URL,
        "source_kind": kind,
        "text": "\n".join(b["text"] for b in blocks),
        "blocks": blocks,
        "truncated": False,
    }


def extraction(*, title=HEADLINE, excerpt=BODY, target=URL):
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review source fields",
            "content_type": "articles",
            "interpretation": "Captured sports content",
            "warnings": [],
            "more_records_available": False,
            "filters": [],
            "query_rules": [],
            "columns": [
                {"name": field, "kind": "text", "unit": "", "description": field}
                for field in ("article_title", "article_url", "article_excerpt")
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {
                            "field": "article_title",
                            "value": title,
                            "evidence": title or "",
                        },
                        {
                            "field": "article_url",
                            "value": target,
                            "evidence": target or "",
                        },
                        {
                            "field": "article_excerpt",
                            "value": excerpt,
                            "evidence": excerpt or "",
                        },
                    ],
                }
            ],
        }
    )


def checked(candidate, captured):
    values = WebsiteInput(
        source="public",
        urls=[URL],
        instructions="Get sports content",
        authorized=True,
        allow_model_api=True,
    )
    rejected, fields, repairs, counts = [], [], [], {}
    records, excluded = validate_extraction(
        candidate,
        values,
        [captured],
        rejected=rejected,
        field_issues=fields,
        field_repairs=repairs,
        review_counts=counts,
    )
    return records, excluded, rejected, fields, repairs, counts


def test_body_quote_is_replaced_only_by_unique_captured_main_headline():
    candidate = extraction(title=BODY)
    records, _, rejected, _, repairs, counts = checked(candidate, page())
    assert not rejected
    assert records[0]["article_title"] == HEADLINE
    assert records[0]["article_excerpt"] == BODY
    assert repairs[0]["issues"][0]["reason"] == "headline_from_unique_captured_h1"
    assert repairs[0]["issues"][0]["evidence"] == HEADLINE
    assert counts["source_fields_corrected"] == 1
    assert candidate.rows[0].cells[0].value == BODY  # The provider response remains unchanged.


@pytest.mark.parametrize("wrapper", ['"{}"', "“{}”", "'{}'"])
def test_display_quote_wrapper_does_not_erase_a_verbatim_excerpt(wrapper):
    records, _, rejected, fields, repairs, _ = checked(
        extraction(excerpt=wrapper.format(BODY)), page()
    )
    assert not rejected and not fields
    assert records[0]["article_excerpt"] == BODY
    assert repairs[0]["issues"][0]["reason"] == "display_quote_wrapper_removed"


def test_literal_source_quotes_are_not_removed_when_they_are_actually_present():
    captured = page()
    literal = f'"{BODY}"'
    captured["blocks"][1]["text"] = literal
    captured["text"] = HEADLINE + "\n" + literal
    records, _, _, _, repairs, _ = checked(extraction(excerpt=literal), captured)
    assert records[0]["article_excerpt"] == literal and not repairs


def test_body_only_capture_cannot_supply_a_headline_from_a_quote_or_url_slug():
    records, _, rejected, _, repairs, _ = checked(extraction(title=BODY), page(heading=False))
    assert not records and not repairs
    assert rejected[0]["issues"][0]["reason"] == "primary_headline_not_captured"


def test_multiple_main_headlines_are_not_guessed():
    captured = page()
    captured["blocks"].append({**captured["blocks"][0], "id": "b3", "text": "Another headline"})
    captured["text"] += "\nAnother headline"
    assert primary_headline(captured) is None
    records, _, rejected, _, repairs, _ = checked(extraction(title=BODY), captured)
    assert not records and rejected and not repairs


def test_multiple_rows_on_detail_page_cannot_be_relabelled_as_the_main_article():
    candidate = extraction(title=BODY)
    candidate.rows.append(candidate.rows[0].model_copy(deep=True))
    records, _, rejected, _, repairs, _ = checked(candidate, page())
    assert not records and len(rejected) == 2 and not repairs


@pytest.mark.parametrize("target", [None, "https://news.example.org/sport/other-story"])
def test_correction_requires_record_url_binding_to_the_captured_page(target):
    records, _, rejected, _, repairs, _ = checked(extraction(title=BODY, target=target), page())
    assert not records and rejected and not repairs


def test_paraphrased_excerpt_is_not_repaired_as_source_text():
    records, _, rejected, fields, repairs, _ = checked(
        extraction(excerpt="A great soccer victory brought joy to supporters."), page()
    )
    assert not rejected and not repairs
    assert records[0]["article_excerpt"] is None
    assert fields[0]["issues"][0]["reason"] == "quote_missing_from_source"


def test_index_teaser_is_not_presented_as_a_detail_body_excerpt():
    captured = page(kind="index")
    captured["blocks"][0]["heading_level"] = 2
    captured["blocks"][0]["content_role"] = "other"
    captured["blocks"][0]["href"] = URL
    captured["text"] += "\n" + URL
    records, _, rejected, fields, _, _ = checked(extraction(), captured)
    assert not rejected
    assert records[0]["article_title"] == HEADLINE
    assert records[0]["article_excerpt"] is None
    assert fields[0]["issues"][0]["reason"] == "detail_body_not_captured"


def test_current_page_kicker_uses_only_an_unambiguous_url_bound_captured_heading():
    captured = page(kind="index")
    captured["blocks"][0].update(heading_level=2, content_role="other", href=URL)
    captured["blocks"].append(
        {
            "id": "b3",
            "kind": "link",
            "text": "LOST IN TRANSLATION",
            "href": URL,
            "group_id": "story-1",
            "association": "record",
        }
    )
    captured["text"] += "\nLOST IN TRANSLATION\n" + URL
    records, _, rejected, _, repairs, _ = checked(
        extraction(title="LOST IN TRANSLATION", excerpt=None), captured
    )
    assert not rejected and records[0]["article_title"] == HEADLINE
    assert repairs[0]["issues"][0]["reason"] == "headline_from_url_bound_captured_heading"
    assert headline_issue("LOST IN TRANSLATION", captured) == "kicker_not_linked_headline"


@pytest.mark.parametrize("kind", ["index", None])
def test_index_hero_h1_does_not_invalidate_other_record_headlines(kind):
    captured = page(kind=kind)
    captured["blocks"].append(
        {
            "id": "b3",
            "kind": "heading",
            "heading_level": 2,
            "content_role": "other",
            "text": "Another soccer headline",
            "href": URL + "-other",
            "group_id": "story-2",
            "association": "record",
        }
    )
    assert headline_issue("Another soccer headline", captured) is None


def test_corrected_title_is_used_for_explicit_filters_not_the_wrong_body_quote():
    candidate = extraction(title=BODY)
    candidate.filters = [Condition(field="article_title", operator="contains", value="Maya Silva")]
    records, excluded, rejected, _, _, counts = checked(candidate, page())
    assert not records and not rejected and excluded == counts["filtered_out"] == 1


def test_old_plain_text_and_legacy_heading_captures_remain_compatible():
    assert checked(extraction(), {"url": URL, "text": HEADLINE + "\n" + BODY})[0]
    legacy = page()
    for block in legacy["blocks"]:
        block.pop("content_role", None)
        block.pop("heading_level", None)
    assert checked(extraction(), legacy)[0]


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_both_frameworks_expose_corrections_in_an_unsaved_partial_preview(
    tmp_path, monkeypatch, framework
):
    values = WebsiteInput(
        source="public",
        urls=[URL],
        instructions="Get sports content",
        framework=framework,
        authorized=True,
        allow_model_api=True,
    )
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [page()])
    monkeypatch.setattr(
        custom_service,
        "interpret",
        lambda *_: (
            extraction(title=BODY, excerpt=f'"{BODY}"'),
            {"model": "fixture", "prompt_version": "website-extractor-v8"},
        ),
    )
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        job = finished(service, custom_service.plan(service, values, object()))
        assert job["status"] == "awaiting_review", job
        proposal = job["result"]["proposal"]
        assert proposal["records"][0]["article_title"] == HEADLINE
        assert proposal["records"][0]["article_excerpt"] == BODY
        assert proposal["partial"] and proposal["field_repairs"]
        assert proposal["review_counts"]["source_fields_corrected"] == 1
        assert not job["result"].get("run_id")
    finally:
        service.close()


def test_captured_link_rejection_exposes_field_reasons_not_a_navigation_error(
    tmp_path, monkeypatch
):
    index_url = "https://news.example.org/"
    values = WebsiteInput(
        source="browser",
        urls=[index_url],
        instructions="Get sports content",
        authorized=True,
        allow_model_api=True,
    )
    captured = page(heading=False)
    captured["parent_url"] = index_url
    index = {
        "url": index_url,
        "source_kind": "index",
        "text": HEADLINE + "\n" + URL,
        "truncated": False,
        "blocks": [],
    }
    candidate = extraction(title=BODY)
    candidate.rows[0].page_index = 1

    def local_capture(_values, control, _settings):
        control.link_coverage = {
            "index_retained": True,
            "links": [{"url": URL, "source_url": URL, "title": HEADLINE, "status": "captured"}],
        }
        return [index, captured]

    monkeypatch.setattr(custom_service, "read_browser", local_capture)
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate, {"model": "fixture"}))
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        job = finished(service, custom_service.plan(service, values, object()))
        assert job["status"] == "needs_input", job
        link = job["result"]["enrichment"]["links"][0]
        assert link["status"] == "captured" and link["record_status"] == "validation_failed"
        assert link["validation_issues"][0]["reason"] == "primary_headline_not_captured"
    finally:
        service.close()


@pytest.fixture
def source_browser(request):
    yield from shared_inventory_browser.__wrapped__(request)


def test_local_dom_keeps_article_header_and_inline_names_but_excludes_global_navigation(
    source_browser,
):
    browser = source_browser
    browser.set_content("""<header><h1>Website navigation only</h1>
      <nav>Account Home Menu</nav></header>
      <article><header class='story-header'><h1>Soccer club wins the cup final</h1></header>
      <main><div class='article-body'><p>The soccer club won after
      <a href='/people/maya'>Maya Silva</a>
      scored in extra time, delighting the travelling fans.</p></div></main></article>""")
    capture = Capture.model_validate(browser.evaluate("(" + COLLECTOR + ")"))
    captured = capture.page()
    assert "Website navigation only" not in captured["text"]
    headline = next(block for block in capture.blocks if block.text == HEADLINE)
    paragraph = next(block for block in capture.blocks if block.text == BODY)
    assert headline.kind == "heading" and headline.heading_level == 1
    assert headline.content_role == "headline" and paragraph.content_role == "body"
    assert headline.group_id == paragraph.group_id
    assert any(block.href == "https://news.example.org/people/maya" for block in capture.blocks)


def test_local_current_page_capture_and_detail_capture_have_honest_different_scopes(
    source_browser,
):
    browser = source_browser
    browser.set_content("""<main><article><header><a href='/sport/cup-final'>
      <h2>Soccer club wins the cup final</h2></a></header><p>Read the match report and interviews
      with the winning team. Follow the story to read the complete report.</p></article></main>""")
    index = Capture.model_validate(browser.evaluate("(" + COLLECTOR + ")"))
    assert any(block.kind == "heading" and block.text == HEADLINE for block in index.blocks)
    assert BODY not in index.page()["text"]
    browser.set_content(f"<article><header><h1>{HEADLINE}</h1></header><p>{BODY}</p></article>")
    detail = Capture.model_validate(browser.evaluate("(" + COLLECTOR + ")"))
    assert BODY in detail.page()["text"]
    assert next(block for block in detail.blocks if block.text == BODY).content_role == "body"


def test_local_nested_hotel_headers_keep_names_and_prices_in_separate_record_groups(
    source_browser,
):
    browser = source_browser
    browser.set_content("""<main><div data-testid='property-card'><header>
      <a href='/hotel/north'><h2>North Hotel in Boston</h2></a></header>
      <p>250 USD nightly rating 4.2</p></div><div data-testid='property-card'><header>
      <a href='/hotel/south'><h2>South Hotel in Boston</h2>
      </a></header><p>350 USD nightly rating 4.8</p></div></main>""")
    capture = Capture.model_validate(browser.evaluate("(" + COLLECTOR + ")"))

    def group(text):
        return next(block.group_id for block in capture.blocks if text in block.text)

    assert group("North Hotel") == group("250 USD")
    assert group("South Hotel") == group("350 USD")
    assert group("North Hotel") != group("South Hotel")


def test_extension_and_built_in_collector_are_identical():
    root = Path(__file__).resolve().parents[1]
    assert (root / "extensions/page-capture/capture_dom.js").read_bytes() == (
        root / "src/agentic_web_demo/dashboard/static/capture_dom.js"
    ).read_bytes()
