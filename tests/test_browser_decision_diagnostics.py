"""Offline response/error regression cases. No external network or browser required."""

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI, pydantic_function_tool
from test_browser_agent import FakeDecider, FakeTools, decision

from agentic_web_demo import browser_agent
from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserDecision,
    DecisionFailure,
    OpenAIBrowserDecider,
    safe_decision_metadata,
    safe_validation_issues,
)
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.service import DashboardService


@pytest.fixture(autouse=True)
def close_owned_test_deciders(monkeypatch):
    """Persistent SDK clients in offline cases must not leak between tests."""
    initialized = []
    initialize = OpenAIBrowserDecider.__init__

    def track(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        initialized.append(self)

    monkeypatch.setattr(OpenAIBrowserDecider, "__init__", track)
    yield
    for decider in initialized:
        decider.close()


def response_body(*, status="completed", text=None, reason=None, refusal=False):
    content = (
        [{"type": "refusal", "refusal": "private-provider-text"}]
        if refusal
        else [
            {
                "type": "output_text",
                "text": text or decision("pause").model_dump_json(),
                "annotations": [],
            }
        ]
    )
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "fixture-model",
        "output": [
            {
                "type": "message",
                "id": "msg_fixture",
                "role": "assistant",
                "status": status,
                "content": content,
            }
        ],
        "incomplete_details": {"reason": reason} if reason else None,
        "error": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


def mocked_decider(monkeypatch, handler):
    calls = []

    def respond(request):
        calls.append(request)
        return handler(request)

    def client(**kwargs):
        kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(respond))
        return OpenAI(**kwargs)

    monkeypatch.setattr(browser_agent, "OpenAI", client)
    settings = SimpleNamespace(
        api_key="fixture-only-key",
        model="fixture-model",
        max_output_tokens=1200,
        timeout_seconds=60,
    )
    return OpenAIBrowserDecider(settings), calls


def test_completed_response_uses_strict_schema_and_collects_metadata(monkeypatch):
    model, calls = mocked_decider(
        monkeypatch,
        lambda _: httpx.Response(
            200, json=response_body(), headers={"x-request-id": "req_fixture"}
        ),
    )
    assert model.decide({"task": "Read source"}, 60).action == "pause"
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["store"] is False and payload["max_output_tokens"] == 1200
    assert (
        payload["text"]["format"]["schema"]
        == pydantic_function_tool(BrowserDecision)["function"]["parameters"]
    )
    assert payload["text"]["format"]["strict"] is True
    assert "tools" not in payload
    assert model.last_decision["decision_valid"]
    assert model.last_decision["request_id"] == "req_fixture"
    assert model.usage["total_tokens"] == 120
    assert model.last_decision["usage"]["reasoning_tokens"] == 5
    assert model.last_decision["input_chars"] == len(
        json.dumps({"task": "Read source"}, separators=(",", ":"))
    )


def test_cached_input_is_measured_as_a_subset_not_added_to_total(monkeypatch):
    body = response_body()
    body["usage"]["input_tokens_details"]["cached_tokens"] = 40
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    model.decide({"task": "Read source"}, 60)
    model.decide({"task": "Read source again"}, 60)
    assert len(calls) == 2
    assert model.usage == {
        "input_tokens": 200,
        "output_tokens": 40,
        "total_tokens": 240,
        "cached_input_tokens": 80,
    }
    assert model.last_decision["usage"]["cached_input_tokens"] == 40
    assert safe_decision_metadata(model.last_decision)["usage"]["cached_input_tokens"] == 40
    assert model.last_decision["system_chars"] > 0
    assert model.last_decision["schema_chars"] > 0


def test_decision_schema_discourages_repeating_the_whole_checklist():
    schema = BrowserDecision.model_json_schema()
    assert schema["properties"]["requirements"]["maxItems"] == 3
    assert schema["properties"]["explanation"]["maxLength"] == 160
    assert schema["properties"]["evidence"]["maxLength"] == 220


