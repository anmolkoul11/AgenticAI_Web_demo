"""A new stay request must replace prior criteria before guest readback."""

from datetime import date

import pytest

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_context import build_navigation_context
from agentic_web_demo.browser_navigation import guest_counts, occupancy_summary_values
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.stay_scope import destination_matches, observed_result_scope
from test_browser_agent import FakeDecider, FakeTools, decision
from test_same_page_result_handoff import hotel_results


PROMPT = "find hotels in new york from 28-30 December 2026, with 5 adults only and 3 rooms"


def displayed_stay(*, destination="New York", month=12, panel_open=False, calendar_open=False):
    page = hotel_results(panel_open=panel_open)
    fields = page["frames"][0]["controls"]
    fields[:] = [item for item in fields if item["id"] != "0:site-search"]
    fields[0].update(label="Search", type="search", value=destination)
    for item, endpoint, day in zip(fields[1:3], ("check_in", "check_out"), (28, 30)):
        full = f"2026-{month:02d}-{day}"
        item.update(label=f"Enter the date. The selected date is {full}.", date=full, date_endpoint=endpoint)
    fields[3].update(
        label="Enter the number of rooms and then enter the number of guests. "
              "The selected number of rooms is 3 and the selected number of guests is 5.",
        text="Rooms/Guests 3 Rooms, 5 Guests")
    for item in fields:
        counter = item.get("counter") or {}
        if counter.get("label") in {"Adults", "Children", "Rooms"}:
            value = {"Adults": 5, "Children": 0, "Rooms": 3}[counter["label"]]
            counter.update(value=value, evidence=f"{counter['label']} {value}")
    if calendar_open:
        fields.extend({"id": f"0:day-{day}", "tag": "BUTTON", "type": "button", "date_kind": "day_choice",
                       "date_widget_id": "calendar", "date": f"2026-12-{day}", "label": f"December {day}, 2026"}
                      for day in (28, 30))
    page["results"].update(record_count=70, headings=[{
        "level": 1, "text": "New York City Hotels" if destination == "New York" else destination + " Hotels"}])
    return page


def test_exact_request_parses_december_and_explicit_adults_only():
    task = TaskLedger(PROMPT, reference_date=date(2026, 11, 8))
    assert task.requested_stay["check_in"] == "2026-12-28"
    assert task.requested_stay["check_out"] == "2026-12-30"
    assert guest_counts(PROMPT) == {"adults": 5, "rooms": 3, "children": 0}
    assert guest_counts("5 adults only and 1 child") is None
    assert guest_counts("5 adults and 3 rooms") == {"adults": 5, "rooms": 3}


@pytest.mark.parametrize("summary,expected", [
    ("Rooms/Guests 3 Rooms, 5 Guests", {"rooms": [3], "guests": [5]}),
    ("The selected number of rooms is 3 and the selected number of guests is 4. Rooms/Guests 3 Rooms, 4 Guests",
     {"rooms": [3], "guests": [4]}),
    ("Adults/Children 5 Adults, 0 Children", {"adults": [5], "children": [0]}),
    ("2 adults / children 1", {"adults": [2], "children": [1]}),
    ("Adults 5 Children 0 Rooms 3 Guests 5", {"adults": [5], "children": [0], "rooms": [3], "guests": [5]}),
])
def test_mixed_headings_do_not_supply_a_guest_count(summary, expected):
    assert occupancy_summary_values(summary) == expected


def test_new_york_city_alias_preserves_state_and_other_place_mismatches():
    assert destination_matches("New York", "New York City")
    assert destination_matches("New York", "New York City, New York, United States")
    assert not destination_matches("New York State", "New York City")
    assert not destination_matches("Mexico", "Mexico City")
    task = TaskLedger(PROMPT)
    scope = observed_result_scope(task.requested_stay, displayed_stay(panel_open=True))
    assert scope["status"] == "verified"
    assert next(item for item in scope["fields"] if item["field"] == "destination")["status"] == "verified"


def test_previous_new_jersey_november_stay_does_not_trigger_guest_readback():
    task = TaskLedger(PROMPT)
    page = displayed_stay(destination="New Jersey", month=11)
    task.observe(page)
    assert task.occupancy_recheck(page) is None
    assert not task.adopt_matching_results(page)
    context = build_navigation_context({"task": PROMPT, "observation": page,
                                        "task_checklist": task.snapshot(), "recent_actions": []})
    assert context["interaction_focus"]["phase"] == "prepare_stay"
    assert set(context["interaction_focus"]["fields"]) == {"destination", "check_in", "check_out"}
    assert "0:guests" not in context["interaction_focus"]["control_ids"]


def test_requested_city_link_can_leave_the_previous_city_before_its_dates_are_changed():
    task = TaskLedger(PROMPT)
    page = displayed_stay(destination="New Jersey", month=11)
    choice = {"id": "0:new-city", "tag": "A", "label": "New York City, New York, United States",
              "href": "https://example.org/new-york"}
    page["frames"][0]["controls"].append(choice)
    task.observe(page)
    assert task.discovery_navigation(decision("click", choice["id"]), choice, page)
    assert task.submission is None and task.pending_submission is None


def test_calendar_day_from_previous_month_is_not_authorized_as_a_new_stay_date():
    task = TaskLedger(PROMPT)
    old = {"id": "0:day", "tag": "BUTTON", "date_kind": "day_choice", "date_widget_id": "calendar",
           "date": "2026-11-28", "label": "November 28, 2026"}
    with pytest.raises(WebsiteError, match="not a requested stay date"):
        task.action_value_problem(old, decision("click", "0:day"), displayed_stay(month=11))
    opener = displayed_stay(month=11)["frames"][0]["controls"][1]
    assert task.action_value_problem(opener, decision("click", opener["id"]), displayed_stay(month=11)) is None


@pytest.mark.parametrize("starting_month", [11, 12])
def test_dates_are_corrected_before_one_guest_read_and_capture(starting_month):
    class AppliedTools(FakeTools):
        panel_open = False
        calendar_open = False
        selected = {"0:in": f"2026-{starting_month:02d}-28", "0:out": f"2026-{starting_month:02d}-30"}

        def observe(self):
            page = displayed_stay(panel_open=self.panel_open, calendar_open=self.calendar_open)
            for item in page["frames"][0]["controls"]:
                if item["id"] in self.selected:
                    item.update(date=self.selected[item["id"]],
                                label="Enter the date. The selected date is " + self.selected[item["id"]] + ".")
            self.references = {item["id"]: (None, None, item) for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            assert action.action == "click"
            if action.control_id == "0:in":
                self.calendar_open = True
            elif action.control_id == "0:day-28":
                self.selected["0:in"] = "2026-12-28"
            elif action.control_id == "0:day-30":
                self.selected["0:out"] = "2026-12-30"
                self.calendar_open = False
            else:
                assert action.control_id == "0:guests" and not self.panel_open
                self.panel_open = True
            self.events.append(action.control_id)
            return {"status": "action_performed"}

        def capture(self, kind="page"):
            assert set(self.selected.values()) == {"2026-12-28", "2026-12-30"}
            self.events.append("capture")
            self.pages.append({"url": "https://example.org/hotels", "text": "New York hotel results",
                               "source_kind": kind})

    tools = AppliedTools()
    report = BrowserAgent(tools, FakeDecider([]), PROMPT).run()
    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events == (["0:in", "0:day-28", "0:day-30"] if starting_month == 11 else []) + ["0:guests", "capture"]
