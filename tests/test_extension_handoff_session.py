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
            nativeDetachListeners:[],
            apiStatus:200, apiBody:run, markerVersion:'current-ui', markerReady:'ready'};
          const noListener = {addListener:() => {}};
          const tabs = config.tabs = {1:{id:1,windowId:1,url:'https://hotels.example.org/',title:'Hotels',active:false},
            2:{id:2,windowId:1,url:'http://localhost:8120/',active:true},
            3:{id:3,windowId:1,url:'https://another.example.org/',title:'Another tab'}};
          const fakeChrome = {
            storage:{session:{get:async key => ({[key]:config.state}),
              set:async value => {config.state = Object.values(value)[0];}}},
            runtime:{sendMessage:async () => {},onMessage:noListener,getURL:()=>'extension://fixture/',
              getManifest:()=>({version:'0.5.20'})},
            windows:{update:async(id,options)=>{config.events.push({kind:'window',id,...options});return {id,focused:config.focusAllowed !== false};},
              get:async id=>({id,focused:config.focusAllowed !== false})},
            tabs:{get:async id => {if(!tabs[id])throw Error('Missing tab');return tabs[id];},
              update:async(id,options)=>{config.events.push({kind:'tab',id,...options});
                if(options.active)for(const tab of Object.values(tabs))tab.active=false;
                Object.assign(tabs[id],options);return tabs[id];},
              query:async query => query.active ? Object.values(tabs).filter(tab=>tab.active) : Object.values(tabs),
              onRemoved:noListener,onUpdated:noListener},
            debugger:{onDetach:{addListener:listener=>config.nativeDetachListeners.push(listener)}},
            scripting:{executeScript:async options => {
              if(options.files)return [{result:undefined}];
              if(options.target.tabId===1){
                if(!options.args?.length)return [{result:{before:false,has_focus:config.documentFocus !== false,visibility:'visible'}}];
                if(config.executorEnvelopeHook)return [{result:await config.executorEnvelopeHook(...options.args)}];
                if(config.executorHook)return [{result:{ok:true,result:await config.executorHook(...options.args)}}];
                if(options.args[0]==='capabilities')return [{result:{ok:true,result:{executor_version:'0.5.20',input_protocol:1}}}];
                throw Error('Unexpected website executor request');
              }
              return [{result:await options.func(...(options.args||[]))}];
            }},
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
          const native = config.native = {
            attachedTabId:null,
            attach:async id=>{
              config.events.push({kind:'native_attach',id});
              if(config.attachError)throw Error(config.attachError);
              if(id!==binding.tab_id)throw Error('unsupported');
              native.attachedTabId=id;
            },
            focus:async id=>{config.events.push({kind:'native_focus',id});},
            perform:async(id,step,validate)=>{
              await validate();
              config.events.push({kind:'native_perform',id,step_id:step.id});
              if(config.performHook)await config.performHook(id,step,validate);
            },
            detach:async id=>{
              if(native.attachedTabId!==id)return;
              config.events.push({kind:'native_detach',id});native.attachedTabId=null;
            }
          };
          const construct = new Function('chrome','location','document','fetch','importScripts','AgenticNativeInput',script +
            ';return {connect,relay,handle,readState,writeState,stopFor,publicState,dashboardRequest,activateWebsite,pump,executeNative,injectCommand,removedTab,updatedTab,followSelectedTab};');
          window.workerFixture = {config,api:construct(fakeChrome,
            {origin:'http://localhost:8120'},fakeDocument,fakeFetch,()=>{},native)};
        }""",
        script,
    )
    return page


def test_native_click_preflight_transport_reports_only_reason_and_field_names(worker_page):
    result = worker_page.evaluate("""async () => {
      const {config,api}=workerFixture, operations=[];
      config.state.run.state='agent_running';config.tabs[1].active=true;
      config.native.attachedTabId=1;
      const step={id:'step-1',kind:'click',point:{x:10,y:10},value:'',selection_steps:0};
      config.executorEnvelopeHook=async operation=>{
        operations.push(operation);
        if(operation==='native_begin')return {ok:true,result:{transaction_id:'tx-1',native_step:step}};
        if(operation==='native_validate')return {ok:false,error:'control_changed',control_preflight:{
          reason:'identity_changed',phase:'native_validate',mismatched_fields:['text','private-value'],
          mismatch_count:999,extra:'private-content'}};
        if(operation==='native_abort')return {ok:true,result:{aborted:true}};
        throw Error('Unexpected operation');
      };
      const output=await api.executeNative(config.state,{document_token:'document-1',
        decision:{action:'click'},facts:{date_kind:''}});
      return {output,operations,events:config.events};
    }""")
    assert result["output"]["status"] == "value_mismatch"
    assert result["output"]["dispatched"] is False
    assert result["output"]["control_preflight"] == {
        "reason": "identity_changed", "phase": "native_validate",
        "mismatched_fields": ["text"], "mismatch_count": 1,
    }
    assert result["operations"] == ["native_begin", "native_validate", "native_abort"]
    assert not any(event["kind"] == "native_perform" for event in result["events"])
    assert "private-value" not in str(result["output"])
    assert "private-content" not in str(result["output"])


def test_native_click_after_input_failure_keeps_unknown_delivery(worker_page):
    result = worker_page.evaluate("""async () => {
      const {config,api}=workerFixture;
      config.state.run.state='agent_running';config.tabs[1].active=true;
      config.native.attachedTabId=1;
      const step={id:'step-1',kind:'click',point:{x:10,y:10},value:'',selection_steps:0};
      config.executorEnvelopeHook=async operation=>{
        if(operation==='native_begin')return {ok:true,result:{transaction_id:'tx-1',native_step:step}};
        if(operation==='native_validate')return {ok:true,result:step};
        if(operation==='native_abort')return {ok:true,result:{aborted:true}};
        throw Error('Unexpected operation');
      };
      config.performHook=async()=>{
        const error=Error('delivery_unknown');
        error.controlPreflight={reason:'identity_changed',phase:'native_validate',
          mismatched_fields:['text'],mismatch_count:1};
        throw error;
      };
      try {return {output:await api.executeNative(config.state,{document_token:'document-1',
        decision:{action:'click'},facts:{date_kind:''}})};}
      catch(error){return {error:error.message,events:config.events};}
    }""")
    assert result["error"] == "delivery_unknown" and "output" not in result
    assert sum(event["kind"] == "native_perform" for event in result["events"]) == 1


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


def test_status_can_pair_initial_selected_tab_without_starting_a_workflow(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state={};
      config.tabs[2].active=false;config.tabs[3].active=true;
      const status=await api.handle({operation:'status',follow_selected_tab:true});
      return {status,calls:config.calls,events:config.events};
    }""")
    assert result["status"]["connection"]["tab_id"] == 3
    assert result["status"]["run"] is None
    assert all(call["method"] == "GET" for call in result["calls"])
    assert not any(event["kind"].startswith("native_") for event in result["events"])


