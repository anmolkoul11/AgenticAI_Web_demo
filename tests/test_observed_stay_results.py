"""Applied same-page stays need fresh results, not a fabricated Search click."""

import copy
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.stay_scope import observed_calendar_endpoints, observed_result_scope


REQUEST = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms."
)


def results_page(*, applied_url=False, signature="11111111", adults=4):
    fields = [
        {"id": "0:destination", "tag": "INPUT", "type": "text", "label": "Destination",
         "name": "destination", "value": "New York"},
        {"id": "0:in", "tag": "INPUT", "type": "date", "label": "Check-in", "value": "2026-10-28"},
        {"id": "0:out", "tag": "INPUT", "type": "date", "label": "Check-out", "value": "2026-10-30"},
        {"id": "0:guests", "tag": "BUTTON", "type": "button",
         "label": f"{adults} adults, 0 children, 2 rooms", "expanded": "false"},
    ]
    page = {
        "url": "https://example.org/hotels", "document_id": "hotel-results",
        "frames": [{"text": "Stable page chrome and accommodation records.", "controls": fields}],
        "results": {"record_count": 4, "no_results": False, "busy": False,
                    "price_contexts": [], "result_signature": signature},
    }
    if applied_url:
        page["stay_url_values"] = {
            "check_in": ["2026-10-28"], "check_out": ["2026-10-30"], "adults": [4], "rooms": [2],
        }
    return page


def test_selected_calendar_dates_are_shared_with_returned_stay_validation():
    page = results_page()
    page["frames"][0]["controls"][1:3] = [
        {"id": "0:in", "tag": "BUTTON", "type": "button", "date_kind": "day_choice",
         "date": "2026-10-28", "label": "Selected October 28, 2026", "selected": "true", "date_widget_id": "calendar:0"},
        {"id": "0:out", "tag": "BUTTON", "type": "button", "date_kind": "day_choice",
         "date": "2026-10-30", "label": "Selected October 30, 2026", "selected": "true", "date_widget_id": "calendar:0"},
    ]
    task = TaskLedger(REQUEST)
    task.observe(page)
    assert all(check["status"] == "verified" for check in task.checks if check["field"] in {"check_in", "check_out"})
    assert observed_result_scope(task.requested_stay, page)["status"] == "verified"
    page["frames"][0]["controls"][2]["date_widget_id"] = "another-calendar"
    assert observed_calendar_endpoints(page) == []


def open_guest_widget(page):
    page["frames"][0]["controls"][3]["expanded"] = "true"
    page["frames"][0]["controls"].extend([
        {"id": "0:increase", "tag": "BUTTON", "type": "button", "label": "Increase Adults",
         "counter": {"label": "Adults", "value": 4, "direction": "increase"}, "widget_scope": "counter"},
        {"id": "0:update", "tag": "BUTTON", "type": "button", "label": "Update", "widget_scope": "counter"},
    ])
    return page["frames"][0]["controls"][-1]


def action(action, control, value=""):
    return SimpleNamespace(action=action, control_id=control["id"], value=value, purpose="set_field")


def test_existing_applied_url_results_can_be_collected_without_claiming_agent_submit():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    task.observe(page)
    assert task.adopt_matching_results(page)
    state = task.snapshot()
    assert state["matching_results_observed"] is True
    assert state["search_submitted"] is False
    assert state["search_transition"]["attempted"] is False
    assert state["search_transition"]["confirmed"] is False
    assert state["search_transition"]["attempt_status"] == "matching_results_observed"
    assert state["search_transition"]["submission_provenance"]["evidence_method"] == "returned_url"
    context = task.capture_context(page)
    assert context["status"] == "observed_matching_results"
    assert context["requested_stay_verified"] is True
    assert context["availability_verified"] is False
    assert context["record_values_verified"] is False
    assert task.completion_problem() is None


def test_matching_draft_fields_and_preexisting_cards_do_not_imply_applied_criteria():
    task, page = TaskLedger(REQUEST), results_page()
    task.observe(page)
    assert not task.adopt_matching_results(page)
    assert task.submission is None


