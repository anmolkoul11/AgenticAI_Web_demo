"""Source-only fixtures for independent returned stay scope; no live website."""

from datetime import date

from agentic_web_demo.browser_context import build_navigation_context
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.stay_scope import (
    observed_result_scope,
    requested_stay,
    url_stay_values,
)

REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms, around 250-350 USD nightly."
)


def returned(document="results", *, catalog=False, full_dates=True, controls=True):
    items = [
        {"id": "0:0", "tag": "INPUT", "type": "text", "name": "destination",
         "label": "Destination", "value": "New York", "form_scope": "0:form:1"},
        {"id": "0:1", "tag": "INPUT", "type": "date", "label": "Check-in",
         "value": "2026-10-28" if full_dates else "", "form_scope": "0:form:1"},
        {"id": "0:2", "tag": "INPUT", "type": "date", "label": "Check-out",
         "value": "2026-10-30" if full_dates else "", "form_scope": "0:form:1"},
        {"id": "0:3", "tag": "BUTTON", "type": "button",
         "label": "4 adults · 0 children · 2 rooms", "form_scope": "0:form:1"},
        {"id": "0:4", "tag": "BUTTON", "type": "submit", "label": "Search",
         "submits_form": True, "form_scope": "0:form:1"},
    ] if controls else []
    return {
        "url": "https://example.org/" + document,
        "document_id": document,
        "frames": [{"text": "Available accommodation records for the destination.",
                    "controls": items}],
        "results": {"record_count": 4, "busy": False, "no_results": False,
                    "price_contexts": ["Price from $419 · 1 night, 2 adults"] if catalog else []},
    }


def test_requested_stay_uses_exact_dates_not_contradictory_night_prose():
    stay = requested_stay(REQUEST.replace("around", "for 9 nights, around"))
    assert stay == {
        "destination": "New York", "check_in": "2026-10-28", "check_out": "2026-10-30",
        "adults": 4, "rooms": 2, "nights": 2,
    }


def test_request_default_year_is_not_a_source_default():
    request = "Find hotels in New York from October 28-30 for 4 adults and 2 rooms."
    stay = requested_stay(request, date(2026, 10, 14))
    page = returned(full_dates=False)
    page["frames"][0]["controls"].append({
        "tag": "BUTTON", "label": "Select dates Oct 28 — Oct 30", "text": "Oct 28 — Oct 30",
    })
    scope = observed_result_scope(stay, page)
    assert stay["nights"] == 2
    assert scope["status"] == "unverified"
    assert scope["observed"]["check_in"] is None
    assert scope["observed"]["check_out"] is None


def test_matching_fresh_returned_context_is_separate_from_availability():
    scope = observed_result_scope(requested_stay(REQUEST), returned())
    assert scope["status"] == "verified"
    assert all(item["status"] == "verified" for item in scope["fields"])
    assert scope["availability_verified"] is False
    assert scope["source"] == "returned_page"


def test_canonical_returned_city_keeps_its_region_without_a_false_mismatch():
    page = returned()
    page["frames"][0]["controls"][0]["value"] = "New York, New York, United States of America"
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "verified"
    assert scope["observed"]["destination"] == "New York, New York, United States of America"


def test_structured_results_heading_verifies_missing_destination_control():
    page = returned()
    page["frames"][0]["controls"] = page["frames"][0]["controls"][1:]
    page["results"]["headings"] = [{"text": "New York: 373 properties found", "level": 1}]
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "verified"
    destination = next(item for item in scope["fields"] if item["field"] == "destination")
    assert destination["method"] == "returned_results_heading"
    assert destination["observed"] == "New York"
    assert destination["evidence"] == "New York: 373 properties found"
    assert scope["availability_verified"] is False


def test_equivalent_heading_and_regional_control_agree():
    page = returned()
    page["frames"][0]["controls"][0]["value"] = "New York, New York, United States"
    page["results"]["headings"] = [{"text": "373 hotels available in New York", "level": 2}]
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "verified"
    assert "returned_results_heading" in scope["fields"][0]["method"]


