"""Source ownership fixtures for multiple updates sharing an identical URL."""

from agentic_web_demo.custom_extract import Extraction, WebsiteInput, prepare_extraction, validate_extraction


def test_shared_live_url_does_not_authorize_a_different_updates_teaser():
    url = "https://example.org/live/world"
    first = "Diplomatic talks resume"
    second = "New statement issued"
    first_teaser = "The first update describes the meeting and its participants."
    second_teaser = "The second update describes a newly published official statement."
    values = WebsiteInput(
        source="paste", urls=["https://example.org/news"],
        page_text="\n".join((first, first_teaser, second, second_teaser, url)),
        instructions="Extract the headline and teaser records.",
        authorized=True, allow_model_api=True,
    )
    candidate = Extraction.model_validate({
        "outcome": "ready", "guidance": "Review", "content_type": "news",
        "interpretation": "Source updates", "filters": [], "warnings": [],
        "more_records_available": False,
        "columns": [{"name": name, "description": name, "kind": "text", "unit": ""}
                    for name in ("headline", "url", "article_snippet")],
        "rows": [{"page_index": 0, "cells": [
            {"field": "headline", "value": first, "evidence": first},
            {"field": "url", "value": url, "evidence": url},
            {"field": "article_snippet", "value": second_teaser, "evidence": second_teaser},
        ]}],
    })
    candidate, effective, _ = prepare_extraction(candidate, values)
    blocks = [
        {"id": "b1", "kind": "heading", "text": first, "href": url, "group_id": "g1", "association": "record"},
        {"id": "b2", "kind": "paragraph", "text": first_teaser, "group_id": "g1", "association": "record"},
        {"id": "b3", "kind": "heading", "text": second, "href": url, "group_id": "g2", "association": "record"},
        {"id": "b4", "kind": "paragraph", "text": second_teaser, "group_id": "g2", "association": "record"},
    ]
    issues = []
    rows, _ = validate_extraction(
        candidate, effective, [{"url": values.urls[0], "text": values.page_text, "blocks": blocks}],
        rejected=[], field_issues=issues,
    )
    assert rows[0]["headline"] == first
    assert rows[0]["article_snippet"] is None
    assert any(issue["reason"] == "values_from_different_source_groups"
               for issue in issues[0]["issues"])
