"""Offline optimization regressions; no real website, browser or paid API calls."""

import copy
import json

import httpx
import pytest
from test_browser_agent import FakeDecider, FakeTools, decision
from test_browser_decision_diagnostics import mocked_decider, response_body
from test_browser_task import TASK, ScopedReadyHotelTools, SearchResultTools

from agentic_web_demo.browser_agent import BrowserAgent, safe_decision_metadata
from agentic_web_demo.browser_context import FOCUSED_CONTEXT_CHARS, NAVIGATION_CONTEXT_CHARS

IMAGE = "data:image/jpeg;base64,fixture-only-pixels"


def text_size(payload):
    return len(
        json.dumps(
            {key: value for key, value in payload.items() if key != "viewport_image"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


class VisualTools(FakeTools):
    """A stable local DOM snapshot with observable, literal text-field changes."""

    def __init__(self, *, ambiguous=False):
        super().__init__()
        self.visual_enabled = True
        self.image_requests = 0
        self.value = ""
        self.ambiguous = ambiguous

    def observe(self):
        self.events.append("observe")
        if self.ambiguous:
            fields = [
                {
                    "id": "0:quantity",
                    "tag": "BUTTON",
                    "type": "button",
                    "label": "",
                    "role": "spinbutton",
                    "counter": {
                        "label": "Quantity",
                        "value": 1,
                        "direction": "unknown",
                        "method": "button",
                    },
                }
            ]
        else:
            fields = [
                {
                    "id": "0:query",
                    "tag": "INPUT",
                    "type": "text",
                    "label": "Query",
                    "value": self.value,
                }
            ]
        self.references = {field["id"]: (None, None, field) for field in fields}
        return {
            "url": "https://example.org/",
            "document_id": "same-document",
            "version": self.version,
            "frames": [
                {
                    "text": "Rendered source content remains available for extraction.",
                    "password_or_code_visible": False,
                    "controls": fields,
                }
            ],
        }

    def execute(self, action):
        outcome = super().execute(action)
        if action.action == "fill":
            self.value = action.value
            return {"status": "value_verified", "expected": self.value, "observed": self.value}
        return outcome

    def viewport_image(self):
        self.image_requests += 1
        return IMAGE


class VisibleSearchTools(SearchResultTools):
    def observe(self):
        fresh = super().observe()
        if not self.submitted:
            fresh["frames"][0]["controls"].append(
                {"id": "0:search", "tag": "BUTTON", "label": "Search"}
            )
        return fresh


class NativeDestinationTools(ScopedReadyHotelTools):
    """Literal field read-back, optional combobox ownership and fake site results."""

    def __init__(self, value="", *, readonly=False, unavailable=False, widget=None, combo=False):
        super().__init__()
        self.destination = value
        self.readonly = readonly
        self.unavailable = unavailable
        self.widget = widget
        self.combo = combo
        self.destination_open = combo

    def observe(self):
        fresh = super().observe()
        if self.submitted:
            return fresh
        frame = fresh["frames"][0]
        field = frame["controls"][0]
        field.update(value=self.destination, readonly=self.readonly)
        if self.unavailable:
            field.pop("value")
        if self.combo:
            field.update(
                role="combobox",
                selection_required=True,
                expanded=str(self.destination_open).lower(),
                option_ids=["0:city", "0:ai"] if self.destination_open else [],
            )
            if self.destination_open:
                frame["controls"].extend(
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
                            "text": "New York\nSearch with AI",
                            "option_primary": "New York",
                        },
                    ]
                )
        if self.widget in {"dialog", "grid", "menu"}:
            frame["widgets"] = [{"role": self.widget, "label": "An open foreground widget"}]
        if self.widget == "counter":
            frame["controls"].append(
                {
                    "id": "0:counter",
                    "tag": "BUTTON",
                    "label": "Increase adults",
                    "counter": {
                        "label": "Adults",
                        "value": 3,
                        "direction": "increase",
                        "method": "button",
                        "evidence": "Adults 3",
                    },
                }
            )
        self.references = {item["id"]: (None, None, item) for item in frame["controls"]}
        return fresh

    def execute(self, action):
        if action.action == "fill":
            assert action.control_id == "0:0"
            self.events.append("fill")
            self.destination = action.value
            return {"status": "value_verified", "expected": action.value, "observed": action.value}
        if action.action == "click" and action.control_id == "0:city":
            self.events.append("click")
            self.destination = "New York, New York, United States of America"
            self.destination_open = False
            return {"status": "action_performed"}
        return super().execute(action)


@pytest.mark.parametrize(
    "requested,initial",
    [("New York", ""), ("Boston", "Chicago"), ("Seattle", "")],
)
def test_known_literal_destination_fill_needs_no_paid_decision(requested, initial):
    tools = NativeDestinationTools(initial)
    model = FakeDecider([])
    agent = BrowserAgent(tools, model, TASK.replace("New York", requested), max_calls=0)
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == 0
    assert model.payloads == [] and tools.events.count("fill") == 1
    assert tools.events.count("click") == tools.events.count("capture") == 1
    assert tools.destination == requested
    assert [entry["action"] for entry in report["actions"]] == ["fill", "click", "finish"]
    assert all(entry["decision_origin"] == "runtime" for entry in report["actions"])
    source = agent.captured_sources()[0]
    assert "300 USD" in source["text"] and "500 USD" in source["text"]
    context = source["browser_task_context"]
    assert (
        next(item for item in context["requirements"] if item["field"] == "destination")["observed"]
        == requested
    )
    assert not context["availability_verified"]


@pytest.mark.parametrize(
    "settings",
    [
        {"readonly": True},
        {"unavailable": True},
        {"widget": "dialog"},
        {"widget": "grid"},
        {"widget": "menu"},
        {"widget": "counter"},
    ],
)
def test_local_destination_fill_does_not_interrupt_unknown_or_foreground_controls(settings):
    tools = NativeDestinationTools(**settings)
    model = FakeDecider([decision("pause", evidence="Inspect the current field or open widget.")])
    report = BrowserAgent(tools, model, TASK).run()

    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events.count("fill") == 0 and tools.events.count("click") == 0
    assert not tools.pages and len(model.payloads) == 1


def test_matching_uncommitted_destination_is_left_for_model_option_selection_not_refilled():
    tools = NativeDestinationTools("New York", combo=True)
    model = FakeDecider(
        [decision("pause", evidence="Review the two owned destination suggestions.")]
    )
    report = BrowserAgent(tools, model, TASK).run()

    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events.count("fill") == tools.events.count("click") == 0
    assert model.payloads[0]["interaction_focus"]["phase"] == "choose_option"
    field = next(
        item for item in report["task_checklist"]["requirements"] if item["field"] == "destination"
    )
    assert field["next_action"] == "select_option" and field["selection_pending"]


def test_previously_clicked_canonical_destination_is_not_retyped_by_local_fill():
    tools = NativeDestinationTools("New York", combo=True)
    agent = BrowserAgent(tools, FakeDecider([]), TASK, max_calls=0)
    before = tools.observe()
    agent.task.observe(before)
    facts = tools.references["0:city"][2]
    choice = decision("click", "0:city", purpose="set_field")
    outcome = tools.execute(choice)
    agent.task.remember_action(facts, outcome, choice, before)
    agent.task.observe(tools.observe())
    tools.events.clear()

    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events.count("fill") == 0 and tools.events.count("click") == 1
    assert tools.destination == "New York, New York, United States of America"
    source = agent.captured_sources()[0]
    assert source["browser_task_context"]["status"] == "form_verified_search_submitted"


def test_local_fill_rechecks_an_operator_change_before_using_the_old_empty_value():
    tools = NativeDestinationTools()
    observe = tools.observe

    def operator_filled_destination():
        if tools.events.count("observe"):
            tools.destination = "New York"
        return observe()

    tools.observe = operator_filled_destination
    model = FakeDecider([])
    report = BrowserAgent(tools, model, TASK, max_calls=0).run()

    assert report["status"] == "ready" and report["calls"] == 0
    assert tools.events.count("fill") == 0 and tools.events.count("click") == 1
    assert report["actions"][0]["status"] == "fill_preflight_changed"
    assert model.payloads == []


def test_focused_paid_context_keeps_packing_metrics_local_without_truncating_the_task():
    tools = NativeDestinationTools("New York", combo=True)
    observe = tools.observe

    def noisy_index():
        fresh = observe()
        fresh["frames"][0]["text"] = "Background navigation and site content " * 1500
        fresh["frames"][0]["controls"].extend(
            {
                "id": f"0:background-{index}",
                "tag": "A",
                "label": f"Unrelated navigation {index}",
                "href": f"https://example.org/background/{index}",
                "context": "Background wrapper text " * 20,
                "rect": {"x": 0, "y": index * 20, "width": 180, "height": 18},
            }
            for index in range(80)
        )
        return fresh

    tools.observe = noisy_index
    model = FakeDecider([decision("pause", evidence="Choose the intended owned location.")])
    report = BrowserAgent(tools, model, TASK).run()

    assert report["status"] == "paused" and report["calls"] == 1
    payload = model.payloads[0]
    assert payload["task"] == TASK and "context_metrics" not in payload
    metric = report["performance"]["navigation_context"][0]
    assert metric["text_chars"] == text_size(payload) <= FOCUSED_CONTEXT_CHARS
    assert metric["packing"]["tier"] == "focused"
    assert metric["packing"]["limit_chars"] == FOCUSED_CONTEXT_CHARS
    assert metric["packing"]["observation_limit_chars"] == 3500
    assert metric["packing"]["raw_chars"] > metric["packing"]["packed_chars"]
    controls = payload["observation"]["frames"][0]["controls"]
    options = {item["id"]: item for item in controls if item.get("role") == "option"}
    assert set(options) == {"0:city", "0:ai"}
    assert "United States of America" in options["0:city"]["text"]
    assert "Search with AI" in options["0:ai"]["text"]
    assert len(tools.observe()["frames"][0]["controls"]) == 89


def test_sdk_defensively_omits_local_context_metrics_from_the_paid_wire(monkeypatch):
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=response_body()))
    payload = {
        "task": "Read the visible source",
        "observation": {"url": "https://example.org/", "frames": []},
        "context_metrics": {"raw_chars": 9000, "fixture_note": "not-for-the-model"},
    }
    original = copy.deepcopy(payload)
    try:
        assert model.decide(payload, 30).action == "pause"
        assert len(calls) == 1 and payload == original
        request = json.loads(calls[0].content)
        actual_text = request["input"][1]["content"]
        wire = json.loads(actual_text)
        assert "context_metrics" not in wire and "not-for-the-model" not in actual_text
        assert wire["task"] == payload["task"] and wire["observation"] == payload["observation"]
        assert model.last_decision["input_chars"] == len(actual_text)
        assert request["model"] == "fixture-model"
        assert request["store"] is False and request["max_output_tokens"] == 1200
        assert request["text"]["format"]["strict"] is True
    finally:
        model.close()


