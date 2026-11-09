"""Optional source amounts may be reviewed; actual price/stay criteria still gate save."""

import json
from copy import deepcopy

import pytest

from agentic_web_demo import custom_service
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.pricing import price_comparison_requested
from test_dashboard import finished
from test_pricing_workflow import BASE_REQUEST, real_pricing_fixture, service


def test_manual_price_filters_and_pinned_nightly_fields_require_price_verification():
    assert not price_comparison_requested(BASE_REQUEST)
    assert price_comparison_requested(BASE_REQUEST, [{"field": "price", "operator": "lt", "value": "300"}])
    assert price_comparison_requested(BASE_REQUEST, output_fields=["hotel_name", "price_per_night"])


def unlabelled_price_plan(service, monkeypatch, suffix=""):
    values, model, page = real_pricing_fixture()
    values = values.model_copy(update={"instructions": BASE_REQUEST + suffix})
    model = model.model_copy(update={
        "filters": [], "columns": [column for column in model.columns if column.name != "price_basis"],
        "rows": [row.model_copy(update={"cells": [cell for cell in row.cells if cell.field != "price_basis"]})
                 for row in model.rows],
    })
    page["blocks"][1]["text"] = "600 USD"
    page["text"] = "North Hotel has rooms shown in the returned hotel list. Its displayed source amount is 600 USD."
    monkeypatch.setattr(custom_service, "read_pages", lambda *_: [deepcopy(page)])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model, {"model": "fixture"}))
    return finished(service, custom_service.plan(service, values, object()))


def test_inferred_price_does_not_invent_a_nightly_condition_and_roundtrips_save(service, monkeypatch):
    planned = unlabelled_price_plan(service, monkeypatch)
    assert planned["status"] == "awaiting_review"
    proposal = planned["result"]["proposal"]
    assert proposal["review_counts"]["matched"] == 1
    assert proposal["review_counts"]["constraint_unverified"] == 0
    assert proposal["pricing_summary"]["target_requested"] is False
    row = proposal["records"][0]
    assert row["price"] == "600" and row["pricing"]["currency"] == "USD"
    assert row["pricing"]["status"] == "unverified"
    assert row["pricing"]["issues"] == ["price_basis_unverified"]
    assert row["pricing_combined_nightly"] is None and row["pricing_budget_status"] == "not_requested"
    saved = finished(service, custom_service.execute(
        service, proposal["plan_id"], planned["result"]["revision"], accept_partial=True
    ))
    assert saved["status"] == "completed"
    snapshot = json.loads((service.data_dir / "exports" / f"{saved['result']['run_id']}.json").read_text(encoding="utf-8"))
    assert snapshot["records"][0]["pricing"] == row["pricing"]


@pytest.mark.parametrize("suffix", [
    "Include nightly prices.", "Try to find prices around 250-350 USD nightly.",
])
def test_actual_nightly_requests_and_soft_targets_stay_readonly(service, monkeypatch, suffix):
    planned = unlabelled_price_plan(service, monkeypatch, suffix)
    assert planned["status"] == "needs_input" and "proposal" not in planned["result"]
    assert planned["result"]["review_counts"]["constraint_unverified"] == 1
    assert not list((service.data_dir / "exports").glob("*.json"))


def test_optional_price_does_not_allow_changed_stay_proof_at_save(service, monkeypatch):
    planned = unlabelled_price_plan(service, monkeypatch)
    proposal = planned["result"]["proposal"]
    proposal["pricing_sources"][0]["browser_task_context"]["result_scope"]["observed"]["adults"] = 2
    custom_service.write_json(service.data_dir / "website-plans" / f"{proposal['plan_id']}.json", proposal)
    with pytest.raises(WebsiteError, match="returned stay"):
        custom_service.execute(service, proposal["plan_id"], custom_service.digest(proposal), accept_partial=True)
    assert not list((service.data_dir / "exports").glob("*.json"))

