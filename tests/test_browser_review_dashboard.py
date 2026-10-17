"""Retained verification-browser fixtures; authored without execution.

API/service cases use in-process fakes only. UI cases reuse the isolated,
opt-in --run-browser fixture: no external website or model requests.
"""

import json
import threading
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_dashboard import SETTINGS, finished
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo import custom_service
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_extract import Extraction, WebsiteInput
from agentic_web_demo.dashboard.app import ASSETS, create_app
from agentic_web_demo.dashboard.service import DashboardService


def sign_in(client, username):
    csrf = client.get("/api/session").json()["csrf"]
    headers = {"Origin": "http://localhost", "X-CSRF-Token": csrf}
    response = client.post(
        "/api/login",
        json={"username": username, "password": SETTINGS.password},
        headers=headers,
    )
    assert response.status_code == 200
    return {**headers, "X-CSRF-Token": response.json()["csrf"]}


@pytest.fixture
def review_site(tmp_path):
    template = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    app = create_app(SETTINGS, template)
    accounts = app.state.accounts
    alice = accounts.register("alice", SETTINGS.password)
    accounts.register("bob", SETTINGS.password)
    with TestClient(app, base_url="http://localhost") as client:
        yield client, accounts.service_for(alice)
    template.close()


def retained_control(service, *, active=True, status="awaiting_review"):
    job_id = str(uuid4())
    service.write({
        "job_id": job_id, "kind": "custom-plan", "status": status,
        "stages": [], "result": {"status": status, "records": [{"name": "Frozen record"}]},
    })

    class ExtraPrivateState(BrowserControl):
        def snapshot(self):
            return {**super().snapshot(), "private_page_text": "private-page-sentinel"}

    control = ExtraPrivateState()
    control.snapshot_frozen = True
    control.update("reviewing" if active else "waiting", "Website open for comparison.")
    if active:
        control.review_open.set()
    with service.lock:
        service.browser_controls[job_id] = control
    return job_id, control


def test_retained_browser_list_requires_login_and_does_not_expose_full_page_state(review_site):
    client, service = review_site
    job_id, _ = retained_control(service)
    retained_control(service, active=False, status="running")
    assert client.get("/api/custom/browsers").status_code == 401
    sign_in(client, "alice")
    response = client.get("/api/custom/browsers")
    assert response.status_code == 200
    rows = response.json()["browsers"]
    assert len(rows) == 1 and rows[0]["job_id"] == job_id
    assert rows[0]["state"] == "reviewing" and rows[0]["snapshot_frozen"] is True
    assert set(rows[0]) <= {"job_id", "state", "guidance", "snapshot_frozen"}
    assert "private-page-sentinel" not in response.text


def test_retained_browser_listing_and_close_are_account_private(review_site):
    client, service = review_site
    job_id, control = retained_control(service)
    sign_in(client, "alice")
    assert client.get("/api/custom/browsers").json()["browsers"][0]["job_id"] == job_id
    bob_headers = sign_in(client, "bob")
    assert client.get("/api/custom/browsers").json() == {"browsers": []}
    assert client.get(f"/api/custom/jobs/{job_id}/browser").status_code == 404
    assert client.post(
        f"/api/custom/jobs/{job_id}/browser/close", json={}, headers=bob_headers
    ).status_code == 404
    assert not control.close_requested.is_set() and not control.cancel.is_set()


@pytest.mark.parametrize("job_status", ["awaiting_review", "needs_input", "completed"])
def test_close_after_terminal_collection_is_not_cancel_or_a_job_mutation(review_site, job_status):
    client, service = review_site
    job_id, control = retained_control(service, status=job_status)
    original = (service.directory / f"{job_id}.json").read_bytes()
    headers = sign_in(client, "alice")
    # Closing an authenticated website window still requires the usual CSRF check.
    assert client.post(f"/api/custom/jobs/{job_id}/browser/close", json={}).status_code == 403
    assert not control.close_requested.is_set()
    response = client.post(
        f"/api/custom/jobs/{job_id}/browser/close", json={}, headers=headers
    )
    assert response.status_code == 200 and response.json()["status"] == "requested"
    assert control.close_requested.is_set()
    assert not control.cancel.is_set()
    assert (service.directory / f"{job_id}.json").read_bytes() == original


