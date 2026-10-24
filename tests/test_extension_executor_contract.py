"""Packaged extension contracts and opt-in isolated DOM fixtures; no live sites."""

import json
from pathlib import Path

import pytest
from test_navigation_verification import local_page as shared_local_page


EXTENSION = Path(__file__).resolve().parents[1] / "extensions" / "page-capture"


def test_extension_permissions_are_selected_tab_and_loopback_scoped():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert set(manifest["host_permissions"]) == {
        "http://localhost:8120/*", "http://127.0.0.1:8120/*"
    }
    assert "activeTab" in manifest["permissions"]
    assert "optional_host_permissions" not in manifest
    assert not {"cookies", "debugger", "webRequest", "tabs"} & set(manifest["permissions"])
    assert manifest["background"]["service_worker"] == "worker.js"
    assert manifest["side_panel"]["default_path"] == "sidepanel.html"


def test_popup_capture_expiry_does_not_clear_agent_session_state():
    script = (EXTENSION / "popup.js").read_text(encoding="utf-8")
    assert "storage.session.clear" not in script
    assert "storage.session.remove(['capture', 'expires'])" in script
    assert "document.getElementById('web-form').dataset.busy === 'true'" in script
    assert "document.getElementById('web-create').disabled" not in script
    assert "Use this tab with agent" in (EXTENSION / "popup.html").read_text(encoding="utf-8")


def test_worker_has_same_origin_session_binding_and_durable_no_replay():
    script = (EXTENSION / "worker.js").read_text(encoding="utf-8")
    assert "X-Dashboard-Instance" in script
    assert "X-CSRF-Token" in script
    assert "session.csrf !== expected.csrf" in script
    assert "session.instance_id !== expected.instance_id" in script
    assert "session.username !== expected.username" in script
    assert "state.pending.ack ||" in script
    assert "error:'delivery_unknown'" in script
    assert "phase:'executing'" in script
    assert "phase:'ack_ready',ack" in script
    assert "sender.tab" in script
    assert "onMessageExternal" not in script
    assert "eval(" not in script
    assert "!FINISHED.has(state.run.state)" in script
    assert "DASHBOARD_ERRORS.has(state.error)" in script
    assert "response.status === 410 ? 'run_expired'" in script
    assert "response.status === 409 ? 'operation_conflict'" in script
    assert "dispatch('validate',{document_token:documentToken,url})" in script


@pytest.fixture
def executor_page(shared_local_page):
    page = shared_local_page
    page.set_content("<main><label>Destination <input name='destination'></label></main>")
    for filename in ("agent_observe.js", "capture_dom.js", "executor.js"):
        page.add_script_tag(path=str(EXTENSION / filename))
    return page


def observed(page):
    return page.evaluate("() => __agenticTabExecutor.dispatch('observe', {focus:'form'})")


def test_executor_fill_verifies_readback_and_rejects_changed_control(executor_page):
    page = executor_page
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    payload = {"document_token": observation["document_token"], "facts": field,
               "decision": {"action": "fill", "control_id": "0:" + field["id"], "value": "Boston"}}
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", payload)
    assert result == {"status": "value_verified", "expected": "Boston", "observed": "Boston"}
    # The old observation is no longer a valid value/identity snapshot.
    with pytest.raises(Exception, match="control_changed"):
        page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", payload)


def test_executor_editable_click_focuses_field_to_open_its_choices(executor_page):
    page = executor_page
    page.set_content("""<main><label>Destination <input name='destination'
      onfocus='document.querySelector("[role=listbox]").hidden=false'></label>
      <div role='listbox' hidden><div role='option'>Boston</div></div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "click", "control_id": field["id"], "value": ""},
    })
    assert result["status"] == "action_performed"
    assert page.locator("input").evaluate("e => document.activeElement === e")
    assert page.get_by_role("listbox").is_visible()


def date_payload(page, observation, role="gridcell"):
    field = next(c for c in observation["frame"]["controls"]
                 if c["role"] == role and "November 28, 2026" in c["label"])
    return {"document_token": observation["document_token"], "facts": field,
            "decision": {"action": "click", "control_id": field["id"], "value": ""}}


def test_executor_calendar_wrapper_resolves_one_same_day_inner_action(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <button onclick='window.clicks=(window.clicks||0)+1;window.trusted=event.isTrusted;
        this.parentElement.setAttribute("aria-selected","true")'>28</button>
      </div></div></main>""")
    observation = observed(page)
    payload = date_payload(page, observation)
    assert payload["facts"]["date_owner_id"] == payload["facts"]["id"]
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", payload)
    assert result["status"] == "action_performed"
    assert result["calendar"] == {"date": "2026-11-28", "status": "selected",
                                  "target": "inner_action", "dispatched": True}
    assert page.evaluate("window.clicks") == 1
    assert page.evaluate("window.trusted") is False