def test_applied_matching_results_do_not_require_another_unowned_global_query():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    query = {"id": "0:site-query", "tag": "INPUT", "type": "search", "label": "Search",
             "value": "", "required": True, "value_missing": True}
    search = {"id": "0:site-search", "tag": "BUTTON", "type": "button", "label": "Search"}
    page["frames"][0]["controls"].extend([query, search])
    task.observe(page)
    assert not task.unresolved_form_fields
    assert task.adopt_matching_results(page)
    task.observe(page)
    assert not task.unresolved_form_fields
    assert task.snapshot()["matching_results_observed"] is True
    assert [item["control_id"] for item in task.required_form_fields(page, search)] == [query["id"]]


def test_matching_results_do_not_waive_a_non_query_required_field():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    page["frames"][0]["controls"].extend([
        {"id": "0:country", "tag": "SELECT", "label": "Country", "value": "",
         "required": True, "value_missing": True},
        {"id": "0:go", "tag": "BUTTON", "type": "button", "label": "Search"},
    ])
    task.observe(page)
    assert not task.adopt_matching_results(page)


@pytest.mark.parametrize("signature,accepted", [("11111111", False), ("22222222", True)])
def test_update_needs_a_closed_widget_and_actual_result_refresh(signature, accepted):
    task, before = TaskLedger(REQUEST), results_page()
    update = open_guest_widget(before)
    task.observe(before)
    click = action("click", update)
    assert not task.is_submit(click, update, before)
    task.remember_action(update, {"status": "action_performed"}, click, before)
    assert not task.adopt_matching_results(before)
    after = results_page(signature=signature)
    task.observe(after)
    assert task.adopt_matching_results(after) is accepted
    if accepted:
        assert task.snapshot()["search_transition"]["submission_provenance"]["evidence_method"] == "observed_result_refresh"


def test_changed_cards_after_actual_field_edit_do_not_require_a_busy_frame_or_search():
    task, before = TaskLedger(REQUEST), results_page()
    field = before["frames"][0]["controls"][1]
    field["value"] = "2026-10-27"
    task.observe(before)
    task.remember_action(field, {"status": "value_verified"}, action("fill", field, "2026-10-28"), before)
    after = results_page(signature="22222222")
    task.observe(after)
    assert task.adopt_matching_results(after)
    assert task.snapshot()["search_submitted"] is False


def test_unchanged_cards_need_an_observed_busy_cycle_when_only_draft_fields_are_available():
    task, before = TaskLedger(REQUEST), results_page()
    field = before["frames"][0]["controls"][1]
    field["value"] = "2026-10-27"
    task.observe(before)
    task.remember_action(field, {"status": "value_verified"}, action("fill", field, "2026-10-28"), before)
    after = results_page()
    task.observe(after)
    assert not task.adopt_matching_results(after)
    busy = copy.deepcopy(after)
    busy["results"]["busy"] = True
    task.observe(busy)
    task.observe(after)
    assert task.adopt_matching_results(after)


def test_counter_verified_auto_update_survives_update_merely_closing_the_widget():
    task, before = TaskLedger(REQUEST), results_page(adults=2)
    open_guest_widget(before)
    counter = before["frames"][0]["controls"][-2]
    counter["counter"]["value"] = 2
    task.observe(before)
    task.remember_action(counter, {"status": "counter_verified", "before": 2, "observed": 4},
                         action("set_counter", counter, "4"), before)
    assert task.result_refresh["criteria_changed"] is True
    refreshed = results_page(signature="22222222")
    update = open_guest_widget(refreshed)
    task.observe(refreshed)
    assert not task.adopt_matching_results(refreshed)
    task.remember_action(update, {"status": "action_performed"}, action("click", update), refreshed)
    assert task.result_refresh["before_results"]["result_signature"] == "11111111"
    final = results_page(signature="22222222")
    task.observe(final)
    assert task.adopt_matching_results(final)
    assert task.snapshot()["search_submitted"] is False


def test_opening_a_date_widget_is_not_tracked_as_changing_the_date():
    task, page = TaskLedger(REQUEST), results_page()
    opener = {"id": "0:in", "tag": "BUTTON", "type": "button", "date_kind": "opener",
              "date": "2026-10-28", "date_endpoint": "check_in", "label": "Enter check-in date"}
    page["frames"][0]["controls"][1] = opener
    task.observe(page)
    task.remember_action(opener, {"status": "action_performed"}, action("click", opener), page)
    assert task.result_refresh is None


