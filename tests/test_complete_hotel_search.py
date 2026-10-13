"""Goal-reviewed search regressions; browser fixtures are local and opt-in."""

import copy
from dataclasses import FrozenInstanceError
from datetime import date
from types import SimpleNamespace

import pytest
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.hotel_search import (
    MAX_ACTIONS,
    HotelSearchDriver,
    prepare_hotel_search,
    run_hotel_search,
)

REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30, "
    "for 3 adults, 2 rooms, priced from 250-350 USD per night. Do not reserve or pay."
)


@pytest.mark.parametrize(
    "instructions",
    [
        REQUEST,
        "Give me hotels in New York with price ranging from 250-350 USD per night, "
        "with checking in and checking out date as 28-30 October 2026 for 3 adults, 2 rooms",
        "GET HOTELS IN NEW YORK WITH CHECK IN AND CHECK OUT DATE FROM OCTOBER 28-30, "
        "2026 WITH 3 ADULTS AND 2 ROOMS, PRICE RANGE 250-350 USD.",
    ],
)
def test_complete_hotel_request_preserves_explicit_values(instructions):
    recipe = prepare_hotel_search(instructions)
    assert recipe.destination.casefold() == "new york"
    assert (recipe.check_in, recipe.check_out) == ("2026-10-28", "2026-10-30")
    assert (recipe.adults, recipe.rooms) == (3, 2)
    assert recipe.children is None
    assert recipe.model_dump()["planning_api_calls"] == 0
    assert [row["application"] for row in recipe.requirements()] == ["site"] * 4 + [
        "extraction"
    ] * 2
    with pytest.raises(FrozenInstanceError):
        recipe.adults = 4


@pytest.mark.parametrize(
    "instructions",
    [
        REQUEST.replace("2026-10-28 and check-out 2026-10-30", "January 2-4"),
        REQUEST.replace("3 adults, 2 rooms", "3 adults"),
        REQUEST.replace("3 adults, 2 rooms", "2 rooms"),
        REQUEST.replace("3 adults, 2 rooms", "3 adults, 2 rooms and 1 child"),
        REQUEST.replace("3 adults, 2 rooms", "3 adults, 4 adults, 2 rooms"),
        REQUEST.replace("2026-10-30", "2026-10-28"),
    ],
)
def test_incomplete_or_unsupported_request_runs_no_form_actions(instructions):
    with pytest.raises(WebsiteError):
        prepare_hotel_search(instructions, reference_date=date(2026, 10, 10))


def test_complete_search_shares_disclosed_future_current_year_default():
    request_text = REQUEST.replace("2026-10-28 and check-out 2026-10-30", "October 28-30")
    recipe = prepare_hotel_search(request_text, reference_date=date(2026, 10, 10))
    assert (recipe.check_in, recipe.check_out) == ("2026-10-28", "2026-10-30")
    assert recipe.model_dump()["date_resolution"]["year"] == 2026


def reviewed_control():
    control = BrowserControl()
    control.update("waiting", "Ready")
    control.command("hotel_plan")
    assert control.hotel_requested.is_set()
    control.set_hotel_plan(prepare_hotel_search(REQUEST), "https://example.org/")
    return control


@pytest.mark.parametrize("action", ["hotel_approve", "hotel_extract"])
def test_hotel_execution_requires_current_review_and_confirmation(action):
    control = reviewed_control()
    revision = control.snapshot()["hotel_revision"]
    for kwargs in ({}, {"hotel_revision": revision}, {"hotel_confirmed": True}):
        with pytest.raises(WebsiteError, match="Confirm"):
            control.command(action, **kwargs)
        assert not control.hotel_approved.is_set()
    control.command(action, hotel_revision=revision, hotel_confirmed=True)
    assert control.state == "hotel_running"
    assert control.hotel_approved.is_set()
    assert control.hotel_capture_after == (action == "hotel_extract")
    assert not control.capture.is_set()