def test_two_decisions_reuse_one_client_and_recompute_request_timeout(monkeypatch):
    constructions, closes, calls, schemas = [], [], [], []
    schema_factory = browser_agent.pydantic_function_tool

    def schema_once(*args, **kwargs):
        schemas.append(args[0])
        return schema_factory(*args, **kwargs)

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=response_body())

    def client(**kwargs):
        kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(respond))
        owned = OpenAI(**kwargs)
        real_close = owned.close

        def counted_close():
            closes.append(owned)
            real_close()

        monkeypatch.setattr(owned, "close", counted_close)
        constructions.append(owned)
        return owned

    monkeypatch.setattr(browser_agent, "pydantic_function_tool", schema_once)
    monkeypatch.setattr(browser_agent, "OpenAI", client)
    model = OpenAIBrowserDecider(
        SimpleNamespace(
            api_key="fixture-only",
            model="fixture-model",
            max_output_tokens=1200,
            timeout_seconds=60,
        )
    )
    assert constructions == [] and schemas == [BrowserDecision]
    assert model.decide({"task": "Read source"}, 60).action == "pause"
    assert model.decide({"task": "Read source again"}, 7.5).action == "pause"
    assert len(constructions) == 1 and closes == [] and len(calls) == 2
    assert schemas == [BrowserDecision]
    for request, timeout in zip(calls, [60, 7.5], strict=True):
        assert request.extensions["timeout"] == {
            "connect": timeout,
            "read": timeout,
            "write": timeout,
            "pool": timeout,
        }
    assert model.last_decision["timeout_seconds"] == 7.5
    assert model.usage["total_tokens"] == 240
    model.close()
    model.close()
    assert closes == constructions and constructions[0].is_closed()
    with pytest.raises(WebsiteError, match="closed"):
        model.decide({"task": "Do not reopen"}, 60)
    assert len(constructions) == 1 and len(calls) == 2


def test_separate_deciders_do_not_share_clients_or_cleanup(monkeypatch):
    clients, calls = [], []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=response_body())

    def client(**kwargs):
        kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(respond))
        result = OpenAI(**kwargs)
        clients.append(result)
        return result

    monkeypatch.setattr(browser_agent, "OpenAI", client)
    settings = SimpleNamespace(
        api_key="fixture-only",
        model="fixture-model",
        max_output_tokens=1200,
        timeout_seconds=60,
    )
    first, second = OpenAIBrowserDecider(settings), OpenAIBrowserDecider(settings)
    first.decide({"task": "First session"}, 60)
    second.decide({"task": "Second session"}, 60)
    assert len(clients) == 2 and clients[0] is not clients[1]
    first.close()
    assert clients[0].is_closed() and not clients[1].is_closed()
    second.decide({"task": "Second session continues"}, 10)
    assert len(clients) == 2 and len(calls) == 3
    second.close()
    assert clients[1].is_closed()


def test_closing_unused_decider_does_not_construct_client(monkeypatch):
    def forbidden(**_):
        pytest.fail("Closing an unused decider must not create an SDK client")

    monkeypatch.setattr(browser_agent, "OpenAI", forbidden)
    model = OpenAIBrowserDecider(
        SimpleNamespace(api_key="fixture-only", model="fixture-model", max_output_tokens=1200)
    )
    model.close()
    model.close()
    with pytest.raises(WebsiteError, match="closed"):
        model.decide({"task": "No request"}, 60)


def test_failed_sdk_construction_closes_its_unclaimed_http_client(monkeypatch):
    closed = []
    monkeypatch.setattr(
        browser_agent.httpx,
        "Client",
        lambda **_: SimpleNamespace(close=lambda: closed.append(True)),
    )

    def fail(**_):
        raise TypeError("fixture constructor failure")

    monkeypatch.setattr(browser_agent, "OpenAI", fail)
    model = OpenAIBrowserDecider(
        SimpleNamespace(api_key="fixture-only", model="fixture-model", max_output_tokens=1200)
    )
    with pytest.raises(TypeError, match="fixture constructor failure"):
        model.decide({"task": "Read source"}, 60)
    assert closed == [True]
    model.close()
    assert closed == [True]


