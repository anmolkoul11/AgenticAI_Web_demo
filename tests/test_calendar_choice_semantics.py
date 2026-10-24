"""Calendar ownership and selection evidence; fixtures only, no browser/model."""

from datetime import date
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_task import TaskLedger


TASK = (
    "Find hotels in New York with check-in 2026-11-28 and check-out 2026-11-30 "
    "for 3 adults and 2 rooms."
)


def ledger():
    return TaskLedger(TASK, reference_date=date(2026, 10, 19))


def day(control_id, *, owner="0:cell", tag="SPAN", role="checkbox", **extra):
    return {
        "id": control_id, "tag": tag, "role": role,
        "label": "Saturday, November 28, 2026", "date": "2026-11-28",
        "enabled": True, "selected": "false", "date_owner_id": owner, **extra,
    }


def observation(*items, summary="Select dates Check-in date — Check-out date"):
    return {
        "url": "https://example.org/", "document_id": "calendar-document",
        "frames": [{"controls": [
            {"id": "0:summary", "tag": "BUTTON", "label": summary, "text": summary},
            *items,
        ]}],
    }


def choices(*items):
    return ledger().observe(observation(*items))["visible_date_choices"]


def test_same_gridcell_prefers_inner_selectable_date_over_wrapper():
    rows = choices(day("0:cell", tag="TD", role="gridcell"), day("0:day"))
    assert [row["control_id"] for row in rows] == ["0:day"]


def test_same_gridcell_prefers_native_button_and_ignores_disabled_choices():
    rows = choices(
        day("0:cell", tag="TD", role="gridcell"), day("0:day"),
        day("0:disabled", tag="BUTTON", role="", enabled=False),
        day("0:native", tag="BUTTON", role=""),
    )
    assert [row["control_id"] for row in rows] == ["0:native"]


def test_owned_native_checkbox_is_a_date_choice_but_date_input_is_not():
    rows = choices(
        day("0:cell", tag="TD", role="gridcell"),
        day("0:native", tag="INPUT", role="", type="checkbox"),
        day("0:field", tag="INPUT", role="", type="date", owner=None),
    )
    assert [row["control_id"] for row in rows] == ["0:native"]


def test_equal_dates_in_separate_widgets_are_not_merged():
    rows = choices(day("0:first", owner="0:first-cell"), day("0:second", owner="0:second-cell"))
    assert [row["control_id"] for row in rows] == ["0:first", "0:second"]


def test_equal_local_owner_ids_in_separate_frames_are_not_merged():
    rows = choices(day("0:first", owner="cell"), day("1:second", owner="cell"))
    assert [row["control_id"] for row in rows] == ["0:first", "1:second"]


def test_equal_priority_controls_remain_ambiguous():
    rows = choices(
        day("0:cell", tag="TD", role="gridcell"), day("0:first"), day("0:second"),
    )
    assert [row["control_id"] for row in rows] == ["0:first", "0:second"]


def test_legacy_unowned_choices_are_not_deduplicated_by_date_or_label():
    rows = choices(day("0:cell", owner=None, tag="TD", role="gridcell"), day("0:day", owner=None))
    assert [row["control_id"] for row in rows] == ["0:cell", "0:day"]


@pytest.mark.parametrize("selection_status", ["selected", "already_selected"])
def test_selected_date_only_grounds_year_until_fresh_form_readback(selection_status):
    task = ledger()
    facts = day("0:day", selected="true")
    observed = observation(facts)
    task.observe(observed)
    task.remember_action(
        facts, {"status": "action_performed", "calendar": {
            "status": selection_status, "date": "2026-11-28",
            "dispatched": selection_status != "already_selected",
        }}, SimpleNamespace(action="click"), observed,
    )
    assert "2026-11-28" in task.date_choices
    task.observe(observed)
    assert {"check_in", "check_out"} <= set(task.pending())
    task.observe(observation(facts, summary="Select dates Sat, Nov 28 — Check-out date"))
    assert "check_in" not in task.pending()
    assert "check_out" in task.pending()


@pytest.mark.parametrize("selection_status", ["changed", "unconfirmed"])
def test_calendar_change_without_selected_readback_does_not_ground_date(selection_status):
    task = ledger()
    facts = day("0:day")
    observed = observation(facts)
    task.observe(observed)
    task.remember_action(
        facts, {"status": "action_performed", "calendar": {"status": selection_status}},
        SimpleNamespace(action="click"), observed,
    )
    assert not task.date_choices
    assert {"check_in", "check_out"} <= set(task.pending())


def test_unconfirmed_executor_outcome_does_not_ground_date():
    task = ledger()
    facts = day("0:day")
    observed = observation(facts)
    task.observe(observed)
    task.remember_action(
        facts, {"status": "value_mismatch", "calendar": {"status": "unconfirmed"}},
        SimpleNamespace(action="click"), observed,
    )
    assert not task.date_choices
