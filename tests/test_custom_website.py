"""Offline fixtures only; no live website or model requests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard import SETTINGS, finished, login

from agentic_web_demo import custom_service
from agentic_web_demo.custom_extract import Extraction, WebsiteInput, validate_extraction
from agentic_web_demo.custom_fetch import PageText, WebsiteError, public_addresses, public_url
from agentic_web_demo.dashboard.app import create_app
from agentic_web_demo.dashboard.service import DashboardService


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


@pytest.fixture
def client(service):
    with TestClient(create_app(SETTINGS, service), base_url="http://localhost") as browser:
        browser.app.state.accounts.register("demo", SETTINGS.password)
        yield browser


def source(**changes):
    return WebsiteInput(
        **{
            "source": "paste",
            "urls": ["https://example.org/hotels"],
            "page_text": "Boston hotel North costs 150 USD rating 4.2. "
            "Boston hotel South costs 250 USD rating 4.8. Boston Other costs 300 USD.",
            "instructions": "Boston hotels between 150 and 250 USD",
            "authorized": True,
            "allow_model_api": True,
            **changes,
        }
    )


def candidate():
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "hotels",
            "interpretation": "Hotels priced 150-250 USD inclusive",
            "warnings": [],
            "more_records_available": False,
            "columns": [{"name": "price", "kind": "number", "unit": "USD", "description": "Price"}],
            "filters": [
                {"field": "price", "operator": "gte", "value": "150"},
                {"field": "price", "operator": "lte", "value": "250"},
            ],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [{"field": "price", "value": value, "evidence": value + " USD"}],
                }
                for value in ["150", "250", "300"]
            ],
        }
    )


def test_inclusive_range_without_demo_ceiling():
    values = source()
    records, excluded = validate_extraction(
        candidate(), values, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert [r["price"] for r in records] == ["150", "250"]
    assert excluded == 1


def test_preview_limit_applies_after_verified_filters():
    result = candidate()  # Three candidates; the requested price range accepts two.
    values = source(record_limit=2)
    records, excluded = validate_extraction(
        result, values, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert len(records) == 2
    assert excluded == 1

    values = source(record_limit=1)
    with pytest.raises(
        WebsiteError, match="2 source-verified matching records exceed your preview limit of 1"
    ):
        validate_extraction(
            result, values, [{"url": values.urls[0], "text": values.page_text}]
        )


def test_preview_discloses_raw_candidates_over_limit(service, monkeypatch):
    monkeypatch.setattr(
        custom_service, "interpret", lambda *_: (candidate(), {"model": "fixture"})
    )
    job = finished(service, custom_service.plan(service, source(record_limit=2), object()))
    assert job["status"] == "awaiting_review"
    assert len(job["result"]["proposal"]["records"]) == 2
    assert any(
        "3 candidate records" in warning
        for warning in job["result"]["proposal"]["warnings"]
    )


def test_empty_instructions_must_not_add_filters():
    values = source(instructions="")
    with pytest.raises(WebsiteError, match="added filters"):
        validate_extraction(
            candidate(), values, [{"url": values.urls[0], "text": values.page_text}]
        )
    result = candidate()
    result.filters = []
    records, _ = validate_extraction(
        result, values, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert len(records) == 3


def test_fabricated_values_are_not_accepted():
    values, result = source(), candidate()
    result.rows[0].cells[0].value = "175"
    with pytest.raises(WebsiteError, match="source evidence"):
        validate_extraction(result, values, [{"url": values.urls[0], "text": values.page_text}])


def test_opened_article_page_url_is_source_evidence():
    article = "https://example.org/research/new-battery"
    values = source(
        urls=[article],
        instructions="Get this research article",
        page_text="A new battery result reports longer cell life after repeated charge cycles. "
        "The research team published its findings this week.",
    )
    result = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Research article",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": "article_title", "kind": "text", "unit": "", "description": "Title"},
                {"name": "article_url", "kind": "text", "unit": "", "description": "URL"},
            ],
            "filters": [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {
                            "field": "article_title",
                            "value": "A new battery result",
                            "evidence": "A new battery result",
                        },
                        {"field": "article_url", "value": article, "evidence": article},
                    ],
                }
            ],
        }
    )
    records, excluded = validate_extraction(
        result, values, [{"url": article, "text": values.page_text}]
    )
    assert excluded == 0
    assert records[0]["article_url"] == article
    assert records[0]["source_url"] == article

    result.rows[0].cells[1].value = "https://example.org/research/invented"
    with pytest.raises(WebsiteError, match="source evidence"):
        validate_extraction(result, values, [{"url": article, "text": values.page_text}])


def test_index_headline_preview_warns_linked_articles_were_not_opened(
    service, monkeypatch
):
    article = "https://example.org/sport/article-one"
    values = source(
        urls=["https://example.org/news"],
        instructions="Get sports article headlines from this page",
        page_text=f"Sports headline. {article} More news and website content here.",
    )
    result = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Sports headlines visible on the index",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": "article_title", "kind": "text", "unit": "", "description": "Title"},
                {"name": "article_url", "kind": "text", "unit": "", "description": "URL"},
            ],
            "filters": [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {
                            "field": "article_title",
                            "value": "Sports headline",
                            "evidence": "Sports headline",
                        },
                        {"field": "article_url", "value": article, "evidence": article},
                    ],
                }
            ],
        }
    )
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (result, {"model": "fixture"}))
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "awaiting_review"
    proposal = job["result"]["proposal"]
    assert proposal["records"][0]["source_url"] == values.urls[0]
    assert any("linked pages were not opened" in warning for warning in proposal["warnings"])


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254",
        "https://user:pass@example.org",
        "file:///etc/passwd",
        "https://example.org:8443",
        "http://localhost",
    ],
)
def test_unsafe_urls(url):
    with pytest.raises(WebsiteError):
        public_url(url)


def test_mixed_private_dns_is_blocked(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(WebsiteError, match="DNS"):
        public_addresses("example.org", 443)


def test_reader_ignores_scripts_and_login_forms():
    parser = PageText()
    parser.feed(
        "<p>Article text</p><script>steal()</script><form>Secret<input value='secret'></form>"
    )
    text = "".join(parser.parts)
    assert "Article text" in text and "steal" not in text and "Secret" not in text


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_preview_save_and_one_attempt(service, monkeypatch, framework):
    monkeypatch.setattr(custom_service, "interpret", lambda *a: (candidate(), {"model": "fixture"}))
    values = source(framework=framework)
    proposal_job = finished(service, custom_service.plan(service, values, object()))
    assert proposal_job["status"] == "awaiting_review", proposal_job
    result = proposal_job["result"]
    plan_id, revision = result["proposal"]["plan_id"], result["revision"]
    with pytest.raises(WebsiteError):
        custom_service.execute(service, plan_id, "0" * 64)
    job = finished(service, custom_service.execute(service, plan_id, revision))
    assert job["status"] == "completed", job
    assert service.records(job["job_id"])["records"][1]["price"] == "250"
    assert job["result"]["delivery"]["published"] == 0
    replay = finished(service, custom_service.execute(service, plan_id, revision))
    assert replay["status"] == "failed"


def test_expired_plan_does_not_save(service):
    plan_id = str(uuid4())
    proposal = {
        "plan_id": plan_id,
        "framework": "langgraph",
        "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    }
    custom_service.write_json(service.data_dir / "website-plans" / f"{plan_id}.json", proposal)
    job = finished(
        service, custom_service.execute(service, plan_id, custom_service.digest(proposal))
    )
    assert job["status"] == "failed"
    assert not (service.data_dir / "website-records.sqlite3").exists()


def test_custom_api_requires_login_and_consent(client):
    assert client.post("/api/custom/plans", json=source().model_dump()).status_code == 401
    headers = login(client)
    payload = source().model_dump()
    payload["allow_model_api"] = False
    assert client.post("/api/custom/plans", json=payload, headers=headers).status_code == 422


def test_custom_plan_is_private(client):
    headers = login(client)
    accounts = client.app.state.accounts
    owner = accounts.authenticate("demo", SETTINGS.password)
    service = accounts.service_for(owner)
    plan_id = str(uuid4())
    custom_service.write_json(
        service.data_dir / "website-plans" / f"{plan_id}.json", {"plan_id": plan_id}
    )
    accounts.register("otheruser", SETTINGS.password)
    client.post("/api/logout", json={}, headers=headers)
    csrf = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost", "X-CSRF-Token": csrf}
    client.post(
        "/api/login", json={"username": "otheruser", "password": SETTINGS.password}, headers=headers
    )
    headers["X-CSRF-Token"] = client.get("/api/session").json()["csrf"]
    assert (
        client.post(
            f"/api/custom/plans/{plan_id}/execute", json={"revision": "0" * 64}, headers=headers
        ).status_code
        == 409
    )
