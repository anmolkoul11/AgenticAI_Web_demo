"""Completion and context regressions; mocked decisions, no live model/site calls."""

import hashlib
import json
from datetime import date
from types import SimpleNamespace

import pytest
from test_browser_agent import FakeDecider, FakeTools, decision, occupancy_markup, tools_for
from test_browser_agent import agent_page as shared_page

from agentic_web_demo import browser_agent, custom_extract
from agentic_web_demo.browser_agent import BrowserAgent, BrowserDecision, BrowserRequirement
from agentic_web_demo.browser_dates import resolve_stay_dates
from agentic_web_demo.browser_task import TaskLedger, compact_observation
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.custom_service import capture_summary

TASK = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 3 adults and 2 rooms."
)


def form_observation(adults="3", rooms="2", dates=True):
    values = [
        ("Destination", "New York"),
        ("Check-in", "2026-10-28" if dates else ""),
        ("Check-out", "2026-10-30" if dates else ""),
        ("Adults", adults),
        ("Rooms", rooms),
    ]
    return {
        "url": "https://example.org/",
        "document_id": "start",
        "frames": [
            {
                "text": "Hotel search",
                "controls": [
                    {"id": f"0:{i}", "tag": "INPUT", "type": "text", "label": label, "value": value}
                    for i, (label, value) in enumerate(values)
                ],
            }
        ],
    }


class SearchResultTools(FakeTools):
    """Checked form and result snapshots, without a browser or model transport."""

    def __init__(self, *, adults="3", delayed=False):
        super().__init__()
        self.adults = adults
        self.submitted = False
        self.response_ready = not delayed
        self.references = {
            "0:search": (None, None, {"tag": "BUTTON", "label": "Search"}),
            "0:3": (None, None, {"tag": "INPUT", "type": "text", "label": "Adults"}),
        }

    def observe(self):
        self.events.append("observe")
        if self.submitted and self.response_ready:
            return {
                "url": "https://example.org/results",
                "document_id": "results",
                "frames": [
                    {
                        "text": "Hotel results: Budget Hotel 300 USD; Other Hotel 500 USD",
                        "controls": [],
                    }
                ],
            }
        return form_observation(adults=self.adults)

    def execute(self, action):
        outcome = super().execute(action)
        if action.action == "click" and action.control_id == "0:search":
            self.submitted = True
        elif action.action == "fill" and action.control_id == "0:3":
            self.adults = action.value
        elif action.action == "wait":
            self.response_ready = True
        return outcome

    def capture(self, kind="page"):
        super().capture(kind)
        self.pages[0].update(
            url="https://example.org/results",
            text="Hotel results: Budget Hotel 300 USD; Other Hotel 500 USD",
            browser_task_context=self.collection_context,
        )


class FastHotelTools(FakeTools):
    """Dynamic autocomplete/calendar/counters, with no external browser or model."""

    def __init__(self):
        super().__init__()
        self.destination = ""
        self.destination_open = False
        self.destination_committed = False
        self.calendar_open = False
        self.dates = {}
        self.occupancy_open = False
        self.counts = {"adults": 2, "rooms": 1}
        self.summary_counts = dict(self.counts)
        self.submitted = False
        self.executed_controls = []

    def observe(self):
        self.events.append("observe")
        if self.submitted:
            return {
                "url": "https://example.org/results",
                "document_id": "results",
                "frames": [{"text": "Budget Hotel 300 USD; Other Hotel 500 USD", "controls": []}],
            }
        date_parts = [
            "Oct 28" if "check_in" in self.dates else "Check-in date",
            "Oct 30" if "check_out" in self.dates else "Check-out date",
        ]
        fields = [
            {
                "id": "0:destination",
                "tag": "INPUT",
                "type": "text",
                "role": "combobox",
                "name": "destination",
                "label": "Enter destination",
                "value": self.destination,
                "selection_required": True,
                "expanded": str(self.destination_open).lower(),
                "option_ids": ["0:city", "0:ai"] if self.destination_open else [],
            },
            {
                "id": "0:calendar",
                "tag": "BUTTON",
                "type": "button",
                "label": "Select dates Check-in date — Check-out date",
                "text": " — ".join(date_parts),
                "expanded": str(self.calendar_open).lower(),
            },
            {
                "id": "0:occupancy",
                "tag": "BUTTON",
                "type": "button",
                "label": f"Number of travelers and rooms. Currently selected: "
                f"{self.summary_counts['adults']} adults, 0 children, "
                f"{self.summary_counts['rooms']} rooms",
                "expanded": str(self.occupancy_open).lower(),
            },
            {"id": "0:search", "tag": "BUTTON", "type": "submit", "label": "Search"},
        ]
        if self.destination_open:
            fields.extend(
                [
                    {
                        "id": "0:city",
                        "tag": "BUTTON",
                        "type": "button",
                        "role": "option",
                        "label": "New York New York, United States of America",
                        "text": "New York\nNew York, United States of America",
                        "option_primary": "New York",
                    },
                    {
                        "id": "0:ai",
                        "tag": "BUTTON",
                        "type": "button",
                        "role": "option",
                        "label": "New York Search with AI",
                        "option_primary": "New York",
                    },
                ]
            )
        if self.calendar_open:
            fields.extend(
                {
                    "id": f"0:{name}",
                    "tag": "BUTTON",
                    "type": "button",
                    "role": "gridcell",
                    "label": value,
                    "date": value,
                }
                for name, value in (("check_in", "2026-10-28"), ("check_out", "2026-10-30"))
            )
        if self.occupancy_open:
            for name, value in self.counts.items():
                for direction in ("decrease", "increase"):
                    fields.append(
                        {
                            "id": f"0:{name}-{direction}",
                            "tag": "BUTTON",
                            "type": "button",
                            "label": f"{direction} {name}",
                            "counter": {
                                "label": name.title(),
                                "value": value,
                                "direction": direction,
                                "method": "button",
                                "evidence": f"{name.title()} {value}",
                            },
                        }
                    )
            fields.append({"id": "0:done", "tag": "BUTTON", "type": "button", "label": "Done"})
        self.references = {field["id"]: (None, None, field) for field in fields}
        return {
            "url": "https://example.org/",
            "document_id": "start",
            "frames": [{"text": "Prepare a hotel search", "controls": fields}],
        }

    def execute(self, action):
        self.events.append(action.action)
        self.executed_controls.append(action.control_id)
        if action.action == "fill":
            assert action.control_id == "0:destination"
            self.destination = action.value
            self.destination_open = True
            return {"status": "value_verified", "expected": action.value, "observed": action.value}
        if action.action == "set_counter":
            name = action.control_id.split(":", 1)[1].split("-", 1)[0]
            self.counts[name] = int(action.value)
            return {
                "status": "counter_verified",
                "expected": int(action.value),
                "observed": self.counts[name],
            }
        assert action.action == "click"
        if action.control_id == "0:city":
            self.destination = "New York, New York, United States of America"
            self.destination_open = False
            self.destination_committed = True
            self.calendar_open = True  # Selecting the city auto-opens the calendar.
        elif action.control_id in {"0:check_in", "0:check_out"}:
            name = action.control_id.split(":", 1)[1]
            self.dates[name] = "2026-10-28" if name == "check_in" else "2026-10-30"
            if name == "check_out":
                self.calendar_open = False
        elif action.control_id == "0:occupancy":
            self.occupancy_open = True
        elif action.control_id == "0:done":
            self.summary_counts = dict(self.counts)
            self.occupancy_open = False
        elif action.control_id == "0:search":
            assert self.destination_committed
            assert self.dates == {"check_in": "2026-10-28", "check_out": "2026-10-30"}
            assert self.summary_counts == self.counts == {"adults": 3, "rooms": 2}
            self.submitted = True
        else:
            raise AssertionError(f"Unexpected fake control: {action.control_id}")
        return {"status": "action_performed"}

    def capture(self, kind="page"):
        assert self.submitted
        self.events.append("capture")
        self.pages = [
            {
                "url": "https://example.org/results",
                "source_kind": kind,
                "text": "Budget Hotel 300 USD per night; Other Hotel 500 USD per night",
                "browser_task_context": self.collection_context,
            }
        ]


