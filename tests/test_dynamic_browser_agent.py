"""Cross-domain mocked decisions and opt-in local browser fixtures; no paid calls."""

import json
from types import SimpleNamespace

import pytest
from test_browser_agent import FakeDecider, FakeTools, controls, decision, tools_for
from test_browser_agent import agent_page as shared_page

from agentic_web_demo import browser_agent
from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserRequirement,
    OpenAIBrowserDecider,
    resolve_counter_decision,
)
from agentic_web_demo.browser_runtime import (
    identity,
    interaction_state,
    state_fingerprint,
    transition,
)
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.app import BrowserAction


@pytest.fixture
def agent_page(request):
    yield from shared_page.__wrapped__(request)


def observation(*items, document="form", widgets=None, text="Visible website"):
    return {
        "url": "https://example.org/",
        "document_id": document,
        "frames": [
            {
                "text": text,
                "widgets": widgets or [],
                "controls": list(items),
                "viewport": {"scroll_y": 0},
                "password_or_code_visible": False,
            }
        ],
    }


def input_control(value="", label="Search", name="q", control_id="0:q"):
    return {
        "id": control_id,
        "tag": "INPUT",
        "type": "text",
        "name": name,
        "role": "",
        "label": label,
        "value": value,
    }


@pytest.mark.parametrize(
    "instructions,name,value,label",
    [
        ("Find soccer stories", "topic", "soccer", "Search this site"),
        ("Find available laptops", "product", "laptops", "What are you looking for?"),
        ("Find cafes in Boston", "location", "Boston", "Where?"),
    ],
)
def test_generic_prompt_fields_bind_to_unrelated_native_field_names(
    instructions, name, value, label
):
    ledger = TaskLedger(instructions)
    fresh = observation(input_control(value, label))
    ledger.declare(
        [
            BrowserRequirement(
                name=name,
                expected=value,
                application="form",
                request_quote=instructions,
                control_id="0:q",
            )
        ],
        fresh,
    )
    check = ledger.observe(fresh)["requirements"][0]
    assert check["status"] == "verified" and check["method"] == "bound_control_readback"
    assert not ledger.date_resolution and not ledger.pending()


def test_interpreted_query_is_disclosed_and_source_readback_is_still_required():
    ledger = TaskLedger("Find soccer stories")
    fresh = observation(input_control("soccer"))
    ledger.declare(
        [
            BrowserRequirement(
                name="topic",
                expected="football",
                application="form",
                request_quote="soccer",
                interpretation="The site calls soccer football",
                control_id="0:q",
            )
        ],
        fresh,
    )
    check = ledger.observe(fresh)["requirements"][0]
    assert check["model_interpreted"] and check["status"] == "mismatch"
    assert (
        ledger.observe(observation(input_control("football")))["requirements"][0]["status"]
        == "verified"
    )


def test_binding_requires_fresh_id_and_never_asserts_a_value_from_model_prose():
    ledger = TaskLedger("Find laptops")
    with pytest.raises(WebsiteError, match="fresh observed"):
        ledger.declare(
            [
                BrowserRequirement(
                    name="product",
                    expected="laptops",
                    application="form",
                    request_quote="laptops",
                    control_id="0:invented",
                )
            ],
            observation(input_control()),
        )


def test_generic_binding_ambiguity_or_a_new_document_cannot_verify_a_field():
    ledger = TaskLedger("Find laptops")
    fresh = observation(input_control("laptops"))
    ledger.declare(
        [
            BrowserRequirement(
                name="product",
                expected="laptops",
                application="form",
                request_quote="laptops",
                control_id="0:q",
            )
        ],
        fresh,
    )
    assert (
        ledger.observe(observation(input_control("laptops"), document="other"))["requirements"][0][
            "status"
        ]
        != "verified"
    )
    duplicate = input_control("laptops", control_id="0:other")
    assert (
        ledger.observe(observation(input_control("laptops"), duplicate))["requirements"][0][
            "status"
        ]
        != "verified"
    )


def test_new_widget_controls_are_reported_as_an_effect_not_an_unchanged_click():
    before = observation({"id": "0:open", "tag": "BUTTON", "label": "Options", "expanded": "false"})
    after = observation(
        {"id": "0:open", "tag": "BUTTON", "label": "Options", "expanded": "true"},
        {"id": "0:new", "tag": "BUTTON", "label": "Increase quantity"},
        widgets=[{"role": "dialog", "label": "Quantity"}],
    )
    effect = transition(before, after)
    assert effect["status"] == "change_observed" and effect["widget_changed"]
    assert effect["new_controls"][0]["id"] == "0:new"
    assert state_fingerprint(before) != state_fingerprint(after)


def test_ad_text_changes_are_not_browser_action_progress():
    before = observation(input_control(), text="Ad A")
    after = observation(input_control(), text="Ad B changes every second")
    assert transition(before, after)["status"] == "no_observable_change"
    assert state_fingerprint(before) == state_fingerprint(after)


