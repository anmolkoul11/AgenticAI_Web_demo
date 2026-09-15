"""Checkpoint-4 CLI adapter; reusable rules and messaging live in separate modules."""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import yaml
from nats.errors import Error as NatsError

from agentic_web_demo.events import delivery_status, evaluate_run
from agentic_web_demo.messaging import Broker, consume, publish_pending
from agentic_web_demo.rules import load_rules

COMMANDS = {"evaluate", "publish", "process", "consume", "events-status"}


def add_commands(commands):
    for name in ("evaluate", "publish", "process", "events-status"):
        command = commands.add_parser(name)
        command.add_argument("--run-id", required=True)
        if name in {"evaluate", "process"}:
            command.add_argument(
                "--rules",
                type=Path,
                default=None,
                help="YAML rules; omit for built-in USD 200 / rating 4 defaults",
            )
    receiver = commands.add_parser("consume", help="Receive and persist events until idle or limit")
    receiver.add_argument("--consumer", default="demo-receiver")
    receiver.add_argument("--limit", type=int, default=100)
    receiver.add_argument("--idle-timeout", type=float, default=3)


def run_command(args, data_dir: Path) -> int:
    try:
        if args.command == "events-status":
            result = delivery_status(args.run_id, data_dir)
        elif args.command == "evaluate":
            result = evaluate_run(args.run_id, load_rules(args.rules), data_dir)
        else:
            broker = Broker(url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"))
            if args.command == "consume":
                result = asyncio.run(
                    consume(
                        data_dir,
                        broker,
                        consumer=args.consumer,
                        limit=args.limit,
                        idle_timeout=args.idle_timeout,
                    )
                )
            elif args.command == "process":
                report = evaluate_run(args.run_id, load_rules(args.rules), data_dir)
                result = {
                    "evaluation": report,
                    "delivery": asyncio.run(publish_pending(args.run_id, data_dir, broker)),
                }
            else:
                result = asyncio.run(publish_pending(args.run_id, data_dir, broker))
    except (ValueError, yaml.YAMLError):
        print(
            "Invalid rules, event data, broker settings or run ID. Check the events guide.",
            file=sys.stderr,
        )
        return 1
    except (NatsError, OSError, sqlite3.Error, TimeoutError):
        print(
            "Messaging/storage operation failed. Check Docker/NATS and local permissions. "
            "Unacknowledged outbox events remain retryable with publish --run-id. "
            "Use events-status to inspect partial progress.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2))
    return 1 if args.command == "consume" and result["invalid"] else 0
