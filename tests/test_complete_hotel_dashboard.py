"""Complete-search dashboard contract and isolated opt-in UI regressions."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS, BrowserAction
from agentic_web_demo.hotel_search import prepare_hotel_search

REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 3 adults, 2 rooms, priced from 250-350 USD per night."
)
REVISION = "a" * 32


def test_complete_search_is_separate_from_paid_single_step_planning():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    assert "Prepare complete hotel search · no API call" in script
    assert "Approve & run search only" in script
    assert "Approve, search & extract · paid API" in script
    assert "hotel_revision: hotelReviewedRevision" in script
    assert "hotel_confirmed: hotelCheckbox.checked" in script
    assert "hotelApprovalState" in script
    assert "hotel_plan" in script and "web-plan-navigation" in script
    assert BrowserAction(hotel_revision=REVISION, hotel_confirmed=True).hotel_confirmed


@pytest.fixture
def hotel_ui(request):
    yield from shared_ui.__wrapped__(request)


def review(ui, *, revision=REVISION):
    ui.evaluate(
        """data => {
          $('web-request').value=data.request;
          $('web-browser-controls').hidden=false;
          setStudioStep('work');
          renderBrowserOptions({state:'hotel_review',hotel_plan:data.plan,
            hotel_revision:data.revision,page_health:{}});
        }""",
        {
            "request": REQUEST,
            "plan": prepare_hotel_search(REQUEST).model_dump(),
            "revision": revision,
        },
    )


def test_goal_review_is_explicit_and_stable_polling_preserves_confirmation(hotel_ui):
    review(hotel_ui)
    run = hotel_ui.locator("#web-hotel-approve")
    assert run.is_visible() and run.is_disabled()
    assert hotel_ui.get_by_text("check in: 2026-10-28", exact=False).is_visible()
    checkbox = hotel_ui.get_by_role("checkbox", name="I reviewed these targets", exact=False)
    checkbox.check()
    assert run.is_enabled()
    review(hotel_ui)
    assert checkbox.is_checked() and run.is_enabled()
    review(hotel_ui, revision="b" * 32)
    assert not checkbox.is_checked() and run.is_disabled()
    assert hotel_ui.evaluate("window.fixtureCalls") == []


@pytest.mark.parametrize("action", ["hotel_approve", "hotel_extract"])
def test_goal_approval_sends_exact_review_and_separate_capture_choice(hotel_ui, action):
    review(hotel_ui)
    hotel_ui.get_by_role("checkbox", name="I reviewed these targets", exact=False).check()
    payload = hotel_ui.evaluate(
        """action => {
          webSelected='fixture-job';
          window.fixtureApi=async (path,data) => {window.approvalPayload={path,data};return {};};
          const button=action==='hotel_extract'?hotelExtract:hotelRun;
          return button.onclick().then(()=>window.approvalPayload);
        }""",
        action,
    )
    assert payload == {
        "path": f"/api/custom/jobs/fixture-job/browser/{action}",
        "data": {"selected_ids": [], "hotel_revision": REVISION, "hotel_confirmed": True},
    }


def test_goal_review_is_waiting_and_execution_reports_actual_stage(hotel_ui):
    result = hotel_ui.evaluate("""() => {
      const job={status:'running',kind:'custom-plan',stages:[{stage:'inspect_website'}]};
      const waiting=workflowActivity(job,{state:'hotel_review'});
      renderWorkflow(job,{state:'hotel_running',guidance:'Hotel search: occupancy.'});
      const node=flowNodes.get('browse');
      return {waiting:waiting.waiting,running:waiting.running,
        activity:flowActivityText.textContent,motion:node.ring.getAnimations().length};
    }""")
    assert result["waiting"] and not result["running"]
    assert "occupancy" in result["activity"]
    assert result["motion"] == 1
