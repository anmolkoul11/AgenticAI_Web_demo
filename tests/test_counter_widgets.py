"""Generic quantity-widget regressions; browser fixtures are local and opt-in."""

import pytest
from test_browser_agent import agent_page as shared_agent_page
from test_browser_agent import controls, decision, tools_for

from agentic_web_demo.browser_agent import BrowserAgent, resolve_counter_decision
from agentic_web_demo.browser_task import TaskLedger, compact_observation
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError


@pytest.fixture
def agent_page(request):
    yield from shared_agent_page.__wrapped__(request)


def quantity_widget(
    label="Adults", count=2, *, role="button", tag="button", icon="inline", effect="normal"
):
    """A button-like row must not hide its real child +/- controls or quantity."""
    icons = {
        "inline": (
            "<svg width=24 height=24><rect x=4 y=11 width=16 height=2 /></svg>",
            "<svg width=24 height=24>"
            "<path d='M4 11 H11 V4 H13 V11 H20 V13 H13 V20 H11 V13 H4 Z'/></svg>",
        ),
        "symbol": (
            "<svg width=24 height=24><use href='#quantity-minus'/></svg>",
            "<svg width=24 height=24><use href='#quantity-plus'/></svg>",
        ),
        "symbol-title": (
            "<svg width=24 height=24><use href='#quantity-glyph-a'/></svg>",
            "<svg width=24 height=24><use href='#quantity-glyph-b'/></svg>",
        ),
        "unknown": (
            "<svg width=24 height=24><circle cx=12 cy=12 r=8 /></svg>",
            "<svg width=24 height=24><circle cx=12 cy=12 r=8 /></svg>",
        ),
    }
    children = []
    for step, delta, artwork in zip(("down", "up"), (-1, 1), icons[icon], strict=True):
        actual_delta = delta if effect == "normal" else -delta if effect == "opposite" else 0
        activate = (
            "window.counterClicks=(window.counterClicks||0)+1;"
            "const count=this.closest('[data-counter-row]').querySelector('.count');"
            f"count.textContent=String(Number(count.textContent)+({actual_delta}));"
        )
        semantics = "type=button" if tag == "button" else "role=button tabindex=0"
        children.append(
            f'<{tag} {semantics} data-step={step} onclick="{activate}">{artwork}</{tag}>'
        )
    wrapper = f"role={role} aria-label='{label}'" if role else ""
    return (
        f"<section data-counter-row {wrapper}><span class=row-label>{label}</span>"
        f"<div class=stepper>{children[0]}<span class=count>{count}</span>{children[1]}</div>"
        "</section>"
    )


def detected(tools):
    return [control for control in controls(tools.observe()) if control.get("counter")]


def selected_step(page, tools, step):
    fresh = controls(tools.observe())
    local_id = page.locator(f'[data-step="{step}"]').get_attribute("data-agentic-loop-id")
    assert local_id is not None, "The actual child stepper must remain in the visible inventory"
    return next(control for control in fresh if control["id"] == f"0:{local_id}")


@pytest.mark.parametrize("tag", ["button", "div"])
def test_local_button_like_rows_keep_real_child_stepper_controls(agent_page, tag):
    agent_page.set_content(quantity_widget(tag=tag))
    tools = tools_for(agent_page)
    found = detected(tools)
    assert len(found) == 2
    assert {control["counter"]["direction"] for control in found} == {"increase", "decrease"}
    assert all(control["counter"]["label"] == "Adults" for control in found)
    assert all(control["counter"]["value"] == 2 for control in found)
    assert all(control["text"] != "Adults 2" for control in found)
    up = next(control for control in found if control["counter"]["direction"] == "increase")
    result = tools.execute(decision("set_counter", up["id"], "3"))
    assert result["status"] == "counter_verified" and result["observed"] == 3


def test_local_native_buttons_do_not_duplicate_nested_button_roles(agent_page):
    markup = (
        quantity_widget()
        .replace("<svg ", "<span role=button><svg ")
        .replace("</svg>", "</svg></span>")
    )
    agent_page.set_content(markup)
    found = detected(tools_for(agent_page))
    assert len(found) == 2 and all(control["tag"] == "BUTTON" for control in found)


