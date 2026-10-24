"""Local current-tab source regressions, authored for manual execution only.

The existing browser fixture is opt-in and stubs all APIs; no provider calls.
"""

from pathlib import Path

import pytest
from test_dashboard_live_updates import live_ui as shared_ui


ASSETS = Path(__file__).resolve().parents[1] / "src/agentic_web_demo/dashboard/static"


@pytest.fixture
def source_ui(request):
    yield from shared_ui.__wrapped__(request)


def select_snapshot(page):
    page.locator("#web-source-alternatives").evaluate("element => element.open = true")
    page.locator("#web-source").select_option("capture")


def test_only_one_website_input_is_presented_for_existing_tab_paths():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    assert 'id="web-open-url" type="hidden" disabled' in html
    assert 'const entered = $("web-urls").value.trim();' in script
    assert "website.readOnly = captured;" in script
    assert "Browser Companion side panel, not the dashboard Run button" in html
    assert 'title: "Open a new browser"' in script
    assert 'title: "Use my current tab"' in script
    assert 'title: "Snapshot my tab"' not in script
    assert "Extract this page only" in html


def test_two_primary_choices_are_workflows_and_extraction_alternatives_are_collapsed(source_ui):
    choices = source_ui.locator(".source-choices button")
    assert choices.count() == 2
    assert choices.nth(0).get_by_text("Open a new browser", exact=True).is_visible()
    assert choices.nth(1).get_by_text("Use my current tab", exact=True).is_visible()
    assert source_ui.locator('[data-source="capture"]').count() == 0
    assert not source_ui.locator("#web-source-alternatives").evaluate("element => element.open")
    assert source_ui.locator("#web-source").is_hidden()
    source_ui.locator('[data-source="extension"]').click()
    assert source_ui.locator("#web-source-alternatives > summary").is_visible()
    source_ui.locator("#web-source-alternatives > summary").click()
    source_ui.locator("#web-source").select_option("capture")
    assert source_ui.locator("#web-source-alternatives").evaluate("element => element.open")
    assert source_ui.locator("#web-extension-preview").is_visible()
    assert "no automated navigation" in source_ui.locator("#web-source optgroup").nth(1).get_attribute("label")
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_snapshot_address_is_editable_before_receipt_and_run_waits_for_capture(source_ui):
    select_snapshot(source_ui)
    source_ui.fill("#web-urls", "https://news.example.org/")
    assert source_ui.input_value("#web-urls") == "https://news.example.org/"
    assert source_ui.locator("#web-urls").is_editable()
    assert source_ui.locator("#web-open-url").is_hidden()
    assert source_ui.locator("#web-open-normal-browser").is_visible()
    assert source_ui.locator("#web-create").is_disabled()
    assert source_ui.locator("#web-create").inner_text() == "Waiting for page capture"
    assert "Opening a website is not a capture" in source_ui.locator("#web-capture-state").inner_text()
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_snapshot_waiting_reason_is_accessible_and_transfer_steps_are_actionable(source_ui):
    select_snapshot(source_ui)
    assert source_ui.locator("#web-source").is_enabled()
    assert source_ui.locator("#web-browser-start-note").is_hidden()
    assert "Send to displayed dashboard account" in source_ui.locator("#web-create-help").inner_text()
    assert source_ui.locator("#web-create").get_attribute("aria-describedby") == "web-create-help"
    source_ui.locator("#web-show-capture-steps").click()
    assert source_ui.locator("#web-capture-steps").evaluate("element => element.open")
    assert "Keeping alone does not send it" in source_ui.locator("#web-capture-steps").inner_text()
    assert "Use my current tab" in source_ui.locator("#web-capture-steps").inner_text()
    assert source_ui.locator("#web-create").is_disabled()
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_snapshot_receipt_enables_extraction_without_automatic_navigation_options(source_ui):
    source_ui.evaluate("""() => {
      window.fixtureReceipt = null;
      window.fixtureApi = async path => {
        if (path.endsWith('/claim')) return {url:'https://news.example.org/world',
          blocks:[{id:'b1',text:'World politics headline'}]};
        throw new Error('Unexpected fixture API operation');
      };
      window.addEventListener('message', event => {
        if (event.data?.type === 'agentic-capture-received-v1') window.fixtureReceipt = event.data;
      });
      $('web-framework').value = 'crewai';
      $('web-workflow-visual').checked = true;
      window.postMessage({type:'agentic-capture-ready-v1',
        capture_id:'12345678-1234-1234-1234-123456789abc',
        transfer_id:'87654321-4321-4321-4321-cba987654321'}, location.origin);
    }""")
    source_ui.wait_for_function("window.fixtureReceipt?.ok === true")
    assert source_ui.locator("#web-source").input_value() == "capture"
    assert source_ui.locator("#web-source-alternatives").evaluate("element => element.open")
    assert source_ui.locator("#web-create").is_enabled()
    assert source_ui.locator("#web-create").is_visible()
    assert source_ui.locator("#web-workflow-options").is_hidden()
    assert source_ui.locator("#web-manual-mode-label").is_hidden()
    assert "No browser navigation or agent actions" in source_ui.locator("#web-consent-text").inner_text()
    assert "Ready to extract this snapshot" in source_ui.locator("#web-create-help").inner_text()
    assert source_ui.locator("#web-show-capture-steps").is_hidden()
    assert not source_ui.locator("#web-consent").is_checked()
    assert source_ui.evaluate("automaticWorkflowSelected()") is False
    assert source_ui.evaluate("window.fixtureCalls") == [
        "/api/custom/captures/12345678-1234-1234-1234-123456789abc/claim"
    ]


