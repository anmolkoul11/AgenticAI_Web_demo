"""Bounded LangGraph workflow with pluggable planning and deterministic tool execution."""

import operator
from collections.abc import Callable
from datetime import date
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from agentic_web_demo.agents.planning import (
    PLANNER_ERRORS,
    Plan,
    Planner,
    PlanningError,
    validate_candidate,
)
from agentic_web_demo.agents.tools import DemoTools
from agentic_web_demo.listings import Snapshot, Stay
from agentic_web_demo.rules import Rules


class State(TypedDict, total=False):
    request: str
    candidate: dict
    plan: dict
    status: str
    missing_fields: list[str]
    snapshot: Snapshot
    run_id: str
    record_count: int
    export_path: str
    evaluation: dict
    delivery: dict
    consumer: dict
    receipts_verified: int
    failed_stage: str
    guidance: str
    reason: str
    error_code: str
    policy: dict
    effective_rules: dict
    trace: Annotated[list[str], operator.add]


RECOVERY = {
    "plan_request": "Planning failed. Check the selected provider or simulated scenario.",
    "validate_plan": "Plan rejected. Check required fields, dates, currency and rating scale.",
    "extract": "Check the portal, Chromium and demo credentials. No snapshot saved at this stage.",
    "save": "Local save failed. Check permissions and disk space before retrying.",
    "export": "Snapshot saved. Retry agentic-demo export --run-id with the reported run ID.",
    "evaluate": "Snapshot saved. Check the rule configuration before processing this run again.",
    "publish": "Check NATS. Use events-status and publish --run-id; do not repeat extraction.",
    "receive": "Check NATS. Run consume, then events-status --run-id to check receipts.",
    "verify": "Could not verify this run's delivery. Inspect events-status --run-id.",
}


