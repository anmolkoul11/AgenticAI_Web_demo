"""Offline regression tests: rejecting a request must never produce an executable plan."""

from datetime import date

import pytest
from pydantic import ValidationError

from agentic_web_demo.agents.planning import validate_candidate
from agentic_web_demo.agents.runners import get_runner


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
@pytest.mark.parametrize("rating", ["8", "80", "not a rating"])
def test_unsupported_fields_do_not_become_validation_failures(framework, rating):
    class RejectionPlanner:
        def plan(self, request, today):
            return {
                "outcome": "unsupported",
                "reason": "unsupported_filter",
                "min_rating": rating,
                "check_in": "not a date",
            }

    class NoTools:
        def __getattr__(self, name):
            raise AssertionError("Rejected requests must never access tools")

    result = get_runner(framework)("synthetic request", RejectionPlanner(), NoTools())
    assert result["status"] == "unsupported"
    assert result["reason"] == "unsupported_filter"
    assert "plan" not in result
    assert "run_id" not in result
    assert not result["workflow_verified"]


@pytest.mark.parametrize("outcome", ["ready", "needs_input"])
def test_non_rejections_still_validate_rating(outcome):
    with pytest.raises(ValidationError):
        validate_candidate({"outcome": outcome, "min_rating": "8"}, date.today())


@pytest.mark.parametrize("extra", [{"reason": "invented"}, {"unknown": True}])
def test_rejections_still_validate_control_fields(extra):
    with pytest.raises(ValidationError):
        validate_candidate({"outcome": "unsupported", **extra}, date.today())


def test_rejection_does_not_mutate_original_candidate():
    candidate = {"outcome": "unsupported", "min_rating": "8"}
    result = validate_candidate(candidate, date.today())
    assert result["status"] == "unsupported"
    assert candidate["min_rating"] == "8"
