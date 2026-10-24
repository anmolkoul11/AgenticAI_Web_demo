"""Offline HTTP fixtures for extension ownership and existing preview reuse."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard import SETTINGS, finished, login

from agentic_web_demo import custom_service
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_extract import Extraction, WebsiteInput
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


def start_fields():
    return {"url": "https://example.org/listings", "tab_id": 7,
            "instructions": "Get item names", "agent_confirmed": True,
            "authorized": True, "allow_model_api": True}


def test_extension_start_requires_session_csrf_instance_and_api_connection(client, monkeypatch):
    assert client.post("/api/extension/runs", json=start_fields()).status_code == 401
    headers = login(client)
    assert client.post("/api/extension/runs", json=start_fields(), headers=headers).status_code == 409
    session = client.get("/api/session").json()
    headers["X-Dashboard-Instance"] = session["instance_id"]
    assert client.post("/api/extension/runs", json=start_fields(), headers=headers).status_code == 400
    account = client.app.state.accounts
    current = next(iter(account.sessions.values()))
    current.model_settings = SimpleNamespace(model="fixture", api_key="fixture-not-a-real-key")
    calls = []
    monkeypatch.setattr(custom_service, "plan", lambda *args, **kwargs: calls.append(kwargs) or str(uuid4()))
    response = client.post("/api/extension/runs", json=start_fields(), headers=headers)
    assert response.status_code == 202
    assert set(response.json()) == {"run_id", "job_id", "instance_id"}
    assert calls[0]["extension_reader"]
    assert isinstance(calls[0]["browser_control"], BrowserControl)
    assert "fixture-not-a-real-key" not in response.text
    assert client.post("/api/extension/runs", json=start_fields(), headers={**headers, "Origin": "https://example.org"}).status_code == 403


def test_extension_source_cannot_launch_through_ordinary_plan_route(client):
    headers = login(client)
    payload = {key: value for key, value in start_fields().items() if key not in {"url", "tab_id"}}
    payload.update(source="extension", urls=["https://example.org/"], workflow_mode="automatic")
    response = client.post("/api/custom/plans", json=payload, headers=headers)
    assert response.status_code == 400


def test_extension_reader_reuses_extraction_preview_without_managed_browser(service, monkeypatch):
    values = WebsiteInput(source="extension", urls=["https://example.org/listings"],
                          workflow_mode="automatic", instructions="Get item names",
                          agent_confirmed=True, authorized=True, allow_model_api=True)
    source = "North item is available in blue. " + "Additional visible page context. " * 4
    candidate = Extraction(outcome="ready", guidance="Review", content_type="items",
        interpretation="Visible item", warnings=[], more_records_available=False,
        columns=[{"name": "item_name", "kind": "text", "unit": "", "description": "Name"}],
        filters=[], rows=[{"page_index": 0, "cells": [
            {"field": "item_name", "value": "North item", "evidence": "North item"}]}])
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate, {"model": "fixture"}))
    monkeypatch.setattr(custom_service, "read_browser", lambda *_: pytest.fail("Managed browser must not open"))
    control = BrowserControl()

    def reader(*_):
        control.update("captured", "Selected tab stays open")
        return [{"url": values.urls[0], "text": source, "truncated": False}]

    job = finished(service, custom_service.plan(service, values, object(),
                   extension_reader=reader, browser_control=control))
    assert job["status"] == "awaiting_review"
    assert job["source"] == "extension"
    assert service.history()[0]["source"] == "extension"
    assert job["result"]["proposal"]["source"] == "extension"
    assert job["result"]["proposal"]["records"][0]["item_name"] == "North item"
    assert not service.browser_controls
    assert control.snapshot()["state"] == "captured"
    assert not control.cancel.is_set()
    assert not list((service.data_dir / "website-runs").glob("*"))


def test_extension_result_large_body_allowance_is_not_global(client):
    headers = login(client)
    headers["X-Dashboard-Instance"] = client.get("/api/session").json()["instance_id"]
    body = {"request_id": "a" * 32, "ok": True, "result": {"padding": "x" * 20_000}}
    endpoint = "/api/extension/runs/" + "b" * 32
    assert client.post(endpoint + "/result", json=body, headers=headers).status_code == 404
    assert client.post(endpoint + "/control", json=body, headers=headers).status_code == 413