def test_reused_client_failure_has_no_automatic_retry_or_stale_usage(monkeypatch):
    attempts = 0

    def respond(_):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            return httpx.Response(
                429,
                json={"error": {"code": "rate_limit_exceeded", "message": "private"}},
            )
        return httpx.Response(200, json=response_body())

    model, calls = mocked_decider(monkeypatch, respond)
    model.decide({"task": "Read source"}, 60)
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source again"}, 7.5)
    assert failure.value.code == "rate_limit" and attempts == len(calls) == 2
    assert model.usage["total_tokens"] == 120
    assert model.last_decision["timeout_seconds"] == 7.5
    assert "usage" not in model.last_decision
    assert not model.last_decision["response_received"]
    # An explicit later decision, not an SDK retry, can reuse the same session.
    model.decide({"task": "Explicit retry after attention"}, 5)
    assert attempts == len(calls) == 3 and model.usage["total_tokens"] == 240


@pytest.mark.parametrize(
    "status,reason,text,refusal,expected",
    [
        ("incomplete", "max_output_tokens", '{"action":', False, "output_limit"),
        ("incomplete", "content_filter", '{"action":', False, "content_filter"),
        ("incomplete", None, '{"action":', False, "incomplete"),
        ("failed", None, '{"action":', False, "response_failed"),
        ("completed", None, '{"action":', False, "invalid_decision"),
        ("completed", None, '{"action":"invented"}', False, "invalid_decision"),
        ("completed", None, None, True, "refusal"),
    ],
)
def test_response_failure_is_specific_and_preserves_usage(
    monkeypatch, status, reason, text, refusal, expected
):
    model, calls = mocked_decider(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=response_body(status=status, reason=reason, text=text, refusal=refusal),
        ),
    )
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == expected
    assert len(calls) == 1
    assert model.last_decision["response_received"]
    assert not model.last_decision["decision_valid"]
    assert model.last_decision["usage"]["total_tokens"] == 120
    assert "private-provider-text" not in json.dumps(model.last_decision)


def test_incomplete_json_is_not_parsed(monkeypatch):
    model, _ = mocked_decider(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=response_body(status="incomplete", reason="max_output_tokens", text="{"),
        ),
    )

    def forbidden(*_):
        pytest.fail("Incomplete output must never reach decision parsing")

    monkeypatch.setattr(BrowserDecision, "model_validate_json", forbidden)
    with pytest.raises(DecisionFailure, match="output-token limit"):
        model.decide({"task": "Read source"}, 60)


def test_missing_output_is_not_a_success(monkeypatch):
    body = response_body()
    body["output"] = []
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "missing_output" and len(calls) == 1


@pytest.mark.parametrize(
    "status,provider_code,expected",
    [
        (401, "invalid_api_key", "authentication"),
        (403, "permission_denied", "authentication"),
        (429, "rate_limit_exceeded", "rate_limit"),
        (429, "insufficient_quota", "quota"),
        (400, "invalid_request_error", "request_invalid"),
        (500, "server_error", "api_error"),
    ],
)
def test_api_errors_do_not_leak_provider_body_or_retry(
    monkeypatch, status, provider_code, expected
):
    model, calls = mocked_decider(
        monkeypatch,
        lambda _: httpx.Response(
            status,
            json={
                "error": {
                    "message": "fixture-only-key private-body",
                    "type": "error",
                    "code": provider_code,
                }
            },
        ),
    )
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == expected and len(calls) == 1
    assert model.last_decision["http_status"] == status
    assert "fixture-only-key" not in str(failure.value)
    assert "private-body" not in json.dumps(model.last_decision)
    if expected == "authentication":
        guidance = str(failure.value)
        assert "API connection" in guidance and "re-paste the complete key" in guidance
        assert "active" in guidance and "expired, revoked or invalid" in guidance
        assert "another active OpenAI API key" in guidance
        assert "start a fresh workflow" in guidance and "Resume retains the old connection" in guidance
        assert "permissions and IP restrictions" in guidance
        assert "No action ran from this decision; no automatic retry" in guidance


