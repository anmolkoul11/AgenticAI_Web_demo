"""Disjoint batch extraction retains all rows and same-URL source identities."""

from copy import deepcopy

import pytest

from agentic_web_demo.custom_extract import Extraction, WebsiteInput
from agentic_web_demo.extraction_batches import interpret_result_batches
from agentic_web_demo.pricing import assess_pricing
from test_all_result_collection import ResultTools, collector
from test_page_price_setting import PROMPT, price_fixture


def test_sixty_source_records_are_extracted_in_six_non_overlapping_paid_batches():
    sources = collector(ResultTools([list(range(60))])).run()
    values = WebsiteInput(source="extension", urls=["https://example.org/results"],
                          instructions="Get hotel listings", collection_extent="all_results", record_limit=5000,
                          workflow_mode="automatic", agent_confirmed=True,
                          authorized=True, allow_model_api=True)
    calls = []
    def interpret(batch, pages, settings, *, column_contract=None):
        calls.append(batch.output_fields)
        if calls[:-1]:
            assert column_contract[0]["name"] == "hotel_name"
        headings = [block for block in pages[0]["blocks"] if block.get("association") == "record" and block["kind"] == "heading"]
        return Extraction.model_validate({
            "outcome": "ready", "guidance": "Review", "content_type": "hotels", "interpretation": "Source records",
            "columns": [{"name": "hotel_name", "kind": "text", "unit": "", "description": "Source hotel name"}],
            "filters": [], "rows": [{"page_index": 0, "cells": [{"field": "hotel_name", "value": item["text"], "evidence": item["text"]}]} for item in headings],
            "warnings": [], "more_records_available": False,
        }), {"provider": "fixture", "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}
    result, metadata = interpret_result_batches(values, sources, object(), interpret, lambda _: None, lambda: True)
    assert len(result.rows) == 60 and len(calls) == 6
    assert calls[0] == [] and all(names == ["hotel_name"] for names in calls[1:])
    assert {row.page_index for row in result.rows} == set(range(6))
    assert metadata["usage"]["total_tokens"] == 900
    assert metadata["extraction_batches"]["complete"]


def test_price_validation_uses_the_correct_capture_when_windows_share_a_url():
    row, page, columns = price_fixture()
    first, second = deepcopy(page), deepcopy(page)
    first["capture_id"], second["capture_id"] = "batch-one", "batch-two"
    first["blocks"][0]["text"] = "Another Hotel"
    first["blocks"][1]["text"] = "$999"
    row["source_capture_id"] = "batch-two"
    price = assess_pricing([row], [first, second], PROMPT, columns)["records"][0]["pricing"]
    assert price["status"] == "verified" and price["displayed_amount"] == "106"


def test_paragraph_headlines_count_as_returned_groups_without_counting_body_mentions():
    title = "The team reaches its first championship final"
    page = {"url": "https://example.org/", "text": title, "blocks": [
        {"id": "b1", "kind": "paragraph", "text": title, "association": "record", "group_id": "g1"},
        {"id": "b2", "kind": "paragraph", "text": "A separate story mentions " + title,
         "association": "record", "group_id": "g2"},
    ], "coverage": {"record_window": True}}
    values = WebsiteInput(source="extension", urls=[page["url"]], instructions="Get sports articles",
                          collection_extent="all_results", record_limit=50,
                          workflow_mode="automatic", agent_confirmed=True,
                          authorized=True, allow_model_api=True)

    def interpret(batch, pages, settings, *, column_contract=None):
        return Extraction.model_validate({
            "outcome": "ready", "guidance": "Review", "content_type": "articles",
            "interpretation": "Captured article", "warnings": [], "more_records_available": False,
            "columns": [{"name": "article_title", "kind": "text", "unit": "", "description": "Headline"}],
            "filters": [], "rows": [{"page_index": 0, "cells": [
                {"field": "article_title", "value": title, "evidence": title},
            ]}],
        }), {"usage": {}}

    _, metadata = interpret_result_batches(values, [page], object(), interpret, lambda _: None, lambda: True)
    assert metadata["extraction_batches"]["source_coverage"] == [
        {"batch": 1, "source_groups": 2, "returned_groups": 1, "unreturned_groups": 1},
    ]


@pytest.mark.parametrize("content_type", ["articles", "audio"])
def test_selected_headline_counts_one_episode_instead_of_every_repeated_programme_label(content_type):
    page = {"url": "https://example.org/", "text": "Sports Daily First final Second final", "blocks": [
        {"id": "b1", "kind": "heading", "text": "Sports Daily", "association": "record", "group_id": "g1"},
        {"id": "b2", "kind": "heading", "text": "First final", "association": "record", "group_id": "g1"},
        {"id": "b3", "kind": "heading", "text": "Sports Daily", "association": "record", "group_id": "g2"},
        {"id": "b4", "kind": "heading", "text": "Second final", "association": "record", "group_id": "g2"},
    ], "coverage": {"record_window": True}}
    values = WebsiteInput(source="extension", urls=[page["url"]], instructions="Get sports articles",
                          collection_extent="all_results", record_limit=50,
                          workflow_mode="automatic", agent_confirmed=True,
                          authorized=True, allow_model_api=True)

    def interpret(batch, pages, settings, *, column_contract=None):
        return Extraction.model_validate({
            "outcome": "ready", "guidance": "Review", "content_type": content_type,
            "interpretation": "Captured article", "warnings": [], "more_records_available": False,
            "columns": [{"name": "article_title", "kind": "text", "unit": "", "description": "Headline"}],
            "filters": [], "rows": [{"page_index": 0, "headline_block_id": "b2", "label_block_ids": ["b1"],
                                      "cells": [{"field": "article_title", "value": "Sports Daily",
                                                 "evidence": "Sports Daily"}]}],
        }), {"usage": {}}

    candidate, metadata = interpret_result_batches(values, [page], object(), interpret, lambda _: None, lambda: True)
    assert candidate.rows[0].headline_block_id == "b2"
    assert metadata["extraction_batches"]["source_coverage"] == [
        {"batch": 1, "source_groups": 2, "returned_groups": 1, "unreturned_groups": 1},
    ]

