"""Authored direct-action regressions; not executed during implementation."""

import pytest

from test_dashboard_live_updates import live_ui


def test_optional_screenshot_settings_are_collapsed_until_opened(live_ui):
    assert live_ui.locator("#web-advanced").is_visible()
    assert live_ui.locator("#web-workflow-visual").is_hidden()
    assert live_ui.locator("#web-workflow-visual").input_value() == "no"
    live_ui.locator("#web-advanced > summary").click()
    assert live_ui.locator("#web-workflow-visual").is_visible()
    assert live_ui.evaluate("window.fixtureCalls") == []


@pytest.mark.parametrize("partial", [False, True])
def test_ready_preview_enables_save_without_an_additional_checkbox(live_ui, partial):
    state = live_ui.evaluate("""async partial => {
      const proposal={plan_id:'review-plan',source:'public',urls:['https://example.org/'],
        request:'Get item names',interpretation:'Visible items',columns:[
          {name:'name',kind:'text',description:'Name'}],records:[
          {listing_id:'one',name:'Sample item',source_url:'https://example.org/'}],
        warnings:[],filters:[],business_rules:[],output_fields:[],partial,publish_event:false};
      window.fixtureApi=async()=>({job:{job_id:'review-job',kind:'custom-plan',
        framework:'langgraph',status:'awaiting_review',stages:[],
        result:{proposal,revision:'review-revision'}},browser:null});
      await customSelect('review-job');clearTimeout(webTimer);
      return {enabled:!$('web-execute').disabled,ready:!!canApproveWeb(),
        label:$('web-execute').textContent,partialNote:!$('web-partial-label').hidden,
        repeatedApproval:$('web-approved')!==null,
        mutations:window.fixtureCalls.filter(path=>!path.endsWith('/workflow'))};
    }""", partial)
    assert state["enabled"] and state["ready"]
    assert state["partialNote"] is partial
    assert not state["repeatedApproval"] and state["mutations"] == []
    expected_label = "Save available results" if partial else "Save results"
    assert state["label"] == expected_label


def test_bare_programmatic_submission_does_not_start_a_paid_workflow(live_ui):
    state = live_ui.evaluate("""async()=>{
      $('web-urls').value='https://example.org/';$('web-request').value='Get item names';
      await webForm.onsubmit({preventDefault(){}});
      return {calls:window.fixtureCalls,submitting:webSubmitting};
    }""")
    assert state == {"calls": [], "submitting": False}


@pytest.mark.parametrize("partial", [False, True])
def test_save_button_scopes_partial_acceptance_to_the_displayed_preview(live_ui, partial):
    state = live_ui.evaluate("""async partial=>{
      webSelected='review-job';webProposal={plan_id:'review-plan',partial};
      webRevision='review-revision';webSubmitting=false;
      const posts=[];
      window.fixtureApi=async(path,data)=>{posts.push({path,data});return {job_id:'save-job'};};
      customSelect=async()=>{};
      const before=posts.length;
      await $('web-execute').onclick();
      const withoutAction=posts.length;
      await $('web-execute').onclick({currentTarget:$('web-execute')});
      return {before,withoutAction,posts};
    }""", partial)
    assert state["before"] == state["withoutAction"] == 0
    assert state["posts"] == [{"path": "/api/custom/plans/review-plan/execute",
                               "data": {"revision": "review-revision", "accept_partial": partial}}]