@pytest.mark.parametrize(
    "error,expected",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")],
)
def test_transport_failures_do_not_retry(monkeypatch, error, expected):
    def fail(request):
        raise error("private transport text", request=request)

    model, calls = mocked_decider(monkeypatch, fail)
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == expected and len(calls) == 1
    assert not model.last_decision["response_received"]
    assert "private transport text" not in str(failure.value)


def test_graph_preserves_failed_call_budget_and_requires_explicit_resume(monkeypatch):
    attempts = 0

    def respond(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            json=response_body(
                status="incomplete" if attempts == 1 else "completed",
                reason="max_output_tokens" if attempts == 1 else None,
                text="{" if attempts == 1 else None,
            ),
        )

    model, calls = mocked_decider(monkeypatch, respond)
    tools = FakeTools()
    agent = BrowserAgent(tools, model, "Read visible source")
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == len(calls) == 1
    assert report["failure"] == {
        "code": "output_limit",
        "stage": "decide",
        "call": 1,
        "no_action_from_failed_decision": True,
    }
    assert tools.events == ["observe"] and not report["actions"]
    assert report["usage"]["total_tokens"] == 120
    assert report["decision_diagnostics"][0]["timeout_seconds"] == 60
    resumed = agent.run()
    assert resumed["calls"] == len(calls) == 2 and resumed["failure"] is None
    assert len(resumed["decision_diagnostics"]) == 2
    assert resumed["decision_diagnostics"][0]["error_code"] == "output_limit"
    second_payload = json.loads(calls[1].content)
    context = json.loads(second_payload["input"][1]["content"])
    assert context["previous_decision_failure"]["error_code"] == "output_limit"
    assert context["loop_contract"]["fresh_observation"] is True


def test_timeout_is_bounded_by_remaining_active_time(monkeypatch):
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=response_body()))
    agent = BrowserAgent(FakeTools(), model, "Read visible source", max_seconds=20)
    report = agent.run()
    assert 0 < report["decision_diagnostics"][0]["timeout_seconds"] <= 20


def test_successful_decision_clears_previous_failure_feedback(monkeypatch):
    attempts = 0

    def respond(_):
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            json=response_body(
                status="incomplete" if attempts == 1 else "completed",
                reason="max_output_tokens" if attempts == 1 else None,
                text="{"
                if attempts == 1
                else decision("wait" if attempts == 2 else "pause").model_dump_json(),
            ),
        )

    model, calls = mocked_decider(monkeypatch, respond)
    agent = BrowserAgent(FakeTools(), model, "Read visible source")
    assert agent.run()["status"] == "paused"
    assert agent.run()["calls"] == 3
    resumed_context = json.loads(json.loads(calls[1].content)["input"][1]["content"])
    next_context = json.loads(json.loads(calls[2].content)["input"][1]["content"])
    assert resumed_context["previous_decision_failure"]["error_code"] == "output_limit"
    assert next_context["previous_decision_failure"] is None


def test_unexpected_local_error_is_not_reported_as_api_quota_failure():
    class BrokenDecider:
        def decide(self, *_args, **_kwargs):
            raise TypeError("private SDK implementation text")

    tools = FakeTools()
    report = BrowserAgent(tools, BrokenDecider(), "Read visible source").run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert report["failure"]["code"] == "internal_error"
    assert report["failure"]["stage"] == "decide"
    assert tools.events == ["observe"]
    assert "private SDK implementation text" not in json.dumps(report)


