import json
from datetime import UTC, date, datetime

import pytest

from agentic_web_demo.agents.langgraph_workflow import run_workflow
from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner
from agentic_web_demo.cli import main
from agentic_web_demo.listings import Listing, Snapshot


class FakeTools:
    """No I/O. Separate browser/broker integration test exercises the real tool wrappers."""

    def __init__(self, fail=None, bad_receipts=False):
        self.calls = []
        self.fail = fail
        self.bad_receipts = bad_receipts
        self.matched = 2

    def call(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError("secret-must-not-leak")

    def extract(self, stay):
        self.call("extract")
        now = datetime.now(UTC)
        records = tuple(
            Listing(
                listing_id=f"NYC-{index}",
                title="Fictional fixture",
                city=stay.city,
                check_in=stay.check_in,
                check_out=stay.check_out,
                price="180",
                currency="USD",
                price_basis="per_night_taxes_included",
                rating="4.6",
                rating_scale=5,
                source_url=f"http://127.0.0.1:8000/listings#NYC-{index}",
                extracted_at=now,
            )
            for index in range(2)
        )
        return Snapshot(stay=stay, extracted_at=now, listings=records)

    def save(self, snapshot):
        self.call("save")
        return "00000000-0000-0000-0000-000000000001"

    def export(self, run_id):
        self.call("export")
        return "fixture-export.json"

    def evaluate(self, run_id, rules):
        self.call("evaluate")
        self.matched = 0 if rules.max_price < 180 else 2
        return {"evaluated": 2, "matched": self.matched}

    def publish(self, run_id):
        self.call("publish")
        return {"acknowledged": self.matched}

    def receive(self):
        self.call("receive")
        # Misleading aggregate: verification must inspect run-specific IDs instead.
        return {"received": 100}

    def status(self, run_id):
        self.call("verify")
        ids = [f"event-{index}" for index in range(self.matched)]
        return {
            "events": [{"event_id": item} for item in ids],
            "receipts": [] if self.bad_receipts else [{"event_id": item} for item in ids],
            "pending": 0,
            "published": self.matched,
        }


def test_success_is_explicitly_simulated():
    tools = FakeTools()
    result = run_workflow(SCENARIOS["new-york"], SimulatedPlanner(), tools)
    assert result["status"] == "completed"
    assert result["model_used"] is False
    assert result["workflow_verified"] is True
    assert result["model_api_attempted"] is False
    assert result["receipts_verified"] == 2
    assert tools.calls == ["extract", "save", "export", "evaluate", "publish", "receive", "verify"]
    assert "snapshot" not in result and "request" not in result


def test_missing_information_stops_before_tools():
    tools = FakeTools()
    result = run_workflow(SCENARIOS["missing-city"], SimulatedPlanner(), tools)
    assert result["status"] == "needs_input"
    assert result["missing_fields"] == ["city"]
    assert tools.calls == []


def test_no_matches_skips_broker():
    tools = FakeTools()
    result = run_workflow(SCENARIOS["no-matches"], SimulatedPlanner(), tools)
    assert result["status"] == "completed"
    assert "publish" not in tools.calls and "receive" not in tools.calls
    assert result["receipts_verified"] == 0


@pytest.mark.parametrize(
    "stage", ["extract", "save", "export", "evaluate", "publish", "receive", "verify"]
)
def test_failure_stops_and_redacts_errors(stage):
    tools = FakeTools(fail=stage)
    result = run_workflow(SCENARIOS["new-york"], SimulatedPlanner(), tools)
    assert result["status"] == "failed"
    assert result["failed_stage"] == stage
    assert tools.calls[-1] == stage
    assert "secret-must-not-leak" not in json.dumps(result)
    if stage not in {"extract", "save"}:
        assert "run_id" in result


def test_no_false_receipt_claim():
    result = run_workflow(SCENARIOS["new-york"], SimulatedPlanner(), FakeTools(bad_receipts=True))
    assert result["status"] == "delivery_unconfirmed"
    assert result["receipts_verified"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "EUR"},
        {"min_rating": "6"},
        {"shell_command": "never-run"},
        {"check_in": "2000-01-01", "check_out": "2000-01-02"},
        {"check_out": "2000-01-01"},
        {"max_price": "NaN"},
    ],
)
def test_invalid_planner_output_cannot_execute_tools(change):
    class InvalidPlanner:
        def plan(self, request, today):
            return {**SimulatedPlanner().plan(request, today), **change}

    tools = FakeTools()
    result = run_workflow(SCENARIOS["new-york"], InvalidPlanner(), tools)
    assert result["status"] == "failed"
    assert result["failed_stage"] == "validate_plan"
    assert tools.calls == []


def test_simulation_does_not_guess_arbitrary_requests():
    tools = FakeTools()
    result = run_workflow("Book something and spend money", SimulatedPlanner(), tools)
    assert result["status"] == "failed"
    assert tools.calls == []


def test_simulated_dates_are_relative_and_unambiguous():
    plan = SimulatedPlanner().plan(SCENARIOS["boston"], date(2026, 9, 15))
    assert plan["check_in"] == "2026-09-22"
    assert plan["check_out"] == "2026-09-24"


def test_cli_requires_explicit_simulated_mode():
    with pytest.raises(SystemExit) as exc:
        main(["langgraph"])
    assert exc.value.code == 2


def test_missing_city_cli_needs_no_credentials_or_output(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "unused"))
    assert main(["langgraph", "--mode", "simulated", "--scenario", "missing-city"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "needs_input"
    assert "SIMULATED" in captured.err
    assert not (tmp_path / "unused").exists()
