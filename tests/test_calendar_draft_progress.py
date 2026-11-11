"""Draft selections must advance without pretending the stay is committed."""

import copy

import pytest

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_context import build_navigation_context, calendar_completion
from agentic_web_demo.browser_task import TaskLedger
from test_browser_agent import FakeDecider, FakeTools, decision
from test_stay_task_transition import PROMPT, displayed_stay


def draft_page(picked=(), *, routed=False, committed=False):
    page = displayed_stay(month=12 if committed else 11, calendar_open=not committed)
    page.update(page_id="physical-tab-a", document_id="route-" + str(len(picked)) if routed else "hotel-document")
    for item in page["frames"][0]["controls"]:
        if item.get("date_kind") == "day_choice":
            selected = item["date"] in picked
            item.update(selected=str(selected).lower(), label=("Selected " if selected else "") + item["label"])
    if not committed:
        page["frames"][0]["controls"].append({"id": "0:apply", "tag": "BUTTON", "type": "button",
                                              "label": "Apply", "date_widget_id": "calendar"})
    return page


def remember_pick(task, page, field="check_in", *, confirmed=True):
    day = "2026-12-28" if field == "check_in" else "2026-12-30"
    facts = next(item for item in page["frames"][0]["controls"] if item.get("date") == day
                 and item.get("date_kind") == "day_choice")
    task.remember_action(facts, {"status": "action_performed" if confirmed else "value_mismatch",
                                "calendar": {"date": day, "status": "selected" if confirmed else "unconfirmed",
                                             "dispatched": True}}, decision("click", facts["id"]), page)
    return facts


@pytest.mark.parametrize("routed", [False, True])
def test_selected_draft_start_moves_to_checkout_while_november_summary_stays_unverified(routed):
    task = TaskLedger(PROMPT)
    before = draft_page(routed=routed)
    task.observe(before)
    remember_pick(task, before)
    after = draft_page(["2026-12-28"], routed=routed)
    state = task.observe(after)
    assert next(item for item in state["requirements"] if item["field"] == "check_in")["status"] != "verified"
    assert state["calendar_progress"]["next_field"] == "check_out"
    assert [item["field"] for item in state["visible_date_choices"]] == ["check_out"]
    context = build_navigation_context({"task": PROMPT, "observation": after,
                                        "task_checklist": state, "recent_actions": []})
    assert context["interaction_focus"]["fields"] == ["check_out"]
    assert not task.adopt_matching_results(after)
    start = next(item for item in after["frames"][0]["controls"] if item.get("date") == "2026-12-28"
                 and item.get("date_kind") == "day_choice")
    assert not task.calendar_reselection_required(start, after)
    assert task.calendar_action_problem(start, decision("click", start["id"]), after)


def test_two_draft_picks_offer_apply_without_marking_old_form_dates_verified():
    task = TaskLedger(PROMPT)
    before = draft_page()
    task.observe(before)
    remember_pick(task, before)
    middle = draft_page(["2026-12-28"])
    task.observe(middle)
    remember_pick(task, middle, "check_out")
    after = draft_page(["2026-12-28", "2026-12-30"])
    state = task.observe(after)
    assert state["calendar_progress"]["status"] == "awaiting_commit"
    assert state["visible_date_choices"] == []
    assert {"check_in", "check_out"} <= set(task.pending())
    assert calendar_completion(after, state)["next_action"] == {"action": "click", "control_id": "0:apply", "value": ""}
    changed = copy.deepcopy(after)
    changed.update(document_id="another-document", page_id="physical-tab-b")
    assert task.observe(changed)["calendar_progress"] is None


def test_committed_form_dates_supersede_a_stale_draft_start_in_the_open_calendar():
    task = TaskLedger(PROMPT)
    before = draft_page()
    task.observe(before)
    remember_pick(task, before)
    after = draft_page(["2026-12-28"])
    for item in after["frames"][0]["controls"]:
        endpoint = item.get("date_endpoint")
        if endpoint in {"check_in", "check_out"}:
            day = "28" if endpoint == "check_in" else "30"
            full = f"2026-12-{day}"
            item.update(date=full, label=f"Enter the date. The selected date is {full}.")
    state = task.observe(after)
    assert all(item["status"] == "verified" for item in state["requirements"]
               if item["field"] in {"check_in", "check_out"})
    assert state["calendar_progress"] is None
    assert state["visible_date_choices"] == []


def test_resume_preserves_a_fresh_confirmed_start_and_pre_input_rejection_is_recoverable():
    task = TaskLedger(PROMPT)
    before = draft_page()
    task.observe(before)
    remember_pick(task, before)
    task.calendar_resume_requested = True
    middle = draft_page(["2026-12-28"])
    assert task.observe(middle)["calendar_progress"]["next_field"] == "check_out"
    end = next(item for item in middle["frames"][0]["controls"] if item.get("date") == "2026-12-30"
               and item.get("date_kind") == "day_choice")
    task.remember_action(end, {"status": "date_unconfirmed", "calendar": {
        "status": "changed_before_input", "dispatched": False}}, decision("click", end["id"]), middle)
    assert task.calendar_action_problem(end, decision("click", end["id"]), middle) is None


@pytest.mark.parametrize("routed", [False, True])
def test_live_loop_picks_each_date_once_applies_then_collects(routed):
    class DraftTools(FakeTools):
        picked = ()
        committed = False

        def observe(self):
            page = draft_page(self.picked, routed=routed, committed=self.committed)
            # Use explicit committed counts to isolate calendar progress from
            # the separately covered read-only total-guests inspection.
            page["frames"][0]["controls"][3].update(label="5 adults, 0 children, 3 rooms", text="")
            self.references = {item["id"]: (None, None, item) for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            assert action.action == "click"
            self.events.append(action.control_id)
            if action.control_id == "0:apply":
                assert self.picked == ("2026-12-28", "2026-12-30")
                self.committed = True
                return {"status": "action_performed"}
            expected = "0:day-28" if not self.picked else "0:day-30"
            assert action.control_id == expected
            day = "2026-12-28" if not self.picked else "2026-12-30"
            self.picked += (day,)
            return {"status": "action_performed", "calendar": {"date": day, "status": "selected", "dispatched": True}}

        def capture(self, kind="page"):
            assert self.committed
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "New York hotel results",
                               "source_kind": kind})

    tools = DraftTools()
    report = BrowserAgent(tools, FakeDecider([]), PROMPT).run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events == ["0:day-28", "0:day-30", "0:apply", "capture"]


def test_uncertain_dispatch_is_not_repeated_after_calendar_fingerprint_changes():
    class UnknownTools(FakeTools):
        def observe(self):
            page = draft_page()
            page["frames"][0]["viewport"] = {"scroll_y": len(self.events) * 70}
            self.references = {item["id"]: (None, None, item) for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            self.events.append(action.control_id)
            return {"status": "value_mismatch", "calendar": {"date": "2026-12-28", "status": "unconfirmed",
                                                              "dispatched": True}}

    tools = UnknownTools()
    report = BrowserAgent(tools, FakeDecider([]), PROMPT).run()
    assert report["status"] == "paused" and tools.events == ["0:day-28"]
    assert report["actions"][-1]["status"] == "date_confirmation_pending"
