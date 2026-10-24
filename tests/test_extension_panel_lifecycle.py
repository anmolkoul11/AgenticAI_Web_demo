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
    page.locator("#consent").check()
    page.locator("#start").click()
    assert page.locator("#connect").inner_text() == "Check status"
    assert page.locator("#start").is_disabled()
    page.locator("#connect").click()
    assert page.locator("#state").inner_text() == "agent running"
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
    assert page.locator("#state").inner_text() == "agent running"
    assert page.locator("#start").is_disabled()


def test_panel_checks_original_connection_even_when_dashboard_tab_is_active(companion_panel):
    page = companion_panel
    page.locator("#connect").click()
    message = page.evaluate("panelFixture.messages.find(m=>m.operation==='connect')")
    assert message["tab_id"] == 1


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
