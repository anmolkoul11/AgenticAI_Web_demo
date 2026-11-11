"""Source fixtures for manual age handoff and committed occupancy readback."""

import copy

import pytest

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_context import build_navigation_context, observed_matching_results_ready
from agentic_web_demo.browser_task import TaskLedger
from test_browser_agent import FakeDecider, FakeTools, decision


REQUEST = (
    "Find hotels in Virginia from November 28-30, 2026 "
    "with 4 adults, 1 child and 3 rooms."
)

CHARLOTTE_REQUEST = "find me hotels in charlotte from 28-30 Nov 2026 ,for 3 adults"


def occupancy_page(*, panel_open=False, rooms=3, adults=4, applied=True):
    fields = [
        {"id": "0:destination", "tag": "INPUT", "label": "Destination", "value": "Virginia"},
        {"id": "0:in", "tag": "INPUT", "type": "date", "label": "Check-in", "value": "2026-11-28"},
        {"id": "0:out", "tag": "INPUT", "type": "date", "label": "Check-out", "value": "2026-11-30"},
        {"id": "0:guests", "tag": "BUTTON", "type": "button",
         "label": "Enter the number of rooms and then enter the number of guests. "
                  f"The selected number of rooms is {rooms} and the selected number of guests is 5.",
         "expanded": "true" if panel_open else "false"},
    ]
    if panel_open:
        fields.extend({
            "id": f"0:{field}", "tag": "BUTTON", "type": "button", "label": f"Increase {field}",
            "counter": {"label": field, "value": value, "direction": "increase", "evidence": f"{field} {value}"},
        } for field, value in (("Adults", adults), ("Children", 1), ("Rooms", rooms)))
        fields.extend([
            {"id": "0:age", "tag": "SELECT", "label": "Age of child 1", "value": "7", "required": True,
             "options": [{"value": "7", "label": "7 years old"}]},
            {"id": "0:update", "tag": "BUTTON", "type": "button", "label": "Update"},
        ])
    page = {
        "url": "https://example.org/hotels", "document_id": "applied-results",
        "frames": [{"text": "Virginia hotel results", "controls": fields}],
        "results": {"record_count": 3, "busy": False, "no_results": False, "result_signature": "11111111"},
    }
    if applied:
        page["stay_url_values"] = {"check_in": ["2026-11-28"], "check_out": ["2026-11-30"],
                                   "adults": [4], "children": [1], "rooms": [3]}
    return page


def charlotte_page(*, panel_open=False, applied=True):
    page = occupancy_page(panel_open=panel_open, rooms=2, adults=3, applied=applied)
    page["frames"][0]["controls"][0]["value"] = "Charlotte"
    page["frames"][0]["controls"][3]["label"] = (
        "Enter the number of rooms and then enter the number of guests. "
        "The selected number of rooms is 2 and the selected number of guests is 3."
    )
    page["frames"][0]["controls"] = [control for control in page["frames"][0]["controls"]
                                       if control["id"] != "0:age"]
    for control in page["frames"][0]["controls"]:
        if control.get("counter", {}).get("label") == "Children":
            control["counter"].update(value=0, evidence="Children 0")
    if applied:
        page["stay_url_values"].update(adults=[3], children=[0], rooms=[2])
    return page


def test_adults_only_request_verifies_only_requested_counts_and_preserves_other_rows():
    task = TaskLedger(CHARLOTTE_REQUEST)
    closed = charlotte_page()
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    assert diagnostic["expected_counts"] == {"adults": 3}
    opened = charlotte_page(panel_open=True)
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert proof["checked_counts"] == {"adults": 3}
    assert "rooms" not in task.requirements and "children" not in task.requirements
    assert task.adopt_matching_results(opened, post_commit_inspection=proof)
    assert observed_matching_results_ready(task.snapshot(), document_id=opened["document_id"])


def test_results_global_query_does_not_block_guest_update_but_targeted_query_is_validated():
    task = TaskLedger(CHARLOTTE_REQUEST)
    page = charlotte_page(panel_open=True)
    query = {"id": "0:site-query", "tag": "INPUT", "type": "search", "label": "Search",
             "value": "", "required": True, "value_missing": True}
    page["frames"][0]["controls"].append(query)
    task.observe(page)
    assert task.required_form_fields(page) == []
    assert [field["control_id"] for field in task.required_form_fields(page, query)] == [query["id"]]
    assert task.action_value_problem(query, decision("press", query["id"], "Enter"), page) is None
    agent = BrowserAgent(FakeTools(), FakeDecider([]), CHARLOTTE_REQUEST)
    agent.task.observe(page)
    assert agent.occupancy_confirmation(page)["label"] == "Update"


