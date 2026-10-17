"""Stable UI regressions. Browser fixtures are local and opt-in; no model calls.

Use --run-browser to exercise actual DOM/animation behavior with stubbed API data.
"""

import re

import pytest
from test_source_inventory import inventory_browser as shared_inventory_browser

from agentic_web_demo.dashboard.app import ASSETS


def test_poll_commits_one_browser_aware_frame_and_rejects_stale_responses():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    poll = script.split("async function customPoll(", 1)[1].split('$("web-execute").onclick', 1)[0]
    assert poll.count("renderWorkflow(job, browser)") == 1
    assert "renderWorkflow(job);" not in poll
    assert poll.index("const browser =") < poll.index("renderWorkflow(job, browser)")
    assert "epoch !== webPollEpoch" in poll
    assert "customPoll(id, epoch)" in poll
    assert "lastAutoOpenedStage" not in script
    for region in (
        "capturePanel",
        "enrichmentPanel",
        "navigationEvidence",
        '$("web-progress")',
    ):
        assert f"updateRegion({region}," in script


def test_local_helpers_are_loaded_before_application_and_circle_is_transformable():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert (
        html.index("/static/ui_updates.js")
        < html.index("/static/app.js")
        < html.index("/static/custom.js")
    )
    css = (ASSETS / "custom.css").read_text(encoding="utf-8")
    assert ".flow-spinner{display:inline-block" in css
    assert "@keyframes checkpoint-spin" in css
    assert '.flow-steps [data-running="true"] .flow-step-ring' in css
    assert "animation:none" in css and "prefers-reduced-motion:reduce" in css


@pytest.fixture
def live_ui(request):
    # Reuse the existing isolated browser fixture: every request is locally fulfilled.
    for browser in shared_inventory_browser.__wrapped__(request):
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
        browser.set_content(html)
        browser.emulate_media(reduced_motion="no-preference")
        browser.add_style_tag(content=(ASSETS / "style.css").read_text(encoding="utf-8"))
        browser.add_style_tag(content=(ASSETS / "custom.css").read_text(encoding="utf-8"))
        browser.add_script_tag(content=(ASSETS / "ui_updates.js").read_text(encoding="utf-8"))
        browser.add_script_tag(
            content="""
          const $ = id => document.getElementById(id);
          let signedIn = true, connectionBlocked = false, modelConfigured = true;
          const terminal = status => !['queued','running'].includes(status);
          const statusLabels = {running:'Running', awaiting_review:'Review needed'};
          window.fixtureCalls = [];
          async function api(path, data) {
            window.fixtureCalls.push(path);
            if (window.fixtureApi) return window.fixtureApi(path, data);
            throw new Error('Unexpected fixture API operation');
          }
          async function loadHistory() {}
          $('workspace').hidden = false; $('auth-shell').hidden = true;
          for (const page of document.querySelectorAll('[data-page]')) {
            page.hidden = page.dataset.page !== 'custom';
          }
        """
        )
        browser.add_script_tag(content=(ASSETS / "custom.js").read_text(encoding="utf-8"))
        # Each fixture drives its intended status updates explicitly. Unrelated
        # background browser-status polling must not race API-call assertions.
        browser.evaluate("clearTimeout(verificationBrowserTimer)")
        yield browser


def test_initial_checkpoints_are_idle_or_pending_not_running(live_ui):
    result = live_ui.evaluate("""() => ({
      setup:flowNodes.get('setup').details.dataset.state,
      label:flowNodes.get('setup').badge.textContent,
      running:document.querySelectorAll('.flow-steps [data-running="true"]').length,
      active:document.querySelectorAll('.flow-steps [data-state="active"]').length,
      meter:flowMeter.value, hidden:flowSpinner.hidden,
      others:[...flowNodes].slice(1).map(([,node]) => node.details.dataset.state)
    })""")
    assert result == {
        "setup": "idle",
        "label": "Idle",
        "running": 0,
        "active": 0,
        "meter": 0,
        "hidden": True,
        "others": ["pending"] * 6,
    }


