"use strict";
let webSelected = null, webTimer = null, webProposal = null, webRevision = null;
let webCapture = null, receivingCapture = false;
let webPollEpoch = 0;
const webForm = $("web-form");
webForm.closest(".card").classList.add("custom-form-card");
$("web-status").closest(".card").classList.add("custom-review-card");
const sourceChoices = document.createElement("div");
sourceChoices.className = "source-choices";
sourceChoices.setAttribute("role", "group");
sourceChoices.setAttribute("aria-label", "Choose how to collect information");
const sourceOptions = [
  {value: "browser", number: "01", title: "Open a website", note: "Interactive pages, searches and sign-in"},
  {value: "capture", number: "02", title: "Use my browser", note: "Capture an open Chrome or Edge tab"},
  {value: "public", number: "03", title: "Read public pages", note: "Up to three HTML pages without a browser"},
  {value: "paste", number: "04", title: "Paste content", note: "Use source text you already have"},
];
for (const option of sourceOptions) {
  const button = document.createElement("button");
  button.type = "button"; button.className = "source-choice";
  button.dataset.source = option.value;
  button.setAttribute("aria-pressed", "false");
  const number = document.createElement("span"), copy = document.createElement("span");
  const title = document.createElement("strong"), note = document.createElement("small");
  number.className = "source-choice-number"; number.textContent = option.number;
  title.textContent = option.title; note.textContent = option.note;
  copy.append(title, note); button.append(number, copy);
  button.onclick = () => {
    $("web-source").value = option.value;
    $("web-source").dispatchEvent(new Event("change"));
  };
  sourceChoices.append(button);
}
const sourceSelectors = $("web-framework").closest(".form-grid");
sourceSelectors.before(sourceChoices);
const sourceGuide = document.createElement("p");
sourceGuide.className = "source-guide";
sourceChoices.after(sourceGuide);
const advanced = document.createElement("details");
advanced.className = "web-advanced"; advanced.id = "web-advanced";
const advancedSummary = document.createElement("summary");
advancedSummary.textContent = "Advanced settings: framework, limits, browser settings and rules";
const advancedBody = document.createElement("div"); advancedBody.className = "web-advanced-body";
advancedBody.append(
  sourceSelectors,
  $("web-limit").closest("label"),
  $("web-browser-options"),
  $("web-verification-options"),
  $("web-rule-field").closest("details")
);
advanced.append(advancedSummary, advancedBody);
$("web-authorized").closest("label").before(advanced);
const loginChoice = document.createElement("fieldset");
loginChoice.id = "web-login-choice";
loginChoice.className = "web-login-choice";
const loginLegend = document.createElement("legend");
loginLegend.textContent = "Website access";
const loginModeLabel = $("web-login-mode").closest("label");
loginModeLabel.firstChild.textContent = "Does this website require sign-in?";
const noLoginOption = document.createElement("option");
noLoginOption.value = "none";
noLoginOption.textContent = "No login needed";
$("web-login-mode").prepend(noLoginOption);
$("web-login-mode").querySelector('[value="manual"]').textContent = "Yes - I will manually sign in ";
$("web-login-mode").querySelector('[value="automatic"]').textContent = "Yes - Sign in automatically using credentials";
$("web-login-mode").value = "none";
const loginHelp = document.createElement("p");
loginHelp.id = "web-login-help";
loginHelp.className = "field-help";
loginChoice.append(loginLegend, loginModeLabel, loginHelp);
$("web-urls").closest("label").nextElementSibling.after(loginChoice);
loginChoice.before($("web-browser-mode-options"));
$("web-browser-options").querySelector("legend").textContent = "Advanced browser access";
$("web-browser-controls").querySelector("p.micro").textContent =
  "Finish any sign-in in the website browser, then choose how to collect the content.";
