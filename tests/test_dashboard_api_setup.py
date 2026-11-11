"""API setup UX regressions; browser checks are local, opt-in and model-free."""

import json
import re

import pytest
from test_source_inventory import inventory_browser as shared_browser

from agentic_web_demo.dashboard.app import ASSETS, UI_VERSION


def test_api_setup_notice_is_outside_hidden_workflow_steps():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert html.index('id="workspace"') < html.index('id="api-setup-notice"')
    assert html.index('id="api-setup-notice"') < html.index('data-page="custom"')
    assert 'aria-labelledby="api-setup-title"' in html
    assert 'id="api-setup-open" type="button"' in html
    assert "Guided hotel demo forms work without one" in html


@pytest.fixture
def setup_ui(request):
    for page in shared_browser.__wrapped__(request):
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        page.set_content(re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S))
        page.add_script_tag(
            content="window.fixtureUiVersion = " + json.dumps(UI_VERSION) + ";" + """
            window.fixtureConfigured = false;
            window.fixtureSignedIn = false;
            window.fixtureRequests = [];
            window.setInterval = () => 0;
            window.fetch = async (path, options = {}) => {
              const method = options.method || 'GET';
              fixtureRequests.push({path, method});
              let value;
              if (path === '/api/session') value = {
                authenticated:fixtureSignedIn, csrf:'fixture-csrf', username:'fixture-user',
                ui_version:fixtureUiVersion, instance_id:'fixture-instance',
                model_configured:fixtureConfigured
              };
              else if (path === '/api/config') value = {
                username:'fixture-user', role:'user', model_configured:fixtureConfigured,
                model:fixtureConfigured ? 'fixture-model' : 'Not configured',
                target:'local-fixture', cities:['New York'], credential_saved:false,
                secure_storage_available:false, secure_storage_label:'Fixture storage'
              };
              else if (path === '/api/readiness') value = {
                portal_port_open:true, nats_port_open:true, note:'Fixture only'
              };
              else if (path === '/api/jobs') value = [];
              else if (path === '/api/model-key' && method === 'POST') {
                fixtureConfigured = true; value = {guidance:'Fixture connection saved'};
              } else if (['/api/model-key/clear','/api/model-key/forget'].includes(path)) {
                fixtureConfigured = false; value = {guidance:'Fixture connection removed'};
              } else throw new Error('Unexpected fixture request: ' + path);
              return new Response(JSON.stringify(value), {
                status:200, headers:{'Content-Type':'application/json'}
              });
            };
            """
        )
        for name in ("ui_updates.js", "app.js", "custom.js"):
            page.add_script_tag(content=(ASSETS / name).read_text(encoding="utf-8"))
        page.evaluate("""async () => {
          clearTimeout(verificationBrowserTimer);
          fixtureSignedIn = true;
          await workspace();
          fixtureRequests.length = 0;
        }""")
        yield page


def test_missing_key_notice_and_run_shortcut_preserve_task_without_calls(setup_ui):
    page = setup_ui
    assert page.locator("#api-setup-notice").is_visible()
    assert page.locator("#api-connection-state").is_visible()
    page.locator("#web-request").fill("Collect visible world-politics headlines")
    # Other required source/permission fields are deliberately empty: setup
    # must be reachable before native form validation prevents submission.
    page.get_by_role("button", name="Set up API connection", exact=True).last.click()
    assert page.evaluate("activeView") == "connection"
    assert page.locator("#api-key").evaluate("el => el === document.activeElement")
    assert page.evaluate("fixtureRequests") == []
    page.get_by_role("button", name="Website Studio", exact=True).click()
    assert (
        page.locator("#web-request").input_value()
        == "Collect visible world-politics headlines"
    )


def test_setup_notice_button_focuses_key_without_running_workflow(setup_ui):
    setup_ui.locator("#api-setup-open").click()
    assert setup_ui.evaluate("activeView") == "connection"
    assert setup_ui.locator("#api-key").evaluate("el => el === document.activeElement")
    assert setup_ui.evaluate("fixtureRequests") == []


@pytest.mark.parametrize("remove_action", ["clear-key", "forget-key"])
def test_saved_connection_hides_notice_and_removal_restores_it(setup_ui, remove_action):
    page = setup_ui
    page.locator("#api-setup-open").click()
    page.evaluate("""async () => {
      $('api-key').value = 'fixture-only-not-a-real-key';
      $('model-id').value = 'fixture-model';
      await $('key-form').onsubmit({preventDefault(){},submitter:$('save-key')});
    }""")
    assert not page.locator("#api-setup-notice").is_visible()
    assert page.locator("#web-create").text_content() == "Start AI workflow"
    assert "added" in page.locator("#model-badge").text_content()
    assert page.locator("#api-key").input_value() == ""
    page.evaluate("fixtureRequests.length = 0; window.confirm = () => true;")
    # OS storage availability is not part of this UI-only fixture.
    page.evaluate(f"async () => {{ await $({json.dumps(remove_action)}).onclick(); }}")
    assert page.locator("#api-setup-notice").is_visible()
    assert page.locator("#web-create").text_content() == "Set up API connection"
    posted = [r["path"] for r in page.evaluate("fixtureRequests") if r["method"] == "POST"]
    expected = (
        "/api/model-key/clear" if remove_action == "clear-key" else "/api/model-key/forget"
    )
    assert posted == [expected]


