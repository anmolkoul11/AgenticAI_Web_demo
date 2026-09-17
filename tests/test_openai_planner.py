"""Real SDK serialization/parsing against MockTransport, never the network."""

import json
from datetime import date

import httpx
import pytest
from openai import OpenAI
from test_langgraph import FakeTools

from agentic_web_demo.agents.langgraph_workflow import run_workflow
from agentic_web_demo.agents.openai_planner import ModelSettings, OpenAIPlanner
from agentic_web_demo.agents.planning import SCENARIOS, PlanningError, SimulatedPlanner
from agentic_web_demo.cli import main
from agentic_web_demo.rules import Rules

TODAY = date(2026, 9, 15)


@pytest.fixture(autouse=True)
def openai_test_provider(monkeypatch):
    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "openai")


def decision(**changes):
    return {
        **SimulatedPlanner().plan(SCENARIOS["new-york"], TODAY),
        "outcome": "ready",
        "clarification_fields": [],
        "reason": "none",
        **changes,
    }


def response_payload(candidate=None, *, text=None, status="completed", refusal=False):
    content = (
        [{"type": "refusal", "refusal": "secret-must-not-leak"}]
        if refusal
        else [
            {
                "type": "output_text",
                "annotations": [],
                "text": text if text is not None else json.dumps(candidate),
            }
        ]
    )
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 1,
        "status": status,
        "model": "fixture-model",
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "usage": {"input_tokens": 50, "output_tokens": 30, "total_tokens": 80},
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
    }


@pytest.fixture
def mocked_planner():
    clients = []

    def make(candidate=None, *, status=200, payload=None, error=None, retries=0):
        requests = []

        def handler(request):
            requests.append(request)
            if error:
                raise error("secret-must-not-leak", request=request)
            body = payload if payload is not None else response_payload(candidate or decision())
            return httpx.Response(status, json=body)

        client = OpenAI(
            api_key="fixture-secret-never-real",
            base_url="https://api.openai.com/v1",
            max_retries=retries,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        planner = OpenAIPlanner(ModelSettings("fixture-model", "fixture-secret"), client=client)
        return planner, requests

    yield make
    for client in clients:
        client.close()


def test_sdk_wire_contract_and_metadata(mocked_planner):
    planner, requests = mocked_planner()
    result = run_workflow("synthetic request", planner, FakeTools(), today=TODAY)
    assert result["status"] == "completed"
    assert result["model_used"] and result["model_api_attempted"]
    assert result["mode"] == "live"
    assert result["receipts_verified"] == 2
    assert result["model"]["usage"]["total_tokens"] == 80
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert str(requests[0].url) == "https://api.openai.com/v1/responses"
    assert body["store"] is False and body["max_output_tokens"] == 1200
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    assert "2026-09-15" in body["input"][0]["content"]
    assert body["input"][1]["content"] == "synthetic request"
    assert "tools" not in body and "previous_response_id" not in body
    assert "fixture-secret" not in json.dumps(result)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (500, "provider_error"),
        (400, "provider_error"),
    ],
)
def test_http_failure_stops_before_tools_and_redacts(mocked_planner, status, code):
    planner, requests = mocked_planner(
        status=status, payload={"error": {"message": "secret-must-not-leak"}}
    )
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools)
    assert result["status"] == "failed" and result["error_code"] == code
    assert result["failed_stage"] == "plan_request"
    assert tools.calls == [] and len(requests) == 1
    assert "secret-must-not-leak" not in json.dumps(result)


@pytest.mark.parametrize(
    "error,code", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")]
)
def test_transport_failures_are_bounded(mocked_planner, error, code):
    planner, requests = mocked_planner(error=error, retries=1)
    with pytest.raises(PlanningError) as exc:
        planner.plan("synthetic", TODAY)
    assert exc.value.code == code
    assert len(requests) == 2


