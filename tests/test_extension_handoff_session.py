"""Offline relay/session fixtures. No site, backend or provider is contacted.

The mocked-worker fixtures use the existing opt-in local JS page harness; they
are intentionally authored here without being executed by the implementation.
"""

from pathlib import Path

import pytest
from test_navigation_verification import local_page as shared_local_page


EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "page-capture"


def test_worker_session_recovery_is_explicit_and_preserves_access_checks():
    script = (EXTENSION / "worker.js").read_text(encoding="utf-8")
    for token in (
        "dashboard_signed_out", "dashboard_csrf_changed", "dashboard_restarted",
        "dashboard_updated", "dashboard_not_ready", "dashboard_account_changed",
        "dashboard_tab_closed", "dashboard_origin_changed",
        "dashboard_relay_forbidden", "dashboard_unavailable",
    ):
        assert token in script
    assert "reconnect_required:DASHBOARD_ERRORS.has(state?.error)" in script
    assert "if (stale && !message.reconnect) return publicState(old);" in script
    assert "session.csrf !== expected.csrf" in script
    assert "session.instance_id !== expected.instance_id" in script
    assert "session.username !== expected.username" in script
    assert "document.documentElement.dataset.agenticUiVersion !== session.ui_version" in script
    assert "document.documentElement.dataset.agenticConnection !== 'ready'" in script
    assert "old.binding?.csrf === session.csrf" in script
    assert "if (memory !== state) return;" in script
    assert "if (latest.run?.run_id !== state.run.run_id) break;" in script
    assert "latest.run?.run_id !== state.run.run_id || latest.run?.state === 'cancelled'" not in script
    assert "error:'delivery_unknown'" in script
    assert "if ((await readState()) !== state) break;" in script
    assert "if (state.revision !== revision) continue;" in script
    assert "const controlled = {...state,run:{...state.run,...result}" in script
    assert "state = latest;" in script
    assert "onMessageExternal" not in script and "eval(" not in script


@pytest.fixture
def worker_page(shared_local_page):
    page = shared_local_page
    script = (EXTENSION / "worker.js").read_text(encoding="utf-8")
    page.evaluate(
        """script => {
          const session = {authenticated:true, csrf:'fresh-csrf', instance_id:'server-1',
            username:'user1', ui_version:'current-ui'};
          const binding = {tab_id:1, window_id:1, origin:'https://hotels.example.org',
            url:'https://hotels.example.org/', title:'Hotels', dashboard_tab_id:2,
            dashboard_url:'http://localhost:8120', ...session};
          const run = {run_id:'a'.repeat(32), job_id:'b'.repeat(32), state:'agent_paused'};
          const config = {session, state:{binding,run,error:null,pending:null}, calls:[], events:[],
            apiStatus:200, apiBody:run, markerVersion:'current-ui', markerReady:'ready'};
          const noListener = {addListener:() => {}};
          const tabs = config.tabs = {1:{id:1,windowId:1,url:'https://hotels.example.org/',title:'Hotels',active:false},
            2:{id:2,windowId:1,url:'http://localhost:8120/',active:true},
            3:{id:3,windowId:1,url:'https://another.example.org/',title:'Another tab'}};
          const fakeChrome = {
            storage:{session:{get:async key => ({[key]:config.state}),
              set:async value => {config.state = Object.values(value)[0];}}},
            runtime:{sendMessage:async () => {},onMessage:noListener,getURL:()=>'extension://fixture/'},
            windows:{update:async(id,options)=>{config.events.push({kind:'window',id,...options});return {id,focused:config.focusAllowed !== false};}},
            tabs:{get:async id => {if(!tabs[id])throw Error('Missing tab');return tabs[id];},
              update:async(id,options)=>{config.events.push({kind:'tab',id,...options});
                if(options.active)for(const tab of Object.values(tabs))tab.active=false;
                Object.assign(tabs[id],options);return tabs[id];},
              query:async query => query.active ? Object.values(tabs).filter(tab=>tab.active) : Object.values(tabs),
              onRemoved:noListener,onUpdated:noListener},
            scripting:{executeScript:async options => [{result:await options.func(...options.args)}]},
          };
          const fakeFetch = async (path,options) => {
            config.calls.push({path,method:options?.method || 'GET',body:options?.body});
            config.events.push({kind:'http',path,method:options?.method || 'GET'});
            if(config.fetchHook){const response=await config.fetchHook(path,options);if(response)return response;}
            const status = path === '/api/session' ? 200 : config.apiStatus;
            const body = path === '/api/session' ? config.session : config.apiBody;
            return {ok:status>=200&&status<300,status,json:async()=>structuredClone(body)};
          };
          const fakeDocument = {documentElement:{dataset:{
            get agenticUiVersion(){return config.markerVersion;},
            get agenticConnection(){return config.markerReady;}
          }}};
          const construct = new Function('chrome','location','document','fetch',script +
            ';return {connect,relay,handle,readState,writeState,stopFor,publicState,dashboardRequest,activateWebsite,pump};');
          window.workerFixture = {config,api:construct(fakeChrome,
            {origin:'http://localhost:8120'},fakeDocument,fakeFetch)};
        }""",
        script,
    )
    return page


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {}, "dashboard_signed_out"),
        (403, {"detail": "Session expired; reload the dashboard."}, "dashboard_csrf_changed"),
        (403, {"detail": "Same-origin requests only."}, "dashboard_relay_forbidden"),
        (409, {"code": "ui_outdated"}, "dashboard_updated"),
        (409, {"detail": "Dashboard changed. Reconnect the extension to this dashboard."}, "dashboard_restarted"),
        (409, {"detail": "Command acknowledgement conflicts."}, "operation_conflict"),
        (400, {"detail": "Configure your API connection in the dashboard first."}, "model_connection_required"),
        (410, {}, "run_expired"),
        (404, {}, "run_unavailable"),
    ],
)
def test_relay_does_not_confuse_http_status_with_session_change(worker_page, status, body, expected):
    result = worker_page.evaluate(
        """async ({status,body}) => {
          const {config,api} = workerFixture;
          config.apiStatus=status;config.apiBody=body;
          try {await api.relay(config.state,'/api/extension/runs/'+config.state.run.run_id);}
          catch(error){return error.message;}
        }""",
        {"status": status, "body": body},
    )
    assert result == expected


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("authenticated", False, "dashboard_signed_out"),
        ("csrf", "rotated", "dashboard_csrf_changed"),
        ("instance_id", "server-2", "dashboard_restarted"),
        ("username", "another-account", "dashboard_account_changed"),
    ],
)
def test_relay_revalidates_backend_session_before_any_workflow_request(worker_page, field, value, expected):
    result = worker_page.evaluate(
        """async ({field,value}) => {
          const {config,api}=workerFixture;
          config.session[field]=value;
          try {await api.relay(config.state,'/api/extension/runs','POST',{});}
          catch(error){return {error:error.message,calls:config.calls};}
        }""",
        {"field": field, "value": value},
    )
    assert result["error"] == expected
    assert [call["path"] for call in result["calls"]] == ["/api/session"]


