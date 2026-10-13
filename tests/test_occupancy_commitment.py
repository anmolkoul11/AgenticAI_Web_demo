"""Closed popup bindings must use current same-frame summaries, not stale values."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_browser_agent import FakeTools, decision

from agentic_web_demo.browser_agent import BrowserAgent
from agentic_web_demo.browser_task import TaskLedger

REQUEST = "3 adults and 2 rooms"
COUNTS = {"adults": "3", "rooms": "2"}


def snapshot(items, document="search"):
    return {
        "url": "https://example.org/" + document,
        "document_id": document,
        "frames": [
            {"text": "Hotel search" if document == "search" else "Hotel results", "controls": items}
        ],
    }


def popup():
    return snapshot(
        [
            {
                "id": "0:" + name,
                "tag": "INPUT",
                "type": "number",
                "name": name,
                "label": name.title(),
                "value": expected,
            }
            for name, expected in COUNTS.items()
        ]
    )


def summary(adults="3", rooms="2", *, frame="0", document="search"):
    return snapshot(
        [
            {
                "id": frame + ":summary",
                "tag": "BUTTON",
                "type": "button",
                "label": f"Select occupancy: {adults} adults · 0 children · {rooms} rooms",
            }
        ],
        document,
    )


def requirement(name):
    return {
        "name": name,
        "expected": COUNTS[name],
        "application": "form",
        "request_quote": COUNTS[name] + " " + name,
        "control_id": "0:" + name,
    }


def task(fresh=None):
    fresh = fresh or popup()
    ledger = TaskLedger(REQUEST)
    ledger.declare(
        [SimpleNamespace(model_dump=lambda name=name: requirement(name)) for name in COUNTS], fresh
    )
    ledger.observe(fresh)
    return ledger


@pytest.mark.parametrize("tag", ["INPUT", "BUTTON"])
def test_closed_bound_quantities_use_current_committed_header_summary(tag):
    fresh = popup()
    if tag == "BUTTON":
        for field in fresh["frames"][0]["controls"]:
            field.update(
                tag="BUTTON",
                type="button",
                role="button",
                value="",
                counter={
                    "label": field["label"],
                    "value": int(COUNTS[field["name"]]),
                    "direction": "increase",
                    "evidence": field["label"] + " quantity",
                },
            )
    ledger = task(fresh)
    results = ledger.observe(summary())["requirements"]
    assert all(check["status"] == "verified" for check in results)
    assert [check["observed"] for check in results] == ["3", "2"]
    assert not ledger.pending()


def test_closed_bound_children_quantity_uses_explicit_same_frame_summary():
    fresh = snapshot(
        [
            {
                "id": "0:children",
                "tag": "INPUT",
                "type": "number",
                "name": "children",
                "label": "Children",
                "value": "0",
            }
        ]
    )
    ledger = TaskLedger("0 children")
    ledger.declare(
        [
            SimpleNamespace(
                model_dump=lambda: {
                    "name": "children",
                    "expected": "0",
                    "application": "form",
                    "request_quote": "0 children",
                    "control_id": "0:children",
                }
            )
        ],
        fresh,
    )
    ledger.observe(fresh)
    check = ledger.observe(summary())["requirements"][0]
    assert check["status"] == "verified" and check["observed"] == "0"


def test_stale_header_is_a_mismatch_not_old_popup_verification():
    results = task().observe(summary("2", "1"))["requirements"]
    assert all(check["status"] == "mismatch" for check in results)
    assert [check["observed"] for check in results] == ["2", "1"]


@pytest.mark.parametrize("fresh", [snapshot([]), summary(frame="1"), summary(document="other")])
def test_missing_wrong_frame_or_new_document_header_cannot_verify_closed_binding(fresh):
    ledger = task()
    results = ledger.observe(fresh)["requirements"]
    assert ledger.pending() == ["adults", "rooms"]
    assert all(check["observed"] is None for check in results)


def test_duplicate_bound_controls_remain_ambiguous_despite_matching_header():
    fresh = popup()
    ledger = task(fresh)
    duplicate = deepcopy(fresh["frames"][0]["controls"][0])
    duplicate["id"] = "0:duplicate"
    fresh["frames"][0]["controls"].extend([duplicate, *summary()["frames"][0]["controls"]])
    adult = ledger.observe(fresh)["requirements"][0]
    assert adult["status"] == "pending" and "ambiguous" in adult["evidence"]


def test_present_bound_native_mismatch_is_not_overridden_by_matching_header():
    fresh = popup()
    ledger = task(fresh)
    fresh["frames"][0]["controls"][0]["value"] = "2"
    fresh["frames"][0]["controls"].extend(summary()["frames"][0]["controls"])
    adult = ledger.observe(fresh)["requirements"][0]
    assert adult["status"] == "mismatch" and adult["observed"] == "2"


def test_visible_counter_and_committed_header_conflict_remains_pending():
    fresh = popup()
    adult = fresh["frames"][0]["controls"][0]
    adult.update(
        tag="BUTTON",
        type="button",
        value="",
        role="button",
        counter={"label": "Adults", "value": 3, "direction": "increase", "evidence": "Adults 3"},
    )
    ledger = task(fresh)
    fresh["frames"][0]["controls"].extend(summary("2")["frames"][0]["controls"])
    result = ledger.observe(fresh)["requirements"][0]
    assert result["status"] == "pending" and result["summary_confirmation_pending"]


def test_search_result_document_keeps_verified_pre_submit_occupancy_evidence():
    ledger = task()
    before = summary()
    ledger.observe(before)
    after = snapshot([], document="results")
    assert ledger.submitted(before, after, before["url"])
    assert all(
        check["method"] == "verified_pre_submit_form"
        for check in ledger.observe(after)["requirements"]
    )


def test_graph_closes_bound_popup_then_submits_and_captures_without_rebind_call():
    class PopupTools(FakeTools):
        state = "popup"

        def observe(self):
            self.events.append("observe")
            fresh = popup() if self.state == "popup" else summary()
            fresh["frames"][0]["controls"] += [
                {"id": "0:done", "tag": "BUTTON", "type": "button", "label": "Done"},
                {
                    "id": "0:search",
                    "tag": "BUTTON",
                    "type": "submit",
                    "label": "Search",
                    "submits_form": True,
                },
            ]
            if self.state == "results":
                fresh = snapshot([], document="results")
            self.references = {c["id"]: (None, None, c) for c in fresh["frames"][0]["controls"]}
            return fresh

        def execute(self, action):
            outcome = super().execute(action)
            self.state = "form" if action.control_id == "0:done" else "results"
            return outcome

    class Model:
        def __init__(self):
            self.actions = iter(
                [
                    decision(
                        "click",
                        "0:done",
                        purpose="set_field",
                        requirements=[requirement(name) for name in COUNTS],
                    ),
                    decision("click", "0:search", purpose="submit_search"),
                    decision("finish"),
                ]
            )

        def decide(self, payload, timeout):
            return next(self.actions)

    report = BrowserAgent(PopupTools(), Model(), REQUEST).run()
    assert report["status"] == "ready" and report["calls"] == 3
    assert report["actions"][1]["status"] == "search_transition_observed"
    assert all(check["status"] == "verified" for check in report["task_checklist"]["requirements"])
