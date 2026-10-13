"""Unit and opt-in local DOM fixtures; no live website or model API calls."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_browser_agent import agent_page as shared_page
from test_browser_agent import decision, tools_for

from agentic_web_demo.browser_task import TaskLedger


@pytest.fixture
def agent_page(request):
    yield from shared_page.__wrapped__(request)


def observation(*, combo=True, opened=True, value="New York", document="search"):
    field = {
        "id": "0:input",
        "tag": "INPUT",
        "type": "text",
        "name": "destination",
        "label": "Destination",
        "value": value,
        "selection_required": combo,
        "expanded": "true" if opened and combo else "false",
        "option_ids": ["0:city", "0:ai"] if opened and combo else [],
    }
    options = (
        [
            {
                "id": "0:city",
                "tag": "LI",
                "role": "option",
                "option_primary": "New York",
                "label": "New York New York, United States of America",
                "text": "New York New York, United States of America",
            },
            {
                "id": "0:ai",
                "tag": "BUTTON",
                "role": "option",
                "option_primary": "New York",
                "label": "New York Search with AI",
                "text": "New York Search with AI",
            },
        ]
        if opened and combo
        else []
    )
    return {
        "url": "https://example.org/" + document,
        "document_id": document,
        "frames": [{"text": "Hotel search", "controls": [field, *options]}],
    }


def requirement(name="destination", control_id=None, expected="New York", quote=None):
    return SimpleNamespace(
        model_dump=lambda: {
            "name": name,
            "expected": expected,
            "application": "form",
            "request_quote": expected if quote is None else quote,
            "control_id": control_id,
        }
    )


def task(fresh, *, bound=False, name="destination", expected="New York"):
    ledger = TaskLedger(expected)
    ledger.declare([requirement(name, "0:input" if bound else None, expected)], fresh)
    ledger.observe(fresh)
    return ledger


def act(ledger, fresh, control_id="0:city", action="click", status="action_performed"):
    facts = next(c for c in fresh["frames"][0]["controls"] if c["id"] == control_id)
    ledger.remember_action(facts, {"status": status}, SimpleNamespace(action=action), fresh)


def check(ledger, fresh):
    return ledger.observe(fresh)["requirements"][0]


@pytest.mark.parametrize("bound", [False, True])
def test_plain_destination_textbox_still_uses_value_readback(bound):
    fresh = observation(combo=False)
    ledger = task(fresh, bound=bound)
    assert check(ledger, fresh)["status"] == "verified"
    assert not ledger.pending()


@pytest.mark.parametrize("bound", [False, True])
def test_native_select_verifies_selected_option_label(bound):
    fresh = observation(combo=False)
    fresh["frames"][0]["controls"][0].update(
        tag="SELECT",
        type="select-one",
        value="nyc",
        options=[{"value": "nyc", "label": "New York", "disabled": False}],
    )
    ledger = task(fresh, bound=bound)
    assert check(ledger, fresh)["status"] == "verified"


@pytest.mark.parametrize("bound", [False, True])
def test_typed_autocomplete_value_does_not_complete_destination(bound):
    fresh = observation()
    ledger = task(fresh, bound=bound)
    result = check(ledger, fresh)
    assert ledger.pending() == ["destination"]
    assert result["selection_pending"] is True
    assert result["next_action"] == "select_option"
    assert [option["control_id"] for option in result["selection_options"]] == ["0:city", "0:ai"]


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("value", ["", "Boston"])
@pytest.mark.parametrize("opened", [False, True])
def test_unentered_or_wrong_destination_requests_a_fill_not_a_committed_choice(
    bound, value, opened
):
    fresh = observation(value=value, opened=opened)
    ledger = task(fresh, bound=bound)
    result = check(ledger, fresh)
    assert result["observed"] == value
    assert result["status"] == ("pending" if not value else "mismatch")
    assert result["method"] == "destination_fill_pending"
    assert result["next_action"] == "fill"
    assert result["selection_options"] == []
    assert "Typed text" not in result["evidence"]
    assert "empty" in result["evidence"] if not value else "does not match" in result["evidence"]
    assert ledger.pending() == ["destination"]


@pytest.mark.parametrize("value", ["", "Boston"])
def test_plain_destination_value_also_exposes_a_fill_when_unentered_or_wrong(value):
    fresh = observation(combo=False, value=value)
    result = check(task(fresh), fresh)
    assert result["observed"] == value
    assert result["next_action"] == "fill"
    assert result["status"] != "verified"


@pytest.mark.parametrize(
    "opened,next_action", [(False, "open_suggestions"), (True, "wait_suggestions")]
)
def test_matching_uncommitted_text_without_owned_options_has_the_correct_next_phase(
    opened, next_action
):
    fresh = observation(opened=opened)
    fresh["frames"][0]["controls"] = fresh["frames"][0]["controls"][:1]
    fresh["frames"][0]["controls"][0]["option_ids"] = []
    result = check(task(fresh), fresh)
    assert result["status"] == "pending"
    assert result["observed"] == "New York"
    assert result["next_action"] == next_action
    assert result["selection_options"] == []
    assert "Matching text is entered" in result["evidence"]


def test_pending_async_suggestions_do_not_offer_stale_rows_for_selection():
    fresh = observation()
    fresh["frames"][0]["controls"][0]["suggestions_pending"] = True
    result = check(task(fresh), fresh)
    assert result["status"] == "pending"
    assert result["next_action"] == "wait_suggestions"
    assert result["selection_options"] == []


def test_successful_option_click_waits_for_its_readback_instead_of_repeating_the_row():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    delayed = check(ledger, fresh)
    assert delayed["status"] == "pending"
    assert delayed["next_action"] == "wait_suggestions"
    assert delayed["selection_options"] == []
    closed = observation(opened=False, value="New York, New York, United States of America")
    assert check(ledger, closed)["status"] == "verified"


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("missing", [False, True])
def test_missing_value_metadata_is_unknown_not_an_empty_destination(bound, missing):
    fresh = observation(value=None)
    if missing:
        fresh["frames"][0]["controls"][0].pop("value")
    result = check(task(fresh, bound=bound), fresh)
    assert result["observed"] is None
    assert result["status"] == "pending"
    assert result["method"] == "destination_value_unavailable"
    assert "next_action" not in result
    assert "unavailable" in result["evidence"]


def test_absent_bound_destination_is_unknown_not_an_empty_input_to_fill():
    fresh = observation()
    ledger = task(fresh, bound=True)
    fresh["frames"][0]["controls"] = []
    result = check(ledger, fresh)
    assert result["observed"] is None
    assert result["status"] == "pending"
    assert "next_action" not in result
    assert "absent or ambiguous" in result["evidence"]


def test_ambiguous_destination_fields_are_not_classified_as_a_unique_empty_field():
    fresh = observation(value="")
    second = deepcopy(fresh["frames"][0]["controls"][0])
    second.update(id="0:second", name="city")
    fresh["frames"][0]["controls"].append(second)
    result = check(task(fresh), fresh)
    assert result["status"] == "pending"
    assert result["observed"] is None
    assert "next_action" not in result
    assert "Multiple destination fields" in result["evidence"]


@pytest.mark.parametrize(
    "readonly,enabled,next_action", [(True, True, "open_suggestions"), (False, False, "inspect")]
)
def test_uneditable_empty_destination_does_not_propose_filling(readonly, enabled, next_action):
    fresh = observation(value="")
    fresh["frames"][0]["controls"][0].update(readonly=readonly, enabled=enabled)
    result = check(task(fresh), fresh)
    assert result["observed"] == ""
    assert result["next_action"] == next_action
    assert result["status"] == "pending"


def test_empty_native_destination_select_still_requires_native_selection_not_fill():
    fresh = observation(combo=False, value="")
    fresh["frames"][0]["controls"][0].update(tag="SELECT", type="select-one", options=[])
    result = check(task(fresh), fresh)
    assert result["observed"] == ""
    assert result["next_action"] == "select"
    assert result["status"] == "pending"


@pytest.mark.parametrize("bound", [False, True])
def test_associated_city_click_then_closed_field_readback_confirms_selection(bound):
    fresh = observation()
    ledger = task(fresh, bound=bound)
    act(ledger, fresh)
    closed = observation(opened=False)
    closed["frames"][0]["controls"][0]["id"] = "0:fresh-input"
    result = check(ledger, closed)
    assert result["status"] == "verified"
    assert result["method"] == "autocomplete_selection_readback"
    assert not ledger.pending()


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize(
    "readback",
    [
        "New York, New York, United States of America",
        "NEW YORK — New York; United States of America",
        "New York\nNew York,  United States of America",
    ],
)
def test_clicked_option_full_canonical_label_keeps_destination_verified(bound, readback):
    fresh = observation()
    ledger = task(fresh, bound=bound)
    act(ledger, fresh)
    closed = observation(opened=False, value=readback)
    result = check(ledger, closed)
    assert result["status"] == "verified"
    assert result["method"] == "autocomplete_selection_readback"
    assert result["observed"] == readback
    assert ledger.requirements["destination"]["expected"] == "New York"
    assert not ledger.pending()
    # A later ordinary observation must not lose the successful option proof.
    assert check(ledger, deepcopy(closed))["status"] == "verified"


@pytest.mark.parametrize(
    "readback",
    [
        "New York, United States of America",  # A qualifier was omitted.
        "New York, New Jersey, United States of America",
        "New York, New York, United States of America, Airport",
        "New York, United States of America, New York",  # Reordered words.
        "New York Central Park, New York, United States of America",
    ],
)
def test_canonical_readback_must_match_the_clicked_option_complete_words(readback):
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False, value=readback))["status"] == "mismatch"
    # Restoring a superficially correct label cannot resurrect invalidated proof.
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_canonical_readback_without_a_successful_scoped_option_click_is_not_verified():
    ledger = task(observation())
    result = check(
        ledger,
        observation(opened=False, value="New York, New York, United States of America"),
    )
    assert result["status"] == "mismatch"
    assert result["selection_pending"]


def test_canonical_option_proof_keeps_a_copy_of_the_actually_clicked_text():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    fresh["frames"][0]["controls"][1]["text"] = "New York, Boston, United States of America"
    assert (
        check(
            ledger, observation(opened=False, value="New York, Boston, United States of America")
        )["status"]
        == "mismatch"
    )


@pytest.mark.parametrize("invalidation", ["fill", "reopen", "document"])
def test_canonical_option_proof_does_not_survive_retyping_reopening_or_new_document(invalidation):
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    closed = observation(opened=False, value="New York, New York, United States of America")
    assert check(ledger, closed)["status"] == "verified"
    if invalidation == "fill":
        act(ledger, closed, "0:input", action="fill", status="value_verified")
    elif invalidation == "reopen":
        assert (
            check(ledger, observation(value=closed["frames"][0]["controls"][0]["value"]))["status"]
            == "pending"
        )
    else:
        closed["document_id"] = "changed"
    assert check(ledger, closed)["status"] != "verified"


def test_popup_dismissal_without_option_click_is_not_selection_proof():
    ledger = task(observation())
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_ineffective_option_click_cannot_be_confirmed_by_unrelated_popup_dismissal():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, fresh)["status"] == "pending"
    ledger.remember_action(
        {"id": "0:calendar", "tag": "BUTTON", "label": "Select dates"},
        {"status": "action_performed"},
        SimpleNamespace(action="click"),
        fresh,
    )
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_uncertain_unrelated_click_invalidates_candidate_before_browser_attempt():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, fresh)["status"] == "pending"
    ledger.before_action(
        {"id": "0:calendar", "tag": "BUTTON", "label": "Select dates"},
        SimpleNamespace(action="click"),
        fresh,
    )
    # Simulate a click that dismissed the popup but timed out: no successful
    # remember_action callback. The pre-action invalidation must be sufficient.
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_delayed_selection_can_confirm_after_readonly_wait():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, fresh)["status"] == "pending"
    ledger.remember_action({}, {"status": "waited"}, SimpleNamespace(action="wait"), fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"


def test_same_value_retyping_invalidates_selection_and_keeps_requirement_sticky():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    closed = observation(opened=False)
    assert check(ledger, closed)["status"] == "verified"
    act(ledger, closed, "0:input", action="fill", status="value_verified")
    # A rerender may temporarily omit the metadata; it cannot erase the requirement.
    closed["frames"][0]["controls"][0]["selection_required"] = False
    assert check(ledger, closed)["status"] == "pending"


def test_uncertain_same_value_fill_invalidates_selection_before_browser_attempt():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    closed = observation(opened=False)
    assert check(ledger, closed)["status"] == "verified"
    ledger.before_action(closed["frames"][0]["controls"][0], SimpleNamespace(action="fill"), closed)
    # A fill can replace the same value before Playwright reports a timeout.
    assert check(ledger, closed)["status"] == "pending"


def test_readback_change_invalidates_previously_confirmed_selection():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"
    assert check(ledger, observation(opened=False, value="Boston"))["status"] == "mismatch"
    assert check(ledger, observation(opened=False))["status"] == "pending"


@pytest.mark.parametrize(
    "primary,text",
    [
        ("LaGuardia Airport", "LaGuardia Airport New York, United States"),
        ("New York", "New York Search with AI"),
        ("New York", "New York Airport, United States"),
        ("New York Central Park", "New York Central Park New York, United States"),
        ("New York-New York", "New York-New York Las Vegas, United States"),
    ],
)
def test_wrong_primary_or_ai_or_airport_variant_does_not_confirm_destination(primary, text):
    fresh = observation()
    fresh["frames"][0]["controls"][1].update(option_primary=primary, label=text, text=text)
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_explicit_requested_airport_can_be_selected_without_city_variant_rejection():
    fresh = observation(value="LaGuardia Airport")
    fresh["frames"][0]["controls"][1].update(
        option_primary="LaGuardia Airport",
        label="LaGuardia Airport New York",
        text="LaGuardia Airport New York",
    )
    ledger = task(fresh, expected="LaGuardia Airport")
    act(ledger, fresh)
    assert (
        check(ledger, observation(opened=False, value="LaGuardia Airport"))["status"] == "verified"
    )


@pytest.mark.parametrize("purpose", ["set_field", "submit_search"])
def test_associated_option_native_submit_button_is_selection_not_search(purpose):
    fresh = observation()
    city = fresh["frames"][0]["controls"][1]
    city.update(tag="BUTTON", role="button", type="submit", submits_form=True)
    ledger = task(fresh)
    click = SimpleNamespace(action="click", purpose=purpose, value="")
    assert not ledger.is_submit(click, city)
    ai = fresh["frames"][0]["controls"][2]
    assert ledger.is_submit(click, ai)
    assert ledger.is_submit(
        click,
        {
            "id": "0:submit",
            "tag": "BUTTON",
            "type": "submit",
            "label": "Search",
            "submits_form": True,
        },
    )
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"


def test_unassociated_option_with_same_primary_does_not_confirm_destination():
    fresh = observation()
    unrelated = deepcopy(fresh["frames"][0]["controls"][1])
    unrelated["id"] = "0:unrelated"
    fresh["frames"][0]["controls"].append(unrelated)
    ledger = task(fresh)
    act(ledger, fresh, "0:unrelated")
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_cross_frame_option_is_never_accepted_as_same_field_selection():
    fresh = observation()
    fresh["frames"][0]["controls"][0]["option_ids"] = ["1:city"]
    fresh["frames"][0]["controls"][1]["id"] = "1:city"
    ledger = task(fresh)
    assert not check(ledger, fresh)["selection_options"]
    act(ledger, fresh, "1:city")
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_binding_to_option_cannot_bypass_destination_input_verification():
    fresh = observation()
    fresh["frames"][0]["controls"][1]["value"] = "New York"
    ledger = TaskLedger("New York")
    ledger.declare([requirement(control_id="0:city")], fresh)
    result = check(ledger, fresh)
    assert result["status"] == "pending"
    assert "input, not a suggestion" in result["evidence"]


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("target", ["0:city", "0:calendar", "0:missing"])
def test_known_destination_ignores_optional_nonvalue_binding_without_losing_choice(bound, target):
    fresh = observation()
    fresh["frames"][0]["controls"].append(
        {"id": "0:calendar", "tag": "BUTTON", "label": "Select dates"}
    )
    ledger = task(fresh, bound=bound)
    original_requirements = deepcopy(ledger.requirements)
    original_bindings = deepcopy(ledger.bindings)
    ledger.declare([requirement(control_id=target, quote="")], fresh)
    assert ledger.requirements == original_requirements
    assert ledger.bindings == original_bindings
    act(ledger, fresh)
    closed = observation(opened=False, value="New York, New York, United States of America")
    assert check(ledger, closed)["status"] == "verified"
    assert not ledger.pending()


def test_known_destination_binding_to_fresh_native_value_field_still_works():
    fresh = observation()
    ledger = task(fresh)
    assert not ledger.bindings
    ledger.declare([requirement(control_id="0:input", quote="")], fresh)
    assert ledger.bindings["destination"]["identity"]["name"] == "destination"
    act(ledger, fresh)
    assert (
        check(
            ledger, observation(opened=False, value="New York, New York, United States of America")
        )["status"]
        == "verified"
    )


def test_document_change_requires_fresh_selection_proof():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"
    assert check(ledger, observation(opened=False, document="other"))["status"] == "pending"


def test_reopened_suggestions_require_committed_choice_before_search():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"
    assert check(ledger, fresh)["status"] == "pending"


def test_option_click_without_successful_browser_outcome_is_not_selection_proof():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh, status="outcome_unknown")
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_option_click_accepts_case_normalized_field_readback():
    fresh = observation(value="NEW YORK")
    ledger = task(fresh)
    act(ledger, fresh)
    assert check(ledger, observation(opened=False))["status"] == "verified"


def test_autocomplete_enter_is_not_search_and_does_not_assert_selection():
    fresh = observation()
    ledger = task(fresh)
    field = fresh["frames"][0]["controls"][0]
    enter = SimpleNamespace(action="press", value="Enter", purpose="set_field")
    assert not ledger.is_submit(enter, field)
    ledger.remember_action(field, {"status": "action_performed"}, enter, fresh)
    assert check(ledger, observation(opened=False))["status"] == "pending"


def test_result_document_can_retain_verified_pre_submit_destination_evidence():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    closed = observation(opened=False)
    assert check(ledger, closed)["status"] == "verified"
    results = observation(opened=False, document="results")
    results["frames"][0]["text"] = "Hotel availability and displayed search results"
    assert ledger.submitted(closed, results, closed["url"])
    assert check(ledger, results)["method"] == "verified_pre_submit_form"


def test_result_document_retains_only_the_canonical_destination_verified_before_submit():
    fresh = observation()
    ledger = task(fresh)
    act(ledger, fresh)
    label = "New York, New York, United States of America"
    closed = observation(opened=False, value=label)
    assert check(ledger, closed)["status"] == "verified"
    results = observation(opened=False, document="results", value=label)
    results["frames"][0]["text"] = "Hotel availability and displayed search results"
    assert ledger.submitted(closed, results, closed["url"])
    assert check(ledger, results)["method"] == "verified_pre_submit_form"
    assert check(ledger, results)["observed"] == label
    wrong = observation(opened=False, document="results", value="New York, New Jersey, US")
    assert check(ledger, wrong)["status"] == "mismatch"


def test_generic_non_hotel_query_binding_keeps_plain_field_verification():
    fresh = observation()
    ledger = task(fresh, bound=True, name="query")
    assert check(ledger, fresh)["status"] == "verified"
    assert check(ledger, fresh)["method"] == "bound_control_readback"


def autocomplete_markup(parent=False, canonical=False):
    attrs = 'id="owner" role="combobox" aria-controls="places" aria-expanded="true"'
    field = '<input name="destination" aria-label="Destination" value="New York"'
    field = f"<div {attrs}>{field}></div>" if parent else f"{field} {attrs}>"
    committed = "New York, New York, United States of America" if canonical else "New York"
    return f"""<form onsubmit="event.preventDefault()">{field}
      <div id=places role=listbox><button aria-label="New York" onclick="
        event.preventDefault();
        document.querySelector('#owner').setAttribute('aria-expanded','false');
        document.querySelector('[name=destination]').value='{committed}';
        this.parentElement.hidden=true">New York <span>New York, United States of America</span>
        </button></div>
      <div role=listbox><button aria-label="New York" type=button>Unrelated New York</button></div>
      <button type=submit>Search</button></form>"""


@pytest.mark.parametrize("parent", [False, True], ids=["input-combobox", "parent-combobox"])
def test_local_observation_links_owned_options_and_verifies_clicked_selection(agent_page, parent):
    agent_page.set_content(autocomplete_markup(parent))
    tools = tools_for(agent_page)
    fresh = tools.observe()
    all_controls = [item for frame in fresh["frames"] for item in frame["controls"]]
    field = next(item for item in all_controls if item.get("name") == "destination")
    assert field["selection_required"] and field["expanded"] == "true"
    owned = [item for item in all_controls if item["id"] in field["option_ids"]]
    assert len(owned) == 1 and owned[0]["option_primary"] == "New York"
    assert owned[0]["id"].startswith("0:") and owned[0]["submits_form"]
    assert "United States" in owned[0]["text"]
    unrelated = next(item for item in all_controls if "Unrelated" in item.get("text", ""))
    assert unrelated["id"] not in field["option_ids"] and "option_primary" not in unrelated
    ledger = task(fresh)
    assert ledger.pending() == ["destination"]
    choose = decision("click", owned[0]["id"], purpose="set_field")
    assert not ledger.is_submit(choose, owned[0])
    ledger.before_action(owned[0], choose, fresh)
    outcome = tools.execute(choose)
    ledger.remember_action(owned[0], outcome, choose, fresh)
    assert check(ledger, tools.observe())["status"] == "verified"
    assert agent_page.locator('[name="destination"]').input_value() == "New York"


@pytest.mark.parametrize("parent", [False, True], ids=["input-combobox", "parent-combobox"])
def test_local_canonical_destination_commitment_does_not_block_search(agent_page, parent):
    agent_page.set_content(autocomplete_markup(parent, canonical=True))
    tools = tools_for(agent_page)
    fresh = tools.observe()
    all_controls = [item for frame in fresh["frames"] for item in frame["controls"]]
    field = next(item for item in all_controls if item.get("name") == "destination")
    owned = [item for item in all_controls if item["id"] in field["option_ids"]]
    assert len(owned) == 1
    ledger = task(fresh)
    choose = decision("click", owned[0]["id"], purpose="set_field")
    ledger.before_action(owned[0], choose, fresh)
    ledger.remember_action(owned[0], tools.execute(choose), choose, fresh)
    result = check(ledger, tools.observe())
    assert result["status"] == "verified"
    assert result["observed"] == "New York, New York, United States of America"
    assert not ledger.pending()
    assert ledger.completion_problem().startswith("Requested form values must be verified")
    # Selection is confirmed, but completion still requires an observed Search response.


@pytest.mark.parametrize("parent", [False, True], ids=["input-combobox", "parent-combobox"])
def test_local_known_destination_option_binding_does_not_poison_canonical_commitment(
    agent_page, parent
):
    agent_page.set_content(autocomplete_markup(parent, canonical=True))
    tools = tools_for(agent_page)
    fresh = tools.observe()
    all_controls = [item for frame in fresh["frames"] for item in frame["controls"]]
    field = next(item for item in all_controls if item.get("name") == "destination")
    owned = [item for item in all_controls if item["id"] in field["option_ids"]]
    ledger = task(fresh)
    ledger.declare([requirement(control_id=field["id"])], fresh)
    before = deepcopy(ledger.bindings)
    ledger.declare([requirement(control_id=owned[0]["id"], quote="")], fresh)
    assert ledger.bindings == before
    choose = decision("click", owned[0]["id"], purpose="set_field")
    ledger.before_action(owned[0], choose, fresh)
    ledger.remember_action(owned[0], tools.execute(choose), choose, fresh)
    result = check(ledger, tools.observe())
    assert result["status"] == "verified"
    assert result["observed"] == "New York, New York, United States of America"
    assert not ledger.pending()


def test_local_empty_destination_enters_text_before_reviewing_an_owned_choice(agent_page):
    agent_page.set_content(autocomplete_markup(parent=True, canonical=True))
    agent_page.locator('[name="destination"]').fill("")
    tools = tools_for(agent_page)
    fresh = tools.observe()
    field = next(
        item
        for frame in fresh["frames"]
        for item in frame["controls"]
        if item.get("name") == "destination"
    )
    ledger = task(fresh)
    empty = check(ledger, fresh)
    assert empty["observed"] == "" and empty["next_action"] == "fill"
    assert empty["selection_options"] == []

    enter = decision("fill", field["id"], "New York", purpose="set_field")
    ledger.before_action(field, enter, fresh)
    ledger.remember_action(field, tools.execute(enter), enter, fresh)
    typed = tools.observe()
    result = check(ledger, typed)
    assert result["observed"] == "New York" and result["next_action"] == "select_option"
    assert result["status"] == "pending"
    choice_id = result["selection_options"][0]["control_id"]
    choice = next(
        item for frame in typed["frames"] for item in frame["controls"] if item["id"] == choice_id
    )
    choose = decision("click", choice_id, purpose="set_field")
    ledger.before_action(choice, choose, typed)
    ledger.remember_action(choice, tools.execute(choose), choose, typed)
    assert check(ledger, tools.observe())["status"] == "verified"
    assert agent_page.locator('[name="destination"]').input_value() == (
        "New York, New York, United States of America"
    )


def test_local_hidden_suggestions_without_click_are_not_selection_proof(agent_page):
    agent_page.set_content(autocomplete_markup(parent=True))
    tools = tools_for(agent_page)
    ledger = task(tools.observe())
    agent_page.locator("#places").evaluate("node=>node.hidden=true")
    agent_page.locator("#owner").evaluate("node=>node.setAttribute('aria-expanded','false')")
    assert check(ledger, tools.observe())["status"] == "pending"


def test_local_combobox_wrapper_with_two_inputs_does_not_guess_option_ownership(agent_page):
    agent_page.set_content("""<div role=combobox aria-controls=places aria-expanded=true>
      <input name=first aria-label=Destination value="New York">
      <input name=second aria-label=City value="New York"></div>
      <div id=places role=listbox><button aria-label="New York">New York US</button></div>""")
    fresh = tools_for(agent_page).observe()
    all_controls = [item for frame in fresh["frames"] for item in frame["controls"]]
    fields = [item for item in all_controls if item.get("tag") == "INPUT"]
    assert len(fields) == 2 and all(not item.get("option_ids") for item in fields)
    assert all(item.get("selection_required") for item in fields)
    assert not any("option_primary" in item for item in all_controls)
    assert task(fresh).pending() == ["destination"]
    bound = TaskLedger("New York")
    bound.declare([requirement(control_id=fields[0]["id"])], fresh)
    assert check(bound, fresh)["status"] == "pending"