@pytest.mark.parametrize(
    ("marker", "value", "expected"),
    [("markerVersion", "old-ui", "dashboard_updated"), ("markerReady", "blocked", "dashboard_not_ready")],
)
def test_relay_requires_current_loaded_dashboard_receiver(worker_page, marker, value, expected):
    result = worker_page.evaluate(
        """async ({marker,value})=>{
          const {config,api}=workerFixture;config[marker]=value;
          try{await api.relay(config.state,'/api/extension/runs','POST',{});}
          catch(error){return {error:error.message,calls:config.calls};}
        }""",
        {"marker": marker, "value": value},
    )
    assert result["error"] == expected
    assert all(call["method"] == "GET" for call in result["calls"])


def test_legacy_stale_binding_requires_explicit_reconnect_and_never_replays(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.error='session_changed';config.state.binding.csrf='old-csrf';
          config.state.pending={request_id:'c'.repeat(32),phase:'executing'};
          const blocked=await api.connect({tab_id:1});
          const connected=await api.connect({tab_id:1,reconnect:true});
          return {blocked,connected,calls:config.calls,state:await api.readState()};
        }"""
    )
    assert result["blocked"]["reconnect_required"] is True
    assert result["blocked"]["run"]["state"] == "agent_paused"
    assert result["connected"]["reconnect_required"] is False
    assert result["connected"]["run"] is None
    assert result["state"]["pending"] is None
    assert result["state"]["binding"]["csrf"] == "fresh-csrf"
    assert all(call["method"] == "GET" for call in result["calls"])


def test_explicit_reconnect_cancels_only_proven_same_session_stale_run(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;config.state.error='dashboard_updated';
          config.state.binding.ui_version='old-ui';
          const connected=await api.connect({tab_id:1,reconnect:true});
          return {connected,calls:config.calls};
        }"""
    )
    assert result["connected"]["run"] is None
    posts = [call for call in result["calls"] if call["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["path"].endswith("/control")
    assert posts[0]["body"] == '{"action":"cancel"}'


def test_healthy_paused_run_cannot_be_silently_retargeted_by_reconnect(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          try{await api.connect({tab_id:3,reconnect:true});}
          catch(error){return {error:error.message,state:await api.readState(),calls:config.calls};}
        }"""
    )
    assert "Cancel it before changing tabs" in result["error"]
    assert result["state"]["binding"]["tab_id"] == 1
    assert result["state"]["run"]["state"] == "agent_paused"
    assert all(call["method"] == "GET" for call in result["calls"])


def test_late_old_session_error_cannot_overwrite_reconnected_binding(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {api}=workerFixture;const old=await api.readState();
          const fresh={binding:{...old.binding,csrf:'new-context'},run:null,error:null,pending:null};
          await api.writeState(fresh);
          await api.stopFor(old,Error('dashboard_csrf_changed'));
          return await api.readState();
        }"""
    )
    assert result["binding"]["csrf"] == "new-context"
    assert result["run"] is None
    assert result["error"] is None


def test_completed_connection_is_reused_without_dashboard_or_website_reselection(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.run.state='awaiting_review';
          config.tabs[4]={id:4,windowId:1,url:'http://localhost:8120/'};
          const checked=await api.connect({tab_id:1});
          return {checked,events:config.events};
        }"""
    )
    assert result["checked"]["connection"]["tab_id"] == 1
    assert result["checked"]["run"]["state"] == "awaiting_review"
    assert all(event["kind"] == "http" for event in result["events"])


def test_explicit_start_activates_bound_site_before_the_paid_start_request(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.run.state='completed';const old=await api.readState();
          config.apiBody={run_id:'d'.repeat(32),job_id:'e'.repeat(32),state:'agent_paused'};
          const started=await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
            agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false});
          return {started,events:config.events,old_run_id:old.run.run_id};
        }"""
    )
    assert result["old_run_id"] == "a" * 32
    assert result["started"]["run"]["run_id"] == "d" * 32
    events = result["events"]
    window = next(i for i, event in enumerate(events) if event["kind"] == "window")
    tab = next(i for i, event in enumerate(events) if event["kind"] == "tab")
    start = next(i for i, event in enumerate(events)
                 if event.get("method") == "POST" and event.get("path") == "/api/extension/runs")
    assert window < tab < start
    assert events[tab]["id"] == 1
    assert result["started"]["website_activity"]["observation"] is None