def test_commentary_is_not_concatenated_with_final_decision(monkeypatch):
    body = response_body()
    final = body["output"][0]
    final["phase"] = "final_answer"
    commentary = {
        **final,
        "id": "msg_commentary",
        "phase": "commentary",
        "content": [
            {
                "type": "output_text",
                "text": "private intermediate progress text",
                "annotations": [],
            }
        ],
    }
    body["output"] = [commentary, final]
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    assert model.decide({"task": "Read source"}, 60).action == "pause"
    assert len(calls) == 1
    assert model.last_decision["message_count"] == 2
    assert model.last_decision["commentary_count"] == 1
    assert model.last_decision["decision_phase"] == "final_answer"
    assert "private intermediate progress text" not in json.dumps(model.last_decision)


@pytest.mark.parametrize("phase", [None, "final_answer"])
def test_two_possible_decisions_are_not_arbitrarily_selected(monkeypatch, phase):
    body = response_body()
    first = body["output"][0]
    first["phase"] = phase
    second = {
        **first,
        "id": "msg_second",
        "content": [
            {
                "type": "output_text",
                "text": decision("wait").model_dump_json(),
                "annotations": [],
            }
        ],
    }
    body["output"].append(second)
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "ambiguous_output" and len(calls) == 1
    assert model.last_decision["validation_issues"] == [
        {"field": "decision", "code": "multiple_decisions"}
    ]


@pytest.mark.parametrize("phase", [None, "final_answer"])
def test_duplicate_identical_decisions_execute_once(monkeypatch, phase):
    body = response_body()
    first = body["output"][0]
    first["phase"] = phase
    body["output"].append({**first, "id": "msg_second"})
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    report = BrowserAgent(FakeTools(), model, "Read visible source").run()
    assert report["calls"] == len(calls) == 1
    assert len(report["actions"]) == 1 and report["actions"][0]["action"] == "pause"
    assert report["failure"] is None
    assert model.last_decision["duplicate_decisions"] == 1
    assert model.last_decision["unique_decision_count"] == 1


def test_final_progress_prose_does_not_hide_unique_schema_decision(monkeypatch):
    body = response_body()
    final = body["output"][0]
    final["phase"] = "final_answer"
    body["output"].insert(
        0,
        {
            **final,
            "id": "msg_progress",
            "content": [
                {
                    "type": "output_text",
                    "text": "private progress prose",
                    "annotations": [],
                }
            ],
        },
    )
    model, calls = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    assert model.decide({"task": "Read source"}, 60).action == "pause"
    assert len(calls) == 1 and model.last_decision["ignored_text_messages"] == 1
    assert "private progress prose" not in json.dumps(model.last_decision)


@pytest.mark.parametrize(
    "malformed", ['{"action":', '[{"action":"click"}]', '```json\n{"action":"click"}\n```']
)
def test_invalid_json_like_alternative_is_not_discarded(monkeypatch, malformed):
    body = response_body()
    body["output"].append(
        {
            **body["output"][0],
            "id": "msg_other",
            "content": [
                {
                    "type": "output_text",
                    "text": malformed,
                    "annotations": [],
                }
            ],
        }
    )
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "invalid_decision"


@pytest.mark.parametrize("refusal,expected", [(True, "refusal"), (False, "incomplete")])
def test_unfinished_or_refused_alternative_cannot_be_hidden_by_valid_decision(
    monkeypatch, refusal, expected
):
    body = response_body()
    other = response_body(refusal=refusal)["output"][0]
    other["id"] = "msg_other"
    if not refusal:
        other["status"] = "incomplete"
    body["output"].append(other)
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == expected


def test_safe_selection_counts_survive_report_without_message_contents(monkeypatch):
    body = response_body()
    body["output"].append({**body["output"][0], "id": "msg_second"})
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    report = BrowserAgent(FakeTools(), model, "Read visible source").run()
    diagnostic = report["decision_diagnostics"][0]
    assert diagnostic["validated_decision_count"] == 2
    assert diagnostic["unique_decision_count"] == diagnostic["duplicate_decisions"] == 1
    assert "output_text" not in diagnostic and "content" not in diagnostic