def test_conflicting_result_heading_does_not_trust_matching_form_control():
    page = returned()
    page["results"]["headings"] = [{"text": "Boston: 373 properties found", "level": 1}]
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "mismatch"
    assert scope["fields"][0]["status"] == "mismatch"
    assert scope["observed"]["destination"] == "boston; new york"


def test_conflicting_structured_headings_do_not_pick_the_requested_one():
    page = returned()
    page["frames"][0]["controls"] = page["frames"][0]["controls"][1:]
    page["results"]["headings"] = [
        {"text": "New York: 373 properties found", "level": 1},
        {"text": "Boston: 42 hotels found", "level": 2},
    ]
    assert observed_result_scope(requested_stay(REQUEST), page)["status"] == "mismatch"


def test_body_card_and_frame_headings_do_not_manufacture_destination_scope():
    page = returned()
    page["frames"][0]["controls"] = page["frames"][0]["controls"][1:]
    page["frames"][0]["text"] = "New York: 373 properties found"
    page["frames"].append({"results": {"headings": [
        {"text": "New York: 373 properties found", "level": 1},
    ]}})
    page["results"]["headings"] = [
        {"text": "New York: 373 properties found", "level": 3},
        {"text": "Find hotels in New York for 4 adults", "level": 1},
        {"text": "Hotels in New York", "level": 1},
    ]
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "unverified"
    assert scope["observed"]["destination"] is None


def test_result_heading_only_establishes_destination_not_dates_or_occupancy():
    page = returned(controls=False)
    page["results"]["headings"] = [{"text": "New York — 1,234 hotels found", "level": 1}]
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "unverified"
    assert scope["fields"][0]["status"] == "verified"
    assert all(item["status"] == "unverified" for item in scope["fields"][1:])


def test_similarly_named_returned_place_does_not_verify_the_requested_city():
    for value in ("Central New York City", "New York-New York, Las Vegas, United States"):
        page = returned()
        page["frames"][0]["controls"][0]["value"] = value
        assert observed_result_scope(requested_stay(REQUEST), page)["status"] == "mismatch"


def test_catalog_card_contradictions_override_matching_form():
    scope = observed_result_scope(requested_stay(REQUEST), returned(catalog=True))
    assert scope["status"] == "mismatch"
    assert all(item["status"] == "verified" for item in scope["fields"])
    assert {item["code"] for item in scope["contradictions"]} == {
        "catalog_starting_price", "price_context_occupancy_mismatch",
        "price_context_nights_mismatch",
    }


def test_allowlisted_url_projection_retains_only_full_dates_and_counts():
    values = url_stay_values(
        "https://example.org/search?checkin=2026-10-28&checkout=2026-10-30"
        "&group_adults=4&no_rooms=2&token=SECRET&email=hidden@example.org&q=private"
    )
    assert values == {
        "check_in": ["2026-10-28"], "check_out": ["2026-10-30"],
        "adults": [4], "rooms": [2],
    }
    assert "SECRET" not in str(values)
    assert url_stay_values("https://example.org/?checkin=Oct28&adults=secret") == {}


def test_url_projection_and_fresh_destination_can_verify_returned_scope():
    page = returned(full_dates=False)
    page["stay_url_values"] = url_stay_values(
        "https://example.org/results?check_in=2026-10-28&check_out=2026-10-30&adults=4&rooms=2"
    )
    assert observed_result_scope(requested_stay(REQUEST), page)["status"] == "verified"


def test_conflicting_url_values_do_not_count_as_exact_request():
    page = returned()
    page["stay_url_values"] = {"adults": [4, 2]}
    scope = observed_result_scope(requested_stay(REQUEST), page)
    assert scope["status"] == "mismatch"
    assert next(item for item in scope["fields"] if item["field"] == "adults")["status"] == "mismatch"


