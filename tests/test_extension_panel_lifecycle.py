"""Opt-in local-page fixtures for companion recovery; no site/provider access."""

import re
from pathlib import Path

import pytest
from test_navigation_verification import local_page as shared_local_page


EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "page-capture"


@pytest.fixture
def companion_panel(shared_local_page):
    page = shared_local_page
    html = (EXTENSION / "sidepanel.html").read_text(encoding="utf-8")
    html = re.sub(r"<script\b[^>]*>.*?</script>|<link\b[^>]*>", "", html, flags=re.S)
    page.set_content(html)
    page.evaluate("""()=>{
      const binding={tab_id:1,title:'Hotels',url:'https://hotels.example.org/',username:'user1'};
      const fixture=window.panelFixture={messages:[],listeners:[],failStatus:0,failStart:false,
        state:{ok:true,revision:1,connection:binding,run:null,error:null}};
      window.chrome={tabs:{query:async()=>[{id:2,url:'http://localhost:8120/'}]},runtime:{
        onMessage:{addListener:listener=>fixture.listeners.push(listener)},
        sendMessage:async message=>{
          fixture.messages.push(structuredClone(message));
          if(message.operation==='status'){
            if(fixture.failStatus>0){fixture.failStatus--;throw Error('Message port closed');}
            return structuredClone(fixture.state);
          }
          if(message.operation==='start'){
            fixture.state={...fixture.state,revision:2,
              run:{run_id:'a'.repeat(32),job_id:'b'.repeat(32),state:'agent_running'}};
            if(fixture.failStart)throw Error('Message port closed');
            return structuredClone(fixture.state);
          }
          return structuredClone(fixture.state);
        }
      }};
    }""")
    page.add_script_tag(path=str(EXTENSION / "sidepanel.js"))
    page.wait_for_function("() => document.getElementById('connect').textContent==='Check connection'")
    return page


def test_panel_status_resync_after_port_failure_does_not_repeat_start(companion_panel):
    page = companion_panel
    page.evaluate("panelFixture.failStart=true")
    page.locator("#instructions").fill("Find hotel names and displayed prices")
    page.locator("#start").click()
    assert page.locator("#connect").inner_text() == "Check status"
    assert page.locator("#start").is_disabled()
    assert page.locator("#connection-status").get_attribute("data-tone") == "attention"
    assert "needs attention" in page.locator("#connection-status-label").inner_text()
    page.locator("#connect").click()
    assert page.locator("#state").inner_text() == "Working on your request"
    assert page.locator("#connection-status").get_attribute("data-tone") == "connected"
    assert page.evaluate("panelFixture.messages.filter(m=>m.operation==='start').length") == 1
    assert page.evaluate("panelFixture.messages.at(-1).operation") == "status"


def test_panel_status_has_one_bounded_transport_retry_but_start_does_not(companion_panel):
    page = companion_panel
    result = page.evaluate("""async()=>{
      panelFixture.messages=[];panelFixture.failStatus=1;
      await send('status');return panelFixture.messages.map(m=>m.operation);
    }""")
    assert result == ["status", "status"]
    result = page.evaluate("""async()=>{
      panelFixture.messages=[];panelFixture.failStart=true;
      try{await send('start');}catch(error){return {error:error.message,messages:panelFixture.messages};}
    }""")
    assert result["error"] == "companion_reply_unknown"
    assert len(result["messages"]) == 1


def test_panel_ignores_older_worker_snapshot_after_start(companion_panel):
    page = companion_panel
    page.evaluate("""()=>{
      const newer={...panelFixture.state,revision:8,run:{state:'agent_running'}};
      render(newer,true);render({...panelFixture.state,revision:7,run:null},true);
    }""")
    assert page.locator("#state").inner_text() == "Working on your request"
    assert page.locator("#start").is_disabled()


def test_panel_checks_original_connection_even_when_dashboard_tab_is_active(companion_panel):
    page = companion_panel
    page.locator("#connect").click()
    message = page.evaluate("panelFixture.messages.find(m=>m.operation==='connect')")
    assert message["tab_id"] == 1


def test_panel_connect_uses_selected_website_without_disconnect(companion_panel):
    page = companion_panel
    page.evaluate("chrome.tabs.query=async()=>[{id:3,url:'https://another.example.org/'}]")
    page.locator("#connect").click()
    message = page.evaluate("panelFixture.messages.find(m=>m.operation==='connect')")
    assert message["tab_id"] == 3
    assert not page.evaluate("panelFixture.messages.some(m=>m.operation==='disconnect')")


def test_panel_idle_poll_follows_selection_without_starting(companion_panel):
    messages = companion_panel.evaluate("panelFixture.messages")
    assert any(message.get("follow_selected_tab") is True for message in messages)
    assert all(message["operation"] == "status" for message in messages)


def test_panel_keeps_previous_review_label_after_idle_tab_switch(companion_panel):
    page = companion_panel
    page.evaluate("""()=>render({...panelFixture.state,revision:2,run_tab_id:1,
      connection:{...panelFixture.state.connection,tab_id:3},
      run:{state:'awaiting_review',job_id:'b'.repeat(32)}},true)""")
    assert page.locator("#activity-title").inner_text() == "Previous results"
    assert page.locator("#state").inner_text() == "Results ready to review"
    assert page.locator("#review").is_enabled()