def test_normalized_control_identity_preserves_frame_without_ephemeral_id():
    raw = input_control(control_id="2:q")
    normalized_control = interaction_state(observation(raw))["controls"][0]
    assert identity(raw) == identity(normalized_control)
    assert identity(normalized_control)["frame"] == "2"


def test_control_id_renumbering_is_not_an_added_control_or_action_progress():
    before = observation(input_control(control_id="0:old"))
    after = observation(input_control(control_id="0:fresh"))
    effect = transition(before, after)
    assert effect["status"] == "no_observable_change"
    assert effect["new_controls"] == [] and effect["removed_controls"] == 0
    assert state_fingerprint(before) == state_fingerprint(after)


@pytest.mark.parametrize(
    "label", ["2 adults, 0 children, 1 room", "Adults and rooms", "3 adults, 1 child"]
)
def test_mixed_occupancy_summary_cannot_fall_through_to_generic_name_binding(label):
    ledger = TaskLedger("Find hotels for 3 adults")
    fresh = observation({"id": "0:summary", "tag": "BUTTON", "label": label})
    ledger.declare(
        [
            BrowserRequirement(
                name="adults",
                expected="3",
                application="form",
                request_quote="3 adults",
                control_id="0:summary",
            )
        ],
        fresh,
    )
    assert ledger.counter_field(controls(fresh)[0]) is None


