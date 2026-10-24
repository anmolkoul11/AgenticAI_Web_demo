'use strict';

// The dashboard is the authenticated relay. This worker never receives API keys,
// reads cookies, installs a debugger, or accepts webpage/external messages.
const STATE_KEY = 'agentic-browser-workflow-v1';
const DASHBOARDS = new Set(['http://localhost:8120','http://127.0.0.1:8120']);
const ACTIVE = new Set(['agent_running']);
const FINISHED = new Set(['captured','awaiting_review','needs_input','cancelled','failed','completed']);
const SAFE_ERRORS = new Set(['stale_document','control_changed','unsupported','access_restriction','permission_required','website_focus_required','tab_closed','origin_changed','delivery_unknown','execution_failed','payload_too_large','session_changed']);
const RELAY_ERRORS = new Set(['run_expired','run_unavailable','operation_conflict','model_connection_required']);
// These errors concern the local relay, not the website or the model. Keep the
// reason separate so the panel can offer explicit reconnect instead of a futile
// Resume against an expired account/server binding.
const DASHBOARD_ERRORS = new Set(['session_changed','dashboard_signed_out','dashboard_csrf_changed','dashboard_restarted','dashboard_updated','dashboard_not_ready','dashboard_account_changed','dashboard_tab_closed','dashboard_origin_changed','dashboard_relay_forbidden','dashboard_unavailable']);
let pumping = false;
let memory;
let handling = Promise.resolve();
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve,milliseconds));
const safeError = error => SAFE_ERRORS.has(error?.message) || RELAY_ERRORS.has(error?.message) || DASHBOARD_ERRORS.has(error?.message) ? error.message : 'execution_failed';
const publicState = state => ({ok:true,revision:state?.revision || 0,connection:state?.binding ? {tab_id:state.binding.tab_id,title:state.binding.title,url:state.binding.url,dashboard_url:state.binding.dashboard_url,username:state.binding.username}:null,run:state?.run || null,error:state?.error || null,reconnect_required:DASHBOARD_ERRORS.has(state?.error),website_activity:state?.website_activity || null});
async function readState() {
  if (memory === undefined) memory = (await chrome.storage.session.get(STATE_KEY))[STATE_KEY] || {};
  return memory;
}
async function writeState(state) {
  state.revision = Math.max(memory?.revision || 0,state.revision || 0)+1;
  memory = state;
  await chrome.storage.session.set({[STATE_KEY]:state});
  if (memory !== state) return;
  chrome.runtime.sendMessage({type:'agentic-panel-state-v1',...publicState(state)}).catch(() => {});
}
function websiteUrl(value) {
  if (!value) throw new Error('permission_required');
  const u = new URL(value);
  if (u.protocol !== 'https:' || u.username || u.password || /^(?:localhost|127\.|0\.|\[|10\.|192\.168\.|169\.254\.)/i.test(u.hostname) || /^172\.(?:1[6-9]|2\d|3[01])\./.test(u.hostname)) throw new Error('unsupported');
  u.hash = '';
  const allowed = /^(?:id|item|product|article|story|hotel|listing|slug|variant|page|p|(?:item|product|article|story|hotel|listing|variant)_id|checkin|checkout|check_in|check_out|group_adults|group_children|no_rooms|adults|children|rooms|dest_id|dest_type|ss)$/i;
  u.search = new URLSearchParams([...u.searchParams].filter(([k,v])=>allowed.test(k)&&v.length<=128&&!/https?:|@|[\u0000-\u001f]/i.test(v)).slice(0,12)).toString();
  return u;
}
// Runs as packaged code in the dashboard's isolated world. Requests remain
// same-origin and use that page's authenticated cookie; no token is forwarded
// from a website or extension-origin fetch and no access check is bypassed.
async function dashboardRequest(route,verb,payload,expected) {
  if (!['http://localhost:8120','http://127.0.0.1:8120'].includes(location.origin) || (expected && location.origin !== expected.dashboard_url)) return {error:'dashboard_origin_changed'};
  let session;
  try {
    const response = await fetch('/api/session',{credentials:'same-origin',cache:'no-store'});
    if (!response.ok) return {error:response.status === 401 ? 'dashboard_signed_out' : response.status === 403 ? 'dashboard_relay_forbidden' : 'dashboard_unavailable'};
    session = await response.json();
  } catch (_) { return {error:'dashboard_unavailable'}; }
  if (!session?.authenticated) return {error:'dashboard_signed_out'};
  if (!session.csrf || !session.instance_id || !session.username || !session.ui_version) return {error:'dashboard_unavailable'};
  // Backend auth alone cannot prove the dashboard's loaded review receiver is
  // current. These markers are readiness hints, never authentication authority.
  if (document.documentElement.dataset.agenticUiVersion !== session.ui_version) return {error:'dashboard_updated'};
  if (document.documentElement.dataset.agenticConnection !== 'ready') return {error:'dashboard_not_ready'};
  if (expected) {
    if (session.instance_id !== expected.instance_id) return {error:'dashboard_restarted'};
    if (session.ui_version !== expected.ui_version) return {error:'dashboard_updated'};
    if (session.username !== expected.username) return {error:'dashboard_account_changed'};
    if (session.csrf !== expected.csrf) return {error:'dashboard_csrf_changed'};
  }
  if (!route) return {body:session};
  const headers = {'X-Dashboard-Instance':expected.instance_id,'X-Dashboard-Version':session.ui_version};
  if (verb === 'POST') { headers['Content-Type']='application/json'; headers['X-CSRF-Token']=session.csrf; }
  try {
    const response = await fetch(route,{method:verb,headers,credentials:'same-origin',body:verb === 'POST' ? JSON.stringify(payload || {}) : undefined,cache:'no-store'});
    let data;
    try { data = await response.json(); } catch (_) { data = {}; }
    if (response.ok) return {body:data};
    if (response.status === 401) return {error:'dashboard_signed_out'};
    if (response.status === 403) return {error:typeof data.detail === 'string' && data.detail.startsWith('Session expired;') ? 'dashboard_csrf_changed' : 'dashboard_relay_forbidden'};
    if (response.status === 409 && data.code === 'ui_outdated') return {error:'dashboard_updated'};
    if (response.status === 409 && typeof data.detail === 'string' && data.detail.startsWith('Dashboard changed.')) return {error:'dashboard_restarted'};
    if (response.status === 400 && data.detail === 'Configure your API connection in the dashboard first.') return {error:'model_connection_required'};
    return {error:response.status === 410 ? 'run_expired' : response.status === 404 ? 'run_unavailable' : response.status === 409 ? 'operation_conflict' : 'execution_failed'};
  } catch (_) { return {error:'dashboard_unavailable'}; }
}
async function sessionAt(tab,expected=null) {
  if (!tab?.id || !tab.url) throw new Error('dashboard_tab_closed');
  if (!DASHBOARDS.has(new URL(tab.url).origin)) throw new Error('dashboard_origin_changed');
  let answer;
  try { [answer] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:dashboardRequest,args:[null,'GET',null,expected]}); }
  catch (_) { throw new Error('dashboard_unavailable'); }
  if (!answer?.result || answer.result.error) throw new Error(answer?.result?.error || 'dashboard_unavailable');
  return answer.result.body;
}
async function relay(state,path,method='GET',body=null) {
  const b = state.binding;
  if (!b || !/^\/api\/extension\/runs(?:\/[a-f0-9-]{32,36}(?:\/(?:next|result|control))?)?$/.test(path)) throw new Error('unsupported');
  const dashboard = await chrome.tabs.get(b.dashboard_tab_id).catch(()=>null);
  if (!dashboard?.url) throw new Error('dashboard_tab_closed');
  if (new URL(dashboard.url).origin !== b.dashboard_url) throw new Error('dashboard_origin_changed');
  let answer;
  try { [answer] = await chrome.scripting.executeScript({target:{tabId:b.dashboard_tab_id},func:dashboardRequest,args:[path,method,body,b]}); }
  catch (_) { throw new Error('dashboard_unavailable'); }
  if (!answer?.result || answer.result.error) throw new Error(answer?.result?.error || 'dashboard_unavailable');
  return answer.result.body;
}
async function selectedTab(state) {
  const b = state.binding, tab = await chrome.tabs.get(b.tab_id).catch(()=>null);
  if (!tab) throw new Error('tab_closed');
  const currentUrl = tab.url || tab.pendingUrl;
  if (!currentUrl) throw new Error('permission_required');
  if (tab.windowId !== b.window_id || new URL(currentUrl).origin !== b.origin) throw new Error('origin_changed');
  return tab;
}
async function activateWebsite(state) {
  const tab = await selectedTab(state);
  // This runs only for an explicit Start/Resume, before paid execution. Browser
  // activation does not grant trusted DOM input or prove the page has focus.
  try {
    const window = await chrome.windows.update(tab.windowId,{focused:true});
    await chrome.tabs.update(tab.id,{active:true});
    const active = await selectedTab(state);
    if (!window?.focused || active.active !== true) throw new Error('website_focus_required');
    state.website_activity = {activation_requested:true,tab_active:true,window_focused:true,observation:null};
    return active;
  } catch(error) {
    if (['origin_changed','tab_closed','permission_required'].includes(error?.message)) throw error;
    throw new Error('website_focus_required');
  }
}
async function dispatchNavigation(state, rawUrl, expectedToken, originalUrl) {
  const target = new URL(rawUrl);
  if (target.origin !== state.binding.origin || target.username || target.password) throw new Error('origin_changed');
  await selectedTab(state);
  const [preflight] = await chrome.scripting.executeScript({target:{tabId:state.binding.tab_id},func:async (documentToken,url) => {
    try { return await globalThis.__agenticTabExecutor.dispatch('validate',{document_token:documentToken,url}); }
    catch (_) { return {valid:false}; }
  },args:[expectedToken,originalUrl]});
  if (preflight?.result?.valid !== true) throw new Error('stale_document');
  // tabs.update is issued once only. A rejected/lost reply is uncertain, not a
  // signal to submit again. The next observation remains completion evidence.
  try { await chrome.tabs.update(state.binding.tab_id,{url:target.href}); }
  catch (_) { throw new Error('delivery_unknown'); }
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    const tab = await selectedTab(state);
    if (tab.status === 'complete' && !tab.pendingUrl) break;
    await sleep(100);
  }
}
async function injectCommand(state,command) {
  const tab = await selectedTab(state);
  if (!['observe','execute','capture','viewport_image'].includes(command.operation)) throw new Error('unsupported');
  if (command.operation === 'viewport_image') throw new Error('unsupported');
  try {
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:['agent_observe.js','capture_dom.js','executor.js']});
    const [answer] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:async (operation,payload) => {
      try { return {ok:true,result:await globalThis.__agenticTabExecutor.dispatch(operation,payload)}; }
      catch(error) { return {ok:false,error:error?.message}; }
    },args:[command.operation,command.payload || {}]});
    if (!answer?.result) throw new Error('delivery_unknown');
    if (!answer.result.ok) throw new Error(SAFE_ERRORS.has(answer.result.error) ? answer.result.error : 'execution_failed');
    if (command.operation === 'observe') {
      const observed = answer.result.result?.tab_state;
      state.website_activity = {...(state.website_activity || {}),observation:observed && ['visible','hidden'].includes(observed.visibility) && typeof observed.has_focus === 'boolean' ? {visibility:observed.visibility,has_focus:observed.has_focus}:null};
    }
    if (answer.result.result?._navigation_url) {
      const { _navigation_url, _navigation_from_url, ...outcome } = answer.result.result;
      await dispatchNavigation(state,_navigation_url,command.payload?.document_token,_navigation_from_url);
      answer.result.result = outcome;
    }
    await selectedTab(state);
    if (new TextEncoder().encode(JSON.stringify(answer.result.result)).length > 350000) throw new Error('payload_too_large');
    return answer.result.result;
  } catch(error) {
    if (SAFE_ERRORS.has(error?.message)) throw error;
    // A navigation can destroy the isolated world after an action dispatched.
    // Do not assume failure and never dispatch that command a second time.
    if (/permission|Cannot access|host permission/i.test(error?.message || '')) throw new Error('permission_required');
    throw new Error(command.operation === 'execute' ? 'delivery_unknown':'execution_failed');
  }
}
async function acknowledge(state,ack) {
  await relay(state,'/api/extension/runs/'+state.run.run_id+'/result','POST',ack);
  const latest = await readState();
  if (latest.run?.run_id !== state.run.run_id) return false;
  latest.pending = null;
  await writeState(latest);
  return true;
}
async function stopFor(state,error) {
  // Tab events and network callbacks can finish after explicit reconnect. They
  // may stop their old run, but must never replace the new local binding.
  if ((await readState()) !== state) return;
  if (FINISHED.has(state.run?.state) && ['run_expired','run_unavailable'].includes(error?.message)) return;
  state.error = safeError(error);
  if (['run_expired','run_unavailable'].includes(state.error)) {
    state.run = state.run ? {...state.run,state:'failed',guidance:'The browser workflow expired or is no longer available. Start a fresh workflow; retained dashboard history can still be reviewed.'} : null;
    state.pending = null;
    if ((await readState()) === state) await writeState(state);
    return;
  }
  if (state.run && ACTIVE.has(state.run.state)) {
    try {
      if (DASHBOARD_ERRORS.has(state.error)) throw error;
      state.run = {...state.run,...await relay(state,'/api/extension/runs/'+state.run.run_id+'/control','POST',{action:'pause'})};
    }
    catch (_) { state.run = {...state.run,state:'agent_paused'}; }
  }
  if ((await readState()) === state) await writeState(state);
}
async function pump() {
  if (pumping) return;
  pumping = true;
  let state;
  try {
    state = await readState();
    if (!state.binding || !state.run || state.error) return;
    // Durable recovery: repeat only a recorded ACK. A claimed/executing command
    // without an ACK is unknown, not permission to replay an interaction.
    if (state.pending) {
      const ack = state.pending.ack || {request_id:state.pending.request_id,ok:false,result:null,error:'delivery_unknown'};
      if (!await acknowledge(state,ack)) return;
      if (!ack.ok) { await stopFor(state,new Error(ack.error)); return; }
    }
    while (state.run && ACTIVE.has(state.run.state) && !state.error) {
      await selectedTab(state);
      if ((await readState()) !== state) break;
      const next = await relay(state,'/api/extension/runs/'+state.run.run_id+'/next','POST',{});
      if (next.command && !/^[a-f0-9]{32}$/.test(next.command.request_id)) throw new Error('unsupported');
      const claimedState = await readState();
      if (claimedState !== state) {
        // Pause/Resume can race a one-shot claim. Release a same-run command
        // without executing it; never replay the old generation after control.
        if (next.command && claimedState.run?.run_id === state.run.run_id && !FINISHED.has(claimedState.run.state)) {
          const ack = {request_id:next.command.request_id,ok:false,result:null,error:'cancelled'};
          claimedState.pending = {request_id:ack.request_id,phase:'ack_ready',ack};
          await writeState(claimedState);
          await acknowledge(claimedState,ack);
        }
        break;
      }
      if (!next.command) {
        const revision = state.revision;
        const status = await relay(state,'/api/extension/runs/'+state.run.run_id);
        if ((await readState()) !== state) break;
        if (state.revision !== revision) continue;
        state.run = {...state.run,...status};
        await writeState(state);
        if (!ACTIVE.has(state.run.state)) break;
        await sleep(500); continue;
      }
      const command = next.command;
      state.pending = {request_id:command.request_id,phase:'executing'};
      await writeState(state);
      let ack;
      try { ack = {request_id:command.request_id,ok:true,result:await injectCommand(state,command),error:null}; }
      catch(error) { ack = {request_id:command.request_id,ok:false,result:null,error:safeError(error)}; }
      const latest = await readState();
      if (latest.run?.run_id !== state.run.run_id) break;
      if (FINISHED.has(latest.run?.state)) {
        latest.pending = null; await writeState(latest); break;
      }
      // A same-run control change owns the latest state. Preserve it while
      // acknowledging the already dispatched action; do not execute it again.
      state = latest;
      state.pending = {request_id:command.request_id,phase:'ack_ready',ack};
      await writeState(state);
      if (!await acknowledge(state,ack)) break;
      if (!ack.ok && ['access_restriction','origin_changed','tab_closed','permission_required','delivery_unknown','session_changed'].includes(ack.error)) { await stopFor(state,new Error(ack.error)); break; }
      state = await readState();
    }
  } catch(error) {
    const latest = await readState();
    // An explicit reconnect may have replaced the old binding while a command
    // was in flight. Never apply that old command/error to the new workflow.
    if (state?.run?.run_id && latest === state) await stopFor(state,error);
  }
  finally {
    pumping = false;
    const latest = await readState();
    if (latest !== state && ACTIVE.has(latest.run?.state) && !latest.error) pump();
  }
}
async function connect(message) {
  const old = await readState();
  if (old.run && !FINISHED.has(old.run.state)) {
    let stale = DASHBOARD_ERRORS.has(old.error);
    if (!stale) {
      try {
        // Reconnection is not a shortcut around session ownership. A healthy
        // live run remains bound to its current tab and account.
        old.run = {...old.run,...await relay(old,'/api/extension/runs/'+old.run.run_id)};
      } catch(error) {
        if (!DASHBOARD_ERRORS.has(error?.message) && !['run_expired','run_unavailable'].includes(error?.message)) throw error;
        await stopFor(old,error);
        stale = DASHBOARD_ERRORS.has(old.error);
      }
    }
    if (stale && !message.reconnect) return publicState(old);
    if (!stale && !FINISHED.has(old.run.state)) {
      if (message.tab_id != null && message.tab_id !== old.binding.tab_id) throw new Error('A workflow is already bound to another tab. Cancel it before changing tabs.');
      await selectedTab(old); await writeState(old); return publicState(old);
    }
  }
  if (old.binding && (!old.run || FINISHED.has(old.run.state)) && !DASHBOARD_ERRORS.has(old.error) && (message.tab_id == null || message.tab_id === old.binding.tab_id)) {
    const tab = await selectedTab(old);
    const dashboard = await chrome.tabs.get(old.binding.dashboard_tab_id).catch(()=>null);
    await sessionAt(dashboard,old.binding);
    old.binding.url = websiteUrl(tab.url).href;
    old.binding.title = String(tab.title || 'Selected website').slice(0,160);
    await writeState(old);
    return publicState(old);
  }
  let tab;
  if (message.tab_id != null) tab = await chrome.tabs.get(message.tab_id);
  else if (old.binding) tab = await chrome.tabs.get(old.binding.tab_id).catch(()=>null);
  if (!tab) [tab] = await chrome.tabs.query({active:true,currentWindow:true});
  const url = websiteUrl(tab.url);
  const candidates = (await chrome.tabs.query({})).filter(candidate => { try { return DASHBOARDS.has(new URL(candidate.url).origin); } catch (_) { return false; } });
  // Multiple signed-in relays must not silently choose a different account.
  const sessions = [], errors = [];
  for (const dashboard of candidates) {
    try { sessions.push({dashboard,session:await sessionAt(dashboard)}); } catch(error) { errors.push(safeError(error)); }
  }
  const same = sessions.filter(({session}) => !old.binding || (session.username === old.binding.username && session.instance_id === old.binding.instance_id));
  const bound = sessions.find(({dashboard,session}) => dashboard.id === old.binding?.dashboard_tab_id && new URL(dashboard.url).origin === old.binding.dashboard_url && session.csrf === old.binding.csrf && session.instance_id === old.binding.instance_id && session.username === old.binding.username && session.ui_version === old.binding.ui_version);
  const available = bound ? [bound] : same.length ? same : sessions;
  if (available.length !== 1) {
    if (!available.length && errors.length === 1 && DASHBOARD_ERRORS.has(errors[0])) throw new Error(errors[0]);
    throw new Error(available.length ? 'Keep one signed-in local dashboard tab open, then connect again.' : 'Open http://localhost:8120 and sign in, then connect again.');
  }
  const {dashboard,session} = available[0];
  // Explicit reconnect never resumes or replays a command. If the fresh relay
  // proves the exact old account/server/CSRF context, cancel that stale channel
  // to release its job slot. A changed account/session/server is not authority
  // to control the old run; in that case its existing timeout remains in force.
  const state = {binding:{tab_id:tab.id,window_id:tab.windowId,origin:url.origin,url:url.href,title:String(tab.title||'Selected website').slice(0,160),dashboard_tab_id:dashboard.id,dashboard_url:new URL(dashboard.url).origin,username:session.username,csrf:session.csrf,instance_id:session.instance_id,ui_version:session.ui_version},run:null,pending:null,error:null};
  if (message.reconnect && DASHBOARD_ERRORS.has(old.error) && old.run && !FINISHED.has(old.run.state) && old.binding?.csrf === session.csrf && old.binding.instance_id === session.instance_id && old.binding.username === session.username) {
    try { await relay(state,'/api/extension/runs/'+old.run.run_id+'/control','POST',{action:'cancel'}); }
    catch(error) { if (!['run_expired','run_unavailable'].includes(error?.message)) throw error; }
  }
  await writeState(state); return publicState(state);
}
async function handle(message) {
  if (message.operation === 'connect') return connect(message);
  const state = await readState();
  if (message.operation === 'status') {
    if (state.run && !DASHBOARD_ERRORS.has(state.error) && !FINISHED.has(state.run.state)) {
      try {
        const revision = state.revision;
        const status = await relay(state,'/api/extension/runs/'+state.run.run_id);
        if ((await readState()) === state && state.revision === revision) {
          state.run = {...state.run,...status}; await writeState(state);
        }
      }
      catch(error) { await stopFor(state,error); }
    }
    pump(); return publicState(await readState());
  }
  if (message.operation === 'start') {
    if (!state.binding) throw new Error('Connect the website tab first.');
    if (DASHBOARD_ERRORS.has(state.error)) throw new Error(state.error);
    if (state.run && !FINISHED.has(state.run.state)) throw new Error('Pause or cancel the existing workflow first.');
    if (!message.agent_confirmed || !message.authorized || !message.allow_model_api || message.agent_visual_confirmed) throw new Error('Review and approve the DOM-only workflow first.');
    const tab = await activateWebsite(state);
    const body = {url:websiteUrl(tab.url).href,tab_id:tab.id,instructions:message.instructions,record_limit:message.record_limit,output_fields:message.output_fields || [],business_rules:message.business_rules || [],publish_event:!!message.publish_event,agent_confirmed:true,agent_visual_confirmed:false,authorized:true,allow_model_api:true};
    const result = await relay(state,'/api/extension/runs','POST',body);
    // A new run gets a new state object. An old pump must retain its old run ID
    // while its final response/ACK is still in flight.
    const nextState = {...state,run:{...result,state:'agent_running',guidance:'Starting in the selected tab.'},pending:null,error:null};
    await writeState(nextState); pump(); return publicState(nextState);
  }
  if (message.operation === 'control') {
    if (!state.run || !['pause','resume','collect','cancel'].includes(message.action)) throw new Error('No matching workflow action is available.');
    if (DASHBOARD_ERRORS.has(state.error)) throw new Error(state.error);
    // An unknown delivery requires explicit user resume; it is never replayed.
    if (message.action === 'resume') {
      if (state.pending) throw new Error('The previous action is still awaiting acknowledgement.');
      await activateWebsite(state);
    }
    let result;
    try { result = await relay(state,'/api/extension/runs/'+state.run.run_id+'/control','POST',{action:message.action}); }
    catch(error) {
      if (message.action !== 'cancel' || !['run_expired','run_unavailable'].includes(error?.message)) throw error;
      const inactive = {...state,run:{...state.run,state:'failed',guidance:'The backend reports this workflow is no longer available; cancellation cannot be independently confirmed. No command was replayed. You can start another workflow.'},pending:null,error:null};
      await writeState(inactive); return publicState(inactive);
    }
    const controlled = {...state,run:{...state.run,...result},error:null,
      pending:message.action === 'cancel' ? null:state.pending};
    await writeState(controlled);
    if (message.action === 'resume' || message.action === 'collect') pump();
    return publicState(controlled);
  }
  if (message.operation === 'open_review') {
    if (!state.binding || !state.run?.job_id || !/^[a-f0-9-]{32,36}$/.test(state.run.job_id)) throw new Error('No workflow review is available yet.');
    const dashboardTab = await chrome.tabs.get(state.binding.dashboard_tab_id).catch(()=>null);
    const session = await sessionAt(dashboardTab);
    if (session.instance_id !== state.binding.instance_id) throw new Error('dashboard_restarted');
    if (session.ui_version !== state.binding.ui_version) throw new Error('dashboard_updated');
    if (session.username !== state.binding.username) throw new Error('dashboard_account_changed');
    if (session.csrf !== state.binding.csrf) throw new Error('dashboard_csrf_changed');
    await chrome.scripting.executeScript({target:{tabId:state.binding.dashboard_tab_id},func:jobId=>window.postMessage({type:'agentic-extension-review-v1',job_id:jobId},location.origin),args:[state.run.job_id]});
    const dashboard = await chrome.tabs.update(state.binding.dashboard_tab_id,{active:true}); await chrome.windows.update(dashboard.windowId,{focused:true});
    return publicState(state);
  }
  if (message.operation === 'disconnect') {
    if (state.run && !FINISHED.has(state.run.state) && !DASHBOARD_ERRORS.has(state.error)) throw new Error('Cancel the workflow before disconnecting.');
    // A changed dashboard session must never be used to control an old account's
    // run. Drop only our local binding; the old channel is paused/timeout-bound.
    await writeState({}); return publicState({});
  }
  throw new Error('Unknown browser companion operation.');
}
chrome.runtime.onMessage.addListener((message,sender,sendResponse) => {
  if (message?.type !== 'agentic-panel-v1') return false;
  if (sender.id !== chrome.runtime.id || sender.tab || !sender.url?.startsWith(chrome.runtime.getURL(''))) { sendResponse({ok:false,error:'Only the extension panel may control this workflow.'}); return false; }
  const result = handling.then(() => handle(message)).catch(async error => {
    // Preserve failures from Start/Resume/Open review as well as the command
    // pump. Otherwise the next status poll erased the only recovery clue.
    if (DASHBOARD_ERRORS.has(error?.message) || ['model_connection_required','website_focus_required','permission_required','tab_closed','origin_changed'].includes(error?.message)) await stopFor(await readState(),error);
    throw error;
  });
  handling = result.catch(() => {});
  result.then(sendResponse,error=>sendResponse({ok:false,error:error?.message || 'Unable to complete this operation.'}));
  return true;
});
async function removedTab(tabId) {
  const state = await readState();
  if (state.binding && [state.binding.tab_id,state.binding.dashboard_tab_id].includes(tabId) && state.run && !FINISHED.has(state.run.state)) await stopFor(state,new Error(tabId === state.binding.tab_id ? 'tab_closed':'dashboard_tab_closed'));
}
async function updatedTab(tabId,change,tab) {
  const state = await readState();
  if (!state.binding || !state.run || FINISHED.has(state.run.state)) return;
  if (tabId === state.binding.tab_id) {
    const currentUrl = change.url || tab.url || tab.pendingUrl;
    if (!currentUrl && change.status === 'complete') await stopFor(state,new Error('permission_required'));
    else if (currentUrl && new URL(currentUrl).origin !== state.binding.origin) await stopFor(state,new Error('origin_changed'));
  }
  if (tabId === state.binding.dashboard_tab_id) {
    const currentUrl = change.url || tab.url || tab.pendingUrl;
    if (!currentUrl || new URL(currentUrl).origin !== state.binding.dashboard_url) await stopFor(state,new Error('dashboard_origin_changed'));
  }
}
chrome.tabs.onRemoved.addListener(tabId => { removedTab(tabId).catch(() => {}); });
chrome.tabs.onUpdated.addListener((tabId,change,tab) => { updatedTab(tabId,change,tab).catch(() => {}); });