def test_matching_counter_with_old_summary_focuses_update_instead_of_another_increment():
    task = TaskLedger(CHARLOTTE_REQUEST)
    page = charlotte_page(panel_open=True, applied=False)
    task.observe(page)
    checklist = task.snapshot()
    adults = next(item for item in checklist["requirements"] if item["field"] == "adults")
    adults.update(status="pending", next_action="confirm_or_close_widget", summary_confirmation_pending=True)
    checklist["pending_fields"] = ["adults"]
    context = build_navigation_context({"task": CHARLOTTE_REQUEST, "observation": page,
                                        "task_checklist": checklist, "recent_actions": []})
    assert context["interaction_focus"]["phase"] == "confirm_widget"
    assert "0:update" in context["interaction_focus"]["control_ids"]


def test_unowned_enter_is_an_unsupported_action_not_a_missing_user_value():
    class QueryTools(FakeTools):
        def observe(self):
            query = {"id": "0:search", "tag": "INPUT", "type": "search", "label": "Search", "value": ""}
            self.references = {query["id"]: (None, None, query)}
            return {"url": "https://example.org/", "frames": [{"controls": [query]}]}

    model = FakeDecider([decision("press", "0:search", "Enter"), decision("pause")])
    tools = QueryTools()
    report = BrowserAgent(tools, model, CHARLOTTE_REQUEST).run()
    assert "press" not in tools.events
    assert "awaiting_user_input" not in report
    assert "Enter was not sent" in report["actions"][0]["guidance"]


def test_applied_adults_only_results_are_collected_before_reopening_a_guest_panel():
    class ResultsTools(FakeTools):
        def observe(self):
            page = charlotte_page()
            self.references = {control["id"]: (None, None, control)
                               for control in page["frames"][0]["controls"]}
            return page

        def capture(self, kind="page"):
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "Charlotte Hotel USD 110 nightly",
                               "source_kind": kind})

    tools = ResultsTools()
    model = FakeDecider([])
    report = BrowserAgent(tools, model, CHARLOTTE_REQUEST).run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events == ["capture"]


@pytest.mark.parametrize("control,available", [
    ({"tag": "SELECT", "value": "7"}, True),
    ({"tag": "SELECT", "value": "0"}, True),
    ({"role": "combobox", "value": "7 years", "value_source": "aria-valuetext"}, True),
    ({"tag": "SELECT", "value": "child-seven", "options": [{"value": "child-seven", "label": "7 years old"}]}, True),
    ({"tag": "SELECT", "value": "-1", "selection_placeholder": True}, False),
    ({"role": "combobox", "value": "Select age"}, False),
    ({"role": "combobox", "value": "7", "invalid": True}, False),
])
def test_age_confirmation_uses_actual_numeric_selection(control, available):
    assert BrowserAgent.age_value_available(control) is available


def test_reopened_rows_can_confirm_applied_results_without_another_update_or_search():
    task = TaskLedger(REQUEST)
    closed = occupancy_page()
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    assert diagnostic["expected_total_guests"] == 5
    assert diagnostic["observed_counts"]["rooms"] == [3]
    assert "adults" not in diagnostic["observed_counts"]
    opened = occupancy_page(panel_open=True)
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert proof["checked_counts"] == {"adults": 4, "children": 1, "rooms": 3}
    assert not task.adopt_matching_results(opened, post_commit_inspection=proof)
    assert task.adopt_matching_results(opened, ages_confirmed=True, post_commit_inspection=proof)
    task.observe(opened)
    snapshot = task.snapshot()
    assert observed_matching_results_ready(snapshot, document_id=opened["document_id"])
    assert snapshot["search_submitted"] is False
    assert snapshot["search_transition"]["submission_provenance"]["evidence_method"] == "post_commit_readback"
    task.observe(closed)
    assert task.submission is None  # Hidden rows are not retained as fresh count proof.