def test_local_generic_quantity_is_not_tied_to_hotel_occupancy(agent_page):
    agent_page.set_content(quantity_widget(label="Quantity", count=4))
    tools = tools_for(agent_page)
    down = next(
        control for control in detected(tools) if control["counter"]["direction"] == "decrease"
    )
    assert down["counter"]["label"] == "Quantity"
    result = tools.execute(decision("set_counter", down["id"], "2"))
    assert result["status"] == "counter_verified" and result["observed"] == 2
    assert result["steps"] == 2


def test_local_nested_counter_rows_survive_background_inventory_limit(agent_page):
    background = "".join(f"<a href='/item-{index}'>Item {index}</a>" for index in range(175))
    agent_page.set_content(background + quantity_widget())
    tools = tools_for(agent_page)
    observation = tools.observe()
    assert observation["frames"][0]["controls_truncated"]
    assert len([control for control in controls(observation) if control.get("counter")]) == 2


def test_local_extra_visible_button_does_not_turn_an_ambiguous_row_into_counter(agent_page):
    markup = quantity_widget().replace(
        "</div></section>", "<button>Reset quantity</button></div></section>"
    )
    agent_page.set_content(markup)
    assert not detected(tools_for(agent_page))


def test_local_hidden_extra_button_does_not_hide_the_actual_counter(agent_page):
    markup = quantity_widget().replace(
        "</div></section>", "<button hidden>Reset quantity</button></div></section>"
    )
    agent_page.set_content(markup)
    assert len(detected(tools_for(agent_page))) == 2


@pytest.mark.parametrize("description", ["Ages 18 or above", "Ages <span>18</span> or above"])
def test_local_wrapper_quantity_is_distinct_from_age_metadata(agent_page, description):
    markup = quantity_widget().replace(
        "</span><div class=stepper>", f"</span><p>{description}</p><div class=stepper>"
    )
    agent_page.set_content(markup)
    found = detected(tools_for(agent_page))
    assert len(found) == 2 and all(control["counter"]["value"] == 2 for control in found)
    assert all("Adults" in control["counter"]["label"] for control in found)


@pytest.mark.parametrize("icon", ["symbol", "symbol-title"])
def test_local_same_document_svg_symbols_expose_direction(agent_page, icon):
    definitions = """<svg width=0 height=0 style='position:absolute'><defs>
      <symbol id=quantity-minus><rect x=4 y=11 width=16 height=2 /></symbol>
      <symbol id=quantity-plus>
        <path d='M4 11 H11 V4 H13 V11 H20 V13 H13 V20 H11 V13 H4 Z'/></symbol>
      <symbol id=quantity-glyph-a><title>Decrease quantity</title>
        <rect x=4 y=11 width=16 height=2 /></symbol>
      <symbol id=quantity-glyph-b><title>Increase quantity</title>
        <path d='M4 11 H11 V4 H13 V11 H20 V13 H13 V20 H11 V13 H4 Z'/></symbol>
      </defs></svg>"""
    agent_page.set_content(definitions + quantity_widget(icon=icon))
    tools = tools_for(agent_page)
    found = detected(tools)
    assert len(found) == 2
    assert {control["counter"]["direction"] for control in found} == {"increase", "decrease"}
    up = next(control for control in found if control["counter"]["direction"] == "increase")
    result = tools.execute(decision("set_counter", up["id"], "4"))
    assert result["status"] == "counter_verified" and result["observed"] == 4


@pytest.mark.parametrize(
    "label,before,target,direction,steps",
    [
        ("Adults", 2, 5, "increase", 3),
        ("Rooms", 1, 4, "increase", 3),
        ("Adults", 4, 1, "decrease", 3),
    ],
)
def test_local_targets_follow_requested_counts_not_a_fixed_demo_pair(
    agent_page, label, before, target, direction, steps
):
    agent_page.set_content(quantity_widget(label=label, count=before))
    tools = tools_for(agent_page)
    control = next(
        control for control in detected(tools) if control["counter"]["direction"] == direction
    )
    result = tools.execute(decision("set_counter", control["id"], str(target)))
    assert result["status"] == "counter_verified" and result["observed"] == target
    assert result["steps"] == steps