def test_user_pause_request_stays_active_until_agent_stops(live_ui):
    activity = live_ui.evaluate("""() => workflowActivity({
      kind:'custom-plan',status:'running',stages:[{stage:'inspect_website'}]
    },{state:'agent_pausing'})""")
    assert activity["running"] and not activity["waiting"]
    assert activity["stage"] == "browse"
    assert "in-flight model call" in activity["message"]


@pytest.mark.parametrize(
    ("delivery", "expected_state", "expected_label", "evidence"),
    [
        ({"enabled": False, "published": 0}, "skipped", "Skipped — disabled", "disabled"),
        ({"enabled": True, "published": 0}, "skipped", "Skipped — no matches", "no saved records"),
        # The real summary publisher returns an ACK without an enabled flag.
        (
            {"published": 1, "broker_acknowledged": True, "stream_sequence": 8},
            "done",
            "Published",
            "1 summary event(s) acknowledged",
        ),
        ({"enabled": True, "published": 1}, "done", "Published", "not a consumer receipt"),
        ({}, "attention", "Needs attention", "acknowledgement evidence is missing"),
    ],
)
def test_publish_checkpoint_distinguishes_acknowledged_skipped_and_unknown(
    live_ui, delivery, expected_state, expected_label, evidence
):
    result = live_ui.evaluate(
        """delivery => {
      renderWorkflow({kind:'custom-execute',status:'completed',stages:[],result:{
        run_id:'fixture-run',delivery,trace:['save:ok','evaluate:ok','publish:ok']}});
      const node=flowNodes.get('event');
      return {state:node.details.dataset.state,label:node.badge.textContent,
        evidence:node.body.textContent,meter:flowMeter.value,
        running:node.details.dataset.running,animations:node.ring.getAnimations().length};
    }""",
        delivery,
    )
    assert result["state"] == expected_state
    assert result["label"] == expected_label
    assert evidence in result["evidence"]
    assert result["meter"] == (6 if expected_state == "attention" else 7)
    assert result["running"] == "false" and result["animations"] == 0


def test_publish_failure_does_not_claim_acknowledgement_or_reactivate_ring(live_ui):
    result = live_ui.evaluate("""() => {
      renderWorkflow({kind:'custom-execute',status:'failed',stages:[{stage:'publish'}],result:{
        run_id:'saved-run',failed_stage:'publish',delivery:{enabled:true,published:0},
        trace:['save:ok','evaluate:ok','publish:ok']}});
      const node=flowNodes.get('event');
      return {state:node.details.dataset.state,label:node.badge.textContent,
        evidence:node.body.textContent,running:node.details.dataset.running,meter:flowMeter.value};
    }""")
    # A handled failure can still have publish:ok in the stage-call trace.
    assert result["state"] == "attention" and result["label"] == "Needs attention"
    assert "unconfirmed" in result["evidence"]
    assert result["running"] == "false" and result["meter"] == 6


@pytest.mark.parametrize(
    ("enabled", "label"),
    [(False, "Optional — disabled"), (True, "Pending approval & save")],
)
def test_preview_does_not_pretend_an_event_has_already_been_published(live_ui, enabled, label):
    result = live_ui.evaluate(
        """enabled => {
      renderWorkflow({kind:'custom-plan',status:'awaiting_review',stages:[],result:{
        proposal:{publish_event:enabled},
        trace:['inspect_website:ok','extract_content:ok','review_content:ok']}});
      return {state:flowNodes.get('event').details.dataset.state,
        label:flowNodes.get('event').badge.textContent,running:flowShell.dataset.running};
    }""",
        enabled,
    )
    assert result == {"state": "pending", "label": label, "running": "false"}