def test_internally_blocked_search_is_not_counted_as_a_real_repeated_click():
    tools = VisibleSearchTools(adults="2")
    model = FakeDecider([decision("click", "0:search", purpose="submit_search") for _ in range(3)])
    agent = BrowserAgent(tools, model, TASK)
    report = agent.run()

    assert report["status"] == "paused" and report["calls"] == 3
    assert not tools.submitted and tools.events.count("click") == 0
    assert not tools.pages and agent.seen_actions == {}
    assert report["performance"]["phase_calls"].get("action", 0) == 0
    assert [entry["status"] for entry in report["actions"]] == [
        "not_completed",
        "not_completed",
        "premature_search_paused",
    ]
    assert "Search was not clicked" in report["guidance"]
    assert "adults" in report["guidance"]
    assert "Repeated click" not in report["guidance"]
    assert not report["task_checklist"]["search_submitted"]


def test_dom_sufficient_steps_do_not_generate_consented_screenshots():
    tools = VisualTools()
    model = FakeDecider(
        [
            decision("fill", "0:query", "quantum"),
            decision("fill", "0:query", "quantum research"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, "Collect the visible source content").run()

    assert report["status"] == "ready" and report["calls"] == 3
    assert tools.image_requests == 0 and report["visual_calls_attempted"] == 0
    assert report["visual_enabled"] and report["visual_policy"] == "adaptive"
    assert all("viewport_image" not in payload for payload in model.payloads)
    assert report["performance"]["phase_calls"] == {
        "observe": 3,
        "context": 3,
        "model": 3,
        "action": 2,
        "capture": 1,
    }
    assert all(value >= 0 for value in report["performance"]["phase_seconds"].values())
    for metric, payload in zip(
        report["performance"]["navigation_context"], model.payloads, strict=True
    ):
        assert metric["text_chars"] == text_size(payload) <= NAVIGATION_CONTEXT_CHARS
        assert not metric["screenshot_sent"]
        assert metric["screenshot_reason"] == "dom_sufficient"
    assert IMAGE not in json.dumps(report)


def test_ambiguous_unchanged_widget_sends_one_image_not_one_per_decision():
    tools = VisualTools(ambiguous=True)
    model = FakeDecider([decision("inspect"), decision("inspect"), decision("finish")])
    report = BrowserAgent(tools, model, "Collect the visible source content").run()

    assert report["status"] == "ready" and report["calls"] == 3
    assert tools.image_requests == report["visual_calls_attempted"] == 1
    assert model.payloads[0]["viewport_image"] == IMAGE
    assert all("viewport_image" not in payload for payload in model.payloads[1:])
    metrics = report["performance"]["navigation_context"]
    assert [item["screenshot_sent"] for item in metrics] == [True, False, False]
    assert [item["screenshot_reason"] for item in metrics] == [
        "ambiguous_controls",
        "unchanged",
        "unchanged",
    ]
    assert report["performance"]["phase_calls"]["screenshot"] == 1
    assert all(text_size(payload) <= NAVIGATION_CONTEXT_CHARS for payload in model.payloads)
    assert IMAGE not in json.dumps(report) and "viewport_image" not in json.dumps(report)


def test_unmodified_dom_no_progress_gets_only_one_consented_recovery_image():
    tools = VisualTools()
    model = FakeDecider([decision("inspect"), decision("inspect"), decision("finish")])
    report = BrowserAgent(tools, model, "Collect the visible source content").run()

    assert report["status"] == "ready" and tools.image_requests == 1
    assert "viewport_image" not in model.payloads[0]
    assert model.payloads[1]["viewport_image"] == IMAGE
    assert "viewport_image" not in model.payloads[2]
    assert [item["screenshot_reason"] for item in report["performance"]["navigation_context"]] == [
        "dom_sufficient",
        "no_progress",
        "unchanged",
    ]
    assert IMAGE not in json.dumps(report)


def test_oversized_complete_request_stops_before_a_model_call_or_screenshot():
    tools = VisualTools()
    model = FakeDecider([decision("finish")])
    instructions = "Read source content. " + "complete-request-word " * 1500
    report = BrowserAgent(tools, model, instructions).run()

    assert report["status"] == "paused" and report["calls"] == 0
    assert model.payloads == [] and tools.image_requests == 0
    assert not tools.pages and not report["actions"]
    assert "navigation context budget" in report["guidance"]
    assert "No model call ran" in report["guidance"]
    assert report["performance"]["phase_calls"]["context"] == 1
    assert report["performance"]["phase_calls"].get("model", 0) == 0
    assert report["failure"]["no_action_from_failed_decision"]


def test_optimized_search_finishes_with_complete_unfiltered_source_for_extraction():
    tools = VisibleSearchTools()
    model = FakeDecider(
        [
            decision("click", "0:search", purpose="submit_search"),
            decision("finish", evidence="Hotel results and their displayed prices are visible."),
        ]
    )
    agent = BrowserAgent(tools, model, TASK + " Include prices from 250 to 350 USD nightly.")
    report = agent.run()

    assert report["status"] == "ready" and report["calls"] == 2
    assert tools.events.count("click") == tools.events.count("capture") == 1
    assert [entry["status"] for entry in report["actions"]] == [
        "search_transition_observed",
        "source_collection_ready",
    ]
    assert model.payloads[1]["task_checklist"]["search_submitted"]
    assert not model.payloads[1]["task_checklist"]["pending_fields"]
    source = agent.captured_sources()[0]
    assert source["url"] == "https://example.org/results"
    assert "300 USD" in source["text"] and "500 USD" in source["text"]
    assert source["browser_task_context"]["status"] == "form_verified_search_submitted"
    assert not source["browser_task_context"]["availability_verified"]
    assert "records" not in report
    for metric, payload in zip(
        report["performance"]["navigation_context"], model.payloads, strict=True
    ):
        assert metric["text_chars"] == text_size(payload) <= NAVIGATION_CONTEXT_CHARS
    # A caller cannot mutate the captured source retained for downstream extraction.
    saved_source = copy.deepcopy(tools.pages[0])
    source["text"] = "changed by caller"
    assert tools.pages[0] == saved_source


def test_actual_response_cache_metrics_are_a_subset_not_extra_input_tokens(monkeypatch):
    response = response_body(text=decision("finish").model_dump_json())
    response["usage"]["input_tokens_details"]["cached_tokens"] = 40
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=response))
    try:
        tools = VisualTools()
        report = BrowserAgent(tools, model, "Collect the visible source content").run()
        assert report["status"] == "ready" and len(calls) == 1
        assert report["usage"] == {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "cached_input_tokens": 40,
        }
        diagnostics = report["decision_diagnostics"][0]
        assert diagnostics["usage"]["cached_input_tokens"] == 40
        assert safe_decision_metadata(model.last_decision)["usage"]["cached_input_tokens"] == 40
        request = json.loads(calls[0].content)
        assert request["max_output_tokens"] == 1200 and request["store"] is False
        actual_text = request["input"][1]["content"]
        assert isinstance(actual_text, str)
        assert len(actual_text) == diagnostics["input_chars"] <= NAVIGATION_CONTEXT_CHARS
        assert (
            diagnostics["input_chars"]
            == report["performance"]["navigation_context"][0]["text_chars"]
        )
        assert diagnostics["system_chars"] > 0 and diagnostics["schema_chars"] > 0
        assert report["visual_calls_attempted"] == 0 and IMAGE not in json.dumps(report)
    finally:
        model.close()