def test_local_unfamiliar_icons_expose_count_without_inventing_direction(agent_page):
    agent_page.set_content(quantity_widget(icon="unknown"))
    found = detected(tools_for(agent_page))
    assert len(found) == 2
    assert all(control["counter"]["direction"] == "unknown" for control in found)
    assert all(control["counter"]["value"] == 2 for control in found)


def test_local_explicitly_selected_unknown_stepper_continues_only_verified_effects(agent_page):
    agent_page.set_content(quantity_widget(icon="unknown"))
    tools = tools_for(agent_page)
    control = selected_step(agent_page, tools, "up")
    result = tools.execute(decision("set_counter", control["id"], "4"))
    assert result["status"] == "counter_verified" and result["observed"] == 4
    assert result["steps"] == 2 and agent_page.evaluate("window.counterClicks") == 2


def test_local_single_unknown_counter_click_reports_effect_not_assumed_direction(agent_page):
    agent_page.set_content(quantity_widget(icon="unknown"))
    tools = tools_for(agent_page)
    control = selected_step(agent_page, tools, "up")
    result = tools.execute(decision("click", control["id"]))
    assert result["status"] == "counter_step_observed"
    assert result["expected"] is None and result["observed"] == 3


def test_local_disabled_unknown_stepper_is_not_clicked(agent_page):
    agent_page.set_content(quantity_widget(icon="unknown"))
    agent_page.locator('[data-step="up"]').evaluate("e=>e.disabled=true")
    tools = tools_for(agent_page)
    control = selected_step(agent_page, tools, "up")
    with pytest.raises(WebsiteError, match="disabled"):
        tools.execute(decision("set_counter", control["id"], "4"))
    assert agent_page.evaluate("window.counterClicks") is None


@pytest.mark.parametrize("effect,expected_count", [("opposite", 1), ("none", 2)])
def test_local_unknown_stepper_stops_after_first_opposite_or_missing_effect(
    agent_page, effect, expected_count
):
    agent_page.set_content(quantity_widget(icon="unknown", effect=effect))
    tools = tools_for(agent_page)
    control = selected_step(agent_page, tools, "up")
    result = tools.execute(decision("set_counter", control["id"], "4"))
    assert result["status"] == "counter_unconfirmed" and result["observed"] == expected_count
    assert result["steps"] == 0 and agent_page.evaluate("window.counterClicks") == 1


def unknown_references():
    return {
        "0:row": (None, None, {"label": "Adults", "tag": "DIV"}),
        **{
            f"0:{side}": (
                None,
                None,
                {
                    "label": "Adults",
                    "tag": "BUTTON",
                    "enabled": True,
                    "counter": {
                        "label": "Adults",
                        "value": 2,
                        "direction": "unknown",
                        "evidence": "Adults 2",
                    },
                },
            )
            for side in ("first", "second")
        },
    }


@pytest.mark.parametrize("selected_id", ["0:first", "0:second"])
def test_unknown_direction_requires_an_explicit_fresh_selected_stepper(selected_id):
    resolved, field = resolve_counter_decision(
        decision("set_counter", selected_id, "3"),
        TaskLedger("Find hotels for 3 adults"),
        unknown_references(),
    )
    assert field == "adults" and resolved.control_id == selected_id and resolved.value == "3"


def test_unknown_direction_never_retargets_a_row_label_to_an_arbitrary_stepper():
    with pytest.raises(WebsiteError):
        resolve_counter_decision(
            decision("set_counter", "0:row", "3"),
            TaskLedger("Find hotels for 3 adults"),
            unknown_references(),
        )


def test_local_review_card_buttons_are_not_quantity_steppers(agent_page):
    agent_page.set_content("""<section>
      <button>Previous</button><div>
        <h3>Hotel Ashland Hills Hotel &amp; Suites</h3>
        <p>Ashland, United States</p><p>8.3 Very Good reviews <span>707</span></p>
      </div><button>Next</button></section>
      <section><button>Previous</button><div>
        <a href='/hotel'>Hotel South Beach</a><p>Miami Beach, United States</p>
        <p>8.9 Excellent 1,249 reviews <span>1</span></p>
      </div><button>Next</button></section>""")
    assert not detected(tools_for(agent_page))