def test_running_ring_and_clicked_checkpoint_have_real_stage_details(live_ui):
    result = live_ui.evaluate("""() => {
      renderWorkflow({status:'running',kind:'custom-plan',stages:[
        {stage:'inspect_website'},{stage:'extract_content'}]}, {state:'captured'});
      const active = document.querySelector('.flow-steps [data-running="true"]');
      return {activeCount:document.querySelectorAll('.flow-steps [data-running="true"]').length,
        step:active.dataset.stage, initiallyOpen:active.open,
        animation:active.querySelector('.flow-step-ring').getAnimations()[0]?.playState,
        spinnerDisplay:getComputedStyle(flowSpinner).display};
    }""")
    assert result == {
        "activeCount": 1,
        "step": "interpret",
        "initiallyOpen": False,
        "animation": "running",
        "spinnerDisplay": "block",  # Flex items are blockified by the browser.
    }
    live_ui.locator('.flow-steps [data-stage="interpret"] summary').click()
    assert live_ui.locator('.flow-steps [data-stage="interpret"]').get_attribute("open") is not None
    assert (
        "model is extracting"
        in live_ui.locator('.flow-steps [data-stage="interpret"] .flow-step-evidence').inner_text()
    )


@pytest.mark.parametrize(
    "state", ["waiting", "link_review", "authentication_pending", "navigation_review"]
)
def test_waiting_does_not_spin_and_preserves_user_opened_checkpoint(live_ui, state):
    result = live_ui.evaluate(
        """state => {
      const job = {status:'running',kind:'custom-plan',stages:[{stage:'inspect_website'}]};
      renderWorkflow(job,{state});
      const details = flowNodes.get('browse').details; details.open = true;
      renderWorkflow(job,{state});
      return {count:document.querySelectorAll('.flow-steps [data-running="true"]').length,
        badge:flowBadge.textContent, open:details.open, hidden:flowSpinner.hidden};
    }""",
        state,
    )
    assert result == {
        "count": 0,
        "badge": "Waiting for you",
        "open": True,
        "hidden": True,
    }


def test_repeated_polls_preserve_coverage_nodes_and_render_only_once(live_ui):
    result = live_ui.evaluate("""async () => {
      const job = {job_id:'fixture-job',status:'running',kind:'custom-plan',
        stages:[{stage:'inspect_website'}]};
      const browser = {state:'waiting',guidance:'Browser ready', page_health:{},
        link_coverage:{index_retained:true,approved:1,captured:1,failed:0,
          links:[{url:'https://news.example.org/story',title:'Story',status:'captured'}]},
        navigation_result:{status:'partial_form',actions:[],requirements:[]}};
      window.fixtureApi = async path => path.includes('/browser') ? browser : job;
      webSelected = 'fixture-job';
      let renders = 0, interim = false;
      const original = renderWorkflow;
      renderWorkflow = (...args) => {
        renders++; if (!args[1]) interim = true; return original(...args);
      };
      await customPoll(webSelected); clearTimeout(webTimer);
      const coverageNode = enrichmentPanel.firstElementChild;
      const evidenceNode = navigationEvidence.firstElementChild;
      enrichmentPanel.open = true;
      await customPoll(webSelected); clearTimeout(webTimer);
      return {renders,interim,sameCoverage:coverageNode===enrichmentPanel.firstElementChild,
        sameEvidence:evidenceNode===navigationEvidence.firstElementChild,open:enrichmentPanel.open};
    }""")
    assert result == {
        "renders": 2,
        "interim": False,
        "sameCoverage": True,
        "sameEvidence": True,
        "open": True,
    }


def test_delayed_response_from_old_selection_cannot_redraw_new_run(live_ui):
    result = live_ui.evaluate("""async () => {
      let resolveOld;
      window.fixtureApi = () => new Promise(resolve => {resolveOld = resolve;});
      webSelected='old-job'; const oldEpoch=webPollEpoch;
      const pending=customPoll('old-job',oldEpoch);
      webSelected='new-job'; webPollEpoch++;
      flowActivityText.textContent='New selection';
      resolveOld({job_id:'old-job',status:'running',kind:'custom-plan',stages:[]});
      await pending; clearTimeout(webTimer);
      return {message:flowActivityText.textContent,calls:window.fixtureCalls};
    }""")
    assert result == {"message": "New selection", "calls": ["/api/jobs/old-job"]}


