"""Literal title/link evidence regressions; no real model calls or external requests.

DOM cases use the existing opt-in, locally fulfilled --run-browser fixture.
"""

from pathlib import Path

import pytest
from test_source_inventory import COLLECTOR, LINK_SNAPSHOT
from test_source_inventory import inventory_browser as shared_browser

from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import Extraction, WebsiteInput, validate_extraction
from agentic_web_demo.source_fields import headline_issue

INDEX = "https://news.example.org/"
TARGET = INDEX + "sport/cup-final"
TITLE = "Soccer club wins the cup final"


def candidate(title=TITLE, *, content_type="articles", field="article_title", url=None):
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review source records",
            "content_type": content_type,
            "interpretation": "Visible source records",
            "warnings": [],
            "more_records_available": False,
            "filters": [],
            "columns": [
                {"name": name, "kind": "text", "description": name, "unit": ""}
                for name in (field, "url")
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": field, "value": title, "evidence": title},
                        {"field": "url", "value": url, "evidence": url or ""},
                    ],
                }
            ],
        }
    )


def validate(result, page):
    values = WebsiteInput(
        source="public",
        urls=[INDEX],
        instructions="get articles related to sports",
        authorized=True,
        allow_model_api=True,
    )
    rejected, repairs = [], []
    rows, _ = validate_extraction(
        result, values, [page], rejected=rejected, field_repairs=repairs, field_issues=[]
    )
    return rows, rejected, repairs


def page_for(blocks):
    return {
        "url": INDEX,
        "source_kind": "index",
        "text": "\n".join(b["text"] + ("\n" + b["href"] if b.get("href") else "") for b in blocks),
        "blocks": blocks,
    }


def link_block(*, title=TITLE, href=TARGET):
    return {
        "id": "b1",
        "kind": "link",
        "text": title,
        "href": href,
        "group_id": "g1",
        "association": "record",
        "content_role": "other",
    }


def test_index_link_label_accepts_literal_title_and_repairs_unique_url():
    rows, rejected, repairs = validate(candidate(), page_for([link_block()]))
    assert not rejected
    assert rows[0]["article_title"] == TITLE and rows[0]["url"] == TARGET
    assert repairs[0]["issues"][0]["reason"] == "literal_value_from_captured_structure"


@pytest.mark.parametrize("relevance", ["relevant", "not_relevant", "uncertain"])
def test_link_evidence_preserves_independent_topic_selection(relevance):
    data = candidate().model_dump()
    data["semantic_selection"] = {"request_quote": "related to sports", "topic": "sports"}
    data["rows"][0].update(
        relevance=relevance,
        relevance_reason="Source headline describes a soccer cup final",
        relevance_evidence=TITLE,
    )
    rows, rejected, _ = validate(Extraction.model_validate(data), page_for([link_block()]))
    assert bool(rows) == (relevance == "relevant")
    if relevance == "relevant":
        assert not rejected and rows[0]["article_title"] == TITLE
    elif relevance == "uncertain":
        assert rejected[0]["issues"][0]["reason"] == "uncertain_relevance"


def test_paragraph_with_href_alone_is_not_reclassified_as_a_title():
    block = {**link_block(), "kind": "paragraph"}
    rows, rejected, _ = validate(candidate(), page_for([block]))
    assert not rows
    assert rejected[0]["issues"][0]["reason"] == "title_not_supported_by_heading_or_link"


def test_same_label_at_two_urls_does_not_guess_missing_record_url():
    blocks = [
        link_block(),
        {**link_block(href=INDEX + "sport/other"), "id": "b2", "group_id": "g2"},
    ]
    rows, rejected, repairs = validate(candidate(), page_for(blocks))
    assert not rejected
    assert rows[0]["url"] is None and not repairs


def test_kicker_link_is_not_a_headline_when_a_real_heading_is_bound_to_its_url():
    blocks = [
        link_block(title="LOST IN TRANSLATION"),
        {**link_block(), "id": "b2", "kind": "heading", "heading_level": 2},
    ]
    page = page_for(blocks)
    assert headline_issue("LOST IN TRANSLATION", page) == "kicker_not_linked_headline"
    rows, rejected, repairs = validate(candidate("LOST IN TRANSLATION"), page)
    assert not rows and not repairs
    assert rejected[0]["issues"][0]["reason"] == "kicker_not_linked_headline"


def test_detail_page_still_requires_main_headline_not_an_inline_body_link():
    page = {**page_for([link_block()]), "source_kind": "detail"}
    rows, rejected, _ = validate(candidate(), page)
    assert not rows
    assert rejected[0]["issues"][0]["reason"] == "primary_headline_not_captured"