def test_observation_request_continues_without_user_resume():
    tools = FakeTools()
    model = FakeDecider(
        [
            decision("pause", pause_reason="observation", value="dialog"),
            decision("fill", "0:0", "science"),
            decision("finish"),
        ]
    )
    report = BrowserAgent(tools, model, "Read visible source").run()
    assert report["status"] == "ready" and report["calls"] == 3
    assert tools.events == ["observe", "inspect", "observe", "fill", "observe", "capture"]
    refresh = report["actions"][0]
    assert refresh["action"] == "inspect" and refresh["requested_action"] == "pause"
    assert refresh["continuation"] == "observation_refresh"
    assert model.payloads[1]["observation"]["version"] == 1
    assert model.payloads[1]["loop_contract"]["observation_refresh_needs_human"] is False


@pytest.mark.parametrize(
    "reason",
    ["none", "user_input", "authentication", "access_restriction", "ambiguous_choice", "blocked"],
)
def test_real_human_handoff_is_not_overridden(reason):
    tools = FakeTools()
    report = BrowserAgent(
        tools, FakeDecider([decision("pause", pause_reason=reason)]), "Read visible source"
    ).run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events == ["observe"]
    assert report["actions"][0]["pause_reason"] == reason


def test_observation_refresh_stops_on_mfa_before_another_model_call():
    tools = FakeTools()
    execute = tools.execute

    def reveal_mfa(action):
        result = execute(action)
        tools.password = True
        return result

    tools.execute = reveal_mfa
    report = BrowserAgent(
        tools, FakeDecider([decision("pause", pause_reason="observation")]), "Read visible source"
    ).run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert tools.events == ["observe", "inspect", "observe"]
    assert "MFA" in report["guidance"]


def test_cancellation_after_refresh_prevents_another_paid_decision():
    tools = FakeTools()
    execute = tools.execute

    def cancel(action):
        result = execute(action)
        tools.allowed = False
        return result

    tools.execute = cancel
    model = FakeDecider([decision("pause", pause_reason="observation")])
    report = BrowserAgent(tools, model, "Read visible source").run()
    assert report["status"] == "paused" and report["calls"] == len(model.payloads) == 1
    assert tools.events == ["observe", "inspect"]


def test_unchanged_observation_requests_are_bounded():
    tools = FakeTools()
    model = FakeDecider([decision("pause", pause_reason="observation") for _ in range(3)])
    report = BrowserAgent(tools, model, "Read visible source").run()
    assert report["status"] == "paused" and report["calls"] == 3
    assert tools.events.count("inspect") == 2
    assert report["actions"][-1]["status"] == "observation_stalled"
    assert not tools.pages


def test_observation_continuation_does_not_reset_paid_budget():
    tools = FakeTools()
    model = FakeDecider([decision("pause", pause_reason="observation")])
    agent = BrowserAgent(tools, model, "Read visible source", max_calls=1)
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == 1
    assert "model-call limit" in report["guidance"]
    assert tools.events == ["observe", "inspect", "observe"]


def test_commentary_alone_is_not_an_executable_decision(monkeypatch):
    body = response_body()
    body["output"][0]["phase"] = "commentary"
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "missing_output"


def test_unfinished_final_message_is_not_executed(monkeypatch):
    body = response_body()
    body["output"][0]["status"] = "incomplete"
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "incomplete"


