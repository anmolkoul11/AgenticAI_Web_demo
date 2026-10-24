"use strict";
const byId = id => document.getElementById(id);
const runningStates = new Set(["agent_running", "agent_pausing", "reviewing", "queued", "running"]);
const terminalStates = new Set(["captured", "awaiting_review", "needs_input", "cancelled", "failed", "completed"]);
const reconnectErrors = new Set(["session_changed", "dashboard_signed_out", "dashboard_csrf_changed",
  "dashboard_restarted", "dashboard_updated", "dashboard_account_changed", "dashboard_tab_closed",
  "dashboard_origin_changed", "dashboard_relay_forbidden", "dashboard_unavailable", "dashboard_not_ready"]);
const transportErrors = new Set(["companion_unavailable", "companion_reply_unknown"]);
const errorLabels = {
  companion_unavailable: "The browser companion is not responding. Choose Check status to reconnect to its existing state; closing the panel is not required. This is not a dashboard sign-in error.",
  companion_reply_unknown: "The companion reply was interrupted. Your action may already have run. Choose Check status before starting or resuming again; nothing will be automatically resubmitted.",
  session_changed: "The previous dashboard connection is no longer valid. Refresh and sign in there, then choose Reconnect dashboard below. Old actions will not be replayed.",
  dashboard_signed_out: "The local dashboard is signed out or its session expired. Sign in there, then choose Reconnect dashboard. Start a fresh workflow afterwards.",
  dashboard_csrf_changed: "The dashboard sign-in session changed. Refresh its tab, then choose Reconnect dashboard. The old workflow cannot be resumed under a new session.",
  dashboard_restarted: "The dashboard server restarted. Refresh its tab and sign in, then choose Reconnect dashboard and start a fresh workflow.",
  dashboard_updated: "The dashboard and this connection have different application versions. Refresh the dashboard tab, then choose Reconnect dashboard.",
  dashboard_account_changed: "The signed-in dashboard account changed. Review that account, refresh its tab, then reconnect explicitly. No old workflow will move to the new account.",
  dashboard_tab_closed: "The connected dashboard tab was closed. Open one signed-in local dashboard tab, then choose Reconnect dashboard.",
  dashboard_origin_changed: "The connected dashboard tab moved away from its original address. Open the intended local dashboard, sign in and reconnect explicitly.",
  dashboard_relay_forbidden: "The dashboard rejected the transfer's session/origin check. Refresh its tab and reconnect. If this repeats, report dashboard_relay_forbidden; it is not an OpenAI key error.",
  dashboard_unavailable: "The local dashboard cannot be reached. Start the local server and open its signed-in tab, then reconnect. Nothing was automatically resubmitted.",
  dashboard_not_ready: "The dashboard page is loading, signed out or blocked pending refresh. Open it, resolve the displayed notice, then choose Reconnect dashboard.",
  model_connection_required: "Configure your API connection in the signed-in dashboard, then approve and start the workflow again. A server restart may clear a session-only key; this is not a website-login error.",
  website_focus_required: "The browser could not activate the connected website window. Open that tab, then approve Start or Resume again. No new paid workflow was started by this failed activation.",
  unsupported: "Connect from the HTTPS website tab, not from the dashboard or a browser settings page. An existing connection keeps its original website tab.",
  permission_required: "Browser access to this tab was lost. Open the extension from the website tab again, then explicitly resume if the run is still available.",
  origin_changed: "The website moved to another origin. Automation paused. Return to the connected site or cancel and connect a new workflow.",
  tab_closed: "The connected tab was closed. Cancel this workflow before connecting another tab.",
  delivery_unknown: "The last action's outcome is unknown and was not replayed. Inspect the tab before deciding whether to resume.",
  access_restriction: "The website needs your attention. Complete any verification yourself; access restrictions cannot be bypassed by this extension.",
  execution_failed: "The browser connection could not complete this operation. Inspect the website and dashboard before trying again.",
  run_expired: "This browser workflow expired. The website stays open. Open any existing results, then reconnect and start a new workflow if needed.",
  run_unavailable: "This workflow is no longer available on the current backend. Reconnect to start a new one; saved dashboard results are unchanged.",
  operation_conflict: "That operation is not available in the current workflow state. Check the latest status before choosing another action.",
};
let current = {connection:null,run:null}, busy = false, timer, signature = "", pollInFlight = false, panelActive = true, transportError = null;
function showError(value) {
  byId("error").textContent = errorLabels[value] || value || "";
  byId("error").hidden = !value;
}
function render(value, synchronized = false) {
  if (value?.ok === false) { showError(value.error); return; }
  if (Number.isSafeInteger(value?.revision) && value.revision < (current.revision || 0)) return;
  if (synchronized) transportError = null;
  current = value || current;
  const connection = current.connection, run = current.run, state = run?.state;
  const needsReconnect = current.reconnect_required === true || reconnectErrors.has(current.error);
  const needsStatus = transportErrors.has(transportError);
  const live = !!run && !terminalStates.has(state), report = run?.agent_report || {};
  byId("connection").textContent = connection ? `${connection.title || "Selected website"} — ${connection.url}` :
    "Open the website, finish any sign-in, then connect. Keep one signed-in dashboard tab open at localhost:8120.";
  const observedTab = current.website_activity?.observation;
  const activityNote = observedTab ? ` Last page observation: ${observedTab.visibility}; document focus ${observedTab.has_focus ? "yes" : "no"}.` : "";
  byId("account").textContent = connection ? `Dashboard account: ${connection.username}. Only this selected tab is connected.${activityNote}` : "";
  byId("connect").disabled = busy || (live && !needsReconnect && !needsStatus);
  byId("connect").textContent = needsStatus ? "Check status" : needsReconnect ? "Reconnect dashboard" : connection ? "Check connection" : "Connect website tab";
  byId("disconnect").hidden = !connection;
  byId("disconnect").disabled = busy || needsStatus || (live && !needsReconnect);
  byId("start").disabled = busy || needsStatus || !connection || live || needsReconnect;
  byId("instructions").disabled = live && !needsReconnect;
  byId("activity").hidden = !run;
  byId("spinner").hidden = needsReconnect || !runningStates.has(state);
  byId("state").textContent = state ? state.replaceAll("_", " ") : "Idle";
  byId("guidance").textContent = run?.guidance || "";
  byId("calls").max = report.max_calls || 30;
  byId("calls").value = report.calls || 0;
  const count = Array.isArray(report.captured_pages) ? report.captured_pages.length : 0;
  byId("usage").textContent = `${report.calls || 0}/${report.max_calls || 30} paid navigation decisions attempted · ${count} retained page(s). This bar shows the decision budget, not result completeness.`;
  byId("observation-diagnostics").textContent = JSON.stringify(report.observation_diagnostics || {}, null, 2);
  byId("pause").hidden = !["agent_running", "agent_pausing"].includes(state);
  byId("resume").hidden = state !== "agent_paused";
  byId("collect").hidden = state !== "agent_paused" || !count;
  byId("cancel").hidden = !live;
  byId("review").disabled = busy || needsReconnect || !run?.job_id;
  for (const id of ["pause", "resume", "collect", "cancel"]) byId(id).disabled = busy || needsReconnect || needsStatus;
  const actions = Array.isArray(report.actions) ? report.actions.slice(-6) : [];
  const nextSignature = JSON.stringify(actions);
  if (nextSignature !== signature) {
    signature = nextSignature;
    byId("actions").replaceChildren(...actions.map(action => {
      const li = document.createElement("li");
      li.textContent = `${action.action || "Action"}${action.control ? " — " + action.control : ""}: ${(action.status || "unknown").replaceAll("_", " ")}. ${action.note || action.guidance || action.explanation || ""}`;
      return li;
    }));
  }
  showError(transportError || current.error);
}
async function requestReply(message, timeout) {
  let deadline;
  try {
    return await Promise.race([
      chrome.runtime.sendMessage(message),
      new Promise((_,reject) => { deadline = setTimeout(() => reject(new Error('port_timeout')),timeout); }),
    ]);
  } finally { clearTimeout(deadline); }
}
async function send(operation, values = {}) {
  // Only a read-only status request can retry after a sleeping/lost worker port.
  // Never retry Start, Resume, Collect or another potentially dispatched action.
  for (let attempt=0;attempt<(operation === "status" ? 2:1);attempt++) {
    let reply;
    try { reply = await requestReply({type:"agentic-panel-v1",operation,...values},operation === "status" ? 3000:12000); }
    catch (_) { /* Classify port failure separately from authenticated relay errors. */ }
    if (reply?.ok === false) throw new Error(reply.error || "execution_failed");
    if (reply?.ok === true) return reply;
    if (operation === "status" && attempt === 0) { await new Promise(resolve=>setTimeout(resolve,100)); continue; }
    throw new Error(["status","open_review"].includes(operation) ? "companion_unavailable":"companion_reply_unknown");
  }
}
async function action(operation, values = {}) {
  busy = true; render(current); showError(null);
  try { render(await send(operation, values), true); }
  catch(error) { if (transportErrors.has(error.message)) transportError = error.message; else current = {...current,error:error.message}; }
  finally { busy = false; render(current); }
}
byId("connect").onclick = async () => {
  if (transportErrors.has(transportError)) { await action("status"); return; }
  const reconnect = current.reconnect_required === true || reconnectErrors.has(current.error);
  const [tab] = current.connection?.tab_id != null ? [{id:current.connection.tab_id}] :
    await chrome.tabs.query({active:true,currentWindow:true});
  if (reconnect) byId("consent").checked = false;
  await action("connect", {...(tab?.id == null ? {} : {tab_id:tab.id}),reconnect});
};
byId("disconnect").onclick = () => action("disconnect");
byId("review").onclick = () => action("open_review");
byId("task-form").onsubmit = async event => {
  event.preventDefault();
  const fields = byId("fields").value.split(",").map(value=>value.trim()).filter(Boolean);
  if (fields.length > 16 || new Set(fields).size !== fields.length || fields.some(name=>!/^[a-z][a-z0-9_]{0,39}$/.test(name))) {
    showError("Use up to 16 unique lowercase output field names, separated by commas."); return;
  }
  const field = byId("rule-field").value.trim(), value = byId("rule-value").value.trim();
  if ((field && !value) || (!field && value) || (field && !/^[a-z][a-z0-9_]{0,39}$/.test(field))) {
    showError("Provide a valid rule field and value, or leave both blank."); return;
  }
  if (!byId("consent").checked) { showError("Approve the paid workflow before starting."); return; }
  await action("start", {instructions:byId("instructions").value.trim(),record_limit:Number(byId("limit").value),output_fields:fields,
    business_rules:field ? [{field,operator:byId("rule-op").value,value}] : [],publish_event:byId("publish").checked,
    agent_confirmed:true,agent_visual_confirmed:false,authorized:true,allow_model_api:true});
  byId("consent").checked = false;
};
for (const name of ["pause", "resume", "collect", "cancel"]) {
  byId(name).onclick = async () => {
    if (["resume", "collect"].includes(name) && !byId("consent").checked) {
      showError("Review the selected tab and renew the paid-workflow approval before resuming or collecting."); return;
    }
    await action("control", {action:name});
    if (["resume", "collect"].includes(name)) byId("consent").checked = false;
  };
}
chrome.runtime.onMessage.addListener(message => {
  if (message?.type === "agentic-panel-state-v1") render(message, true);
});
async function poll() {
  if (pollInFlight || !panelActive) return;
  pollInFlight = true;
  try { if (!busy) render(await send("status"), true); }
  catch(error) { if (transportErrors.has(error.message)) transportError = error.message; else current = {...current,error:error.message}; render(current); }
  finally { pollInFlight = false; clearTimeout(timer); if (panelActive) timer = setTimeout(poll, 2000); }
}
const resumePolling = () => { panelActive = true; clearTimeout(timer); poll(); };
window.addEventListener("pagehide", () => { panelActive = false; clearTimeout(timer); });
window.addEventListener("pageshow", resumePolling);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") resumePolling();
  else { panelActive = false; clearTimeout(timer); }
});
poll();