def test_executor_calendar_already_selected_is_idempotent(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026'>
      <input type='checkbox' value='28' checked onclick='window.clicks=(window.clicks||0)+1'>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "already_selected"
    assert result["calendar"]["dispatched"] is False
    assert page.evaluate("window.clicks||0") == 0


def test_executor_calendar_does_not_skip_a_previously_selected_range_interior(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='true'>
      <button onclick='window.clicks=(window.clicks||0)+1;
        this.parentElement.setAttribute("aria-label","Saturday, November 28, 2026, Check-in date")'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "selected"
    assert result["calendar"]["dispatched"] is True
    assert page.evaluate("window.clicks") == 1


def test_executor_calendar_keeps_selection_readback_when_checkout_closes_popup(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <button onclick='this.parentElement.setAttribute("aria-selected","true");
        this.closest("[role=grid]").hidden=true'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "selected"
    assert result["calendar"]["dispatched"] is True
    assert not page.get_by_role("grid", include_hidden=True).is_visible()


def test_executor_calendar_reads_unique_replacement_day_only_in_observed_grid(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <button onclick='const replacement=this.parentElement.cloneNode(true);
        replacement.setAttribute("aria-selected","true");
        this.parentElement.replaceWith(replacement)'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "selected"


def test_executor_calendar_resolves_full_date_accessible_labelledby(executor_page):
    page = executor_page
    page.set_content("""<main><span id='full-day'>Saturday, November 28, 2026</span>
      <div role='grid'><div role='gridcell' aria-labelledby='full-day' aria-selected='false'>
      <button onclick='this.parentElement.setAttribute("aria-selected","true")'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "selected"


@pytest.mark.parametrize("label", ["Sat, Nov 28, 2026", "Sat, Nov. 28, 2026"])
def test_executor_abbreviated_full_date_without_grid_does_not_bypass_readback(executor_page, label):
    page = executor_page
    page.set_content("<main><button aria-label='" + label
                     + "' onclick='window.clicks=(window.clicks||0)+1'>28</button></main>")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["tag"] == "BUTTON")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "click", "control_id": field["id"], "value": ""},
    })
    assert result["status"] == "value_mismatch"
    assert result["calendar"]["date"] == "2026-11-28"
    assert result["calendar"]["status"] == "unconfirmed"
    assert page.evaluate("window.clicks") == 1


def test_executor_unparsed_full_calendar_date_does_not_fall_through_to_generic_click(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='28 novembre 2026' onclick='window.clicks=(window.clicks||0)+1'>28</div>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["role"] == "gridcell")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "click", "control_id": field["id"], "value": ""},
    })
    assert result["status"] == "value_mismatch"
    assert result["calendar"]["status"] == "unconfirmed"
    assert result["calendar"]["dispatched"] is False
    assert page.evaluate("window.clicks||0") == 0


def test_executor_unrelated_checkbox_keeps_generic_click_behavior(executor_page):
    page = executor_page
    page.set_content("<main><label>Free breakfast<input type='checkbox'></label></main>")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["type"] == "checkbox")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "click", "control_id": field["id"], "value": ""},
    })
    assert result["status"] == "action_performed"
    assert "calendar" not in result
    assert page.get_by_role("checkbox").is_checked()


def test_executor_calendar_waits_for_delayed_selection_without_reclick(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <button onclick='window.clicks=(window.clicks||0)+1;
        setTimeout(()=>this.parentElement.setAttribute("aria-selected","true"),250)'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["status"] == "selected"
    assert page.evaluate("window.clicks") == 1


def test_executor_calendar_no_change_is_not_reported_as_selected(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <button onclick='window.clicks=(window.clicks||0)+1'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["status"] == "value_mismatch"
    assert result["expected"] == "2026-11-28"
    assert result["observed"] is None
    assert result["calendar"]["status"] == "unconfirmed"
    assert page.evaluate("window.clicks") == 1


def test_executor_old_hidden_selection_is_not_new_date_evidence(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'>
      <span hidden aria-label='Saturday, November 28, 2026' aria-selected='true'>28</span>
      <button onclick='window.clicks=(window.clicks||0)+1'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["status"] == "value_mismatch"
    assert result["calendar"]["status"] == "unconfirmed"
    assert page.evaluate("window.clicks") == 1


@pytest.mark.parametrize("inner", [
    "<button>28</button><button>28</button>",
    "<button aria-label='Sunday, November 29, 2026'>28</button>",
])
def test_executor_calendar_rejects_ambiguous_or_conflicting_inner_actions(executor_page, inner):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' onclick='window.clicks=(window.clicks||0)+1'>"""
                     + inner + "</div></div></main>")
    payload = date_payload(page, observed(page))
    with pytest.raises(Exception, match="control_changed"):
        page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", payload)
    assert page.evaluate("window.clicks||0") == 0


def test_executor_calendar_does_not_infer_a_day_in_another_widget(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' aria-selected='false'
      onclick='window.outerClicks=(window.outerClicks||0)+1'>28</div></div>
      <div role='grid'><div role='gridcell' aria-label='Saturday, November 28, 2026'>
      <button onclick='window.otherClicks=(window.otherClicks||0)+1'>28</button>
      </div></div></main>""")
    result = page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)",
                           date_payload(page, observed(page)))
    assert result["calendar"]["target"] == "observed_control"
    assert result["calendar"]["status"] == "unconfirmed"
    assert page.evaluate("window.outerClicks") == 1
    assert page.evaluate("window.otherClicks||0") == 0


def test_executor_calendar_rejects_stale_accessible_date_before_dispatch(executor_page):
    page = executor_page
    page.set_content("""<main><div role='grid'><div role='gridcell'
      aria-label='Saturday, November 28, 2026' onclick='window.clicks=(window.clicks||0)+1'>28</div>
      </div></main>""")
    payload = date_payload(page, observed(page))
    page.get_by_role("gridcell").evaluate("e=>e.setAttribute('aria-label','Sunday, November 29, 2026')")
    with pytest.raises(Exception, match="control_changed"):
        page.evaluate("p=>__agenticTabExecutor.dispatch('execute',p)", payload)
    assert page.evaluate("window.clicks||0") == 0


def test_executor_fill_notifies_owner_outside_open_shadow_root(executor_page):
    page = executor_page
    page.set_content("<main><div id='search-widget'></div></main>")
    page.evaluate("""() => {
      const root = document.getElementById('search-widget').attachShadow({mode:'open'});
      root.innerHTML = '<label>Destination <input name="destination"></label>';
      document.body.addEventListener('input', event => {
        window.inputEvidence = {composed:event.composed, trusted:event.isTrusted,
          inputType:event.inputType, data:event.data};
      });
    }""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "fill", "control_id": field["id"], "value": "Boston"},
    })
    assert result["status"] == "value_verified"
    assert page.evaluate("window.inputEvidence") == {
        "composed": True, "trusted": False,
        "inputType": "insertReplacementText", "data": "Boston",
    }


@pytest.mark.parametrize("event_name", ["focus", "input"])
def test_executor_does_not_verify_a_detached_field(executor_page, event_name):
    page = executor_page
    page.evaluate("""eventName => {
      const field = document.querySelector('input');
      field.addEventListener(eventName, () => {
        const replacement = document.createElement('input');
        replacement.name = 'destination';
        field.replaceWith(replacement);
      }, {once:true});
    }""", event_name)
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    with pytest.raises(Exception, match="control_changed"):
        page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
            "document_token": observation["document_token"], "facts": field,
            "decision": {"action": "fill", "control_id": field["id"], "value": "Boston"},
        })
    assert page.locator("input").input_value() == ""