def test_graph_fills_generic_query_submits_verifies_and_collects_source():
    class QueryTools(FakeTools):
        def __init__(self):
            super().__init__()
            self.value, self.submitted = "", False

        def observe(self):
            fresh = observation(document="results" if self.submitted else "form")
            if not self.submitted:
                fresh["frames"][0]["controls"] = [
                    input_control(self.value),
                    {
                        "id": "0:search",
                        "tag": "BUTTON",
                        "label": "Search",
                        "submits_form": True,
                    },
                ]
            self.references = {c["id"]: (None, None, c) for c in controls(fresh)}
            return fresh

        def execute(self, action):
            self.events.append(action.action)
            if action.action == "fill":
                self.value = action.value
                return {
                    "status": "value_verified",
                    "expected": action.value,
                    "observed": self.value,
                }
            self.submitted = True
            return {"status": "action_performed"}

    tools = QueryTools()
    model = FakeDecider(
        [
            decision(
                "fill",
                "0:q",
                "football",
                purpose="set_field",
                requirements=[
                    BrowserRequirement(
                        name="topic",
                        expected="football",
                        application="form",
                        request_quote="soccer",
                        interpretation="Soccer is called football here",
                        control_id="0:q",
                    )
                ],
            ),
            decision("click", "0:search", purpose="submit_search"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, "Find soccer stories").run()
    assert report["status"] == "ready" and report["calls"] == 3
    assert report["task_checklist"]["search_submitted"]
    assert report["actions"][0]["verification"]["changed_controls"][0]["after"] == "football"
    assert tools.pages and "viewport_image" not in model.payloads[0]


def test_generic_numeric_counter_can_use_request_binding_without_hotel_fields():
    fresh = observation(
        {
            "id": "0:plus",
            "tag": "BUTTON",
            "label": "Add one item",
            "counter": {
                "label": "Quantity",
                "value": 1,
                "direction": "increase",
                "evidence": "Quantity 1",
            },
        }
    )
    ledger = TaskLedger("Find 3 tickets")
    ledger.declare(
        [
            BrowserRequirement(
                name="ticket_count",
                expected="3",
                application="form",
                request_quote="3 tickets",
                control_id="0:plus",
            )
        ],
        fresh,
    )
    refs = {"0:plus": (None, None, controls(fresh)[0])}
    resolved, field = resolve_counter_decision(decision("set_counter", "0:plus", "3"), ledger, refs)
    assert field == "ticket_count" and resolved.control_id == "0:plus"


def test_visual_mode_requires_separate_consent_and_can_be_revoked_on_resume():
    control = BrowserControl()
    control.update("waiting", "Ready")
    control.command("agent_start", agent_confirmed=True)
    assert not control.agent_visual_enabled
    control.set_agent_report({"status": "paused", "captured_pages": [], "guidance": "Inspect"})
    control.update("agent_paused", "Inspect")
    control.command("agent_resume", agent_confirmed=True, agent_visual_confirmed=True)
    assert control.agent_visual_enabled
    control.update("agent_paused", "Inspect")
    control.command("agent_resume", agent_confirmed=True)
    assert not control.agent_visual_enabled and not BrowserAction().agent_visual_confirmed


def test_image_payload_uses_input_image_and_never_serializes_base64_into_text(
    monkeypatch,
):
    received = {}

    class Client:
        def __init__(self, **kwargs):
            self.http = kwargs["http_client"]
            self.responses = self

        def close(self):
            self.http.close()

        def create(self, **kwargs):
            received.update(kwargs)
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
                usage=None,
            )

    monkeypatch.setattr(browser_agent, "OpenAI", Client)
    image = "data:image/jpeg;base64,ZmFrZS1pbWFnZQ=="
    model = OpenAIBrowserDecider(
        SimpleNamespace(api_key="fixture", model="fixture-model", max_output_tokens=900)
    )
    try:
        model.decide({"task": "Find laptops", "viewport_image": image}, 10)
    finally:
        model.close()
    content = received["input"][1]["content"]
    assert content[1] == {"type": "input_image", "image_url": image, "detail": "high"}
    assert "viewport_image" not in json.loads(content[0]["text"])
    assert received["store"] is False and received["model"] == "fixture-model"
    assert model.last_decision["input_chars"] == len(content[0]["text"])
    assert image not in json.dumps(model.last_decision)


def test_failed_visual_capture_does_not_attempt_a_model_call():
    tools = FakeTools()
    tools.visual_enabled = True

    def blocked():
        raise WebsiteError("Finish sign-in/MFA before using visual observation.")

    tools.viewport_image = blocked
    model = FakeDecider([])
    report = BrowserAgent(tools, model, "Find laptops").run()
    assert report["status"] == "paused" and report["calls"] == 0 and not model.payloads


def test_local_open_shadow_fields_are_observed_and_editable(agent_page):
    agent_page.set_content("<div id=host></div>")
    agent_page.evaluate("""() => {
      document.querySelector('#host').attachShadow({mode:'open'}).innerHTML=
      '<label>Product<input name=q type=search></label><button>Search</button>';
    }""")
    tools = tools_for(agent_page)
    field = next(c for c in controls(tools.observe()) if c["name"] == "q")
    outcome = tools.execute(decision("fill", field["id"], "laptops"))
    assert outcome["status"] == "value_verified"
    assert tools.observe()["frames"][0]["controls"][0]["value"] == "laptops"


def test_local_contenteditable_and_checkbox_have_actual_readback(agent_page):
    agent_page.set_content("""<div role=textbox contenteditable=true aria-label=Topic></div>
      <label><input type=checkbox name=available>Available only</label>""")
    tools = tools_for(agent_page)
    field = next(c for c in controls(tools.observe()) if c.get("editable"))
    assert tools.execute(decision("fill", field["id"], "science"))["observed"] == "science"
    checkbox = next(c for c in controls(tools.observe()) if c["name"] == "available")
    assert tools.execute(decision("check", checkbox["id"], "true"))["observed"] == "true"
    checkbox = next(c for c in controls(tools.observe()) if c["name"] == "available")
    assert tools.execute(decision("check", checkbox["id"], "true"))["observed"] == "true"


def test_local_inspection_focus_changes_inventory_without_a_website_action(agent_page):
    agent_page.set_content("<form><input name=q aria-label=Product><button>Search</button></form>")
    tools = tools_for(agent_page)
    outcome = tools.execute(decision("inspect", value="form"))
    assert outcome["status"] == "inventory_focus_changed"
    assert tools.observe()["frames"][0]["focus"] == "form"


def test_local_screenshot_without_consent_is_not_taken(agent_page, monkeypatch):
    tools = tools_for(agent_page)
    monkeypatch.setattr(agent_page, "screenshot", lambda **_: pytest.fail("No screenshot consent"))
    with pytest.raises(WebsiteError, match="authorized"):
        tools.viewport_image()


def test_local_visual_observation_has_no_disk_output_or_injected_labels(agent_page, monkeypatch):
    agent_page.set_content("<input aria-label=Topic><button>Search</button>")
    tools = tools_for(agent_page)
    tools.visual_enabled = True
    tools.observe()
    calls = []
    agent_page.evaluate("""() => {
      window.visualLabelMutations=0;
      new MutationObserver(records=>{
        for(const record of records) for(const node of record.addedNodes)
          if(node.nodeType===1 && node.matches('[data-agentic-visual-label]'))
            window.visualLabelMutations++;
      }).observe(document.documentElement,{childList:true,subtree:true});
    }""")

    def image(**kwargs):
        calls.append(kwargs)
        assert agent_page.locator("[data-agentic-visual-label]").count() == 0
        return b"fixture"

    monkeypatch.setattr(agent_page, "screenshot", image)
    assert tools.viewport_image().startswith("data:image/jpeg;base64,")
    assert "path" not in calls[0] and calls[0]["full_page"] is False
    assert calls[0]["scale"] == "css" and calls[0]["mask"]
    assert agent_page.locator("[data-agentic-visual-label]").count() == 0
    assert agent_page.evaluate("window.visualLabelMutations") == 0


def test_local_visible_mfa_prevents_screenshot_before_any_image_capture(agent_page, monkeypatch):
    agent_page.set_content("<input name=code autocomplete=one-time-code>")
    tools = tools_for(agent_page)
    tools.visual_enabled = True
    tools.observe()
    monkeypatch.setattr(
        agent_page, "screenshot", lambda **_: pytest.fail("MFA screen must not be sent")
    )
    with pytest.raises(WebsiteError, match="MFA"):
        tools.viewport_image()
