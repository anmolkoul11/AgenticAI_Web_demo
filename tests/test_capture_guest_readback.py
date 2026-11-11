"""Post-Update row inspection must survive passive same-document capture."""

from copy import deepcopy

import pytest

from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.stay_scope import (
    observed_result_scope, reconcile_captured_occupancy, reconcile_captured_result_scope,
)
from test_guest_label_scope import named_counters, requested


def captured_guest_context():
    task = TaskLedger(requested(4))
    closed = named_counters(opened=False)
    task.observe(closed)
    diagnostic = task.occupancy_recheck(closed, include_verified=True)
    opened = named_counters()
    task.observe(opened)
    proof = task.confirm_occupancy_inspection(opened, diagnostic)
    assert proof is not None and task.adopt_matching_results(opened, post_commit_inspection=proof)
    return task.capture_context(opened), closed


def test_passive_capture_keeps_independent_guest_split_with_unchanged_committed_summary():
    context, closed = captured_guest_context()
    original = deepcopy(context)
    scope = observed_result_scope(context["result_scope"]["requested"], closed)
    assert scope["status"] == "unverified"
    result = reconcile_captured_occupancy(scope, context, closed)
    # Reconciliation must also accept the full-date methods used by navigation.
    result = reconcile_captured_result_scope(result, [{
        "id": "b1", "kind": "heading", "association": "page", "group_id": None,
        "heading_level": 1, "text": "New York City Hotels",
    }], document_id=closed["document_id"])
    assert result["status"] == "verified"
    assert result["observed"]["adults"] == "4" and result["observed"]["children"] == "0"
    assert result["availability_verified"] is False
    assert context == original and scope["status"] == "unverified"


@pytest.mark.parametrize("change", ["summary", "rooms", "dates", "document", "proof", "busy", "open_widget"])
def test_capture_does_not_promote_changed_or_unproven_counts(change):
    context, closed = captured_guest_context()
    fields = closed["frames"][0]["controls"]
    if change == "summary":
        fields[3]["text"] = "Rooms/Guests 3 Rooms, 5 Guests"
    elif change == "rooms":
        fields[3].update(label="Rooms/Guests 2 Rooms, 4 Guests", text="")
    elif change == "dates":
        fields[1].update(date="2026-11-28", label="Check-in November 28, 2026")
    elif change == "document":
        closed["document_id"] = "another-document"
    elif change == "proof":
        context["submission_provenance"].pop("occupancy_inspection")
    elif change == "busy":
        closed["results"]["busy"] = True
    else:
        fields.append({"id": "0:new-row", "counter": {"label": "child", "value": 1}})
    scope = observed_result_scope(context["result_scope"]["requested"], closed)
    result = reconcile_captured_occupancy(scope, context, closed)
    assert result["status"] != "verified"