@pytest.mark.parametrize(
    "source,manual,network,images,publish",
    [
        ("browser", False, "normal", False, False),
        ("browser", False, "restricted", True, True),
        ("browser", True, "normal", True, False),
        ("public", False, "normal", False, False),
        ("paste", False, "normal", False, True),
        ("capture", False, "normal", False, False),
    ],
)
def test_explicit_start_preserves_source_mode_and_optional_permissions(
    live_ui, source, manual, network, images, publish
):
    result = live_ui.evaluate("""async setting => {
      $('web-source').value=setting.source;$('web-source').onchange();
      if(setting.source==='browser'){
        $('web-manual-mode').checked=setting.manual;$('web-manual-mode').onchange();
        $('web-browser-mode').value=setting.network;$('web-browser-mode').onchange();
      }
      $('web-urls').value='https://example.org/items';
      $('web-request').value='Collect visible item names and source links';
      $('web-text').value='Sample item and its locally supplied description.';
      $('web-workflow-visual').value=setting.images?'yes':'no';
      $('web-publish').value=setting.publish?'yes':'no';
      if(setting.source==='capture'){
        webCapture={url:'https://example.org/captured',
          text:'Sample captured item',links:[],blocks:[]};
        updateSourceInputs();
      }
      const posts=[];
      window.fixtureApi=async(path,data)=>{
        posts.push({path,data:structuredClone(data)});return {job_id:'new-job'};
      };
      customSelect=async()=>{};
      await webForm.onsubmit({preventDefault(){},submitter:$('web-create')});
      return posts;
    }""", {"source": source, "manual": manual, "network": network,
            "images": images, "publish": publish})
    assert len(result) == 1
    assert result[0]["path"] == "/api/custom/plans"
    payload = result[0]["data"]
    assert payload["source"] == source
    assert payload["authorized"] and payload["allow_model_api"]
    assert payload["publish_event"] is publish
    if source == "browser":
        assert payload["workflow_mode"] == ("manual" if manual else "automatic")
        assert payload["agent_confirmed"] is (not manual)
        assert payload["agent_visual_confirmed"] is (images and not manual)
        assert payload["browser_mode"] == network
        assert payload["normal_browser_confirmed"] is (network == "normal")
    else:
        assert "agent_confirmed" not in payload
        assert "normal_browser_confirmed" not in payload
    if source == "capture":
        assert payload["urls"] == ["https://example.org/captured"]
        assert payload["capture"]["text"] == "Sample captured item"
    if source == "paste":
        assert payload["page_text"] == "Sample item and its locally supplied description."


def test_settings_changes_and_an_unrelated_submitter_cannot_start_work(live_ui):
    state = live_ui.evaluate("""async()=>{
      $('web-source').value='browser';$('web-source').onchange();
      $('web-browser-mode').value='restricted';$('web-browser-mode').onchange();
      $('web-workflow-visual').value='yes';
      await webForm.onsubmit({preventDefault(){},submitter:$('web-download')});
      return {calls:window.fixtureCalls,submitting:webSubmitting};
    }""")
    assert state == {"calls": [], "submitting": False}


def test_repeated_start_keeps_one_request_with_the_original_task(live_ui):
    state = live_ui.evaluate("""async()=>{
      $('web-urls').value='https://example.org/original';
      $('web-request').value='Collect the original item list';
      let finish;const posts=[],selected=[];
      window.fixtureApi=(path,data)=>{
        posts.push({path,data:structuredClone(data)});
        return new Promise(resolve=>{finish=resolve;});
      };
      customSelect=async id=>selected.push(id);
      const first=webForm.onsubmit({preventDefault(){},submitter:$('web-create')});
      const busy=webSubmitting;
      $('web-urls').value='https://example.org/changed';
      $('web-request').value='A different task';
      await webForm.onsubmit({preventDefault(){},submitter:$('web-create')});
      finish({job_id:'original-job'});await first;
      return {busy,posts,selected};
    }""")
    assert state["busy"] is True
    assert len(state["posts"]) == 1
    assert state["posts"][0]["data"]["urls"] == ["https://example.org/original"]
    assert state["posts"][0]["data"]["instructions"] == "Collect the original item list"
    assert state["selected"] == ["original-job"]


@pytest.mark.parametrize("images", [False, True])
def test_resume_sends_images_only_when_selected_and_does_not_restart_on_render(live_ui, images):
    result = live_ui.evaluate("""async images=>{
      webSelected='paused-job';$('web-browser-controls').hidden=false;setStudioStep('work');
      renderBrowserOptions({state:'agent_paused',page_health:{},agent_report:{
        status:'paused',calls:3,max_calls:30,actions:[],captured_pages:[],guidance:'Continue'}});
      const before=window.fixtureCalls.length;
      agentVisualSelect.value=images?'yes':'no';
      const posts=[];
      window.fixtureApi=async(path,data)=>{posts.push({path,data:structuredClone(data)});return {};};
      await agentResume.onclick({currentTarget:agentResume});
      return {before,posts,imagesAfter:agentVisualSelect.value};
    }""", images)
    assert result["before"] == 0
    assert result["posts"] == [{"path": "/api/custom/jobs/paused-job/browser/agent_resume",
                                "data": {"selected_ids": [], "agent_confirmed": True,
                                         "agent_visual_confirmed": images}}]
    assert result["imagesAfter"] == "no"
