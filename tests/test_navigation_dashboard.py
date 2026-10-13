"""Navigation guidance regressions; browser fixtures are isolated and opt-in."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS


def test_navigation_review_displays_actual_values_purpose_and_missing_fields():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    assert "browser.navigation_plan.guidance" in script
    assert "browser.navigation_plan.missing_fields" in script
    assert "control.purpose.replaceAll" in script
    assert "result.pending_fields" in script
    assert "result.missing_fields" in script
    assert "This session keeps its original request" in script
    assert '$("web-browser-controls").before(navigationEvidence)' in script


@pytest.fixture
def navigation_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_missing_year_evidence_tells_user_to_correct_request_not_repeat_planning(navigation_ui):
    navigation_ui.evaluate("""() => showNavigationEvidence({
      navigation_result:{status:'partial_form',submitted:false,
        actions:[{control:'Search',action:'fill',status:'value_verified',
          expected:'Boston',observed:'Boston'}],
        requirements:[],pending_fields:['check_in','check_out'],
        missing_fields:['check_in','check_out']},navigation_history:[]
    })""")
    evidence_title = navigation_ui.get_by_text("Search action evidence", exact=True)
    # Background rendering must not navigate away from the user's Source tab.
    assert evidence_title.count() == 1
    assert navigation_ui.evaluate("studioStep") == "source"
    assert not evidence_title.is_visible()
    assert navigation_ui.evaluate("""() => ({
      inWorkflow: navigationEvidence.parentElement === workPanel,
      inDisclosure: navigationEvidence.closest('details') !== null,
      technicalLogOpen: stageLog.open
    })""") == {
        "inWorkflow": True,
        "inDisclosure": False,
        "technicalLogOpen": False,
    }
    navigation_ui.get_by_role("tab", name="2. Workflow", exact=True).click()
    assert evidence_title.is_visible()
    # Guidance stays accessible even without live browser controls or an open log.
    assert not navigation_ui.locator("#web-browser-controls").is_visible()
    assert navigation_ui.evaluate("stageLog.open") is False
    assert navigation_ui.get_by_text("Still needed before search:", exact=False).is_visible()
    assert navigation_ui.get_by_text(
        "Add the missing values to your request", exact=False
    ).is_visible()
    assert navigation_ui.evaluate("window.fixtureCalls") == []


def test_known_request_values_keep_pending_form_work_in_same_session(navigation_ui):
    navigation_ui.evaluate("""() => {
      showNavigationEvidence({navigation_result:{
        status:'partial_form',submitted:false,actions:[],requirements:[],
        pending_fields:['check_in','check_out'],missing_fields:[]
      },navigation_history:[]});
      setStudioStep('work');
    }""")
    assert navigation_ui.get_by_text("Your request values are available", exact=False).is_visible()
    assert navigation_ui.get_by_text("in this same session", exact=False).is_visible()
    assert "cancel this browser" not in navigation_ui.evaluate("navigationEvidence.textContent")
    assert "missing year" not in navigation_ui.evaluate("navigationEvidence.textContent")
    assert navigation_ui.evaluate("window.fixtureCalls") == []