class ScopedFastHotelTools(FastHotelTools):
    """Actual-form association separates the submit from a distracting catalogue link."""

    def observe(self):
        fresh = super().observe()
        if self.submitted:
            fresh["results"] = {"record_count": 2, "busy": False, "no_results": False}
            return fresh
        fields = fresh["frames"][0]["controls"]
        for field in fields:
            if field["id"] in {"0:destination", "0:calendar", "0:occupancy", "0:search"}:
                field["form_scope"] = "0:form:0"
        next(field for field in fields if field["id"] == "0:search")["submits_form"] = True
        fields.append(
            {
                "id": "0:catalogue",
                "tag": "A",
                "label": "New York hotels",
                "href": "https://example.org/city/new-york",
            }
        )
        self.references = {field["id"]: (None, None, field) for field in fields}
        return fresh


class ScopedReadyHotelTools(SearchResultTools):
    """Already-filled native inputs and real form-submit metadata, not a browser."""

    def __init__(
        self,
        *,
        adults="3",
        search_scope="0:form:0",
        search_label="Search",
        duplicate_submit=False,
        busy=False,
    ):
        super().__init__(adults=adults)
        self.search_scope = search_scope
        self.search_label = search_label
        self.duplicate_submit = duplicate_submit
        self.busy = busy

    def observe(self):
        fresh = super().observe()
        fields = fresh["frames"][0]["controls"]
        if self.submitted:
            fresh["results"] = {"record_count": 2, "busy": self.busy, "no_results": False}
        else:
            for field in fields:
                field["form_scope"] = "0:form:0"
            fields.extend(
                [
                    {
                        "id": "0:search",
                        "tag": "BUTTON",
                        "type": "submit",
                        "submits_form": True,
                        "label": self.search_label,
                        "form_scope": self.search_scope,
                    },
                    {
                        "id": "0:catalogue",
                        "tag": "A",
                        "label": "New York hotels",
                        "href": "https://example.org/city/new-york",
                    },
                ]
            )
            if self.duplicate_submit:
                fields.append({**fields[-2], "id": "0:second-search"})
        self.references = {field["id"]: (None, None, field) for field in fields}
        return fresh


def test_seven_paid_widget_steps_with_local_fill_submit_and_capture_avoid_catalogue():
    tools = ScopedFastHotelTools()
    model = FakeDecider(
        [
            decision("click", "0:city", purpose="set_field"),
            decision("click", "0:check_in", purpose="set_field"),
            decision("click", "0:check_out", purpose="set_field"),
            decision("click", "0:occupancy", purpose="set_field"),
            decision("set_counter", "0:adults-increase", "3", purpose="set_field"),
            decision("set_counter", "0:rooms-increase", "2", purpose="set_field"),
            decision("click", "0:done", purpose="set_field"),
            # Known fill, Search and capture must not incur extra paid decisions.
            decision("click", "0:catalogue", purpose="navigate"),
        ]
    )
    agent = BrowserAgent(tools, model, TASK, max_calls=7)
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == len(model.payloads) == 7
    assert report["actions"][0]["action"] == "fill"
    assert report["actions"][0]["decision_origin"] == "runtime"
    assert tools.executed_controls.count("0:search") == 1 and tools.submitted
    assert "0:catalogue" not in tools.executed_controls
    assert len(report["actions"]) == 10
    assert [entry["action"] for entry in report["actions"]][-2:] == ["click", "finish"]
    assert [entry["status"] for entry in report["actions"]][-2:] == [
        "search_transition_observed",
        "source_collection_ready",
    ]
    source = agent.captured_sources()[0]
    assert source["url"] == "https://example.org/results"
    assert "300 USD" in source["text"] and "500 USD" in source["text"]
    context = source["browser_task_context"]
    assert context["status"] == "form_verified_search_submitted"
    assert not context["availability_verified"] and not context["record_values_verified"]
    assert {item["field"]: item["observed"] for item in context["requirements"]} == {
        "destination": "New York, New York, United States of America",
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "adults": "3",
        "rooms": "2",
    }


def test_prepared_native_listing_form_needs_no_paid_terminal_decisions():
    tools = ScopedReadyHotelTools()
    model = FakeDecider([])
    agent = BrowserAgent(tools, model, TASK, max_calls=0)
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == 0
    assert model.payloads == [] and tools.events.count("click") == 1
    assert tools.events.count("capture") == 1 and len(report["actions"]) == 2
    assert report["task_checklist"]["collection_mode"] == "listing_results"
    source = agent.captured_sources()[0]
    assert source["browser_task_context"]["status"] == "form_verified_search_submitted"
    assert "300 USD" in source["text"] and "500 USD" in source["text"]


@pytest.mark.parametrize(
    "changes",
    [
        {"adults": "2"},
        {"search_scope": "0:form:1"},
        {"search_scope": ""},
        {"duplicate_submit": True},
        {"search_label": "Pay now"},
    ],
)
def test_local_submission_requires_complete_unique_retrieval_control_in_the_right_form(changes):
    tools = ScopedReadyHotelTools(**changes)
    model = FakeDecider([decision("pause", evidence="Inspect the current form before continuing.")])
    report = BrowserAgent(tools, model, TASK).run()

    assert report["status"] == "paused" and report["calls"] == 1
    assert len(model.payloads) == 1 and tools.events.count("click") == 0
    assert not tools.submitted and not tools.pages
    assert not report["task_checklist"]["search_submitted"]


def test_prepared_hotel_controls_do_not_take_over_a_generic_news_task():
    tools = ScopedReadyHotelTools()
    model = FakeDecider([decision("pause", evidence="The current page is not the requested news.")])
    report = BrowserAgent(tools, model, "Find soccer headlines and open relevant stories").run()

    assert report["status"] == "paused" and report["calls"] == 1
    assert report["task_checklist"]["collection_mode"] != "listing_results"
    assert tools.events.count("click") == 0 and tools.events.count("capture") == 0


