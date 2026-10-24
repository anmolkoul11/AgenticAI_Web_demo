"""Snapshot handoff regressions, authored for the user's opt-in manual run.

Only packaged popup code and mocked Chrome APIs are used. These fixtures never
contact a website, dashboard, provider, or real extension session.
"""

from pathlib import Path

import pytest
from test_navigation_verification import local_page as shared_local_page


EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "page-capture"
CAPTURE = {"version": 1, "url": "https://news.example.org/world", "blocks": []}
ACCOUNT = {"authenticated": True, "username": "user1", "csrf": "csrf-fixture",
           "instance_id": "instance-fixture", "ui_version": "2026-10-19.2", "page_ready": True}
DASHBOARD = {"id": 2, "windowId": 4, "url": "http://127.0.0.1:8120/"}


def test_popup_requires_reviewed_account_and_actual_dashboard_receipt():
    script = (EXTENSION / "popup.js").read_text(encoding="utf-8")
    html = (EXTENSION / "popup.html").read_text(encoding="utf-8")
    assert 'id="dashboard-choice"' in html
    assert 'id="open-dashboard"' in html
    assert "if (dashboards.length === 1) selectedDashboard = dashboards[0]" in script
    assert "s.username !== expected.username" in script
    assert "s.csrf !== expected.csrf" in script
    assert "s.instance_id !== expected.instance_id" in script
    assert "dataset.agenticUiVersion !== s.ui_version" in script
    assert "dataset.agenticConnection !== 'ready'" in script
    assert "'X-Dashboard-Version': s.ui_version" in script
    assert "agentic-capture-received-v1" in script
    assert "data.transfer_id !== transferId" in script
    assert "data.capture_id !== body.capture_id" in script
    assert "event.source !== window || event.origin !== location.origin" in script
    assert "storage.session.clear" not in script
    assert "error.message ||" not in script


@pytest.fixture
def popup(shared_local_page):
    page = shared_local_page

    def load(*, pending=False, dashboards=None, session=None, result=None, interrupt=False,
             expired=False):
        page.set_content((EXTENSION / "popup.html").read_text(encoding="utf-8"))
        page.evaluate("""fixture => {
          window.fixtureCapture = fixture.capture;
          window.fixtureStored = {agenticTabSession:{run_id:'preserve-agent'}};
          if (fixture.pending) Object.assign(window.fixtureStored, {
            capture:fixture.capture, expires:Date.now() + (fixture.expired ? -1 : 600000)});
          window.fixtureCalls = [];
          const website = {id:1,windowId:4,url:'https://news.example.org/world'};
          const dashboards = fixture.dashboards;
          globalThis.captureDocument = function captureDocument() {};
          globalThis.chrome = {
            tabs: {
              query: async query => query.active ? [website] : [website,...dashboards],
              get: async id => [website,...dashboards].find(tab => tab.id === id),
              update: async (id, values) => window.fixtureCalls.push({type:'activate',id,values}),
              create: async values => window.fixtureCalls.push({type:'create',values}),
            },
            windows: {update:async (id,values) => window.fixtureCalls.push({type:'focus',id,values})},
            scripting: {executeScript: async details => {
              const name = details.func.name;
              window.fixtureCalls.push({type:name,target:details.target,args:details.args});
              if (name === 'sessionInfo') return [{result:fixture.session}];
              if (name === 'captureDocument') return [{result:fixture.capture}];
              if (name === 'sendCapture') {
                if (fixture.interrupt) throw new Error('private page data must not leak');
                return [{result:fixture.result}];
              }
              throw new Error('Unexpected fixture operation');
            }},
            storage: {session: {
              get: async keys => Object.fromEntries(keys.filter(key => key in window.fixtureStored)
                .map(key => [key,window.fixtureStored[key]])),
              set: async values => Object.assign(window.fixtureStored,values),
              remove: async keys => keys.forEach(key => delete window.fixtureStored[key]),
            }},
            runtime: {sendMessage:async () => ({ok:true})},
            sidePanel: {open:async () => {}},
          };
          window.close = () => { window.fixtureClosed = true; };
        }""", {"capture": CAPTURE, "pending": pending, "expired": expired,
                "dashboards": [DASHBOARD] if dashboards is None else dashboards,
                "session": ACCOUNT if session is None else session,
                "result": {"ok": True} if result is None else result,
                "interrupt": interrupt})
        page.add_script_tag(path=str(EXTENSION / "popup.js"))
        page.wait_for_function("document.getElementById('status').textContent !== 'Checking the selected tab...'")
        if pending and not expired:
            page.wait_for_function("!document.getElementById('open-dashboard').hidden")
        return page

    return load


