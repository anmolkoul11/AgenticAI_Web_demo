"""CLI presentation over reusable proposal/execution services."""

import json
import os
import sys
from datetime import date
from pathlib import Path

from agentic_web_demo.agents.planning import validate_candidate
from agentic_web_demo.agents.saved_plans import (
    execute_proposal,
    load_proposal,
    revision,
    save_proposal,
)
from agentic_web_demo.rules import load_rules


def run_saved_command(args, data_dir):
    try:
        return _run(args, data_dir)
    except FileExistsError:
        print(
            "This plan already has an execution attempt. Inspect its result and recover "
            "by run ID; do not replay side effects.",
            file=sys.stderr,
        )
        return 2
    except Exception:
        print(
            "Plan operation rejected. Check required arguments, plan ID/revision, expiry, "
            "unchanged policy, supported adapter and local configuration. "
            "No secret values are displayed.",
            file=sys.stderr,
        )
        return 2


def _run(args, data_dir):
    framework = args.command
    if args.adapter != "demo-hotels" or args.scenario or args.list_scenarios or args.plan_only:
        raise ValueError("Unsupported adapter or legacy flags.")
    fields = [args.city, args.check_in, args.check_out, args.max_price, args.min_rating]
    if args.action in {"review", "execute"}:
        if (
            not args.plan_id
            or any(value is not None for value in fields)
            or args.all_cities
            or args.request is not None
            or args.mode is not None
            or args.allow_model_api
        ):
            raise ValueError("Execution accepts a saved plan, not new planning inputs.")
        proposal = load_proposal(data_dir, args.plan_id)
        if proposal.framework != framework:
            raise ValueError("Use the framework recorded in the proposal")
        if args.action == "review":
            if args.approve or args.base_url or args.headed or args.policy:
                raise ValueError("Review does not change execution settings.")
            print(
                json.dumps(
                    {
                        "proposal": proposal.model_dump(mode="json"),
                        "revision": revision(proposal),
                        "guidance": "Compare every field with your intent. Execute with "
                        "--approve REVISION only after review. No model call occurs.",
                    },
                    indent=2,
                )
            )
            return 0
        if not args.approve:
            raise ValueError("Explicit revision approval required.")
        from agentic_web_demo.agents.tools import DemoTools
        from agentic_web_demo.messaging import Broker

        tools = DemoTools(
            data_dir=data_dir,
            base_url=args.base_url or proposal.base_url,
            headed=args.headed,
            broker=Broker(url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222")),
        )
        result = execute_proposal(
            data_dir,
            args.plan_id,
            args.approve,
            load_rules(args.policy or Path("config/rules.yaml")),
            tools,
            progress=lambda stage: print(f"[{framework}] {stage}", file=sys.stderr),
            framework=framework,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "completed" else 1
    if args.plan_id or args.approve or args.headed:
        raise ValueError("Planning does not execute or edit an existing proposal.")
    policy = load_rules(args.policy or Path("config/rules.yaml"))
    metadata = {}
    if args.request is not None:
        if any(value is not None for value in fields) or args.all_cities:
            raise ValueError("Choose explicit fields or a request, not both.")
        if args.mode not in {None, "live"}:
            raise ValueError("Model-assisted planning cannot be simulated.")
        provider = os.environ.get("AGENTIC_MODEL_PROVIDER", "openai")
        if framework == "crewai" and provider != "ollama":
            raise ValueError("CrewAI initially supports the explicit local Ollama provider only")
        if provider == "ollama":
            from agentic_web_demo.agents.ollama_planner import (
                OllamaPlanner,
                OllamaSettings,
            )

            planner = OllamaPlanner(OllamaSettings.from_env())
        elif provider == "openai" and args.allow_model_api:
            from agentic_web_demo.agents.openai_planner import (
                ModelSettings,
                OpenAIPlanner,
            )

            planner = OpenAIPlanner(ModelSettings.from_env())
        else:
            raise ValueError("Unknown provider or missing hosted API permission.")
        from agentic_web_demo.agents.runners import get_runner

        if framework == "crewai":
            from agentic_web_demo.agents.crewai_planner import CrewAIPlanner

            planner = CrewAIPlanner(planner)
        run_workflow = get_runner(framework)

        # plan_only guarantees no browser/storage/event tools are called.
        result = run_workflow(args.request, planner, None, policy=policy, plan_only=True)
        if result["status"] != "planned":
            print(json.dumps(result, indent=2))
            return 2
        plan, metadata = result["plan"], result["model"]
        source = "model-assisted"
    else:
        if args.mode or args.allow_model_api or (args.all_cities == (args.city is not None)):
            raise ValueError("Select exactly one of --city and --all-cities.")
        if args.city is not None and not args.city.strip():
            raise ValueError("Use --all-cities explicitly.")
        candidate = dict(
            city="" if args.all_cities else args.city,
            check_in=args.check_in,
            check_out=args.check_out,
            max_price=args.max_price,
            min_rating=args.min_rating,
        )
        result = validate_candidate(candidate, date.today(), policy)
        if result["status"] != "running":
            print(json.dumps(result, indent=2))
            return 2
        plan, source = result["plan"], "structured"
    proposal = save_proposal(
        data_dir,
        plan,
        policy,
        args.base_url or "http://127.0.0.1:8000",
        source=source,
        request=args.request,
        model=metadata,
        framework=framework,
    )
    print(
        json.dumps(
            {
                "status": "awaiting_review",
                "proposal": proposal.model_dump(mode="json"),
                "revision": revision(proposal),
                "guidance": "Review the original request, fields and target. "
                "Execution requires --plan-id and --approve REVISION. "
                "Model interpretation is experimental; approval is human review, "
                "not proof of semantic accuracy.",
            },
            indent=2,
        )
    )
    return 0
