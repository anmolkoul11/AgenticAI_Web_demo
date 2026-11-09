"""Source-only coverage for portal transition policies, not selector recipes."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_task import TaskLedger, site_search_behavior
from test_observed_stay_results import REQUEST, action, open_guest_widget, results_page


def portal_page(host, **options):
    page = results_page(**options)
    page["url"] = f"https://{host}/hotels"
    return page


@pytest.mark.parametrize("url,site,mode", [
    ("https://www.booking.com/", "booking.com", "explicit_submit"),
    ("https://secure.booking.com/", "booking.com", "explicit_submit"),
    ("https://www.tripadvisor.com/Hotels", "tripadvisor.com", "live_update"),
    ("https://booking.com.example.org/", "booking.com.example.org", "observed"),
    ("https://fakebooking.com/", "fakebooking.com", "observed"),
    ("https://tripadvisor.com@example.org/", "example.org", "observed"),
])
def test_site_identity_matches_host_boundaries(url, site, mode):
    behavior = site_search_behavior(url, stay_request=True)
    assert behavior["site"] == site and behavior["search_mode"] == mode


def test_booking_keeps_initial_already_applied_result_url_reuse():
    task, page = TaskLedger(REQUEST), portal_page("www.booking.com", applied_url=True)
    task.observe(page)
    assert task.adopt_matching_results(page)
    assert task.snapshot()["matching_results_observed"]
    assert not task.snapshot()["search_submitted"]


def test_booking_form_edit_requires_search_even_if_old_url_and_form_now_match():
    task, page = TaskLedger(REQUEST), portal_page("www.booking.com", applied_url=True)
    task.observe(page)
    field = page["frames"][0]["controls"][1]
    task.before_action(field, SimpleNamespace(action="fill", value="2026-10-29"), page)
    task.observe(page)
    assert not task.adopt_matching_results(page)
    assert task.result_handoff["reason"] == "search_submit_required"
    assert task.submission is None


@pytest.mark.parametrize("host,expected", [("www.booking.com", False), ("www.tripadvisor.com", True), ("example.org", True)])
def test_matching_live_refresh_is_portal_specific(host, expected):
    task, before = TaskLedger(REQUEST), portal_page(host)
    update = open_guest_widget(before)
    task.observe(before)
    task.remember_action(update, {"status": "action_performed"}, action("click", update), before)
    after = portal_page(host, signature="22222222")
    task.observe(after)
    assert task.adopt_matching_results(after) is expected
    assert task.snapshot()["site_behavior"]["search_mode"] == site_search_behavior(after["url"], stay_request=True)["search_mode"]


def test_booking_actual_confirmed_search_is_not_replaced_by_adoption_policy():
    task, before = TaskLedger(REQUEST), portal_page("www.booking.com")
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    after = portal_page("www.booking.com", signature="22222222")
    task.observe(after)
    assert task.snapshot()["search_submitted"]
    previous = deepcopy(task.submission)
    assert not task.adopt_matching_results(after)
    assert task.submission == previous and task.pending_submission is None


@pytest.mark.parametrize("host", ["www.nytimes.com", "www.bbc.com", "www.booking.com"])
def test_nonhotel_collection_keeps_observed_goal_behavior(host):
    task = TaskLedger("Get all articles about sports on the current page")
    page = portal_page(host)
    task.observe(page)
    assert not task.requested_stay
    assert task.snapshot()["site_behavior"]["search_mode"] == "observed"
