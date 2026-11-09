"""Existing hotel results must not require replaying the search that made them."""

import pytest

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_context import build_navigation_context, observed_matching_results_ready
from agentic_web_demo.browser_task import TaskLedger, occupancy_widget_action
from test_browser_agent import FakeDecider, FakeTools, decision
from test_manual_occupancy_resume import charlotte_page
from test_observed_stay_results import REQUEST as AUTO_REQUEST, action, results_page


REQUEST = "Find hotels in New Jersey from 28-30 November 2026 for 3 adults and 2 rooms"


def hotel_results(*, panel_open=False, explicit_adults=False):
    page = charlotte_page(panel_open=panel_open, applied=False)
    fields = page["frames"][0]["controls"]
    fields[0]["value"] = "New Jersey"
    fields[1:3] = [
        {"id": "0:in", "tag": "BUTTON", "type": "button", "label": "Enter the check-in date November 28, 2026",
         "date_kind": "opener", "date": "2026-11-28", "date_endpoint": "check_in", "expanded": "false"},
        {"id": "0:out", "tag": "BUTTON", "type": "button", "label": "Enter the check-out date November 30, 2026",
         "date_kind": "opener", "date": "2026-11-30", "date_endpoint": "check_out", "expanded": "false"},
    ]
    if explicit_adults:
        fields[3]["label"] = "3 adults, 0 children, 2 rooms"
    page["results"]["headings"] = [{"level": 1, "text": "New Jersey Hotels and Places to Stay"}]
    fields.append({"id": "0:site-search", "tag": "INPUT", "type": "search", "label": "Search",
                   "value": "", "required": True, "value_missing": True})
    return page


def test_committed_current_summaries_do_not_require_url_or_observed_refresh():
    task = TaskLedger(REQUEST)
    page = hotel_results(explicit_adults=True)
    task.observe(page)
    assert task.result_scope["status"] == "verified"
    assert task.result_refresh is None and "stay_url_values" not in page
    assert task.adopt_matching_results(page)
    snapshot = task.snapshot()
    assert observed_matching_results_ready(snapshot, document_id=page["document_id"])
    assert snapshot["search_submitted"] is False
    provenance = snapshot["search_transition"]["submission_provenance"]
    assert provenance["evidence_method"] == "committed_results_summary"
    heading = next(field for field in provenance["committed_summary"]["fields"] if field["field"] == "destination")
    assert heading["evidence"] == "New Jersey Hotels and Places to Stay"
    assert task.capture_context(page)["availability_verified"] is False


def test_guest_split_readback_completes_current_results_with_unchanged_cards():
    task = TaskLedger(REQUEST)
    closed = hotel_results()
    task.observe(closed)
    assert next(check for check in task.checks if check["field"] == "destination")["status"] == "verified"
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    opened = hotel_results(panel_open=True)
    assert opened["results"]["result_signature"] == closed["results"]["result_signature"]
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert proof is not None
    assert task.adopt_matching_results(opened, post_commit_inspection=proof)
    task.observe(opened)
    assert task.completion_problem() is None
    state = task.snapshot()
    assert observed_matching_results_ready(state, document_id=opened["document_id"])
    assert state["search_transition"]["submission_provenance"]["applied_evidence_method"] == "committed_results_summary"


@pytest.mark.parametrize("change", ["missing_year", "wrong_adults", "draft_fields", "different_location"])
def test_existing_cards_do_not_turn_unknown_or_wrong_criteria_into_matches(change):
    task = TaskLedger(REQUEST)
    page = hotel_results(explicit_adults=True)
    if change == "missing_year":
        page["frames"][0]["controls"][1].update(date="", label="Check-in Nov 28")
    elif change == "wrong_adults":
        page["frames"][0]["controls"][3]["label"] = "2 adults, 0 children, 2 rooms"
    elif change == "different_location":
        page["results"]["headings"][0]["text"] = "Boston Hotels and Places to Stay"
    else:
        for item in page["frames"][0]["controls"][1:3]:
            item.update(tag="INPUT", type="date", value=item["date"], readonly=False)
            item.pop("date_kind")
    task.observe(page)
    assert not task.adopt_matching_results(page)


def test_fresh_summary_claim_is_withdrawn_when_its_committed_witness_disappears():
    task = TaskLedger(REQUEST)
    page = hotel_results(explicit_adults=True)
    task.observe(page)
    assert task.adopt_matching_results(page)
    draft = hotel_results(panel_open=True)
    task.observe(draft)
    assert task.submission is None