@pytest.fixture
def review_ui(request):
    for page in shared_ui.__wrapped__(request):
        # Status polling is exercised explicitly below, without a background
        # timeout racing these isolated DOM assertions.
        page.evaluate("clearTimeout(verificationBrowserTimer)")
        yield page


def test_verification_browser_panel_survives_each_workflow_tab(review_ui):
    review_ui.evaluate("""() => {
      webSelected='different-selected-job';
      renderVerificationBrowsers([{job_id:'source-browser-job',state:'reviewing',
        snapshot_frozen:true,guidance:'Compare with the source'}]);
    }""")
    panel = review_ui.get_by_role("region", name="Browsers open for verification", exact=True)
    for tab in ("1. Source", "2. Workflow", "3. Results"):
        review_ui.get_by_role("tab", name=tab, exact=True).click()
        assert panel.is_visible()
        assert panel.get_by_role("heading", name="Verify in your browser", exact=True).is_visible()
    assert "captured snapshot" in panel.inner_text()
    assert "does not" in panel.inner_text() and "cancel extraction/saving" in panel.inner_text()
    assert review_ui.evaluate("""() => ({
      outsidePanels:![...studioPanels.values()].some(panel=>panel.contains(verificationBrowsersPanel)),
      selected:webSelected, calls:window.fixtureCalls
    })""") == {"outsidePanels": True, "selected": "different-selected-job", "calls": []}


def test_close_uses_original_browser_job_after_save_selects_a_new_job(review_ui):
    result = review_ui.evaluate("""async () => {
      renderVerificationBrowsers([{job_id:'original-browser-job',state:'reviewing',
        snapshot_frozen:true,guidance:'Compare the retained source'}]);
      window.fixtureSnapshot={records:[{listing_id:'record-1',title:'Frozen source title',
        source_url:'https://news.example.org/story',evidence:{title:'Frozen source title'}}],
        columns:['listing_id','title','source_url']};
      const before=JSON.stringify(window.fixtureSnapshot);
      previewQuality={};webTable(window.fixtureSnapshot.records,window.fixtureSnapshot.columns);
      const card=$('web-record-cards').firstElementChild;
      webSelected='new-save-job';setStudioStep('results');
      window.fixtureApi=async (path,data)=>({status:'requested'});
      await verificationBrowsersList.querySelector('button').onclick();
      return {calls:window.fixtureCalls,selected:webSelected,
        frozen:before===JSON.stringify(window.fixtureSnapshot),
        sameCard:card===$('web-record-cards').firstElementChild,
        disabled:verificationBrowsersList.querySelector('button').disabled,
        message:verificationBrowsersList.textContent};
    }""")
    assert result["calls"] == ["/api/custom/jobs/original-browser-job/browser/close"]
    assert result["selected"] == "new-save-job"
    assert result["frozen"] and result["sameCard"] and result["disabled"]
    assert "Captured results are unchanged" in result["message"]


def test_verification_status_poll_only_updates_small_browser_panel(review_ui):
    result = review_ui.evaluate("""async () => {
      webSelected='completed-save-job';setStudioStep('results');
      previewQuality={};
      webTable([{listing_id:'record-1',title:'Saved result',source_url:'https://news.example.org/'}],
        ['listing_id','title','source_url']);
      const card=$('web-record-cards').firstElementChild;
      let workflowRenders=0;
      const originalRender=renderWorkflow;
      renderWorkflow=(...args)=>{workflowRenders++;return originalRender(...args);};
      window.fixtureApi=async path=>({browsers:[{job_id:'original-browser-job',state:'reviewing',
        snapshot_frozen:true,guidance:'Verify'}]});
      await pollVerificationBrowsers();clearTimeout(verificationBrowserTimer);
      const first=verificationBrowsersList.firstElementChild;
      await pollVerificationBrowsers();clearTimeout(verificationBrowserTimer);
      return {calls:window.fixtureCalls,workflowRenders,
        sameCard:card===$('web-record-cards').firstElementChild,
        sameRow:first===verificationBrowsersList.firstElementChild,
        selected:webSelected,step:studioStep};
    }""")
    assert result == {
        "calls": ["/api/custom/browsers", "/api/custom/browsers"],
        "workflowRenders": 0, "sameCard": True, "sameRow": True,
        "selected": "completed-save-job", "step": "results",
    }