// One visible task surface instead of a long stack of setup, review and results.
const sourcePanel = webForm.closest(".card"), workPanel = $("web-status").closest(".card");
const resultsPanel = $("web-record-cards").closest(".card");
const studioLayout = sourcePanel.parentElement;
const studioTabs = document.createElement("nav"); studioTabs.className = "studio-step-tabs";
studioTabs.setAttribute("role", "tablist"); studioTabs.setAttribute("aria-label", "Website workflow");
const studioPanels = new Map([["source", sourcePanel], ["work", workPanel], ["results", resultsPanel]]);
const studioTabButtons = new Map();
let studioStep = "source";
function setStudioStep(step, moveFocus = false) {
  if (!studioPanels.has(step)) return;
  studioStep = step;
  studioLayout.hidden = step === "results";
  for (const [name, panel] of studioPanels) {
    panel.hidden = name !== step;
    const tab = studioTabButtons.get(name);
    tab.setAttribute("aria-selected", String(name === step)); tab.tabIndex = name === step ? 0 : -1;
  }
  if (moveFocus) studioTabButtons.get(step).focus({preventScroll: true});
}
for (const [name, title] of [["source", "1. Source"], ["work", "2. Workflow"], ["results", "3. Results"]]) {
  const button = document.createElement("button"), panel = studioPanels.get(name);
  button.type = "button"; button.id = "web-tab-" + name; button.textContent = title;
  button.setAttribute("role", "tab"); panel.id = "web-panel-" + name;
  button.setAttribute("aria-controls", panel.id); panel.setAttribute("role", "tabpanel");
  panel.setAttribute("aria-labelledby", button.id);
  button.onclick = () => setStudioStep(name, true);
  button.onkeydown = event => {
    const names = [...studioPanels.keys()], index = names.indexOf(name);
    const next = event.key === "ArrowRight" ? names[(index + 1) % names.length] :
      event.key === "ArrowLeft" ? names[(index + names.length - 1) % names.length] :
      event.key === "Home" ? names[0] : event.key === "End" ? names.at(-1) : null;
    if (next) { event.preventDefault(); setStudioStep(next, true); }
  };
  studioTabButtons.set(name, button); studioTabs.append(button);
}
document.querySelector('[data-page="custom"] .page-heading').after(studioTabs);
setStudioStep("source");
const customHeading = document.querySelector('[data-page="custom"] .page-heading');
customHeading.querySelector("h1").textContent = "Extract. Review. Download.";
customHeading.querySelector("p").textContent = "Choose a source and tell us what you need.";
sourcePanel.querySelector("h2").textContent = "Set up your source";
workPanel.querySelector("h2").textContent = "Workflow & review";
resultsPanel.querySelector("h2").textContent = "Your results";
$("web-urls").rows = 2; $("web-request").rows = 3;
const requestLabel = $("web-request").closest("label");
$("web-urls").closest("label").after(requestLabel);
const primaryInputs = document.createElement("div"); primaryInputs.className = "source-primary-grid";
$("web-urls").closest("label").before(primaryInputs);
primaryInputs.append($("web-urls").closest("label"), requestLabel);
// Keep required permissions visible; optional configuration is folded away.
const normalPermission = $("web-normal-confirm-label");
normalPermission.lastChild.textContent = "I allow unrestricted browser networking and will supervise this session. Third-party scripts, redirects, frames, WebSockets, popups, service workers and downloads may send data to third parties or local network services.";
advanced.before(normalPermission);
advancedBody.prepend($("web-browser-mode-options"), $("web-output-fields").closest("label"));
advancedSummary.textContent = "Settings & optional rules";
const sourceHelp = document.createElement("details"), sourceHelpTitle = document.createElement("summary");
sourceHelpTitle.textContent = "Help & capture limits"; sourceHelp.append(sourceHelpTitle);
for (const item of [...webForm.children]) {
  if (item.matches("p.field-help,p.micro") && !item.id) sourceHelp.append(item);
}
webForm.append(sourceHelp);
// Do not silently leave required fields inaccessible inside collapsed settings.
webForm.addEventListener("invalid", event => {
  setStudioStep("source");
  for (let node = event.target.parentElement; node && node !== webForm; node = node.parentElement) {
    if (node.tagName === "DETAILS") node.open = true;
  }
}, true);
const reviewDetails = document.createElement("details"), reviewDetailsTitle = document.createElement("summary");
reviewDetailsTitle.textContent = "Fields, filters & scope"; reviewDetails.append(reviewDetailsTitle);
reviewDetails.append($("web-summary"));
for (const id of ["web-fields", "web-filters"]) {
  const element = $(id); reviewDetails.append(element.previousElementSibling, element);
}
$("web-review").prepend(reviewDetails);
const reviewWarnings = document.createElement("details"), reviewWarningsTitle = document.createElement("summary");
reviewWarningsTitle.textContent = "Warnings & coverage"; reviewWarnings.append(reviewWarningsTitle);
$("web-warnings").before(reviewWarnings); reviewWarnings.append($("web-warnings"));
const previewResultsButton = document.createElement("button");
previewResultsButton.type = "button"; previewResultsButton.className = "secondary";
previewResultsButton.textContent = "Preview results"; previewResultsButton.disabled = true;
previewResultsButton.onclick = () => setStudioStep("results", true);
$("web-status").after(previewResultsButton);
function updateSourceChoice() {
  const selected = $("web-source").value;
  for (const button of sourceChoices.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.source === selected));
  }
  $("web-create").textContent = selected === "browser" ?
    "Open website and start" : "Create a preview";
  const guidance = {
    browser: "Open an interactive browser to search, sign in and collect content.",
    capture: "Send the reviewed page from Chrome or Edge using the extension.",
    public: "Read up to three public HTML pages from one website.",
    paste: "Paste authorized content and its original page address.",
  };
  sourceGuide.textContent = guidance[selected];
  if (selected === "browser") {
    sourceGuide.textContent += $("web-browser-mode").value === "normal" ?
      " Normal networking." : " Restricted networking.";
  }
  if (!webSelected) renderWorkflow();
}
const flowShell = document.createElement("section");
flowShell.className = "workflow-map card";
flowShell.setAttribute("aria-label", "Live workflow progress");
const flowHeader = document.createElement("div"); flowHeader.className = "workflow-map-header";
const flowIntro = document.createElement("div");
const flowEyebrow = document.createElement("span"); flowEyebrow.className = "eyebrow";
flowEyebrow.textContent = "LIVE WORKFLOW";
const flowTitle = document.createElement("h2"); flowTitle.textContent = "Run progress";
const flowDescription = document.createElement("p"); flowDescription.className = "muted";
flowDescription.textContent = "Select a checkpoint for details.";
flowIntro.append(flowEyebrow, flowTitle, flowDescription);
const flowBadge = document.createElement("span"); flowBadge.className = "flow-badge";
flowBadge.setAttribute("role", "status"); flowBadge.setAttribute("aria-live", "polite");
flowHeader.append(flowIntro, flowBadge);
const flowActivity = document.createElement("div"); flowActivity.className = "flow-activity";
const flowSpinner = document.createElement("span"); flowSpinner.className = "flow-spinner";
flowSpinner.setAttribute("aria-hidden", "true");
const flowActivityText = document.createElement("span");
flowActivityText.setAttribute("role", "status"); flowActivityText.setAttribute("aria-live", "polite");
flowActivity.append(flowSpinner, flowActivityText);
function setFlowActivity(running, message) {
  flowShell.dataset.running = String(running);
  flowSteps.setAttribute("aria-busy", String(running));
  flowSpinner.hidden = !running;
  setRingMotion(flowSpinner, running);
  if (!running) for (const node of flowNodes.values()) {
    node.details.dataset.running = "false"; setRingMotion(node.ring, false);
  }
  stableText(flowActivityText, message);
}
const flowMeterLabel = document.createElement("p"); flowMeterLabel.className = "flow-meter-label";
const flowMeter = document.createElement("progress");
flowMeter.max = 7; flowMeter.value = 0;
flowMeter.setAttribute("aria-label", "Completed workflow checkpoints");
const flowSteps = document.createElement("ol"); flowSteps.className = "flow-steps";
flowShell.append(flowHeader, flowActivity, flowMeterLabel, flowMeter, flowSteps);
document.querySelector('[data-page="custom"] .layout').before(flowShell);
const stageLog = document.createElement("details"); stageLog.className = "flow-stage-log";
const stageLogSummary = document.createElement("summary");
stageLogSummary.textContent = "Detailed stage log";
stageLog.append(stageLogSummary, $("web-progress"));
flowShell.after(stageLog);
const flowDefinitions = [
  {id: "setup", title: "Set up source", description: "Choose a source and describe the information you need."},
  {id: "browse", title: "Explore website", description: "Open the website and review any search or link actions."},
  {id: "capture", title: "Capture content", description: "Collect the approved page content and record what was available."},
  {id: "interpret", title: "Interpret request", description: "Extract candidate records and apply source-evidence checks."},
  {id: "review", title: "Review results", description: "Check fields, filters, quotes and any partial coverage."},
  {id: "save", title: "Save results", description: "Save the approved snapshot and make downloads available."},
  {id: "event", title: "Publish event", description: "Optional summary event, only after approval and matching rules."},
];
const flowNodes = new Map();
for (const [index, item] of flowDefinitions.entries()) {
  const row = document.createElement("li"), details = document.createElement("details");
  const summary = document.createElement("summary"), number = document.createElement("span");
  const copy = document.createElement("span"), title = document.createElement("strong");
  const badge = document.createElement("span"), body = document.createElement("p");
  const ring = document.createElement("span"), glyph = document.createElement("span");
  ring.className = "flow-step-ring"; ring.setAttribute("aria-hidden", "true");
  details.dataset.stage = item.id;
  number.className = "flow-step-number"; glyph.textContent = String(index + 1);
  number.append(ring, glyph);
  copy.className = "flow-step-copy"; title.textContent = item.title;
  badge.className = "flow-step-state";
  copy.append(title, badge); summary.append(number, copy);
  body.className = "flow-step-evidence";
  details.append(summary, body); row.append(details); flowSteps.append(row);
  flowNodes.set(item.id, {details, badge, body, number: glyph, ring});
}
function renderWorkflow(job = null, browser = null) {
  const result = job?.result || {};
  const proposal = result.proposal || {};
  const execution = job?.kind === "custom-execute";
  const started = new Set((job?.stages || []).map(item => item.stage));
  const trace = new Map((result.trace || []).map(item => {
    const position = item.indexOf(":");
    return [item.slice(0, position), item.slice(position + 1)];
  }));
  const captured = result.captured_pages || proposal.captured_pages || [];
  const browserSource = proposal.source ? proposal.source === "browser" :
    (browser?.state && browser.state !== "closed") || $("web-source").value === "browser";
  const hasExtraction = started.has("extract_content") || trace.has("extract_content");
  const hasReview = started.has("review_content") || trace.has("review_content");
  const inspectFailed = trace.get("inspect_website") === "failed";
  const noMatches = result.review_outcome === "no_matches";
  const attention = !noMatches && ["needs_input", "unsupported", "failed", "interrupted"].includes(job?.status);
  const publishFailed = trace.get("publish") === "failed" || result.failed_stage === "publish";
  const publishFinished = trace.get("publish") === "ok";
  const delivery = result.delivery || {};
  // A successful optional stage can deliberately send nothing. Do not leave it
  // pending, or claim an acknowledgement merely because delivery was enabled.
  const eventState = !execution ? "pending" : publishFailed ? "attention" :
    publishFinished ? delivery.published > 0 ? "done" :
      delivery.enabled === false || delivery.enabled === true && delivery.published === 0 ?
      "skipped" : "attention" :
    started.has("publish") && job.status === "running" ? "active" : "pending";
  const eventLabel = eventState === "skipped" ? delivery.enabled === false ?
    "Skipped — disabled" : "Skipped — no matches" : eventState === "done" ? "Published" :
    eventState === "pending" ? proposal.publish_event === false ? "Optional — disabled" :
    proposal.publish_event === true ? "Pending approval & save" : "Pending (optional)" : null;
  const states = {
    setup: job ? "done" : "idle",
    browse: !job ? "pending" : inspectFailed && browserSource ? "attention" :
      execution || hasExtraction ? "done" :
      browserSource ? "active" : "skipped",
    capture: execution || hasExtraction ? "done" : inspectFailed ?
      browserSource ? "pending" : "attention" :
      started.has("inspect_website") ? "active" : "pending",
    interpret: execution || hasReview ? "done" : trace.get("extract_content") === "failed" ?
      "attention" : hasExtraction ? "active" : "pending",
    review: execution || noMatches ? "done" : job?.status === "awaiting_review" ? "review" :
      hasReview && attention ? "attention" : hasReview ? "active" : "pending",
    save: execution ? result.run_id ? "done" : trace.get("save") === "failed" ?
      "attention" : started.has("save") ? "active" : "pending" : "pending",
    event: eventState,
  };
  if (attention && !Object.values(states).includes("attention")) {
    const current = execution ? "save" : hasReview ? "review" : hasExtraction ? "interpret" : "capture";
    states[current] = "attention";
  }
  const activity = workflowActivity(job, browser, browserSource ? "browser" : proposal.source || $("web-source").value);
  // Only the step actually processing gets a running ring. Website exploration
  // and capture are not simultaneous merely because inspect_website has started.
  for (const id of Object.keys(states)) {
    if (states[id] === "active" && job && id !== activity.stage) states[id] = "pending";
  }
  if (job && !terminal(job.status) && activity.stage) {
    states[activity.stage] = activity.waiting ? "waiting" : "active";
    if (activity.stage === "capture" && browserSource) states.browse = "done";
  }
  const evidence = {
    setup: job ? `Source accepted. ${proposal.source || $("web-source").value} method selected.` :
      "No run started yet. Choose a source and describe your request.",
    browse: execution ? "Source inspection happened in the approved proposal. Open that job in history for its evidence." :
      browser?.guidance || (browserSource ?
      "Review the website before collecting data. Search and link actions require your approval." :
      "This source does not need the built-in website browser."),
    capture: execution ? "Previously captured content was reviewed before this save operation." :
      captured.length ? `${captured.length} page(s) captured; ` +
      `${captured.reduce((sum, page) => sum + (page.paragraph_blocks || 0), 0)} paragraph blocks. ` +
      `${captured.filter(page => page.truncated).length} page(s) were truncated.` :
      hasExtraction ? "The source was inspected. Open Captured pages below for coverage." :
      "Waiting for content. No page has been approved for extraction yet.",
    interpret: execution ? "The earlier proposal interpreted the captured content; open it in history for model evidence." :
      (result.model || proposal.model) ?
      `Model response received from ${(result.model || proposal.model).provider || "configured provider"}. ` +
      `Review extracted values against the source; a model response is not proof of accuracy.` :
      "No model interpretation is available yet.",
    review: execution ? "A reviewed proposal was approved before this save operation." :
      proposal.plan_id ? `${proposal.records?.length || 0} records to review; ` +
      `${proposal.rejected_records?.length || 0} rejected; ` +
      `${proposal.field_issues?.length || 0} with cleared optional fields. ` +
      "Nothing is saved until you approve." : result.guidance ||
      "A source-backed preview and any issues will appear here.",
    save: result.run_id ? `Saved run ${result.run_id}. ` +
      `${result.record_count ?? 0} records; downloads are available below.` :
      "Not saved. Review and approve the preview before exporting.",
    event: publishFailed ?
      "Records were saved, but event delivery is unconfirmed. Check the saved event and broker before retrying." :
      eventState === "done" ? `${delivery.published} summary event(s) acknowledged by the broker. This is not a consumer receipt.` :
      publishFinished && delivery.enabled === false ?
      "Finished without sending an event: publishing was disabled in the approved proposal. Enable event delivery in Advanced settings before creating a new preview." :
      publishFinished && eventState === "skipped" ?
      "Finished without sending an event: no saved records qualified for the configured rules." :
      publishFinished ? "Publishing finished, but acknowledgement evidence is missing. Review Technical evidence before retrying." :
      proposal.publish_event === true ? "Event delivery is requested. It runs only after you approve and save the preview, and only if records qualify." :
      "Optional. Enable summary event delivery in Advanced settings before creating the preview.",
  };
  const diagnostics = browser || result.browser_diagnostics || proposal.browser_diagnostics;
  if (diagnostics?.browser_mode) {
    evidence.browse += ` Browser networking: ${diagnostics.browser_mode}; engine: ${diagnostics.browser_channel || "chromium"}.`;
  }
  if (diagnostics?.page_health) {
    const health = diagnostics.page_health;
    evidence.browse += ` Page: HTTP ${health.main_status ?? "unknown"}, ` +
      `${health.visible_text_chars ?? 0} visible text characters.`;
  }
  const blockedRenderOrigins = (diagnostics?.blocked_resources || []).filter(item =>
    ["script", "stylesheet", "font"].includes(item.type));
  if (blockedRenderOrigins.length) {
    evidence.browse += ` ${blockedRenderOrigins.length} script/style/font origin(s) were blocked. ` +
      (browser ? "Open page loading diagnostics before trusting the capture." :
        "Open Technical evidence below before trusting the capture.");
  }
  if (trace.get("inspect_website") === "failed" || trace.get("review_content") === "needs_input") {
    evidence[trace.get("inspect_website") === "failed" ? "capture" : "review"] =
      result.guidance || "This stage needs attention. Check the message below.";
  }
  if (execution && states.save === "attention" && !result.run_id) {
    evidence.save = result.guidance || "Approval or saving failed. No new download is available.";
  }
  const stateNames = {idle: "Idle", pending: "Pending", active: "Running", done: "Done", waiting: "Waiting for you",
    review: "Your review", attention: "Needs attention", skipped: "Not needed"};
  for (const item of flowDefinitions) {
    const node = flowNodes.get(item.id);
    node.details.dataset.state = states[item.id];
    node.details.dataset.running = String(activity.running && item.id === activity.stage);
    setRingMotion(node.ring, activity.running && item.id === activity.stage);
    stableText(node.badge, item.id === "event" && states.event === eventState && eventLabel ?
      eventLabel : stateNames[states[item.id]]);
    stableText(node.number, states[item.id] === "done" ? "✓" : states[item.id] === "attention" ? "!" :
      states[item.id] === "waiting" || states[item.id] === "review" ? "Ⅱ" : String(flowDefinitions.indexOf(item) + 1));
    const brief = item.id === activity.stage && (activity.running || activity.waiting) ? activity.message :
      states[item.id] === "pending" && item.id !== "event" ? item.description : evidence[item.id];
    stableText(node.body, brief.length > 230 ? brief.slice(0, 227) + "… See the message and source details below." : brief);
  }
  const count = Object.values(states).filter(state => ["done", "skipped"].includes(state)).length;
  flowMeter.value = count;
  stableText(flowMeterLabel, `${count} of ${flowDefinitions.length} checkpoints completed or not needed`);
  flowBadge.dataset.tone = noMatches ? "review" : attention ? "attention" : job?.status === "completed" ?
    "done" : job?.status === "awaiting_review" ? "review" : job ? "active" : "idle";
  stableText(flowBadge, noMatches ? "No matches in captured content" : attention ? "Needs attention" : job?.status === "completed" ?
    "Saved" : job?.status === "awaiting_review" ? "Ready for review" : browser?.state === "waiting" ?
    "Browser ready" : job ? "Working" : "Ready to begin");
  setFlowActivity(activity.running, activity.message);
  if (activity.waiting) stableText(flowBadge, "Waiting for you");
}
renderWorkflow();
const capturePanel = document.createElement("details");
capturePanel.id = "web-captured-pages"; capturePanel.hidden = true;
stageLog.after(capturePanel);
function showCapturedPages(pages) {
  updateRegion(capturePanel, pages || [], () => {
  capturePanel.replaceChildren(); capturePanel.hidden = !pages?.length;
  if (!pages?.length) return;
  const heading = document.createElement("summary");
  heading.textContent = `Collected pages and coverage (${pages.length} page${pages.length === 1 ? "" : "s"})`;
  const list = document.createElement("ul");
  for (const page of pages) {
    const item = document.createElement("li");
    item.textContent = `${page.source_kind === "index" ? "Starting page: " : page.source_kind === "detail" ? "Detail page: " : ""}${page.source_url} — ${page.visible_text_chars} text characters, ` +
      `${page.paragraph_blocks} paragraph blocks${page.truncated ? "; capture truncated" : ""}`;
    if (page.headline_blocks !== undefined) {
      item.textContent += `; ${page.headline_blocks} main headline marker(s), ${page.body_paragraph_blocks} body paragraph(s)`;
    }
    if (page.coverage) {
      const c = page.coverage;
      const details = document.createElement("p"); details.className = "micro";
      details.textContent = `Loaded-page coverage: ${c.captured_text_chars} captured text characters; ` +
        `${c.omitted_text_chars} omitted by collection limits; ${c.unique_links_detected} eligible links ` +
        `(${c.links_returned} in the discovery window); ${c.record_groups} record groups. ` +
        (c.preparation === "bounded_browser" ? `${c.scroll_steps} loading scroll(s); ` +
          `content ${c.content_settled ? "settled during sampling" : "not confirmed settled"}; ` : "Manual snapshot; readiness not sampled. ") +
        `page end ${c.at_page_end ? "observed" : "not observed"}. ` +
        `${c.frames_excluded} iframe(s) excluded from text capture. ` +
        (c.limit_reasons.length ? `Limits: ${c.limit_reasons.join(", ")}. ` : "") +
        "This is not full-site coverage.";
      item.append(details);
    }
    list.append(item);
  }
  capturePanel.append(heading, list);
  });
}
const enrichmentPanel = document.createElement("details");
enrichmentPanel.className = "source-details";
enrichmentPanel.hidden = true; capturePanel.after(enrichmentPanel);
function showEnrichment(report) {
  updateRegion(enrichmentPanel, report || null, () => {
  enrichmentPanel.replaceChildren(); enrichmentPanel.hidden = !report?.index_retained;
  if (!report?.index_retained) return;
  const heading = document.createElement("summary"), summary = document.createElement("p");
  heading.textContent = "Starting page & linked-page coverage";
  summary.textContent = `Starting page retained. ${report.approved || 0} approved link(s); ` +
    `${report.captured || 0} captured; ${report.failed || 0} failed.`;
  if (report.verified_index_records !== undefined) {
    summary.textContent += ` ${report.verified_index_records} verified starting-page records; ` +
      `${report.enriched_records} enriched; ${report.index_only_records} without matched details; ` +
      `${report.detail_only_records} separate detail records; ${report.conflicting_records} with conflicts. ` +
      `${report.excluded_after_enrichment || 0} excluded by user filters after reconciliation.`;
  }
  const list = document.createElement("ul");
  const labels = {pending: "Waiting", opening: "Opening", captured: "Captured", failed: "Failed",
    enriched: "Verified counterpart joined", conflict: "Conflicting source values — review",
    not_opened: "Not opened", not_extracted: "No matched detail record", detail_only: "Separate detail record",
    no_verified_record: "No verified record", validation_failed: "Captured, but source validation failed",
    ambiguous_index_match: "Ambiguous starting-page match"};
  for (const item of report.links || []) {
    const li = document.createElement("li");
    li.textContent = `${item.title || item.url}: ${labels[item.status] || item.status}` +
      `${item.record_status ? "; " + (labels[item.record_status] || item.record_status) : ""}` +
      `${item.reason ? ". " + item.reason : ""} — ${item.url}`;
    if (item.validation_issues?.length) {
      const issues = document.createElement("ul");
      for (const issue of item.validation_issues) {
        const line = document.createElement("li");
        line.textContent = `${issue.field}: ${issue.reason.replaceAll("_", " ")}`;
        issues.append(line);
      }
      li.append(issues);
    }
    list.append(li);
  }
  const note = document.createElement("p"); note.className = "micro";
  note.textContent = "Only approved links were opened. Unopened pages and omitted model records are not complete results. Conflicts retain source values for your review; no replacement values were invented.";
  enrichmentPanel.append(heading, summary, list, note);
  });
}
const navPanel = document.createElement("section"), navTitle = document.createElement("h4");
const agentPanel = document.createElement("section"); agentPanel.className = "journey-action";
const agentTitle = document.createElement("h4"); agentTitle.textContent = "Let the browser agent do the task";
const agentHelp = document.createElement("p"); agentHelp.className = "micro";
agentHelp.textContent = "LangGraph agent: interprets your request, observes the live page, takes one action and checks what changed. It can search, adjust fields and collect relevant same-site pages. Navigation uses a smaller, task-focused view; extraction captures the full source separately. MFA stays with you.";
const agentConsent = document.createElement("label"); agentConsent.className = "inline consent";
const agentCheckbox = document.createElement("input"); agentCheckbox.type = "checkbox";
agentConsent.append(agentCheckbox, document.createTextNode("I authorize autonomous information-retrieval actions and up to 30 paid model decisions (5 active minutes), followed by paid extraction of up to 6 captured pages. No reservation/payment. I will review results before saving."));
const agentVisualConsent = document.createElement("label"); agentVisualConsent.className = "check-row";
const agentVisualCheckbox = document.createElement("input"); agentVisualCheckbox.type = "checkbox";
agentVisualCheckbox.id = "web-agent-visual";
agentVisualConsent.append(agentVisualCheckbox, document.createTextNode("Also allow viewport screenshots when the agent needs layout help during this start/resume (extra image-token cost). Images are not sent on every step. Screenshots may include page/account information; known credential fields are masked. Images stay out of saved history and exports."));
const agentButtons = document.createElement("div"); agentButtons.className = "button-group";
const agentStart = document.createElement("button"); agentStart.type = "button";
agentStart.id = "web-agent-start"; agentStart.textContent = "Run browser agent · paid API";
const agentResume = document.createElement("button"); agentResume.type = "button";
agentResume.id = "web-agent-resume"; agentResume.textContent = "Resume agent · paid API";
const agentCollect = document.createElement("button"); agentCollect.type = "button";
agentCollect.id = "web-agent-collect"; agentCollect.textContent = "Extract retained captures · paid API";
const agentManual = document.createElement("button"); agentManual.type = "button";
agentManual.id = "web-agent-manual"; agentManual.className = "secondary";
agentManual.textContent = "Continue manually";
const agentStatus = document.createElement("p"); agentStatus.setAttribute("role", "status");
const agentDetails = document.createElement("details"), agentSummary = document.createElement("summary");
agentSummary.textContent = "Browser-agent action evidence";
const agentLog = document.createElement("ol"); agentDetails.append(agentSummary, agentLog);
const agentChecklist = document.createElement("details"), agentChecklistTitle = document.createElement("summary");
const agentChecklistFields = document.createElement("ul"), agentChecklistNote = document.createElement("p");
agentChecklistNote.className = "micro";
agentChecklist.append(agentChecklistTitle, agentChecklistFields, agentChecklistNote);
agentButtons.append(agentStart, agentResume, agentCollect, agentManual);
agentPanel.append(agentTitle, agentHelp, agentConsent, agentVisualConsent, agentButtons, agentStatus, agentChecklist, agentDetails);
let latestAgentBrowser = {};
function agentApprovalState() {
  const browser = latestAgentBrowser, report = browser.agent_report;
  agentStart.hidden = !!report;
  agentResume.hidden = !report || !!report.task_checklist?.request_error ||
    !["agent_paused", "waiting"].includes(browser.state);
  agentCollect.hidden = browser.state !== "agent_paused" || !report?.captured_pages?.length;
  agentManual.hidden = browser.state !== "agent_paused";
  const available = ["waiting", "agent_paused"].includes(browser.state);
  agentStart.disabled = agentResume.disabled = agentCollect.disabled =
    !agentCheckbox.checked || !available || $("web-framework").value !== "langgraph";
  agentManual.disabled = browser.state !== "agent_paused";
  agentCheckbox.disabled = !available;
  agentVisualCheckbox.disabled = !available;
}
agentCheckbox.onchange = agentApprovalState;
navPanel.id = "web-nav-panel"; navTitle.textContent = "Search this website";
const navHelp = document.createElement("p"); navHelp.className = "micro";
navHelp.textContent = "One paid call proposes up to five actions. Open a search form or calendar, choose a suggestion, then request another reviewed step when new controls appear. Entered values are checked; a successful click alone does not prove your filters were applied.";
const navActions = document.createElement("div"); navActions.className = "button-group";
const navPlanButton = document.createElement("button"); navPlanButton.id = "web-plan-navigation";
navPlanButton.type = "button"; navPlanButton.textContent = "Suggest search actions · paid API";
const navApprove = document.createElement("button"); navApprove.id = "web-approve-navigation";
navApprove.type = "button"; navApprove.textContent = "Run these search actions"; navApprove.hidden = true;
const navDismiss = document.createElement("button"); navDismiss.id = "web-dismiss-navigation";
navDismiss.type = "button"; navDismiss.className = "secondary";
navDismiss.textContent = "Dismiss search plan"; navDismiss.hidden = true;
const navSteps = document.createElement("ol"); navSteps.id = "web-navigation-steps";
const navCoverage = document.createElement("p"); navCoverage.id = "web-navigation-coverage";
navCoverage.setAttribute("role", "status");
navActions.append(navPlanButton, navApprove, navDismiss);
navPanel.append(navTitle, navHelp, navCoverage, navActions, navSteps);
const hotelPanel = document.createElement("section"), hotelTitle = document.createElement("h4");
let hotelReviewedRevision = null;
hotelTitle.textContent = "Complete hotel search";
const hotelHelp = document.createElement("p"); hotelHelp.className = "micro";
hotelHelp.textContent = "Review destination, full dates, adults and rooms once. The browser then prepares the standard form, verifies each value and submits Search. No reservation/payment and no extra model-planning calls. Unsupported or ambiguous controls stop for your attention.";
const hotelPrepare = document.createElement("button"); hotelPrepare.type = "button";
hotelPrepare.id = "web-hotel-plan"; hotelPrepare.textContent = "Prepare complete hotel search · no API call";
const hotelRun = document.createElement("button"); hotelRun.type = "button";
hotelRun.id = "web-hotel-approve"; hotelRun.textContent = "Approve & run search only";
const hotelExtract = document.createElement("button"); hotelExtract.type = "button";
hotelExtract.id = "web-hotel-extract"; hotelExtract.textContent = "Approve, search & extract · paid API";
const hotelDismiss = document.createElement("button"); hotelDismiss.type = "button";
hotelDismiss.id = "web-hotel-dismiss"; hotelDismiss.className = "secondary";
hotelDismiss.textContent = "Dismiss hotel search";
const hotelReview = document.createElement("section"), hotelTargets = document.createElement("ul");
const hotelConsent = document.createElement("label"), hotelCheckbox = document.createElement("input");
hotelCheckbox.type = "checkbox"; hotelConsent.className = "inline consent";
hotelConsent.append(hotelCheckbox, document.createTextNode("I reviewed these targets and authorize the bounded calendar/occupancy actions and one Search submission. Extraction happens only if I choose the paid option."));
const hotelActions = document.createElement("div"); hotelActions.className = "button-group";
hotelActions.append(hotelRun, hotelExtract, hotelDismiss);
hotelReview.append(hotelTargets, hotelConsent, hotelActions);
hotelPanel.append(hotelTitle, hotelHelp, hotelPrepare, hotelReview);
function hotelApprovalState() {
  hotelRun.disabled = hotelExtract.disabled = !hotelCheckbox.checked || hotelReview.hidden;
}
hotelCheckbox.onchange = hotelApprovalState;
const navigationEvidence = document.createElement("section");
navigationEvidence.className = "notice"; navigationEvidence.hidden = true;
navigationEvidence.setAttribute("aria-live", "polite");
// Actionable guidance belongs in Workflow, not in the collapsed technical log
// or browser controls (which are hidden when a session ends).
$("web-browser-controls").before(navigationEvidence);
function showNavigationEvidence(diagnostics) {
  updateRegion(navigationEvidence, [diagnostics?.navigation_result || null, diagnostics?.navigation_history || []], () => {
  navigationEvidence.replaceChildren();
  const result = diagnostics?.navigation_result;
  navigationEvidence.hidden = !result;
  if (!result) return;
  const title = document.createElement("h4"), status = document.createElement("p");
  title.textContent = "Search action evidence";
  const labels = {partial_form: "Form step completed; continue with a new plan",
    search_submitted: "Search submitted; inspect the results", search_completed: "Hotel search completed; listing elements appeared",
    running: "Complete hotel search is running", needs_review: "Action needs attention"};
  status.textContent = `${labels[result.status] || result.status}. ` +
    `${diagnostics.navigation_history?.length || 1} reviewed step(s) recorded. ` +
    "Form read-back is not proof of matching result records.";
  const list = document.createElement("ul");
  for (const action of result.actions || []) {
    const li = document.createElement("li");
    li.textContent = `${action.control}: ${action.action.replaceAll("_", " ")} — ` +
      `${action.status.replaceAll("_", " ")}` +
      (action.expected !== undefined ? `; requested “${action.expected}”, observed “${action.observed || "blank"}”` : "");
    list.append(li);
  }
  for (const check of result.requirements || []) {
    const li = document.createElement("li");
    li.textContent = `${check.field.replaceAll("_", " ")}: ${check.value} — ` +
      check.status.replaceAll("_", " "); list.append(li);
  }
  navigationEvidence.append(title, status, list);
  if (result.pending_fields?.length) {
    const pending = document.createElement("p");
    pending.textContent = "Still needed before search: " + result.pending_fields.map(field => field.replaceAll("_", " ")).join(", ") + ".";
    navigationEvidence.append(pending);
  }
  const next = document.createElement("p"); next.className = "micro";
  next.textContent = result.submitted ?
    "Review the rendered results, then capture. Only source-supported fields can be filtered during extraction." :
    "Inspect the newly opened controls, then use Suggest search actions again. Each new plan is separately reviewed and paid.";
  if (result.missing_fields?.length) next.textContent =
    "Missing from the request: " + result.missing_fields.map(field => field.replaceAll("_", " ")).join(", ") +
    ". Add the missing values to your request, cancel this browser and start a new session. This session keeps its original request. Unconfirmed website fields alone do not require a new session.";
  else if (result.pending_fields?.length) next.textContent =
    "Your request values are available; the website form is not complete. Inspect the visible suggestions or calendar and use Suggest search actions again in this same session. Review each next step before running it.";
  if (result.workflow === "complete_hotel_search") next.textContent =
    result.status === "running" ? `Running ${result.stage || "hotel search"}. No additional planning API calls. Use Cancel & close browser to stop.` :
    result.status === "needs_review" ? result.guidance || "Hotel search stopped. Inspect the browser before a fresh review; no automatic retry." :
    "Listing elements appeared after Search. Review actual dates, occupancy, prices and units. This does not prove every result matches; extraction applies source-verifiable filters.";
  if (result.available_controls?.length) next.textContent += " Visible controls now: " +
    result.available_controls.map(control => control.label || control.kind).join(", ") + ".";
  navigationEvidence.append(next);
  if (result.destination_diagnostics) {
    const detection = result.destination_diagnostics;
    const details = document.createElement("details"), summary = document.createElement("summary");
    summary.textContent = "Destination field detection";
    const counts = document.createElement("p");
    counts.textContent = `${detection.matching_fields || 0} matching destination field(s); ` +
      `${detection.structured_matching_fields || 0} in hotel forms; ${detection.visible_text_fields || 0} visible text input(s). ` +
      "This shows field metadata, not entered values or credentials.";
    const fields = document.createElement("ul");
    for (const field of detection.candidates || []) {
      const li = document.createElement("li");
      li.textContent = `${field.label || "Unlabelled field"}${field.name ? " [" + field.name + "]" : ""}: ` +
        `${field.reason.replaceAll("_", " ")}; ${field.structured ? "hotel form context" : "no hotel form context"}`;
      fields.append(li);
    }
    details.append(summary, counts, fields); navigationEvidence.append(details);
  }
  if (result.destination_suggestions) {
    const matching = result.destination_suggestions;
    const details = document.createElement("details"), summary = document.createElement("summary");
    summary.textContent = "Destination suggestion matching";
    const description = document.createElement("p");
    description.textContent = `Requested: ${matching.requested}. ${matching.visible_count} visible suggestion(s), ` +
      `${matching.matching_count} name match(es), ${matching.preferred_count} preferred candidate(s). ` +
      `${matching.reason.replaceAll("_", " ")}. ` +
      (matching.selected ? `Selected: ${matching.selected.primary} (${matching.selected.kind}).` :
        "Destination selection was not confirmed. Entered text alone does not confirm the location.");
    const candidates = document.createElement("ul");
    for (const row of matching.candidates || []) {
      const li = document.createElement("li");
      li.textContent = `${row.primary || "Unnamed suggestion"} (${row.kind || "unknown"}) — ` +
        `${row.matched ? "name matched" : "name did not match"}. ${row.text || ""}`;
      candidates.append(li);
    }
    details.append(summary, description, candidates); navigationEvidence.append(details);
  }
  const earlier = (diagnostics.navigation_history || []).slice(0, -1);
  if (earlier.length) {
    const details = document.createElement("details"), summary = document.createElement("summary");
    summary.textContent = "Earlier reviewed steps";
    const history = document.createElement("ol");
    for (const item of earlier) {
      const li = document.createElement("li");
      li.textContent = `${item.status.replaceAll("_", " ")}: ` +
        ((item.actions || []).map(action => `${action.control} — ${action.status.replaceAll("_", " ")}`).join("; ") ||
          item.guidance || "No form action completed");
      history.append(li);
    }
    details.append(summary, history); navigationEvidence.append(details);
  }
  });
}
const linkPanel = document.createElement("section"), linkTitle = document.createElement("h4");
linkPanel.id = "web-link-panel"; linkTitle.textContent = "Explore linked pages";
const linkHelp = document.createElement("p"); linkHelp.className = "micro";
linkHelp.textContent = "Review up to five links before opening them. Detail pages add context and may increase API usage.";
const linkGuidance = document.createElement("p"); linkGuidance.className = "micro";
linkGuidance.setAttribute("role", "status");
const linkActions = document.createElement("div"); linkActions.className = "button-group";
const linkDiscover = document.createElement("button"); linkDiscover.type = "button";
linkDiscover.id = "web-discover-links"; linkDiscover.textContent = "Find relevant links (paid API)";
const linkApprove = document.createElement("button"); linkApprove.type = "button";
linkApprove.id = "web-approve-links"; linkApprove.textContent = "Keep starting page & enrich selected links";
linkApprove.hidden = true;
const linkDismiss = document.createElement("button"); linkDismiss.type = "button";
linkDismiss.id = "web-dismiss-links"; linkDismiss.className = "secondary";
linkDismiss.textContent = "Dismiss link proposal"; linkDismiss.hidden = true;
const linkList = document.createElement("div"); linkList.id = "web-link-list";
linkActions.append(linkDiscover, linkApprove, linkDismiss);
linkPanel.append(linkTitle, linkHelp, linkGuidance, linkActions, linkList);
let lastLinkSignature = "";
let lastResourceSignature = "";
const healthPanel = document.createElement("section"), healthTitle = document.createElement("h4");
healthTitle.textContent = "Page loading status";
const healthStatus = document.createElement("p"); healthStatus.id = "web-page-health";
healthStatus.setAttribute("role", "status");
healthPanel.append(healthTitle, healthStatus);
const healthDisclosure = document.createElement("details"); healthDisclosure.className = "source-details";
const healthSummary = document.createElement("summary"); healthSummary.textContent = "Page loading and sign-in details";
healthDisclosure.append(healthSummary, healthPanel);
const resourcePanel = document.createElement("section"), resourceTitle = document.createElement("h4");
resourcePanel.id = "web-resource-panel"; resourceTitle.textContent = "Page loading diagnostics";
const resourceHelp = document.createElement("p"); resourceHelp.className = "micro";
resourceHelp.textContent = "Blocked domains may prevent rendering. Review ownership and trust before selecting any. Adding one applies only to the next session, never bypasses a site's access decision.";
const resourceList = document.createElement("div"); resourceList.id = "web-resource-list";
const resourceAdd = document.createElement("button"); resourceAdd.type = "button";
resourceAdd.id = "web-add-resources"; resourceAdd.className = "secondary";
resourceAdd.textContent = "Add selected resource origins for next session";
const resourceStatus = document.createElement("p"); resourceStatus.id = "web-resource-status";
resourceStatus.setAttribute("role", "status");
resourcePanel.append(resourceTitle, resourceHelp, resourceList, resourceAdd, resourceStatus);
const browserActions = $("web-capture").parentElement;
const pageOnlyTitle = document.createElement("h4");
pageOnlyTitle.textContent = "Or use just this page";
const pageOnlyHelp = document.createElement("p"); pageOnlyHelp.className = "micro";
pageOnlyHelp.textContent = "Capture the content visible at this URL. Linked detail pages will not be opened.";
$("web-capture").textContent = "Extract current page only (paid API)";
browserActions.before($("web-resume-login"), agentPanel, healthDisclosure, hotelPanel, navPanel, linkPanel,
  pageOnlyTitle, pageOnlyHelp);