def test_named_room_guest_summary_is_a_stay_widget_without_popup_attributes():
    summary = {"id": "0:guests", "tag": "BUTTON", "type": "button",
               "label": "The selected number of rooms is 3 and the selected number of guests is 5."}
    assert TaskLedger.stay_form_control(summary)


def test_closing_widget_preserves_a_completed_auto_update_cycle():
    task, before = TaskLedger(REQUEST), results_page()
    field = before["frames"][0]["controls"][1]
    field["value"] = "2026-10-27"
    task.observe(before)
    task.remember_action(field, {"status": "value_verified"}, action("fill", field, "2026-10-28"), before)
    busy = results_page(signature="22222222")
    busy["results"]["busy"] = True
    task.observe(busy)
    settled = results_page(signature="22222222")
    update = open_guest_widget(settled)
    task.observe(settled)
    task.remember_action(update, {"status": "action_performed"}, action("click", update), settled)
    closed = results_page(signature="22222222")
    task.observe(closed)
    assert task.adopt_matching_results(closed)


@pytest.mark.parametrize("change", ["wrong_adults", "catalog_prices", "loading", "no_rendered_records", "open_widget"])
def test_matching_result_adoption_preserves_stay_and_render_guards(change):
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    if change == "wrong_adults":
        page["frames"][0]["controls"][3]["label"] = "2 adults, 0 children, 2 rooms"
    elif change == "catalog_prices":
        page["results"]["price_contexts"] = ["Price from $419 for 1 night, 2 adults"]
    elif change == "loading":
        page["results"]["busy"] = True
    elif change == "no_rendered_records":
        page["results"]["record_count"] = 0
    else:
        open_guest_widget(page)
    task.observe(page)
    assert not task.adopt_matching_results(page)
    assert task.submission is None


def test_uncertain_submission_cannot_be_replaced_by_matching_result_adoption():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    task.observe(page)
    assert task.begin_submission(page, page["url"])
    task.pending_submission["dispatch_status"] = "outcome_unknown"
    assert not task.adopt_matching_results(page)
    assert task.pending_submission["dispatch_status"] == "outcome_unknown"
    assert task.snapshot()["search_response_pending"] is True


def test_required_child_age_and_unconfirmed_site_default_still_require_handoff():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    age = {"id": "0:age", "tag": "SELECT", "label": "Age of child 1",
           "value": "7", "required": True, "value_missing": False, "widget_scope": "dialog"}
    page["frames"][0]["controls"].append(age)
    task.observe(page)
    assert not task.adopt_matching_results(page)
    assert task.adopt_matching_results(page, ages_confirmed=True)
    task = TaskLedger(REQUEST)
    age.update(value="", value_missing=True, invalid=True)
    task.observe(page)
    assert not task.adopt_matching_results(page, ages_confirmed=True)
    assert [item["control_id"] for item in task.required_form_fields(page)] == ["0:age"]


def test_js_stay_controls_isolate_required_site_query_but_preserve_targeted_validation():
    task, page = TaskLedger(REQUEST), results_page()
    query = {"id": "0:global-query", "tag": "INPUT", "type": "search", "label": "Search",
             "name": "globalSearch", "form_scope": "global", "required": True, "value_missing": True, "value": ""}
    submit = {"id": "0:global-submit", "tag": "BUTTON", "type": "submit", "submits_form": True,
              "label": "Search", "form_scope": "global"}
    page["frames"][0]["controls"].extend([query, submit])
    task.observe(page)
    assert task.required_form_fields(page) == []
    assert [item["control_id"] for item in task.required_form_fields(page, submit)] == [query["id"]]
    query["label"] = "Search destination"
    assert [item["control_id"] for item in task.required_form_fields(page)] == [query["id"]]