def test_idle_tab_switch_keeps_completed_review_and_its_original_target(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state.run.state='awaiting_review';
      config.tabs[2].active=false;config.tabs[3].active=true;
      const status=await api.handle({operation:'status',follow_selected_tab:true});
      return {status,calls:config.calls,events:config.events};
    }""")
    assert result["status"]["connection"]["tab_id"] == 3
    assert result["status"]["run"]["job_id"] == "b" * 32
    assert result["status"]["run"]["state"] == "awaiting_review"
    assert result["status"]["run_tab_id"] == 1
    assert all(call["method"] == "GET" for call in result["calls"])
    assert not any(event["kind"].startswith("native_") for event in result["events"])


@pytest.mark.parametrize("run_state", ["agent_running", "agent_paused", "reviewing"])
def test_following_selection_never_retargets_an_unfinished_run(worker_page, run_state):
    result = worker_page.evaluate("""async runState=>{
      const {config,api}=workerFixture;config.state.run.state=runState;
      config.tabs[2].active=false;config.tabs[3].active=true;
      const notice=await api.followSelectedTab();
      return {notice,state:await api.readState(),calls:config.calls,events:config.events};
    }""", run_state)
    assert result["state"]["binding"]["tab_id"] == 1
    assert result["state"]["run"]["state"] == run_state
    assert result["calls"] == result["events"] == []


def test_unchanged_idle_selection_does_not_refresh_session_or_revision(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state.run=null;
      config.tabs[2].active=false;config.tabs[1].active=true;
      const first=await api.handle({operation:'status',follow_selected_tab:true});
      const second=await api.handle({operation:'status',follow_selected_tab:true});
      return {first,second,calls:config.calls};
    }""")
    assert result["first"]["connection"]["tab_id"] == 1
    assert result["first"]["revision"] == result["second"]["revision"]
    assert result["calls"] == []


