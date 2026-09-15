"""NATS JetStream delivery for a loopback-only, single-node demo."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import nats
from nats.errors import TimeoutError as NatsTimeout
from nats.js.api import AckPolicy, ConsumerConfig, StorageType, StreamConfig
from nats.js.errors import NotFoundError
from pydantic import ValidationError

from agentic_web_demo.events import (
    QualifiedEvent,
    mark_published,
    pending_events,
    record_receipt,
)


@dataclass(frozen=True)
class Broker:
    url: str = "nats://127.0.0.1:4222"
    stream: str = "AGENTIC_DEMO"

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if (
            parsed.scheme != "nats"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.port == 0
        ):
            raise ValueError("Only a loopback NATS URL without credentials is supported")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.stream):
            raise ValueError("Invalid stream name")

    @property
    def subject(self):
        return self.stream.lower() + ".listings.qualified.v1"


async def connect(broker: Broker):
    async def safe_error(_error):
        # Surface connection errors to the caller, never print arbitrary URLs or payloads.
        pass

    return await nats.connect(
        broker.url,
        connect_timeout=2,
        allow_reconnect=False,
        max_reconnect_attempts=1,
        reconnect_time_wait=0.1,
        error_cb=safe_error,
    )


async def ensure_stream(js, broker: Broker):
    try:
        info = await js.stream_info(broker.stream)
    except NotFoundError:
        await js.add_stream(
            config=StreamConfig(
                name=broker.stream,
                subjects=[broker.subject],
                storage=StorageType.FILE,
                max_age=86400,
                max_msgs=10000,
                max_bytes=50_000_000,
                duplicate_window=120,
            )
        )
        return
    if info.config.subjects != [broker.subject] or info.config.storage != StorageType.FILE:
        raise ValueError("Existing stream configuration does not match the demo")


async def publish_pending(run_id: str, data_dir: Path, broker: Broker | None = None) -> dict:
    broker = broker or Broker()
    events = pending_events(run_id, data_dir)
    if not events:
        return {"run_id": run_id, "acknowledged": 0, "broker_contacted": False}
    nc = await connect(broker)
    try:
        js = nc.jetstream(timeout=3)
        await ensure_stream(js, broker)
        acknowledged = 0
        for item in events:
            ack = await js.publish(
                broker.subject,
                item.model_dump_json().encode(),
                headers={"Nats-Msg-Id": str(item.event_id)},
                timeout=3,
            )
            mark_published(item, ack.seq, data_dir)
            acknowledged += 1
        return {"run_id": run_id, "acknowledged": acknowledged, "broker_contacted": True}
    finally:
        await nc.close()


async def consume(
    data_dir: Path,
    broker: Broker | None = None,
    *,
    consumer: str = "demo-receiver",
    limit: int = 100,
    idle_timeout: float = 3,
) -> dict:
    broker = broker or Broker()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", consumer) or not 1 <= limit <= 10000:
        raise ValueError("Invalid consumer name or limit")
    if not 0.1 <= idle_timeout <= 60:
        raise ValueError("Idle timeout must be between 0.1 and 60 seconds")
    nc = await connect(broker)
    result = {"received": 0, "duplicates": 0, "invalid": 0, "event_ids": []}
    try:
        js = nc.jetstream(timeout=3)
        await ensure_stream(js, broker)
        sub = await js.pull_subscribe(
            broker.subject,
            durable=consumer,
            stream=broker.stream,
            config=ConsumerConfig(ack_policy=AckPolicy.EXPLICIT, ack_wait=30, max_ack_pending=100),
        )
        for _ in range(limit):
            try:
                messages = await sub.fetch(batch=1, timeout=idle_timeout)
            except NatsTimeout:
                break
            for message in messages:
                try:
                    item = QualifiedEvent.model_validate_json(message.data)
                except ValidationError:
                    # Invalid events cannot become successful receipts. Keep stream data for review.
                    await message.term()
                    result["invalid"] += 1
                    continue
                identity = broker.stream + ":" + consumer
                fresh = record_receipt(item, identity, data_dir)
                await message.ack_sync(timeout=3)
                result["received" if fresh else "duplicates"] += 1
                result["event_ids"].append(str(item.event_id))
        return result
    finally:
        await nc.close()