def test_generic_hotel_name_can_use_unique_literal_link_for_url():
    name = "Boston Hotel North"
    rows, rejected, repairs = validate(
        candidate(name, content_type="hotel listings", field="name"),
        page_for([link_block(title=name, href=INDEX + "hotel/north")]),
    )
    assert not rejected and repairs
    assert rows[0]["name"] == name and rows[0]["url"] == INDEX + "hotel/north"


def test_extension_and_browser_use_identical_collector():
    root = Path(__file__).resolve().parents[1]
    assert (root / "extensions/page-capture/capture_dom.js").read_text(
        encoding="utf-8"
    ) == COLLECTOR


@pytest.fixture
def local_page(request):
    yield from shared_browser.__wrapped__(request)


@pytest.mark.parametrize(
    "markup",
    [
        '<a href="/sport/cup-final"><p>Soccer club wins the cup final</p></a>',
        '<p><a href="/sport/cup-final">Soccer club wins the cup final</a></p>',
        '<a href="/sport/cup-final"><span>Soccer club wins the cup final</span></a>',
        '<li><a href="/sport/cup-final">Soccer club wins the cup final</a></li>',
        '<a href="/sport/cup-final"><div><span>Soccer club wins the cup final</span></div></a>',
        '<a href="/sport/cup-final"><p>Soccer club <em>wins</em> the cup final</p></a>',
    ],
)
def test_current_page_and_link_discovery_share_nonheading_label_evidence(local_page, markup):
    local_page.set_content(
        "<main><article>" + markup + "<p>Actual match teaser: the team won after extra time.</p>"
        "</article><p>Additional visible source text for this isolated fixture.</p></main>"
    )
    links = local_page.evaluate(LINK_SNAPSHOT)
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    assert links[0]["title"] == TITLE and links[0]["url"] == TARGET
    assert any(b.kind == "link" and b.text == TITLE and b.href == TARGET for b in capture.blocks)
    assert any(b.kind == "paragraph" and "Actual match teaser" in b.text for b in capture.blocks)
    rows, rejected, _ = validate(candidate(), {**capture.page(), "source_kind": "index"})
    assert not rejected and rows[0]["url"] == TARGET


def test_link_labels_exclude_hidden_navigation_and_form_text(local_page):
    local_page.set_content("""<nav><a href='/menu'>Navigation only label</a></nav>
      <main><a href='/sport/cup-final'><p>Soccer club
      <span aria-hidden='true'>SECRET HIDDEN WORDS</span>wins the cup final</p></a>
      <p>Extra visible source text to keep this local fixture meaningful.</p></main>
      <a href='/hidden' style='display:none'>Invisible headline</a>
      <form><a href='/form-only'>Private form label</a><input value='fixture-secret'></form>""")
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    text = capture.page()["text"]
    for forbidden in (
        "SECRET HIDDEN",
        "Navigation only",
        "Invisible headline",
        "Private form",
        "fixture-secret",
    ):
        assert forbidden not in text
    assert any(b.kind == "link" and b.text == TITLE for b in capture.blocks)


def test_repeated_label_and_url_are_preserved_once_as_link_evidence(local_page):
    local_page.set_content(
        "<main>"
        + '<a href="/sport/cup-final"><p>'
        + TITLE
        + "</p></a>"
        + '<a href="/sport/cup-final"><span>'
        + TITLE
        + "</span></a>"
        + "<p>Additional visible fixture content explaining the match results.</p></main>"
    )
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    labels = [
        b for b in capture.blocks if b.kind == "link" and b.href == TARGET and b.text == TITLE
    ]
    assert len(labels) == 1


def test_late_nonheading_title_survives_early_secondary_text(local_page):
    labels = "".join(f"<p>Secondary label {i}</p>" for i in range(650))
    local_page.set_content(
        "<main>" + labels + '<a href="/sport/cup-final"><p>' + TITLE + "</p></a></main>"
    )
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    assert any(b.kind == "link" and b.text == TITLE and b.href == TARGET for b in capture.blocks)
    assert capture.truncated and len(capture.blocks) <= 600
    assert sum(len(b.text) + len(b.href or "") for b in capture.blocks) <= 24000


def test_long_visible_link_label_is_not_truncated_to_discovery_display_length(local_page):
    title = TITLE + " with further literal headline detail" * 6
    local_page.set_content("<main><a href='/sport/cup-final'><p>" + title + "</p></a></main>")
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    assert local_page.evaluate(LINK_SNAPSHOT)[0]["title"] == title[:180]
    assert any(b.kind == "link" and b.text == title and b.href == TARGET for b in capture.blocks)
    rows, rejected, _ = validate(candidate(title), {**capture.page(), "source_kind": "index"})
    assert not rejected and rows[0]["article_title"] == title