def test_unselected_calendar_day_does_not_verify_stay():
    page = returned(full_dates=False)
    page["frames"][0]["controls"] += [
        {"tag": "SPAN", "role": "gridcell", "date": "2026-10-28",
         "label": "Wednesday, October 28, 2026", "selected": "false"},
        {"tag": "SPAN", "role": "checkbox", "date": "2026-10-30",
         "label": "Friday, October 30, 2026", "selected": "false"},
    ]
    assert observed_result_scope(requested_stay(REQUEST), page)["status"] == "unverified"


def test_selected_full_date_requires_endpoint_state():
    page = returned(full_dates=False)
    page["frames"][0]["controls"] += [
        {"tag": "SPAN", "role": "checkbox", "date": "2026-10-28",
         "label": "Wednesday, October 28, 2026, Check-in date", "selected": "true"},
        {"tag": "SPAN", "role": "checkbox", "date": "2026-10-30",
         "label": "Friday, October 30, 2026, Check-out date", "selected": "true"},
    ]
    assert observed_result_scope(requested_stay(REQUEST), page)["status"] == "verified"


def test_pre_submit_fallback_and_old_calendar_choices_do_not_verify_results():
    task = TaskLedger(REQUEST)
    before = returned("form")
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    after = returned("unscoped", controls=False)
    task.observe(after)
    task.date_choices = {"2026-10-28": "Previously selected", "2026-10-30": "Previously selected"}
    task.observe(after)
    assert task.submission
    assert all(item["status"] == "verified" for item in task.checks)
    assert task.snapshot()["result_scope"]["status"] == "unverified"
    context = task.capture_context(after)
    assert context["source_preview_only"] is True
    assert context["requested_stay_verified"] is False
    assert context["result_scope"]["observed"]["check_in"] is None


def test_pre_submit_results_heading_is_not_reused_on_another_document():
    task = TaskLedger(REQUEST)
    before = returned("form")
    before["results"]["headings"] = [{"text": "New York: 373 properties found", "level": 1}]
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    after = returned("unscoped", controls=False)
    task.observe(after)
    scope = task.snapshot()["result_scope"]
    assert scope["status"] == "unverified"
    assert scope["observed"]["destination"] is None


def test_new_catalog_can_prepare_only_one_fresh_form_search():
    task = TaskLedger(REQUEST)
    before = returned("form")
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    first_catalog = returned("catalog-one", catalog=True)
    task.observe(first_catalog)
    assert task.submission is None
    assert task.catalog_followup_used
    assert task.snapshot()["search_submitted"] is False
    assert len(task.submission_candidates) == 1
    assert task.begin_submission(first_catalog, first_catalog["url"])
    second_catalog = returned("catalog-two", catalog=True)
    task.observe(second_catalog)
    assert task.submission
    assert task.source_preview_ready()
    assert task.submission_candidates == []


def test_same_document_catalog_does_not_authorize_a_repeat_search():
    task = TaskLedger(REQUEST)
    before = returned("same-document")
    before["frames"][0]["text"] = "Prepared destination and requested stay form."
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    after = returned("same-document", catalog=True)
    after["frames"][0]["text"] = "Different catalog content containing many starting-price cards."
    task.observe(after)
    assert task.submission
    assert not task.catalog_followup_used
    assert task.source_preview_ready()
    assert task.submission_candidates == []


def test_nonstay_tasks_have_no_manufactured_scope():
    assert requested_stay("Find relevant soccer headlines on this page.") == {}
    assert observed_result_scope({}, returned())["status"] == "not_requested"


def test_initial_none_result_scope_can_build_navigation_context():
    task = TaskLedger(REQUEST)
    page = returned("form")
    checklist = task.observe(page)
    assert checklist["result_scope"] is None
    context = build_navigation_context({
        "task": REQUEST, "task_checklist": checklist, "observation": page,
    })
    assert "result_scope" not in context["task_checklist"]
    assert context["interaction_focus"]["phase"] == "submit_search"
