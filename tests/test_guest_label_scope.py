"""Actual singular stepper labels must survive post-Update result checks."""

import pytest

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_navigation import guest_component
from agentic_web_demo.browser_task import TaskLedger, occupancy_component
from agentic_web_demo.stay_scope import observed_result_scope
from test_browser_agent import FakeDecider, FakeTools
from test_stay_task_transition import displayed_stay


def requested(adults):
    return f"Find hotels in New York from 28-30 December 2026 with {adults} adults only and 3 rooms"


def named_counters(adults=4, *, opened=True):
    page = displayed_stay(panel_open=opened)
    fields = page["frames"][0]["controls"]
    fields[:] = [item for item in fields if not item.get("counter")]
    fields[3].update(label="Enter the number of rooms and then enter the number of guests. "
                           f"The selected number of rooms is 3 and the selected number of guests is {adults}.",
                     text=f"Rooms/Guests 3 Rooms, {adults} Guests")
    if opened:
        for label, value in (("adult", adults), ("child", 0), ("room", 3)):
            for direction in ("increase", "decrease"):
                fields.append({"id": f"0:{label}-{direction}", "tag": "BUTTON", "type": "button",
                               "label": f"{direction.title()} {label} count by 1",
                               "counter": {"label": label, "value": value, "direction": direction,
                                           "method": "button", "evidence": f"{label} {value}"}})
    return page


@pytest.mark.parametrize("label,field", [("adult", "adults"), ("Adults", "adults"),
    ("child", "children"), ("Children", "children"), ("kids", "children"), ("room", "rooms")])
def test_controller_and_result_scope_share_quantity_label_meanings(label, field):
    page = named_counters()
    for item in page["frames"][0]["controls"]:
        if item.get("counter") and guest_component({"label": item["counter"]["label"]}) == field:
            item["counter"]["label"] = label
    task = TaskLedger(requested(4))
    task.observe(page)
    scope = observed_result_scope(task.requested_stay, page)
    assert occupancy_component(label) == guest_component({"label": label}) == field
    assert scope["status"] == "verified"
    assert next(item for item in scope["fields"] if item["field"] == field)["status"] == "verified"


@pytest.mark.parametrize("adults", [4, 5])
def test_post_update_readback_of_real_singular_labels_collects_without_another_update(adults):
    class GuestTools(FakeTools):
        opened = False

        def observe(self):
            page = named_counters(adults, opened=self.opened)
            self.references = {item["id"]: (None, None, item) for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            assert action.action == "click" and action.control_id == "0:guests" and not self.opened
            self.opened = True
            self.events.append("read_guest_counts")
            return {"status": "action_performed"}

        def capture(self, kind="page"):
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "New York hotel records",
                               "source_kind": kind})

    tools = GuestTools()
    report = BrowserAgent(tools, FakeDecider([]), requested(adults)).run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events == ["read_guest_counts", "capture"]
    assert report["task_checklist"]["matching_results_observed"]


@pytest.mark.parametrize("age", [
    {"id": "0:age", "tag": "SELECT", "label": "Age of child 1", "value": "7",
     "options": [{"value": "7", "label": "7 years old"}]},
    {"id": "0:age", "tag": "INPUT", "type": "number", "label": "Age of child 1", "value": "7",
     "counter": {"label": "Age of child 1", "value": 7, "method": "number_input"}},
])
def test_age_and_child_ordinal_are_not_child_quantities(age):
    page = named_counters()
    page["frames"][0]["controls"].append(age)
    assert guest_component(age) is None
    scope = observed_result_scope(TaskLedger(requested(4)).requested_stay, page)
    child = next(item for item in scope["fields"] if item["field"] == "children")
    assert child["status"] == "verified" and child["observed"] == "0"


def test_singular_child_label_keeps_a_real_count_mismatch():
    page = named_counters()
    for item in page["frames"][0]["controls"]:
        if item.get("counter", {}).get("label") == "child":
            item["counter"].update(value=1, evidence="child 1")
    scope = observed_result_scope(TaskLedger(requested(4)).requested_stay, page)
    child = next(item for item in scope["fields"] if item["field"] == "children")
    assert child["status"] == "mismatch" and child["observed"] == "1"


def test_readback_failure_is_a_workflow_pause_not_missing_request_data():
    agent = BrowserAgent(FakeTools(), FakeDecider([]), requested(4))
    page = named_counters(opened=False)
    agent.task.observe(page)
    diagnostic = agent.task.occupancy_recheck(page)
    assert diagnostic is not None
    agent.occupancy_reopen(diagnostic)
    agent.occupancy_reopen(diagnostic)
    paused = agent.occupancy_reopen(diagnostic)["decision"]
    assert paused["action"] == "pause" and paused["pause_reason"] == "none"