def test_same_page_result_context_does_not_tell_model_to_refill_global_search():
    task = TaskLedger(REQUEST)
    page = hotel_results()
    task.observe(page)
    context = build_navigation_context({"task": REQUEST, "observation": page,
                                        "task_checklist": task.snapshot(), "recent_actions": []})
    assert context["interaction_focus"]["phase"] != "fill_fields"
    assert context["task_checklist"]["result_scope"]["fields"]


def test_manual_resume_discards_transient_readback_and_loop_state_but_keeps_budgets():
    agent = BrowserAgent(FakeTools(), FakeDecider([decision("pause")]), "Read visible information")
    agent.report["status"] = "paused"
    agent.calls, agent.elapsed = 7, 12
    agent.occupancy_inspection_diagnostic = {"old": "summary"}
    agent.pending_autocomplete = {"old": "binding"}
    agent.unsubmitted_transition_watch = {"document": "old", "action": "old"}
    agent.seen_actions["old-action"] = 2
    agent.local_submission_attempts.add(("document", "actual-form"))
    report = agent.run()
    assert report["calls"] == 8 and agent.elapsed >= 12
    assert agent.occupancy_inspection_diagnostic is None and agent.pending_autocomplete is None
    assert agent.unsubmitted_transition_watch is None and "old-action" not in agent.seen_actions
    assert ("document", "actual-form") in agent.local_submission_attempts


def test_search_preflight_collects_results_that_finished_auto_updating_during_decision():
    class AutoResults(FakeTools):
        reads = 0

        def observe(self):
            self.reads += 1
            page = results_page(signature="11111111" if self.reads == 1 else "22222222")
            page["frames"][0]["controls"].extend([
                {"id": "0:query", "tag": "INPUT", "type": "search", "label": "Search", "value": "",
                 "required": True, "value_missing": True, "form_scope": "0:global"},
                {"id": "0:search", "tag": "BUTTON", "type": "submit", "label": "Search",
                 "submits_form": True, "form_scope": "0:global"},
            ])
            self.references = {control["id"]: (None, None, control)
                               for control in page["frames"][0]["controls"]}
            return page

        def capture(self, kind="page"):
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "Hotel results USD 300 nightly",
                               "source_kind": kind})

    tools = AutoResults()
    model = FakeDecider([decision("click", "0:search", purpose="submit_search")])
    agent = BrowserAgent(tools, model, AUTO_REQUEST)
    before = results_page()
    field = before["frames"][0]["controls"][1]
    field["value"] = "2026-10-27"
    agent.task.observe(before)
    agent.task.remember_action(field, {"status": "value_verified"}, action("fill", field, "2026-10-28"), before)
    report = agent.run()
    assert report["status"] == "ready"
    assert report["calls"] == 1 and tools.events == ["capture"]
    assert any(entry["status"] == "search_not_needed" for entry in report["actions"])
    assert report["task_checklist"]["search_submitted"] is False


def test_handoff_diagnostics_name_the_unknown_stay_field_instead_of_a_search_value():
    task = TaskLedger(REQUEST)
    page = hotel_results(explicit_adults=True)
    page["frames"][0]["controls"][1].update(date="", label="Check-in Nov 28")
    task.observe(page)
    assert not task.adopt_matching_results(page)
    assert task.snapshot()["result_handoff"]["reason"] == "returned_scope_unverified"
    assert task.snapshot()["result_handoff"]["unverified_fields"] == ["check_in"]


def test_both_required_query_paths_use_known_destination_instead_of_asking_for_search_data():
    agent = BrowserAgent(FakeTools(), FakeDecider([]), REQUEST)
    agent.task.result_handoff = {"ready": False, "reason": "returned_scope_unverified",
                                 "unverified_fields": ["check_in"]}
    entry = {"action": "click", "control": "Search"}
    result = agent.await_user_input(entry, "The website still requires: Search.", ["Search"])
    assert result["status"] == "running" and "awaiting_user_input" not in agent.report
    result = agent.await_user_input(entry, "Please enter Search in the website, then press Resume.")
    assert result["status"] == "paused" and "awaiting_user_input" not in agent.report
    assert "check_in" in agent.report["guidance"]
    assert "no new Search value is needed" in agent.report["guidance"]