def test_stale_review_cannot_approve_changed_targets():
    control = reviewed_control()
    revision = control.hotel_revision
    control.set_hotel_plan(prepare_hotel_search(REQUEST), "https://example.org/")
    with pytest.raises(WebsiteError, match="Confirm"):
        control.command("hotel_extract", hotel_revision=revision, hotel_confirmed=True)


@pytest.mark.parametrize("action", ["hotel_dismiss", "authentication"])
def test_dismiss_or_mfa_invalidates_goal_and_never_captures(action):
    control = reviewed_control()
    if action == "authentication":
        control.require_authentication("Finish sign-in")
    else:
        control.command(action)
    assert control.hotel_plan is None and control.hotel_revision is None
    assert not control.hotel_capture_after
    assert not control.capture.is_set() and not control.hotel_approved.is_set()


class FixtureDriver:
    approved_origin = "https://example.org"
    actions = 0

    def __init__(self, *, wrong=None):
        self.called, self.wrong = [], wrong

    def destination(self, value):
        self.called.append("destination")
        return "Boston" if self.wrong == "destination" else value

    def dates(self, check_in, check_out):
        self.called.append("dates")
        return {
            "check_in": "2027-10-28" if self.wrong == "dates" else check_in,
            "check_out": check_out,
        }

    def occupancy(self, adults, rooms, children):
        self.called.append("occupancy")
        return {"adults": 2 if self.wrong == "occupancy" else adults, "rooms": rooms}

    def submit(self, recipe, *, on_submission):
        self.called.append("submit")
        if self.wrong == "preflight":
            raise WebsiteError("Changed form")
        on_submission("attempted")
        if self.wrong == "click":
            raise WebsiteError("Click timed out; inspect tab")
        on_submission("submitted")
        return {"record_elements": 0 if self.wrong == "results" else 5}


def test_goal_runs_all_stages_and_does_not_claim_result_filter_verification():
    driver, stages = FixtureDriver(), []
    report = run_hotel_search(
        driver, prepare_hotel_search(REQUEST), on_progress=lambda r: stages.append(copy.deepcopy(r))
    )
    assert driver.called == ["destination", "dates", "occupancy", "submit"]
    assert report["status"] == "search_completed"
    assert report["submitted"] and not report["results_verified"]
    assert report["planning_api_calls"] == 0
    assert report["pending_fields"] == []
    assert {r["stage"] for r in stages} == {
        "destination",
        "dates",
        "occupancy",
        "submit",
        "results",
    }
    assert [r["status"] for r in report["requirements"]][-2:] == ["deferred_to_extraction"] * 2


@pytest.mark.parametrize(
    "wrong", ["destination", "dates", "occupancy", "preflight", "click", "results"]
)
def test_mismatches_and_failed_submission_preserve_honest_progress(wrong):
    driver = FixtureDriver(wrong=wrong)
    with pytest.raises(WebsiteError) as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    report = caught.value.navigation_result
    assert report["status"] == "needs_review"
    assert report["submission_attempted"] == (wrong in {"click", "results"})
    assert report["submitted"] == (wrong == "results")
    assert not report["results_verified"]
    if wrong in {"destination", "dates", "occupancy"}:
        assert "submit" not in driver.called


def test_cancel_and_action_budget_stop_before_a_browser_action():
    page = SimpleNamespace(url="https://example.org/")
    driver = HotelSearchDriver(page, "https://example.org", permitted=lambda: False)
    with pytest.raises(WebsiteError, match="cancelled"):
        driver.inventory()
    driver = HotelSearchDriver(page, "https://example.org")
    driver.actions = MAX_ACTIONS
    with pytest.raises(WebsiteError, match="action limit"):
        driver.dismiss(lambda _: True)