def send_calls(page):
    return page.evaluate("fixtureCalls.filter(call => call.type === 'sendCapture')")


def test_keep_exposes_explicit_account_review_without_sending(popup):
    page = popup()
    page.locator("#capture").click()
    page.locator("#consent").check()
    page.locator("#keep").click()
    page.wait_for_function("!document.getElementById('send').hidden")
    assert "Snapshot kept" in page.locator("#pending-status").inner_text()
    assert "user1 at http://127.0.0.1:8120" in page.locator("#dashboard-account").inner_text()
    assert not page.locator("#consent").is_checked()
    assert page.evaluate("fixtureStored.capture.url") == CAPTURE["url"]
    assert send_calls(page) == []


def test_pending_capture_restores_on_website_and_can_open_dashboard(popup):
    page = popup(pending=True)
    assert "waiting for transfer" in page.locator("#status").inner_text()
    assert CAPTURE["url"] in page.locator("#preview").inner_text()
    page.locator("#open-dashboard").click()
    page.wait_for_function("window.fixtureClosed === true")
    assert page.evaluate("fixtureCalls.some(call => call.type === 'activate' && call.id === 2)")
    assert page.evaluate("fixtureCalls.some(call => call.type === 'focus' && call.id === 4)")
    assert send_calls(page) == []


def test_multiple_dashboard_tabs_require_explicit_selection(popup):
    page = popup(pending=True, dashboards=[DASHBOARD, {
        "id": 3, "windowId": 4, "url": "http://localhost:8120/"}])
    assert page.locator("#dashboard-choice").input_value() == ""
    assert page.locator("#send").is_hidden()
    page.locator("#dashboard-choice").select_option("3")
    assert "http://localhost:8120" in page.locator("#dashboard-account").inner_text()
    assert page.locator("#send").is_visible()
    assert not page.locator("#consent").is_checked()
    assert send_calls(page) == []


def test_explicit_send_targets_selected_dashboard_once_and_preserves_agent_state(popup):
    page = popup(pending=True)
    page.locator("#consent").check()
    page.locator("#send").click()
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Snapshot received.')")
    calls = send_calls(page)
    assert len(calls) == 1 and calls[0]["target"]["tabId"] == DASHBOARD["id"]
    assert page.evaluate("fixtureStored.capture === undefined && fixtureStored.expires === undefined")
    assert page.evaluate("fixtureStored.agenticTabSession.run_id") == "preserve-agent"
    assert "No model call was made" in page.locator("#status").inner_text()


def test_interrupted_delivery_is_retained_locked_and_not_automatically_retried(popup):
    page = popup(pending=True, interrupt=True)
    page.locator("#consent").check()
    page.locator("#send").click()
    page.wait_for_function("window.fixtureStored.snapshotTransfer?.state === 'unknown'")
    assert "acknowledgement was interrupted" in page.locator("#status").inner_text()
    assert "private page data" not in page.locator("#status").inner_text()
    assert page.evaluate("fixtureStored.capture.url") == CAPTURE["url"]
    page.locator("#find-dashboard").click()
    page.wait_for_function("document.getElementById('pending-status').textContent.includes('already attempted')")
    assert page.locator("#send").is_hidden()
    assert len(send_calls(page)) == 1


def test_changed_session_never_claims_sent_and_requires_new_account_confirmation(popup):
    page = popup(pending=True, result={"ok": False, "submitted": False, "stage": "session_changed"})
    page.locator("#consent").check()
    page.locator("#send").click()
    page.wait_for_function("document.getElementById('status').textContent.includes('Nothing was sent.')")
    assert page.evaluate("fixtureStored.capture.url") == CAPTURE["url"]
    assert page.evaluate("fixtureStored.snapshotTransfer === undefined")
    assert not page.locator("#consent").is_checked()
    assert page.locator("#send").is_hidden()


def test_old_or_unready_dashboard_cannot_receive_snapshot(popup):
    page = popup(pending=True, session={**ACCOUNT, "page_ready": False})
    assert "Refresh this dashboard" in page.locator("#dashboard-account").inner_text()
    assert page.locator("#send").is_hidden()
    assert page.locator("#open-dashboard").is_visible()
    assert send_calls(page) == []


def test_expired_capture_clears_only_snapshot_state(popup):
    page = popup(pending=True, expired=True)
    assert page.evaluate("fixtureStored.capture === undefined && fixtureStored.expires === undefined")
    assert page.evaluate("fixtureStored.agenticTabSession.run_id") == "preserve-agent"
    assert page.locator("#handoff").is_hidden()
    assert send_calls(page) == []
