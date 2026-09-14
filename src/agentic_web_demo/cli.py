"""Foundation smoke check, not an agent runner or service health check."""

import argparse
import json

from agentic_web_demo.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agentic AI Web Demo starter kit")
    parser.add_argument("command", choices=["status"], help="Show foundation configuration")
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
                    "checkpoint": "1-foundation",
                    "data_dir": str(settings.data_dir),
                    "log_level": settings.log_level,
                    "workflow_implemented": False,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
