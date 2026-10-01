"""Offline handoff and partial-result regressions. Run manually; no paid API calls."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_custom_website import candidate, source
from test_dashboard import SETTINGS, finished, login

from agentic_web_demo import custom_service
from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import (
    Cell,
    Column,
    Extraction,
    WebsiteInput,
    validate_extraction,
    value_supported,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService


def payload():
    return {
        "version": 1,
        "url": "https://example.org/hotels?private=token#secret",
        "captured_at": "2026-09-23T12:00:00Z",
        "truncated": False,
        "blocks": [{"id": "b1", "kind": "paragraph", "text": source().page_text, "href": None}],
    }


def test_capture_normalizes_urls_and_preserves_blocks():
    capture = Capture.model_validate(payload())
    assert capture.url == "https://example.org/hotels"
    assert capture.page()["text"] == source().page_text
    assert capture.page()["blocks"][0]["id"] == "b1"


@pytest.mark.parametrize(
    "change",
    [
        {"url": "http://127.0.0.1"},
        {"version": 2},
        {"cookies": "not-allowed"},
        {"blocks": []},
        {"captured_at": "2026-09-23T12:00:00"},
    ],
)
def test_capture_contract_rejects_invalid_or_secret_fields(change):
    with pytest.raises((ValueError, ValidationError)):
        Capture.model_validate({**payload(), **change})


def test_capture_rejects_duplicate_ids_and_excess_text():
    value = payload()
    value["blocks"] *= 2
    with pytest.raises(ValueError):
        Capture.model_validate(value)
    value["blocks"] = [{"id": f"b{i}", "kind": "text", "text": "x" * 6000} for i in range(5)]
    with pytest.raises(ValueError):
        Capture.model_validate(value)


def test_capture_source_cannot_mix_inputs():
    capture = Capture.model_validate(payload())
    values = source().model_dump()
    values.update(source="capture", capture=capture.model_dump(mode="json"), page_text="")
    assert WebsiteInput.model_validate(values).capture is not None
    values["page_text"] = "Conflicting input"
    with pytest.raises(ValueError):
        WebsiteInput.model_validate(values)


def test_capture_record_groups_reject_cross_card_values():
    values = source(instructions="List Boston hotels")
    page = {
        "url": values.urls[0],
        "text": "North Hotel 150 USD\nSouth Hotel 250 USD",
        "blocks": [
            {"id": "b1", "kind": "text", "text": "North Hotel 150 USD", "group_id": "g1"},
            {"id": "b2", "kind": "text", "text": "South Hotel 250 USD", "group_id": "g2"},
        ],
    }
    result = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "hotels",
            "interpretation": "Boston hotels",
            "columns": [
                {"name": "name", "kind": "text", "unit": "", "description": "Hotel name"},
                {"name": "price", "kind": "number", "unit": "USD", "description": "Price"},
            ],
            "filters": [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": "name", "value": "North Hotel", "evidence": "North Hotel"},
                        {"field": "price", "value": "250", "evidence": "250 USD"},
                    ],
                }
            ],
            "warnings": [],
            "more_records_available": False,
        }
    )
    rejected = []
    records, _ = validate_extraction(result, values, [page], rejected=rejected)
    assert records == []
    assert rejected[0]["issues"][-1]["reason"] == "values_from_different_source_groups"

    result.rows[0].cells[1] = Cell(field="price", value="150", evidence="150 USD")
    records, _ = validate_extraction(result, values, [page])
    assert [(row["name"], row["price"]) for row in records] == [("North Hotel", "150")]


def test_optional_composite_field_is_cleared_without_losing_verified_article():
    values = source(instructions="Find soccer articles")
    article = "https://example.org/sport/football/article"
    page = {
        "url": article,
        "text": "City win soccer final. Related topics Premier League Manchester City Football.",
    }
    result = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Soccer articles",
            "columns": [
                {"name": "article_title", "kind": "text", "unit": "", "description": "Headline"},
                {"name": "topic_tags", "kind": "text", "unit": "", "description": "Topics"},
            ],
            "filters": [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {
                            "field": "article_title",
                            "value": "City win soccer final",
                            "evidence": "City win soccer final",
                        },
                        {
                            "field": "topic_tags",
                            "value": "Premier League; Manchester City; Football",
                            "evidence": '"Related topics" ... "Premier League" ... "Football"',
                        },
                    ],
                }
            ],
            "warnings": [],
            "more_records_available": False,
        }
    )
    rejected, field_issues = [], []
    records, _ = validate_extraction(
        result, values, [page], rejected=rejected, field_issues=field_issues
    )
    assert not rejected
    assert records[0]["article_title"] == "City win soccer final"
    assert records[0]["source_url"] == article
    assert records[0]["topic_tags"] is None
    assert records[0]["evidence"]["topic_tags"] == ""
    assert field_issues[0]["issues"][0]["reason"] == "quote_missing_from_source"

    result.rows[0].cells[0] = Cell(
        field="article_title", value="Invented headline", evidence="Invented headline"
    )
    rejected, field_issues = [], []
    records, _ = validate_extraction(
        result, values, [page], rejected=rejected, field_issues=field_issues
    )
    assert not records and rejected
    assert not field_issues


def test_partial_validation_quarantines_whole_bad_record():
    values, result = source(), candidate()
    result.rows[0].cells[0].value = "175"
    rejected = []
    records, excluded = validate_extraction(
        result, values, [{"url": values.urls[0], "text": values.page_text}], rejected=rejected
    )
    assert [row["price"] for row in records] == ["250"]
    assert excluded == 1
    assert rejected[0]["issues"][0]["reason"] == "value_missing_from_quote"


@pytest.mark.parametrize(
    "value,evidence,expected",
    [
        ("1000", "USD 1,000.00", True),
        ("4", "rating 4.8", False),
        ("4", "rating 40", False),
        ("4.20", "rating 4.2", True),
    ],
)
def test_numeric_evidence_compares_whole_tokens(value, evidence, expected):
    column = Column(name="amount", description="Amount", kind="number", unit="USD")
    assert value_supported(Cell(field="amount", value=value, evidence=evidence), column) is expected


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_partial_requires_explicit_approval_and_exports_only_verified(
    service, monkeypatch, framework
):
    result = candidate()
    result.rows[0].cells[0].value = "175"
    monkeypatch.setattr(custom_service, "interpret", lambda *a: (result, {"model": "fixture"}))
    job = finished(service, custom_service.plan(service, source(framework=framework), object()))
    proposal = job["result"]["proposal"]
    assert proposal["partial"] and len(proposal["rejected_records"]) == 1
    args = (service, proposal["plan_id"], job["result"]["revision"])
    with pytest.raises(WebsiteError, match="partial"):
        custom_service.execute(*args)
    execution = finished(service, custom_service.execute(*args, accept_partial=True))
    saved = service.records(execution["job_id"])
    assert [r["price"] for r in saved["records"]] == ["250"]
    assert saved["partial"] and saved["rejected_count"] == 1


def test_all_rejected_returns_diagnostics_without_proposal(service, monkeypatch):
    result = candidate()
    for row in result.rows:
        row.cells[0].value = "999"
    monkeypatch.setattr(custom_service, "interpret", lambda *a: (result, {"model": "fixture"}))
    job = finished(service, custom_service.plan(service, source(), object()))
    assert job["status"] == "needs_input"
    assert "proposal" not in job["result"]
    assert len(job["result"]["rejected_records"]) == 3
    assert job["result"]["trace"][-1] == "review_content:needs_input"


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_capture_planning_uses_snapshot_without_network_fetch(service, monkeypatch, framework):
    capture = Capture.model_validate(payload())
    values = source().model_dump()
    values.update(
        source="capture", capture=capture.model_dump(mode="json"), page_text="", framework=framework
    )
    monkeypatch.setattr(custom_service, "read_pages", lambda *a: pytest.fail("No refetch"))

    def interpret_fixture(inputs, pages, settings):
        assert pages[0]["blocks"][0]["id"] == "b1"
        return candidate(), {"model": "fixture"}

    monkeypatch.setattr(custom_service, "interpret", interpret_fixture)
    job = finished(
        service, custom_service.plan(service, WebsiteInput.model_validate(values), object())
    )
    assert job["status"] == "awaiting_review"
    assert job["result"]["proposal"]["source_blocks"][0][0]["id"] == "b1"


def test_expired_session_prevents_capture_model_call(service, monkeypatch):
    monkeypatch.setattr(custom_service, "interpret", lambda *a: pytest.fail("No model call"))
    job = finished(
        service, custom_service.plan(service, source(), object(), session_alive=lambda: False)
    )
    assert job["status"] == "needs_input"
    assert job["result"]["trace"] == ["inspect_website:ok", "extract_content:failed"]


def test_handoff_requires_csrf_and_is_session_private_one_time(service, monkeypatch):
    monkeypatch.setattr(custom_service, "interpret", lambda *a: pytest.fail("No model call"))
    with TestClient(create_app(SETTINGS, service), base_url="http://localhost") as client:
        accounts = client.app.state.accounts
        accounts.register("demo", SETTINGS.password)
        assert client.post("/api/custom/captures", json=payload()).status_code == 401
        headers = login(client)
        assert client.post("/api/custom/captures", json=payload()).status_code == 403
        response = client.post("/api/custom/captures", json=payload(), headers=headers)
        assert response.status_code == 201
        capture_id = response.json()["capture_id"]
        path = f"/api/custom/captures/{capture_id}/claim"
        assert client.post(path, json={}, headers=headers).status_code == 200
        assert client.post(path, json={}, headers=headers).status_code == 404
        response = client.post("/api/custom/captures", json=payload(), headers=headers)
        other_id = response.json()["capture_id"]
        client.post("/api/logout", json={}, headers=headers)
        headers = login(client)
        assert (
            client.post(
                f"/api/custom/captures/{other_id}/claim", json={}, headers=headers
            ).status_code
            == 404
        )


def test_extension_permissions_are_narrow_and_dom_capture_matches_browser():
    root = Path(__file__).resolve().parents[1]
    folder = root / "extensions" / "page-capture"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
    assert "host_permissions" not in manifest and "content_scripts" not in manifest
    assert (folder / "capture_dom.js").read_bytes() == (
        root / "src/agentic_web_demo/dashboard/static/capture_dom.js"
    ).read_bytes()
    assert "parent.closest('a[href]')" in (folder / "capture_dom.js").read_text(
        encoding="utf-8"
    )
    assert "if (root === primary && budget >= 500) break;" in (
        folder / "capture_dom.js"
    ).read_text(encoding="utf-8")