def test_explicit_js_stay_search_isolates_unowned_query_before_results_are_applied():
    task, page = TaskLedger(REQUEST), results_page()
    query = {"id": "0:global-query", "tag": "INPUT", "type": "search", "label": "Search",
             "required": True, "value_missing": True, "value": ""}
    global_search = {"id": "0:global-submit", "tag": "BUTTON", "type": "button", "label": "Search"}
    stay_search = {"id": "0:stay-submit", "tag": "BUTTON", "type": "button", "label": "Search hotels"}
    page["frames"][0]["controls"].extend([query, global_search, stay_search])
    task.observe(page)
    assert task.required_form_fields(page) == []
    assert task.required_form_fields(page, stay_search) == []
    assert [item["control_id"] for item in task.required_form_fields(page, global_search)] == [query["id"]]
    age = {"id": "0:age", "tag": "SELECT", "label": "Age of child 1", "required": True,
           "value_missing": True, "value": "", "widget_scope": "dialog"}
    page["frames"][0]["controls"].append(age)
    assert [item["control_id"] for item in task.required_form_fields(page, stay_search)] == [age["id"]]
    query["label"] = "Search destination"
    assert query["id"] in [item["control_id"] for item in task.required_form_fields(page, stay_search)]


def test_global_search_popup_opener_is_not_a_stay_submission():
    task, page = TaskLedger(REQUEST), results_page()
    opener = {"id": "0:open-search", "tag": "BUTTON", "type": "button", "label": "Search",
              "haspopup": "dialog", "expanded": "false"}
    page["frames"][0]["controls"].append(opener)
    click = action("click", opener)
    assert task.discovery_navigation(click, opener, page)
    assert not task.is_submit(click, opener, page)
    assert not task.pending_submission


def test_same_page_submit_response_can_change_only_result_cards():
    task, before = TaskLedger(REQUEST), results_page()
    task.observe(before)
    assert task.begin_submission(before, before["url"])
    after = results_page(signature="22222222")
    assert before["document_id"] == after["document_id"]
    assert before["frames"][0]["text"] == after["frames"][0]["text"]
    task.observe(after)
    assert task.snapshot()["search_submitted"] is True
    assert task.pending_submission is None


def test_adopted_result_scope_is_withdrawn_when_same_page_occupancy_changes():
    task, page = TaskLedger(REQUEST), results_page(applied_url=True)
    task.observe(page)
    assert task.adopt_matching_results(page)
    changed = results_page(applied_url=True, adults=2)
    task.observe(changed)
    assert task.snapshot()["matching_results_observed"] is False
    assert task.capture_context(changed) is None


def test_declared_child_age_must_match_actual_selection_even_with_manual_confirmation():
    task, page = TaskLedger(REQUEST + " Include a child aged 7."), results_page(applied_url=True)
    age = {"id": "0:age", "tag": "SELECT", "label": "Age of child 1", "value": "age-eight",
           "options": [{"value": "age-eight", "label": "8 years old"},
                       {"value": "age-seven", "label": "7 years old"}]}
    page["frames"][0]["controls"].append(age)
    task.observe(page)
    assert not task.adopt_matching_results(page, ages_confirmed=True)
    age["value"] = "age-seven"
    task.observe(page)
    assert task.adopt_matching_results(page)


def test_widget_apply_to_explicit_empty_results_retains_empty_evidence_without_submit():
    task, before = TaskLedger(REQUEST), results_page()
    update = open_guest_widget(before)
    task.observe(before)
    task.remember_action(update, {"status": "action_performed"}, action("click", update), before)
    after = results_page(signature="empty")
    after["results"].update(record_count=0, no_results=True)
    task.observe(after)
    assert task.adopt_matching_results(after)
    assert task.snapshot()["search_transition"]["result_state"] == "empty"
    assert task.snapshot()["search_submitted"] is False


@pytest.mark.parametrize("change", ["count_only", "unknown_action_outcome", "unrelated_apply"])
def test_refresh_evidence_cannot_be_invented_from_count_or_unrelated_action(change):
    task, before = TaskLedger(REQUEST), results_page()
    update = open_guest_widget(before)
    if change == "unrelated_apply":
        update = {"id": "0:newsletter", "tag": "BUTTON", "type": "button", "label": "Subscribe"}
    task.observe(before)
    status = "outcome_unknown" if change == "unknown_action_outcome" else "action_performed"
    task.remember_action(update, {"status": status}, action("click", update), before)
    after = results_page(signature="11111111" if change == "count_only" else "22222222")
    after["results"]["record_count"] = 5
    task.observe(after)
    assert not task.adopt_matching_results(after)
