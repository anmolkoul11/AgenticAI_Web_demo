"""Real NATS tests use a uniquely owned stream, removed in finally; never purge demo data."""

import asyncio
import os
import socket
from uuid import uuid4

import pytest
from nats.errors import Error as NatsError
from test_rules_events import seeded_run

from agentic_web_demo.events import delivery_status, evaluate_run, pending_events
from agentic_web_demo.messaging import Broker, connect, consume, publish_pending
from agentic_web_demo.rules import Rules


def test_real_delivery_retry_and_consumer_dedup(request, tmp_path):
    if not request.config.getoption("--run-nats"):
        pytest.skip("Use --run-nats with local JetStream running")

    async def scenario():
        broker = Broker(
            url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"),
            stream="TEST_" + uuid4().hex.upper(),
        )
        nc = await connect(broker)
        js = nc.jetstream()
        try:
            run = seeded_run(tmp_path)
            evaluate_run(run, Rules(), tmp_path)
            original = pending_events(run, tmp_path)
            assert (await publish_pending(run, tmp_path, broker))["acknowledged"] == 2
            assert (await publish_pending(run, tmp_path, broker))["acknowledged"] == 0
            assert (await js.stream_info(broker.stream)).state.messages == 2
            result = await consume(tmp_path, broker, idle_timeout=0.3)
            assert result["received"] == 2
            assert len(delivery_status(run, tmp_path)["receipts"]) == 2
            # Inject a redelivery-like duplicate without a broker deduplication header.
            await js.publish(broker.subject, original[0].model_dump_json().encode())
            duplicate = await consume(tmp_path, broker, idle_timeout=0.3)
            assert duplicate["duplicates"] == 1
            assert duplicate["received"] == 0
            assert len(delivery_status(run, tmp_path)["receipts"]) == 2
            await js.publish(broker.subject, b"not-a-valid-event")
            assert (await consume(tmp_path, broker, idle_timeout=0.3))["invalid"] == 1
        finally:
            try:
                await js.delete_stream(broker.stream)
            finally:
                await nc.close()

    asyncio.run(scenario())


def test_broker_unavailable_preserves_pending(tmp_path):
    # A bound but non-listening local socket gives a deterministic refused connection.
    run = seeded_run(tmp_path)
    evaluate_run(run, Rules(), tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        with pytest.raises(NatsError):
            asyncio.run(publish_pending(run, tmp_path, Broker(url=f"nats://127.0.0.1:{port}")))
    status = delivery_status(run, tmp_path)
    assert status["pending"] == 2
    assert status["published"] == 0