@pytest.mark.parametrize("fault", ["wrong_closed_rooms", "wrong_open_adults", "wrong_open_rooms", "different_document"])
def test_inspection_does_not_accept_off_by_one_or_stale_counts(fault):
    task = TaskLedger(REQUEST)
    closed = occupancy_page(rooms=2 if fault == "wrong_closed_rooms" else 3)
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    opened = occupancy_page(panel_open=True, rooms=2 if fault == "wrong_open_rooms" else 3,
                            adults=5 if fault == "wrong_open_adults" else 4)
    if fault == "different_document":
        opened["document_id"] = "another-page"
    task.observe(opened)
    assert task.confirm_occupancy_inspection(opened, diagnostic) is None
    assert not task.adopt_matching_results(opened, ages_confirmed=True,
                                          post_commit_inspection={"closed_diagnostic": diagnostic})


def test_inspection_does_not_replace_evidence_that_results_applied_the_stay():
    task = TaskLedger(REQUEST)
    closed = occupancy_page(applied=False)
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed)
    opened = occupancy_page(panel_open=True, applied=False)
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert proof is not None
    assert not task.adopt_matching_results(opened, ages_confirmed=True, post_commit_inspection=proof)


@pytest.mark.parametrize("change", ["missing_application", "different_document", "wrong_count", "missing_reading"])
def test_inspection_provenance_must_remain_bound_to_applied_results(change):
    task = TaskLedger(REQUEST)
    closed = occupancy_page()
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    opened = occupancy_page(panel_open=True)
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert task.adopt_matching_results(opened, ages_confirmed=True, post_commit_inspection=proof)
    snapshot = task.snapshot()
    provenance = snapshot["search_transition"]["submission_provenance"]
    if change == "missing_application":
        provenance.pop("applied_evidence_method")
    elif change == "different_document":
        provenance["occupancy_inspection"]["document_id"] = "old-document"
    elif change == "wrong_count":
        provenance["occupancy_inspection"]["checked_counts"]["adults"] = 5
    else:
        provenance["occupancy_inspection"]["readings"].pop("children")
    assert not observed_matching_results_ready(snapshot, document_id=opened["document_id"])


def test_reopen_attempts_are_bounded_even_if_control_ids_change():
    agent = BrowserAgent(FakeTools(), FakeDecider([]), REQUEST)
    page = occupancy_page(applied=False)
    agent.task.observe(page)
    diagnostic = agent.task.occupancy_recheck(page)
    assert agent.occupancy_reopen(diagnostic)["decision"]["action"] == "click"
    changed = copy.deepcopy(diagnostic)
    changed["opener"]["control_id"] = "0:new-handle"
    assert agent.occupancy_reopen(changed)["decision"]["action"] == "click"
    assert agent.occupancy_reopen(changed)["decision"]["action"] == "pause"


def test_explicit_resume_reads_age_after_update_changes_document_identity():
    class AgeTools(FakeTools):
        age, panel_open, document = "8", True, "before-update"

        def observe(self):
            self.events.append("observe")
            age = {"id": "0:age", "role": "combobox", "tag": "DIV", "label": "Age of child 1",
                   "value": self.age, "required": True, "value_source": "aria-valuetext"}
            opener = {"id": "0:guests", "tag": "BUTTON", "type": "button",
                      "label": "The selected number of rooms is 3 and the selected number of guests is 5."}
            fields = [opener] + ([age] if self.panel_open else [])
            self.references = {field["id"]: (None, None, field) for field in fields}
            return {"url": "https://example.org/hotels", "document_id": self.document,
                    "frames": [{"controls": fields}]}

        def execute(self, action):
            if action.action == "click" and action.control_id == "0:guests":
                self.panel_open = True
            return super().execute(action)

    tools = AgeTools()
    model = FakeDecider([decision("pause", pause_reason="user_input")])
    agent = BrowserAgent(tools, model, REQUEST)
    assert agent.run()["calls"] == 0
    tools.age, tools.panel_open, tools.document = "7", False, "after-update"
    report = agent.run()
    assert report["calls"] == 1
    assert tools.events.count("click") == 1
    assert "select" not in tools.events and tools.age == "7"
    assert agent.ages_still_confirmed(tools.observe())
    tools.age = "8"
    assert not agent.ages_still_confirmed(tools.observe())