def test_received_snapshot_submits_only_capture_after_explicit_extraction_consent(source_ui):
    source_ui.evaluate("""() => {
      webCapture = {url:'https://news.example.org/world', blocks:[{id:'b1',text:'World politics'}]};
      $('web-source').value = 'capture'; $('web-source').onchange();
      window.fixtureApi = async (path, data) => {
        if (path === '/api/custom/plans') {
          window.fixtureSubmitted = data;
          return new Promise(() => {});
        }
        throw new Error('Unexpected fixture API operation');
      };
    }""")
    source_ui.fill("#web-request", "Get world politics headlines")
    source_ui.locator("#web-authorized").check()
    source_ui.locator("#web-consent").check()
    source_ui.locator("#web-create").click()
    source_ui.wait_for_function("window.fixtureSubmitted?.source === 'capture'")
    submitted = source_ui.evaluate("window.fixtureSubmitted")
    assert submitted["capture"]["url"] == "https://news.example.org/world"
    assert submitted["urls"] == ["https://news.example.org/world"]
    assert submitted["allow_model_api"] is True
    assert "agent_confirmed" not in submitted and "browser_mode" not in submitted
    assert source_ui.evaluate("window.fixtureCalls") == ["/api/custom/plans"]


def test_snapshot_busy_and_discard_states_explain_why_extraction_is_unavailable(source_ui):
    source_ui.evaluate("""() => {
      webCapture = {url:'https://news.example.org/world',blocks:[{id:'b1',text:'World politics'}]};
      $('web-source').value = 'capture'; $('web-source').onchange();
      webBusy(true);
    }""")
    assert source_ui.locator("#web-create").is_disabled()
    assert "Another workflow is active" in source_ui.locator("#web-create-help").inner_text()
    source_ui.evaluate("webBusy(false)")
    assert source_ui.locator("#web-create").is_enabled()
    source_ui.locator("#web-discard-capture").click()
    assert source_ui.locator("#web-create").is_disabled()
    assert source_ui.locator("#web-show-capture-steps").is_visible()
    assert "Extraction unlocks" in source_ui.locator("#web-create-help").inner_text()
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_received_snapshot_locks_its_source_and_discard_restores_editing(source_ui):
    source_ui.evaluate("""() => {
      webCapture = {url:'https://news.example.org/sports', blocks:[{id:'b1',text:'Sports'}]};
      $('web-urls').value = webCapture.url;
      $('web-source').value = 'capture'; $('web-source').onchange();
    }""")
    assert not source_ui.locator("#web-urls").is_editable()
    assert source_ui.locator("#web-url-label-text").inner_text() == "Captured page address (read-only)"
    assert source_ui.locator("#web-open-normal-browser").is_hidden()
    assert source_ui.locator("#web-create").is_enabled()
    assert source_ui.locator("#web-create").inner_text() == "Extract received snapshot · paid API"
    # Editing a different source must not relabel the retained snapshot.
    source_ui.locator('[data-source="browser"]').click()
    source_ui.fill("#web-urls", "https://other.example.org/")
    assert not source_ui.locator("#web-source-alternatives").evaluate("element => element.open")
    select_snapshot(source_ui)
    assert source_ui.input_value("#web-urls") == "https://news.example.org/sports"
    source_ui.locator("#web-discard-capture").click()
    assert source_ui.locator("#web-urls").is_editable()
    source_ui.fill("#web-urls", "https://other.example.org/")
    assert source_ui.input_value("#web-urls") == "https://other.example.org/"
    assert source_ui.locator("#web-create").is_disabled()
    assert source_ui.evaluate("webCapture") is None
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_current_tab_agent_has_optional_opener_and_explicit_sidepanel_handoff(source_ui):
    source_ui.locator('[data-source="extension"]').click()
    assert source_ui.locator("#web-urls").is_visible()
    assert source_ui.locator("#web-urls").is_editable()
    assert source_ui.evaluate("$('web-urls').required") is False
    assert source_ui.locator("#web-request").is_hidden()
    assert source_ui.locator("#web-create").is_hidden()
    assert source_ui.locator("#web-extension-agent-help").is_visible()
    assert "Start workflow" in source_ui.locator("#web-extension-agent-help").inner_text()
    source_ui.fill("#web-urls", "https://www.booking.com/")
    source_ui.evaluate("window.fixtureOpened = []; window.open = (...args) => { window.fixtureOpened.push(args); return null; }")
    source_ui.locator("#web-open-normal-browser").click()
    assert source_ui.evaluate("window.fixtureOpened[0][0]") == "https://www.booking.com/"
    assert "choose Start workflow" in source_ui.locator("#web-tab-next-step").inner_text()
    assert source_ui.evaluate("window.fixtureCalls") == []


def test_return_to_separate_browser_restores_normal_task_inputs(source_ui):
    source_ui.locator('[data-source="extension"]').click()
    source_ui.locator('[data-source="browser"]').click()
    assert source_ui.locator("#web-urls").is_editable()
    assert source_ui.locator("#web-request").is_visible()
    assert source_ui.locator("#web-create").is_visible()
    assert source_ui.locator("#web-create").is_enabled()
    assert source_ui.locator("#web-browser-start-note").is_visible()
    assert source_ui.locator("#web-existing-tab-setup").is_hidden()
    assert source_ui.locator("#web-extension-preview").is_hidden()
    assert source_ui.evaluate("window.fixtureCalls") == []
