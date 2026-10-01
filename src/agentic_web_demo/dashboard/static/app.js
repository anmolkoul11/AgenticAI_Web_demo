"use strict";
const $ = id => document.getElementById(id);
const UI_VERSION = "2026-10-01.2";
let instanceId = null, connectionBlocked = false;
const connectionPanel = document.createElement("section");
connectionPanel.className = "notice"; connectionPanel.hidden = true; connectionPanel.setAttribute("role", "alert");
const connectionText = document.createElement("p"), refreshButton = document.createElement("button");
refreshButton.textContent = "Refresh application";
refreshButton.onclick = () => location.reload();
connectionPanel.append(connectionText, refreshButton);
document.querySelector("main").prepend(connectionPanel);
function connectionWarning(text) {
  if (typeof clearWebCapture === "function") clearWebCapture();
  connectionBlocked = true; clearTimeout(timer);
  connectionText.textContent = text; connectionPanel.hidden = false;
  $("api-key").value = ""; $("password").value = ""; $("register-password").value = "";
  $("web-login-password").value = ""; $("web-login-user").value = "";
  $("admin-password").value = "";
  $("consent").checked = false; $("approved").checked = false; $("execute").disabled = true;
}
async function checkConnection() {
  try {
    const response = await fetch("/api/session", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("unavailable");
    const session = await response.json();
    if (session.ui_version !== UI_VERSION) {
      connectionWarning("The application has been updated. Refresh to load the matching version. Unsaved form entries will be lost.");
    } else if (instanceId && instanceId !== session.instance_id) {
      connectionWarning("The server restarted. Refresh and sign in again, then re-enter your session API key if needed. Check job history before retrying any work.");
    } else if (signedIn && !session.authenticated) {
      connectionWarning("Your session expired. Refresh and sign in again. Your saved account and jobs are unchanged; re-enter your API key if needed.");
    } else if (connectionBlocked) {
      connectionText.textContent = "The server is reachable again. Refresh to reconnect, then check job history before retrying. No work was automatically resubmitted.";
    }
    instanceId = session.instance_id;
  } catch (_) {
    connectionWarning("Connection to the dashboard was lost. Waiting for the server; no work will be automatically resubmitted. Refresh when it is available.");
  }
}
let csrf = "", selected = null, timer = null, records = [], decisions = [], signedIn = false, currentJob = null;
let activeView = "custom", isAdmin = false, modelConfigured = false, recordsLoaded = false;
const statusLabels = {queued: "Queued", running: "Running", awaiting_review: "Review needed", completed: "Completed", needs_input: "Needs information", unsupported: "Unsupported request", policy_rejected: "Outside search policy", failed: "Failed", interrupted: "Interrupted"};
const stageLabels = {plan_request: "Interpret request", validate_plan: "Validate search", extract: "Sign in & extract", save: "Save records", export: "Export results", evaluate: "Evaluate rules", publish: "Publish events", receive: "Receive events", verify: "Verify receipts"};
function setBadge(element, text, tone = "neutral") { element.textContent = text; element.dataset.tone = tone; }
function statusTone(status) {
  if (status === "completed") return "success";
  if (["running", "queued"].includes(status)) return "active";
  if (status === "failed") return "error";
  return "warning";
}
function showView(view, moveFocus = false) {
  if (!["custom", "studio", "history", "connection", "admin"].includes(view) || (view === "admin" && !isAdmin)) view = "custom";
  activeView = view;
  for (const page of document.querySelectorAll("[data-page]")) page.hidden = page.dataset.page !== view;
  for (const button of document.querySelectorAll("[data-view]")) {
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (moveFocus) {
    const title = document.querySelector(`[data-page="${view}"] h1`);
    title.tabIndex = -1; title.focus(); title.scrollIntoView({block: "start"});
  }
}
for (const button of document.querySelectorAll("[data-view]")) button.onclick = () => showView(button.dataset.view, true);
function metrics(result = {}) {
  $("metric-records").textContent = result.record_count ?? (recordsLoaded ? records.length : "—");
  $("metric-matches").textContent = result.evaluation?.matched ?? "—";
  $("metric-events").textContent = result.delivery?.published ?? "—";
  $("metric-receipts").textContent = result.receipts_verified ?? "—";
}
function futureDate(days) {
  const date = new Date(); date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
}
const labels = {check_in: "Check-in date", check_out: "Check-out date", city: "City", min_price: "Minimum nightly price", max_price: "Maximum nightly price", min_rating: "Minimum rating", currency: "Currency", rating_scale: "Rating scale", price_basis: "Price basis"};
function authPage() {
  $("auth-shell").hidden = signedIn;
  const registration = location.hash === "#register";
  $("login-panel").hidden = signedIn || registration;
  $("register-panel").hidden = signedIn || !registration;
  $("password").value = ""; $("register-password").value = "";
  if (!signedIn) (registration ? $("register-user") : $("username")).focus();
}
window.addEventListener("hashchange", () => { message(); authPage(); });
function showFeedback(job) {
  const result = job.result || {}, status = job.status;
  const visible = ["needs_input", "unsupported", "failed", "interrupted", "policy_rejected"].includes(status);
  $("feedback").hidden = !visible;
  if (!visible) return;
  $("feedback").dataset.severity = status === "failed" ? "error" : "warning";
  $("feedback-title").textContent = {needs_input: "A little more information is needed", unsupported: "This search is not supported yet", failed: "This step could not be completed", interrupted: "This job was interrupted", policy_rejected: "Your search exceeds the configured policy"}[status];
  $("feedback-text").textContent = result.guidance || job.guidance || "Review your search and configuration before continuing.";
  $("feedback-fields").replaceChildren();
  for (const field of Array.isArray(result.missing_fields) ? result.missing_fields : []) {
    const item = document.createElement("li"); item.textContent = labels[field] || String(field).replaceAll("_", " "); $("feedback-fields").append(item);
  }
  const planning = job.kind === "plan";
  $("feedback-next").textContent = planning ? "Edit the complete search below and submit a new proposal. Nothing is retried automatically. Natural-language submissions require renewed paid API consent." : "Inspect the job evidence and service connections before starting another execution. Earlier stages may already have saved data or published events.";
  $("edit-request").hidden = !planning; $("use-form").hidden = !planning;
}
function editSearch(useForm = false) {
  if (!currentJob) return;
  showView("studio"); $("framework").value = currentJob.framework;
  if (useForm) $("mode").value = "structured";
  modeChanged();
  const field = $("mode").value === "model-assisted" ? $("request") : $("check-in");
  $("plan-form").scrollIntoView({behavior: "smooth", block: "start"}); field.focus();
  message("Review all search fields before submitting. The guided form does not automatically copy model interpretations.");
}
const terminal = status => !["queued", "running"].includes(status);
function message(text = "") {
  $("message").textContent = text;
  if (text) $("message").scrollIntoView({block: "nearest"});
}
async function api(path, data) {
  if (connectionBlocked) throw new Error("Refresh the application to reconnect before continuing.");
  let response;
  try {
    response = await fetch(path, {method: data === undefined ? "GET" : "POST",
      headers: data === undefined ? {} : {"Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Dashboard-Version": UI_VERSION},
      body: data === undefined ? undefined : JSON.stringify(data)});
  } catch (_) {
    connectionWarning("Connection lost. The request may have reached the server. Refresh and inspect job history before retrying; nothing is automatically resubmitted.");
    throw new Error("Connection lost. See the reconnect notice above.");
  }
  const body = await response.json();
  if (body.code === "ui_outdated") connectionWarning(body.detail);
  if (response.status === 401 || (response.status === 403 && body.detail?.includes("Session expired"))) {
    if (path !== "/api/login") connectionWarning("Your session is no longer valid. Refresh and sign in again. Re-enter your API key if needed.");
  }
  if (!response.ok) throw new Error(body.detail || "Request failed. Reload and try again.");
  return body;
}
function modeChanged() {
  const model = $("mode").value === "model-assisted";
  $("structured").hidden = model; $("structured").disabled = model;
  $("natural").hidden = !model; $("natural").disabled = !model;
  $("consent").checked = false;
  $("mode-help").textContent = model ? "AI drafts the plan; you review it. A model request incurs API usage." : "You supply exact criteria. No AI call or model cost is needed.";
  $("model-help").hidden = !model || modelConfigured;
}
async function readiness() {
  const status = await api("/api/readiness");
  setBadge($("portal-badge"), `Portal · ${status.portal_port_open ? "reachable" : "offline"}`, status.portal_port_open ? "success" : "error");
  setBadge($("nats-badge"), `NATS · ${status.nats_port_open ? "reachable" : "offline"}`, status.nats_port_open ? "success" : "error");
  $("readiness").textContent = `Portal: ${status.portal_port_open ? "port reachable" : "not reachable"} · NATS: ${status.nats_port_open ? "port reachable" : "not reachable"}. ${status.note}`;
}
async function workspace() {
  signedIn = true; authPage();
  $("login-panel").hidden = true; $("workspace").hidden = false; $("logout").hidden = false;
  const cfg = await api("/api/config");
  isAdmin = cfg.role === "admin"; modelConfigured = cfg.model_configured;
  $("admin-nav").hidden = !isAdmin;
  $("account-label").hidden = false; $("account-label").textContent = cfg.username;
  $("account-label").title = `${cfg.username} · ${cfg.role}`;
  setBadge($("model-badge"), modelConfigured ? "API key · configured, unverified" : "API key · optional", modelConfigured ? "active" : "neutral");
  $("model-help").hidden = $("mode").value !== "model-assisted" || modelConfigured;
  if (modelConfigured) $("model-id").value = cfg.model;
  showView(activeView);
  $("configuration").textContent = `Signed in: ${cfg.username} · Target: ${cfg.target} · Model: ${cfg.model} · Hotel price and rating rules come from each approved request.`;
  $("key-status").textContent = cfg.model_configured ? `${cfg.model}: session key configured, access not verified.` : "No API key for this session. Guided forms are available.";
  $("storage-status").textContent = `${cfg.secure_storage_label}. Saved key: ${cfg.credential_saved ? "yes" : "no"}. ${cfg.credential_notice || ""}`;
  $("remember-key").disabled = !cfg.secure_storage_available;
  $("remember-key").checked = false;
  $("forget-key").disabled = !cfg.credential_saved;
  $("admin-panel").hidden = cfg.role !== "admin";
  if (cfg.role === "admin") await loadAdmin();
  $("cities").replaceChildren();
  for (const city of cfg.cities) { const option = document.createElement("option"); option.value = city; $("cities").append(option); }
  await Promise.all([readiness(), loadHistory()]);
}
async function loadHistory() {
  const jobs = await api("/api/jobs"); $("history").replaceChildren();
  $("history-count").textContent = jobs.length;
  if (!jobs.length) {
    const empty = document.createElement("div"); empty.className = "empty-state";
    const title = document.createElement("strong"); title.textContent = "A fresh workspace.";
    const copy = document.createElement("p"); copy.textContent = "Create your first proposal in Search Studio. Its evidence will be saved here.";
    empty.append(title, copy); $("history").append(empty);
  }
  for (const job of jobs) {
    const button = document.createElement("button");
    button.className = "history-item"; button.setAttribute("aria-pressed", String(job.job_id === selected));
    const copy = document.createElement("span"), title = document.createElement("strong"), time = document.createElement("small"), badge = document.createElement("span"), arrow = document.createElement("span");
    copy.className = "history-copy"; badge.className = "badge"; arrow.className = "history-arrow"; arrow.textContent = "→"; arrow.setAttribute("aria-hidden", "true");
    title.textContent = `${job.framework === "crewai" ? "CrewAI" : "LangGraph"} · ${job.kind.startsWith("custom-") ? "Custom website · " + job.kind.slice(7) : job.kind === "plan" ? "Search proposal" : "Workflow execution"}`;
    time.textContent = `${new Date(job.created_at).toLocaleString()} · ${job.job_id.slice(0, 8)}`;
    setBadge(badge, statusLabels[job.status] || job.status, statusTone(job.status));
    copy.append(title, time); button.append(copy, badge, arrow);
    button.onclick = () => {
      if (job.kind.startsWith("custom-")) { showView("custom", true); customSelect(job.job_id).catch(e => message(e.message)); }
      else { showView("studio", true); select(job.job_id).catch(e => message(e.message)); }
    };
    $("history").append(button);
  }
}
function table() {
  const query = $("filter").value.toLowerCase(); $("records").replaceChildren();
  const outcome = $("decision-filter").value;
  const visible = records.filter(r => {
    const decision = decisions.find(d => d.listing_id === r.listing_id);
    return `${r.title} ${r.city} ${r.listing_id}`.toLowerCase().includes(query) && (outcome === "all" || (outcome === "matched" ? decision?.matched === true : decision?.matched === false));
  });
  $("visible-count").textContent = recordsLoaded ? `${visible.length} of ${records.length} records` : "";
  $("records-empty").hidden = visible.length > 0;
  $("records-empty").querySelector("strong").textContent = recordsLoaded ? (records.length ? "No records match these filters." : "This search returned no records.") : "No records to display yet.";
  $("records-empty").querySelector("p").textContent = recordsLoaded ? (records.length ? "Try another search term or select All records." : "An empty result is valid. Check your destination and search criteria.") : "Complete a run, or open one from your history.";
  for (const row of visible) {
    const decision = decisions.find(d => d.listing_id === row.listing_id);
    const tr = document.createElement("tr");
    for (const value of [row.listing_id, row.title, row.city, row.price, row.rating]) {
      const td = document.createElement("td"); td.textContent = value; tr.append(td);
    }
    const cell = document.createElement("td"), badge = document.createElement("span"); badge.className = "badge";
    setBadge(badge, decision ? (decision.matched ? "Matched" : "Not matched") : "Not evaluated", decision?.matched ? "success" : "neutral");
    cell.append(badge);
    if (decision && !decision.matched) { const why = document.createElement("small"); why.className = "decision-reason"; why.textContent = decision.reasons.map(r => ({price_below_minimum: "Below minimum price", price_above_maximum: "Above maximum price", rating_below_minimum: "Below minimum rating"}[r] || r.replaceAll("_", " "))).join(", "); cell.append(why); }
    tr.append(cell);
    $("records").append(tr);
  }
}
async function select(id) {
  clearTimeout(timer); selected = id; $("approved").checked = false; $("execute").disabled = true;
  currentJob = null; records = []; decisions = []; recordsLoaded = false; metrics(); $("filter").value = ""; $("decision-filter").value = "all"; table(); $("downloads").hidden = true;
  $("review").hidden = true; $("feedback").hidden = true;
  $("review-empty").hidden = true; $("job-title").textContent = "Loading job…";
  $("job-state").textContent = "Retrieving saved evidence. No work is being rerun.";
  $("execute").removeAttribute("data-plan"); $("execute").removeAttribute("data-revision");
  $("summary").textContent = "No exported records loaded for this job.";
  await poll(id);
}
async function poll(id) {
  const job = await api(`/api/jobs/${id}`); if (selected !== id) return;
  currentJob = job;
  const previousStatus = $("feedback").dataset.jobStatus;
  showFeedback(job);
  if (!$("feedback").hidden && activeView === "studio" && previousStatus !== `${id}:${job.status}`) { $("feedback").focus(); }
  $("feedback").dataset.jobStatus = `${id}:${job.status}`;
  $("create").disabled = !terminal(job.status);
  $("create").textContent = terminal(job.status) ? "Create proposal →" : "Job in progress…";
  setBadge($("job-badge"), statusLabels[job.status] || job.status, statusTone(job.status));
  $("job-title").textContent = `${job.framework === "crewai" ? "CrewAI" : "LangGraph"} · ${job.kind === "plan" ? "Search proposal" : "Workflow execution"}`;
  $("job-state").textContent = job.guidance || job.result?.guidance || "Working on the current stage…";
  metrics(job.result || {});
  $("details").textContent = JSON.stringify(job, null, 2);
  $("progress").replaceChildren();
  const trace = job.result?.trace || [];
  for (const entry of job.stages) {
    const evidence = trace.find(t => t.startsWith(entry.stage + ":"));
    const li = document.createElement("li");
    const outcome = evidence ? evidence.split(":")[1] : "started";
    li.dataset.outcome = outcome;
    const title = document.createElement("span"), state = document.createElement("span");
    title.textContent = stageLabels[entry.stage] || entry.stage; state.textContent = outcome === "ok" ? "Complete" : outcome === "started" && terminal(job.status) ? "Started · no final evidence" : outcome;
    li.append(title, state);
    $("progress").append(li);
  }
  if (terminal(job.status) && job.kind === "execute") {
    for (const stage of ["validate_plan", "extract", "save", "export", "evaluate", "publish", "receive", "verify"]) {
      if (!job.stages.some(entry => entry.stage === stage)) {
        const li = document.createElement("li"); li.textContent = `${stageLabels[stage]} · not run / skipped`;
        $("progress").append(li);
      }
    }
  }
  const result = job.result || {};
  $("review").hidden = job.status !== "awaiting_review";
  if (result.proposal) {
    $("proposal-summary").replaceChildren();
    const proposal = result.proposal;
    for (const [name, value] of Object.entries({"Original request": proposal.request || "Guided form", "Website": proposal.base_url, ...proposal.plan, "Expires": proposal.expires_at})) {
      const term = document.createElement("dt"), definition = document.createElement("dd");
      term.textContent = labels[name] || name.replaceAll("_", " ");
      definition.textContent = name === "city" && !value ? "All cities" : value === null ? "Not specified" : value === "per_night_taxes_included" ? "Per night, taxes included" : name === "Expires" ? new Date(value).toLocaleString() : String(value);
      $("proposal-summary").append(term, definition);
    }
    $("proposal").textContent = JSON.stringify(result.proposal, null, 2);
    $("execute").dataset.plan = result.proposal.plan_id;
    $("execute").dataset.revision = result.revision;
  }
  if (terminal(job.status)) {
    if (result.run_id) {
      try {
        const payload = await api(`/api/jobs/${id}/records`);
        if (selected !== id) return;
        records = payload.listings; decisions = result.evaluation?.decisions || []; recordsLoaded = true; table(); metrics(result);
        $("summary").textContent = `${records.length} records · matches: ${result.evaluation?.matched ?? "not evaluated"} · events published: ${result.delivery?.published ?? "not reported"} · receipts verified: ${result.receipts_verified ?? "not reported"}. Run: ${result.run_id}`;
        $("downloads").hidden = false;
        $("export-status").textContent = "";
      } catch (e) { $("summary").textContent = e.message; }
    }
    await loadHistory();
  } else timer = setTimeout(() => poll(id).catch(e => message(e.message)), 1000);
}
$("login-form").onsubmit = async event => {
  event.preventDefault(); message();
  try { const result = await api("/api/login", {username: $("username").value, password: $("password").value});
    $("password").value = ""; csrf = result.csrf; await workspace();
  } catch (e) { $("password").value = ""; message(e.message); }
};
$("register-form").onsubmit = async event => {
  event.preventDefault();
  try {
    await api("/api/register", {username: $("register-user").value, password: $("register-password").value});
    $("username").value = $("register-user").value;
    history.replaceState(null, "", "#login"); authPage();
    message("Account created. Sign in with your new account password.");
  } catch (e) { message(e.message); }
  finally { $("register-password").value = ""; }
};
$("key-form").onsubmit = async event => {
  event.preventDefault();
  const payload = {api_key: $("api-key").value, model: $("model-id").value,
    remember: $("remember-key").checked, authorized: $("key-authorized").checked};
  $("api-key").value = "";
  try { const result = await api("/api/model-key", payload); message(result.guidance); await workspace(); }
  catch (e) { message(e.message); }
  finally { payload.api_key = ""; $("key-authorized").checked = false; }
};
$("forget-key").onclick = async () => {
  if (!confirm("Remove your saved key from this computer and clear keys in your account sessions? Already-started work may finish.")) return;
  try { const result = await api("/api/model-key/forget", {}); await workspace(); message(result.guidance); }
  catch (e) { message(e.message); }
};
async function loadAdmin() {
  const [users, audit] = await Promise.all([api("/api/admin/users"), api("/api/admin/audit")]);
  $("admin-user").replaceChildren();
  for (const user of users) {
    const option = document.createElement("option"); option.value = user.user_id;
    option.textContent = `${user.username} — ${user.role} — ${user.enabled ? "enabled" : "disabled"}`;
    $("admin-user").append(option);
  }
  $("admin-audit").textContent = JSON.stringify(audit, null, 2);
}
$("admin-refresh").onclick = () => loadAdmin().catch(e => message(e.message));
$("admin-form").onsubmit = async event => {
  event.preventDefault();
  const target = $("admin-user").selectedOptions[0]?.textContent;
  if (!confirm(`Apply ${$("admin-action").value} to ${target}? This revokes that account's sessions.`)) { $("admin-password").value = ""; return; }
  const payload = {action: $("admin-action").value, password: $("admin-password").value};
  $("admin-password").value = "";
  try {
    const result = await api(`/api/admin/users/${$("admin-user").value}`, payload);
    $("admin-result").textContent = result.guidance; await loadAdmin();
  } catch (e) { $("admin-result").textContent = e.message; }
  finally { payload.password = ""; }
};
$("clear-key").onclick = async () => {
  try { await api("/api/model-key/clear", {}); $("api-key").value = ""; await workspace(); message("Session key cleared. Already-started work may finish."); }
  catch (e) { message(e.message); }
};
$("plan-form").onsubmit = async event => {
  event.preventDefault(); message();
  $("min-price").setCustomValidity("");
  if ($("mode").value === "structured" && $("check-out").value <= $("check-in").value) {
    $("check-out").setCustomValidity("Check-out must be later than check-in."); $("check-out").reportValidity(); return;
  }
  if ($("mode").value === "structured" && $("min-price").value &&
      Number($("min-price").value) > Number($("price").value)) {
    $("min-price").setCustomValidity("Minimum price cannot exceed maximum price.");
    $("min-price").reportValidity(); return;
  }
  $("create").disabled = true; $("create").textContent = "Creating proposal…";
  const payload = {framework: $("framework").value, mode: $("mode").value};
  if (payload.mode === "structured") Object.assign(payload, {
    city: $("all-cities").checked ? null : $("city").value, all_cities: $("all-cities").checked,
    check_in: $("check-in").value, check_out: $("check-out").value,
    min_price: $("min-price").value || null,
    max_price: $("price").value, min_rating: $("rating").value});
  else Object.assign(payload, {request: $("request").value, allow_model_api: $("consent").checked});
  try { const result = await api("/api/plans", payload); showView("studio"); await select(result.job_id); $("review-card").focus(); }
  catch (e) { message(e.message); $("create").disabled = false; $("create").textContent = "Create proposal"; } finally { $("consent").checked = false; }
};
$("execute").onclick = async () => {
  if (!$("approved").checked) return; $("execute").disabled = true; message();
  try { const result = await api(`/api/plans/${$("execute").dataset.plan}/execute`, {revision: $("execute").dataset.revision});
    await select(result.job_id);
  } catch (e) { message(e.message); $("approved").checked = false; }
};
$("approved").onchange = () => { $("execute").disabled = !$("approved").checked; };
$("all-cities").onchange = () => { $("city").disabled = $("all-cities").checked; };
$("mode").onchange = modeChanged;
$("open-connection").onclick = () => { showView("connection", true); $("api-key").focus(); };
$("example-request").onclick = () => {
  $("request").value = `Find hotels in Boston from ${futureDate(7)} to ${futureDate(9)}, priced at most USD 200 per night including taxes, with a rating of at least 4 out of 5. Search only the local demo portal.`;
  $("consent").checked = false; $("request").focus();
};
for (const id of ["check-in", "check-out"]) $(id).oninput = () => $("check-out").setCustomValidity("");
$("edit-request").onclick = () => editSearch();
$("use-form").onclick = () => editSearch(true);
$("filter").oninput = table;
$("decision-filter").onchange = table;
$("filter").maxLength = 200;
$("download-export").onclick = async () => {
  if (!selected || !recordsLoaded || connectionBlocked) return;
  const id = selected, format = $("export-format").value;
  const query = new URLSearchParams({scope: $("export-scope").value});
  if (query.get("scope") === "filtered") {
    query.set("search", $("filter").value);
    query.set("outcome", $("decision-filter").value);
  }
  $("download-export").disabled = true;
  $("export-status").textContent = "Preparing your download…";
  try {
    const response = await fetch(`/api/jobs/${id}/download/${format}?${query}`, {cache: "no-store"});
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(typeof detail.detail === "string" ? detail.detail : "Download unavailable. Please try again.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = response.headers.get("Content-Disposition")?.match(/filename="([a-zA-Z0-9.-]+)"/)?.[1] || `records.${format}`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    if (selected === id) $("export-status").textContent = "Download sent to your browser. Check its Downloads folder or save prompt.";
  } catch (error) {
    if (selected === id) $("export-status").textContent = error.message;
  } finally { $("download-export").disabled = false; }
};
$("check").onclick = () => readiness().catch(e => message(e.message));
$("refresh-history").onclick = () => loadHistory().catch(e => message(e.message));
$("logout").onclick = async () => { try { await api("/api/logout", {}); location.reload(); } catch (e) { message(e.message); } };
for (const [id, days] of [["check-in", 7], ["check-out", 9]]) {
  $(id).value = futureDate(days); $(id).min = futureDate(0);
}
modeChanged();
table();
authPage();
api("/api/session").then(async session => {
  csrf = session.csrf; instanceId = session.instance_id;
  if (session.ui_version !== UI_VERSION) { connectionWarning("Application versions differ. Refresh the application before continuing."); return; }
  if (session.authenticated) await workspace();
}).catch(e => message(e.message));
setInterval(checkConnection, 10000);