def build_graph(
    planner: Planner,
    tools: DemoTools,
    *,
    today: date | None = None,
    progress: Callable[[str], None] | None = None,
    policy: Rules | None = None,
    plan_only: bool = False,
    saved_plan: dict | None = None,
):
    today = today or date.today()

    def guarded(name, function):
        def node(state):
            if progress:
                progress(name)
            try:
                update = function(state)
                return {**update, "trace": [name + ":ok"]}
            except PlanningError as exc:
                return {
                    "status": "failed",
                    "failed_stage": name,
                    "error_code": exc.code,
                    "guidance": PLANNER_ERRORS[exc.code],
                    "trace": [name + ":failed"],
                }
            except Exception:
                # Do not log raw tool exceptions: browser errors may contain form values.
                return {
                    "status": "failed",
                    "failed_stage": name,
                    "guidance": RECOVERY[name],
                    "trace": [name + ":failed"],
                }

        return node

    def validate(state):
        result = validate_candidate(state["candidate"], today, policy)
        if result["status"] == "running":
            plan = Plan.model_validate(result["plan"])
            result["effective_rules"] = rules_for(plan).model_dump(mode="json")
            if plan_only:
                result.update(
                    status="planned",
                    guidance="Plan validated; no tools ran. "
                    "A new execution request replans; this preview is not resumed.",
                )
        return result

    def rules_for(plan):
        return Rules(
            rule_id=policy.rule_id if policy else "affordable-quality-stay",
            version=policy.version if policy else 1,
            max_price=plan.max_price,
            min_rating=plan.min_rating,
            currency=plan.currency,
            rating_scale=plan.rating_scale,
            price_basis=plan.price_basis,
        )

    def extract(state):
        plan = Plan.model_validate(state["plan"])
        snapshot = tools.extract(
            Stay(city=plan.city, check_in=plan.check_in, check_out=plan.check_out)
        )
        snapshot = Snapshot.model_validate_json(snapshot.model_dump_json())
        expected = (plan.city, plan.check_in, plan.check_out)
        if (
            snapshot.stay.city,
            snapshot.stay.check_in,
            snapshot.stay.check_out,
        ) != expected:
            raise ValueError("Extraction does not match validated plan")
        return {"snapshot": snapshot, "record_count": len(snapshot.listings)}

    def evaluate(state):
        rules = Rules.model_validate(state["effective_rules"])
        return {"evaluation": tools.evaluate(state["run_id"], rules)}

    def verify(state):
        delivery = tools.status(state["run_id"])
        expected = {item["event_id"] for item in delivery["events"]}
        received = {item["event_id"] for item in delivery["receipts"]}
        confirmed = len(expected & received)
        if (
            len(expected) != state["evaluation"]["matched"]
            or delivery["pending"]
            or delivery["published"] != len(expected)
            or not expected.issubset(received)
        ):
            return {
                "status": "delivery_unconfirmed",
                "receipts_verified": confirmed,
                "guidance": "Check events-status for missing receipts; do not re-extract.",
            }
        return {
            "status": "completed",
            "receipts_verified": confirmed,
            "delivery": delivery,
            "guidance": "Tool workflow and run-specific receipts verified.",
        }

    graph = StateGraph(State)
    functions = {
        "plan_request": lambda state: {"candidate": planner.plan(state["request"], today)},
        "validate_plan": validate,
        "extract": extract,
        "save": lambda state: {"run_id": tools.save(state["snapshot"])},
        "export": lambda state: {"export_path": tools.export(state["run_id"])},
        "evaluate": evaluate,
        "publish": lambda state: {"delivery": tools.publish(state["run_id"])},
        "receive": lambda state: {"consumer": tools.receive()},
        "verify": verify,
    }
    for name, function in functions.items():
        graph.add_node(name, guarded(name, function))
    graph.add_edge(START, "validate_plan" if saved_plan is not None else "plan_request")

    def route(next_node):
        return lambda state: next_node if state.get("status") == "running" else END

    sequence = list(functions)
    for current, following in zip(sequence, sequence[1:], strict=False):
        if current == "evaluate":
            graph.add_conditional_edges(
                current,
                lambda state: (
                    END
                    if state.get("status") == "failed"
                    else "verify"
                    if state["evaluation"]["matched"] == 0
                    else "publish"
                ),
            )
        else:
            graph.add_conditional_edges(current, route(following))
    graph.add_edge("verify", END)
    return graph.compile()


def run_workflow(
    request: str,
    planner: Planner,
    tools: DemoTools,
    *,
    progress=None,
    policy: Rules | None = None,
    plan_only: bool = False,
    today: date | None = None,
    saved_plan: dict | None = None,
) -> dict:
    mode = getattr(planner, "mode", "simulated")
    if mode == "live" and policy is None:
        policy = Rules()
    graph = build_graph(
        planner,
        tools,
        progress=progress,
        policy=policy,
        plan_only=plan_only,
        today=today,
        saved_plan=saved_plan,
    )
    # Explicitly disable external tracing for this demo, including inherited tracing settings.
    with tracing_context(enabled=False):
        state = graph.invoke(
            {
                "request": request,
                "status": "running",
                "trace": [],
                **({"candidate": saved_plan} if saved_plan is not None else {}),
            },
            config={"recursion_limit": 15},
        )
    fields = (
        "status",
        "plan",
        "missing_fields",
        "run_id",
        "record_count",
        "export_path",
        "evaluation",
        "delivery",
        "consumer",
        "receipts_verified",
        "failed_stage",
        "guidance",
        "trace",
        "reason",
        "error_code",
        "policy",
        "effective_rules",
    )
    metadata = getattr(planner, "metadata", {})
    return {
        "framework": "langgraph",
        "mode": mode,
        "model_used": bool(metadata.get("response_received", False)),
        "model_api_attempted": bool(metadata.get("api_attempted", False)),
        "model": metadata,
        "workflow_verified": state["status"] == "completed",
        **{key: state[key] for key in fields if key in state},
    }
