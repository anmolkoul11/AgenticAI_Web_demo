"""Offline destination-commitment fixtures; no browser, site or model calls."""

from copy import deepcopy

import pytest
from test_destination_selection import act, check, observation, requirement, task


CANONICAL_CITY = "New York, New York, United States of America"


def scoped_observation(*, scope="0:form:0", **kwargs):
    fresh = observation(**kwargs)
    fresh["frames"][0]["controls"][0]["form_scope"] = scope
    return fresh


@pytest.mark.parametrize("bound", [False, True])
def test_named_destination_click_survives_form_index_change_before_readback(bound):
    before = scoped_observation()
    ledger = task(before, bound=bound)
    act(ledger, before)

    # An unrelated form inserted earlier in the document changes the collector's
    # form index, not this named input or the destination the user selected.
    committed = scoped_observation(
        scope="0:form:1", opened=False, value=CANONICAL_CITY
    )
    committed["frames"][0]["controls"][0]["id"] = "0:fresh-input"
    committed["frames"][0]["controls"].append(
        {"id": "0:subscribe", "tag": "BUTTON", "type": "submit",
         "label": "Subscribe", "form_scope": "0:form:0"}
    )
    result = check(ledger, committed)

    assert result["status"] == "verified"
    assert result["method"] == "autocomplete_selection_readback"
    assert result["observed"] == CANONICAL_CITY
    assert not ledger.pending()


@pytest.mark.parametrize("bound", [False, True])
def test_verified_named_destination_is_not_lost_when_unrelated_form_is_inserted(bound):
    before = scoped_observation()
    ledger = task(before, bound=bound)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=CANONICAL_CITY)
    assert check(ledger, committed)["status"] == "verified"

    shifted = deepcopy(committed)
    shifted["frames"][0]["controls"][0]["form_scope"] = "0:form:3"
    shifted["frames"][0]["controls"][0]["id"] = "0:rerendered-input"
    result = check(ledger, shifted)

    assert result["status"] == "verified"
    assert result["observed"] == CANONICAL_CITY
    assert "next_action" not in result
    assert len(ledger.destination_selections) == 1


@pytest.mark.parametrize("bound", [False, True])
def test_form_index_change_does_not_let_duplicate_named_inputs_reuse_commitment(bound):
    before = scoped_observation()
    ledger = task(before, bound=bound)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=CANONICAL_CITY)
    assert check(ledger, committed)["status"] == "verified"

    ambiguous = deepcopy(committed)
    duplicate = deepcopy(ambiguous["frames"][0]["controls"][0])
    duplicate.update(id="0:other-destination", form_scope="0:form:1")
    ambiguous["frames"][0]["controls"].append(duplicate)
    result = check(ledger, ambiguous)

    assert result["status"] == "pending"
    assert "destination" in ledger.pending()
    assert "next_action" not in result
    assert "ambiguous" in result["evidence"] or "Multiple destination" in result["evidence"]


@pytest.mark.parametrize("other_scope", ["0:form:1", "0:form:0"])
def test_distinctly_labelled_named_inputs_do_not_share_clicked_destination_proof(other_scope):
    before = scoped_observation()
    other = deepcopy(before["frames"][0]["controls"][0])
    other.update(
        id="0:other-destination", label="Alternate destination", form_scope=other_scope,
        expanded="false", option_ids=[]
    )
    before["frames"][0]["controls"].append(other)
    ledger = task(before, bound=True)
    act(ledger, before)

    committed = deepcopy(before)
    first = committed["frames"][0]["controls"][0]
    first.update(value=CANONICAL_CITY, expanded="false", option_ids=[])
    second = next(
        field for field in committed["frames"][0]["controls"]
        if field["id"] == "0:other-destination"
    )
    second.update(value=CANONICAL_CITY)
    assert check(ledger, committed)["status"] == "verified"

    # A distinct accessible label can give the planner an explicit, unique
    # binding even when native names repeat. It does not transfer the option
    # click performed on the first input to this second input.
    ledger.declare([requirement(control_id="0:other-destination", quote="")], committed)
    assert check(ledger, committed)["status"] != "verified"
    assert "destination" in ledger.pending()