def test_panel_pageshow_recovers_polling_without_an_automatic_paid_resume(companion_panel):
    page = companion_panel
    page.evaluate("""()=>{
      window.dispatchEvent(new Event('pagehide'));panelFixture.messages=[];
      window.dispatchEvent(new Event('pageshow'));
    }""")
    page.wait_for_function("() => panelFixture.messages.length>0")
    assert page.evaluate("panelFixture.messages.every(m=>m.operation==='status')")


def test_panel_shows_actual_document_focus_separately_from_browser_activation(companion_panel):
    page = companion_panel
    page.evaluate("""()=>render({...panelFixture.state,revision:2,
      website_activity:{activation_requested:true,tab_active:true,window_focused:true,
        observation:{visibility:'visible',has_focus:false}}},true)""")
    assert "document focus no" in page.locator("#account").inner_text()


@pytest.mark.parametrize("case,tone,label", [
    ("disconnected", "disconnected", "Browser agent is not connected"),
    ("ready", "connected", "Browser agent is connected"),
    ("paused", "attention", "Browser agent is paused"),
])
def test_panel_connection_status_uses_words_as_well_as_color(companion_panel, case, tone, label):
    page = companion_panel
    page.evaluate("""caseName => render({...panelFixture.state,revision:2,
      connection:caseName==='disconnected'?null:panelFixture.state.connection,
      run:caseName==='paused'?{state:'agent_paused'}:null},true)""", case)
    assert page.locator("#connection-status").get_attribute("data-tone") == tone
    assert page.locator("#connection-status-label").inner_text() == label
    assert page.locator("#connection-hint").inner_text()


def test_panel_account_change_is_attention_and_cannot_resume_old_work(companion_panel):
    page = companion_panel
    page.evaluate("""() => render({...panelFixture.state,revision:2,
      error:'dashboard_account_changed',reconnect_required:true,
      run:{state:'agent_paused'}},true)""")
    assert page.locator("#connection-status").get_attribute("data-tone") == "attention"
    assert "needs attention" in page.locator("#connection-status-label").inner_text()
    assert page.locator("#resume").is_disabled()
    assert "signed-in dashboard account changed" in page.locator("#error").inner_text()


def test_panel_used_budget_does_not_claim_task_completion(companion_panel):
    page = companion_panel
    page.evaluate("""() => render({...panelFixture.state,revision:2,
      run:{state:'agent_paused',agent_report:{calls:30,max_calls:30,
        awaiting_user_input:{reason:'missing_form_value'}}}},true)""")
    assert page.locator("#state").inner_text() == "Waiting for you"
    assert page.locator("#connection-status").get_attribute("data-tone") == "attention"
    assert page.locator("#step-count").inner_text() == "30 / 30 AI steps"
    assert "not percentage complete" in page.locator("#usage").inner_text()


def test_panel_start_button_authorizes_selected_tab_without_repeated_checkboxes(companion_panel):
    page = companion_panel
    result = page.evaluate("""async()=>{
      panelFixture.messages=[];
      document.getElementById('instructions').value='Find hotel names';
      await document.getElementById('task-form').onsubmit({preventDefault(){}});
      return {start:panelFixture.messages.find(m=>m.operation==='start'),
        starts:panelFixture.messages.filter(m=>m.operation==='start').length,
        consent:document.getElementById('consent'),native:document.getElementById('native-input-consent')};
    }""")
    assert result["starts"] == 1
    assert result["start"]["agent_confirmed"] is True
    assert result["start"]["allow_model_api"] is True
    assert result["start"]["native_input_confirmed"] is True
    assert result["start"]["publish_event"] is False
    assert result["consent"] is None and result["native"] is None


def test_panel_resume_is_one_explicit_action_and_polling_never_resumes(companion_panel):
    page = companion_panel
    page.evaluate("""()=>{
      panelFixture.messages=[];
      panelFixture.state={...panelFixture.state,revision:2,run:{state:'agent_paused'}};
      render(panelFixture.state,true);
    }""")
    assert page.evaluate("panelFixture.messages.every(m=>m.operation==='status')")
    page.locator("#resume").click()
    controls = page.evaluate("panelFixture.messages.filter(m=>m.operation==='control')")
    assert len(controls) == 1
    assert controls[0]["action"] == "resume"
    assert controls[0]["native_input_confirmed"] is True


def test_panel_counter_evidence_shows_real_counts_and_dispatch(companion_panel):
    page = companion_panel
    page.evaluate("""()=>render({...panelFixture.state,revision:3,run:{state:'agent_paused',
      agent_report:{actions:[{action:'set_counter',control:'increase Adults',
        status:'counter_unconfirmed',before:2,expected:3,observed:2,
        attempts:1,dispatched:true}]}}},true)""")
    text = page.locator("#actions").text_content()
    assert "before 2; requested 3; observed 2" in text
    assert "Input attempts: 1; dispatched: yes" in text
