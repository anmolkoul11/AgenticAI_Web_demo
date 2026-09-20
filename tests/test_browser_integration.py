"""Real Chromium + Uvicorn tests, explicitly enabled using --run-browser."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import date, timedelta

import httpx
import pytest

from agentic_web_demo.browser import Credentials, ExtractionError, extract_listings
from agentic_web_demo.cli import main
from agentic_web_demo.listings import Stay
from agentic_web_demo.storage import export_snapshot, save_snapshot


@pytest.fixture(scope="module")
def portal(request):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser after installing Chromium")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    password = secrets.token_urlsafe(24)
    env.update(
        DEMO_USERNAME="browser-test",
        DEMO_PASSWORD=password,
        DEMO_SESSION_SECRET=secrets.token_urlsafe(48),
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agentic_web_demo.portal.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            for _ in range(40):
                if process.poll() is not None:
                    pytest.fail("Test portal exited during startup")
                try:
                    if client.get(origin + "/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                pytest.fail("Test portal startup timed out")
        yield origin, Credentials("browser-test", password)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def stay(city):
    start = date.today() + timedelta(days=2)
    return Stay(city=city, check_in=start, check_out=start + timedelta(days=2))


def test_browser_to_sqlite_and_json(portal, tmp_path):
    origin, credentials = portal
    snapshot = extract_listings(stay("New York"), credentials, base_url=origin)
    assert len(snapshot.listings) == 4
    assert {row.listing_id for row in snapshot.listings} == {
        "NYC-001",
        "NYC-002",
        "NYC-003",
        "NYC-004",
    }
    run_id = save_snapshot(snapshot, tmp_path)
    payload = json.loads(export_snapshot(run_id, tmp_path).read_text())
    assert payload["record_count"] == 4
    assert payload["listings"][0]["title"] == "Harbor House"
    assert payload["listings"][0]["price"] == "180"


def test_browser_empty_search(portal):
    origin, credentials = portal
    assert extract_listings(stay("No Such City"), credentials, base_url=origin).listings == ()


def test_browser_wrong_password(portal):
    origin, credentials = portal
    with pytest.raises(ExtractionError, match="Login failed"):
        extract_listings(
            stay("Boston"), Credentials(credentials.username, "wrong-password"), base_url=origin
        )


def test_cli_complete_browser_workflow(portal, tmp_path, monkeypatch, capsys):
    origin, credentials = portal
    monkeypatch.setenv("DEMO_USERNAME", credentials.username)
    monkeypatch.setenv("DEMO_PASSWORD", credentials.password)
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    assert main(["extract", "--base-url", origin, "--city", "Boston"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["record_count"] == 2
    assert credentials.password not in json.dumps(result)
    assert main(["export", "--run-id", result["run_id"]]) == 0


def test_browser_through_rules_to_consumer(portal, request, tmp_path, monkeypatch, capsys):
    if not request.config.getoption("--run-nats"):
        pytest.skip("Full pipeline requires --run-nats as well as --run-browser")
    import asyncio
    from uuid import uuid4

    import agentic_web_demo.event_cli as event_cli
    from agentic_web_demo.messaging import Broker, connect

    broker = Broker(
        url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
        stream="TEST_" + uuid4().hex.upper(),
    )
    monkeypatch.setattr(event_cli, "Broker", lambda **kwargs: broker)
    origin, credentials = portal
    monkeypatch.setenv("DEMO_USERNAME", credentials.username)
    monkeypatch.setenv("DEMO_PASSWORD", credentials.password)
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))

    async def cleanup():
        from nats.js.errors import NotFoundError

        nc = await connect(broker)
        try:
            try:
                await nc.jetstream().delete_stream(broker.stream)
            except NotFoundError:
                pass
        finally:
            await nc.close()

    try:
        assert main(["extract", "--base-url", origin, "--city", "New York"]) == 0
        run = json.loads(capsys.readouterr().out)["run_id"]
        assert main(["process", "--run-id", run]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["evaluation"]["matched"] == 2
        assert result["delivery"]["acknowledged"] == 2
        assert main(["consume", "--idle-timeout", "0.3"]) == 0
        assert json.loads(capsys.readouterr().out)["received"] == 2
        assert main(["events-status", "--run-id", run]) == 0
        state = json.loads(capsys.readouterr().out)
        assert state["published"] == 2 and state["pending"] == 0
        assert len(state["receipts"]) == 2
        assert main(["process", "--run-id", run]) == 0
        assert json.loads(capsys.readouterr().out)["delivery"]["acknowledged"] == 0
    finally:
        asyncio.run(cleanup())


@pytest.mark.parametrize(
    "planner_kind",
    ["simulated", "mocked-openai", "saved-plan", "crewai-saved", "crewai-mocked"],
)
def test_langgraph_simulated_plan_real_tools(portal, request, tmp_path, monkeypatch, planner_kind):
    if not request.config.getoption("--run-nats"):
        pytest.skip("LangGraph real-tool integration requires --run-nats")
    import asyncio
    from uuid import uuid4

    from agentic_web_demo.agents.langgraph_workflow import run_workflow
    from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner
    from agentic_web_demo.agents.tools import DemoTools
    from agentic_web_demo.messaging import Broker, connect

    origin, credentials = portal
    monkeypatch.setenv("DEMO_USERNAME", credentials.username)
    monkeypatch.setenv("DEMO_PASSWORD", credentials.password)
    broker = Broker(
        url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
        stream="TEST_" + uuid4().hex.upper(),
    )
    tools = DemoTools(data_dir=tmp_path, broker=broker, base_url=origin)

    def run_scenario(name):
        if planner_kind in {"saved-plan", "crewai-saved"}:
            from agentic_web_demo.agents.saved_plans import (
                execute_proposal,
                revision,
                save_proposal,
            )
            from agentic_web_demo.rules import Rules

            proposal = save_proposal(
                tmp_path,
                SimulatedPlanner().plan(SCENARIOS[name], date.today()),
                Rules(),
                origin,
                source="structured",
                framework="crewai" if planner_kind == "crewai-saved" else "langgraph",
            )
            return execute_proposal(
                tmp_path,
                str(proposal.plan_id),
                revision(proposal),
                Rules(),
                tools,
                framework=proposal.framework,
            )
        if planner_kind == "simulated":
            return run_workflow(SCENARIOS[name], SimulatedPlanner(), tools)
        from openai import OpenAI
        from test_openai_planner import decision, response_payload

        from agentic_web_demo.agents.openai_planner import ModelSettings, OpenAIPlanner

        candidate = decision(**SimulatedPlanner().plan(SCENARIOS[name], date.today()))
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=response_payload(candidate))
        )
        with OpenAI(
            api_key="fixture-only", max_retries=0, http_client=httpx.Client(transport=transport)
        ) as client:
            planner = OpenAIPlanner(ModelSettings("fixture-model", "fixture-only"), client=client)
            if planner_kind == "crewai-mocked":
                from agentic_web_demo.agents.crewai_planner import CrewAIPlanner
                from agentic_web_demo.agents.crewai_workflow import run_workflow as crew_run

                return crew_run(SCENARIOS[name], CrewAIPlanner(planner), tools)
            return run_workflow(SCENARIOS[name], planner, tools)

    async def cleanup():
        from nats.js.errors import NotFoundError

        nc = await connect(broker)
        try:
            try:
                await nc.jetstream().delete_stream(broker.stream)
            except NotFoundError:
                pass
        finally:
            await nc.close()

    try:
        result = run_scenario("new-york")
        assert result["status"] == "completed"
        assert result["record_count"] == 4
        assert result["evaluation"]["matched"] == 2
        assert result["receipts_verified"] == 2
        assert result["model_used"] is (planner_kind in {"mocked-openai", "crewai-mocked"})
        assert credentials.password not in json.dumps(result)
        result = run_scenario("no-matches")
        assert result["status"] == "completed"
        assert result["record_count"] == 4
        assert result["evaluation"]["matched"] == 0
        assert "publish:ok" not in result["trace"]
    finally:
        asyncio.run(cleanup())


def test_langgraph_live_model_real_tools(
    live_planner, portal, request, tmp_path, monkeypatch, record_property, model_workflow
):
    """Live local/hosted acceptance; OpenAI additionally requires API-use permission."""
    if not request.config.getoption("--run-nats"):
        pytest.skip("Live end-to-end acceptance also requires --run-nats")
    import asyncio
    from uuid import uuid4

    from agentic_web_demo.agents.tools import DemoTools
    from agentic_web_demo.messaging import Broker, connect
    from agentic_web_demo.rules import Rules

    origin, credentials = portal
    monkeypatch.setenv("DEMO_USERNAME", credentials.username)
    monkeypatch.setenv("DEMO_PASSWORD", credentials.password)
    broker = Broker(
        url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
        stream="TEST_" + uuid4().hex.upper(),
    )
    tools = DemoTools(data_dir=tmp_path, broker=broker, base_url=origin)
    start = date.today() + timedelta(days=7)
    end = start + timedelta(days=2)
    prompt = (
        f"Find New York hotels from {start} to {end}, at most USD 200 per night "
        "including taxes and rating at least 4 out of 5."
    )

    async def cleanup():
        from nats.js.errors import NotFoundError

        nc = await connect(broker)
        try:
            try:
                await nc.jetstream().delete_stream(broker.stream)
            except NotFoundError:
                pass
        finally:
            await nc.close()

    try:
        result = model_workflow(prompt, live_planner, tools, policy=Rules())
        record_property("model", live_planner.settings.model)
        record_property("run_id", result.get("run_id", ""))
        record_property("receipts_verified", result.get("receipts_verified", 0))
        assert result["status"] == "completed"
        assert result["model_used"] and result["workflow_verified"]
        assert result["plan"]["city"] == "New York"
        assert result["plan"]["check_in"] == start.isoformat()
        assert result["plan"]["check_out"] == end.isoformat()
        assert result["record_count"] == 4
        assert result["evaluation"]["matched"] == 2
        assert result["receipts_verified"] == 2
        assert credentials.password not in json.dumps(result)
    finally:
        asyncio.run(cleanup())
