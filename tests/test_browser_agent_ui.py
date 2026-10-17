"""Browser-agent UI behavior with isolated, opt-in browser fixtures."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui


@pytest.fixture
def agent_ui(request):
    for page in shared_ui.__wrapped__(request):
        # The shared fixture starts at an idle dashboard. Production customPoll
        # reveals this parent for an active browser; renderBrowserOptions only
        # renders its children and intentionally does not change job visibility.
        page.evaluate("""() => {
          $('web-framework').value='langgraph';
          $('web-browser-controls').hidden=false;
          setStudioStep('work');
        }""")
        yield page


def test_running_agent_has_live_activity_and_paused_agent_waits_without_animation(
    agent_ui,
):
    data = agent_ui.evaluate("""() => {
      const job={status:'running',kind:'custom-plan',stages:[{stage:'inspect_website'}]};
      const running=workflowActivity(job,{state:'agent_running',
        guidance:'Choosing a calendar date'});
      const paused=workflowActivity(job,{state:'agent_paused',guidance:'Finish MFA'});
      return {running,paused};
    }""")
    assert data["running"]["running"] and "calendar" in data["running"]["message"]
    assert data["paused"]["waiting"] and not data["paused"]["running"]


def test_agent_consent_survives_polling_and_submission_sends_explicit_permission(
    agent_ui,
):
    agent_ui.evaluate("""() => {
      renderBrowserOptions({state:'waiting',page_health:{}});
      webSelected='fixture';setStudioStep('work');
    }""")
    start = agent_ui.get_by_role("button", name="Run browser agent · paid API", exact=True)
    assert start.count() == 1
    assert start.is_visible()
    assert start.is_disabled()
    agent_ui.get_by_role(
        "checkbox", name="I authorize autonomous information-retrieval", exact=False
    ).check()
    agent_ui.evaluate("renderBrowserOptions({state:'waiting',page_health:{}})")
    assert start.is_enabled()
    sent = agent_ui.evaluate("""async () => {
      window.fixtureApi=async (path,data)=>{window.agentPayload={path,data};return {};};
      await agentStart.onclick();return window.agentPayload;
    }""")
    assert sent["path"].endswith("/browser/agent_start")
    assert sent["data"]["agent_confirmed"] is True
    assert not agent_ui.get_by_role(
        "checkbox", name="I authorize autonomous information-retrieval", exact=False
    ).is_checked()


def test_paused_agent_displays_actual_readback_and_retained_capture_choice(agent_ui):
    agent_ui.evaluate("""() => {
      renderBrowserOptions({state:'agent_paused',page_health:{},agent_report:{status:'paused',
        calls:4,max_calls:30,captured_pages:['https://example.org/'],guidance:'Complete MFA',
        actions:[{step:1,action:'fill',control:'Destination',status:'value_verified',
          explanation:'Enter the requested city',expected:'New York',observed:'New York'}]}});
      setStudioStep('work');
    }""")
    evidence = agent_ui.get_by_text("Browser-agent action evidence", exact=True)
    assert evidence.is_visible()
    evidence.click()
    assert agent_ui.get_by_text("Requested: New York; observed: New York.", exact=True).is_visible()
    assert agent_ui.get_by_role(
        "button", name="Extract retained captures · paid API", exact=True
    ).is_visible()
    assert agent_ui.get_by_role("button", name="Continue manually", exact=True).is_visible()


def test_option_renderer_does_not_reveal_an_inactive_browser_parent(agent_ui):
    agent_ui.evaluate("""() => {
      $('web-browser-controls').hidden=true;
      renderBrowserOptions({state:'waiting',page_health:{}});
    }""")
    assert agent_ui.locator("#web-browser-controls").is_hidden()
    assert agent_ui.locator("#web-agent-start").count() == 1
    assert agent_ui.locator("#web-agent-start").is_hidden()


def test_decision_failure_shows_code_stage_timeout_and_output_budget(agent_ui):
    agent_ui.evaluate("""() => renderBrowserOptions({state:'agent_paused',page_health:{},
      agent_report:{status:'paused',calls:3,max_calls:30,captured_pages:[],actions:[],
        guidance:'The model hit this decision output limit.',prompt_version:'browser-agent-v6',
        failure:{code:'output_limit',stage:'decide'},decision_diagnostics:[
          {call:3,error_code:'output_limit',timeout_seconds:60,max_output_tokens:1200,
           response_status:'incomplete',usage:{output_tokens:1200}}]}})""")
    assert agent_ui.get_by_text("Paused at decide: output_limit.", exact=False).is_visible()
    assert agent_ui.get_by_text(
        "timeout 60s; output budget 1200 tokens; output used 1200", exact=False
    ).is_visible()


def test_schema_failure_shows_specific_field_without_output_contents(agent_ui):
    agent_ui.evaluate("""() => renderBrowserOptions({state:'agent_paused',page_health:{},
      agent_report:{status:'paused',calls:1,max_calls:30,captured_pages:[],actions:[],
        guidance:'Returned decision was invalid.',prompt_version:'browser-agent-v7',
        failure:{code:'invalid_decision',stage:'decide'},decision_diagnostics:[
          {call:1,error_code:'invalid_decision',timeout_seconds:60,max_output_tokens:1200,
           response_status:'completed',message_count:1,commentary_count:0,decision_phase:'final_answer',
           validation_issues:[{field:'requirements.0.expected',code:'string_type'}]}]}})""")
    assert agent_ui.get_by_text(
        "Validation: requirements.0.expected (string_type).", exact=False
    ).is_visible()
    assert agent_ui.get_by_text("decision phase: final_answer.", exact=False).is_visible()


def test_agent_checklist_displays_requested_and_observed_occupancy_without_claiming_availability(
    agent_ui,
):
    agent_ui.evaluate("""() => renderBrowserOptions({state:'agent_paused',page_health:{},
      agent_report:{status:'paused',calls:4,max_calls:30,captured_pages:[],
        guidance:'Rooms pending',actions:[],
        task_checklist:{search_submitted:false,requirements:[
          {field:'adults',expected:'3',observed:'3',status:'verified',application:'form'},
          {field:'rooms',expected:'2',observed:'1',status:'mismatch',application:'form'}]}}})""")
    summary = agent_ui.get_by_text("Search readiness · 1/2 form fields verified", exact=True)
    assert summary.is_visible()
    summary.click()
    assert agent_ui.get_by_text(
        "rooms: requested 2; observed 1 — mismatch", exact=True
    ).is_visible()
    assert agent_ui.get_by_text("Search not yet confirmed.", exact=False).is_visible()


def test_year_resolution_is_visible_and_request_errors_do_not_offer_useless_resume(
    agent_ui,
):
    agent_ui.evaluate("""() => renderBrowserOptions({state:'agent_paused',page_health:{},
      agent_report:{status:'paused',calls:0,max_calls:30,captured_pages:[],guidance:'Fix dates',
        actions:[],task_checklist:{request_error:'Fix dates',requirements:[],
          date_resolution:{guidance:'Year omitted: using 2026; '+
            'check-in 2026-10-28, check-out 2026-10-30.'}}}})""")
    assert agent_ui.locator("#web-agent-resume").is_hidden()
    assert agent_ui.get_by_text("Year omitted: using 2026", exact=False).is_visible()


def test_counter_failure_exposes_target_detected_controls_and_running_agent_version(
    agent_ui,
):
    agent_ui.evaluate("""() => {
      renderBrowserOptions({state:'agent_paused',page_health:{},agent_report:{status:'paused',
        calls:5,max_calls:30,prompt_version:'browser-agent-v4',captured_pages:[],
        guidance:'Counter needs attention',actions:[{step:5,action:'set_counter',
          control:'Adults',status:'not_completed',explanation:'Set adults',
          guidance:'Inspect detected steppers',counter_evidence:{target:'3 adults',
            selected_label:'Adults',selected_tag:'DIV',selected_role:'spinbutton',selected_type:'',
            numeric_probe:{child_buttons:2,accessibility_hidden_buttons:2,aria_value:'2'},
            selected_counter:null,requested_counts:{adults:'3',rooms:'2'},
            available_counters:[{control_id:'0:plus',label:'Adults',value:2,
              direction:'increase',enabled:true}]}}]}});
      setStudioStep('work');
    }""")
    assert agent_ui.get_by_text("Agent version: browser-agent-v4.", exact=False).is_visible()
    agent_ui.get_by_text("Browser-agent action evidence", exact=True).click()
    assert agent_ui.get_by_text("Counter target: 3 adults", exact=False).is_visible()
    assert agent_ui.get_by_text(
        "Detected steppers: Adults 2 (increase; 0:plus)", exact=True
    ).is_visible()
    assert agent_ui.get_by_text(
        "Control structure: DIV; role spinbutton; type none.", exact=False
    ).is_visible()
    assert agent_ui.get_by_text(
        "accessibility-hidden child buttons: 2; numeric ARIA value: 2.", exact=False
    ).is_visible()


def test_screenshot_consent_is_separate_optional_and_sent_only_when_checked(agent_ui):
    visual = agent_ui.get_by_role("checkbox", name="Also allow viewport screenshots", exact=False)
    assert not visual.is_checked()
    visual.check()
    sent = agent_ui.evaluate("""async () => {
      webSelected='fixture'; agentCheckbox.checked=true;
      window.agentPayload=null;
      api=async (path,data)=>{window.agentPayload={path,data};return {status:'requested'};};
      await agentStart.onclick();return window.agentPayload;
    }""")
    assert sent["data"]["agent_visual_confirmed"] is True
    assert sent["data"]["agent_confirmed"] is True
    assert not visual.is_checked()


def test_action_effect_feedback_and_interpretation_are_visible_without_json(agent_ui):
    agent_ui.evaluate("""() => {
      renderBrowserOptions({state:'agent_paused',page_health:{},agent_report:{status:'paused',
        calls:2,max_calls:30,captured_pages:[],prompt_version:'browser-agent-v5',visual_enabled:true,
        visual_calls_attempted:2,guidance:'Review the open widget',
        task_checklist:{requirements:[{field:'topic',expected:'football',observed:'football',
          status:'verified',application:'form',model_interpreted:true,
          interpretation:'Soccer is called football here'}]},
        actions:[{step:1,action:'click',control:'Options',status:'action_performed',
          explanation:'Open the search options',verification:{status:'change_observed',
            widget_changed:true,new_controls:[{id:'0:new',label:'Quantity'}],
            changed_controls:[{control:'Options',after:'',expanded:'true'}]}}]}});
      setStudioStep('work');
    }""")
    assert agent_ui.get_by_text("DOM + adaptive screenshots", exact=False).is_visible()
    agent_ui.get_by_text("Browser-agent action evidence", exact=True).click()
    assert agent_ui.get_by_text("Widget state changed.", exact=False).is_visible()
    assert agent_ui.get_by_text("Options: true", exact=False).is_visible()
    assert agent_ui.get_by_text("New controls: Quantity (0:new)", exact=True).is_visible()
    agent_ui.get_by_text("Search readiness", exact=False).click()
    assert agent_ui.get_by_text(
        "model interpretation: Soccer is called football here", exact=False
    ).is_visible()