@pytest.mark.parametrize("bound", [False, True])
def test_form_index_change_cannot_transfer_a_named_commitment_to_a_new_document(bound):
    before = scoped_observation()
    ledger = task(before, bound=bound)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=CANONICAL_CITY)
    assert check(ledger, committed)["status"] == "verified"

    navigated = scoped_observation(
        scope="0:form:2", opened=False, value=CANONICAL_CITY, document="other"
    )
    assert check(ledger, navigated)["status"] != "verified"
    assert "destination" in ledger.pending()


@pytest.mark.parametrize("bound", [False, True])
def test_form_index_change_does_not_accept_a_different_destination_readback(bound):
    before = scoped_observation()
    ledger = task(before, bound=bound)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=CANONICAL_CITY)
    assert check(ledger, committed)["status"] == "verified"

    wrong = scoped_observation(
        scope="0:form:1", opened=False, value="New York, New Jersey, United States"
    )
    assert check(ledger, wrong)["status"] == "mismatch"
    # Returning to the earlier canonical label cannot resurrect discarded proof.
    restored = scoped_observation(
        scope="0:form:1", opened=False, value=CANONICAL_CITY
    )
    assert check(ledger, restored)["status"] != "verified"


@pytest.mark.parametrize("bound", [False, True])
def test_unnamed_input_does_not_gain_named_field_scope_stability(bound):
    before = scoped_observation()
    before["frames"][0]["controls"][0]["name"] = ""
    ledger = task(before, bound=bound)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=CANONICAL_CITY)
    committed["frames"][0]["controls"][0]["name"] = ""
    assert check(ledger, committed)["status"] == "verified"

    shifted = deepcopy(committed)
    shifted["frames"][0]["controls"][0]["form_scope"] = "0:form:1"
    assert check(ledger, shifted)["status"] != "verified"


@pytest.mark.parametrize(
    "expected,accessible_label,readback",
    [
        ("New York", "New York New York, United States of America", CANONICAL_CITY),
        ("Lisbon", "Lisbon Lisbon Region, Portugal", "Lisbon, Lisbon Region, Portugal"),
    ],
)
def test_observed_primary_preserves_full_clicked_option_provenance(
    expected, accessible_label, readback
):
    before = scoped_observation(value=expected)
    option = before["frames"][0]["controls"][1]
    option.update(
        option_primary=expected, label=accessible_label, text=accessible_label
    )
    ledger = task(before, bound=True, expected=expected)
    act(ledger, before)
    committed = scoped_observation(opened=False, value=readback)
    result = check(ledger, committed)

    assert result["status"] == "verified"
    assert result["observed"] == readback
    assert ledger.requirements["destination"]["expected"] == expected
    selection = next(iter(ledger.destination_selections.values()))
    assert selection["choice"]["option_primary"] == expected
    assert selection["choice"]["label"] == accessible_label


@pytest.mark.parametrize(
    "primary,label",
    [
        ("New York Central Park", "New York Central Park New York, United States"),
        ("New York-New York", "New York-New York Las Vegas, United States"),
        ("New York", "New York Airport, United States"),
        ("New York", "New York Search with AI"),
    ],
)
def test_stable_named_key_does_not_relax_destination_match_to_a_prefix(primary, label):
    before = scoped_observation()
    before["frames"][0]["controls"][1].update(
        option_primary=primary, label=label, text=label
    )
    ledger = task(before, bound=True)
    act(ledger, before)
    closed = scoped_observation(scope="0:form:1", opened=False)
    assert check(ledger, closed)["status"] == "pending"
    assert "destination" in ledger.pending()