def test_heartbeat_key_removal_does_not_navigate_or_retry(setup_ui):
    result = setup_ui.evaluate("""async () => {
      setModelConnectionState(true);
      showView('history');
      $('refresh-history').focus();
      const focused = document.activeElement;
      fixtureConfigured = false;
      fixtureRequests.length = 0;
      await checkConnection();
      return {view:activeView, focusUnchanged:focused === document.activeElement,
        missing:!$('api-setup-notice').hidden, requests:fixtureRequests};
    }""")
    assert result == {
        "view": "history",
        "focusUnchanged": True,
        "missing": True,
        "requests": [{"path": "/api/session", "method": "GET"}],
    }


@pytest.mark.parametrize("new_state", [True, False])
def test_stale_heartbeat_cannot_replace_newer_saved_connection_state(setup_ui, new_state):
    result = setup_ui.evaluate(
        """async newState => {
          setModelConnectionState(!newState);
          const originalFetch = window.fetch;
          let deliver;
          window.fetch = () => new Promise(resolve => { deliver = resolve; });
          const pending = checkConnection();
          setModelConnectionState(newState);
          deliver(new Response(JSON.stringify({
            authenticated:true, csrf:'fixture-csrf', username:'fixture-user',
            ui_version:fixtureUiVersion, instance_id:'fixture-instance',
            model_configured:!newState
          }), {status:200}));
          try { await pending; } finally { window.fetch = originalFetch; }
          return {configured:modelConfigured, missing:!$('api-setup-notice').hidden};
        }""",
        new_state,
    )
    assert result == {"configured": new_state, "missing": not new_state}


def test_guided_mode_and_snapshot_wait_remain_available_without_key(setup_ui):
    result = setup_ui.evaluate("""() => {
      showView('studio');
      $('mode').value = 'structured'; modeChanged();
      $('web-source').value = 'capture'; $('web-source').onchange();
      return {guidedEnabled:!$('structured').disabled,
        createEnabled:!$('create').disabled, waiting:$('web-create').disabled,
        label:$('web-create').textContent, setupAvailable:!$('api-setup-notice').hidden,
        requests:fixtureRequests};
    }""")
    assert result == {
        "guidedEnabled": True,
        "createEnabled": True,
        "waiting": True,
        "label": "Waiting for page capture",
        "setupAvailable": True,
        "requests": [],
    }


def test_explicit_start_without_a_key_opens_setup_without_a_paid_request(setup_ui):
    result = setup_ui.evaluate("""async()=>{
      $('web-urls').value='https://example.org/items';
      $('web-request').value='Collect visible item names';
      await webForm.onsubmit({preventDefault(){},submitter:$('web-create')});
      return {requests:fixtureRequests,view:activeView,
        keyFocused:document.activeElement===$('api-key'),submitting:webSubmitting};
    }""")
    assert result == {"requests": [], "view": "connection",
                      "keyFocused": True, "submitting": False}


def test_key_save_requires_its_button_and_repeated_submit_sends_one_payload(setup_ui):
    result = setup_ui.evaluate("""async()=>{
      $('api-key').value='fixture-only-not-a-real-key';$('model-id').value='fixture-model';
      await $('key-form').onsubmit({preventDefault(){},submitter:$('clear-key')});
      const withoutSave=fixtureRequests.length;
      const originalFetch=window.fetch;let finish;const payloads=[];
      window.fetch=async(path,options={})=>{
        if(path==='/api/model-key' && options.method==='POST'){
          payloads.push(JSON.parse(options.body));
          await new Promise(resolve=>{finish=resolve;});
        }
        return originalFetch(path,options);
      };
      const first=$('key-form').onsubmit({preventDefault(){},submitter:$('save-key')});
      const inFlight=keySubmitting;
      await $('key-form').onsubmit({preventDefault(){},submitter:$('save-key')});
      finish();await first;window.fetch=originalFetch;
      return {withoutSave,inFlight,payloads,
        keyAfter:$('api-key').value,submitting:keySubmitting,
        saveEnabled:!$('save-key').disabled};
    }""")
    assert result == {"withoutSave": 0, "inFlight": True,
                      "payloads": [{"api_key": "fixture-only-not-a-real-key",
                                    "model": "fixture-model", "remember": False,
                                    "authorized": True}],
                      "keyAfter": "", "submitting": False, "saveEnabled": True}