def test_multiple_text_blocks_are_not_combined_into_action_json(monkeypatch):
    body = response_body()
    content = body["output"][0]["content"]
    content.append({"type": "output_text", "text": "private trailing text", "annotations": []})
    model, _ = mocked_decider(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(DecisionFailure) as failure:
        model.decide({"task": "Read source"}, 60)
    assert failure.value.code == "ambiguous_output"
    assert model.last_decision["validation_issues"][0]["code"] == "multiple_text_blocks"


def test_schema_rejection_reports_field_and_code_without_values(monkeypatch):
    malformed = decision("pause").model_dump()
    malformed["requirements"] = [
        {
            "name": "adults",
            "expected": 3,
            "application": "form",
            "request_quote": "private page/request text",
        }
    ]
    model, _ = mocked_decider(
        monkeypatch,
        lambda _: httpx.Response(200, json=response_body(text=json.dumps(malformed))),
    )
    tools = FakeTools()
    report = BrowserAgent(tools, model, "Read source").run()
    diagnostic = report["decision_diagnostics"][0]
    assert diagnostic["validation_issues"] == [
        {"field": "requirements.0.expected", "code": "string_type"}
    ]
    assert report["failure"]["code"] == "invalid_decision"
    assert tools.events == ["observe"]
    assert "private page/request text" not in json.dumps(report)


def test_validation_issues_never_store_unknown_property_names():
    from pydantic import ValidationError

    malformed = decision("pause").model_dump()
    malformed["private-credential-shaped-key"] = "private value"
    with pytest.raises(ValidationError) as failure:
        BrowserDecision.model_validate(malformed)
    issues = safe_validation_issues(failure.value)
    assert issues == [{"field": "unexpected_field", "code": "extra_forbidden"}]
    assert "private" not in json.dumps(issues)


def test_safe_metadata_whitelists_only_schema_validation_paths():
    result = safe_decision_metadata(
        {
            "validation_issues": [
                {
                    "field": "requirements.0.expected",
                    "code": "string_type",
                    "input": "private",
                },
                {"field": "private-field", "code": "string_type"},
                {"field": "value", "code": "private-provider-text"},
            ]
        }
    )
    assert result["validation_issues"] == [
        {"field": "requirements.0.expected", "code": "string_type"}
    ]
    assert "private" not in json.dumps(result)


def test_safe_metadata_does_not_retain_arbitrary_text():
    safe = safe_decision_metadata(
        {
            "status": ["hostile"],
            "response_status": "completed",
            "error_code": "private error text",
            "output_text": "private page text",
            "viewport_image": "data:image/jpeg;base64,private",
            "request_id": "private",
            "usage": {"input_tokens": 5, "total_tokens": -1, "secret": "private"},
            "max_output_tokens": True,
        }
    )
    assert safe == {"response_status": "completed", "usage": {"input_tokens": 5}}


def test_live_diagnostics_survive_progress_final_write_and_restart(tmp_path):
    service = DashboardService(tmp_path, tmp_path / "rules.yaml", "http://127.0.0.1:8000")
    job = {"job_id": str(uuid4()), "status": "running", "stages": []}
    try:
        service.write(job)
        control = BrowserControl()
        control.on_agent_diagnostics = lambda data: service.remember_agent_diagnostics(
            job["job_id"], data
        )

        def publish(calls, status, failure):
            control.set_agent_report(
                {
                    "run_id": "fixture",
                    "prompt_version": "browser-agent-v6",
                    "status": status,
                    "guidance": "Review",
                    "calls": calls,
                    "failure": failure,
                    "decision_diagnostics": [{"call": calls}],
                    "actions": [{"evidence": "private source"}],
                    "viewport_image": "private image",
                }
            )

        publish(1, "paused", {"code": "output_limit"})
        service.write(job)
        publish(2, "paused", {"code": "timeout"})
        job["status"] = "interrupted"
        service.write(job)
        saved = service.read(job["job_id"])["browser_agent_diagnostics"]
        assert saved["calls"] == 2 and saved["failure"]["code"] == "timeout"
        assert "private" not in json.dumps(saved)
    finally:
        service.close()
    restarted = DashboardService(tmp_path, tmp_path / "rules.yaml", "http://127.0.0.1:8000")
    try:
        assert restarted.read(job["job_id"])["browser_agent_diagnostics"] == saved
    finally:
        restarted.close()
