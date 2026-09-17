"""Explicit simulated/live modes; no implicit paid model calls or provider fallback."""

import json
import os
import sys
from pathlib import Path

from agentic_web_demo.agents.planning import SCENARIOS, SimulatedPlanner


def add_command(commands):
    command = commands.add_parser("langgraph", help="Run the bounded LangGraph hotel workflow")
    command.add_argument("action", nargs="?", choices=["plan", "review", "execute"])
    command.add_argument("--mode", choices=["simulated", "live"])
    command.add_argument("--city")
    command.add_argument("--all-cities", action="store_true")
    command.add_argument("--check-in")
    command.add_argument("--check-out")
    command.add_argument("--max-price")
    command.add_argument("--min-rating")
    command.add_argument("--adapter", default="demo-hotels")
    command.add_argument("--plan-id")
    command.add_argument("--approve", help="Exact SHA-256 revision displayed by review")
    source = command.add_mutually_exclusive_group()
    source.add_argument("--scenario", choices=list(SCENARIOS))
    source.add_argument("--request", help="Synthetic natural-language request (live mode only)")
    command.add_argument("--list-scenarios", action="store_true")
    command.add_argument(
        "--allow-model-api",
        action="store_true",
        help="Explicitly permit sending the request to the paid model API",
    )
    command.add_argument("--plan-only", action="store_true", help="Validate plan, run no tools")
    command.add_argument(
        "--policy",
        type=Path,
        help="Policy YAML; live default config/rules.yaml, simulated default none",
    )
    command.add_argument("--base-url")
    command.add_argument("--headed", action="store_true")


def run_command(args, data_dir: Path) -> int:
    if args.action:
        from agentic_web_demo.agents.plan_commands import run_saved_command

        return run_saved_command(args, data_dir)
    if args.mode is None:
        print("Choose plan/review/execute or an explicit legacy --mode.", file=sys.stderr)
        raise SystemExit(2)
    if (
        any(
            value is not None
            for value in [
                args.city,
                args.check_in,
                args.check_out,
                args.max_price,
                args.min_rating,
                args.plan_id,
                args.approve,
            ]
        )
        or args.all_cities
        or args.adapter != "demo-hotels"
    ):
        print("Saved-plan fields require plan/review/execute.", file=sys.stderr)
        return 2
    provider = os.environ.get("AGENTIC_MODEL_PROVIDER", "openai")
    if args.mode == "live" and provider not in {"openai", "ollama"}:
        print(
            "Unsupported model provider; choose openai or ollama. No fallback is used.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "simulated" and (args.request is not None or args.allow_model_api):
        print(
            "Simulated mode accepts bundled scenarios, not --request or --allow-model-api.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "live" and (
        (provider == "openai" and not args.allow_model_api)
        or args.scenario is not None
        or args.list_scenarios
        or args.request is None
        or not args.request.strip()
        or len(args.request) > 2000
    ):
        print(
            "Live mode requires a nonempty --request (max 2000 characters). "
            "OpenAI additionally requires --allow-model-api. "
            "Do not use --scenario/--list-scenarios. Use synthetic data only.",
            file=sys.stderr,
        )
        return 2
    if args.list_scenarios:
        print(json.dumps({"mode": "simulated", "scenarios": SCENARIOS}, indent=2))
        return 0
    from agentic_web_demo.agents.langgraph_workflow import run_workflow
    from agentic_web_demo.agents.tools import DemoTools
    from agentic_web_demo.messaging import Broker
    from agentic_web_demo.rules import load_rules

    try:
        policy_path = args.policy
        if args.mode == "live":
            policy_path = policy_path or Path("config/rules.yaml")
        policy = load_rules(policy_path) if policy_path is not None else None
        tools = DemoTools(
            data_dir=data_dir,
            base_url=args.base_url or "http://127.0.0.1:8000",
            headed=args.headed,
            broker=Broker(url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222")),
        )
        if args.mode == "live":
            request = args.request
            if provider == "ollama":
                from agentic_web_demo.agents.ollama_planner import (
                    OllamaPlanner,
                    OllamaSettings,
                )

                planner = OllamaPlanner(OllamaSettings.from_env())
                print(
                    "LIVE LOCAL PLANNING: Ollama on localhost; no hosted API calls.",
                    file=sys.stderr,
                )
            else:
                from agentic_web_demo.agents.openai_planner import (
                    ModelSettings,
                    OpenAIPlanner,
                )

                planner = OpenAIPlanner(ModelSettings.from_env())
                print(
                    "LIVE PLANNING: request sent to OpenAI; API usage may incur charges.",
                    file=sys.stderr,
                )
        else:
            planner = SimulatedPlanner()
            request = SCENARIOS[args.scenario or "new-york"]
            print("SIMULATED PLANNING: real tools; no AI model call.", file=sys.stderr)
        result = run_workflow(
            request,
            planner,
            tools,
            policy=policy,
            plan_only=args.plan_only,
            progress=lambda stage: print(f"[langgraph] {stage}", file=sys.stderr),
        )
    except Exception:
        print(
            "LangGraph setup/execution failed. Check model settings, policy file, local "
            "service configuration and dependencies. Secret values are not displayed.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2))
    return {
        "completed": 0,
        "planned": 0,
        "needs_input": 2,
        "unsupported": 2,
        "policy_rejected": 2,
    }.get(result["status"], 1)