def test_failed_window_activation_does_not_send_a_paid_start_request(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.run.state='completed';config.focusAllowed=false;
          try{await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
            agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false});}
          catch(error){return {error:error.message,calls:config.calls};}
        }"""
    )
    assert result["error"] == "website_focus_required"
    assert all(call["method"] == "GET" for call in result["calls"])


def test_resume_activation_is_explicit_and_status_poll_never_focuses(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          await api.handle({operation:'status'});
          const passive=structuredClone(config.events);config.events.length=0;
          await api.handle({operation:'control',action:'resume'});
          return {passive,resume:config.events};
        }"""
    )
    assert all(event["kind"] == "http" for event in result["passive"])
    resume = result["resume"]
    tab = next(i for i, event in enumerate(resume) if event["kind"] == "tab")
    command = next(i for i, event in enumerate(resume) if event.get("method") == "POST")
    assert tab < command


def test_late_cancelled_run_expiry_does_not_erase_its_terminal_state(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;config.state.run.state='cancelled';
          const state=await api.readState();await api.stopFor(state,Error('run_expired'));
          return await api.readState();
        }"""
    )
    assert result["run"]["state"] == "cancelled"
    assert result["error"] is None


def test_explicit_cancel_for_unavailable_run_is_inactive_without_false_confirmation(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;config.apiStatus=410;
          return await api.handle({operation:'control',action:'cancel'});
        }"""
    )
    assert result["run"]["state"] == "failed"
    assert "cannot be independently confirmed" in result["run"]["guidance"]
    assert result["connection"]["tab_id"] == 1


def test_public_revisions_survive_terminal_reuse_and_disconnect(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;config.state.run.state='completed';
          const checked=await api.connect({tab_id:1});
          const disconnected=await api.handle({operation:'disconnect'});
          return {first:checked.revision,second:disconnected.revision};
        }"""
    )
    assert result["first"] > 0
    assert result["second"] > result["first"]


@pytest.mark.parametrize("action,expected", [("pause", "agent_pausing"), ("cancel", "cancelled")])
def test_late_same_run_status_cannot_overwrite_explicit_control(worker_page, action, expected):
    result = worker_page.evaluate(
        """async ({action,expected})=>{
          const {config,api}=workerFixture;
          config.state.run.state='agent_running';
          const old=await api.readState(), runId=old.run.run_id;
          let release,entered;
          const waiting=new Promise(resolve=>{entered=resolve;});
          const gate=new Promise(resolve=>{release=resolve;});
          const response=body=>({ok:true,status:200,json:async()=>structuredClone(body)});
          config.fetchHook=async(path,options)=>{
            if(path.endsWith('/next'))return response({command:null});
            if(path.endsWith('/'+runId)&&(options?.method||'GET')==='GET'){
              entered();await gate;return response({...old.run,state:'agent_running'});
            }
          };
          const pumping=api.pump();await waiting;
          config.apiBody={run_id:runId,state:expected};
          await api.handle({operation:'control',action});
          release();await pumping;
          return {state:await api.readState(),oldState:old.run.state};
        }""",
        {"action": action, "expected": expected},
    )
    assert result["state"]["run"]["state"] == expected
    assert result["state"]["error"] is None
    assert result["oldState"] == "agent_running"