def test_executor_rejects_old_document_token_before_action(executor_page):
    page = executor_page
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    with pytest.raises(Exception, match="stale_document"):
        page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
            "document_token": "not-this-document", "facts": field,
            "decision": {"action": "fill", "control_id": field["id"], "value": "Boston"},
        })
    assert page.locator("input").input_value() == ""


def test_executor_rejects_same_document_url_change_before_action(executor_page):
    page = executor_page
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"] if c["name"] == "destination")
    page.evaluate("() => history.pushState({}, '', '/another-page')")
    with pytest.raises(Exception, match="stale_document"):
        page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
            "document_token": observation["document_token"], "facts": field,
            "decision": {"action": "fill", "control_id": field["id"], "value": "Boston"},
        })
    assert page.locator("input").input_value() == ""


def test_executor_link_returns_navigation_intent_without_destroying_context(executor_page):
    page = executor_page
    starting = page.url
    page.set_content('<main><a href="/world">World news</a></main>')
    observation = observed(page)
    link = next(c for c in observation["frame"]["controls"] if c["tag"] == "A")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": link,
        "decision": {"action": "click", "control_id": link["id"], "value": ""},
    })
    assert result["status"] == "action_performed"
    assert result["_navigation_url"].endswith("/world")
    assert result["_navigation_from_url"] == starting
    assert page.url == starting
    assert page.evaluate("payload => __agenticTabExecutor.dispatch('validate', payload)", {
        "document_token": observation["document_token"], "url": starting,
    }) == {"valid": True}


