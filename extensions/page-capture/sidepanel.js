"use strict";
const byId = id => document.getElementById(id);
const runningStates = new Set(["agent_running", "agent_pausing", "reviewing", "queued", "running"]);
const terminalStates = new Set(["captured", "awaiting_review", "needs_input", "cancelled", "failed", "completed"]);
const reconnectErrors = new Set(["session_changed", "dashboard_signed_out", "dashboard_csrf_changed",
  "dashboard_restarted", "dashboard_updated", "dashboard_account_changed", "dashboard_tab_closed",
  "dashboard_origin_changed", "dashboard_relay_forbidden", "dashboard_unavailable", "dashboard_not_ready"]);
const transportErrors = new Set(["companion_unavailable", "companion_reply_unknown"]);
const workflowLabels = {
  agent_running:"Working on your request", agent_pausing:"Pausing…",
  reviewing:"Preparing your results", queued:"Getting ready", running:"Working on your request",
  agent_paused:"Paused", needs_input:"More information needed", failed:"Couldn't finish",
  captured:"Results ready to review", awaiting_review:"Results ready to review",
  completed:"Task complete", cancelled:"Stopped",
};
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
  model_connection_required: "Configure your API connection in the signed-in dashboard, then start the workflow again. A server restart may clear a session-only key; this is not a website-login error.",
  website_focus_required: "The browser could not confirm focus on the connected website. Inspect that tab and the latest action evidence, then choose Start or Resume again. Nothing was automatically retried.",
  native_input_consent_required: "Choose Start or Resume to begin browser-level control of the connected website tab.",
  native_input_unavailable: "Browser-level input could not attach to this website tab. Check the extension's debugger permission and close DevTools or another debugger on this tab, then choose Start or Resume again. No automatic retry was made; inspect the latest action evidence first.",
  native_input_detached: "Browser-level input was detached. The last action may have run; inspect the website and action evidence before choosing Resume. Cancelling the browser's debugging warning or opening DevTools can detach control. Nothing was automatically replayed.",
  extension_update_required: "The extension worker and website helper are different versions. In edge://extensions or chrome://extensions, reload Browser Companion 0.5.21 from this project's extensions/page-capture folder, refresh the website, reconnect and start a fresh workflow. Nothing was automatically retried.",
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
let requestRun = null;
function recordLimitValid() {
  const value = Number(byId("limit").value);
  return byId("limit").value !== "" && Number.isInteger(value) && value >= 1 && value <= 500;
}
function updateRecordLimit(source, commit = false) {
  const input = byId("limit"), slider = byId("limit-slider");
  let value = Number(source.value);
  if (commit && source.value !== "" && Number.isFinite(value)) {
    value = Math.max(0, Math.min(500, Math.round(value)));
    source.value = String(value);
  }
  const valid = source.value !== "" && Number.isInteger(value) && value >= 0 && value <= 500;
  if (valid) {
    input.value = String(value); slider.value = String(value);
    // Larger limits need batched collection; preserve the user's chosen count.
    if (value > 50) byId("extent").value = "all_results";
  }
  const all = byId("extent").value === "all_results";
  setText("limit-help", !valid ? "Enter a whole number from 0 to 500." : value === 0 ?
    "Choose at least 1 record to start. No task runs at 0." :
    `Collect up to ${value} records. ${value > 50 ? "Uses the result list and additional pages when available. " : ""}The source may provide fewer.`);
  setText("result-cost", valid && value > 0 ? all ?
    `Collects up to ${value} records, using paid extraction in batches of up to 10. Review before saving.` :
    `Collects a preview of up to ${value} records using your configured AI service. Review before saving.` :
    "Choose a record limit before starting.");
}
function setText(id, text) {
  const element = byId(id);
  // Keep live regions and layout stable between identical status polls.
  if (element.textContent !== text) element.textContent = text;
}
function connectionPresentation(connection, state, report, error, needsReconnect) {
  if (!connection || error === "tab_closed") return {
    tone:"disconnected", label:"Browser agent is not connected",
    hint:current.selection_notice || "Open a website tab and keep your dashboard signed in.",
  };
  if (error || needsReconnect || current.selection_notice) return {
    tone:"attention", label:"Browser agent needs attention",
    hint:current.selection_notice || "Check the message below to continue.",
  };
  if (["agent_paused", "agent_pausing", "needs_input", "failed"].includes(state)) return {
    tone:"attention", label:state === "agent_pausing" ? "Browser agent is pausing" :
      state === "agent_paused" && !report.awaiting_user_input ? "Browser agent is paused" : "Browser agent needs your help",
    hint:state === "agent_pausing" ? "Finishing the current action before pausing." :
      state === "agent_paused" ? "Check the website, then choose Resume task when you're ready." : "Review the task message for the next step.",
  };
  return {tone:"connected", label:"Browser agent is connected",
    hint:runningStates.has(state) ? "Working in your connected website tab." :
      ["captured", "awaiting_review", "completed"].includes(state) ? "Your results are ready for review." : "Ready when you are. Describe your task below."};
}
function showError(value) {
  setText("error", errorLabels[value] || value || "");
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
  const runKey = run ? run.run_id || run.job_id || "current-task" : null;
  if (runKey !== requestRun) {
    // Collapse only for a new run, never override a user's choice on each poll.
    byId("request-details").open = !run;
    requestRun = runKey;
  }
  setText("task-title", run ? "Your request" : "What would you like to find?");
  const status = connectionPresentation(connection, state, report, transportError || current.error, needsReconnect);
  const working = status.tone === "connected" && runningStates.has(state);
  byId("connection-status").dataset.tone = status.tone;
  byId("connection-status").dataset.working = String(working);
  setText("connection-status-label", status.label);
  setText("connection-hint", run?.saved_run_id && !needsReconnect && !needsStatus && !current.error ?
    "Your results are saved in the dashboard. You can view them or start another task." : status.hint);
  setText("website-title", connection?.title || (connection ? "Selected website" : "No website selected"));
  let domain = "Your own browser tab";
  try { if (connection?.url) domain = new URL(connection.url).hostname; } catch (_) { domain = "Selected website"; }
  setText("website-domain", domain);
  setText("connection", connection ? `${connection.title || "Selected website"} — ${connection.url}` :
    "Select a website tab to connect automatically while idle. Keep one signed-in dashboard tab open at localhost:8120. A task starts only when you choose Start task.");
  const observedTab = current.website_activity?.observation;
  const activityNote = observedTab ? ` Last page observation: ${observedTab.visibility}; document focus ${observedTab.has_focus ? "yes" : "no"}.` : "";
  const selectionNote = current.selection_notice ? ` ${current.selection_notice}` : "";
  setText("account", (connection ? `Dashboard account: ${connection.username}. ${live ? "This task stays in its connected tab until it finishes or you stop it." : "Idle connection follows the selected website tab."}${activityNote}` : "") + selectionNote);
  byId("connect").disabled = busy || (live && !needsReconnect && !needsStatus);
  byId("connect").textContent = needsStatus ? "Check status" : needsReconnect ? "Reconnect dashboard" : connection ? "Check connection" : "Connect website tab";
  byId("disconnect").hidden = !connection;
  byId("disconnect").disabled = busy || needsStatus || (live && !needsReconnect);
  byId("start").disabled = busy || needsStatus || !connection || live || needsReconnect || !recordLimitValid();
  byId("instructions").disabled = live && !needsReconnect;
  byId("activity").hidden = !run;
  setText("activity-title", run && terminalStates.has(state) && current.run_tab_id !== connection?.tab_id ? "Previous results" : "Your progress");
  byId("activity").dataset.tone = ["agent_paused", "agent_pausing", "needs_input", "failed"].includes(state) || current.error || needsStatus || needsReconnect ?
    "attention" : ["captured", "awaiting_review", "completed"].includes(state) ? "ready" : state === "cancelled" ? "stopped" : "working";
  byId("spinner").hidden = !working;
  setText("state", run?.execution_job_id && ["queued", "running"].includes(state) ? "Saving your results" :
    run?.saved_run_id && state === "completed" ? "Results saved" :
    state === "agent_paused" && report.awaiting_user_input ? "Waiting for you" : workflowLabels[state] || "Ready when you are");
  setText("guidance", run?.guidance || "");
  byId("guidance").hidden = !run?.guidance;
  byId("calls").max = report.max_calls || 30;
  byId("calls").value = report.calls || 0;
  const count = Array.isArray(report.captured_pages) ? report.captured_pages.length : 0;
  setText("step-count", `${report.calls || 0} / ${report.max_calls || 30} AI steps`);
  const collected = report.listing_collection;
  setText("pages-collected", collected ? `${collected.records_collected} listings · ${collected.result_pages} result pages${collected.source_preview_only ? " · source preview" : ""}` :
    `${count} ${count === 1 ? "page" : "pages"} collected`);
  setText("usage", "Steps used, not percentage complete.");
  setText("observation-diagnostics", JSON.stringify(report.observation_diagnostics || {}, null, 2));
  byId("pause").hidden = !["agent_running", "agent_pausing"].includes(state);
  byId("resume").hidden = state !== "agent_paused";
  byId("collect").hidden = state !== "agent_paused" || !count;
  byId("cancel").hidden = !live || !!run?.execution_job_id;
  setText("review", run?.saved_run_id ? "View saved results →" : "Review results →");
  setText("review-note", run?.saved_run_id ? "Opens the existing saved results in your dashboard." :
    run?.execution_job_id ? "Your approval is being processed or needs attention. Opens the existing save attempt." :
    "Opens your dashboard. Nothing is saved until you approve.");
  byId("review").disabled = busy || needsReconnect || !run?.job_id;
  for (const id of ["pause", "resume", "collect", "cancel"]) byId(id).disabled = busy || needsReconnect || needsStatus;
  const actions = Array.isArray(report.actions) ? report.actions.slice(-6) : [];
  const nextSignature = JSON.stringify(actions);
  if (nextSignature !== signature) {
    signature = nextSignature;
    byId("actions").replaceChildren(...actions.map(action => {
      const li = document.createElement("li");
      li.textContent = `${action.action || "Action"}${action.control ? " — " + action.control : ""}: ${(action.status || "unknown").replaceAll("_", " ")}. ${action.note || action.guidance || action.explanation || ""}`;
      if (action.action === "set_counter") {
        const detail = document.createElement("p"); detail.className = "muted";
        const count = value => Number.isInteger(value) && value >= 0 && value <= 100 ? String(value) : "unconfirmed";
        const attempts = Number.isInteger(action.attempts) && action.attempts >= 0 && action.attempts <= 30 ? String(action.attempts) : "not reported";
        const dispatched = action.dispatched === true ? "yes" : action.dispatched === false ? "no" : "not reported";
        detail.textContent = `Counter: before ${count(action.before)}; requested ${count(action.expected)}; observed ${count(action.observed)}. Input attempts: ${attempts}; dispatched: ${dispatched}.`;
        li.append(detail);
      }
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
  if (transportErrors.has(transportError)) { await action("status", {follow_selected_tab:true}); return; }
  const reconnect = current.reconnect_required === true || reconnectErrors.has(current.error);
  const [selected] = await chrome.tabs.query({active:true,currentWindow:true});
  const tab = reconnect || !selected?.url?.startsWith("https:") ?
    (current.connection?.tab_id != null ? {id:current.connection.tab_id} : selected) : selected;
  await action("connect", {...(tab?.id == null ? {} : {tab_id:tab.id}),reconnect});
};
byId("disconnect").onclick = () => action("disconnect");
byId("review").onclick = () => action("open_review");
byId("extent").onchange = () => {
  updateRecordLimit(byId("limit")); render(current);
};
for (const id of ["limit", "limit-slider"]) {
  byId(id).oninput = () => { updateRecordLimit(byId(id)); render(current); };
  byId(id).onchange = () => { updateRecordLimit(byId(id), true); render(current); };
}
byId("task-form").onsubmit = async event => {
  event.preventDefault();
  if (!recordLimitValid()) { showError("Choose a whole number from 1 to 500 records before starting."); return; }
  const fields = byId("fields").value.split(",").map(value=>value.trim()).filter(Boolean);
  if (fields.length > 16 || new Set(fields).size !== fields.length || fields.some(name=>!/^[a-z][a-z0-9_]{0,39}$/.test(name))) {
    showError("Use up to 16 unique lowercase output field names, separated by commas."); return;
  }
  const field = byId("rule-field").value.trim(), value = byId("rule-value").value.trim();
  if ((field && !value) || (!field && value) || (field && !/^[a-z][a-z0-9_]{0,39}$/.test(field))) {
    showError("Provide a valid rule field and value, or leave both blank."); return;
  }
  await action("start", {instructions:byId("instructions").value.trim(),record_limit:Number(byId("limit").value),output_fields:fields,
    collection_extent:byId("extent").value,
    business_rules:field ? [{field,operator:byId("rule-op").value,value}] : [],publish_event:byId("publish").value === "yes",
    agent_confirmed:true,agent_visual_confirmed:false,authorized:true,allow_model_api:true,native_input_confirmed:true});
};
for (const name of ["pause", "resume", "collect", "cancel"]) {
  byId(name).onclick = async () => {
    await action("control", {action:name,...(name === "resume" ? {native_input_confirmed:true} : {})});
  };
}
chrome.runtime.onMessage.addListener(message => {
  if (message?.type === "agentic-panel-state-v1") render(message, true);
});
async function poll() {
  if (pollInFlight || !panelActive) return;
  pollInFlight = true;
  try { if (!busy) render(await send("status", {follow_selected_tab:true}), true); }
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
