"""Grounded, uniquely observed occupancy operations need no new model plan."""

from copy import deepcopy

from agentic_web_demo.browser_agent import BrowserAgent
from test_browser_agent import FakeDecider, FakeTools


REQUEST = "Find hotels in Edison from November 28-30 2026 for 6 adults and 4 rooms, 0 children."


def planner(*, opened=False, duplicate=False):
    model, tools = FakeDecider([]), FakeTools()
    agent = BrowserAgent(tools, model, REQUEST)
    summary = {"id": "0:guests", "tag": "BUTTON", "type": "button", "role": "button",
               "label": "Number of travelers and rooms. Currently selected: 2 adults · 0 children · 1 room",
               "expanded": "true" if opened else "false", "form_scope": "stay", "enabled": True}
    fields = [summary]
    counter_ids = []
    if opened:
        for direction in ("increase", "decrease"):
            field = {"id": "0:" + direction, "tag": "BUTTON", "type": "button",
                     "label": direction + " Adults", "form_scope": "stay", "enabled": True,
                     "counter": {"label": "Adults", "value": 2, "direction": direction,
                                 "method": "button", "evidence": "Adults 2"}}
            fields.append(field)
            counter_ids.append({"control_id": field["id"], "direction": direction, "enabled": True})
        if duplicate:
            other = deepcopy(fields[1])
            other["id"] = "0:other-increase"
            fields.append(other)
            counter_ids.append({"control_id": other["id"], "direction": "increase", "enabled": True})
    agent.task.checks = [
        {"field": "destination", "expected": "Edison", "status": "verified"},
        {"field": "check_in", "expected": "2026-11-28", "status": "verified"},
        {"field": "check_out", "expected": "2026-11-30", "status": "verified"},
        {"field": "adults", "expected": "6", "status": "pending", "observed": "2",
         "next_action": "set_counter" if opened else "inspect", "counter_controls": counter_ids},
        {"field": "rooms", "expected": "4", "status": "pending", "observed": "1"},
        {"field": "children", "expected": "0", "status": "verified", "observed": "0"},
    ]
    observation = {"url": "https://example.org/hotels", "document_id": "stay-document",
                   "frames": [{"controls": fields, "widgets": []}]}
    tools.references = {field["id"]: (None, None, deepcopy(field)) for field in fields}
    return agent, tools, model, observation


def test_pending_guests_open_once_after_core_form_is_verified():
    agent, tools, model, page = planner()
    action = agent.local_occupancy_action(page)
    assert action.action == "click" and action.control_id == "0:guests"
    assert agent.local_occupancy_action(page) is None
    assert not model.payloads and not tools.events


def test_visible_counter_uses_absolute_requested_target_without_a_paid_decision():
    agent, tools, model, page = planner(opened=True)
    action = agent.local_occupancy_action(page)
    assert action.action == "set_counter" and action.value == "6"
    assert action.control_id == "0:increase" and action.purpose == "set_field"
    assert agent.local_occupancy_action(page) is None
    assert not model.payloads and not tools.events


def test_ambiguous_counter_actuators_keep_the_existing_model_fallback():
    agent, _, _, page = planner(opened=True, duplicate=True)
    assert agent.local_occupancy_action(page) is None


def test_pending_dates_or_open_calendar_prevent_occupancy_planning():
    agent, _, _, page = planner()
    agent.task.checks[2]["status"] = "pending"
    assert agent.local_occupancy_action(page) is None
    agent.task.checks[2]["status"] = "verified"
    page["frames"][0]["controls"].append({"id": "0:day", "date_kind": "day_choice"})
    assert agent.local_occupancy_action(page) is None


def test_unreadable_or_age_controls_are_never_runtime_counter_targets():
    for change in ({"counter": None}, {"label": "Child age", "name": "child_age"}):
        agent, tools, _, page = planner(opened=True)
        tools.references["0:increase"][2].update(change)
        assert agent.local_occupancy_action(page) is None
