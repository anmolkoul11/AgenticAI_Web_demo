"""Adapters for existing tools. Credentials are never passed to a planner or graph state."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from agentic_web_demo.browser import Credentials, extract_listings, portal_origin
from agentic_web_demo.events import delivery_status, evaluate_run
from agentic_web_demo.listings import Snapshot, Stay
from agentic_web_demo.messaging import Broker, consume, publish_pending
from agentic_web_demo.rules import Rules
from agentic_web_demo.storage import export_snapshot, save_snapshot


@dataclass
class DemoTools:
    data_dir: Path
    broker: Broker
    base_url: str = "http://127.0.0.1:8000"
    headed: bool = False

    def __post_init__(self):
        self.base_url = portal_origin(self.base_url)

    def extract(self, stay: Stay) -> Snapshot:
        return extract_listings(
            stay, Credentials.from_env(), base_url=self.base_url, headed=self.headed
        )

    def save(self, snapshot: Snapshot) -> str:
        return save_snapshot(snapshot, self.data_dir)

    def export(self, run_id: str) -> str:
        return str(export_snapshot(run_id, self.data_dir).resolve())

    def evaluate(self, run_id: str, rules: Rules) -> dict:
        return evaluate_run(run_id, rules, self.data_dir)

    def publish(self, run_id: str) -> dict:
        return asyncio.run(publish_pending(run_id, self.data_dir, self.broker))

    def receive(self) -> dict:
        # Reuse the sample receiver. Verification filters receipts to this extraction run.
        return asyncio.run(
            consume(self.data_dir, self.broker, consumer="demo-receiver", limit=100, idle_timeout=1)
        )

    def status(self, run_id: str) -> dict:
        return delivery_status(run_id, self.data_dir)