def test_idle_same_tab_new_origin_is_paired_as_a_fresh_target(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state.run=null;
      config.tabs[2].active=false;config.tabs[1].active=true;
      config.tabs[1].url='https://another.example.org/hotels';
      const status=await api.handle({operation:'status',follow_selected_tab:true});
      return {status,state:await api.readState(),calls:config.calls};
    }""")
    assert result["status"]["error"] is None
    assert result["state"]["binding"]["origin"] == "https://another.example.org"
    assert result["status"]["connection"]["url"] == "https://another.example.org/hotels"
    assert all(call["method"] == "GET" for call in result["calls"])


def test_changed_dashboard_session_cannot_be_adopted_by_automatic_tab_follow(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state.run=null;
      config.tabs[2].active=false;config.tabs[3].active=true;
      config.session={...config.session,csrf:'different-session'};
      let error;try{await api.followSelectedTab();}catch(problem){error=problem.message;}
      return {error,state:await api.readState(),calls:config.calls};
    }""")
    assert result["error"] == "dashboard_csrf_changed"
    assert result["state"]["binding"]["tab_id"] == 1
    assert result["state"]["binding"]["csrf"] == "fresh-csrf"
    assert all(call["method"] == "GET" for call in result["calls"])


@pytest.mark.parametrize("selected_url", ["http://localhost:8120/", "edge://settings/", None])
def test_ineligible_or_unreadable_selected_tab_preserves_existing_connection(worker_page, selected_url):
    result = worker_page.evaluate("""async url=>{
      const {config,api}=workerFixture;config.state.run=null;
      config.tabs[2].active=false;config.tabs[3].active=true;
      if(url===null)delete config.tabs[3].url;else config.tabs[3].url=url;
      const status=await api.handle({operation:'status',follow_selected_tab:true});
      return {status,calls:config.calls};
    }""", selected_url)
    assert result["status"]["connection"]["tab_id"] == 1
    assert result["calls"] == []
    if selected_url is None:
        assert "grant browser access" in result["status"]["selection_notice"]
    else:
        assert result["status"]["selection_notice"] == ""


def test_disconnect_prevents_the_next_status_poll_from_pairing_again(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;config.state.run=null;
      config.tabs[2].active=false;config.tabs[3].active=true;
      await api.handle({operation:'disconnect'});
      const status=await api.handle({operation:'status',follow_selected_tab:true});
      return {status,state:await api.readState(),calls:config.calls};
    }""")
    assert result["status"]["connection"] is None
    assert result["state"]["auto_connect"] is False
    assert result["calls"] == []


def test_explicit_start_activates_bound_site_before_the_paid_start_request(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.run.state='completed';const old=await api.readState();
          config.apiBody={run_id:'d'.repeat(32),job_id:'e'.repeat(32),state:'agent_paused'};
          const started=await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
            agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false,
            native_input_confirmed:true});
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
    attach = next(i for i, event in enumerate(events) if event["kind"] == "native_attach")
    focus = next(i for i, event in enumerate(events) if event["kind"] == "native_focus")
    assert window < tab < attach < focus < start
    assert events[tab]["id"] == 1
    assert events[attach]["id"] == events[focus]["id"] == 1
    assert result["started"]["website_activity"]["input_driver"] == "native_cdp"
    assert result["started"]["website_activity"]["focus_confirmed"] is True


def test_failed_window_activation_does_not_send_a_paid_start_request(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          config.state.run.state='completed';config.focusAllowed=false;
          try{await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
            agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false,
            native_input_confirmed:true});}
          catch(error){return {error:error.message,calls:config.calls};}
        }"""
    )
    assert result["error"] == "website_focus_required"
    assert all(call["method"] == "GET" for call in result["calls"])