@pytest.mark.parametrize(
    "payload,code",
    [
        (response_payload(refusal=True), "refusal"),
        (response_payload(decision(), status="incomplete"), "incomplete"),
        (response_payload(text="not-json secret-must-not-leak"), "invalid_response"),
        (response_payload(decision(shell_command="never-run")), "invalid_response"),
        (response_payload(decision(outcome="invented")), "invalid_response"),
    ],
)
def test_unusable_responses_do_not_fallback(mocked_planner, payload, code):
    planner, _ = mocked_planner(payload=payload)
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools)
    assert result["status"] == "failed" and result["error_code"] == code
    assert tools.calls == []
    assert "secret-must-not-leak" not in json.dumps(result)


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"city": None}, "needs_input"),
        (
            {"outcome": "needs_input", "clarification_fields": ["check_in", "check_out"]},
            "needs_input",
        ),
        ({"outcome": "unsupported", "reason": "unsupported_task"}, "unsupported"),
        ({"max_price": "201"}, "policy_rejected"),
        ({"min_rating": "3.9"}, "policy_rejected"),
        ({"max_price": "NaN"}, "failed"),
        ({"max_price": "200.001"}, "failed"),
        ({"min_rating": "6"}, "failed"),
        ({"check_in": "2000-01-01", "check_out": "2000-01-02"}, "failed"),
        ({"check_out": "2026-09-20"}, "failed"),
        ({"check_out": "2026-11-20"}, "failed"),
    ],
)
def test_domain_gate_stops_tools(mocked_planner, changes, status):
    planner, _ = mocked_planner(decision(**changes))
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools, today=TODAY)
    assert result["status"] == status
    assert tools.calls == []
    assert "run_id" not in result


def test_plan_only_is_side_effect_free_and_preserves_policy_identity(mocked_planner):
    planner, _ = mocked_planner(decision(max_price="190", min_rating="4.5"))
    tools = FakeTools()
    result = run_workflow(
        "synthetic",
        planner,
        tools,
        today=TODAY,
        plan_only=True,
        policy=Rules(rule_id="demo-policy", version=3),
    )
    assert result["status"] == "planned" and not result["workflow_verified"]
    assert tools.calls == []
    assert result["effective_rules"]["rule_id"] == "demo-policy"
    assert result["effective_rules"]["version"] == 3
    assert result["effective_rules"]["max_price"] == "190"


@pytest.mark.parametrize("request_text", ["", "  ", "x" * 2001])
def test_request_limits_prevent_network(mocked_planner, request_text):
    planner, requests = mocked_planner()
    with pytest.raises(PlanningError, match="request_invalid"):
        planner.plan(request_text, TODAY)
    assert requests == [] and not planner.metadata["api_attempted"]


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"OPENAI_API_KEY": "fixture"},
        {"AGENTIC_MODEL_NAME": "fixture"},
        {"AGENTIC_MODEL_TIMEOUT_SECONDS": "nan"},
        {"AGENTIC_MODEL_TIMEOUT_SECONDS": "61"},
        {"AGENTIC_MODEL_MAX_RETRIES": "3"},
        {"AGENTIC_MODEL_MAX_OUTPUT_TOKENS": "99999"},
        {"AGENTIC_MODEL_PROVIDER": "unimplemented"},
    ],
)
def test_bad_settings_fail_without_exposing_values(env):
    supplied = {"OPENAI_API_KEY": "fixture", "AGENTIC_MODEL_NAME": "fixture", **env}
    if env in ({}, {"OPENAI_API_KEY": "fixture"}, {"AGENTIC_MODEL_NAME": "fixture"}):
        supplied = env
    with pytest.raises(ValueError) as exc:
        ModelSettings.from_env(supplied)
    assert "fixture" not in str(exc.value)


def test_settings_repr_excludes_key():
    assert "secret-must-not-leak" not in repr(ModelSettings("fixture", "secret-must-not-leak"))


@pytest.mark.parametrize(
    "args",
    [
        ["--mode", "live", "--request", "synthetic"],
        ["--mode", "live", "--allow-model-api"],
        ["--mode", "live", "--allow-model-api", "--request", " "],
        ["--mode", "live", "--allow-model-api", "--scenario", "new-york"],
        ["--mode", "simulated", "--request", "synthetic"],
        ["--mode", "simulated", "--allow-model-api"],
    ],
)
def test_cli_requires_explicit_valid_live_request(args, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "unused"))
    assert main(["langgraph", *args]) == 2
    assert not (tmp_path / "unused").exists()