def test_yearless_summary_cannot_create_full_date_readback():
    driver = HotelSearchDriver(SimpleNamespace(url="https://example.org/"), "https://example.org")
    state = {
        "fields": [],
        "days": [],
        "openers": [{"purpose": "dates", "text": "Select dates: Oct 28 — Oct 30"}],
    }
    assert driver.cached_dates(state) == {}
    verified = {"check_in": "2026-10-28", "check_out": "2026-10-30"}
    driver.date_cache = (verified, driver.date_summary(state))
    assert driver.cached_dates(state) == verified
    state["openers"][0]["text"] = "Select dates: Oct 29 — Oct 30"
    assert driver.cached_dates(state) == {}


def test_conflicting_native_dates_do_not_override_selected_calendar_dates():
    with pytest.raises(WebsiteError, match="conflict"):
        HotelSearchDriver.read_dates(
            {
                "fields": [{"key": "check_in", "value": "2027-10-28"}],
                "days": [{"date": "2026-10-28", "selected": True}],
            }
        )


@pytest.fixture
def hotel_page(request):
    yield from shared_local_page.__wrapped__(request)


def test_native_form_complete_search_and_listing_observation(hotel_page):
    hotel_page.set_content("""
      <form onsubmit="event.preventDefault();document.querySelector('main').innerHTML=
        '<div data-listing-id=hotel1>New York hotel USD 300</div>'">
        <label>Destination<input name=destination></label>
        <label>Check-in<input name=check_in type=date></label>
        <label>Check-out<input name=check_out type=date></label>
        <label>Adults<input name=group_adults type=number value=2></label>
        <label>Rooms<input name=no_rooms type=number value=1></label>
        <button>Search</button>
      </form><main></main>
    """)
    report = run_hotel_search(
        HotelSearchDriver(hotel_page, "https://example.org"), prepare_hotel_search(REQUEST)
    )
    assert report["status"] == "search_completed"
    assert report["result_observation"]["record_elements"] == 1
    assert hotel_page.locator('[name="check_in"]').input_value() == "2026-10-28"
    assert hotel_page.locator('[name="group_adults"]').input_value() == "3"
    assert hotel_page.locator('[name="no_rooms"]').input_value() == "2"


DYNAMIC_FORM = """
<form onsubmit="event.preventDefault();document.querySelector('main').innerHTML=
  '<div data-testid=property-card>New York hotel USD 300</div>'">
  <input name=ss placeholder="Enter destination" oninput="options.hidden=false">
  <input name=dest_id type=hidden>
  <ul id=options hidden><li role=option onclick="selectCity(this)">
    <strong>New York</strong><span>United States</span></li></ul>
  <button type=button id=dateOpen onclick="calendar.hidden=false">Select dates</button>
  <div id=calendar class=calendar hidden>
    <button type=button data-date=2026-10-28 aria-checked=false
      onclick="chooseDay(this)">28</button>
    <button type=button data-date=2026-10-30 aria-checked=false
      onclick="chooseDay(this)">30</button>
  </div>
  <button type=button id=guestOpen onclick="occupancy.hidden=false">
    Number of travelers and rooms. 2 adults · 0 children · 1 room</button>
  <div id=occupancy role=dialog hidden>
    <div>Adults <button type=button aria-label="Decrease adults"
      onclick="change(this,-1)">−</button>
      <span>2</span><button type=button aria-label="Increase adults"
      onclick="change(this,1)">+</button>
    </div>
    <div>Rooms <button type=button aria-label="Decrease rooms" onclick="change(this,-1)">−</button>
      <span>1</span><button type=button aria-label="Increase rooms"
      onclick="change(this,1)">+</button>
    </div>
  </div>
  <button>Search</button>
</form><main></main>
<script>
function selectCity(e) {
  document.querySelector('[name=ss]').value='New York';
  document.querySelector('[name=dest_id]').value='nyc';options.hidden=true;
}
function chooseDay(e) {
  e.setAttribute('aria-checked','true');
  dateOpen.textContent='Select dates: Oct 28 — Oct 30';
}
function change(e,n) {
  const s=e.parentElement.querySelector('span');s.textContent=+s.textContent+n;
}
document.addEventListener('keydown', e=>{
  if(e.key==='Escape') {
    calendar.hidden=true;occupancy.hidden=true;
    const counts=[...occupancy.querySelectorAll('span')].map(s=>s.textContent);
    guestOpen.textContent=`Number of travelers and rooms. ${counts[0]} adults · `+
      `0 children · ${counts[1]} rooms`;
  }
});
</script>
"""


