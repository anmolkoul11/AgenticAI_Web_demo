"use strict";
let webSelected = null, webTimer = null, webProposal = null, webRevision = null;
let webCapture = null, receivingCapture = false;
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
  "Use the original Chromium tab to navigate to the content. If you chose sign-in, complete and verify it before capture. Review what the model may see.";
function updateSourceChoice() {
  const selected = $("web-source").value;
  for (const button of sourceChoices.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.source === selected));
  }
  $("web-create").textContent = selected === "browser" ?
    "Open website and start" : "Create a preview";
  const guidance = {
    browser: "Enter one website address. A separate Chromium window opens so you can search, sign in if needed, and review the page before capture.",
    capture: "Open a site in your normal Chrome or Edge tab, browse and sign in yourself, then send a reviewed capture with the extension.",
    public: "Enter up to three public page addresses from the same website. This reads HTML without opening an interactive browser.",
    paste: "Enter the original page address and paste only the content you are authorized to process.",
  };
  sourceGuide.textContent = guidance[selected];
  if (selected === "browser") {
    sourceGuide.textContent += $("web-browser-mode").value === "normal" ?
      " Normal networking is selected: the app does not filter browser requests." :
      " Restricted networking is selected by default.";
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
const flowTitle = document.createElement("h2"); flowTitle.textContent = "See where your run stands";
const flowDescription = document.createElement("p"); flowDescription.className = "muted";
flowDescription.textContent = "Open any checkpoint for evidence and next steps. Progress shows stages, not elapsed time.";
flowIntro.append(flowEyebrow, flowTitle, flowDescription);
const flowBadge = document.createElement("span"); flowBadge.className = "flow-badge";
flowBadge.setAttribute("role", "status"); flowBadge.setAttribute("aria-live", "polite");
flowHeader.append(flowIntro, flowBadge);
const flowMeterLabel = document.createElement("p"); flowMeterLabel.className = "flow-meter-label";
const flowMeter = document.createElement("progress");
flowMeter.max = 7; flowMeter.value = 0;
flowMeter.setAttribute("aria-label", "Completed workflow checkpoints");
const flowSteps = document.createElement("ol"); flowSteps.className = "flow-steps";
flowShell.append(flowHeader, flowMeterLabel, flowMeter, flowSteps);
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
  details.dataset.stage = item.id;
  number.className = "flow-step-number"; number.textContent = String(index + 1);
  copy.className = "flow-step-copy"; title.textContent = item.title;
  badge.className = "flow-step-state";
  copy.append(title, badge); summary.append(number, copy);
  body.className = "flow-step-evidence";
  details.append(summary, body); row.append(details); flowSteps.append(row);
  flowNodes.set(item.id, {details, badge, body});
}
let lastAutoOpenedStage = null;
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
  const attention = ["needs_input", "unsupported", "failed", "interrupted"].includes(job?.status);
  const states = {
    setup: job ? "done" : "active",
    browse: !job ? "pending" : inspectFailed && browserSource ? "attention" :
      execution || hasExtraction ? "done" :
      browserSource ? "active" : "skipped",
    capture: execution || hasExtraction ? "done" : inspectFailed ?
      browserSource ? "pending" : "attention" :
      started.has("inspect_website") ? "active" : "pending",
    interpret: execution || hasReview ? "done" : trace.get("extract_content") === "failed" ?
      "attention" : hasExtraction ? "active" : "pending",
    review: execution ? "done" : job?.status === "awaiting_review" ? "review" :
      hasReview && attention ? "attention" : hasReview ? "active" : "pending",
    save: execution ? result.run_id ? "done" : trace.get("save") === "failed" ?
      "attention" : started.has("save") ? "active" : "pending" : "pending",
    event: execution ? trace.get("publish") === "failed" || result.failed_stage === "publish" ?
      "attention" : trace.get("publish") === "ok" ? result.delivery?.enabled ? "done" : "skipped" :
      started.has("publish") ? "active" : "pending" : "pending",
  };
  if (attention && !Object.values(states).includes("attention")) {
    const current = execution ? "save" : hasReview ? "review" : hasExtraction ? "interpret" : "capture";
    states[current] = "attention";
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
    event: result.failed_stage === "publish" ?
      "Records were saved, but event delivery is unconfirmed. Check the saved event and broker before retrying." :
      result.delivery?.enabled ? `${result.delivery.published || 0} summary event(s) acknowledged by the broker. This is not a consumer receipt.` :
      execution && trace.get("publish") === "ok" ? "No event was requested or no records qualified." :
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
  const stateNames = {pending: "Next", active: "In progress", done: "Done",
    review: "Your review", attention: "Needs attention", skipped: "Not needed"};
  const focus = flowDefinitions.find(item => states[item.id] === "attention")?.id ||
    flowDefinitions.find(item => states[item.id] === "review")?.id ||
    flowDefinitions.find(item => states[item.id] === "active")?.id;
  if (focus && focus !== lastAutoOpenedStage) flowNodes.get(focus).details.open = true;
  lastAutoOpenedStage = focus || null;
  for (const item of flowDefinitions) {
    const node = flowNodes.get(item.id);
    node.details.dataset.state = states[item.id];
    node.badge.textContent = stateNames[states[item.id]];
    node.body.textContent = `${item.description} ${evidence[item.id]}`;
  }
  const count = Object.values(states).filter(state => ["done", "skipped"].includes(state)).length;
  flowMeter.value = count;
  flowMeterLabel.textContent = `${count} of ${flowDefinitions.length} checkpoints completed or not needed`;
  flowBadge.dataset.tone = attention ? "attention" : job?.status === "completed" ?
    "done" : job?.status === "awaiting_review" ? "review" : "active";
  flowBadge.textContent = attention ? "Needs attention" : job?.status === "completed" ?
    "Saved" : job?.status === "awaiting_review" ? "Ready for review" : browser?.state === "waiting" ?
    "Browser ready" : job ? "Working" : "Ready to begin";
}
renderWorkflow();
const capturePanel = document.createElement("section");
capturePanel.id = "web-captured-pages"; capturePanel.hidden = true;
stageLog.after(capturePanel);
function showCapturedPages(pages) {
  capturePanel.replaceChildren(); capturePanel.hidden = !pages?.length;
  if (!pages?.length) return;
  const heading = document.createElement("h3");
  heading.textContent = `${pages.length} captured page${pages.length === 1 ? "" : "s"}`;
  const list = document.createElement("ul");
  for (const page of pages) {
    const item = document.createElement("li");
    item.textContent = `${page.source_url} — ${page.visible_text_chars} text characters, ` +
      `${page.paragraph_blocks} paragraph blocks${page.truncated ? "; capture truncated" : ""}`;
    list.append(item);
  }
  capturePanel.append(heading, list);
}
const navPanel = document.createElement("section"), navTitle = document.createElement("h4");
navPanel.id = "web-nav-panel"; navTitle.textContent = "Search this website";
const navHelp = document.createElement("p"); navHelp.className = "micro";
navHelp.textContent = "Optional: one paid model call proposes up to five actions on visible search controls. Review before any click. Dynamic suggestions may require another separately reviewed planning step.";
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
const linkPanel = document.createElement("section"), linkTitle = document.createElement("h4");
linkPanel.id = "web-link-panel"; linkTitle.textContent = "Explore linked pages";
const linkHelp = document.createElement("p"); linkHelp.className = "micro";
linkHelp.textContent = "Need details beyond the current page? Review up to five proposed same-site links before the browser opens them. Some websites need a dedicated connector.";
const linkGuidance = document.createElement("p"); linkGuidance.className = "micro";
linkGuidance.setAttribute("role", "status");
const linkActions = document.createElement("div"); linkActions.className = "button-group";
const linkDiscover = document.createElement("button"); linkDiscover.type = "button";
linkDiscover.id = "web-discover-links"; linkDiscover.textContent = "Find relevant links (paid API)";
const linkApprove = document.createElement("button"); linkApprove.type = "button";
linkApprove.id = "web-approve-links"; linkApprove.textContent = "Open selected pages and extract";
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
browserActions.before(healthPanel, navPanel, linkPanel, pageOnlyTitle, pageOnlyHelp);
const resourceDisclosure = document.createElement("details");
resourceDisclosure.className = "web-resource-disclosure";
const resourceSummary = document.createElement("summary");
resourceSummary.textContent = "Advanced: page loading and blocked resources";
resourceDisclosure.append(resourceSummary, resourcePanel);
browserActions.after(resourceDisclosure);
navPanel.classList.add("journey-action"); linkPanel.classList.add("journey-action");
function renderBrowserOptions(browser) {
  const health = browser.page_health || {};
  const loadState = health.ready_state || "unknown";
  const status = health.main_status == null ? "not recorded" : String(health.main_status);
  healthStatus.textContent = `Document: ${loadState}; HTTP status: ${status}; visible text: ${health.visible_text_chars ?? 0} characters; frames: ${health.frame_count ?? 0}. This does not prove the site's app has finished rendering. Review the Chromium tab before planning.`;
  healthStatus.textContent += browser.browser_mode === "normal" ?
    ` Normal networking (${browser.browser_channel || "chromium"}): no application proxy, origin allowlist or request/WebSocket/popup blocking. Network failures below may originate from the site, browser or network.` :
    ` Restricted networking (${browser.browser_channel || "chromium"}): application request filters are active.`;
  if (browser.blocked_main_navigation) {
    healthStatus.textContent += ` Main-page navigation to ${browser.blocked_main_navigation} was blocked. If that is the site's trusted canonical address, cancel and use its URL as the starting website in a new session.`;
  }
  const blockedAssets = (browser.blocked_resources || []).filter(item =>
    ["script", "stylesheet", "font"].includes(item.type));
  if (blockedAssets.length) {
    healthStatus.textContent += ` ${blockedAssets.length} script/style/font origin(s) were blocked. This may explain a text-only page. Review the origins below; only add ones you trust, then start a new session. Do not extract until the page looks complete.`;
  }
  navSteps.replaceChildren();
  navPlanButton.disabled = browser.state !== "waiting";
  navApprove.hidden = navDismiss.hidden = browser.state !== "navigation_review";
  navApprove.disabled = navDismiss.disabled = browser.state !== "navigation_review";
  navCoverage.textContent = browser.navigation_plan?.coverage === "text_search" ?
    "Text-search discovery only. The website has not applied your dates, price, rating, or other structured filters. Review results; extraction will apply only source-verifiable criteria." :
    browser.navigation_plan?.coverage === "partial_form" ?
    "Intermediate form actions only; no site search has been submitted. Inspect newly visible suggestions or controls, then request another plan." :
    browser.navigation_plan ? "Review every proposed site control and verify the resulting page before capture." : "";
  if (browser.navigation_plan) {
    const controls = new Map((browser.navigation_controls || []).map(item => [item.id, item]));
    for (const step of browser.navigation_plan.steps) {
      const li = document.createElement("li"), control = controls.get(step.control_id);
      li.textContent = `${step.action === "fill" ? "Fill" : step.action === "select" ? "Select" : step.action === "choose_option" ? "Choose suggestion" : step.action === "press_enter" ? "Press Enter in" : "Click"} ${control?.label || "control " + step.control_id}${["click", "press_enter", "choose_option"].includes(step.action) ? "" : " with " + step.value}`;
      navSteps.append(li);
    }
  }
  linkDiscover.disabled = browser.state !== "waiting";
  linkApprove.hidden = linkDismiss.hidden = browser.state !== "link_review";
  linkApprove.disabled = linkDismiss.disabled = browser.state !== "link_review";
  linkApprove.textContent = browser.link_selection?.kind === "section" ?
    "Open approved section (no extraction)" : "Open selected pages and extract";
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
function showRejected(items, fieldIssues = []) {
  const target = $("web-rejected"); target.replaceChildren();
  const showGroup = (entries, headingText) => {
    if (!entries?.length) return;
    const heading = document.createElement("h3"); heading.textContent = headingText; target.append(heading);
    for (const item of entries) {
      const details = document.createElement("details"), title = document.createElement("summary"), body = document.createElement("pre");
      title.textContent = `${item.record_id}: ${item.issues.map(i => i.field + " — " + i.reason.replaceAll("_", " ")).join(", ")}`;
      body.textContent = JSON.stringify(item, null, 2); details.append(title, body); target.append(details);
    }
  };
  showGroup(items, `${items.length} rejected records (excluded from exports and events)`);
  showGroup(fieldIssues, `${fieldIssues.length} records with unsupported optional fields cleared to blank`);
}
function webText(id, value) { document.getElementById(id).textContent = value; }
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
    record_limit: Number($("web-limit").value), business_rules: field ? [{field, operator: $("web-rule-op").value, value: $("web-rule-value").value}] : [],
    publish_event: $("web-publish").checked, authorized: $("web-authorized").checked, allow_model_api: $("web-consent").checked,
  };
  if (values.source === "browser") {
    values.browser_mode = $("web-browser-mode").value;
    values.browser_channel = $("web-browser-channel").value;
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
        url: $("web-login-url").value,
        username: $("web-login-user").value,
        password: $("web-login-password").value,
        auth_origins: values.browser_mode === "normal" ? [] : $("web-auth-origins").value.split(/\r?\n/).map(s => s.trim()).filter(Boolean),
      };
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
  try {
    const job = await api("/api/custom/plans", values);
    await customSelect(job.job_id);
  } catch (error) { webText("web-status", error.message); webBusy(false); }
  finally { $("web-consent").checked = false; $("web-normal-confirm").checked = false; $("web-login-password").value = ""; $("web-login-user").value = ""; delete values.login; }
};
function webTable(rows, fields) {
  const head = $("web-table").querySelector("thead"), body = $("web-table").querySelector("tbody");
  head.replaceChildren(); body.replaceChildren();
  const names = fields.filter(name => name !== "evidence");
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
      line.append(td);
    }
    const td = document.createElement("td"), details = document.createElement("details"), summary = document.createElement("summary"), evidence = document.createElement("pre");
    summary.textContent = "View quotes"; evidence.textContent = JSON.stringify(row.evidence || {}, null, 2);
    details.append(summary, evidence); td.append(details); line.append(td); body.append(line);
  }
}
async function customSelect(id) {
  clearTimeout(webTimer); webSelected = id; webProposal = null; webRevision = null;
  lastAutoOpenedStage = null;
  lastLinkSignature = ""; lastResourceSignature = "";
  linkList.replaceChildren(); resourceList.replaceChildren();
  for (const {details} of flowNodes.values()) details.open = false;
  $("web-approved").checked = false; $("web-review").hidden = true; $("web-downloads").hidden = true;
  $("web-browser-controls").hidden = true;
  $("web-partial-approved").checked = false; $("web-partial-label").hidden = true;
  showRejected([]);
  showCapturedPages([]);
  renderWorkflow({kind: "custom-plan", status: "queued", stages: []});
  webText("web-download-status", ""); webText("web-count", "No records saved for this job.");
  webTable([], []); webBusy(true);
  await customPoll(id);
}
async function customPoll(id) {
  try {
    if (connectionBlocked || !signedIn) { clearTimeout(webTimer); webBusy(false); return; }
    const job = await api(`/api/jobs/${id}`); if (webSelected !== id) return;
    const result = job.result || {};
    renderWorkflow(job);
    showCapturedPages(result.proposal?.captured_pages || result.captured_pages || []);
    webText("web-status", `${statusLabels[job.status] || job.status}: ${result.guidance || job.guidance || "Processing the current stage…"}`);
    webText("web-evidence", JSON.stringify(job, null, 2));
    $("web-status").dataset.tone = ["needs_input", "unsupported", "failed", "interrupted"]
      .includes(job.status) ? "attention" : job.status === "completed" ? "done" : "active";
    $("web-progress").replaceChildren();
    for (const item of job.stages || []) {
      const li = document.createElement("li");
      const evidence = (result.trace || []).find(t => t.startsWith(item.stage + ":"));
      li.textContent = `${item.stage.replaceAll("_", " ")} · ${evidence ? evidence.split(":")[1] : terminal(job.status) ? "started; no final evidence" : "started"}`;
      $("web-progress").append(li);
    }
    webBusy(!terminal(job.status));
    if (!terminal(job.status)) {
      const browser = await api(`/api/custom/jobs/${id}/browser`);
      if (webSelected !== id) return;
      renderWorkflow(job, browser);
      $("web-browser-controls").hidden = browser.state === "closed";
      webText("web-browser-status", browser.guidance);
      renderBrowserOptions(browser);
      $("web-capture").disabled = browser.state !== "waiting";
      $("web-cancel-browser").disabled = browser.state === "captured";
      webTimer = setTimeout(() => customPoll(id), 1000); return;
    }
    $("web-browser-controls").hidden = true;
    showRejected(
      result.proposal?.rejected_records || result.rejected_records || [],
      result.proposal?.field_issues || result.field_issues || []
    );
    if (result.proposal) {
      webProposal = result.proposal; webRevision = result.revision;
      $("web-partial-label").hidden = !webProposal.partial;
      $("web-review").hidden = false;
      $("web-summary").replaceChildren();
      for (const [label, value] of Object.entries({"Original instructions": webProposal.request || "No filters; infer main page content", "Source method": webProposal.source, "Pages": webProposal.urls.join("\n"), "Interpretation": webProposal.interpretation, "Topic selection": webProposal.semantic_selection?.topic || "None", "Captured": webProposal.captured_at, "Expires": webProposal.expires_at, "Excluded by filters": webProposal.excluded_by_filters, "Query rules": (webProposal.query_rules || []).map(r => `${r.name}: ${r.description} (${r.combination === "all" ? "ALL" : "ANY"}: ${r.conditions.map(c => `${c.field} ${c.operator} ${c.value}`).join("; ")})`).join("\n") || "None", "Additional manual conditions": webProposal.business_rules.length ? JSON.stringify(webProposal.business_rules) : "None", "Publish summary event": webProposal.publish_event ? "Yes, after approval" : "No"})) {
        const dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = label; dd.textContent = String(value); $("web-summary").append(dt, dd);
      }
      $("web-fields").replaceChildren();
      for (const field of webProposal.columns) { const p = document.createElement("p"); p.textContent = `${field.name} (${field.kind}${field.unit ? ", " + field.unit : ""}): ${field.description}`; $("web-fields").append(p); }
      for (const [id, items] of [["web-warnings", webProposal.warnings], ["web-filters", webProposal.filters.length ? webProposal.filters.map(f => `${f.field} ${f.operator} ${f.value}`) : ["None — no implicit price or rating restrictions."]]]) {
        $(id).replaceChildren(); for (const text of items) { const li = document.createElement("li"); li.textContent = text; $(id).append(li); }
      }
      webTable(webProposal.records, ["listing_id", ...webProposal.columns.map(c => c.name), "source_url"]);
      webText("web-count", `${webProposal.records.length} preview records. Not yet saved as an approved run. Coverage is limited to submitted page text.`);
    }
    if (result.run_id) {
      try {
        const snapshot = await api(`/api/jobs/${id}/records`); if (webSelected !== id) return;
        webTable(snapshot.records, snapshot.columns);
        webText("web-count", `${snapshot.records.length} saved records · rule matches: ${result.evaluation?.matched ?? "not evaluated"} · summary events acknowledged: ${result.delivery?.published ?? 0}. Run ${result.run_id}`);
        $("web-downloads").hidden = false;
      } catch (_) { webText("web-count", "Saved export not available. Inspect technical evidence before retrying."); }
    }
    await loadHistory();
  } catch (error) {
    webText("web-status", error.message);
    $("web-status").dataset.tone = "attention";
    flowBadge.dataset.tone = "attention";
    flowBadge.textContent = "Connection issue";
    webBusy(false);
  }
}
$("web-execute").onclick = async () => {
  if (!canApproveWeb()) return;
  webBusy(true);
  try {
    const job = await api(`/api/custom/plans/${webProposal.plan_id}/execute`, {
      revision: webRevision, accept_partial: $("web-partial-approved").checked,
    });
    await customSelect(job.job_id);
  } catch (error) { webText("web-status", error.message); webBusy(false); }
};
for (const [id, action] of [["web-capture", "capture"], ["web-cancel-browser", "cancel"],
  ["web-plan-navigation", "plan"], ["web-approve-navigation", "approve"],
  ["web-dismiss-navigation", "dismiss"], ["web-discover-links", "discover"],
  ["web-approve-links", "approve_links"], ["web-dismiss-links", "dismiss_links"]]) {
  $(id).onclick = async () => {
    if (!webSelected) return;
    $(id).disabled = true;
    try {
      const selected_ids = action === "approve_links" ?
        [...linkList.querySelectorAll('input[type="checkbox"]:checked')]
          .map(item => Number(item.value)) : [];
      await api(`/api/custom/jobs/${webSelected}/browser/${action}`, {selected_ids});
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
