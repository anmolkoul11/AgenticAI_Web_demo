import hashlib
import json
from datetime import date

import httpx
import pytest
from test_langgraph import FakeTools
from test_ollama_planner import body
from test_openai_planner import decision
from test_saved_plans import args as structured_args

from agentic_web_demo.agents.crewai_planner import CrewAIPlanner, LocalPlanningLLM
from agentic_web_demo.agents.crewai_workflow import run_workflow
from agentic_web_demo.agents.ollama_planner import OllamaPlanner, OllamaSettings
from agentic_web_demo.agents.planning import SCENARIOS, PlanningError, SimulatedPlanner
from agentic_web_demo.agents.saved_plans import execute_proposal, revision, save_proposal
from agentic_web_demo.cli import main
from agentic_web_demo.rules import Rules


def test_real_crew_task_with_mocked_transport():
    calls = []
    candidate = decision(**SimulatedPlanner().plan(SCENARIOS["new-york"], date.today()))

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=body(candidate))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        planner = CrewAIPlanner(OllamaPlanner(OllamaSettings(), client=client))
        result = run_workflow(SCENARIOS["new-york"], planner, None, plan_only=True)
    assert result["status"] == "planned", result
    assert result["model"]["orchestrator"] == "crewai"
    assert result["model_used"] is True
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["options"]["num_ctx"] == 8192
    assert "Hotel request planner" in json.dumps(payload["messages"])
    assert SCENARIOS["new-york"] in json.dumps(payload["messages"])
    assert str(calls[0].url) == "http://127.0.0.1:11434/api/chat"
    assert "authorization" not in calls[0].headers


@pytest.mark.parametrize(
    "stage", [None, "extract", "save", "export", "evaluate", "publish", "receive", "verify"]
)
def test_independent_flow_and_failure_stops(stage):
    tools = FakeTools(fail=stage)
    result = run_workflow(SCENARIOS["new-york"], SimulatedPlanner(), tools)
    assert result["framework"] == "crewai"
    expected = ["extract", "save", "export", "evaluate", "publish", "receive", "verify"]
    if stage:
        assert result["status"] == "failed"
        assert result["failed_stage"] == stage
        expected = expected[: expected.index(stage) + 1]
    else:
        assert result["status"] == "completed"
        assert result["receipts_verified"] == 2
    assert tools.calls == expected
    assert "secret-must-not-leak" not in json.dumps(result)


def test_no_match_and_unconfirmed_receipts():
    tools = FakeTools()
    result = run_workflow(SCENARIOS["no-matches"], SimulatedPlanner(), tools)
    assert result["status"] == "completed" and result["receipts_verified"] == 0
    assert "publish" not in tools.calls and "receive" not in tools.calls
    result = run_workflow(SCENARIOS["new-york"], SimulatedPlanner(), FakeTools(bad_receipts=True))
    assert result["status"] == "delivery_unconfirmed"


def test_missing_fields_never_access_tools():
    result = run_workflow(SCENARIOS["missing-city"], SimulatedPlanner(), None)
    assert result["status"] == "needs_input"
    assert result["missing_fields"] == ["city"]
    assert result["trace"] == ["plan_request:ok", "validate_plan:ok"]


def test_saved_framework_binding_and_no_replanning(tmp_path, monkeypatch):
    saved = save_proposal(
        tmp_path,
        SimulatedPlanner().plan(SCENARIOS["new-york"], date.today()),
        Rules(),
        "http://127.0.0.1:8000",
        source="structured",
        framework="crewai",
    )
    tools = FakeTools()
    tools.base_url = saved.base_url
    with pytest.raises(ValueError, match="Framework"):
        execute_proposal(tmp_path, str(saved.plan_id), revision(saved), Rules(), tools)

    def forbidden(*args, **kwargs):
        raise AssertionError("CrewAI must not call LangGraph")

    monkeypatch.setattr("agentic_web_demo.agents.langgraph_workflow.run_workflow", forbidden)
    result = execute_proposal(
        tmp_path, str(saved.plan_id), revision(saved), Rules(), tools, framework="crewai"
    )
    assert result["status"] == "completed" and result["framework"] == "crewai"
    assert result["model_api_attempted"] is False
    assert "plan_request:ok" not in result["trace"]
    with pytest.raises(FileExistsError):
        execute_proposal(
            tmp_path, str(saved.plan_id), revision(saved), Rules(), tools, framework="crewai"
        )


def test_v1_revision_compatibility(tmp_path):
    saved = save_proposal(
        tmp_path,
        SimulatedPlanner().plan(SCENARIOS["new-york"], date.today()),
        Rules(),
        "http://127.0.0.1:8000",
        source="structured",
    )
    saved.version = 1
    payload = saved.model_dump(mode="json")
    payload.pop("framework")
    old = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    assert revision(saved) == old.hexdigest()


def test_crewai_cli_structured_review_and_provider_rejection(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    args = structured_args()
    args[0] = "crewai"
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["proposal"]["framework"] == "crewai"
    plan_id = result["proposal"]["plan_id"]
    assert main(["crewai", "review", "--plan-id", plan_id]) == 0
    capsys.readouterr()
    assert main(["langgraph", "review", "--plan-id", plan_id]) == 2
    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "openai")
    assert main(["crewai", "plan", "--request", "demo", "--allow-model-api"]) == 2


def test_bridge_cannot_retry_or_call_tools():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        llm = LocalPlanningLLM(OllamaPlanner(OllamaSettings(), client=client), date.today())
        with pytest.raises(PlanningError):
            llm.call("test")
        with pytest.raises(PlanningError):
            llm.call("retry")


def test_local_conversation_bound():
    transport = OllamaPlanner(OllamaSettings())
    with pytest.raises(PlanningError):
        transport.plan_messages([{"role": "user", "content": "x" * 17000}], date.today())