const resourceDisclosure = document.createElement("details");
resourceDisclosure.className = "web-resource-disclosure";
const resourceSummary = document.createElement("summary");
resourceSummary.textContent = "Advanced: page loading and blocked resources";
resourceDisclosure.append(resourceSummary, resourcePanel);
browserActions.after(resourceDisclosure);
navPanel.classList.add("journey-action"); linkPanel.classList.add("journey-action");
hotelPanel.classList.add("journey-action");
function renderBrowserOptions(browser) {
  const authenticationPending = ["authentication_pending", "checking_authentication"].includes(browser.state);
  $("web-resume-login").hidden = !authenticationPending;
  $("web-resume-login").disabled = browser.state !== "authentication_pending";
  navPanel.hidden = linkPanel.hidden = pageOnlyTitle.hidden = pageOnlyHelp.hidden = authenticationPending;
  latestAgentBrowser = browser;
  agentPanel.hidden = authenticationPending || $("web-framework").value !== "langgraph";
  agentApprovalState();
  const agentReport = browser.agent_report;
  const agentMessage = agentReport ?
    `${agentReport.status.replaceAll("_", " ")} · ${agentReport.calls}/${agentReport.max_calls} model calls attempted · ${agentReport.captured_pages.length} retained page(s). ${agentReport.guidance}` :
    "Ready when you authorize it. Your original task remains unchanged throughout this session.";
  const lastDecision = agentReport?.decision_diagnostics?.at(-1);
  const decisionMessage = lastDecision ?
    ` Decision ${lastDecision.call}: ${lastDecision.error_code || lastDecision.response_status || "no completed response"}; ` +
    `timeout ${lastDecision.timeout_seconds ?? "unknown"}s; output budget ${lastDecision.max_output_tokens ?? "unknown"} tokens` +
    (lastDecision.usage?.output_tokens != null ? `; output used ${lastDecision.usage.output_tokens}` : "") +
    (lastDecision.http_status ? `; HTTP ${lastDecision.http_status}` : "") + "." : "";
  const validationMessage = lastDecision?.validation_issues?.length ?
    " Validation: " + lastDecision.validation_issues.map(issue =>
      `${issue.field} (${issue.code})`).join("; ") + "." : "";
  const messageStructure = lastDecision?.error_code && lastDecision.message_count != null ?
    ` Response messages: ${lastDecision.message_count}; commentary: ${lastDecision.commentary_count || 0}; ` +
    `decision phase: ${lastDecision.decision_phase || "unspecified"}.` : "";
  const selectionMessage = lastDecision?.decision_valid && lastDecision.validated_decision_count != null ?
    ` Selected ${lastDecision.unique_decision_count} unique decision; ` +
    `${lastDecision.ignored_text_messages || 0} non-decision message(s) ignored; ` +
    `${lastDecision.duplicate_decisions || 0} identical duplicate(s) removed.` : "";
  const navigationUsage = agentReport?.usage;
  const usageMessage = navigationUsage?.input_tokens != null ?
    ` Navigation usage: ${navigationUsage.input_tokens.toLocaleString()} input tokens, ` +
    `${(navigationUsage.output_tokens || 0).toLocaleString()} output tokens` +
    (navigationUsage.cached_input_tokens != null ?
      `; ${navigationUsage.cached_input_tokens.toLocaleString()} input tokens cached (included in input total)` : "") +
    ". Extraction usage is separate." : "";
  stableText(agentStatus, agentMessage + (agentReport?.task_checklist?.date_resolution?.guidance ?
    " " + agentReport.task_checklist.date_resolution.guidance : "") +
    (agentReport?.prompt_version ? ` Agent version: ${agentReport.prompt_version}.` : "") +
    (agentReport ? ` Observation: ${agentReport.visual_enabled ? "DOM + adaptive screenshots" : "DOM/text"}; ` +
      `${agentReport.visual_calls_attempted || 0} visual model decisions attempted.` : "") +
    (agentReport?.failure ? ` Paused at ${agentReport.failure.stage}: ${agentReport.failure.code}.` : "") +
    decisionMessage + validationMessage + messageStructure + selectionMessage + usageMessage);
  agentDetails.hidden = !agentReport;
  const checklist = agentReport?.task_checklist;
  const fields = checklist?.requirements || [];
  const formFields = fields.filter(item => item.application === "form");
  agentChecklist.hidden = !fields.length;
  stableText(agentChecklistTitle, `Search readiness · ${formFields.filter(item => item.status === "verified").length}/${formFields.length} form fields verified`);
  stableText(agentChecklistNote, (checklist?.search_submitted ? "Search page transition observed. " :
    checklist?.search_response_pending ? "Waiting for the Search response; no repeat submission. " : "Search not yet confirmed. ") +
    "Form checks do not prove a listing's availability or price. Review the extracted source evidence.");
  updateRegion(agentChecklistFields, fields, () => {
    agentChecklistFields.replaceChildren();
    for (const field of fields) {
      const row = document.createElement("li");
      row.textContent = `${field.field.replaceAll("_", " ")}: requested ${field.expected}; ` +
        `observed ${field.observed ?? "not yet confirmed"} — ${field.status.replaceAll("_", " ")}`;
      if (field.summary_confirmation_pending) row.textContent += "; confirm/close the widget, then verify its header.";
      if (field.model_interpreted) row.textContent += `; model interpretation: ${field.interpretation || "review this value"}.`;
      agentChecklistFields.append(row);
    }
  });
  updateRegion(agentLog, agentReport?.actions || [], () => {
    agentLog.replaceChildren();
    for (const item of agentReport?.actions || []) {
      const row = document.createElement("li"), text = document.createElement("p");
      text.textContent = `${item.step}. ${item.action}${item.control ? " — " + item.control : ""}: ${item.status.replaceAll("_", " ")}. ${item.explanation}`;
      row.append(text);
      if (item.expected !== undefined) {
        const evidence = document.createElement("p"); evidence.className = "micro";
        evidence.textContent = `Requested: ${item.expected}; observed: ${item.observed ?? "not available"}.`;
        row.append(evidence);
      }
      if (item.evidence || item.guidance) {
        const detail = document.createElement("p"); detail.className = "micro";
        detail.textContent = item.guidance || item.evidence; row.append(detail);
      }
      if (item.verification) {
        const verification = item.verification;
        const change = document.createElement("p"); change.className = "micro";
        change.textContent = `After action: ${verification.status.replaceAll("_", " ")}. ` +
          (verification.document_changed ? "Page changed. " : "") +
          (verification.widget_changed ? "Widget state changed. " : "") +
          (verification.scrolled ? "Viewport moved. " : "") +
          (verification.changed_controls || []).map(c => {
            const actual = c.after !== "" && c.after != null ? c.after :
              c.counter?.value ?? (c.expanded || c.selected || "changed");
            return `${c.control}: ${actual}`;
          }).join("; ");
        row.append(change);
        if (verification.new_controls?.length) {
          const discovered = document.createElement("p"); discovered.className = "micro";
          discovered.textContent = "New controls: " + verification.new_controls.map(c =>
            `${c.label || c.role || "unlabelled control"} (${c.id})`).join("; ");
          row.append(discovered);
        }
      }
      if (item.counter_evidence) {
        const counter = item.counter_evidence;
        const target = document.createElement("p"); target.className = "micro";
        target.textContent = `Counter target: ${counter.target || "not supplied"}; requested counts: ` +
          Object.entries(counter.requested_counts || {}).map(([field, value]) => `${field} ${value}`).join(", ") +
          `. Selected control: ${counter.selected_label || "unknown"}; ` +
          (counter.selected_counter ? `row ${counter.selected_counter.label}, count ${counter.selected_counter.value}.` :
            "not recognized as a stepper.");
        row.append(target);
        const structure = document.createElement("p"); structure.className = "micro";
        structure.textContent = `Control structure: ${counter.selected_tag || "unknown"}; ` +
          `role ${counter.selected_role || "none"}; type ${counter.selected_type || "none"}. ` +
          `Visible child buttons: ${counter.numeric_probe?.child_buttons ?? "not recorded"}; ` +
          `accessibility-hidden child buttons: ${counter.numeric_probe?.accessibility_hidden_buttons ?? "not recorded"}; ` +
          `numeric ARIA value: ${counter.numeric_probe?.aria_value || "none"}.`;
        row.append(structure);
        const available = document.createElement("p"); available.className = "micro";
        available.textContent = "Detected steppers: " + ((counter.available_counters || []).map(c =>
          `${c.label} ${c.value} (${c.direction}${c.enabled === false ? ", disabled" : ""}; ${c.control_id})`).join("; ") ||
          "none. Open the quantity widget and inspect its controls.");
        row.append(available);
        if (item.resolved_control_id) {
          const resolved = document.createElement("p"); resolved.className = "micro";
          resolved.textContent = `Resolved stepper: ${item.counter_field} (${item.resolved_control_id}).`;
          row.append(resolved);
        }
      }
      agentLog.append(row);
    }
  });
  const health = browser.page_health || {};
  const loadState = health.ready_state || "unknown";
  const status = health.main_status == null ? "not recorded" : String(health.main_status);
  healthStatus.textContent = `Document: ${loadState}; HTTP status: ${status}; visible text: ${health.visible_text_chars ?? 0} characters; frames: ${health.frame_count ?? 0}. This does not prove the site's app has finished rendering. Review the Chromium tab before planning.`;
  if (browser.startup_timing?.launch_seconds != null) {
    const timing = browser.startup_timing;
    healthStatus.textContent += ` Startup: browser/driver ${timing.launch_seconds}s; ` +
      `navigation ${timing.navigation_seconds ?? "pending"}s; DOM readiness ${timing.readiness_seconds ?? "pending"}s. ` +
      "Background resources may still be loading; capture checks readiness separately.";
  }
  if (browser.authentication?.status && browser.authentication.status !== "not_requested") {
    healthStatus.textContent += ` Sign-in: ${browser.authentication.status.replaceAll("_", " ")}. ` +
      (browser.authentication.verified ? "Visible signed-in indicator verified." :
        "No independent proof of sign-in yet. Codes and login links stay in the browser.");
  }
  healthStatus.textContent += browser.browser_mode === "normal" ?
    ` Normal networking (${browser.browser_channel || "chromium"}): no application proxy, origin allowlist or request/WebSocket/popup blocking. Network failures below may originate from the site, browser or network.` :
    ` Restricted networking (${browser.browser_channel || "chromium"}): application request filters are active.`;
  if (browser.content_preparation?.preparation) {
    const c = browser.content_preparation;
    healthStatus.textContent += ` Last content preparation: ${c.scroll_steps} loading scroll(s); ` +
      `${c.content_settled ? "stable during sampling" : "stability not confirmed"}; ` +
      `${c.at_page_end ? "page end observed" : "page end not reached"}.`;
  }
  if (browser.browser_error) healthStatus.textContent +=
    ` Last browser error: ${browser.browser_error.stage} (${browser.browser_error.code}).`;
  if (browser.blocked_main_navigation) {
    healthStatus.textContent += ` Main-page navigation to ${browser.blocked_main_navigation} was blocked. If that is the site's trusted canonical address, cancel and use its URL as the starting website in a new session.`;
  }
  const blockedAssets = (browser.blocked_resources || []).filter(item =>
    ["script", "stylesheet", "font"].includes(item.type));
  if (blockedAssets.length) {
    healthStatus.textContent += ` ${blockedAssets.length} script/style/font origin(s) were blocked. This may explain a text-only page. Review the origins below; only add ones you trust, then start a new session. Do not extract until the page looks complete.`;
  }
  navPlanButton.disabled = browser.state !== "waiting";
  hotelPanel.hidden = authenticationPending ||
    (!/\b(?:hotels?|stays?|accommodations?)\b/i.test($("web-request").value) && !browser.hotel_plan);
  hotelPrepare.disabled = browser.state !== "waiting";
  hotelReview.hidden = browser.state !== "hotel_review" || !browser.hotel_plan;
  updateRegion(hotelTargets, [browser.hotel_plan || null, browser.hotel_revision || null], () => {
    hotelTargets.replaceChildren(); hotelCheckbox.checked = false;
    if (browser.hotel_plan?.date_resolution?.guidance) {
      const dateNote = document.createElement("li");
      dateNote.textContent = browser.hotel_plan.date_resolution.guidance;
      hotelTargets.append(dateNote);
    }
    hotelReviewedRevision = browser.hotel_revision || null;
    if (!browser.hotel_plan) return;
    for (const item of browser.hotel_plan.requirements || []) {
      const li = document.createElement("li");
      li.textContent = `${item.field.replaceAll("_", " ")}: ${item.value}` +
        (item.application === "extraction" ? " — filtered during extraction, not applied by the website" : " — verify in website form");
      hotelTargets.append(li);
    }
    const limits = document.createElement("li");
    limits.textContent = `At most ${browser.hotel_plan.max_actions} browser actions / ${browser.hotel_plan.max_seconds} seconds; 0 model-planning calls. Children are unchanged unless explicitly requested. Results are not saved until you approve the extraction preview.`;
    hotelTargets.append(limits);
  });
  hotelApprovalState();
  navApprove.hidden = navDismiss.hidden = browser.state !== "navigation_review";
  navApprove.disabled = navDismiss.disabled = browser.state !== "navigation_review";
  navCoverage.textContent = browser.navigation_plan?.coverage === "text_search" ?
    "Text-search discovery only. The website has not applied your dates, price, rating, or other structured filters. Review results; extraction will apply only source-verifiable criteria." :
    browser.navigation_plan?.coverage === "partial_form" ?
    "Intermediate form actions only; no site search has been submitted. Inspect newly visible suggestions or controls, then request another plan." :
    browser.navigation_plan ? "Review every proposed site control and verify the resulting page before capture." : "";
  if (browser.navigation_plan) navCoverage.textContent += " " + browser.navigation_plan.guidance;
  if (browser.navigation_plan?.missing_fields?.length) navCoverage.textContent +=
    " Correct the missing values, cancel this browser and start a new session. This session keeps its original request.";
  updateRegion(navSteps, [browser.navigation_plan, browser.navigation_controls], () => {
  navSteps.replaceChildren();
  if (browser.navigation_plan) {
    const controls = new Map((browser.navigation_controls || []).map(item => [item.id, item]));
    for (const step of browser.navigation_plan.steps) {
      const li = document.createElement("li"), control = controls.get(step.control_id);
      const purpose = control?.purpose && !["query", "other"].includes(control.purpose) ? ` (${control.purpose.replaceAll("_", " ")})` : "";
      li.textContent = `${step.action === "fill" ? "Fill" : step.action === "select" ? "Select" : step.action === "choose_option" ? "Choose option" : step.action === "open_control" ? "Open" : step.action === "press_enter" ? "Press Enter in" : "Click"} ${control?.label || "control " + step.control_id}${purpose}${["click", "press_enter", "open_control"].includes(step.action) ? "" : " with " + step.value}`;
      navSteps.append(li);
    }
    for (const requirement of browser.navigation_plan.requirements || []) {
      const li = document.createElement("li");
      li.textContent = `Requested ${requirement.field.replaceAll("_", " ")}: ${requirement.value} — ` +
        (requirement.application === "site" ? "verify in website form before submission" :
          "deferred to source-based extraction; not a website filter");
      navSteps.append(li);
    }
    for (const field of browser.navigation_plan.missing_fields || []) {
      const li = document.createElement("li");
      li.textContent = `Needs clarification: ${field.replaceAll("_", " ")}. This step cannot submit a search.`;
      navSteps.append(li);
    }
  }
  });
  linkDiscover.disabled = browser.state !== "waiting";
  linkApprove.hidden = linkDismiss.hidden = browser.state !== "link_review";
  linkApprove.disabled = linkDismiss.disabled = browser.state !== "link_review";
  linkApprove.textContent = browser.link_selection?.kind === "section" ?
    "Open approved section (no extraction)" : "Keep starting page & enrich selected links";
  linkGuidance.textContent = browser.state === "link_review" ?
    browser.link_selection?.guidance || "Review the proposed links before opening them." : "";
  const signature = browser.state === "link_review" ?
    JSON.stringify([browser.link_selection, browser.link_candidates]) : "";
  if (signature !== lastLinkSignature) {
    const selectedLinks = new Set(browser.link_selection?.selected_ids || []);
    lastLinkSignature = signature;
    linkList.replaceChildren();
    for (const item of (browser.link_candidates || []).filter(candidate =>
      selectedLinks.has(candidate.id))) {
      const line = document.createElement("label"); line.className = "inline";
      const checkbox = document.createElement("input"); checkbox.type = "checkbox";
      checkbox.value = String(item.id); checkbox.checked = selectedLinks.has(item.id);
      const roleNote = item.role_hint === "section" ? " (section; navigation only)" : "";
      line.append(checkbox, document.createTextNode(` ${item.title}${roleNote} - ${item.url}`));
      linkList.append(line);
    }
  }
  if (browser.state === "link_review") {
    linkApprove.disabled = !linkList.querySelector('input[type="checkbox"]:checked');
  }
  const resourceSignature = JSON.stringify([browser.blocked_resources, browser.network_failures]);
  if (resourceSignature !== lastResourceSignature) {
    lastResourceSignature = resourceSignature;
    const selectedOrigins = new Set([...resourceList.querySelectorAll('input[type="checkbox"]:checked')]
      .map(item => item.value));
    resourceList.replaceChildren();
    for (const item of browser.blocked_resources || []) {
      const line = document.createElement("label"); line.className = "inline";
      const checkbox = document.createElement("input"); checkbox.type = "checkbox";
      checkbox.value = item.origin;
      checkbox.disabled = !["script", "stylesheet", "font", "image", "xhr", "fetch"].includes(item.type);
      checkbox.checked = selectedOrigins.has(item.origin) && !checkbox.disabled;
      line.append(checkbox, document.createTextNode(` ${item.origin} · ${item.type} · ${item.count} blocked`));
      resourceList.append(line);
    }
    for (const item of browser.network_failures || []) {
      const p = document.createElement("p"); p.className = "micro";
      p.textContent = `${item.origin} · ${item.type} · ${item.count} network failures`;
      resourceList.append(p);
    }
  }
  resourceDisclosure.hidden = !resourceList.childElementCount;
}
function clearWebCapture() {
  webCapture = null;
  $("web-capture-preview").textContent = "No extension capture received.";
  $("web-consent").checked = false;
}
window.addEventListener("message", async event => {
  if (event.source !== window || event.origin !== location.origin ||
      event.data?.type !== "agentic-capture-ready-v1" ||
      typeof event.data.capture_id !== "string" ||
      !/^[a-f0-9-]{36}$/.test(event.data.capture_id) || !signedIn || connectionBlocked) return;
  if (receivingCapture || $("web-create").disabled) {
    webText("web-status", "Another operation is active. Send the capture again after it finishes."); return;
  }
  receivingCapture = true;
  try {
    const capture = await api(`/api/custom/captures/${event.data.capture_id}/claim`, {});
    if (!signedIn || connectionBlocked) return;
    webCapture = capture;
    document.querySelector('[data-view="custom"]').click();
    $("web-source").value = "capture"; $("web-source").onchange();
    $("web-urls").value = capture.url;
    $("web-capture-preview").textContent = JSON.stringify(capture, null, 2);
    webText("web-status", "Browser capture received. Review its text below, enter optional instructions, and explicitly consent to extraction. No model call has run.");
  } catch (error) { webText("web-status", error.message); }
  finally { receivingCapture = false; }
});
$("web-discard-capture").onclick = clearWebCapture;
$("web-open-normal-browser").onclick = () => {
  const entered = $("web-open-url").value.trim() || $("web-urls").value.trim();
  let website;
  try {
    website = new URL(entered);
    if (website.protocol !== "https:" || website.username || website.password) throw new Error();
  } catch (_) {
    webText("web-status", "Enter one full HTTPS website address without embedded credentials, such as https://www.nytimes.com/.");
    return;
  }
  window.open(website.href, "_blank", "noopener,noreferrer");
  webText("web-status", "The website was sent to a new tab in this browser. Sign in and navigate there, then use the Page Capture extension to send the page back. If no tab appeared, check your browser's pop-up setting.");
};
function canApproveWeb() {
  return webProposal && $("web-approved").checked &&
    (!webProposal.partial || $("web-partial-approved").checked);
}
function showRejected(items, fieldIssues = [], fieldRepairs = []) {
  const target = $("web-rejected");
  updateRegion(target, [items, fieldIssues, fieldRepairs], () => {
  target.replaceChildren();
  const showGroup = (entries, headingText) => {
    if (!entries?.length) return;
    const groupDetails = document.createElement("details"), heading = document.createElement("summary");
    heading.textContent = headingText; groupDetails.append(heading); target.append(groupDetails);
    for (const item of entries) {
      const details = document.createElement("details"), title = document.createElement("summary"), body = document.createElement("pre");
      title.textContent = `${item.record_id}: ${item.issues.map(i => i.field + " — " + i.reason.replaceAll("_", " ")).join(", ")}`;
      body.textContent = JSON.stringify(item, null, 2); details.append(title, body); groupDetails.append(details);
    }
  };
  const uncertain = items.filter(item => item.issues.length &&
    item.issues.every(issue => issue.reason === "uncertain_relevance"));
  const invalid = items.filter(item => !uncertain.includes(item));
  showGroup(invalid, `${invalid.length} invalid records (excluded from exports and events)`);
  showGroup(uncertain, `${uncertain.length} records with uncertain topic relevance (not included)`);
  showGroup(fieldIssues, `${fieldIssues.length} records with unsupported optional fields cleared to blank`);
  showGroup(fieldRepairs, `${fieldRepairs.length} records with source-backed corrections — review before saving`);
  });
}
const reviewCountsPanel = document.createElement("section");
reviewCountsPanel.className = "notice"; reviewCountsPanel.hidden = true;
reviewCountsPanel.setAttribute("role", "status");
reviewCountsPanel.setAttribute("aria-live", "polite");
const reviewCountsText = document.createElement("p");
const reviewCountsNote = document.createElement("p"); reviewCountsNote.className = "micro";
const retryLinkDiscovery = document.createElement("button");
retryLinkDiscovery.type = "button"; retryLinkDiscovery.className = "secondary";
retryLinkDiscovery.textContent = "Set up a new session to find relevant links";
const reviewCountsHelp = document.createElement("details"), reviewCountsHelpTitle = document.createElement("summary");
reviewCountsHelpTitle.textContent = "What these counts mean";
reviewCountsHelp.append(reviewCountsHelpTitle, reviewCountsNote);
reviewCountsPanel.append(reviewCountsText, reviewCountsHelp, retryLinkDiscovery);
$("web-status").after(reviewCountsPanel);
let linkRetryContext = null;
function showReviewCounts(data) {
  const counts = data?.review_counts;
  reviewCountsPanel.hidden = !counts;
  retryLinkDiscovery.hidden = true; linkRetryContext = null;
  if (!counts) return;
  reviewCountsText.textContent = `Ready: ${counts.matched} · Unrelated: ${counts.unrelated} · ` +
    `Uncertain: ${counts.uncertain} · Invalid: ${counts.invalid} · ` +
    `Filtered out: ${counts.filtered_out} · Duplicate candidates: ${counts.duplicates}`;
  reviewCountsNote.textContent = `${counts.candidates} model candidates reviewed; ` +
    `${counts.optional_fields_cleared} accepted candidates had unsupported optional fields cleared. ` +
    `${counts.source_fields_corrected || 0} accepted candidates had source-backed corrections. ` +
    "Unrelated means AI-assessed topic mismatch, not invalid source data. " +
    (counts.linked_sources_merged ? "Linked-source candidates may merge into fewer preview records. " : "") +
    "Counts cover captured content, not every record on the website.";
  if (data.next_step === "open_browser_for_links" && data.source_urls?.[0]) {
    linkRetryContext = {url: data.source_urls[0], request: data.request || ""};
    retryLinkDiscovery.hidden = false;
  }
}
retryLinkDiscovery.onclick = () => {
  if (!linkRetryContext) return;
  $("web-source").value = "browser"; $("web-source").onchange();
  $("web-urls").value = linkRetryContext.url;
  $("web-request").value = linkRetryContext.request;
  $("web-consent").checked = false; $("web-normal-confirm").checked = false;
  webText("web-status", "Source and request copied. Review sign-in and browser settings, " +
    "renew API consent, then submit a new session. Once the page is ready, choose " +
    "Find relevant links and review the proposed pages. Nothing started automatically.");
  setStudioStep("source"); $("web-request").focus({preventScroll: true});
};
function webText(id, value) { stableText(document.getElementById(id), value); }
function webBusy(busy) {
  $("web-create").disabled = busy;
  $("web-execute").disabled = busy || !canApproveWeb();
}
$("web-source").onchange = () => {
  updateSourceChoice();
  const paste = $("web-source").value === "paste";
  const browser = $("web-source").value === "browser";
  $("web-extension-preview").hidden = $("web-source").value !== "capture";
  $("web-urls").readOnly = $("web-source").value === "capture";
  loginChoice.hidden = !browser;
  loginChoice.disabled = !browser;
  $("web-browser-mode-options").hidden = !browser;
  $("web-browser-mode-options").disabled = !browser;
  $("web-normal-confirm").checked = false;
  $("web-browser-options").hidden = !browser;
  $("web-browser-options").disabled = !browser;
  $("web-text-label").hidden = !paste;
  $("web-text").required = paste;
  if (!browser) $("web-login-user").value = "";
  $("web-login-password").value = "";
  updateBrowserMode();
  $("web-login-mode").onchange();
  $("web-consent").checked = false;
};
$("web-login-mode").onchange = () => {
  const mode = $("web-login-mode").value;
  const browser = $("web-source").value === "browser";
  const automatic = mode === "automatic";
  if (automatic && browser) advanced.open = true;
  $("web-login-fields").hidden = !automatic; $("web-login-fields").disabled = !automatic;
  const normal = $("web-browser-mode").value === "normal";
  const manualVerification = browser && mode === "manual" && !normal;
  $("web-verification-options").hidden = !manualVerification;
  $("web-verification-options").disabled = !manualVerification;
  if (!manualVerification) $("web-verification-origins").value = "";
  if (!automatic) $("web-login-user").value = "";
  $("web-login-password").value = "";
  loginHelp.textContent = mode === "automatic" ?
    "Enter this website's credentials under Advanced settings. They are used for one sign-in attempt and are not saved." :
    mode === "manual" ? "Chromium will open so you can complete sign-in yourself before capture." :
      "The website opens without a sign-in attempt or website credentials.";
  updateAuthenticationMethod();
};
function updateAuthenticationMethod() {
  const emailOnly = $("web-auth-method").value === "email_verification";
  const password = $("web-login-password");
  password.closest("label").hidden = emailOnly;
  password.disabled = emailOnly;
  password.required = !emailOnly;
  if (emailOnly) password.value = "";
}
$("web-auth-method").onchange = () => {
  updateAuthenticationMethod(); $("web-consent").checked = false;
};
function updateBrowserMode() {
  const normal = $("web-browser-mode").value === "normal";
  const browser = $("web-source").value === "browser";
  $("web-normal-confirm-label").hidden = !browser || !normal;
  $("web-normal-confirm").disabled = !browser || !normal;
  $("web-normal-confirm").required = browser && normal;
  $("web-browser-mode-help").textContent = normal ?
    "Normal networking uses the browser's own network stack, without the app proxy or origin filters. A fresh isolated profile still opens. Browser sandbox/TLS checks and data-review checks remain; this does not bypass a website's bot or login restrictions. Cancel and start a new session to change modes." :
    "Restricted networking uses the current origin allowlist and network proxy. Third-party resources and identity origins need explicit approval. Cancel and start a new session to change modes.";
  $("web-resource-origins").closest("details").hidden = normal;
  $("web-auth-origins").closest("details").hidden = normal;
  updateSourceChoice();
}
$("web-browser-mode").onchange = () => {
  $("web-normal-confirm").checked = false;
  $("web-consent").checked = false;
  updateBrowserMode();
  $("web-login-mode").onchange();
};
$("web-source").onchange();
$("web-approved").onchange = () => { $("web-execute").disabled = !canApproveWeb(); };
$("web-partial-approved").onchange = $("web-approved").onchange;
$("web-form").onsubmit = async event => {
  event.preventDefault();
  if (!modelConfigured) { webText("web-status", "Configure your API key under API connection first."); return; }
  const field = $("web-rule-field").value.trim();
  if (field && !$("web-rule-value").value.trim()) { webText("web-status", "Provide a value for the optional business rule."); return; }
  const values = {
    framework: $("web-framework").value, source: $("web-source").value,
    urls: $("web-urls").value.split(/\r?\n/).map(v => v.trim()).filter(Boolean),
    instructions: $("web-request").value, page_text: $("web-source").value === "paste" ? $("web-text").value : "",
    output_fields: $("web-output-fields").value.split(",").map(value => value.trim()).filter(Boolean),
    record_limit: Number($("web-limit").value), business_rules: field ? [{field, operator: $("web-rule-op").value, value: $("web-rule-value").value}] : [],
    publish_event: $("web-publish").checked, authorized: $("web-authorized").checked, allow_model_api: $("web-consent").checked,
  };
  if (values.output_fields.length > 16 || new Set(values.output_fields).size !== values.output_fields.length ||
      values.output_fields.some(name => !/^[a-z][a-z0-9_]{0,39}$/.test(name))) {
    webText("web-status", "Use up to 16 unique output field names in lowercase, separated by commas (for example: name, price, rating). No model call ran.");
    return;
  }
  if (values.source === "browser") {
    values.browser_mode = $("web-browser-mode").value;
    values.browser_channel = $("web-browser-channel").value;
    values.browser_scroll_steps = Number($("web-scroll-steps").value);
    values.normal_browser_confirmed = values.browser_mode === "normal" && $("web-normal-confirm").checked;
    if (values.browser_mode === "normal" && !values.normal_browser_confirmed) {
      webText("web-status", "Confirm normal networking for this supervised session before opening the browser.");
      return;
    }
    values.login_mode = $("web-login-mode").value;
    values.resource_origins = values.browser_mode === "normal" ? [] : $("web-resource-origins").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    values.verification_origins = values.browser_mode === "normal" ? [] : $("web-verification-origins").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (values.verification_origins.length && values.login_mode !== "manual") {
      webText("web-status", "Trusted verification origins require manual sign-in. Select manual sign-in or clear that list.");
      return;
    }
    if (values.login_mode === "automatic") {
      values.login = {
        method: $("web-auth-method").value,
        url: $("web-login-url").value,
        username: $("web-login-user").value,
        auth_origins: values.browser_mode === "normal" ? [] : $("web-auth-origins").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean),
      };
      if (values.login.method === "password") values.login.password = $("web-login-password").value;
      for (const [field, id] of [["username_selector", "web-user-selector"], ["password_selector", "web-password-selector"], ["submit_selector", "web-submit-selector"], ["success_selector", "web-success-selector"]]) {
        if ($(id).value.trim()) values.login[field] = $(id).value.trim();
      }
    }
  }
  if (values.source === "capture") {
    if (!webCapture) { webText("web-status", "Send a new capture from the browser extension first."); return; }
    values.capture = webCapture; values.urls = [webCapture.url];
  }
  webBusy(true); webText("web-status", "Submitting source inspection…");
  setFlowActivity(true, "Submitting source inspection — waiting for the server to accept the run.");
  try {
    const job = await api("/api/custom/plans", values);
    await customSelect(job.job_id);
  } catch (error) {
    webText("web-status", error.message); webBusy(false);
    setFlowActivity(false, "Submission did not complete. Check the message before retrying.");
  }
  finally { $("web-consent").checked = false; $("web-normal-confirm").checked = false; $("web-login-password").value = ""; $("web-login-user").value = ""; delete values.login; }
};
function webTable(rows, fields) {
  previewRows = rows; previewFields = fields;
  previewResultsButton.disabled = !rows.length;
  renderRecordCards();
  updateRegion($("web-table"), [rows, fields], () => {
  const head = $("web-table").querySelector("thead"), body = $("web-table").querySelector("tbody");
  head.replaceChildren(); body.replaceChildren();
  const names = fields.filter(name => !["evidence", "evidence_sources", "enrichment_conflicts"].includes(name));
  const tr = document.createElement("tr");
  for (const name of [...names, "Source evidence"]) {
    const th = document.createElement("th"); th.scope = "col"; th.textContent = name.replaceAll("_", " "); tr.append(th);
  }
  head.append(tr);
  for (const row of rows) {
    const line = document.createElement("tr");
    for (const name of names) {
      const td = document.createElement("td");
      const value = row[name]; td.textContent = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
      if (typeof value === "string" && /^https?:\/\//i.test(value)) {
        try {
          const url = new URL(value);
          if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) {
            const link = document.createElement("a"); link.href = url.href;
            link.textContent = value; link.target = "_blank"; link.rel = "noopener noreferrer";
            td.replaceChildren(link);
          }
        } catch (_) { /* Non-URL source text remains plain text. */ }
      }
      line.append(td);
    }
    const td = document.createElement("td"), details = document.createElement("details"), summary = document.createElement("summary"), evidence = document.createElement("pre");
    summary.textContent = row.evidence_sources ? "View quotes, sources & conflicts" : "View quotes";
    evidence.textContent = JSON.stringify(row.evidence_sources ? {
      quotes: row.evidence || {}, sources: row.evidence_sources,
      conflicts: row.enrichment_conflicts || {},
    } : row.evidence || {}, null, 2);
    details.append(summary, evidence); td.append(details); line.append(td); body.append(line);
    const preview = document.createElement("button"); preview.type = "button";
    preview.className = "secondary"; preview.textContent = "Preview record";
    preview.onclick = () => openRecordPreview(rows.indexOf(row), preview);
    td.prepend(preview);
  }
  });
}
let previewRows = [], previewFields = [], previewIndex = 0, previewReturnFocus = null;
let previewQuality = {};
const previewDialog = $("web-record-preview");
function recordTitle(row, index) {
  return String(row.article_title || row.headline || row.title || row.hotel_name ||
    row.product_name || row.name || row.listing_id || `Record ${index + 1}`);
}
function sourceValue(target, value) {
  target.textContent = value === null || value === undefined ? "Not extracted — check field issues and page coverage" :
    typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  if (typeof value !== "string" || !/^https?:\/\//i.test(value)) return;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return;
    const link = document.createElement("a"); link.href = url.href; link.textContent = value;
    link.target = "_blank"; link.rel = "noopener noreferrer"; target.replaceChildren(link);
  } catch (_) { /* Keep malformed source values as text. */ }
}
function recordFieldIssues(row) {
  return (previewQuality.field_issues || []).filter(item => item.record_id === row.listing_id)
    .flatMap(item => item.issues || []);
}
function recordFieldStatus(row, name) {
  return (previewQuality.field_statuses || []).find(item => item.record_id === row.listing_id)?.fields?.[name];
}
function outputFields() {
  return previewFields.filter(name => !["listing_id", "source_url", "extracted_at", "record_url",
    "detail_status", "evidence", "evidence_sources", "enrichment_conflicts", "topic_relevance",
    "relevance_reason"].includes(name) && !name.startsWith("rule_"));
}
function recordCoverage(row) {
  const names = outputFields();
  const missing = names.filter(name => row[name] === null || row[name] === undefined || row[name] === "");
  return {names, missing, filled: names.length - missing.length};
}
function renderRecordCards() {
  const cards = $("web-record-cards");
  updateRegion(cards, [previewRows, previewFields, previewQuality.field_issues, previewQuality.field_statuses], () => {
  cards.replaceChildren();
  if (!previewRows.length) {
    const empty = document.createElement("p"); empty.className = "preview-empty";
    empty.textContent = "No preview records yet. Follow the workflow above; your results will appear here.";
    cards.append(empty); return;
  }
  previewRows.forEach((row, index) => {
    const card = document.createElement("article"); card.className = "record-card";
    const number = document.createElement("span"); number.className = "eyebrow";
    number.textContent = `RECORD ${index + 1} OF ${previewRows.length}`;
    const title = document.createElement("h3"); title.textContent = recordTitle(row, index);
    const excerpt = document.createElement("p"); excerpt.className = "record-card-excerpt";
    excerpt.textContent = row.article_excerpt || row.excerpt || row.description || row.summary ||
      "No description or body excerpt was extracted. Open the full preview to inspect the available fields.";
    const coverage = recordCoverage(row);
    const completeness = document.createElement("p"); completeness.className = "record-completeness";
    completeness.dataset.incomplete = String(coverage.missing.length > 0);
    completeness.textContent = `${coverage.filled}/${coverage.names.length} output fields filled` +
      (coverage.missing.length ? ` · ${coverage.missing.length} need attention` : " · review source accuracy");
    const facts = document.createElement("dl"); facts.className = "record-card-facts";
    const keys = previewFields.filter(name => !["listing_id", "evidence", "evidence_sources",
      "enrichment_conflicts", "source_url", "article_excerpt", "excerpt", "description", "summary",
      "article_title", "headline", "title", "hotel_name", "product_name", "name"].includes(name));
    for (const key of keys.slice(0, 3)) {
      const label = document.createElement("dt"), value = document.createElement("dd");
      label.textContent = key.replaceAll("_", " "); sourceValue(value, row[key]); facts.append(label, value);
    }
    const source = document.createElement("p"); source.className = "record-card-source";
    sourceValue(source, row.record_url || row.article_url || row.source_url || "Source unavailable");
    const allFields = document.createElement("details"); allFields.className = "record-all-fields";
    const allSummary = document.createElement("summary");
    allSummary.textContent = `All output fields (${coverage.names.length})`;
    const allValues = document.createElement("dl"); allValues.className = "record-card-facts";
    const issues = recordFieldIssues(row);
    for (const key of coverage.names) {
      const label = document.createElement("dt"), value = document.createElement("dd");
      label.textContent = key.replaceAll("_", " "); sourceValue(value, row[key]);
      const issue = issues.find(item => item.field === key);
      if (issue) {
        const why = document.createElement("small"); why.className = "field-missing-reason";
        why.textContent = `Source check: ${issue.reason.replaceAll("_", " ")}`; value.append(why);
      } else if (coverage.missing.includes(key)) {
        const state = recordFieldStatus(row, key);
        const why = document.createElement("small"); why.className = "field-missing-reason";
        why.textContent = state?.status === "model_not_returned" ?
          "Field preserved, but the model did not return it." :
          state?.reason || "No value extracted; source availability is unconfirmed.";
        value.append(why);
      }
      allValues.append(label, value);
    }
    allFields.append(allSummary, allValues);
    const button = document.createElement("button"); button.type = "button";
    button.textContent = "Preview record & evidence"; button.onclick = () => openRecordPreview(index, button);
    card.append(number, title, completeness, excerpt, facts, allFields, source, button); cards.append(card);
  });
  });
}
function openRecordPreview(index, opener = null) {
  if (!previewRows[index]) return;
  previewIndex = index; if (opener) previewReturnFocus = opener;
  const row = previewRows[index];
  $("web-preview-title").textContent = recordTitle(row, index);
  $("web-preview-position").textContent = `Record ${index + 1} of ${previewRows.length}. ` +
    ($("web-downloads").hidden ? "Preview only — not saved yet." : "Saved snapshot — downloading does not call the model.");
  const coverage = recordCoverage(row);
  $("web-preview-quality").textContent = coverage.missing.length ?
    `${coverage.filled}/${coverage.names.length} output fields filled. Not extracted: ` +
    coverage.missing.map(name => name.replaceAll("_", " ")).join(", ") +
    ". A blank does not prove that the website lacks this information." :
    `${coverage.filled}/${coverage.names.length} output fields filled. This does not prove all website content was captured.`;
  const fields = $("web-preview-fields"); fields.replaceChildren();
  for (const key of previewFields.filter(name => !["evidence", "evidence_sources", "enrichment_conflicts"].includes(name))) {
    const label = document.createElement("dt"), value = document.createElement("dd");
    label.textContent = key.replaceAll("_", " "); sourceValue(value, row[key]); fields.append(label, value);
    const issue = recordFieldIssues(row).find(item => item.field === key);
    if (issue) {
      const why = document.createElement("small"); why.className = "field-missing-reason";
      why.textContent = `Source check: ${issue.reason.replaceAll("_", " ")}`; value.append(why);
    }
  }
  $("web-preview-evidence").textContent = JSON.stringify({quotes: row.evidence || {},
    sources: row.evidence_sources || {}, conflicts: row.enrichment_conflicts || {}}, null, 2);
  $("web-preview-previous").disabled = index === 0;
  $("web-preview-next").disabled = index === previewRows.length - 1;
  if (!previewDialog.open) previewDialog.showModal();
  $("web-preview-back").focus({preventScroll: true});
}
$("web-preview-back").onclick = () => previewDialog.close();
previewDialog.addEventListener("close", () => {
  if (previewReturnFocus?.isConnected) previewReturnFocus.focus({preventScroll: true});
});
$("web-preview-previous").onclick = () => openRecordPreview(previewIndex - 1);
$("web-preview-next").onclick = () => openRecordPreview(previewIndex + 1);
function setResultLayout(mode) {
  $("web-record-cards").hidden = mode !== "cards";
  $("web-table-wrap").hidden = mode !== "table";
  $("web-view-cards").setAttribute("aria-pressed", String(mode === "cards"));
  $("web-view-table").setAttribute("aria-pressed", String(mode === "table"));
}
$("web-view-cards").onclick = () => setResultLayout("cards");
$("web-view-table").onclick = () => setResultLayout("table");
$("web-back-review").onclick = () => {
  setStudioStep("work");
  $("web-status").setAttribute("tabindex", "-1"); $("web-status").focus({preventScroll: true});
};
$("web-back-source").onclick = () => {
  setStudioStep("source"); $("web-request").focus({preventScroll: true});
};
async function customSelect(id) {
  setStudioStep("work");
  if (previewDialog.open) previewDialog.close();
  clearTimeout(webTimer); webSelected = id; webProposal = null; webRevision = null;
  const epoch = ++webPollEpoch;
  lastLinkSignature = ""; lastResourceSignature = "";
  linkList.replaceChildren(); resourceList.replaceChildren();
  for (const {details} of flowNodes.values()) details.open = false;
  $("web-approved").checked = false; $("web-review").hidden = true; $("web-downloads").hidden = true;
  $("web-browser-controls").hidden = true;
  $("web-partial-approved").checked = false; $("web-partial-label").hidden = true;
  showRejected([]);
  showReviewCounts(null);
  showCapturedPages([]);
  showEnrichment(null);
  showNavigationEvidence(null);
  previewQuality = {};
  renderWorkflow({kind: "custom-plan", status: "queued", stages: []});
  webText("web-download-status", ""); webText("web-count", "No records saved for this job.");
  webTable([], []); webBusy(true);
  await customPoll(id, epoch);
}
async function customPoll(id, epoch = webPollEpoch) {
  try {
    if (connectionBlocked || !signedIn) {
      clearTimeout(webTimer); webBusy(false);
      setFlowActivity(false, "Status updates paused — sign in or restore the connection before continuing."); return;
    }
    const job = await api(`/api/jobs/${id}`);
    if (webSelected !== id || epoch !== webPollEpoch) return;
    // Commit one coherent frame, never a browser-less intermediate render.
    const browser = !terminal(job.status) ? await api(`/api/custom/jobs/${id}/browser`) : null;
    if (webSelected !== id || epoch !== webPollEpoch) return;
    const result = job.result || {};
    previewQuality = result.proposal || result;
    showReviewCounts(result.proposal || result);
    showNavigationEvidence(browser || result.proposal?.browser_diagnostics || result.browser_diagnostics);
    renderWorkflow(job, browser);
    showCapturedPages(result.proposal?.captured_pages || result.captured_pages || []);
    showEnrichment(browser?.link_coverage || result.proposal?.enrichment || result.enrichment || result.browser_diagnostics?.link_coverage);
    webText("web-status", `${result.review_outcome === "no_matches" ? "No matching records" : statusLabels[job.status] || job.status}: ${result.guidance || job.guidance || "Processing the current stage…"}`);
    webText("web-evidence", JSON.stringify(job, null, 2));
    $("web-status").dataset.tone = result.review_outcome === "no_matches" ? "review" : ["needs_input", "unsupported", "failed", "interrupted"]
      .includes(job.status) ? "attention" : job.status === "completed" ? "done" : "active";
    updateRegion($("web-progress"), [job.stages, result.trace, terminal(job.status)], () => {
    $("web-progress").replaceChildren();
    for (const item of job.stages || []) {
      const li = document.createElement("li");
      const evidence = (result.trace || []).find(t => t.startsWith(item.stage + ":"));
      li.textContent = `${item.stage.replaceAll("_", " ")} · ${evidence ? evidence.split(":")[1] : terminal(job.status) ? "started; no final evidence" : "started"}`;
      $("web-progress").append(li);
    }
    });
    webBusy(!terminal(job.status));
    if (!terminal(job.status)) {
      $("web-browser-controls").hidden = browser.state === "closed";
      webText("web-browser-status", browser.guidance);
      renderBrowserOptions(browser);
      $("web-capture").disabled = browser.state !== "waiting";
      $("web-cancel-browser").disabled = browser.state === "captured";
      webTimer = setTimeout(() => customPoll(id, epoch), 1000); return;
    }
    $("web-browser-controls").hidden = true;
    showRejected(
      result.proposal?.rejected_records || result.rejected_records || [],
      result.proposal?.field_issues || result.field_issues || [],
      result.proposal?.field_repairs || result.field_repairs || []
    );
    if (result.proposal) {
      webProposal = result.proposal; webRevision = result.revision;
      $("web-partial-label").hidden = !webProposal.partial;
      $("web-review").hidden = false;
      $("web-summary").replaceChildren();
for (const [label, value] of Object.entries({"Original instructions": webProposal.request || "No filters; infer main page content", "Source method": webProposal.source, "Pages": webProposal.urls.join("\n"), "Interpretation": webProposal.interpretation, "Topic selection": webProposal.semantic_selection?.topic || "None", "Captured": webProposal.captured_at, "Expires": webProposal.expires_at, "Excluded by topic or filters": webProposal.excluded_by_filters, "Query rules": (webProposal.query_rules || []).map(r => `${r.name}: ${r.description} (${r.combination === "all" ? "ALL" : "ANY"}: ${r.conditions.map(c => `${c.field} ${c.operator} ${c.value}`).join("; ")})`).join("\n") || "None", "Additional manual conditions": webProposal.business_rules.length ? JSON.stringify(webProposal.business_rules) : "None", "Publish summary event": webProposal.publish_event ? "Yes, after approval" : "No"})) {
        const dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = label; dd.textContent = String(value); $("web-summary").append(dt, dd);
      }
      $("web-fields").replaceChildren();
      for (const field of webProposal.columns) { const p = document.createElement("p"); p.textContent = `${field.name} (${field.kind}${field.unit ? ", " + field.unit : ""}): ${field.description}`; $("web-fields").append(p); }
      for (const [id, items] of [["web-warnings", webProposal.warnings], ["web-filters", webProposal.filters.length ? webProposal.filters.map(f => `${f.field} ${f.operator} ${f.value}`) : ["None — no implicit price or rating restrictions."]]]) {
        $(id).replaceChildren(); for (const text of items) { const li = document.createElement("li"); li.textContent = text; $(id).append(li); }
      }
      webTable(webProposal.records, ["listing_id", ...webProposal.columns.map(c => c.name),
        ...(webProposal.enrichment ? ["record_url", "detail_status"] : []), "source_url"]);
      webText("web-count", `${webProposal.records.length} preview records. Not yet saved as an approved run. Coverage is limited to submitted page text.`);
    }
    if (result.run_id) {
      try {
        const snapshot = await api(`/api/jobs/${id}/records`);
        if (webSelected !== id || epoch !== webPollEpoch) return;
        previewQuality = snapshot;
        webTable(snapshot.records, snapshot.columns);
        showEnrichment(snapshot.enrichment);
        showCapturedPages(snapshot.captured_pages || []);
        showReviewCounts(snapshot);
        showRejected(snapshot.rejected_records || [], snapshot.field_issues || [], snapshot.field_repairs || []);
        webText("web-count", `${snapshot.records.length} saved records · rule matches: ${result.evaluation?.matched ?? "not evaluated"} · summary events acknowledged: ${result.delivery?.published ?? 0}. Run ${result.run_id}`);
        $("web-downloads").hidden = false;
      } catch (_) { webText("web-count", "Saved export not available. Inspect technical evidence before retrying."); }
    }
    await loadHistory();
  } catch (error) {
    if (webSelected !== id || epoch !== webPollEpoch) return;
    webText("web-status", error.message);
    $("web-status").dataset.tone = "attention";
    flowBadge.dataset.tone = "attention";
    flowBadge.textContent = "Connection issue";
    setFlowActivity(false, "Status connection lost — the backend state is unknown. Refresh or inspect the server; this did not cancel the run.");
    webBusy(false);
  }
}
$("web-execute").onclick = async () => {
  if (!canApproveWeb()) return;
  webBusy(true);
  setFlowActivity(true, "Submitting your approval — results are not saved until the server confirms.");
  try {
    const job = await api(`/api/custom/plans/${webProposal.plan_id}/execute`, {
      revision: webRevision, accept_partial: $("web-partial-approved").checked,
    });
    await customSelect(job.job_id);
  } catch (error) {
    webText("web-status", error.message); webBusy(false);
    setFlowActivity(false, "Save submission did not complete. Check the message before retrying.");
  }
};
for (const [id, action] of [["web-capture", "capture"], ["web-cancel-browser", "cancel"],
  ["web-plan-navigation", "plan"], ["web-approve-navigation", "approve"],
  ["web-dismiss-navigation", "dismiss"], ["web-discover-links", "discover"],
  ["web-resume-login", "resume_login"],
  ["web-hotel-plan", "hotel_plan"], ["web-hotel-approve", "hotel_approve"],
  ["web-hotel-extract", "hotel_extract"], ["web-hotel-dismiss", "hotel_dismiss"],
  ["web-agent-start", "agent_start"], ["web-agent-resume", "agent_resume"],
  ["web-agent-collect", "agent_collect"], ["web-agent-manual", "agent_manual"],
  ["web-approve-links", "approve_links"], ["web-dismiss-links", "dismiss_links"]]) {
  $(id).onclick = async () => {
    if (!webSelected) return;
    if (["hotel_approve", "hotel_extract"].includes(action) && (!hotelCheckbox.checked || hotelReview.hidden)) return;
    if (["agent_start", "agent_resume", "agent_collect"].includes(action) && !agentCheckbox.checked) return;
    $(id).disabled = true;
    try {
      const selected_ids = action === "approve_links" ?
        [...linkList.querySelectorAll('input[type="checkbox"]:checked')]
          .map(item => Number(item.value)) : [];
      const approval = ["hotel_approve", "hotel_extract"].includes(action) ?
        {hotel_revision: hotelReviewedRevision, hotel_confirmed: hotelCheckbox.checked} :
        ["agent_start", "agent_resume", "agent_collect"].includes(action) ?
        {agent_confirmed: agentCheckbox.checked,
          agent_visual_confirmed: ["agent_start", "agent_resume"].includes(action) && agentVisualCheckbox.checked} : {};
      await api(`/api/custom/jobs/${webSelected}/browser/${action}`, {selected_ids, ...approval});
      if (action.startsWith("agent_")) {
        agentCheckbox.checked = false;
        agentVisualCheckbox.checked = false;
      }
    }
    catch (error) { webText("web-browser-status", error.message); }
  };
}
resourceAdd.onclick = () => {
  const selected = [...resourceList.querySelectorAll('input[type="checkbox"]:checked')]
    .map(item => item.value);
  const configured = $("web-resource-origins").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const combined = [...new Set([...configured, ...selected])];
  if (!selected.length) { resourceStatus.textContent = "Select a trusted resource origin first."; return; }
  if (combined.length > 8) { resourceStatus.textContent = "Only eight trusted resource origins are supported. Narrow the list."; return; }
  $("web-resource-origins").value = combined.join("\n");
  advanced.open = true;
  resourceStatus.textContent = "Origins added for the next session only. Cancel this browser, review the list, then submit a new session.";
};
$("web-download").onclick = async () => {
  const id = webSelected, format = $("web-format").value;
  if (!id || connectionBlocked) return;
  $("web-download").disabled = true;
  try {
    const response = await fetch(`/api/jobs/${id}/download/${format}`, {cache: "no-store"});
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === "string" ? body.detail : "Download failed."); }
    const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
    link.href = url; link.download = response.headers.get("Content-Disposition")?.match(/filename="([a-zA-Z0-9.-]+)"/)?.[1] || `records.${format}`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    webText("web-download-status", "Download sent to your browser.");
  } catch (error) { webText("web-download-status", error.message); }
  finally { $("web-download").disabled = false; }
};