def test_local_visible_aria_hidden_stepper_buttons_are_not_css_hidden(agent_page):
    agent_page.set_content(quantity_widget().replace("data-step=", "aria-hidden=true data-step="))
    tools = tools_for(agent_page)
    found = detected(tools)
    assert len(found) == 2
    up = next(control for control in found if control["counter"]["direction"] == "increase")
    assert tools.execute(decision("set_counter", up["id"], "3"))["observed"] == 3


@pytest.mark.parametrize("visibility", ["hidden", "style='visibility:hidden'", "inert"])
def test_local_nonrendered_or_inert_quantity_controls_stay_unavailable(agent_page, visibility):
    agent_page.set_content(f"<div {visibility}>" + quantity_widget() + "</div>")
    assert not detected(tools_for(agent_page))


def test_local_aria_hidden_nonquantity_button_is_not_exposed(agent_page):
    agent_page.set_content("<button aria-hidden=true>Internal control</button>")
    assert not controls(tools_for(agent_page).observe())


def semantic_spinbutton(*, count=2, behavior="normal", readonly=False):
    delta = "step" if behavior == "normal" else "-step" if behavior == "opposite" else "0"
    return f"""<div role=spinbutton aria-label=Adults aria-valuenow={count}
      aria-valuemin=1 aria-valuemax=6 aria-readonly={"true" if readonly else "false"}
      tabindex=0 onkeydown="if(['ArrowUp','ArrowDown'].includes(event.key)){{
        event.preventDefault();window.keySteps=(window.keySteps||0)+1;
        const step=event.key==='ArrowUp'?1:-1;
        this.setAttribute('aria-valuenow',String(Number(this.getAttribute('aria-valuenow'))+({delta})));
      }}">
      <span>Adults</span><button aria-hidden=true aria-label='Decrease adults'>-</button>
      <span>Visible quantity</span>
      <button aria-hidden=true aria-label='Increase adults'>+</button></div>"""


@pytest.mark.parametrize("before,target,steps", [(2, 3, 1), (2, 5, 3), (4, 1, 3)])
def test_local_semantic_spinbutton_keyboard_uses_requested_absolute_target(
    agent_page, before, target, steps
):
    agent_page.set_content(semantic_spinbutton(count=before))
    tools = tools_for(agent_page)
    found = detected(tools)
    spin = next(control for control in found if control["role"] == "spinbutton")
    assert spin["counter"]["direction"] == "both" and spin["counter"]["value"] == before
    assert len(found) == 3  # semantic field plus its two rendered actuators
    result = tools.execute(decision("set_counter", spin["id"], str(target)))
    assert result["status"] == "counter_verified" and result["observed"] == target
    assert result["input_method"] == "keyboard" and result["steps"] == steps


@pytest.mark.parametrize("behavior,expected", [("opposite", 1), ("none", 2)])
def test_local_spinbutton_keyboard_stops_after_wrong_or_missing_effect(
    agent_page, behavior, expected
):
    agent_page.set_content(semantic_spinbutton(behavior=behavior))
    tools = tools_for(agent_page)
    spin = next(control for control in detected(tools) if control["role"] == "spinbutton")
    result = tools.execute(decision("set_counter", spin["id"], "4"))
    assert result["status"] == "counter_unconfirmed" and result["observed"] == expected
    assert agent_page.evaluate("window.keySteps") == 1


@pytest.mark.parametrize("readonly,target", [(True, "3"), (False, "7")])
def test_local_spinbutton_does_not_override_readonly_or_observed_limits(
    agent_page, readonly, target
):
    agent_page.set_content(semantic_spinbutton(readonly=readonly))
    tools = tools_for(agent_page)
    spin = next(control for control in detected(tools) if control["role"] == "spinbutton")
    with pytest.raises(WebsiteError, match="read-only|observed limits"):
        tools.execute(decision("set_counter", spin["id"], target))
    assert agent_page.evaluate("window.keySteps") is None