def test_failed_native_attach_does_not_send_a_paid_start_request(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      config.state.run.state='completed';config.attachError='native_input_unavailable';
      try{await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
        agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false,
        native_input_confirmed:true});}
      catch(error){return {error:error.message,calls:config.calls,events:config.events,
        attached:config.native.attachedTabId};}
    }""")
    assert result["error"] == "native_input_unavailable"
    assert result["attached"] is None
    assert all(call["method"] == "GET" for call in result["calls"])
    assert [e["id"] for e in result["events"] if e["kind"] == "native_attach"] == [1]


def test_incompatible_page_executor_is_rejected_before_backend_start(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      config.state.run.state='completed';
      config.executorHook=async operation=>{
        if(operation==='capabilities')return {executor_version:'0.5.0'};
        throw Error('Unexpected input');
      };
      try{await api.handle({operation:'start',instructions:'Find hotels',record_limit:5,
        agent_confirmed:true,authorized:true,allow_model_api:true,agent_visual_confirmed:false,
        native_input_confirmed:true});}
      catch(error){return {error:error.message,calls:config.calls,events:config.events,
        attached:config.native.attachedTabId};}
    }""")
    assert result["error"] == "extension_update_required"
    assert result["attached"] is None
    assert result["calls"] == []
    assert not any(event["kind"] == "native_perform" for event in result["events"])


@pytest.mark.parametrize("attached", [False, True])
def test_observation_driver_is_confirmed_by_worker_attachment(worker_page, attached):
    result = worker_page.evaluate("""async attached=>{
      const {config,api}=workerFixture;
      config.state.run.state='agent_running';config.native.attachedTabId=attached?1:null;
      config.executorHook=async operation=>{
        if(operation==='observe')return {executor_version:'0.5.20',input_driver:'dom',
          document_token:'fixture-document',url:'https://hotels.example.org/',
          tab_state:{visibility:'visible',has_focus:true},frame:{controls:[]}};
        throw Error('Unexpected input');
      };
      try{return {observation:await api.injectCommand(await api.readState(),
        {operation:'observe',payload:{focus:'form'}}),calls:config.calls};}
      catch(error){return {error:error.message,calls:config.calls};}
    }""", attached)
    assert result["calls"] == []
    if attached:
        assert result["observation"]["input_driver"] == "native_cdp"
        assert result["observation"]["native_attached"] is True
        assert result["observation"]["worker_version"] == "0.5.20"
        assert result["observation"]["input_protocol"] == 1
    else:
        assert result["error"] == "native_input_detached"


@pytest.mark.parametrize("operation", ["start", "resume"])
def test_native_consent_is_required_before_attach_or_paid_control(worker_page, operation):
    result = worker_page.evaluate("""async operation=>{
      const {config,api}=workerFixture;
      const message=operation==='start' ? {operation:'start',instructions:'Find hotels',
        record_limit:5,agent_confirmed:true,authorized:true,allow_model_api:true,
        agent_visual_confirmed:false} : {operation:'control',action:'resume'};
      if(operation==='start')config.state.run.state='completed';
      try{await api.handle(message);}
      catch(error){return {error:error.message,calls:config.calls,events:config.events};}
    }""", operation)
    assert result == {"error": "native_input_consent_required", "calls": [], "events": []}


def test_external_debugger_detach_pauses_without_reattaching_or_resuming(worker_page):
    page = worker_page
    page.evaluate("""()=>{
      const {config}=workerFixture;
      config.state.run.state='agent_running';
      config.apiBody={...config.state.run,state:'agent_paused'};
      config.native.attachedTabId=null;
      config.nativeDetachListeners.forEach(listener=>listener({tabId:1},'canceled_by_user'));
    }""")
    page.wait_for_function("() => workerFixture.config.state.error==='native_input_detached'")
    result = page.evaluate("({state:workerFixture.config.state,calls:workerFixture.config.calls,events:workerFixture.config.events})")
    assert result["state"]["run"]["state"] == "agent_paused"
    assert not any(event["kind"] == "native_attach" for event in result["events"])
    posted = [call for call in result["calls"] if call["method"] == "POST"]
    assert len(posted) == 1 and posted[0]["path"].endswith("/control")
    assert posted[0]["body"] == '{"action":"pause"}'


