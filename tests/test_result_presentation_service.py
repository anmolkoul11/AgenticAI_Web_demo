"""Read-only saved-preview fixtures; no live browser or provider required."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agentic_web_demo.custom_extract import WebsiteInput
from agentic_web_demo.custom_service import write_json
from agentic_web_demo.dashboard.service import DashboardService


@pytest.fixture
def saved(tmp_path):
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    job_id, run_id, plan_id = (str(uuid4()) for _ in range(3))
    url = "https://example.org/catalog"
    row = {"listing_id": "record-0001", "product_name": "Item One", "warranty": None,
           "source_url": url, "evidence": {"product_name": "Item One", "warranty": ""}}
    snapshot = {"columns": ["listing_id", "product_name", "warranty", "source_url"],
                "records": [row], "output_contract": None}
    proposal = {"plan_id": plan_id, "urls": [url], "captured_pages": [{"source_url": url}],
                "source_columns": [{"name": "product_name"}, {"name": "warranty"}],
                "source_blocks": [[
                    {"id": "b1", "group_id": "g1", "kind": "heading", "text": "Item One"},
                    {"id": "b2", "group_id": "g1", "kind": "text", "text": "Two year warranty"},
                    {"id": "b3", "group_id": "g2", "kind": "text", "text": "Lifetime warranty"},
                ]]}
    service.write({"job_id": job_id, "kind": "custom-execute", "plan_id": plan_id,
                   "result": {"run_id": run_id}})
    export_path = service.data_dir / "exports" / f"{run_id}.json"
    plan_path = service.data_dir / "website-plans" / f"{plan_id}.json"
    write_json(export_path, snapshot)
    write_json(plan_path, proposal)
    yield service, job_id, export_path, plan_path
    service.close()


def test_historical_presentation_never_rewrites_exports_or_fills_nulls(saved):
    service, job_id, export_path, plan_path = saved
    original_export, original_plan = export_path.read_bytes(), plan_path.read_bytes()
    preview = service.preview_records(job_id)
    row = preview["records"][0]
    assert row["warranty"] is None
    assert [item["text"] for item in row["source_coverage"]["additional_details"]] == [
        "Two year warranty"
    ]
    assert preview["output_contract"]["presentation"]["sections"]
    assert export_path.read_bytes() == original_export
    assert plan_path.read_bytes() == original_plan
    assert "source_coverage" not in service.records(job_id)["records"][0]
    assert json.loads(original_export)["records"][0] == service.records(job_id)["records"][0]


def test_missing_historical_plan_keeps_saved_record_available(saved):
    service, job_id, _, _ = saved
    job = service.read(job_id)
    job["plan_id"] = str(uuid4())
    service.write(job)
    preview = service.preview_records(job_id)
    assert preview["records"][0]["product_name"] == "Item One"
    assert "source_coverage" not in preview["records"][0]
    fields = [field for section in preview["output_contract"]["presentation"]["sections"]
              for field in section["fields"]]
    assert fields == ["product_name", "warranty"]


def test_source_coverage_cannot_be_requested_as_a_model_field():
    with pytest.raises(ValueError, match="reserved|field|Field"):
        WebsiteInput(framework="langgraph", source="paste", urls=["https://example.org/"],
                     page_text="Some public source content " * 5, instructions="Extract records",
                     output_fields=["source_coverage"], authorized=True, allow_model_api=True)