def test_cards_expose_all_fields_and_do_not_claim_blank_means_absent(live_ui):
    live_ui.evaluate("""() => {
      previewQuality={field_issues:[{record_id:'record-1',issues:[
        {field:'author',reason:'quote_missing_from_source'}]}]};
      webTable([{listing_id:'record-1',title:'Source title',price:'250',currency:'USD',rating:'4.2',
        city:'Boston',author:null,source_url:'https://news.example.org/story',
        evidence:{title:'Source title'}}],
        ['listing_id','title','price','currency','rating','city','author','source_url']);
      setStudioStep('results');
    }""")
    card = live_ui.locator("#web-record-cards .record-card")
    assert card.locator(".record-fact-section dt").count() == 4
    assert card.get_by_text("Source title", exact=True).is_visible()
    card.locator(".record-missing-details summary").click()
    assert "author" in card.locator(".record-missing-details").inner_text()
    assert "quote missing from source" in card.locator(".record-missing-details").inner_text()
    assert "5/6 output fields filled" in live_ui.locator(".record-completeness").inner_text()
    live_ui.locator(".record-card>button").click()
    assert "blank does not prove" in live_ui.locator("#web-preview-quality").inner_text()
    live_ui.locator("#web-preview-back").click()
    assert card.locator(".record-missing-details").get_attribute("open") is not None
    assert live_ui.evaluate("window.fixtureCalls") == []


def test_running_indicator_is_always_animated_without_a_motion_setting(live_ui):
    live_ui.emulate_media(reduced_motion="reduce")
    result = live_ui.evaluate("""() => {
      renderWorkflow({status:'running',kind:'custom-plan',stages:[{stage:'extract_content'}]},
        {state:'captured'});
      const active=document.querySelector('.flow-steps [data-running="true"]');
      const ring=active.querySelector('.flow-step-ring');
      return {animation:ring.getAnimations().length,
        text:active.textContent, activity:flowActivityText.textContent};
    }""")
    assert result["animation"] == 1
    assert "Running" in result["text"] and "extracting records" in result["activity"]


def test_ring_revolves_and_polling_does_not_restart_animation(live_ui):
    result = live_ui.evaluate("""async () => {
      const job={status:'running',kind:'custom-plan',stages:[{stage:'extract_content'}]};
      // A stale browser waiting state must not stop active model progress.
      renderWorkflow(job,{state:'waiting'});
      const ring=flowNodes.get('interpret').ring;
      const animation=ring.getAnimations()[0];
      await new Promise(resolve => setTimeout(resolve,150));
      const firstTime=animation.currentTime, firstTransform=getComputedStyle(ring).transform;
      renderWorkflow(job,{state:'waiting'});
      await new Promise(resolve => setTimeout(resolve,230));
      return {same:ring.getAnimations()[0]===animation,
        advanced:animation.currentTime > firstTime,
        moved:getComputedStyle(ring).transform !== firstTransform,
        running:flowNodes.get('interpret').details.dataset.running};
    }""")
    assert result == {"same": True, "advanced": True, "moved": True, "running": "true"}


def test_waiting_stops_ring_and_new_work_restarts_it_without_a_toggle(live_ui):
    live_ui.evaluate("""() => renderWorkflow({status:'running',kind:'custom-plan',
      stages:[{stage:'extract_content'}]},{state:'captured'})""")
    live_ui.evaluate("""() => renderWorkflow({status:'awaiting_review',kind:'custom-plan',
      stages:[{stage:'extract_content'}]},{state:'captured'})""")
    assert live_ui.evaluate("flowNodes.get('interpret').ring.getAnimations().length") == 0
    live_ui.evaluate("""() => renderWorkflow({status:'running',kind:'custom-plan',
      stages:[{stage:'extract_content'}]},{state:'captured'})""")
    assert (
        live_ui.evaluate("flowNodes.get('interpret').ring.getAnimations()[0].playState")
        == "running"
    )
