"""Ollama HTTP contract and safety tests; no model server or downloads required."""

import json
from datetime import date

import httpx
import pytest
from test_langgraph import FakeTools
from test_openai_planner import decision

from agentic_web_demo.agents.langgraph_workflow import run_workflow
from agentic_web_demo.agents.ollama_planner import OllamaPlanner, OllamaSettings
from agentic_web_demo.agents.planning import PlanningError
from agentic_web_demo.cli import main

TODAY = date(2026, 9, 15)


def body(candidate=None):
    return {
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": json.dumps(candidate or decision())},
        "prompt_eval_count": 100,
        "eval_count": 80,
    }


@pytest.fixture
def local_planner():
    clients = []

    def make(payload=None, status=200, error=None):
        calls = []

        def handler(request):
            calls.append(request)
            if error:
                raise error("secret-must-not-leak", request=request)
            return httpx.Response(status, json=body() if payload is None else payload)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return OllamaPlanner(OllamaSettings(), client=client), calls

    yield make
    for client in clients:
        client.close()


def test_request_contract_and_real_graph(local_planner):
    planner, calls = local_planner()
    result = run_workflow("synthetic", planner, FakeTools(), today=TODAY)
    assert result["status"] == "completed" and result["receipts_verified"] == 2
    assert result["model"]["provider"] == "ollama" and result["model_used"]
    assert result["model"]["usage"]["total_tokens"] == 180
    assert len(calls) == 1
    sent = json.loads(calls[0].content)
    assert str(calls[0].url) == "http://127.0.0.1:11434/api/chat"
    assert "authorization" not in calls[0].headers
    assert sent["stream"] is False and sent["think"] is False
    assert sent["options"]["num_ctx"] == 4096
    assert sent["options"]["num_predict"] == 1200
    assert sent["format"]["additionalProperties"] is False
    assert "2026-09-15" in sent["messages"][0]["content"]
    assert "tools" not in sent


@pytest.mark.parametrize(
    "payload,status,code",
    [
        ({"error": "secret-must-not-leak"}, 404, "local_model_missing"),
        ({"error": "secret-must-not-leak"}, 500, "local_service_error"),
        ({}, 302, "local_service_error"),
        ([], 200, "invalid_response"),
        ({**body(), "done": False}, 200, "incomplete"),
        ({**body(), "done_reason": "length"}, 200, "incomplete"),
        ({**body(), "message": {}}, 200, "invalid_response"),
        (
            {**body(), "message": {"role": "assistant", "content": "secret-must-not-leak"}},
            200,
            "invalid_response",
        ),
        (body(decision(shell="never-run")), 200, "invalid_response"),
    ],
)
def test_bad_responses_stop_and_redact(local_planner, payload, status, code):
    planner, calls = local_planner(payload, status)
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools, today=TODAY)
    assert result["status"] == "failed" and result["error_code"] == code
    assert not tools.calls and len(calls) == 1
    assert "secret-must-not-leak" not in json.dumps(result)


@pytest.mark.parametrize(
    "error,code", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "local_connection")]
)
def test_network_failures_do_not_retry(local_planner, error, code):
    planner, calls = local_planner(error=error)
    with pytest.raises(PlanningError, match=code):
        planner.plan("synthetic", TODAY)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change,status",
    [
        ({"city": None}, "needs_input"),
        ({"max_price": "300"}, "policy_rejected"),
        ({"outcome": "unsupported", "reason": "unsupported_task"}, "unsupported"),
        ({"check_out": "2000-01-01"}, "failed"),
    ],
)
def test_validation_still_applies(local_planner, change, status):
    planner, _ = local_planner(body(decision(**change)))
    tools = FakeTools()
    result = run_workflow("synthetic", planner, tools, today=TODAY)
    assert result["status"] == status and not tools.calls


@pytest.mark.parametrize(
    "model", ["qwen3:8b-cloud", "gpt-oss:120b-cloud", "custom", "", "http://x"]
)
def test_only_reviewed_local_models_allowed(model):
    with pytest.raises(ValueError):
        OllamaSettings(model=model)


@pytest.mark.parametrize("timeout", ["nan", "0", "301", "bad"])
def test_timeout_validation(timeout):
    with pytest.raises(ValueError):
        OllamaSettings.from_env({"AGENTIC_OLLAMA_TIMEOUT_SECONDS": timeout})


def test_request_bound_prevents_inference(local_planner):
    planner, calls = local_planner()
    with pytest.raises(PlanningError, match="request_invalid"):
        planner.plan("x" * 2001, TODAY)
    assert not calls


def test_cli_ollama_requires_no_openai_key_or_paid_flag(local_planner, monkeypatch, capsys):
    import agentic_web_demo.agents.ollama_planner as adapter
    from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner

    candidate = decision(**SimulatedPlanner().plan(SCENARIOS["new-york"], date.today()))
    planner, _ = local_planner(body(candidate))
    monkeypatch.setattr(adapter, "OllamaPlanner", lambda settings: planner)
    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("AGENTIC_MODEL_NAME", "qwen3:8b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["langgraph", "--mode", "live", "--request", "synthetic", "--plan-only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "planned" and report["model"]["provider"] == "ollama"


def test_unknown_provider_never_falls_back(monkeypatch):
    monkeypatch.setenv("AGENTIC_MODEL_PROVIDER", "unknown")
    assert main(["langgraph", "--mode", "live", "--request", "synthetic"]) == 2


def test_client_disables_proxies_and_redirects(monkeypatch, local_planner):
    import agentic_web_demo.agents.ollama_planner as adapter

    injected, calls = local_planner()
    settings = {}

    def factory(**kwargs):
        settings.update(kwargs)
        return injected.client

    monkeypatch.setattr(adapter.httpx, "Client", factory)
    OllamaPlanner(OllamaSettings()).plan("synthetic", TODAY)
    assert settings["trust_env"] is False and settings["follow_redirects"] is False
    assert injected.client.is_closed and len(calls) == 1