def test_executor_counter_handles_requested_target_with_each_step_readback(executor_page):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults' onclick='document.querySelector("output").textContent--'>-</button>
      <output>2</output>
      <button aria-label='Increase Adults' onclick='document.querySelector("output").textContent++'>+</button>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "5"},
    })
    assert result["status"] == "counter_verified"
    assert result["expected"] == result["observed"] == 5
    assert result["steps"] == 3
    assert page.locator("output").inner_text() == "5"


@pytest.mark.parametrize("native", [False, True])
def test_executor_counter_preflight_ignores_transport_object_key_order(executor_page, native):
    page = executor_page
    page.set_content(
        "<main><label>Adults <input type='number' value='2' min='1' max='8'></label></main>"
        if native else """<main><div>Adults
          <button aria-label='Decrease Adults'>-</button><output>2</output>
          <button aria-label='Increase Adults'
            onclick='window.clicks=(window.clicks||0)+1;document.querySelector("output").textContent++'>+</button>
          </div></main>"""
    )
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == ("both" if native else "increase"))
    # Model the extension's structured-object transport rather than preserving
    # the live JavaScript object's insertion order by accident in this fixture.
    field["counter"] = dict(sorted(field["counter"].items()))
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "3"},
    })
    assert result["status"] == "counter_verified"
    assert result["observed"] == 3 and result["steps"] == 1
    if not native:
        assert page.evaluate("window.clicks") == 1


@pytest.mark.parametrize("changed", [
    {"value": 3}, {"label": "Rooms"}, {"direction": "decrease"},
    {"method": "number_input"}, {"extra": True},
])
def test_executor_counter_preflight_still_rejects_changed_facts(executor_page, changed):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults'>-</button><output>2</output>
      <button aria-label='Increase Adults' onclick='window.clicks=(window.clicks||0)+1'>+</button>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    field["counter"].update(changed)
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "4"},
    })
    assert result["status"] == "counter_unconfirmed" and result["dispatched"] is False
    assert result["counter_preflight"]["reason"] == "counter_changed"
    assert set(result["counter_preflight"]["mismatched_fields"]) <= {
        "label", "value", "direction", "method", "minimum", "maximum", "owner_readonly", "evidence", "keys"
    }
    assert page.evaluate("window.clicks||0") == 0
    assert page.locator("output").inner_text() == "2"