def test_cli_live_preview_with_mock_sdk(mocked_planner, monkeypatch, tmp_path, capsys):
    import agentic_web_demo.agents.openai_planner as adapter

    # Fixed dates must remain future relative to the local test date.
    candidate = decision(**SimulatedPlanner().plan(SCENARIOS["new-york"], date.today()))
    planner, requests = mocked_planner(candidate)
    monkeypatch.setattr(adapter, "OpenAIPlanner", lambda settings: planner)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    monkeypatch.setenv("AGENTIC_MODEL_NAME", "fixture")
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "unused"))
    assert (
        main(
            [
                "langgraph",
                "--mode",
                "live",
                "--allow-model-api",
                "--plan-only",
                "--request",
                "synthetic",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "planned" and result["model_used"]
    assert len(requests) == 1 and not (tmp_path / "unused").exists()


def test_owned_client_pins_endpoint_and_closes(monkeypatch, mocked_planner):
    import agentic_web_demo.agents.openai_planner as adapter

    injected, _ = mocked_planner()
    seen = {}

    def factory(**kwargs):
        seen.update(kwargs)
        kwargs["http_client"].close()
        return injected.client

    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.invalid")
    monkeypatch.setattr(adapter, "OpenAI", factory)
    planner = OpenAIPlanner(ModelSettings("fixture", "fixture-key"))
    planner.plan("synthetic", TODAY)
    assert seen["base_url"] == "https://api.openai.com/v1"
    assert seen["timeout"] == 30 and seen["max_retries"] == 1
    assert injected.client.is_closed()


def test_rate_limit_retries_are_bounded(mocked_planner):
    planner, requests = mocked_planner(
        status=429, retries=1, payload={"error": {"message": "secret-must-not-leak"}}
    )
    with pytest.raises(PlanningError, match="rate_limit"):
        planner.plan("synthetic", TODAY)
    assert len(requests) == 2


def test_missing_output_cannot_execute(mocked_planner):
    payload = response_payload(decision())
    payload["output"] = []
    planner, _ = mocked_planner(payload=payload)
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools, today=TODAY)
    assert result["error_code"] == "invalid_response"
    assert tools.calls == []


def test_policy_file_failure_prevents_model_creation(monkeypatch, tmp_path, capsys):
    import agentic_web_demo.agents.openai_planner as adapter

    def forbidden(settings):
        pytest.fail("Model must not be constructed when policy loading failed")

    monkeypatch.setattr(adapter, "OpenAIPlanner", forbidden)
    assert (
        main(
            [
                "langgraph",
                "--mode",
                "live",
                "--allow-model-api",
                "--request",
                "synthetic",
                "--policy",
                str(tmp_path / "missing.yaml"),
            ]
        )
        == 1
    )
    assert "setup/execution failed" in capsys.readouterr().err


def test_missing_key_never_constructs_model(monkeypatch, capsys):
    import agentic_web_demo.agents.openai_planner as adapter

    def forbidden(settings):
        pytest.fail("Missing configuration must stop before model construction")

    monkeypatch.setattr(adapter, "OpenAIPlanner", forbidden)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AGENTIC_MODEL_NAME", "fixture")
    assert main(["langgraph", "--mode", "live", "--allow-model-api", "--request", "synthetic"]) == 1
    assert "setup/execution failed" in capsys.readouterr().err


def test_temporary_provider_error_can_recover_once():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": {"message": "temporary"}})
        return httpx.Response(200, json=response_payload(decision()))

    with OpenAI(
        api_key="fixture",
        max_retries=1,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        planner = OpenAIPlanner(ModelSettings("fixture", "fixture"), client=client)
        result = run_workflow("synthetic", planner, FakeTools(), today=TODAY)
    assert result["status"] == "completed"
    assert len(requests) == 2
