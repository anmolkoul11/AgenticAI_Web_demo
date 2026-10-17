"""Readonly criterion previews and capture messages; local browser fixture only."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS


def test_ui_exposes_unresolved_criteria_without_a_savable_proposal():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    assert "showRequestConstraints(result.proposal || result)" in script
    assert "result.unverified_preview?.length" in script
    assert "criteria_unverified_preview: true" in script
    assert "This is not a matched result" in script
    assert "item.capture_diagnostics" in script


@pytest.fixture
def source_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_source_preview_shows_prices_but_cannot_be_saved_or_downloaded(source_ui):
    state = source_ui.evaluate("""async () => {
      window.fixtureApi=async () => ({job_id:'fixture',kind:'custom-plan',framework:'langgraph',
        status:'needs_input',stages:[{stage:'inspect_website'},{stage:'extract_content'},{stage:'review_content'}],
        result:{review_outcome:'constraint_unresolved',guidance:'Nightly basis unavailable',
          columns:[{name:'hotel_name',kind:'text'},{name:'price',kind:'number'},{name:'hotel_url',kind:'text'}],
          request_constraint_coverage:{issues:[{field:'price',reason:'requested_filter_not_preserved',operator:'lte',value:'350'}]},
          unverified_preview:[{listing_id:'record-0001',hotel_name:'Harbor House',price:'300',
            hotel_url:'https://example.org/hotel/harbor',source_url:'https://example.org/results',
            evidence:{hotel_name:'Harbor House',price:'US$300 for two nights',hotel_url:'https://example.org/hotel/harbor'}}],
          unverified_preview_more_available:true}});
      await customSelect('fixture');
      return {savable:canApproveWeb(),reviewHidden:$('web-review').hidden,
        downloadsHidden:$('web-downloads').hidden,count:$('web-count').textContent,
        price:previewRows[0].price,quality:previewQuality.criteria_unverified_preview};
    }""")
    assert not state["savable"] and state["reviewHidden"] and state["downloadsHidden"]
    assert state["price"] == "300" and state["quality"]
    assert "More source candidates" in state["count"]
    assert source_ui.get_by_text("Requested criteria need attention", exact=True).is_visible()
    source_ui.evaluate("setStudioStep('results'); openRecordPreview(0)")
    assert source_ui.get_by_text("This is not a matched result", exact=False).is_visible()


def test_capture_error_code_is_visible_without_opening_job_json(source_ui):
    source_ui.evaluate("""() => {
      $('web-browser-controls').hidden=false;setStudioStep('work');
      renderBrowserOptions({state:'agent_paused',workflow_mode:'automatic',automatic_start:'started',
        page_health:{},agent_report:{status:'paused',calls:1,max_calls:30,captured_pages:[],
          guidance:'Source capture failed',actions:[
            {step:1,action:'capture',status:'capture_failed',explanation:'Collect current source',
              capture_diagnostics:{code:'insufficient_content',captured_text_chars:32}}
          ]}});
      agentDetails.open=true;
    }""")
    assert source_ui.get_by_text("Capture stopped: insufficient content", exact=False).is_visible()
    assert source_ui.get_by_text("32 retained text characters", exact=False).is_visible()
