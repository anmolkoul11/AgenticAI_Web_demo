"""Single-run Studio contract and opt-in local browser regressions.

Browser fixtures fulfill requests locally. No website or model calls are made.
"""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS


def test_initial_workflow_controls_and_explicit_paid_permission_are_present():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    for identifier in (
        "web-workflow-options",
        "web-workflow-visual",
        "web-manual-mode",
        "web-consent-text",
    ):
        assert f'id="{identifier}"' in html
    assert 'id="web-manual-mode" type="checkbox" checked' not in html
    assert "30 paid agent decisions (5 active minutes)" in html
    assert "I will review results before saving" in html
    assert 'values.workflow_mode = automatic ? "automatic" : "manual"' in script
    assert 'values.agent_confirmed = automatic && $("web-consent").checked' in script
    assert 'agentPause.id = "web-agent-pause"' in script
    assert 'advancedTools.id = "web-advanced-tools"' in script
    assert "advancedTools.open = !automatic" in script
    assert "lastToolsMode" in script


@pytest.fixture
def unified_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_browser_defaults_to_one_run_and_mode_changes_require_new_consent(unified_ui):
    state = unified_ui.evaluate("""() => ({
      automatic:automaticWorkflowSelected(),
      button:$('web-create').textContent,
      required:$('web-request').required,
      visualVisible:!$('web-workflow-options').hidden
    })""")
    assert state == {
        "automatic": True,
        "button": "Run workflow",
        "required": True,
        "visualVisible": True,
    }
    state = unified_ui.evaluate("""() => {
      $('web-consent').checked=true; $('web-workflow-visual').checked=true;
      $('web-manual-mode').checked=true; $('web-manual-mode').onchange();
      return {automatic:automaticWorkflowSelected(),
        consent:$('web-consent').checked,visual:$('web-workflow-visual').checked,
        required:$('web-request').required};
    }""")
    assert state == {"automatic": False, "consent": False, "visual": False, "required": False}


def test_initial_run_sends_agent_and_optional_visual_permission_without_extra_calls(unified_ui):
    sent = unified_ui.evaluate("""async () => {
      $('web-urls').value='https://example.org/search';
      $('web-request').value='Find relevant records with names, links and details';
      $('web-authorized').checked=true; $('web-consent').checked=true;
      $('web-normal-confirm').checked=true; $('web-workflow-visual').checked=true;
      window.fixtureApi=async (path,data)=>{
        window.initialPayload={path,data:structuredClone(data)};
        return {job_id:'fixture'};
      };
      customSelect=async () => {};
      await webForm.onsubmit(new Event('submit',{cancelable:true}));
      return {payload:window.initialPayload,calls:window.fixtureCalls,
        consent:$('web-consent').checked,visual:$('web-workflow-visual').checked};
    }""")
    assert sent["payload"]["path"] == "/api/custom/plans"
    assert sent["payload"]["data"]["workflow_mode"] == "automatic"
    assert sent["payload"]["data"]["agent_confirmed"] is True
    assert sent["payload"]["data"]["agent_visual_confirmed"] is True
    assert sent["calls"] == ["/api/custom/plans"]
    assert not sent["consent"] and not sent["visual"]


@pytest.mark.parametrize("source,framework", [("browser", "crewai"), ("public", "langgraph")])
def test_crewai_and_nonbrowser_sources_remain_manual(unified_ui, source, framework):
    data = unified_ui.evaluate(
        """({source,framework}) => {
      $('web-source').value=source; $('web-framework').value=framework;
      $('web-source').onchange();
      return {automatic:automaticWorkflowSelected(),
        hidden:$('web-workflow-options').hidden,required:$('web-request').required,
        framework:$('web-framework').value};
    }""",
        {"source": source, "framework": framework},
    )
    assert not data["automatic"] and data["hidden"] and not data["required"]
    assert data["framework"] == framework


