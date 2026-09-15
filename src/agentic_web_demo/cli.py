"""Local demo commands. No paid model calls, external scraping or event publishing."""

import argparse
import json
import sqlite3
import sys
from datetime import date, timedelta

from pydantic import ValidationError

from agentic_web_demo.browser import Credentials, ExtractionError, extract_listings
from agentic_web_demo.config import Settings
from agentic_web_demo.event_cli import COMMANDS, add_commands, run_command
from agentic_web_demo.listings import Stay
from agentic_web_demo.storage import export_snapshot, save_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agentic AI Web Demo starter kit")
    commands = parser.add_subparsers(dest="command", required=True)
    add_commands(commands)
    commands.add_parser("status", help="Show implemented checkpoint, not service health")
    extract = commands.add_parser("extract", help="Log in, extract, validate, save and export")
    extract.add_argument("--city", default="")
    extract.add_argument("--check-in", default=(date.today() + timedelta(days=1)).isoformat())
    extract.add_argument("--check-out", default=(date.today() + timedelta(days=2)).isoformat())
    extract.add_argument("--base-url", default="http://127.0.0.1:8000")
    extract.add_argument("--headed", action="store_true", help="Show the browser during extraction")
    export = commands.add_parser(
        "export", help="Recreate a JSON export from an existing stored run"
    )
    export.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "status":
        print(
            json.dumps(
                {
                    "project": "AgenticAI_Web_demo",
                    "checkpoint": "4-rules-events",
                    "data_dir": str(settings.data_dir),
                    "log_level": settings.log_level,
                    "workflow_implemented": False,
                },
                indent=2,
            )
        )
        return 0
    if args.command in COMMANDS:
        return run_command(args, settings.data_dir)
    try:
        if args.command == "export":
            path = export_snapshot(args.run_id, settings.data_dir)
            print(json.dumps({"export_path": str(path.resolve())}, indent=2))
            return 0
        stay = Stay(city=args.city, check_in=args.check_in, check_out=args.check_out)
        stay.require_current_dates()
        snapshot = extract_listings(
            stay, Credentials.from_env(), base_url=args.base_url, headed=args.headed
        )
        run_id = save_snapshot(snapshot, settings.data_dir)
    except ExtractionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (ValidationError, ValueError):
        print(
            "Invalid dates, configuration, stored records or run ID. Check the guide.",
            file=sys.stderr,
        )
        return 1
    except (OSError, sqlite3.Error):
        print(
            "Local storage operation failed. Check permissions and available disk space.",
            file=sys.stderr,
        )
        return 1
    try:
        path = export_snapshot(run_id, settings.data_dir)
    except (OSError, sqlite3.Error, ValueError):
        print(
            f"Run {run_id} is saved in SQLite, but JSON export failed. "
            f"Retry: agentic-demo export --run-id {run_id}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "run_id": run_id,
                "record_count": len(snapshot.listings),
                "database_path": str((settings.data_dir / "listings.sqlite3").resolve()),
                "export_path": str(path.resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
