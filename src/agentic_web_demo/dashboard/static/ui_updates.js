"use strict";
// Real ring elements + persistent Web Animations: polling must not restart motion.
const activityAnimations = new WeakMap();
function setRingMotion(element, running) {
  element.dataset.motionRunning = String(running);
  let animation = activityAnimations.get(element);
  if (running) {
    if (!animation && element.animate) {
      animation = element.animate([{transform: "rotate(0deg)"}, {transform: "rotate(360deg)"}],
        {duration: 950, iterations: Infinity});
      activityAnimations.set(element, animation);
    }
    element.dataset.motionFallback = String(!element.animate);
  } else {
    animation?.cancel(); activityAnimations.delete(element);
    element.dataset.motionFallback = "false";
  }
}
// Keep unchanged DOM nodes (focus, checkboxes, disclosure state and animations).
const uiRegionSignatures = new WeakMap();
function updateRegion(element, value, draw) {
  const signature = JSON.stringify(value);
  if (uiRegionSignatures.get(element) === signature) return false;
  draw();
  uiRegionSignatures.set(element, signature);
  return true;
}
function stableText(element, value) {
  const text = value === null || value === undefined ? "" : String(value);
  if (element.textContent !== text) element.textContent = text;
}
function workflowActivity(job, browser, source = "browser") {
  if (!job) return {running: false, waiting: false, stage: "setup", message: "Idle — ready for your request."};
  if (!["queued", "running"].includes(job.status)) {
    return {running: false, waiting: false, stage: null, message:
      job.status === "awaiting_review" ? "Waiting for your review — preview the records before saving." :
      job.status === "completed" ? "Finished — saved results are ready to explore and download." :
      job.result?.review_outcome === "no_matches" ? "Finished reviewing — no matches in the captured content." :
      "Stopped — check the highlighted step and message below."};
  }
  // Once extraction starts, job stages outrank an old waiting browser snapshot.
  const modelStarted = (job.stages || []).some(item => item.stage === "extract_content");
  const waiting = job.kind !== "custom-execute" && !modelStarted &&
    ["waiting", "authentication_pending", "navigation_review", "link_review",
    "verification_required", "hotel_review", "agent_paused"].includes(browser?.state);
  const browserWork = {
    starting: "Opening the browser and loading your website.",
    authentication_pending: "Waiting for you to finish sign-in in the website browser.",
    checking_authentication: "Checking the visible sign-in status before continuing.",
    verification_required: "Waiting for you to complete website verification or cancel.",
    waiting: "Browser ready — choose a search, linked pages, or this-page extraction.",
    planning_navigation: "Reading the visible search controls and proposing actions.",
    navigation_review: "Waiting for you to review and approve the proposed search actions.",
    navigating: "Applying your approved search actions and checking the website form.",
    hotel_preparing: "Preparing the complete hotel search for your review; no model call.",
    hotel_review: "Waiting for you to approve the destination, dates, adults and rooms.",
    hotel_running: browser?.guidance || "Setting hotel fields, checking values and submitting Search.",
    agent_running: browser?.guidance || "Agent observing the page and choosing its next action.",
    agent_pausing: "Pausing before the next browser action. An in-flight model call may finish first.",
    agent_paused: browser?.guidance || "Agent paused — check the browser and choose how to continue.",
    agent_collecting: "Passing the agent's retained source pages to extraction.",
    discovering_links: "Finding relevant links in the captured starting page.",
    link_review: "Waiting for you to select and approve which links to open.",
    opening_section: "Opening the approved website section to find relevant content.",
    capturing: "Collecting visible content and links from the current page.",
    capturing_articles: "Opening approved links and collecting their detail content.",
  };
  const stages = new Set((job.stages || []).map(item => item.stage));
  const execution = job.kind === "custom-execute";
  const stage = execution ? stages.has("publish") ? "event" : "save" :
    stages.has("review_content") ? "review" : stages.has("extract_content") ? "interpret" :
    ["capturing", "capturing_articles", "captured"].includes(browser?.state) || source !== "browser" ?
    "capture" : "browse";
  const message = !execution && !stages.has("extract_content") && browserWork[browser?.state] ?
    browserWork[browser.state] : {
      browse: "Opening and inspecting the website before any extraction.",
      capture: "Collecting the supplied page content and source evidence.",
      interpret: "The model is extracting records according to your request.",
      review: "Checking fields, source quotes and your requested filters.",
      save: "Checking your approval and saving the reviewed records.",
      event: "Evaluating optional event delivery and publishing qualifying results.",
    }[stage];
  return {running: !waiting, waiting, stage, message:
    job.status === "queued" ? "Queued — waiting for the background task to start." : message};
}
