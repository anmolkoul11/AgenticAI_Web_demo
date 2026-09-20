import json
from datetime import UTC, date, datetime, timedelta

import pytest
from test_langgraph import FakeTools

from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner
from agentic_web_demo.agents.saved_plans import (
    execute_proposal,
    load_proposal,
    plan_path,
    revision,
    save_proposal,
)
from agentic_web_demo.cli import main
from agentic_web_demo.rules import Rules


def proposal(tmp_path, **changes):
    plan = SimulatedPlanner().plan(SCENARIOS["new-york"], date.today())
    plan.update(changes)
    return save_proposal(tmp_path, plan, Rules(), "http://127.0.0.1:8100", source="structured")


def tools():
    instance = FakeTools()
    instance.base_url = "http://127.0.0.1:8100"
    return instance


def test_execute_exact_plan_no_model_and_no_replay(tmp_path):
    saved = proposal(tmp_path)
    instance = tools()
    result = execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), instance)
    assert result["status"] == "completed"
    assert result["plan"] == saved.plan.model_dump(mode="json")
    assert result["model_used"] is False and result["model_api_attempted"] is False
    assert result["trace"][0] == "validate_plan:ok"
    assert not any("plan_request" in step for step in result["trace"])
    assert load_proposal(tmp_path, str(saved.plan_id)) == saved
    with pytest.raises(FileExistsError):
        execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), tools())


@pytest.mark.parametrize("change", ["approval", "content", "expiry", "policy", "target", "date"])
def test_reject_before_tools(tmp_path, change):
    saved = proposal(tmp_path)
    digest = revision(saved)
    policy = Rules()
    instance = tools()
    if change == "approval":
        digest = "wrong"
    elif change == "content":
        saved.plan = saved.plan.model_copy(update={"city": "Boston"})
    elif change == "expiry":
        saved.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        digest = revision(saved)
    elif change == "policy":
        policy = Rules(max_price=190)
    elif change == "target":
        instance.base_url = "http://127.0.0.1:8200"
    elif change == "date":
        saved.plan = saved.plan.model_copy(update={"check_in": date.today() - timedelta(days=1)})
        digest = revision(saved)
    plan_path(tmp_path, str(saved.plan_id)).write_text(saved.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        execute_proposal(tmp_path, str(saved.plan_id), digest, policy, instance)
    assert instance.calls == []
    assert not plan_path(tmp_path, str(saved.plan_id)).with_suffix(".attempt.json").exists()


def test_no_matches_skips_publishing(tmp_path):
    saved = proposal(tmp_path, max_price="50")
    instance = tools()
    result = execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), instance)
    assert result["status"] == "completed"
    assert result["receipts_verified"] == 0
    assert "publish" not in instance.calls


@pytest.mark.parametrize("stage", ["extract", "save", "export", "evaluate", "publish", "receive"])
def test_failure_retains_attempt_and_report(tmp_path, stage):
    saved = proposal(tmp_path)
    instance = tools()
    instance.fail = stage
    result = execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), instance)
    assert result["failed_stage"] == stage
    report = plan_path(tmp_path, str(saved.plan_id)).with_suffix(".result.json")
    assert json.loads(report.read_text())["status"] == "failed"
    assert "secret-must-not-leak" not in report.read_text()
    with pytest.raises(FileExistsError):
        execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), tools())


def args():
    return [
        "langgraph",
        "plan",
        "--city",
        "New York",
        "--check-in",
        (date.today() + timedelta(days=7)).isoformat(),
        "--check-out",
        (date.today() + timedelta(days=9)).isoformat(),
        "--max-price",
        "200",
        "--min-rating",
        "4",
        "--base-url",
        "http://127.0.0.1:8100",
    ]


def test_cli_structured_review_execute(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    assert main(args()) == 0
    output = json.loads(capsys.readouterr().out)
    plan_id = output["proposal"]["plan_id"]
    assert output["proposal"]["source"] == "structured"
    assert main(["langgraph", "review", "--plan-id", plan_id]) == 0
    assert json.loads(capsys.readouterr().out)["revision"] == output["revision"]
    assert main(["langgraph", "execute", "--plan-id", plan_id]) == 2
    capsys.readouterr()
    monkeypatch.setattr("agentic_web_demo.agents.tools.DemoTools", lambda **kwargs: tools())
    assert (
        main(
            [
                "langgraph",
                "execute",
                "--plan-id",
                plan_id,
                "--approve",
                output["revision"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["workflow_verified"] is True


@pytest.mark.parametrize(
    "extra",
    [
        ["--adapter", "unknown"],
        ["--all-cities"],
        ["--request", "ambiguous"],
        ["--mode", "live"],
    ],
)
def test_cli_reject_mixed_or_unsupported_inputs(tmp_path, monkeypatch, extra):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    assert main(args() + extra) == 2
    assert not (tmp_path / "plans").exists()


def test_cli_model_proposal_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("AGENTIC_MODEL_NAME", "fixture-model")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    from agentic_web_demo.agents.openai_planner import OpenAIPlanner

    def fake_plan(self, request, today):
        self.metadata = {"provider": "openai", "response_received": True}
        return SimulatedPlanner().plan(SCENARIOS["new-york"], today)

    monkeypatch.setattr(OpenAIPlanner, "plan", fake_plan)
    assert main(["langgraph", "plan", "--request", "synthetic request", "--allow-model-api"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "awaiting_review"
    assert output["proposal"]["source"] == "model-assisted"
    assert output["proposal"]["request"] == "synthetic request"
    assert not list((tmp_path / "plans").glob("*.attempt.json"))


def test_invalid_id_cannot_escape_directory(tmp_path):
    with pytest.raises(ValueError):
        load_proposal(tmp_path, "../../config/rules")
