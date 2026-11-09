"""Disjoint batch extraction retains all rows and same-URL source identities."""

from copy import deepcopy

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