@pytest.mark.parametrize("association", ["role", "owned_ids"])
def test_autocomplete_suggestion_is_not_a_local_native_submit(association):
    tools = ScopedReadyHotelTools()
    observe = tools.observe

    def suggestion_not_submit():
        fresh = observe()
        fields = fresh["frames"][0]["controls"]
        search = next(item for item in fields if item["id"] == "0:search")
        if association == "role":
            search["role"] = "option"
        else:
            fields[0]["option_ids"] = [search["id"]]
        return fresh

    tools.observe = suggestion_not_submit
    model = FakeDecider([decision("pause", evidence="Review the actual search control.")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert not tools.submitted and tools.events.count("click") == 0


def test_destination_selection_identity_cannot_cross_actual_form_owners():
    ledger = TaskLedger(TASK)
    observed = {"url": "https://example.org/", "document_id": "form"}
    first = {"id": "0:1", "tag": "INPUT", "name": "ss", "form_scope": "0:form:0"}
    second = {**first, "id": "0:2", "form_scope": "0:form:1"}
    assert ledger.destination_key(first, observed) != ledger.destination_key(second, observed)


def test_explicit_linked_hotel_details_do_not_auto_finish_at_the_result_index():
    tools = ScopedReadyHotelTools()
    model = FakeDecider(
        [
            decision("click", "0:search", purpose="submit_search"),
            decision("pause", evidence="Linked hotel detail pages still need to be collected."),
        ]
    )
    report = BrowserAgent(
        tools, model, TASK + " Open the linked hotel detail pages and include room descriptions."
    ).run()

    assert report["status"] == "paused" and report["calls"] == 2
    assert report["task_checklist"]["collection_mode"] == "linked_details"
    assert tools.submitted and tools.events.count("click") == 1
    assert tools.events.count("capture") == 0 and not tools.pages


def test_local_search_rechecks_form_association_before_any_click():
    tools = ScopedReadyHotelTools()
    observe = tools.observe

    def moved_submit():
        if tools.events.count("observe"):
            tools.search_scope = "0:form:1"
        return observe()

    tools.observe = moved_submit
    model = FakeDecider([])
    report = BrowserAgent(tools, model, TASK, max_calls=0).run()

    assert report["status"] == "paused" and report["calls"] == 0
    assert tools.events.count("click") == 0 and not tools.submitted
    assert not tools.pages and not model.payloads


def test_local_search_rechecks_unique_native_candidate_before_any_click():
    tools = ScopedReadyHotelTools()
    observe = tools.observe

    def duplicate_appears():
        if tools.events.count("observe"):
            tools.duplicate_submit = True
        return observe()

    tools.observe = duplicate_appears
    model = FakeDecider([])
    report = BrowserAgent(tools, model, TASK, max_calls=0).run()

    assert report["status"] == "paused" and report["calls"] == 0
    assert tools.events.count("click") == 0 and not tools.submitted
    assert not tools.pages and model.payloads == []
    assert len(report["task_checklist"]["submission_candidates"]) == 2
    assert report["actions"][0]["status"] == "not_completed"


def test_unknown_result_structure_can_finish_with_one_model_decision_after_local_search():
    tools = ScopedReadyHotelTools()
    observe = tools.observe

    def unknown_result_structure():
        fresh = observe()
        if tools.submitted:
            fresh["results"] = {"record_count": 0, "busy": False, "no_results": False}
        return fresh

    tools.observe = unknown_result_structure
    model = FakeDecider(
        [decision("finish", evidence="The searched page displays hotel names and prices as text.")]
    )
    agent = BrowserAgent(tools, model, TASK, max_calls=1)
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == len(model.payloads) == 1
    assert tools.submitted and tools.events.count("click") == 1
    assert tools.events.count("capture") == 1
    assert [entry["action"] for entry in report["actions"]] == ["click", "finish"]
    assert [entry["decision_origin"] for entry in report["actions"]] == ["runtime", "model"]
    assert model.payloads[0]["task_checklist"]["search_submitted"]
    assert model.payloads[0]["interaction_focus"]["phase"] == "collect_results"
    assert "300 USD" in model.payloads[0]["observation"]["frames"][0]["text"]
    source = agent.captured_sources()[0]
    assert "300 USD" in source["text"] and "500 USD" in source["text"]
    assert source["browser_task_context"]["status"] == "form_verified_search_submitted"
    assert not source["browser_task_context"]["availability_verified"]


def test_confirmed_search_with_busy_results_does_not_auto_capture_unfinished_content():
    tools = ScopedReadyHotelTools(busy=True)
    model = FakeDecider([])
    report = BrowserAgent(tools, model, TASK, max_calls=0).run()

    assert report["status"] == "paused" and report["calls"] == 0
    assert tools.submitted and tools.events.count("click") == 1
    assert tools.events.count("capture") == 0 and not tools.pages
    assert model.payloads == []


@pytest.mark.parametrize("interruption", ["mfa", "cancel"])
def test_local_result_handoff_still_stops_for_sign_in_or_cancellation(interruption):
    tools = ScopedReadyHotelTools()
    observe = tools.observe

    def interrupted_result():
        fresh = observe()
        if tools.submitted:
            if interruption == "mfa":
                fresh["frames"][0]["password_or_code_visible"] = True
            else:
                tools.allowed = False
        return fresh

    tools.observe = interrupted_result
    model = FakeDecider([])
    report = BrowserAgent(tools, model, TASK, max_calls=0).run()

    assert report["status"] == "paused" and report["calls"] == 0
    assert tools.events.count("click") == 1 and tools.events.count("capture") == 0
    assert not tools.pages and model.payloads == []


def test_normalized_request_and_dynamic_widgets_complete_search_within_fifteen_decisions(
    monkeypatch,
):
    text = (
        "Find hotels in New York with check-in October 28 and check-out October 30 "
        "for 3 adults and 2 rooms. Include nightly prices from 250 to 350 USD."
    )
    monkeypatch.setattr(
        browser_agent,
        "TaskLedger",
        lambda instructions: TaskLedger(instructions, date(2026, 10, 13)),
    )

    def known(name, value, control):
        return BrowserRequirement(
            name=name,
            expected=value,
            application="form",
            request_quote=f"Canonical {name}: {value}",
            control_id=control,
        )

    actions = [
        decision(
            "fill",
            "0:destination",
            "New York",
            purpose="set_field",
            requirements=[known("destination", "New York", "0:destination")],
        ),
        decision(
            "click",
            "0:city",
            purpose="set_field",
            requirements=[known("destination", "New York", "0:city")],
        ),
        decision(
            "click",
            "0:check_in",
            purpose="set_field",
            requirements=[known("check_in", "2026-10-28", "0:calendar")],
        ),
        decision(
            "click",
            "0:check_out",
            purpose="set_field",
            requirements=[known("check_out", "2026-10-30", "0:calendar")],
        ),
        decision("click", "0:occupancy", purpose="set_field"),
        decision(
            "set_counter",
            "0:adults-increase",
            "3",
            purpose="set_field",
            requirements=[known("adults", "3", "0:adults-increase")],
        ),
        decision(
            "set_counter",
            "0:rooms-increase",
            "2",
            purpose="set_field",
            requirements=[known("rooms", "2", "0:rooms-increase")],
        ),
        decision("click", "0:done", purpose="set_field"),
        decision("click", "0:search", purpose="submit_search"),
        decision("finish", evidence="The checked search returned visible hotel results."),
    ]
    tools = FastHotelTools()
    model = FakeDecider(actions)
    agent = BrowserAgent(tools, model, text)
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == len(actions) <= 15
    assert all(entry["status"] != "requirement_rejected" for entry in report["actions"])
    assert tools.executed_controls.count("0:search") == 1 and tools.submitted
    assert "0:calendar" not in tools.executed_controls
    assert model.payloads[0]["task"] == text
    assert model.payloads[0]["task_checklist"]["date_resolution"]["year"] == 2026
    assert all(
        not action.request_quote or action.request_quote not in text
        for item in actions
        for action in item.requirements
    )
    context = agent.captured_sources()[0]["browser_task_context"]
    assert context["status"] == "form_verified_search_submitted"
    assert not context["availability_verified"]
    observed = {item["field"]: item["observed"] for item in context["requirements"]}
    assert observed == {
        "destination": "New York, New York, United States of America",
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "adults": "3",
        "rooms": "2",
    }
    assert "300 USD" in tools.pages[0]["text"] and "500 USD" in tools.pages[0]["text"]


def test_literal_stay_checklist_retains_every_requested_component():
    task = TaskLedger(TASK)
    assert set(task.requirements) == {"destination", "check_in", "check_out", "adults", "rooms"}
    task.observe(form_observation(adults="2", rooms="1", dates=False))
    assert set(task.pending()) == {"check_in", "check_out", "adults", "rooms"}
    assert task.completion_problem()


def test_pending_full_calendar_dates_are_exposed_as_exact_control_choices():
    task = TaskLedger(TASK)
    observed = form_observation(dates=False)
    observed["frames"][0]["controls"] += [
        {"id": "0:in", "tag": "BUTTON", "label": "Wednesday, October 28, 2026"},
        {"id": "0:out", "tag": "BUTTON", "label": "Friday, October 30, 2026"},
        {"id": "0:unrelated", "tag": "BUTTON", "label": "Thursday, October 29, 2026"},
    ]
    snapshot = task.observe(observed)
    assert [(c["field"], c["control_id"]) for c in snapshot["visible_date_choices"]] == [
        ("check_in", "0:in"),
        ("check_out", "0:out"),
    ]
    assert {"check_in", "check_out"} <= set(task.pending())
    assert task.observe(form_observation())["visible_date_choices"] == []


def test_agent_does_not_advance_past_an_already_visible_requested_date():
    tools = FakeTools()
    observed = form_observation(dates=False)
    observed["frames"][0]["controls"] += [
        {"id": "0:in", "tag": "BUTTON", "label": "Wednesday, October 28, 2026"},
        {"id": "0:next", "tag": "BUTTON", "label": "Next month"},
    ]
    tools.references = {c["id"]: (None, None, c) for c in observed["frames"][0]["controls"]}
    tools.observe = lambda: observed
    model = FakeDecider([decision("click", "0:next"), decision("pause")])
    report = BrowserAgent(tools, model, TASK).run()
    assert "click" not in tools.events
    assert "already visible" in report["actions"][0]["guidance"]
    assert "0:in" in report["actions"][0]["guidance"]


def test_destination_prefers_named_field_over_unrelated_generic_site_search():
    observed = form_observation()
    observed["frames"][0]["controls"].append(
        {"tag": "INPUT", "type": "text", "label": "Search this website", "value": "sports"}
    )
    task = TaskLedger(TASK)
    task.observe(observed)
    assert not task.pending()
    assert task.checks[0]["observed"] == "New York"


def test_empty_destination_does_not_borrow_a_generic_search_value():
    observed = form_observation()
    observed["frames"][0]["controls"][0]["value"] = ""
    observed["frames"][0]["controls"].append(
        {"tag": "INPUT", "type": "text", "label": "Search", "value": "New York"}
    )
    task = TaskLedger(TASK)
    task.observe(observed)
    assert "destination" in task.pending()


def test_single_generic_destination_excludes_text_typed_dates_and_occupancy():
    observed = form_observation()
    observed["frames"][0]["controls"][0]["label"] = "Search in your own words"
    observed["frames"][0]["controls"].append(
        {"tag": "INPUT", "type": "text", "label": "Newsletter email", "value": "fixture"}
    )
    task = TaskLedger(TASK)
    task.observe(observed)
    assert not task.pending()


@pytest.mark.parametrize("second_value", ["New York", "sports", ""])
def test_multiple_generic_textboxes_never_guess_the_destination(second_value):
    observed = form_observation()
    observed["frames"][0]["controls"][0]["label"] = "Search in your own words"
    observed["frames"][0]["controls"].append(
        {"tag": "INPUT", "type": "search", "label": "Search", "value": second_value}
    )
    task = TaskLedger(TASK)
    task.observe(observed)
    assert task.pending() == ["destination"]
    assert "Multiple generic textboxes" in task.checks[0]["evidence"]


def test_conflicting_explicit_destination_controls_remain_unconfirmed():
    observed = form_observation()
    observed["frames"][0]["controls"].append(
        {"tag": "INPUT", "type": "text", "label": "City", "value": "Boston"}
    )
    task = TaskLedger(TASK)
    task.observe(observed)
    assert task.pending() == ["destination"]
    assert task.checks[0]["status"] == "mismatch"


def test_city_catalog_and_open_widgets_do_not_prove_a_completed_search():
    task = TaskLedger(TASK)
    task.observe(
        {
            "url": "https://example.org/city",
            "frames": [
                {
                    "text": "New York hotels",
                    "controls": [
                        {"tag": "BUTTON", "label": "Select dates Check-in — Check-out"},
                        {"tag": "BUTTON", "label": "2 adults · 0 children · 1 room"},
                    ],
                }
            ],
        }
    )
    assert set(task.pending()) == set(task.requirements)
    assert task.submission is None


def test_form_verified_is_not_search_submitted_and_unchanged_click_is_not_success():
    task = TaskLedger(TASK)
    before = form_observation()
    task.observe(before)
    assert not task.pending()
    assert "Search" in task.completion_problem()
    assert not task.submitted(before, before, before["url"])
    assert task.capture_context(before) is None


def test_small_background_text_changes_do_not_confirm_search_submission():
    task = TaskLedger(TASK)
    before = form_observation()
    before["frames"][0]["text"] = "Stable hotel search content " * 100 + "Advertisement 1"
    task.observe(before)
    after = form_observation()
    after["frames"][0]["text"] = "Stable hotel search content " * 100 + "Advertisement 2"
    assert not task.submitted(before, after, before["url"])


def test_delayed_search_response_confirms_later_without_a_second_submission():
    task = TaskLedger(TASK)
    before = form_observation()
    task.observe(before)
    assert not task.submitted(before, before, before["url"])
    assert task.snapshot()["search_response_pending"]
    assert "do not submit again" in task.completion_problem()
    after = {
        "url": "https://example.org/results",
        "document_id": "result-document",
        "frames": [{"text": "Hotel results", "controls": []}],
    }
    task.observe(after)
    assert task.snapshot()["search_submitted"] and not task.snapshot()["search_response_pending"]
    assert not task.pending()
    assert task.capture_context(after)["status"] == "form_verified_search_submitted"


def test_pre_submit_context_survives_form_exclusion_but_is_bound_to_result_document():
    task = TaskLedger(TASK)
    before = form_observation()
    task.observe(before)
    after = {
        "url": "https://example.org/results",
        "document_id": "results-one",
        "frames": [{"text": "Hotels available to review", "controls": []}],
    }
    assert task.submitted(before, after, before["url"])
    task.observe(after)
    context = task.capture_context(after)
    assert context["status"] == "form_verified_search_submitted"
    assert not context["availability_verified"] and not context["record_values_verified"]
    assert {item["field"]: item["observed"] for item in context["requirements"]} == {
        "destination": "New York",
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "adults": "3",
        "rooms": "2",
    }
    unrelated = {**after, "document_id": "results-two"}
    task.observe(unrelated)
    assert task.pending() and task.capture_context(unrelated) is None


def test_visible_result_form_mismatch_invalidates_old_search_context():
    task = TaskLedger(TASK)
    before = form_observation()
    task.observe(before)
    after = {**form_observation(), "document_id": "results"}
    task.submitted(before, after, before["url"])
    after["frames"][0]["controls"][3]["value"] = "2"
    task.observe(after)
    assert "adults" in task.pending() and task.submission is None


def test_sticky_requirements_cannot_be_dropped_changed_or_invented():
    task = TaskLedger(TASK)
    task.declare([])
    assert "rooms" in task.requirements
    with pytest.raises(WebsiteError, match="changed"):
        task.declare(
            [
                BrowserRequirement(
                    name="rooms", expected="1", application="form", request_quote="2 rooms"
                )
            ]
        )
    with pytest.raises(WebsiteError, match="explicit value"):
        task.declare(
            [
                BrowserRequirement(
                    name="currency",
                    expected="EUR",
                    application="extraction",
                    request_quote="hotels in New York",
                )
            ]
        )


@pytest.mark.parametrize("name", ["destination", "check_in", "check_out", "adults", "rooms"])
def test_known_grounded_values_do_not_need_the_model_to_requote_the_original_request(name):
    task = TaskLedger(TASK)
    original = {key: dict(value) for key, value in task.requirements.items()}
    expected = task.requirements[name]["expected"]
    canonical_quote = f"Canonical {name} requirement: {expected}"
    assert canonical_quote not in TASK
    task.declare(
        [
            BrowserRequirement(
                name=name,
                expected=expected,
                application="form",
                request_quote=canonical_quote,
            )
        ]
    )
    assert task.requirements == original
    task.observe(form_observation())
    assert not task.pending()


@pytest.mark.parametrize(
    "changes",
    [{"expected": "Boston"}, {"application": "extraction"}],
)
def test_nonverbatim_known_redeclaration_cannot_change_values_or_application(changes):
    task = TaskLedger(TASK)
    with pytest.raises(WebsiteError, match="changed"):
        task.declare(
            [
                BrowserRequirement(
                    **{
                        "name": "destination",
                        "expected": "New York",
                        "application": "form",
                        "request_quote": "Canonical destination: New York",
                        **changes,
                    }
                )
            ]
        )
    assert task.requirements["destination"]["expected"] == "New York"
    assert task.requirements["destination"]["application"] == "form"


def test_new_requirement_still_requires_a_real_quote_even_after_known_redeclarations():
    task = TaskLedger(TASK)
    with pytest.raises(WebsiteError, match="quote"):
        task.declare(
            [
                BrowserRequirement(
                    name="destination",
                    expected="New York",
                    application="form",
                    request_quote="Canonical destination: New York",
                ),
                BrowserRequirement(
                    name="category",
                    expected="luxury",
                    application="extraction",
                    request_quote="I want luxury hotels",
                ),
            ]
        )
    assert "category" not in task.requirements


def test_new_duplicate_declaration_cannot_skip_grounding_within_the_same_action():
    task = TaskLedger("Find laptops")
    with pytest.raises(WebsiteError, match="quote"):
        task.declare(
            [
                BrowserRequirement(
                    name="product", expected="laptops", application="form", request_quote="laptops"
                ),
                BrowserRequirement(
                    name="product", expected="laptops", application="form", request_quote=""
                ),
            ]
        )
    assert not task.requirements and not task.bindings


@pytest.mark.parametrize(
    "name,invalid",
    [
        ("destination", {"tag": "BUTTON", "role": "option", "label": "New York"}),
        ("check_in", {"tag": "BUTTON", "label": "Select dates Check-in — Check-out"}),
        ("check_out", {"tag": "BUTTON", "role": "gridcell", "date": "2026-10-30"}),
        ("adults", {"tag": "BUTTON", "label": "2 adults, 1 room"}),
        ("rooms", {"tag": "SPAN", "label": "Rooms", "text": "2"}),
    ],
)
def test_known_optional_binding_to_a_choice_or_widget_does_not_poison_readback(name, invalid):
    task = TaskLedger(TASK)
    fresh = form_observation()
    invalid = {"id": "0:invalid", **invalid}
    fresh["frames"][0]["controls"].append(invalid)
    task.declare(
        [
            BrowserRequirement(
                name=name,
                expected=task.requirements[name]["expected"],
                application="form",
                request_quote=f"Canonical {name} value",
                control_id=invalid["id"],
            )
        ],
        fresh,
    )
    assert name not in task.bindings
    task.observe(fresh)
    check = next(item for item in task.checks if item["field"] == name)
    # The wrong optional metadata cannot become a bound source of proof.
    assert check["method"] != "bound_control_readback"
    if name != "adults":
        assert check["status"] == "verified"


@pytest.mark.parametrize("name,index", [("destination", 0), ("check_in", 1), ("adults", 3)])
def test_known_binding_accepts_actual_native_value_fields_with_unfamiliar_labels(name, index):
    task = TaskLedger(TASK)
    fresh = form_observation()
    field = fresh["frames"][0]["controls"][index]
    field["label"] = "An unfamiliar website label"
    if name == "check_in":
        field["type"] = "date"
    if name == "adults":
        field["type"] = "number"
    task.declare(
        [
            BrowserRequirement(
                name=name,
                expected=task.requirements[name]["expected"],
                application="form",
                request_quote=f"Canonical {name} value",
                control_id=field["id"],
            )
        ],
        fresh,
    )
    assert task.bindings[name]["identity"]["label"] == field["label"]
    task.observe(fresh)
    check = next(item for item in task.checks if item["field"] == name)
    assert check["status"] == "verified"


def test_known_occupancy_binding_accepts_a_recognized_counter_not_its_opener():
    task = TaskLedger(TASK)
    fresh = form_observation()
    counter = {
        "id": "0:rooms-increase",
        "tag": "BUTTON",
        "type": "button",
        "label": "Increase rooms",
        "counter": {
            "label": "Rooms",
            "value": 2,
            "direction": "increase",
            "method": "button",
            "evidence": "Rooms 2",
        },
    }
    fresh["frames"][0]["controls"].append(counter)
    task.declare(
        [
            BrowserRequirement(
                name="rooms",
                expected="2",
                application="form",
                request_quote="Canonical rooms count: 2",
                control_id=counter["id"],
            )
        ],
        fresh,
    )
    assert task.bindings["rooms"]["counter_label"] == "Rooms"
    task.observe(fresh)
    check = next(item for item in task.checks if item["field"] == "rooms")
    assert check["status"] == "verified" and check["method"] == "visible_counter"


def test_generic_request_quoted_form_requirements_do_not_need_a_hotel_site_recipe():
    task = TaskLedger("Search for quantum research")
    task.declare(
        [
            BrowserRequirement(
                name="query",
                expected="quantum research",
                application="form",
                request_quote="quantum research",
            )
        ]
    )
    task.observe(
        {
            "url": "https://example.org/",
            "frames": [
                {"controls": [{"tag": "INPUT", "label": "Query", "value": "quantum research"}]}
            ],
        }
    )
    assert not task.pending() and task.completion_problem()


def test_past_missing_year_pauses_before_a_paid_decision(monkeypatch):
    monkeypatch.setattr(
        browser_agent, "TaskLedger", lambda text: TaskLedger(text, date(2026, 10, 10))
    )
    model = FakeDecider([])
    report = BrowserAgent(
        FakeTools(), model, "Find hotels in New York January 2-4 for 3 adults"
    ).run()
    assert report["status"] == "paused" and report["calls"] == 0
    assert "year" in report["guidance"]


@pytest.mark.parametrize(
    "text",
    [
        "October 28-30",
        "28–30 October",
        "Oct 28 to 30",
        "check-in October 28 and check-out October 30",
    ],
)
def test_future_missing_year_uses_disclosed_current_year(text):
    task = TaskLedger("Find hotels in New York " + text, date(2026, 10, 10))
    assert task.request_error is None
    assert task.requirements["check_in"]["expected"] == "2026-10-28"
    assert task.requirements["check_out"]["expected"] == "2026-10-30"
    assert task.snapshot()["date_resolution"]["year"] == 2026


def test_year_default_allows_today_and_never_rolls_into_next_year():
    assert resolve_stay_dates("October 10-12", date(2026, 10, 10))[0] == [
        "2026-10-10",
        "2026-10-12",
    ]
    with pytest.raises(WebsiteError, match="no next year"):
        resolve_stay_dates("December 31 to January 2", date(2026, 10, 10))


def test_year_default_does_not_override_explicit_year_or_invent_invalid_date():
    dates, disclosure = resolve_stay_dates("October 28-30, 2027", date(2026, 10, 10))
    assert dates == ["2027-10-28", "2027-10-30"] and disclosure is None
    with pytest.raises(WebsiteError, match="does not exist"):
        resolve_stay_dates("September 29-31", date(2026, 9, 1))


def test_future_default_reaches_model_with_canonical_dates(monkeypatch):
    monkeypatch.setattr(
        browser_agent, "TaskLedger", lambda text: TaskLedger(text, date(2026, 10, 10))
    )
    model = FakeDecider([decision("pause")])
    report = BrowserAgent(FakeTools(), model, "Find hotels in New York October 28-30").run()
    assert report["calls"] == 1
    assert model.payloads[0]["reference_date"] == "2026-10-10"
    checklist = model.payloads[0]["task_checklist"]
    assert checklist["date_resolution"]["year"] == 2026
    assert (
        next(r for r in checklist["requirements"] if r["field"] == "check_in")["expected"]
        == "2026-10-28"
    )


def test_open_counter_values_expose_targets_without_trusting_a_stale_header():
    observed = form_observation()
    observed["frames"][0]["controls"] = [
        c for c in observed["frames"][0]["controls"] if c["label"] not in {"Adults", "Rooms"}
    ]
    observed["frames"][0]["controls"].append({"tag": "BUTTON", "label": "2 adults · 1 room"})
    for label, count in (("Adults", 3), ("Rooms", 1)):
        for direction in ("increase", "decrease"):
            observed["frames"][0]["controls"].append(
                {
                    "tag": "BUTTON",
                    "id": f"{label}-{direction}",
                    "label": direction,
                    "counter": {
                        "label": label,
                        "value": count,
                        "direction": direction,
                        "evidence": f"{label} {count}",
                    },
                    "enabled": True,
                }
            )
    task = TaskLedger(TASK)
    task.observe(observed)
    adults = next(c for c in task.checks if c["field"] == "adults")
    rooms = next(c for c in task.checks if c["field"] == "rooms")
    assert adults["observed"] == "3" and adults["summary_confirmation_pending"]
    assert adults["next_action"] == "confirm_or_close_widget"
    assert rooms["observed"] == "1" and rooms["next_action"] == "set_counter"
    assert len(rooms["counter_controls"]) == 2
    assert set(task.pending()) == {"adults", "rooms"}


def test_short_date_summary_needs_a_full_year_bound_calendar_choice():
    task = TaskLedger(TASK)
    observed = form_observation()
    observed["frames"][0]["controls"] = [
        c for c in observed["frames"][0]["controls"] if c["label"] not in {"Check-in", "Check-out"}
    ] + [
        {
            "tag": "BUTTON",
            "label": "Select dates Check-in — Check-out",
            "text": "Wed, Oct 28 — Fri, Oct 30",
        }
    ]
    task.observe(observed)
    assert {"check_in", "check_out"} <= set(task.pending())
    for day in ("2026-10-28", "2026-10-30"):
        task.remember_action({"date": day, "label": day}, {"status": "action_performed"})
    task.observe(observed)
    assert not task.pending()
    assert all(
        "Selected full date" in c["evidence"]
        for c in task.checks
        if c["field"] in {"check_in", "check_out"}
    )


def test_premature_finish_is_fed_back_and_repeated_finish_pauses_without_capture():
    tools = FakeTools()
    model = FakeDecider([decision("finish"), decision("finish")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and not tools.pages
    assert report["calls"] == 2
    assert all(a["status"] == "completion_rejected" for a in report["actions"])
    assert model.payloads[1]["recent_actions"][0]["status"] == "completion_rejected"
    assert set(report["task_checklist"]["pending_fields"]) == {
        "destination",
        "check_in",
        "check_out",
        "adults",
        "rooms",
    }


def test_finish_is_the_only_source_handoff_signal_without_a_redundant_completion_flag():
    tools = FakeTools()
    model = FakeDecider([decision("finish")])
    report = BrowserAgent(tools, model, "Collect the visible headlines").run()
    assert report["status"] == "ready" and len(tools.pages) == 1
    assert report["calls"] == 1
    assert report["actions"][0]["status"] == "source_collection_ready"
    assert "completion_status" not in BrowserDecision.model_json_schema()["properties"]
    assert "completion_status" not in model.payloads[0]
    assert "completion_status" not in browser_agent.INSTRUCTIONS


def test_checked_hotel_search_captures_results_and_defers_price_filtering_to_extraction():
    tools = SearchResultTools()
    task_text = TASK + " Include hotels priced between 250 and 350 USD nightly."
    filters = [
        BrowserRequirement(
            name=name,
            expected=value,
            application="extraction",
            request_quote="priced between 250 and 350 USD nightly",
        )
        for name, value in (("min_price", "250"), ("max_price", "350"))
    ]
    model = FakeDecider(
        [
            decision("click", "0:search", purpose="submit_search", requirements=filters),
            decision("finish", evidence="Hotel results and displayed prices are visible."),
        ]
    )
    agent = BrowserAgent(tools, model, task_text)
    report = agent.run()
    assert report["status"] == "ready" and report["calls"] == 2
    assert tools.events.count("click") == tools.events.count("capture") == 1
    assert [action["status"] for action in report["actions"]] == [
        "search_transition_observed",
        "source_collection_ready",
    ]
    assert model.payloads[1]["task_checklist"]["search_submitted"]
    assert not model.payloads[1]["task_checklist"]["pending_fields"]
    filters = [
        check
        for check in report["task_checklist"]["requirements"]
        if check["application"] == "extraction"
    ]
    assert {check["field"] for check in filters} == {"min_price", "max_price"}
    assert all(check["status"] == "deferred_to_extraction" for check in filters)
    source = agent.captured_sources()[0]
    assert "300 USD" in source["text"] and "500 USD" in source["text"]
    context = source["browser_task_context"]
    assert context["status"] == "form_verified_search_submitted"
    assert context["availability_verified"] is context["record_values_verified"] is False
    assert "records" not in report


def test_old_finish_rejection_does_not_poison_pending_then_confirmed_search_response():
    tools = SearchResultTools(delayed=True)
    model = FakeDecider(
        [
            decision("finish"),
            decision("click", "0:search", purpose="submit_search"),
            decision("finish"),
            decision("wait"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "ready" and report["calls"] == 5
    assert tools.events.count("click") == tools.events.count("capture") == 1
    assert model.payloads[2]["task_checklist"]["search_response_pending"]
    assert model.payloads[3]["recent_actions"][-1]["status"] == "completion_rejected"
    assert model.payloads[4]["task_checklist"]["search_submitted"]
    assert not model.payloads[4]["task_checklist"]["search_response_pending"]


def test_changed_form_values_reset_premature_finish_rejections_until_checked_search():
    tools = SearchResultTools(adults="1")
    model = FakeDecider(
        [
            decision("finish"),
            decision("fill", "0:3", "2", purpose="set_field"),
            decision("finish"),
            decision("fill", "0:3", "3", purpose="set_field"),
            decision("click", "0:search", purpose="submit_search"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "ready" and report["calls"] == 6
    assert tools.events.count("fill") == 2
    assert tools.events.count("click") == tools.events.count("capture") == 1
    assert [action["status"] for action in report["actions"]].count("completion_rejected") == 2


def test_resume_starts_a_fresh_finish_rejection_streak_without_resetting_model_budget():
    tools = FakeTools()
    model = FakeDecider(
        [decision("finish"), decision("finish"), decision("finish"), decision("pause")]
    )
    agent = BrowserAgent(tools, model, TASK)
    assert agent.run()["calls"] == 2
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == 4
    assert len(report["actions"]) == 4 and not tools.pages
    assert report["actions"][-1]["status"] == "user_input_required"


@pytest.mark.parametrize("change", ["widget", "scroll", "ad_control", "unchanged"])
def test_only_meaningful_widget_progress_resets_rejected_finish_streak(change):
    tools = FakeTools()

    def observation():
        result = form_observation(adults="2")
        frame = result["frames"][0]
        frame.update(widgets=[], viewport={"scroll_y": 0})
        if "inspect" in tools.events:
            if change == "widget":
                frame["widgets"] = [{"role": "dialog", "label": "Choose occupancy"}]
            elif change == "scroll":
                frame["viewport"]["scroll_y"] = 120
            elif change == "ad_control":
                frame["controls"].append(
                    {"id": "0:ad", "tag": "BUTTON", "label": "Advertisement details"}
                )
        return result

    tools.observe = observation
    model = FakeDecider(
        [decision("finish"), decision("inspect"), decision("finish"), decision("pause")]
    )
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and not tools.pages
    assert report["calls"] == (4 if change == "widget" else 3)
    assert report["actions"][-1]["status"] == (
        "user_input_required" if change == "widget" else "completion_rejected"
    )


def test_unchanged_search_response_cannot_finish_or_capture():
    tools = SearchResultTools(delayed=True)
    model = FakeDecider(
        [
            decision("click", "0:search", purpose="submit_search"),
            decision("finish"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and not tools.pages
    assert tools.events.count("click") == 1 and "capture" not in tools.events
    assert report["task_checklist"]["search_response_pending"]
    assert [action["status"] for action in report["actions"]][-2:] == [
        "completion_rejected",
        "completion_rejected",
    ]


def test_finish_capture_failure_cannot_report_ready_or_synthesize_final_records():
    tools = SearchResultTools()

    def fail_capture(kind="page"):
        tools.events.append("capture")
        raise WebsiteError("The result page could not be captured.")

    tools.capture = fail_capture
    model = FakeDecider(
        [decision("click", "0:search", purpose="submit_search"), decision("finish")]
    )
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and not tools.pages
    assert report["failure"]["stage"] == "act"
    assert tools.events.count("capture") == 1
    assert not any(action["status"] == "source_collection_ready" for action in report["actions"])


@pytest.mark.parametrize("interruption", ["mfa", "cancel"])
def test_sign_in_or_cancellation_after_search_stops_before_source_handoff(interruption):
    tools = SearchResultTools()
    observe = tools.observe

    def interrupted_observation():
        result = observe()
        if tools.submitted:
            if interruption == "mfa":
                result["frames"][0]["password_or_code_visible"] = True
            else:
                tools.allowed = False
        return result

    tools.observe = interrupted_observation
    model = FakeDecider([decision("click", "0:search", purpose="submit_search")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events.count("click") == 1 and "capture" not in tools.events
    assert not tools.pages


def test_search_with_unconfirmed_occupancy_never_calls_the_click_tool():
    tools = FakeTools()
    tools.observe = lambda: form_observation(adults="2", rooms="1")
    tools.references["0:search"] = (None, None, {"tag": "BUTTON", "label": "Search"})
    model = FakeDecider([decision("click", "0:search", purpose="submit_search"), decision("pause")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and "click" not in tools.events
    assert "adults, rooms" in report["actions"][0]["guidance"]


@pytest.mark.parametrize(
    "facts",
    [
        {"tag": "BUTTON", "label": "Search hotels in New York"},
        {"tag": "BUTTON", "label": "Find available stays"},
        {"tag": "BUTTON", "type": "submit", "submits_form": True, "label": "Go"},
        {"tag": "INPUT", "type": "submit", "label": "Continue"},
        {"tag": "A", "label": "Search results", "href": "https://example.org/results"},
        {"tag": "DIV", "role": "option", "label": "New York Search with AI"},
    ],
)
def test_decorated_native_and_ai_searches_cannot_bypass_unfinished_form(facts):
    tools = FakeTools()
    tools.observe = lambda: form_observation(adults="2", rooms="1", dates=False)
    tools.references["0:search"] = (None, None, facts)
    model = FakeDecider([decision("click", "0:search", purpose="navigate"), decision("pause")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and "click" not in tools.events
    assert "Set and verify" in report["actions"][0]["guidance"]


def test_destination_option_and_calendar_opener_are_not_search_submissions():
    task = TaskLedger(TASK)
    assert not task.is_submit(
        decision("click"),
        {"tag": "DIV", "role": "option", "label": "New York, United States of America"},
    )
    assert not task.is_submit(
        decision("click"),
        {"tag": "BUTTON", "type": "submit", "submits_form": True, "label": "Select dates"},
    )


def test_submission_evidence_cannot_be_created_from_unverified_form():
    task = TaskLedger(TASK)
    before = form_observation(adults="2")
    task.observe(before)
    assert not task.submitted(before, {"url": "https://example.org/results"}, before["url"])
    assert task.submission is None and task.pending_submission is None


def test_accidental_destination_navigation_pauses_instead_of_editing_catalog():
    class AutoNavigatingTools(FakeTools):
        def observe(self):
            if "fill" in self.events:
                return {
                    "url": "https://example.org/city/new-york",
                    "document_id": "catalog",
                    "frames": [{"text": "New York hotels", "controls": []}],
                }
            return form_observation(dates=False, adults="2", rooms="1")

    tools = AutoNavigatingTools()
    tools.references["0:destination"] = (None, None, {"tag": "INPUT", "label": "Destination"})
    model = FakeDecider([decision("fill", "0:destination", "New York", purpose="set_field")])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert "navigated before" in report["guidance"]
    assert not tools.pages


def test_failed_search_retries_ignore_changing_background_ads():
    tools = FakeTools()
    state = {"count": 0}

    def observation():
        state["count"] += 1
        result = form_observation(dates=False, adults="2", rooms="1")
        result["frames"][0]["text"] = f"Advertisement {state['count']}"
        return result

    tools.observe = observation
    tools.references["0:search"] = (None, None, {"tag": "BUTTON", "label": "Search hotels"})
    model = FakeDecider([decision("click", "0:search", purpose="navigate") for _ in range(3)])
    report = BrowserAgent(tools, model, TASK).run()
    assert report["status"] == "paused" and report["calls"] == 3
    assert "click" not in tools.events and not tools.pages
    assert (
        "no observable progress" in report["guidance"]
        or "repeatedly tried Search" in report["guidance"]
    )


def test_pending_search_does_not_navigate_to_a_catalog_and_call_that_the_response():
    tools = FakeTools()
    before = form_observation()
    tools.observe = lambda: before
    tools.references["0:link"] = (None, None, {"tag": "A", "label": "City hotels"})
    model = FakeDecider([decision("click", "0:link", purpose="navigate"), decision("pause")])
    agent = BrowserAgent(tools, model, TASK)
    agent.task.observe(before)
    agent.task.submitted(before, before, before["url"])
    report = agent.run()
    assert report["status"] == "paused" and "click" not in tools.events
    assert "do not navigate away" in report["actions"][0]["guidance"]


def test_compacted_navigation_context_is_bounded_with_fresh_ids_and_disclosure():
    observation = {
        "url": "https://example.org/",
        "frames": [
            {
                "text": "Body " * 2400,
                "controls": [
                    {
                        "id": f"0:{i}",
                        "tag": "BUTTON",
                        "label": "Control " + str(i),
                        "context": "Long context " * 80,
                        "text": "Long text " * 80,
                        "enabled": True,
                        "readonly": False,
                        "options": [],
                    }
                    for i in range(140)
                ],
            }
        ],
    }
    compact = compact_observation(observation)
    assert len(json.dumps(compact, ensure_ascii=False, separators=(",", ":"))) <= 24000
    assert compact["frames"][0]["controls"][0]["id"] == "0:0"
    assert compact["navigation_context_compacted"]
    assert "not proof of absence" in compact["omission_notice"]
    assert len(observation["frames"][0]["controls"]) == 140
    assert len(observation["frames"][0]["text"]) == 12000


def test_capture_summary_preserves_separate_search_context():
    context = {"status": "form_verified_search_submitted", "availability_verified": False}
    summary = capture_summary(
        [{"url": "https://example.org/results", "text": "Source", "browser_task_context": context}]
    )
    assert summary[0]["browser_task_context"] == context


@pytest.fixture
def agent_page(request):
    yield from shared_page.__wrapped__(request)


def test_local_native_submit_with_generic_label_cannot_search_before_dates_and_guests(agent_page):
    agent_page.set_content("""<form onsubmit='event.preventDefault();window.searched=true'>
      <input aria-label=Destination value='New York'>
      <input type=date aria-label='Check-in'><input type=date aria-label='Check-out'>
      <input type=number aria-label=Adults value=2><input type=number aria-label=Rooms value=1>
      <button type=submit>Continue</button></form>""")
    tools = tools_for(agent_page)

    class Model:
        first = True

        def decide(self, payload, timeout):
            if not self.first:
                return decision("pause")
            self.first = False
            button = next(
                c
                for c in payload["observation"]["frames"][0]["controls"]
                if c["label"] == "Continue"
            )
            return decision("click", button["id"], purpose="navigate")

    report = BrowserAgent(tools, Model(), TASK).run()
    assert report["status"] == "paused" and agent_page.evaluate("window.searched") is None
    assert report["actions"][0]["control_semantics"]["submits_form"]
    assert set(report["actions"][0]["pending_fields_before"]) == {
        "check_in",
        "check_out",
        "adults",
        "rooms",
    }


def test_local_search_sets_all_counters_confirms_popup_then_submits(agent_page):
    widget = (
        occupancy_markup()
        .replace("<section>", "<section id=occupancy>")
        .replace(
            "<button>Done</button>",
            """<button onclick="const counts=document.querySelectorAll('.count');
          document.querySelector('#summary').textContent=counts[0].textContent+
          ' adults, '+counts[2].textContent+' rooms';
          document.querySelector('#occupancy').hidden=true">Done</button>""",
        )
    )
    agent_page.set_content(
        """<main><input aria-label=Destination value='New York'>
      <input type=date aria-label='Check-in' value=2026-10-28>
      <input type=date aria-label='Check-out' value=2026-10-30>
      <button id=summary>2 adults, 1 room</button>"""
        + widget
        + """
      <button onclick="document.querySelector('main').innerHTML=
        '<h1>Hotel results</h1><p>New York Hotel 300 USD per night</p>'">Search</button></main>"""
    )

    class Model:
        def decide(self, payload, timeout):
            checks = payload["task_checklist"]["requirements"]
            for check in checks:
                if check.get("next_action") == "set_counter":
                    current, target = int(check["observed"]), int(check["expected"])
                    direction = "increase" if current < target else "decrease"
                    items = payload["observation"]["frames"][0]["controls"]
                    option = next(
                        c
                        for c in items
                        if c.get("counter", {}).get("label", "").casefold() == check["field"]
                        and c["counter"]["direction"] == direction
                    )
                    return decision(
                        "set_counter", option["id"], check["expected"], purpose="set_field"
                    )
            items = payload["observation"]["frames"][0]["controls"]
            if any(c.get("summary_confirmation_pending") for c in checks):
                return decision(
                    "click",
                    next(c["id"] for c in items if c["label"] == "Done"),
                    purpose="set_field",
                )
            if not payload["task_checklist"]["search_submitted"]:
                return decision(
                    "click",
                    next(c["id"] for c in items if c["label"] == "Search"),
                    purpose="submit_search",
                )
            return decision(
                "finish", evidence="Hotel results are visible after the checked search."
            )

    tools = tools_for(agent_page)
    report = BrowserAgent(tools, Model(), TASK).run()
    assert report["status"] == "ready"
    assert [a["action"] for a in report["actions"]] == [
        "set_counter",
        "set_counter",
        "click",
        "click",
        "finish",
    ]
    context = tools.pages[0]["browser_task_context"]
    assert {c["field"]: c["observed"] for c in context["requirements"]}["rooms"] == "2"
    assert context["availability_verified"] is False


def test_local_agent_completes_form_search_before_capture_and_carries_context(agent_page):
    agent_page.set_content("""<main><input aria-label=Destination value='New York'>
      <input type=date aria-label='Check-in'><input type=date aria-label='Check-out'>
      <input type=number aria-label=Adults value=2><input type=number aria-label=Rooms value=1>
      <button onclick="document.querySelector('main').innerHTML=
        '<h1>Hotel results</h1><p>New York Hotel 300 USD per night</p>'">Search</button></main>""")

    class FormModel:
        def decide(self, payload, timeout):
            items = payload["observation"]["frames"][0]["controls"]
            needed = payload["task_checklist"]["pending_fields"]
            labels = {
                "check_in": "Check-in",
                "check_out": "Check-out",
                "adults": "Adults",
                "rooms": "Rooms",
            }
            if needed:
                name = needed[0]
                item = next(c for c in items if c["label"] == labels[name])
                expected = next(
                    c["expected"]
                    for c in payload["task_checklist"]["requirements"]
                    if c["field"] == name
                )
                return decision("fill", item["id"], expected, purpose="set_field")
            if not payload["task_checklist"]["search_submitted"]:
                return decision(
                    "click",
                    next(c["id"] for c in items if c["label"] == "Search"),
                    purpose="submit_search",
                )
            return decision(
                "finish", evidence="Hotel results are visible after the verified search."
            )

    tools = tools_for(agent_page)
    report = BrowserAgent(tools, FormModel(), TASK).run()
    assert report["status"] == "ready"
    assert [a["status"] for a in report["actions"]][-2:] == [
        "search_transition_observed",
        "source_collection_ready",
    ]
    assert "Hotel results" in tools.pages[0]["text"]
    assert tools.pages[0]["browser_task_context"]["availability_verified"] is False
    assert all(c["status"] == "verified" for c in report["task_checklist"]["requirements"])


def test_local_unselected_calendar_choices_are_not_verified_dates(agent_page):
    agent_page.set_content("""<button>Select dates Check-in — Check-out</button>
      <div role=dialog><button data-date=2026-10-28 aria-checked=false>
        Check-in October 28 2026</button>
      <button data-date=2026-10-30 aria-checked=false>
        Check-out October 30 2026</button></div>""")
    task = TaskLedger(TASK)
    task.observe(tools_for(agent_page).observe())
    assert {"check_in", "check_out"} <= set(task.pending())


def test_local_search_rechecks_occupancy_changed_during_model_decision(agent_page):
    agent_page.set_content("""<input aria-label=Destination value='New York'>
      <input type=date aria-label='Check-in' value=2026-10-28>
      <input type=date aria-label='Check-out' value=2026-10-30>
      <input type=number aria-label=Adults value=3><input type=number aria-label=Rooms value=2>
      <button onclick='window.searched=true'>Search</button>""")

    class ChangedFormModel:
        first = True

        def decide(self, payload, timeout):
            if not self.first:
                return decision("pause")
            self.first = False
            search = next(
                c for c in payload["observation"]["frames"][0]["controls"] if c["label"] == "Search"
            )
            agent_page.get_by_label("Rooms", exact=True).fill("1")
            return decision("click", search["id"], purpose="submit_search")

    report = BrowserAgent(tools_for(agent_page), ChangedFormModel(), TASK).run()
    assert report["status"] == "paused"
    assert agent_page.evaluate("window.searched") is None
    assert "rooms" in report["actions"][0]["guidance"]


def test_local_query_stripped_capture_keeps_bound_context_and_refreshes_old_snapshot(agent_page):
    agent_page.goto("https://example.org/results?checkin=2026-10-28")
    agent_page.set_content("<main>Old catalog</main>")
    tools = tools_for(agent_page)
    tools.capture("page")
    tools.collection_context = {
        "status": "form_verified_search_submitted",
        "result_document_id": hashlib.sha256(agent_page.url.encode()).hexdigest(),
        "availability_verified": False,
    }
    agent_page.set_content("<main>Actual searched hotel results</main>")
    # Production Capture strips URL query strings; evidence remains bound using
    # the actual browser document identity rather than the exported URL.
    tools.capture_page = lambda: {
        "url": "https://example.org/results",
        "text": agent_page.locator("main").inner_text(),
    }
    tools.capture("page")
    assert len(tools.pages) == 1
    assert tools.pages[0]["text"] == "Actual searched hotel results"
    assert tools.pages[0]["browser_task_context"] == tools.collection_context


def test_extraction_adapter_passes_form_context_separately_and_does_not_duplicate_blocks(
    monkeypatch,
):
    received = {}

    class Client:
        def __init__(self, **kwargs):
            self.http = kwargs["http_client"]
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.http.close()

        def parse(self, **kwargs):
            received.update(kwargs)
            return SimpleNamespace(
                status="completed",
                output_parsed=custom_extract.Extraction(
                    outcome="needs_input",
                    guidance="Fixture",
                    content_type="hotels",
                    interpretation="Fixture",
                    warnings=[],
                    more_records_available=False,
                    columns=[
                        custom_extract.Column(
                            name="name", kind="text", unit="", description="Hotel name"
                        )
                    ],
                    filters=[],
                    rows=[],
                ),
                usage=None,
            )

    monkeypatch.setattr(custom_extract, "OpenAI", Client)
    page = {
        "url": "https://example.org/results",
        "text": "Hotel 300 USD",
        "blocks": [{"id": "b1", "text": "Hotel 300 USD"}],
        "browser_task_context": {
            "availability_verified": False,
            "scope": "form_values_and_submission_only",
        },
    }
    request_text = TASK + " Include hotel name, price and URL; price range 250-350 USD nightly."
    values = SimpleNamespace(
        instructions=request_text, output_fields=["name", "price", "url"], record_limit=25
    )
    _, metadata = custom_extract.interpret(
        values,
        [page],
        SimpleNamespace(api_key="fixture-only", model="fixture-model", timeout_seconds=10),
    )
    payload = json.loads(received["input"][1]["content"])
    assert payload["instructions"] == request_text
    assert payload["output_fields"] == ["name", "price", "url"]
    assert "text" not in payload["pages"][0]
    assert payload["pages"][0]["browser_task_context"] == page["browser_task_context"]
    assert metadata["prompt_version"] == "website-extractor-v15"
    assert "proof of per-hotel availability" in received["input"][0]["content"]
