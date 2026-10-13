"""Offline agent decisions and opt-in local browser tools; no live API/site calls."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo import browser_agent
from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserDecision,
    BrowserRequirement,
    DOMBrowserTools,
    OpenAIBrowserDecider,
    counter_action_evidence,
    resolve_counter_decision,
)
from agentic_web_demo.browser_context import build_navigation_context
from agentic_web_demo.browser_runtime import identity
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.app import ASSETS, BrowserAction


def decision(action, control_id=None, value="", evidence="Visible source content", **changes):
    return BrowserDecision(
        action=action,
        control_id=control_id,
        value=value,
        explanation=f"Next: {action}",
        evidence=evidence,
        **changes,
    )


class FakeTools:
    def __init__(self):
        self.pages, self.references, self.events = [], {}, []
        self.secrets = ()
        self.allowed = True
        self.password = False
        self.version = 0

    def guard(self):
        if not self.allowed:
            raise WebsiteError("Cancelled by user")

    def observe(self):
        self.events.append("observe")
        return {
            "url": "https://example.org/",
            "version": self.version,
            "frames": [{"password_or_code_visible": self.password}],
        }

    def execute(self, action):
        self.events.append(action.action)
        self.version += 1
        return {"status": "action_performed"}

    def capture(self, kind="page"):
        self.events.append("capture")
        self.pages = [{"url": "https://example.org/", "text": "Source text", "source_kind": kind}]


class FakeDecider:
    def __init__(self, actions):
        self.actions, self.payloads = iter(actions), []
        self.usage = {}

    def decide(self, payload, timeout):
        self.payloads.append(payload)
        assert 0 < timeout <= 30
        return next(self.actions)


def test_real_graph_observes_again_after_each_action_and_retains_state():
    tools = FakeTools()
    model = FakeDecider([decision("wait"), decision("finish")])
    agent = BrowserAgent(tools, model, "Get visible information")
    report = agent.run()
    assert report["status"] == "ready" and report["calls"] == 2
    assert tools.events == ["observe", "wait", "observe", "capture"]
    assert model.payloads[1]["observation"]["version"] == 1
    assert model.payloads[1]["recent_actions"][0]["action"] == "wait"
    assert agent.captured_sources()[0]["source_kind"] == "page"


def test_autocomplete_settling_reads_new_owned_options_without_an_extra_decision():
    field = {
        "id": "0:field",
        "tag": "INPUT",
        "type": "text",
        "role": "combobox",
        "name": "destination",
        "label": "Destination",
        "value": "New York",
        "option_ids": ["0:choice"],
    }

    def snapshot(primary):
        return {
            "document_id": "page",
            "frames": [
                {
                    "controls": [
                        copy.deepcopy(field),
                        {
                            "id": "0:choice",
                            "role": "option",
                            "label": primary,
                            "option_primary": primary,
                            "text": primary,
                        },
                    ]
                }
            ],
        }

    old = snapshot("Charlotte")
    tools = FakeTools()
    tools.page = SimpleNamespace(wait_for_timeout=lambda _: tools.events.append("read_only_wait"))
    snapshots = iter([snapshot("New York"), snapshot("New York")])
    tools.observe = lambda: next(snapshots)
    pending = {
        "binding": {"document": "page", "identity": identity(field)},
        "value": "New York",
        "before_options": (("Charlotte", "Charlotte", "Charlotte"),),
    }
    result = DOMBrowserTools.settle_autocomplete(tools, old, pending)
    assert result["frames"][0]["controls"][1]["option_primary"] == "New York"
    assert tools.events == ["read_only_wait", "read_only_wait"]
    assert not tools.pages


def test_unsettled_autocomplete_exposes_pending_state_without_selecting_a_city():
    field = {
        "id": "0:field",
        "tag": "INPUT",
        "type": "text",
        "role": "combobox",
        "name": "destination",
        "label": "Destination",
        "value": "New York",
        "option_ids": ["0:choice"],
    }
    old = {
        "document_id": "page",
        "frames": [
            {
                "controls": [
                    field,
                    {
                        "id": "0:choice",
                        "role": "option",
                        "label": "Charlotte",
                        "option_primary": "Charlotte",
                        "text": "Charlotte",
                    },
                ]
            }
        ],
    }
    tools = FakeTools()
    pending = {
        "binding": {"document": "page", "identity": identity(field)},
        "value": "New York",
        "before_options": (("Charlotte", "Charlotte", "Charlotte"),),
    }
    result = DOMBrowserTools.settle_autocomplete(tools, old, pending, max_seconds=0)
    assert result["frames"][0]["controls"][0]["suggestions_pending"]
    assert not tools.events and not tools.pages


def test_repeated_ungrounded_new_fields_do_not_spend_the_entire_call_budget():
    requirement = BrowserRequirement(
        name="category", expected="luxury", application="extraction", request_quote=""
    )
    model = FakeDecider([decision("wait", requirements=[requirement]) for _ in range(3)])
    tools = FakeTools()
    report = BrowserAgent(tools, model, "Collect visible source information").run()
    assert report["status"] == "paused" and report["calls"] == 3
    assert "Three consecutive requirement declarations failed" in report["guidance"]
    assert all(item["status"] == "requirement_rejected" for item in report["actions"])
    assert tools.events == ["observe", "observe", "observe"] and not tools.pages


def test_paused_agent_resumes_same_history_and_does_not_reset_call_budget():
    tools = FakeTools()
    agent = BrowserAgent(tools, FakeDecider([decision("pause"), decision("finish")]), "Task")
    assert agent.run()["status"] == "paused"
    report = agent.run()
    assert report["status"] == "ready" and report["calls"] == 2
    assert len(report["actions"]) == 2


def test_call_limit_never_silently_restarts_on_resume():
    agent = BrowserAgent(FakeTools(), FakeDecider([decision("pause")]), "Task", max_calls=1)
    agent.run()
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert "model-call limit" in report["guidance"]


def test_mfa_form_pauses_before_any_model_call():
    tools = FakeTools()
    tools.password = True
    model = FakeDecider([])
    report = BrowserAgent(tools, model, "Task").run()
    assert report["status"] == "paused" and report["calls"] == 0
    assert not model.payloads


def test_cancellation_during_inference_cannot_execute_returned_action():
    tools = FakeTools()

    class CancelDecider:
        def decide(self, payload, timeout):
            tools.allowed = False
            return decision("click", "0:0")

    report = BrowserAgent(tools, CancelDecider(), "Task").run()
    assert report["status"] == "paused"
    assert tools.events == ["observe"] and not tools.pages


def test_tool_failure_is_fed_back_for_a_new_decision_not_blindly_retried():
    tools = FakeTools()

    def fail(action):
        tools.events.append(action.action)
        raise WebsiteError("No unique option remained")

    tools.execute = fail
    model = FakeDecider([decision("click", "0:0"), decision("pause")])
    report = BrowserAgent(tools, model, "Task").run()
    assert report["status"] == "paused"
    assert model.payloads[1]["recent_actions"][0]["status"] == "not_completed"
    assert tools.events.count("click") == 1


def test_model_action_history_is_bounded_without_mutating_full_evidence():
    history = [
        {
            "step": index,
            "action": "set_counter",
            "control": "Quantity " + "Q" * 400,
            "status": "not_completed",
            "expected": "3",
            "observed": "2",
            "guidance": "Current counter failure " + "G" * 400,
            "explanation": "Observe again " + "E" * 400,
            "evidence": "Source counter " + "V" * 400,
            "purpose": "set_field",
            "note": "Read-back " + "N" * 400,
            "counter_field": "quantity",
            "control_id": f"0:outdated-{index}",
            "available_counters": [{"id": f"0:{n}", "text": "X" * 500} for n in range(30)],
            "counter_evidence": {"selected_control_id": "0:outdated"},
            "verification": {"new_controls": [{"id": "0:old"}]},
        }
        for index in range(1, 16)
    ]
    original = copy.deepcopy(history)
    recent = build_navigation_context({"recent_actions": history})["recent_actions"]
    assert 0 < len(recent) <= 3 and len(json.dumps(recent, ensure_ascii=False)) <= 2200
    assert recent[-1]["step"] == 15
    assert [entry["step"] for entry in recent] == sorted(entry["step"] for entry in recent)
    assert recent[-1]["guidance"].startswith("Current counter failure")
    for entry in recent:
        assert set(entry) <= {
            "step",
            "action",
            "control",
            "status",
            "expected",
            "observed",
            "guidance",
            "explanation",
            "evidence",
            "purpose",
            "note",
            "counter_field",
        }
        assert all(len(value) <= 120 for value in entry.values() if isinstance(value, str))
    assert "outdated" not in json.dumps(recent)
    assert history == original


def test_graph_sends_compact_failure_context_but_keeps_full_report_history():
    tools = FakeTools()
    message = "Latest action failure: no matching quantity control. " + "F" * 2000

    def fail(action):
        tools.events.append(action.action)
        raise WebsiteError(message)

    tools.execute = fail
    model = FakeDecider([decision("click", "0:0"), decision("pause")])
    agent = BrowserAgent(tools, model, "Read source")
    prior = [
        {
            "step": index,
            "action": "inspect",
            "control": "Old widget",
            "status": "inventory_focus_changed",
            "evidence": "Full evidence " + "E" * 1000,
            "available_counters": [{"id": "0:stale", "value": n} for n in range(100)],
        }
        for index in range(1, 15)
    ]
    agent.history = copy.deepcopy(prior)
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == 2
    assert report["actions"][:14] == prior
    assert report["actions"][14]["guidance"] == message
    recent = model.payloads[1]["recent_actions"]
    assert len(recent) <= 3 and len(json.dumps(recent, ensure_ascii=False)) <= 2200
    assert recent[-1]["status"] == "not_completed"
    assert recent[-1]["guidance"] == message[:120]
    assert "available_counters" not in json.dumps(recent)
    assert "control_id" not in json.dumps(recent)
    assert model.payloads[1]["loop_contract"]["action_history_bounded"] is True
    assert tools.events.count("click") == 1


def test_missing_finish_evidence_does_not_capture_or_claim_readiness():
    tools = FakeTools()
    report = BrowserAgent(tools, FakeDecider([decision("finish", evidence="")]), "Task").run()
    assert report["status"] == "paused" and not tools.pages


def test_same_action_without_changed_observation_stops_after_two_attempts():
    tools = FakeTools()
    tools.execute = lambda _: {"status": "not_completed"}
    model = FakeDecider([decision("click", "0:0") for _ in range(3)])
    report = BrowserAgent(tools, model, "Task").run()
    assert report["status"] == "paused" and len(report["actions"]) == 2
    assert "no observable progress" in report["guidance"]


def test_browser_command_requires_explicit_paid_consent_and_keeps_manual_alternative():
    control = BrowserControl()
    control.update("waiting", "Ready")
    with pytest.raises(WebsiteError, match="Authorize"):
        control.command("agent_start")
    assert not control.agent_requested.is_set()
    control.command("agent_start", agent_confirmed=True)
    assert control.agent_requested.is_set() and control.state == "agent_running"
    control.set_agent_report(
        {
            "status": "paused",
            "guidance": "Choose a location",
            "captured_pages": ["https://example.org/"],
        }
    )
    control.command("agent_collect", agent_confirmed=True)
    assert control.state == "agent_collecting"
    control.set_agent_report({"status": "paused", "guidance": "Choose a location"})
    control.command("agent_manual")
    assert control.state == "waiting"
    assert BrowserAction(agent_confirmed=True).agent_confirmed


def test_api_adapter_uses_account_settings_no_storage_and_no_retries(monkeypatch):
    received = {}

    class MockClient:
        def __init__(self, **kwargs):
            received["settings"] = kwargs
            self.responses = self

        def close(self):
            received["settings"]["http_client"].close()
            received["closed"] = True

        def create(self, **kwargs):
            received["request"] = kwargs
            return SimpleNamespace(
                status="completed",
                output_text=decision("pause").model_dump_json(),
                output=[
                    SimpleNamespace(
                        type="message",
                        phase=None,
                        status="completed",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text=decision("pause").model_dump_json(),
                            )
                        ],
                    )
                ],
                usage=SimpleNamespace(input_tokens=3, output_tokens=4, total_tokens=7),
            )

    monkeypatch.setattr(browser_agent, "OpenAI", MockClient)
    decider = OpenAIBrowserDecider(
        SimpleNamespace(api_key="fixture-only", model="fixture-model", max_output_tokens=1200)
    )
    try:
        assert decider.decide({"task": "fixture"}, 10).action == "pause"
        assert received["settings"]["max_retries"] == 0
        assert received["request"]["store"] is False
        assert received["request"]["model"] == "fixture-model"
        assert received["request"]["timeout"] == 10
        assert decider.usage["total_tokens"] == 7
    finally:
        decider.close()
    assert received["closed"]


def test_dashboard_exposes_agent_as_a_separate_opt_in_path():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    assert "Run browser agent · paid API" in script
    assert "agent_confirmed: agentCheckbox.checked" in script
    assert "Browser-agent action evidence" in script
    assert "Prepare complete hotel search · no API call" in script


@pytest.fixture
def agent_page(request):
    yield from shared_local_page.__wrapped__(request)


def tools_for(page):
    return DOMBrowserTools(
        page,
        "https://example.org",
        lambda: {"url": page.url, "text": page.locator("body").inner_text()},
        lambda: True,
        lambda: False,
    )


def controls(observation):
    return [control for frame in observation["frames"] for control in frame["controls"]]


def test_local_autocomplete_preserves_subtitles_for_agent_disambiguation(agent_page):
    agent_page.set_content("""<input name=ss placeholder='Search in your own words'>
      <ul><li role=option onclick="document.querySelector('input').value='New York';
        this.parentElement.remove()">
        <b>New York</b><span>New York, United States of America</span></li>
      <li role=option><b>New York</b><span>Search with AI</span></li></ul>""")
    tools = tools_for(agent_page)
    observed = controls(tools.observe())
    options = [c for c in observed if c["role"] == "option"]
    assert len(options) == 2
    assert "United States" in options[0]["text"] and "Search with AI" in options[1]["text"]
    tools.execute(decision("click", options[0]["id"]))
    assert agent_page.locator("input").input_value() == "New York"


def test_local_generic_fill_dates_and_native_occupancy_select_are_read_back(agent_page):
    agent_page.set_content("""<input type=date aria-label='Check-in'>
      <select aria-label=Adults><option value=2>2 adults</option>
        <option value=3>3 adults</option></select>""")
    tools = tools_for(agent_page)
    initial = controls(tools.observe())
    date_control = next(c for c in initial if c["type"] == "date")
    outcome = tools.execute(decision("fill", date_control["id"], "2026-10-28"))
    assert outcome["status"] == "value_verified"
    current = controls(tools.observe())
    adults = next(c for c in current if c["tag"] == "SELECT")
    assert tools.execute(decision("select", adults["id"], "3 adults"))["observed"] == "3"


def test_local_secret_controls_and_hidden_text_are_not_sent_to_model(agent_page):
    agent_page.set_content("""<main><p>Public content</p><p hidden>Hidden private content</p>
      <input type=password value=secret><input type=email value=private@example.org>
      <input autocomplete=one-time-code value=123456></main>""")
    observation = tools_for(agent_page).observe()
    assert observation["frames"][0]["password_or_code_visible"]
    assert not controls(observation)
    assert "Hidden private" not in observation["frames"][0]["text"]


def test_local_source_captures_keep_index_and_detail_roles_without_inventing_them(agent_page):
    tools = tools_for(agent_page)
    agent_page.set_content("<main>Index fixture</main>")
    tools.capture("index")
    agent_page.goto("https://example.org/details")
    tools.capture("detail")
    assert tools.pages[1]["parent_url"] == tools.pages[0]["url"]
    assert tools.pages[1]["source_kind"] == "detail"
    assert tools.capture("detail")["status"] == "already_captured"


def test_local_sensitive_action_is_not_executed(agent_page):
    agent_page.set_content("<button onclick='window.paid=true'>Book now</button>")
    tools = tools_for(agent_page)
    control = controls(tools.observe())[0]
    with pytest.raises(WebsiteError, match="outside information retrieval"):
        tools.execute(decision("click", control["id"]))
    assert agent_page.evaluate("window.paid") is None


def test_local_dynamic_calendar_and_occupancy_loop_reobserves_new_controls(agent_page):
    agent_page.set_content("""<main>Hotel search fixture
      <button onclick="dates.hidden=false">Select dates</button>
      <div id=dates role=dialog hidden>
        <button data-date=2026-10-28 aria-checked=false
          onclick="this.setAttribute('aria-checked','true')">October 28 2026</button>
        <button data-date=2026-10-30 aria-checked=false
          onclick="this.setAttribute('aria-checked','true');dates.hidden=true">
          October 30 2026</button>
      </div>
      <button onclick="guests.hidden=false">Guests</button>
      <div id=guests role=dialog hidden>
        <label>Adults <span id=adultCount>2</span>
          <button aria-label='Increase adults' onclick="adultCount.textContent='3'">+</button>
        </label>
        <label>Rooms <span id=roomCount>1</span>
          <button aria-label='Increase rooms' onclick="roomCount.textContent='2'">+</button>
        </label>
        <button onclick="guests.hidden=true">Done</button>
      </div>
      <button onclick="document.querySelector('main').innerHTML=
        '<h1>New York results</h1><p>Hotel USD 300 per night</p>'">Search</button>
    </main>""")

    class LocalScriptedModel:
        def __init__(self):
            self.labels = iter(
                [
                    "Select dates",
                    "October 28 2026",
                    "October 30 2026",
                    "Guests",
                    "Increase adults",
                    "Increase rooms",
                    "Done",
                    "Search",
                ]
            )

        def decide(self, payload, timeout):
            label = next(self.labels, None)
            if label is None:
                assert "New York results" in payload["observation"]["frames"][0]["text"]
                return decision("finish")
            matches = [c for c in controls(payload["observation"]) if c["label"] == label]
            assert len(matches) == 1
            return decision("click", matches[0]["id"])

    report = BrowserAgent(tools_for(agent_page), LocalScriptedModel(), "Hotel task").run()
    assert report["status"] == "ready" and report["calls"] == 9
    assert report["captured_pages"] == ["https://example.org/"]


def test_local_changed_suggestion_is_not_clicked_using_stale_evidence(agent_page):
    agent_page.set_content("<ul><li role=option>New York</li></ul>")
    tools = tools_for(agent_page)
    choice = controls(tools.observe())[0]
    agent_page.locator("li").evaluate("e=>e.textContent='Newark'")
    with pytest.raises(WebsiteError, match="changed identity"):
        tools.execute(decision("click", choice["id"]))


def occupancy_markup():
    """Decorative SVG buttons; row labels are outside the nested stepper wrapper."""
    rows = []
    for label, count in (("Adults", 2), ("Children", 0), ("Rooms", 1)):
        rows.append(f"""<div class=row><span>{label}</span><div><div><div>
          <button data-testid=counter-button {"disabled" if count == 0 else ""}
            onclick="this.parentElement.querySelector('.count').textContent--">
            <svg aria-hidden=true width=24 height=24 viewBox='0 0 24 24'>
              <rect x=4 y=11 width=16 height=2 /></svg></button>
          <span class=count>{count}</span>
          <button data-testid=counter-button
            onclick="this.parentElement.querySelector('.count').textContent++">
            <svg aria-hidden=true width=24 height=24 viewBox='0 0 24 24'>
              <path d='M4 11 H11 V4 H13 V11 H20 V13 H13 V20 H11 V13 H4 Z'/>
            </svg></button>
        </div></div></div></div>""")
    return (
        "<section>" + "".join(rows) + "<p>Traveling with pets?</p><button>Done</button></section>"
    )


def test_local_icon_only_occupancy_buttons_expose_rows_counts_and_readback(agent_page):
    agent_page.set_content(occupancy_markup())
    tools = tools_for(agent_page)
    for label, before, after in (("Adults", 2, 3), ("Rooms", 1, 2), ("Rooms", 2, 1)):
        action = "increase" if after > before else "decrease"
        matches = [
            c
            for c in controls(tools.observe())
            if c.get("counter")
            and c["counter"]["label"] == label
            and c["counter"]["direction"] == action
        ]
        assert len(matches) == 1
        control = matches[0]
        assert control["label"] == f"{action} {label}"
        assert control["counter"]["value"] == before
        result = tools.execute(decision("click", control["id"]))
        assert result["status"] == "counter_verified"
        assert result["before"] == before
        assert result["expected"] == result["observed"] == after
    fresh = controls(tools.observe())
    children = [c for c in fresh if (c.get("counter") or {}).get("label") == "Children"]
    assert len(children) == 2 and all(c["counter"]["value"] == 0 for c in children)
    assert not next(c for c in children if c["counter"]["direction"] == "decrease")["enabled"]


def test_local_occupancy_counters_survive_background_inventory_limit(agent_page):
    background = "".join(f"<a href='/item-{i}'>Background {i}</a>" for i in range(160))
    agent_page.set_content(background + occupancy_markup())
    observation = tools_for(agent_page).observe()
    assert observation["frames"][0]["controls_truncated"]
    counters = [c["counter"] for c in controls(observation) if c.get("counter")]
    assert len(counters) == 6
    assert {c["label"] for c in counters} == {"Adults", "Children", "Rooms"}


def test_local_search_form_widgets_are_not_lost_behind_background_link_limit(agent_page):
    background = "".join(f"<a href='/item-{i}'>Background {i}</a>" for i in range(170))
    agent_page.set_content(
        background
        + """<form>
      <input aria-label=Destination value='New York'>
      <button type=button>Select dates</button><button type=button>Select guests and rooms</button>
      <button type=submit>Find stays</button></form>"""
    )
    fresh = controls(tools_for(agent_page).observe())
    assert {"Destination", "Select dates", "Select guests and rooms", "Find stays"} <= {
        c["label"] for c in fresh
    }
    assert next(c for c in fresh if c["label"] == "Find stays")["submits_form"]
    assert not next(c for c in fresh if c["label"] == "Select dates")["submits_form"]


def test_local_counter_stale_count_is_not_clicked(agent_page):
    agent_page.set_content(occupancy_markup())
    tools = tools_for(agent_page)
    control = next(c for c in controls(tools.observe()) if c["label"] == "increase Adults")
    agent_page.locator(".count").first.evaluate("e=>e.textContent='4'")
    with pytest.raises(WebsiteError, match="counter changed"):
        tools.execute(decision("click", control["id"]))
    assert agent_page.locator(".count").first.inner_text() == "4"


def test_local_counter_no_effect_is_unconfirmed_not_success(agent_page):
    agent_page.set_content(occupancy_markup())
    agent_page.locator("button").evaluate_all(
        "buttons=>buttons.forEach(b=>b.removeAttribute('onclick'))"
    )
    tools = tools_for(agent_page)
    control = next(c for c in controls(tools.observe()) if c["label"] == "increase Rooms")
    result = tools.execute(decision("click", control["id"]))
    assert result["status"] == "counter_unconfirmed"
    assert result["expected"] == 2 and result["observed"] == 1


@pytest.mark.parametrize("description", ["Ages 18 or above", "Ages <span>18</span> or above"])
def test_local_counter_age_description_does_not_hide_the_actual_quantity(agent_page, description):
    markup = occupancy_markup().replace(
        "<span>Adults</span>", f"<span>Adults</span><p>{description}</p>"
    )
    agent_page.set_content(markup)
    tools = tools_for(agent_page)
    options = [
        c
        for c in controls(tools.observe())
        if c.get("counter") and "Adults" in c["counter"]["label"]
    ]
    assert len(options) == 2 and all(c["counter"]["value"] == 2 for c in options)


@pytest.mark.parametrize(
    "label,target,direction,steps",
    [("Adults", "5", "increase", 3), ("Rooms", "3", "increase", 2), ("Adults", "1", "decrease", 1)],
)
def test_local_set_counter_reaches_target_with_checked_steps(
    agent_page, label, target, direction, steps
):
    agent_page.set_content(occupancy_markup())
    tools = tools_for(agent_page)
    control = next(c for c in controls(tools.observe()) if c["label"] == f"{direction} {label}")
    result = tools.execute(decision("set_counter", control["id"], target))
    assert result["status"] == "counter_verified"
    assert result["observed"] == int(target) and result["steps"] == steps
    assert agent_page.locator(".count").nth(1).inner_text() == "0"


def test_local_set_counter_stops_after_first_click_with_no_effect(agent_page):
    agent_page.set_content(occupancy_markup())
    agent_page.locator("button").evaluate_all(
        "buttons=>buttons.forEach(b=>{b.removeAttribute('onclick');b.onclick=()=>window.clicks=(window.clicks||0)+1;})"
    )
    tools = tools_for(agent_page)
    control = next(c for c in controls(tools.observe()) if c["label"] == "increase Adults")
    result = tools.execute(decision("set_counter", control["id"], "5"))
    assert result["status"] == "counter_unconfirmed" and result["observed"] == 2
    assert agent_page.evaluate("window.clicks") == 1


def test_set_counter_cannot_change_an_unrequested_field():
    tools = FakeTools()
    tools.references["0:rooms"] = (
        None,
        None,
        {"label": "increase Rooms", "counter": {"label": "Rooms", "value": 1}},
    )
    model = FakeDecider([decision("set_counter", "0:rooms", "2"), decision("pause")])
    report = BrowserAgent(tools, model, "Collect visible content").run()
    assert "set_counter" not in tools.events
    assert "requested occupancy" in report["actions"][0]["guidance"]


def counter_refs():
    refs = {
        "0:label": (None, None, {"label": "Adults", "tag": "BUTTON"}),
        "0:summary": (None, None, {"label": "2 adults, 0 children, 1 room", "tag": "BUTTON"}),
    }
    for direction in ("increase", "decrease"):
        refs[f"0:{direction}"] = (
            None,
            None,
            {
                "label": "Adults",
                "tag": "BUTTON",
                "enabled": True,
                "counter": {
                    "label": "Adults",
                    "value": 2,
                    "direction": direction,
                    "evidence": "Adults 2",
                },
            },
        )
    return refs


@pytest.mark.parametrize("control_id", ["0:label", "0:increase", "0:decrease"])
@pytest.mark.parametrize("target", ["3", "3 adults", "03"])
def test_counter_target_binds_label_or_either_button_to_requested_absolute_count(
    control_id, target
):
    task = TaskLedger("Find hotels in New York for 3 adults and 2 rooms")
    resolved, field = resolve_counter_decision(
        decision("set_counter", control_id, target), task, counter_refs()
    )
    assert field == "adults" and resolved.value == "3"
    assert resolved.control_id == "0:increase" and resolved.purpose == "set_field"


@pytest.mark.parametrize("target", ["1", "4", "increase by 1", "3 rooms", "3 adults 2 rooms"])
def test_counter_resolution_never_substitutes_another_target_or_click_delta(target):
    with pytest.raises(WebsiteError, match="absolute count"):
        resolve_counter_decision(
            decision("set_counter", "0:increase", target),
            TaskLedger("Find hotels for 3 adults"),
            counter_refs(),
        )


def test_counter_resolution_rejects_mixed_summary_and_reports_detected_rows():
    task = TaskLedger("Find hotels for 3 adults and 2 rooms")
    action = decision("set_counter", "0:summary", "3")
    with pytest.raises(WebsiteError, match="mixed summary"):
        resolve_counter_decision(action, task, counter_refs())
    evidence = counter_action_evidence(action, task, counter_refs())
    assert evidence["target"] == "3" and evidence["selected_counter"] is None
    assert evidence["requested_counts"] == {"adults": "3", "rooms": "2"}
    assert len(evidence["available_counters"]) == 2


def test_counter_resolution_does_not_choose_between_two_visible_adults_rows():
    refs = counter_refs()
    refs["0:duplicate"] = refs["0:increase"]
    with pytest.raises(WebsiteError, match="2 matching controls"):
        resolve_counter_decision(
            decision("set_counter", "0:label", "3"), TaskLedger("Find hotels for 3 adults"), refs
        )


def test_counter_resolution_does_not_retarget_into_another_frame():
    refs = counter_refs()
    refs["1:increase"] = refs.pop("0:increase")
    with pytest.raises(WebsiteError, match="0 matching controls"):
        resolve_counter_decision(
            decision("set_counter", "0:label", "3"), TaskLedger("Find hotels for 3 adults"), refs
        )


def test_local_counter_external_accessible_row_label_is_observed(agent_page):
    agent_page.set_content("""<span id=quantity-label>Adults</span>
      <div role=group aria-labelledby=quantity-label>
        <button aria-label=decrease>-</button><span>2</span>
        <button aria-label=increase>+</button>
      </div>""")
    found = [c["counter"] for c in controls(tools_for(agent_page).observe()) if c.get("counter")]
    assert len(found) == 2 and all(c["label"] == "Adults" and c["value"] == 2 for c in found)


def test_local_agent_accepts_unit_labelled_target_on_accessibly_named_button(agent_page):
    agent_page.set_content(occupancy_markup())
    agent_page.locator(".row").first.locator("button").evaluate_all(
        "buttons=>buttons.forEach(b=>b.setAttribute('aria-label','Adults'))"
    )

    class CounterModel:
        def decide(self, payload, timeout):
            if payload["recent_actions"]:
                return decision("pause")
            choice = next(
                c
                for c in controls(payload["observation"])
                if (c.get("counter") or {}).get("label") == "Adults"
                and c["counter"]["direction"] == "decrease"
            )
            return decision("set_counter", choice["id"], "3 adults")

    report = BrowserAgent(tools_for(agent_page), CounterModel(), "Find hotels for 3 adults").run()
    assert report["actions"][0]["status"] == "counter_verified"
    assert report["actions"][0]["counter_evidence"]["target"] == "3 adults"
    assert agent_page.locator(".row").first.locator(".count").inner_text() == "3"


def test_local_unknown_icons_do_not_infer_directions_from_button_order(agent_page):
    agent_page.set_content("""<section><span>Adults</span><button><svg width=24 height=24>
      <circle cx=12 cy=12 r=8 /></svg></button><span>2</span><button><svg width=24 height=24>
      <circle cx=12 cy=12 r=8 /></svg></button></section>""")
    found = [c["counter"] for c in controls(tools_for(agent_page).observe()) if c["counter"]]
    assert len(found) == 2
    assert all(c["direction"] == "unknown" and c["value"] == 2 for c in found)


def test_local_agent_loop_sets_icon_only_adults_and_rooms_without_changing_children(agent_page):
    agent_page.set_content(occupancy_markup())

    class OccupancyModel:
        def decide(self, payload, timeout):
            fresh = controls(payload["observation"])
            for label, target in (("Adults", 3), ("Rooms", 2)):
                choice = next(c for c in fresh if c["label"] == f"increase {label}")
                if choice["counter"]["value"] < target:
                    return decision("click", choice["id"])
            return decision("finish", evidence="Adults 3, Children 0, Rooms 2 are visible.")

    report = BrowserAgent(tools_for(agent_page), OccupancyModel(), "3 adults, 2 rooms").run()
    assert report["status"] == "ready"
    assert [item["status"] for item in report["actions"][:2]] == [
        "counter_verified",
        "counter_verified",
    ]
    assert agent_page.locator(".count").all_inner_texts() == ["3", "0", "2"]


def test_local_new_dialog_inventory_does_not_leave_duplicate_old_handles(agent_page):
    agent_page.set_content("""<button id=opener onclick="this.hidden=true;popup.hidden=false">
      Open</button><div id=popup role=dialog hidden><button>Pick</button></div>""")
    tools = tools_for(agent_page)
    opener = controls(tools.observe())[0]
    tools.execute(decision("click", opener["id"]))
    pick = controls(tools.observe())[0]
    assert agent_page.locator('[data-agentic-loop-id="0"]').count() == 1
    tools.execute(decision("click", pick["id"]))


def test_local_native_form_scope_includes_external_owner_not_catalogue_or_payment(agent_page):
    agent_page.set_content("""<main>
      <form id=hotel><input name=destination aria-label=Destination value='New York'>
        <input name=arrival type=date aria-label='Check-in' value='2026-10-29'>
        <button type=submit>Search</button></form>
      <input form=hotel name=rooms type=number aria-label=Rooms value=2>
      <a href='/city/new-york'>New York hotels</a>
      <form id=payment><button type=submit>Book now</button></form>
      </main>""")
    tools = tools_for(agent_page)
    before_text = agent_page.locator("body").inner_text()
    before_values = agent_page.locator("input").evaluate_all("es=>es.map(e=>e.value)")
    found = controls(tools.observe())
    search = next(item for item in found if item["label"] == "Search")
    destination = next(item for item in found if item["name"] == "destination")
    rooms = next(item for item in found if item["name"] == "rooms")
    catalogue = next(item for item in found if item["label"] == "New York hotels")
    payment = next(item for item in found if item["label"] == "Book now")
    assert search["form_scope"] == destination["form_scope"] == rooms["form_scope"]
    assert search["form_scope"].startswith("0:form:")
    assert catalogue["form_scope"] is None and not catalogue["submits_form"]
    assert payment["form_scope"] != search["form_scope"]
    assert search["submits_form"] and payment["submits_form"]
    with pytest.raises(WebsiteError, match="outside information retrieval"):
        tools.execute(decision("click", payment["id"]))
    tools.observe()
    assert agent_page.locator("body").inner_text() == before_text
    assert agent_page.locator("input").evaluate_all("es=>es.map(e=>e.value)") == before_values


def test_local_form_scope_does_not_change_when_other_form_popup_takes_priority(agent_page):
    agent_page.set_content("""<main>
      <form id=first><input name=city aria-label=Destination value='New York'>
        <button type=submit>Search</button></form>
      <form id=second><input name=category aria-label=Category value=Research>
        <section id=popup role=dialog hidden><input name=topic aria-label=Topic value=Science>
          <button type=button>Done</button></section></form>
      </main>""")
    tools = tools_for(agent_page)
    before = {
        item["name"]: item["form_scope"] for item in controls(tools.observe()) if item["name"]
    }
    agent_page.locator("#popup").evaluate("e=>e.hidden=false")
    after = {item["name"]: item["form_scope"] for item in controls(tools.observe()) if item["name"]}
    assert after["city"] == before["city"]
    assert after["category"] == before["category"]
    assert after["topic"] == after["category"]
    assert after["city"] != after["category"]


@pytest.mark.parametrize(
    ("markup", "record_count", "busy", "no_results", "ready"),
    [
        (
            "<article><a href='/hotel/one'>Hotel One</a><p>Displayed room details and USD 300 "
            "for the requested stay are visible here.</p></article>",
            1,
            False,
            False,
            True,
        ),
        (
            "<article><a href='/hotel/one'>Hotel One</a><p>Displayed room details are "
            "still loading "
            "for the requested stay.</p></article><div role=progressbar aria-label=Loading "
            "style='width:20px;height:20px'></div>",
            1,
            True,
            False,
            False,
        ),
        (
            "<section aria-busy=true><article><a href='/hotel/one'>Hotel One</a><p>Displayed room "
            "details and USD 300 are still rendering.</p></article></section>",
            1,
            True,
            False,
            False,
        ),
        ("<p>No hotels available for your selected dates.</p>", 0, False, True, True),
        (
            "<nav><article><a href='/city/new-york'>New York hotels</a><p>Popular city catalogue "
            "navigation should not count as a rendered result.</p></article></nav>",
            0,
            False,
            False,
            False,
        ),
        (
            "<div class=property><a href='/hotel/one'>Hotel One</a><p>Unfamiliar custom property "
            "markup is not independent proof that results are missing.</p></div>",
            0,
            False,
            False,
            False,
        ),
    ],
    ids=["record", "icon-spinner", "busy-container", "empty-results", "navigation", "unknown-dom"],
)
def test_local_render_readiness_facts_distinguish_records_loading_and_empty_results(
    agent_page, markup, record_count, busy, no_results, ready
):
    agent_page.set_content(f"<main>{markup}</main>")
    observed = tools_for(agent_page).observe()
    assert observed["results"] == {
        "record_count": record_count,
        "busy": busy,
        "no_results": no_results,
    }
    assert browser_agent.rendered_results_ready(observed) is ready
