"""Shared collection regressions. Browser fixtures are opt-in; no API/site requests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_web_demo.browser_links import LINK_SNAPSHOT, link_role_hint
from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_browser import (
    CONTENT_METRICS,
    BrowserControl,
    capture_rendered_page,
    prepare_browser_content,
)
from agentic_web_demo.custom_extract import (
    Condition,
    Extraction,
    WebsiteInput,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError


def payload(**changes):
    return {
        "version": 1,
        "url": "https://news.example.org/",
        "captured_at": datetime.now(UTC).isoformat(),
        "truncated": False,
        "blocks": [{"id": "b1", "kind": "paragraph", "text": "Visible source content. " * 5}],
        **changes,
    }


def coverage(text_count, **changes):
    return {
        "collector_version": "source-inventory-v1",
        "scope": "loaded_dom",
        "eligible_text_chars": text_count,
        "captured_text_chars": text_count,
        "omitted_text_chars": 0,
        "excluded_navigation_chars": 0,
        "unique_links_detected": 2,
        "links_returned": 2,
        "candidate_limit_reached": False,
        "frames_excluded": 0,
        "open_shadow_roots": 0,
        "record_groups": 1,
        "limit_reasons": [],
        "scroll_steps": 0,
        "at_page_end": True,
        "content_settled": False,
        "preparation": "manual_snapshot",
        **changes,
    }


def test_old_extension_capture_remains_compatible():
    capture = Capture.model_validate(payload())
    assert capture.coverage is None
    assert "coverage" not in capture.page()


def test_coverage_validates_counts_and_discloses_omission():
    data = payload()
    count = len(data["blocks"][0]["text"])
    data["coverage"] = coverage(count, omitted_text_chars=9)
    assert Capture.model_validate(data).page()["truncated"] is True
    data["coverage"] = coverage(count, limit_reasons=["block_limit"])
    assert Capture.model_validate(data).truncated is True
    for invalid in (
        coverage(count + 1),
        coverage(count, links_returned=3),
        coverage(count, scroll_steps=9),
    ):
        with pytest.raises(ValidationError):
            Capture.model_validate({**data, "coverage": invalid})


@pytest.mark.parametrize("steps", [0, 3, 8])
def test_browser_loading_steps_are_explicit_and_bounded(steps):
    values = WebsiteInput(
        source="browser",
        urls=["https://news.example.org/"],
        browser_scroll_steps=steps,
        authorized=True,
        allow_model_api=True,
    )
    assert values.browser_scroll_steps == steps


@pytest.mark.parametrize("steps", [-1, 9])
def test_invalid_loading_steps_are_rejected(steps):
    with pytest.raises(ValidationError):
        WebsiteInput(
            source="browser",
            urls=["https://news.example.org/"],
            browser_scroll_steps=steps,
            authorized=True,
            allow_model_api=True,
        )


def test_loading_steps_cannot_enable_browser_behavior_for_static_sources():
    with pytest.raises(ValidationError):
        WebsiteInput(
            source="public",
            urls=["https://news.example.org/"],
            browser_scroll_steps=0,
            authorized=True,
            allow_model_api=True,
        )


def test_deep_categories_stay_navigation_not_detail_records():
    assert link_role_hint("https://news.example.org/category/tech/technologies/phones") == "section"
    assert link_role_hint("https://news.example.org/tech/phones/new-device") == "unknown"


class LoadingPage:
    url = "https://news.example.org/"

    def __init__(self, *, unstable=False):
        self.position = {"x": 7, "y": 100}
        self.y = 100
        self.unstable = unstable
        self.samples = 0
        self.waits = []

    def locator(self, selector):
        return self

    def count(self):
        return 0

    def is_closed(self):
        return False

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

    def evaluate(self, script, argument=None):
        if script == CONTENT_METRICS:
            self.samples += 1
            return {
                "chars": 500,
                "links": 3,
                "height": 600,
                "ready": "complete",
                "signature": self.samples if self.unstable else 1,
                "at_end": self.y >= 400,
            }
        if "({x: scrollX" in script:
            return dict(self.position)
        if "scrollTo(0, 0)" in script:
            self.y = 0
        elif "scrollBy" in script:
            self.y += 200
        elif "scrollTo(p.x" in script:
            self.y = argument["y"]


def test_bounded_loading_scrolls_and_restores_operator_position():
    page, control = LoadingPage(), BrowserControl()
    result = prepare_browser_content(page, control, 3)
    assert result == {
        "scroll_steps": 2,
        "at_page_end": True,
        "content_settled": True,
        "preparation": "bounded_browser",
    }
    assert page.y == 100
    assert control.snapshot()["content_preparation"] == result
    assert all(wait == 250 for wait in page.waits)


def test_unstable_content_is_disclosed_without_unbounded_waiting():
    page = LoadingPage(unstable=True)
    result = prepare_browser_content(page, BrowserControl(), 0)
    assert result["content_settled"] is False
    assert result["scroll_steps"] == 0
    assert len(page.waits) <= 16


def test_cancel_stops_preparation_without_scroll_actions():
    page, control = LoadingPage(), BrowserControl()
    control.cancel.set()
    with pytest.raises(WebsiteError, match="cancelled"):
        prepare_browser_content(page, control, 3)
    assert page.y == 100
    assert page.samples == 0


def test_redaction_keeps_coverage_counts_consistent(monkeypatch):
    data = payload()
    data["coverage"] = coverage(len(data["blocks"][0]["text"]))

    class Page(LoadingPage):
        def evaluate(self, script, argument=None):
            assert argument == {}
            return data

    monkeypatch.setattr("agentic_web_demo.custom_browser.check_robots", lambda _: None)
    result = capture_rendered_page(Page(), "https://news.example.org", ["source"], [200])
    assert result["coverage"]["captured_text_chars"] == sum(
        len(b["text"]) for b in result["blocks"]
    )
    assert "[redacted]" in result["text"]


def extraction_for(fields):
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "records",
            "interpretation": "Source records",
            "filters": [],
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": name, "kind": "text", "unit": "", "description": name}
                for name, _ in fields
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": name, "value": value, "evidence": value} for name, value in fields
                    ],
                }
            ],
        }
    )


def grouped_page():
    blocks = [
        {"id": "b1", "text": "Hotel North", "group_id": "g1", "association": "record"},
        {
            "id": "b2",
            "text": "LOST IN TRANSLATION",
            "group_id": "g2",
            "association": "record",
        },
        {"id": "b3", "text": "250 USD", "group_id": "g2", "association": "record"},
    ]
    return {
        "url": "https://news.example.org/",
        "text": "\n".join(b["text"] for b in blocks),
        "blocks": blocks,
    }


def test_wrong_optional_metadata_is_blanked_not_attached_to_neighbor():
    page = grouped_page()
    values = WebsiteInput(
        source="public",
        urls=[page["url"]],
        instructions="Extract records",
        authorized=True,
        allow_model_api=True,
    )
    rejected, issues = [], []
    records, _ = validate_extraction(
        extraction_for([("name", "Hotel North"), ("section_label", "LOST IN TRANSLATION")]),
        values,
        [page],
        rejected=rejected,
        field_issues=issues,
    )
    assert not rejected
    assert records[0]["name"] == "Hotel North"
    assert records[0]["section_label"] is None
    assert issues[0]["issues"][0]["reason"] == "values_from_different_source_groups"


def test_wrong_filter_value_still_rejects_record():
    page = grouped_page()
    values = WebsiteInput(
        source="public",
        urls=[page["url"]],
        instructions="Extract records",
        authorized=True,
        allow_model_api=True,
    )
    candidate = extraction_for([("name", "Hotel North"), ("price", "250 USD")])
    candidate.filters = [Condition(field="price", operator="contains", value="250")]
    rejected = []
    records, _ = validate_extraction(candidate, values, [page], rejected=rejected, field_issues=[])
    assert records == []
    assert rejected[0]["issues"][0]["reason"] == "values_from_different_source_groups"


def test_ambiguous_optional_metadata_is_disclosed_and_blanked():
    page = grouped_page()
    page["blocks"][1].update(group_id=None, association="ambiguous")
    values = WebsiteInput(
        source="public",
        urls=[page["url"]],
        instructions="Extract records",
        authorized=True,
        allow_model_api=True,
    )
    issues = []
    records, _ = validate_extraction(
        extraction_for([("name", "Hotel North"), ("section_label", "LOST IN TRANSLATION")]),
        values,
        [page],
        rejected=[],
        field_issues=issues,
    )
    assert records[0]["section_label"] is None
    assert issues[0]["issues"][0]["reason"] == "ambiguous_record_association"


@pytest.fixture
def inventory_browser(request):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser for isolated local DOM fixtures")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.route(
            "**/*",
            lambda route: route.fulfill(status=200, content_type="text/html", body=""),
        )
        page = context.new_page()
        page.goto("https://news.example.org/")
        yield page
        browser.close()


COLLECTOR = (
    Path(__file__).resolve().parents[1] / "src/agentic_web_demo/dashboard/static/capture_dom.js"
).read_text(encoding="utf-8")


def test_inventory_covers_body_and_merges_kicker_with_real_heading(inventory_browser):
    page = inventory_browser
    page.set_content("""<main><p>Visible introduction with enough source text to represent the
      original main area that used to cause early termination of the page collector.</p></main>
      <article><a href='/story-one'>LOST IN TRANSLATION</a>
      <a href='/story-one'><h2>Technology researchers publish a new discovery</h2></a>
      <a href='/story-two'><h2>Another independent sports headline</h2></a></article>""")
    capture = Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))
    links = page.evaluate(LINK_SNAPSHOT)
    assert len(links) == 2
    assert links[0]["title"] == "Technology researchers publish a new discovery"
    assert "LOST IN TRANSLATION" in links[0]["labels"]
    assert "Another independent sports headline" in capture.page()["text"]
    first = next(b for b in capture.blocks if "new discovery" in b.text)
    second = next(b for b in capture.blocks if "sports headline" in b.text)
    assert first.group_id != second.group_id
    assert capture.coverage.unique_links_detected == 2


def test_inventory_pairs_hotel_metadata_with_primary_link(inventory_browser):
    page = inventory_browser
    page.set_content("""<main><div data-testid='property-card'>
      <a href='/hotel-north'><h2>Hotel North in central Boston</h2></a>
      <a href='/hotel-north/reviews'>Read customer reviews</a><p>150 USD nightly, rating 4.2</p>
      </div><div data-testid='property-card'>
      <a href='/hotel-south'><h2>Hotel South beside the harbor</h2></a>
      <p>250 USD nightly, rating 4.8</p></div></main>""")
    capture = Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))

    def group_of(text):
        return next(b.group_id for b in capture.blocks if text in b.text)

    assert group_of("Hotel North") == group_of("150 USD")
    assert group_of("Hotel South") == group_of("250 USD")
    assert group_of("Hotel North") != group_of("Hotel South")


def test_inventory_collects_open_shadow_content_not_form_values(inventory_browser):
    page = inventory_browser
    page.set_content("""<p>Visible introduction with enough information to produce a meaningful
      captured source document for this local fixture only.</p><div id='host'></div>
      <form><input value='fixture-secret'><p>Do not capture form content</p></form>""")
    page.evaluate("""() => document.getElementById('host').attachShadow({mode:'open'}).innerHTML =
      '<a href="/shadow-story"><h2>Research result inside an open shadow root</h2></a>'""")
    capture = Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))
    assert "Research result" in capture.page()["text"]
    assert "form content" not in capture.page()["text"]
    assert "fixture-secret" not in capture.page()["text"]
    assert capture.coverage.open_shadow_roots == 1
    assert page.evaluate(LINK_SNAPSHOT)[0]["url"].endswith("/shadow-story")


def test_inventory_limits_are_visible_not_claimed_complete(inventory_browser):
    page = inventory_browser
    page.set_content(
        "<main>"
        + "".join(f"<p>Record {i}: " + "source text " * 15 + "</p>" for i in range(220))
        + "</main>"
    )
    capture = Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))
    assert capture.truncated is True
    assert capture.coverage.omitted_text_chars > 0
    assert capture.coverage.limit_reasons
    assert len(capture.blocks) <= 600
    assert sum(len(b.text) + len(b.href or "") for b in capture.blocks) <= 24000