def test_unknown_child_age_still_requires_manual_input():
    agent = BrowserAgent(FakeTools(), FakeDecider([]), REQUEST)
    result = agent.await_user_input({"action": "pause"}, "Please enter or confirm child ages.", ["Age of child 1"])
    assert result["status"] == "paused"
    assert agent.report["awaiting_user_input"]["fields"] == ["Age of child 1"]


def test_guest_update_precedes_required_global_query_despite_different_widget_types():
    task = TaskLedger(REQUEST)
    page = hotel_results(panel_open=True, explicit_adults=True)
    for field in page["frames"][0]["controls"]:
        field["widget_scope"] = "counter" if field.get("counter") else "choice"
    task.observe(page)
    assert not task.adopt_matching_results(page)
    checklist = task.snapshot()
    checklist["unresolved_form_fields"] = [{"control_id": "0:site-search", "label": "Search"}]
    expected = {"action": "click", "control_id": "0:update", "value": ""}
    assert occupancy_widget_action(page, checklist) == expected
    assert checklist["result_handoff"]["widget_completion"] == expected
    context = build_navigation_context({"task": REQUEST, "observation": page,
                                        "task_checklist": checklist, "recent_actions": []})
    assert context["interaction_focus"]["next_action"] == expected
    assert context["interaction_focus"]["phase"] == "confirm_widget"


@pytest.mark.parametrize("has_update", [True, False])
@pytest.mark.parametrize("adults,rooms", [(3, 2), (4, 3)])
def test_completed_guest_widget_hands_off_same_page_hotels_without_paid_search(has_update, adults, rooms):
    class GuestResults(FakeTools):
        panel_open = True

        def observe(self):
            page = hotel_results(panel_open=self.panel_open, explicit_adults=True)
            fields = page["frames"][0]["controls"]
            for item in fields:
                item["widget_scope"] = "counter" if item.get("counter") else "choice"
                if item["id"] == "0:guests":
                    item["label"] = f"{adults} adults, 0 children, {rooms} rooms"
                if item["id"] == "0:update":
                    item.update(label="Apply guest selection", text="Update")
                counter = item.get("counter") or {}
                if counter.get("label") in {"Adults", "Rooms"}:
                    value = adults if counter["label"] == "Adults" else rooms
                    counter.update(value=value, evidence=f"{counter['label']} {value}")
            if not has_update:
                page["frames"][0]["controls"] = [item for item in fields if item["id"] != "0:update"]
            self.references = {item["id"]: (None, None, item) for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            assert (action.action, action.control_id, action.value) == (
                ("click", "0:update", "") if has_update else ("press", "0:guests", "Escape"))
            self.events.append(action.action)
            self.panel_open = False
            return {"status": "action_performed"}

        def capture(self, kind="page"):
            assert not self.panel_open
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "New Jersey Hotel USD 300 nightly",
                               "source_kind": kind})

    tools = GuestResults()
    wording = f"Find hotels in New Jersey from 28-30 November 2026 for {adults} adults and {rooms} rooms"
    report = BrowserAgent(tools, FakeDecider([]), wording).run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events == ["click" if has_update else "press", "capture"]
    assert report["task_checklist"]["matching_results_observed"]
    assert not report["task_checklist"]["search_submitted"]


@pytest.mark.parametrize("problem", ["wrong_adults", "missing_age", "ambiguous_update", "calendar_open"])
def test_guest_completion_does_not_hide_unresolved_values_or_guess_a_control(problem):
    task = TaskLedger(REQUEST)
    page = hotel_results(panel_open=True, explicit_adults=True)
    fields = page["frames"][0]["controls"]
    if problem == "wrong_adults":
        next(item for item in fields if item.get("counter", {}).get("label") == "Adults")["counter"]["value"] = 2
    elif problem == "ambiguous_update":
        fields.append({"id": "0:other-update", "tag": "BUTTON", "type": "button", "label": "Update"})
    elif problem == "calendar_open":
        fields.append({"id": "0:day", "tag": "BUTTON", "date_kind": "day_choice", "date_widget_id": "calendar",
                       "date": "2026-11-28", "label": "November 28, 2026"})
    task.observe(page)
    checklist = task.snapshot()
    if problem == "missing_age":
        fields.append({"id": "0:age", "tag": "SELECT", "label": "Age of child 1", "value": "", "required": True})
        checklist["unresolved_form_fields"] = [{"control_id": "0:age", "label": "Age of child 1"}]
    assert occupancy_widget_action(page, checklist) is None