def test_executor_counter_preflight_rejects_live_count_change_before_any_click(executor_page):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults'>-</button><output>2</output>
      <button aria-label='Increase Adults' onclick='window.clicks=(window.clicks||0)+1'>+</button>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    page.locator("output").evaluate("e => e.textContent='3'")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "4"},
    })
    assert result["status"] == "counter_unconfirmed" and result["dispatched"] is False
    assert result["counter_preflight"]["reason"] == "counter_changed"
    assert "value" in result["counter_preflight"]["mismatched_fields"]
    assert page.evaluate("window.clicks||0") == 0


def test_executor_counter_focuses_verified_button_before_click(executor_page):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults'>-</button><output>2</output>
      <button aria-label='Increase Adults' onclick='window.clicks=(window.clicks||0)+1;
        if(document.activeElement===this) document.querySelector("output").textContent++'>+</button>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "3"},
    })
    assert result["status"] == "counter_verified" and result["observed"] == 3
    assert page.evaluate("window.clicks") == 1


@pytest.mark.parametrize("focus_change,reason", [
    ("replace", "focus_changed"),
    ("quantity", "counter_changed"),
    ("hide", "not_actionable"),
])
def test_executor_counter_rechecks_focus_time_changes_without_click(executor_page, focus_change, reason):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults'>-</button><output>2</output>
      <button aria-label='Increase Adults' onclick='window.clicks=(window.clicks||0)+1'>+</button>
      </div></main>""")
    page.get_by_role("button", name="Increase Adults").evaluate(
        """(e,change)=>e.addEventListener('focus',()=>{
          if(change==='replace') e.replaceWith(e.cloneNode(true));
          if(change==='quantity') document.querySelector('output').textContent='3';
          if(change==='hide') e.parentElement.hidden=true;
        },{once:true})""", focus_change,
    )
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    result = page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
        "document_token": observation["document_token"], "facts": field,
        "decision": {"action": "set_counter", "control_id": field["id"], "value": "4"},
    })
    assert result["status"] == "counter_unconfirmed" and result["dispatched"] is False
    assert result["steps"] == 0
    assert result["counter_preflight"]["reason"] == reason
    assert page.evaluate("window.clicks||0") == 0


def test_executor_counter_preflight_does_not_mask_forbidden_control(executor_page):
    page = executor_page
    page.set_content("""<main><div>Adults
      <button aria-label='Decrease Adults'>-</button><output>2</output>
      <button aria-label='Increase Adults subscribe' onclick='window.clicks=(window.clicks||0)+1'>+</button>
      </div></main>""")
    observation = observed(page)
    field = next(c for c in observation["frame"]["controls"]
                 if (c.get("counter") or {}).get("direction") == "increase")
    with pytest.raises(Exception, match="unsupported"):
        page.evaluate("payload => __agenticTabExecutor.dispatch('execute', payload)", {
            "document_token": observation["document_token"], "facts": field,
            "decision": {"action": "set_counter", "control_id": field["id"], "value": "3"},
        })
    assert page.evaluate("window.clicks||0") == 0


def test_executor_observation_includes_only_safe_tab_state(executor_page):
    observation = observed(executor_page)
    assert set(observation["tab_state"]) == {"visibility", "has_focus"}
    assert observation["tab_state"]["visibility"] in {"visible", "hidden"}
    assert isinstance(observation["tab_state"]["has_focus"], bool)


def test_executor_tripadvisor_restriction_returns_manual_pause_without_controls(executor_page):
    page = executor_page
    page.set_content("<main><h1>Access is temporarily restricted</h1><p>We detected unusual activity from your device or network.</p></main>")
    observation = observed(page)
    assert observation["frame"]["manual_verification_required"] is True
    assert observation["frame"]["access_restriction"] is True
    assert observation["frame"]["controls"] == []


def test_executor_newsletter_is_not_a_signin_challenge(executor_page):
    page = executor_page
    page.set_content("<main><h1>Hotel results</h1><form>Subscribe to our newsletter<input type='email'></form></main>")
    assert not observed(page)["frame"].get("manual_verification_required")


def test_executor_screenshots_are_explicitly_unsupported(executor_page):
    with pytest.raises(Exception, match="unsupported"):
        executor_page.evaluate("() => __agenticTabExecutor.dispatch('viewport_image', {})")
