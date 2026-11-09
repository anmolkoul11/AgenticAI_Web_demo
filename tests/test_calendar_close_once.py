"""Calendar closure uses fresh expanded controls and bounded fallback input."""

import copy

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_context import calendar_completion
from test_browser_agent import FakeDecider, FakeTools
from test_stay_task_transition import PROMPT, displayed_stay


def open_calendar():
    page = displayed_stay(calendar_open=True)
    page["document_id"] = "same-hotel-document"
    fields = page["frames"][0]["controls"]
    opener = next(item for item in fields if item.get("date_endpoint") == "check_in")
    opener["expanded"] = "true"
    fields[3].update(label="5 adults, 0 children, 3 rooms", text="")
    return page, opener["id"]


def verified_dates():
    return {"requirements": [
        {"field": "check_in", "expected": "2026-12-28", "status": "verified"},
        {"field": "check_out", "expected": "2026-12-30", "status": "verified"},
    ]}


def test_expanded_opener_toggle_precedes_escape_after_dates_are_verified():
    page, opener = open_calendar()
    close = calendar_completion(page, verified_dates())
    assert close["next_action"] == {"action": "click", "control_id": opener, "value": ""}
    assert close["close_actions"][-1]["action"] == "press"
    assert close["close_actions"][-1]["value"] == "Escape"


def test_closed_or_unknown_date_opener_is_never_clicked_to_close_a_calendar():
    page, opener = open_calendar()
    for item in page["frames"][0]["controls"]:
        if item["id"] == opener:
            item["expanded"] = "false"
    close = calendar_completion(page, verified_dates())
    assert all(action["action"] == "press" for action in close["close_actions"])


def test_ignored_calendar_close_inputs_are_not_repeated_or_sent_to_model():
    class UnchangedCalendar(FakeTools):
        def observe(self):
            page, _ = open_calendar()
            self.references = {item["id"]: (None, None, copy.deepcopy(item))
                               for item in page["frames"][0]["controls"]}
            return page

        def execute(self, action):
            self.events.append((action.action, action.control_id, action.value))
            return {"status": "action_performed"}

    tools = UnchangedCalendar()
    report = BrowserAgent(tools, FakeDecider([]), PROMPT).run()
    assert report["status"] == "paused" and report["calls"] == 0
    assert [action[0] for action in tools.events] == ["click", "press"]
    assert "calendar did not close" in report["guidance"]