def test_running_workflow_keeps_pause_visible_and_manual_alternatives_folded(unified_ui):
    unified_ui.evaluate("""() => {
      webSelected='fixture'; $('web-browser-controls').hidden=false;setStudioStep('work');
      renderBrowserOptions({state:'agent_running',workflow_mode:'automatic',
        automatic_start:'started',guidance:'Choosing the next search control',page_health:{},
        agent_report:{status:'running',calls:1,max_calls:30,captured_pages:[],actions:[],
          guidance:'Choosing the next search control'}});
    }""")
    pause = unified_ui.get_by_role("button", name="Pause workflow", exact=True)
    assert pause.is_visible() and pause.is_enabled()
    assert unified_ui.get_by_role("button", name="Cancel & close browser", exact=True).is_visible()
    assert not unified_ui.locator("#web-advanced-tools").evaluate("element => element.open")
    assert unified_ui.locator("#web-plan-navigation").is_hidden()
    assert unified_ui.locator("#web-capture").is_hidden()
    # Polling must not close a disclosure that the operator deliberately opened.
    assert unified_ui.evaluate("""() => {
      advancedTools.open=true;
      renderBrowserOptions({state:'agent_running',workflow_mode:'automatic',
        automatic_start:'started',page_health:{}});
      return advancedTools.open;
    }""")


def test_pause_and_resume_use_explicit_commands_without_automatic_retry(unified_ui):
    sent = unified_ui.evaluate("""async () => {
      webSelected='fixture'; $('web-browser-controls').hidden=false;setStudioStep('work');
      window.fixtureApi=async (path,data)=>({path,data});
      renderBrowserOptions({state:'agent_running',workflow_mode:'automatic',
        automatic_start:'started',page_health:{}});
      await agentPause.onclick();
      renderBrowserOptions({state:'agent_pausing',workflow_mode:'automatic',
        automatic_start:'started',page_health:{}});
      return {calls:window.fixtureCalls,disabled:agentPause.disabled};
    }""")
    assert sent["calls"] == ["/api/custom/jobs/fixture/browser/agent_pause"]
    assert sent["disabled"]
    unified_ui.evaluate("""() => renderBrowserOptions({state:'agent_paused',
      workflow_mode:'automatic',automatic_start:'started',page_health:{},
      agent_report:{status:'paused',calls:2,max_calls:30,captured_pages:[],actions:[],
        guidance:'Inspect the browser before resuming'}})""")
    assert unified_ui.locator("#web-agent-resume").is_visible()
    assert unified_ui.locator("#web-agent-resume").is_disabled()
    assert unified_ui.locator("#web-agent-manual").is_visible()
    assert not unified_ui.locator("#web-advanced-tools").evaluate("element => element.open")


def test_manual_collection_requires_explicit_takeover_of_automatic_start(unified_ui):
    states = unified_ui.evaluate("""() => [
      manualCollectionAvailable({state:'waiting',workflow_mode:'automatic',automatic_start:'pending'}),
      manualCollectionAvailable({state:'waiting',workflow_mode:'automatic',automatic_start:'started'}),
      manualCollectionAvailable({state:'waiting',workflow_mode:'automatic',automatic_start:'manual'}),
      manualCollectionAvailable({state:'waiting',workflow_mode:'manual'}),
      manualCollectionAvailable({state:'agent_paused',workflow_mode:'automatic'})
    ]""")
    assert states == [False, False, True, True, False]
    unified_ui.evaluate("""() => {
      $('web-browser-controls').hidden=false;setStudioStep('work');
      renderBrowserOptions({state:'waiting',workflow_mode:'automatic',
        automatic_start:'pending',page_health:{}});
    }""")
    assert unified_ui.locator("#web-agent-manual").is_visible()
    assert unified_ui.locator("#web-agent-manual").is_enabled()
    assert unified_ui.locator("#web-plan-navigation").is_disabled()
