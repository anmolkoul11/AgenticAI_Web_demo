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