def test_dynamic_suggestions_calendar_and_counters_complete_in_one_goal(hotel_page):
    hotel_page.set_content(DYNAMIC_FORM)
    driver = HotelSearchDriver(hotel_page, "https://example.org")
    # Exercise Booking's destination-selection requirement on an isolated local fixture.
    driver.booking = True
    report = run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert report["status"] == "search_completed"
    assert driver.date_cache[0] == {"check_in": "2026-10-28", "check_out": "2026-10-30"}
    assert hotel_page.locator("#guestOpen").inner_text().endswith("3 adults · 0 children · 2 rooms")
    assert hotel_page.locator('[data-testid="property-card"]').count() == 1


def test_calendar_moves_month_before_selecting_explicit_dates(hotel_page):
    markup = DYNAMIC_FORM.replace("data-date=2026-10-", "data-date=2026-09-")
    markup = markup.replace(
        "<div id=calendar class=calendar hidden>",
        """
      <div id=calendar class=calendar hidden>
        <button type=button aria-label="Next month" onclick="
          this.parentElement.querySelectorAll('[data-date]').forEach(e=>
            e.dataset.date=e.dataset.date.replace('2026-09','2026-10'))">Next month</button>
    """,
    )
    hotel_page.set_content(markup)
    driver = HotelSearchDriver(hotel_page, "https://example.org")
    driver.booking = True
    report = run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert report["status"] == "search_completed"
    assert driver.date_cache[0]["check_in"] == "2026-10-28"


def test_calendar_aria_full_dates_are_recognized_but_yearless_labels_are_not(hotel_page):
    hotel_page.set_content("""
      <div class=calendar>
        <button aria-label="28 October 2026" aria-selected=true>28</button>
        <button aria-label="October 30, 2026" aria-selected=true>30</button>
        <button aria-label="October 31">31</button>
      </div>
    """)
    state = HotelSearchDriver(hotel_page, "https://example.org").inventory()
    assert [row["date"] for row in state["days"]] == ["2026-10-28", "2026-10-30"]


def test_ambiguous_destination_stops_before_dates_or_submission(hotel_page):
    hotel_page.set_content(DYNAMIC_FORM)
    hotel_page.evaluate("options.append(options.firstElementChild.cloneNode(true))")
    driver = HotelSearchDriver(hotel_page, "https://example.org")
    driver.booking = True
    with pytest.raises(WebsiteError, match="ambiguous") as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert caught.value.navigation_result["stage"] == "destination"
    assert not caught.value.navigation_result["submitted"]
    assert hotel_page.locator("#calendar").is_hidden()


def test_unexpected_counter_increment_stops_before_search(hotel_page):
    hotel_page.set_content(DYNAMIC_FORM.replace("change(this,1)", "change(this,2)"))
    driver = HotelSearchDriver(hotel_page, "https://example.org")
    driver.booking = True
    with pytest.raises(WebsiteError, match="changed unexpectedly") as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert not caught.value.navigation_result["submitted"]
    assert hotel_page.locator('[data-testid="property-card"]').count() == 0


def test_natural_language_box_is_not_a_structured_destination(hotel_page):
    hotel_page.set_content(
        '<form><input name=ss placeholder="Search in your own words"><button>Search</button></form>'
    )
    driver = HotelSearchDriver(hotel_page, "https://example.org")
    assert driver.inventory()["destination"] is None
    with pytest.raises(WebsiteError, match="standard destination"):
        driver.destination("New York")
    assert hotel_page.locator("input").input_value() == ""
