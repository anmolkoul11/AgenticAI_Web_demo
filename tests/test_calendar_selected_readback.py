"""Fresh selected endpoints retain their year across the same form's close."""

from copy import deepcopy
from types import SimpleNamespace

from agentic_web_demo.browser_context import calendar_completion
from agentic_web_demo.browser_task import TaskLedger


REQUEST = "Find hotels in Edison from November 28-30 2026 for 6 adults and 4 rooms, 0 children."


def calendar_page(*, opened=True, widget_ids=True):
    controls = [
        {"id": "0:destination", "tag": "INPUT", "type": "text", "label": "Destination",
         "value": "Edison", "form_scope": "0:form:0", "enabled": True},
        {"id": "0:dates", "tag": "BUTTON", "type": "button", "date_kind": "opener",
         "label": "Select dates Sat, Nov 28 — Mon, Nov 30", "expanded": str(opened).lower(),
         "form_scope": "0:form:0", "enabled": True},
    ]
    if opened:
        for field, day in (("check_in", "28"), ("check_out", "30")):
            controls.append({"id": "0:" + field, "tag": "SPAN", "role": "checkbox",
                             "date_kind": "day_choice", "date": "2026-11-" + day,
                             "date_endpoint": field, "selected": "true", "enabled": True,
                             "label": "November " + day + ", 2026, " + field.replace("_", "-"),
                             "form_scope": "0:form:0",
                             **({"date_widget_id": "calendar:0"} if widget_ids else {})})
    return {"url": "https://example.org/hotels", "document_id": "same-document",
            "frames": [{"controls": controls}]}


def date_checks(snapshot):
    return {item["field"]: item for item in snapshot["requirements"]
            if item["field"] in {"check_in", "check_out"}}


def test_fresh_selected_full_dates_survive_close_without_executor_selection_proof():
    task = TaskLedger(REQUEST)
    opened = task.observe(calendar_page())
    assert all(item["status"] == "verified" for item in date_checks(opened).values())
    assert not task.calendar_actions  # No successful click result was invented.
    closed = task.observe(calendar_page(opened=False))
    assert all(item["status"] == "verified" for item in date_checks(closed).values())


def test_year_proof_cannot_transfer_to_another_document_or_changed_destination():
    for change in ("document", "destination"):
        task = TaskLedger(REQUEST)
        task.observe(calendar_page())
        closed = calendar_page(opened=False)
        if change == "document":
            closed["document_id"] = "another-document"
        else:
            closed["frames"][0]["controls"][0]["value"] = "Raleigh"
        assert not all(item["status"] == "verified" for item in date_checks(task.observe(closed)).values())


def test_date_or_destination_edit_invalidates_the_affected_selected_year_proof():
    for target in ("0:destination", "0:check_in", "0:check_out"):
        task = TaskLedger(REQUEST)
        page = calendar_page()
        task.observe(page)
        control = next(item for item in page["frames"][0]["controls"] if item["id"] == target)
        action = "fill" if target == "0:destination" else "click"
        task.before_action(control, SimpleNamespace(action=action, value="Edison"), page)
        assert "2026-11-30" not in task.date_choices
        if target != "0:check_out":
            assert not task.date_choices


def test_conflicting_selected_endpoint_cannot_supply_the_old_checkout_year():
    task = TaskLedger(REQUEST)
    task.observe(calendar_page())
    changed = calendar_page()
    end = changed["frames"][0]["controls"][-1]
    end.update(date="2026-11-29", label="November 29, 2026, Check-out date")
    task.observe(changed)
    assert "2026-11-30" not in task.date_choices
    assert date_checks(task.observe(calendar_page(opened=False)))["check_out"]["status"] != "verified"


def test_roleless_or_two_pane_calendar_can_close_only_its_unique_form_opener():
    for widgets in (False, True):
        page = calendar_page(widget_ids=widgets)
        if widgets:
            page["frames"][0]["controls"][-1]["date_widget_id"] = "calendar:1"
        task = TaskLedger(REQUEST)
        close = calendar_completion(page, task.observe(page))
        assert close["close_actions"] == [{"action": "click", "control_id": "0:dates", "value": ""}]
        unrelated = deepcopy(page)
        unrelated["frames"][0]["controls"][-1]["form_scope"] = "0:another-form"
        assert calendar_completion(unrelated, task.snapshot()) is None