def test_local_readonly_spinbutton_does_not_allow_its_child_actuator(agent_page):
    agent_page.set_content(semantic_spinbutton(readonly=True))
    tools = tools_for(agent_page)
    up = next(
        control for control in detected(tools) if control["counter"]["direction"] == "increase"
    )
    with pytest.raises(WebsiteError, match="read-only"):
        tools.execute(decision("set_counter", up["id"], "3"))


@pytest.mark.parametrize(
    "label,before,target", [("Adults", 2, 3), ("Rooms", 1, 3), ("Quantity", 4, 1)]
)
def test_local_native_number_control_uses_keyboard_readback(agent_page, label, before, target):
    agent_page.set_content(f"<label>{label}<input type=number min=0 max=6 value={before}></label>")
    tools = tools_for(agent_page)
    control = detected(tools)[0]
    assert control["counter"]["method"] == "number_input"
    result = tools.execute(decision("set_counter", control["id"], str(target)))
    assert result["observed"] == target and result["status"] == "counter_verified"


def test_local_readonly_display_does_not_hide_its_rendered_stepper_buttons(agent_page):
    agent_page.set_content("""<div><label for=count>Rooms</label>
      <button aria-hidden=true aria-label='Decrease rooms'
        onclick="count.value=String(Number(count.value)-1)">-</button>
      <input id=count type=number value=1 readonly>
      <button aria-hidden=true aria-label='Increase rooms'
        onclick="count.value=String(Number(count.value)+1)">+</button></div>""")
    tools = tools_for(agent_page)
    up = next(
        control for control in detected(tools) if control["counter"]["direction"] == "increase"
    )
    result = tools.execute(decision("set_counter", up["id"], "2"))
    assert result["status"] == "counter_verified" and result["observed"] == 2


def test_semantic_counter_resolution_preserves_selected_numeric_control():
    references = {
        "0:adults": (
            None,
            None,
            {
                "tag": "DIV",
                "role": "spinbutton",
                "label": "Adults",
                "counter": {"label": "Adults", "value": 2, "direction": "both"},
            },
        ),
    }
    resolved, field = resolve_counter_decision(
        decision("set_counter", "0:adults", "3"), TaskLedger("Find hotels for 3 adults"), references
    )
    assert field == "adults" and resolved.control_id == "0:adults"


def test_numeric_probe_does_not_displace_controls_from_model_observation():
    full = {
        "frames": [
            {
                "text": "",
                "controls": [
                    {
                        "id": "0:adults",
                        "role": "spinbutton",
                        "numeric_probe": {"child_buttons": 2, "aria_value": "2"},
                    }
                ],
            }
        ]
    }
    assert "numeric_probe" not in compact_observation(full)["frames"][0]["controls"][0]
    assert full["frames"][0]["controls"][0]["numeric_probe"]["child_buttons"] == 2


def test_counter_structure_diagnostics_exclude_labels_values_and_private_attributes():
    from test_browser_agent import FakeDecider, FakeTools

    class NumericTools(FakeTools):
        def observe(self):
            current = super().observe()
            facts = {
                "id": "0:adults",
                "tag": "DIV",
                "role": "spinbutton",
                "type": "",
                "label": "Adults",
                "numeric_probe": {
                    "aria_value": "private-value",
                    "child_buttons": 2,
                    "accessibility_hidden_buttons": 2,
                    "private": "private-value",
                },
            }
            self.references = {"0:adults": (None, None, facts)}
            current["frames"][0]["controls"] = [facts]
            return current

    report = BrowserAgent(
        NumericTools(),
        FakeDecider([decision("set_counter", "0:adults", "3"), decision("pause")]),
        "Find hotels for 3 adults",
    ).run()
    control = BrowserControl()
    saved = []
    control.on_agent_diagnostics = saved.append
    control.set_agent_report(report)
    diagnostic = saved[0]["counter_diagnostics"]
    assert diagnostic["role"] == "spinbutton" and diagnostic["child_buttons"] == 2
    assert diagnostic["has_numeric_aria_value"] is True
    assert "label" not in diagnostic and "private" not in repr(diagnostic)