def test_verification_browser_script_does_not_recapture_or_redirect_the_result():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    retained = script.split("function renderVerificationBrowsers(", 1)[1].split(
        'sourcePanel.querySelector("h2")', 1
    )[0]
    assert "encodeURIComponent(browser.job_id)" in retained
    assert "/api/custom/browsers" in retained
    assert "/browser/close" in retained
    assert "webSelected" not in retained
    assert "customSelect(" not in retained and "customPoll(" not in retained
    assert "renderWorkflow(" not in retained and "webTable(" not in retained
    assert "/capture" not in retained and "agent_start" not in retained


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_retained_browser_does_not_hold_job_gate_or_block_approval_save(service, monkeypatch, framework):
    controls = []
    calls = []
    source_page = {
        "url": "https://example.org/catalog", "source_kind": "index", "truncated": False,
        "text": "Product One is the visible product name in this captured source. "
                "The catalogue record was captured before any subsequent manual website browsing.",
    }

    def fake_browser(values, control, model_settings):
        # A lifecycle stand-in, not a Playwright/browser execution. The owner
        # thread intentionally outlives read_browser and the plan/save jobs.
        control.snapshot_frozen = True
        control.review_open.set()
        control.update("reviewing", "Captured source remains open for verification.")

        def own_window():
            control.close_requested.wait()
            control.review_open.clear()
            control.worker_closed.set()
            control.update("closed", "Verification browser closed.")
            if control.on_closed:
                control.on_closed()

        control.owner_thread = threading.Thread(target=own_window, daemon=True)
        controls.append(control)
        control.owner_thread.start()
        return [deepcopy(source_page)]

    def fake_interpret(*_):
        calls.append("extract")
        return Extraction.model_validate({
            "outcome": "ready", "guidance": "Review captured product names",
            "content_type": "product_catalog", "interpretation": "Visible source product names",
            "columns": [{"name": "product_name", "kind": "text", "unit": "", "description": "Name"}],
            "rows": [{"page_index": 0, "cells": [{"field": "product_name", "value": "Product One",
                                                     "evidence": "Product One"}]}],
            "warnings": [], "filters": [], "more_records_available": False,
        }), {"model": "offline-fixture"}

    monkeypatch.setattr(custom_service, "read_browser", fake_browser)
    monkeypatch.setattr(custom_service, "interpret", fake_interpret)
    values = WebsiteInput(
        framework=framework, source="browser", login_mode="none",
        urls=[source_page["url"]], instructions="Get the visible product names.",
        authorized=True, allow_model_api=True,
    )
    try:
        job_id = custom_service.plan(service, values, object())
        planned = finished(service, job_id)
        assert planned["status"] == "awaiting_review"
        control = controls[0]
        assert service.browser_controls[job_id] is control
        assert control.owner_thread.is_alive() and control.review_open.is_set()
        assert not service.busy
        proposal = planned["result"]["proposal"]
        original_records = deepcopy(proposal["records"])
        # A user browsing elsewhere in the retained window cannot mutate the
        # already handed-off capture or implicitly run extraction again.
        source_page["text"] = "A later manual website view, not the frozen source."
        saved = finished(service, custom_service.execute(
            service, proposal["plan_id"], planned["result"]["revision"], accept_partial=True
        ))
        assert saved["status"] == "completed" and not service.busy
        assert service.browser_controls[job_id] is control and control.review_open.is_set()
        snapshot_path = service.data_dir / "exports" / f"{saved['result']['run_id']}.json"
        before = snapshot_path.read_bytes()
        assert json.loads(before)["records"][0]["product_name"] == "Product One"
        assert service.read(job_id)["result"]["proposal"]["records"] == original_records
        control.command("close")
        control.owner_thread.join(timeout=3)
        assert control.worker_closed.is_set() and job_id not in service.browser_controls
        assert not control.cancel.is_set()
        assert snapshot_path.read_bytes() == before and calls == ["extract"]
    finally:
        for control in controls:
            control.close_requested.set()
            control.owner_thread.join(timeout=3)
