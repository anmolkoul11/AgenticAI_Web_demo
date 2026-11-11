"""Two-month calendars need observed arrows before off-screen date selection."""

from calendar import monthrange

import pytest

from agentic_web_demo.browser_context import build_navigation_context, calendar_navigation
from agentic_web_demo.browser_task import TaskLedger
from test_stay_task_transition import displayed_stay


def month_window(first_year, first_month):
    page = displayed_stay()
    fields = page["frames"][0]["controls"]
    for offset in range(2):
        index = first_year * 12 + first_month - 1 + offset
        year, month = index // 12, index % 12 + 1
        fields.extend({"id": f"0:d-{year}-{month}-{day}", "tag": "BUTTON", "type": "button",
                       "label": f"{year}-{month:02d}-{day:02d}", "date": f"{year}-{month:02d}-{day:02d}",
                       "date_kind": "day_choice", "date_widget_id": "calendar:0"}
                      for day in range(1, monthrange(year, month)[1] + 1))
    fields.extend({"id": "0:" + direction, "tag": "BUTTON", "type": "button", "label": "",
                   "date_navigation": direction, "date_widget_id": "calendar:0"}
                  for direction in ("previous", "next"))
    return page


@pytest.mark.parametrize("year,month,target,direction", [
    (2026, 11, "2027-02", "next"), (2027, 2, "2027-01", "previous"),
    (2026, 11, "2026-12", None),
])
def test_observed_month_window_controls_direction_across_year_boundary(year, month, target, direction):
    prompt = f"Find hotels in New York from {target}-26 to {target}-28 with 4 adults and 3 rooms"
    page = month_window(year, month)
    task = TaskLedger(prompt)
    state = task.observe(page)
    navigation = calendar_navigation(page, state)
    if direction is None:
        assert navigation is None
    else:
        assert navigation["next_action"]["control_id"] == "0:" + direction
        context = build_navigation_context({"task": prompt, "observation": page,
                                            "task_checklist": state, "recent_actions": []})
        assert context["interaction_focus"]["phase"] == "navigate_calendar"
        assert context["interaction_focus"]["control_ids"] == ["0:" + direction]


def test_spillover_days_do_not_make_a_third_month_look_available():
    page = month_window(2026, 11)
    page["frames"][0]["controls"].extend({
        "id": f"0:spill-{day}", "date": f"2027-01-{day:02d}",
        "date_kind": "day_choice", "date_widget_id": "calendar:0",
    } for day in range(1, 5))
    task = TaskLedger("Find hotels in New York from 2027-01-28 to 2027-01-30")
    assert calendar_navigation(page, task.observe(page))["next_action"]["control_id"] == "0:next"


def test_disabled_or_unscoped_arrows_are_not_used():
    page = month_window(2026, 11)
    page["frames"][0]["controls"][-1]["enabled"] = False
    page["frames"][0]["controls"].append({"id": "0:carousel", "date_navigation": "next"})
    task = TaskLedger("Find hotels in New York from 2027-01-28 to 2027-01-30")
    assert calendar_navigation(page, task.observe(page)) is None