def test_unknown_native_delivery_is_aborted_without_input_replay(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      config.state.run.state='agent_running';config.tabs[1].active=true;
      config.native.attachedTabId=1;config.operations=[];
      const step={id:'step-1',kind:'click',point:{x:20,y:30},value:'',selection_steps:0};
      config.executorHook=async operation=>{
        config.operations.push(operation);
        if(operation==='native_begin')return {transaction_id:'tx-1',native_step:step};
        if(operation==='native_validate')return step;
        if(operation==='native_abort')return {aborted:true};
        throw Error('Unexpected native continuation');
      };
      config.performHook=async()=>{throw Error('delivery_unknown');};
      try{await api.executeNative(await api.readState(),{document_token:'fixture-token'});}
      catch(error){return {error:error.message,operations:config.operations,events:config.events,calls:config.calls};}
    }""")
    assert result["error"] == "delivery_unknown"
    assert result["operations"] == ["native_begin", "native_validate", "native_abort"]
    assert len([e for e in result["events"] if e["kind"] == "native_perform"]) == 1
    assert result["calls"] == []


def test_native_input_is_not_dispatched_after_connected_origin_changes(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      config.state.run.state='agent_running';config.native.attachedTabId=1;
      config.tabs[1].url='https://another.example.org/';
      try{await api.executeNative(await api.readState(),{document_token:'fixture-token'});}
      catch(error){return {error:error.message,events:config.events,calls:config.calls};}
    }""")
    assert result == {"error": "origin_changed", "events": [], "calls": []}


def test_resume_activation_is_explicit_and_status_poll_never_focuses(worker_page):
    result = worker_page.evaluate(
        """async()=>{
          const {config,api}=workerFixture;
          await api.handle({operation:'status'});
          const passive=structuredClone(config.events);config.events.length=0;
          await api.handle({operation:'control',action:'resume',native_input_confirmed:true});
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
          config.state.run.state='agent_running';config.native.attachedTabId=1;
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


def test_reloaded_worker_without_native_attachment_pauses_before_claiming_commands(worker_page):
    result = worker_page.evaluate("""async()=>{
      const {config,api}=workerFixture;
      config.state.run.state='agent_running';config.native.attachedTabId=null;
      config.apiBody={...config.state.run,state:'agent_paused'};
      await api.pump();
      return {error:config.state.error,calls:config.calls,events:config.events};
    }""")
    assert result["error"] == "native_input_detached"
    assert not any(call["path"].endswith("/next") for call in result["calls"])
    assert not any(event["kind"] == "native_attach" for event in result["events"])


@pytest.mark.parametrize("attached", [False, True])
def test_collect_retained_pages_polls_review_without_native_input(worker_page, attached):
    result = worker_page.evaluate("""async attached=>{
      const {config,api}=workerFixture;
      config.native.attachedTabId=attached?1:null;
      config.apiBody={...config.state.run,state:'agent_running'};
      const collecting=await api.handle({operation:'control',action:'collect'});
      await api.pump();
      // Intentional detachment while extracting retained sources is not a
      // request to pause or reacquire browser control.
      for(const listener of config.nativeDetachListeners)listener({tabId:1});
      await new Promise(resolve=>setTimeout(resolve,0));
      const polling=await api.handle({operation:'status'});
      config.apiBody={...config.apiBody,state:'reviewing'};
      const reviewing=await api.handle({operation:'status'});
      return {collecting,polling,reviewing,calls:config.calls,events:config.events,
        attachedTabId:config.native.attachedTabId};
    }""", attached)
    assert result["collecting"]["run"]["collection_only"] is True
    assert result["polling"]["error"] is None
    assert result["reviewing"]["error"] is None
    assert result["reviewing"]["run"]["state"] == "reviewing"
    assert result["attachedTabId"] is None
    assert not any(call["path"].endswith("/next") for call in result["calls"])
    posts = [call for call in result["calls"] if call["method"] == "POST"]
    assert len(posts) == 1 and posts[0]["body"] == '{"action":"collect"}'
    assert not any(event["kind"] in {"native_attach", "native_perform"} for event in result["events"])
