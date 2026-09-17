"""Independent CrewAI Flow. Never imports or executes a LangGraph runner."""

import asyncio
from datetime import date

from agentic_web_demo.agents.crewai_runtime import configure

configure()

from crewai.flow.flow import Flow, listen, start  # noqa: E402

from agentic_web_demo.agents.planning import (  # noqa: E402
    PLANNER_ERRORS,
    Plan,
    PlanningError,
    validate_candidate,
)
from agentic_web_demo.listings import Snapshot, Stay  # noqa: E402
from agentic_web_demo.rules import Rules  # noqa: E402


def run_workflow(
    request,
    planner,
    tools,
    *,
    policy=None,
    plan_only=False,
    saved_plan=None,
    progress=None,
    today=None,
):
    today = today or date.today()
    policy = policy or Rules()
    mode = getattr(planner, "mode", "simulated")

    class HotelFlow(Flow[dict]):
        async def step(self, name, action):
            if self.state.get("status") != "running":
                return
            if progress:
                progress(name)
            try:
                # Playwright sync and NATS asyncio.run must not run inside Flow's loop.
                update = await asyncio.to_thread(action)
                self.state.update(update)
                self.state["trace"].append(name + ":ok")
            except Exception as exc:
                self.state.update(
                    status="failed",
                    failed_stage=name,
                    guidance="Stage failed. Inspect the reported run ID before "
                    "recovery; do not blindly repeat extraction or publication.",
                )
                if isinstance(exc, PlanningError):
                    self.state.update(error_code=exc.code, guidance=PLANNER_ERRORS[exc.code])
                self.state["trace"].append(name + ":failed")

        @start()
        async def plan_request(self):
            self.state.update(status="running", trace=[])
            if saved_plan is not None:
                self.state["candidate"] = saved_plan
            else:
                await self.step("plan_request", lambda: {"candidate": planner.plan(request, today)})

        @listen(plan_request)
        async def validate_plan(self):
            def action():
                result = validate_candidate(self.state["candidate"], today, policy)
                if result["status"] == "running":
                    plan = Plan.model_validate(result["plan"])
                    result["effective_rules"] = Rules(
                        rule_id=policy.rule_id,
                        version=policy.version,
                        max_price=plan.max_price,
                        min_rating=plan.min_rating,
                    ).model_dump(mode="json")
                    if plan_only:
                        result.update(
                            status="planned", guidance="Proposal validated; no tools ran."
                        )
                return result

            await self.step("validate_plan", action)

        @listen(validate_plan)
        async def extract(self):
            def action():
                plan = Plan.model_validate(self.state["plan"])
                stay = Stay(city=plan.city, check_in=plan.check_in, check_out=plan.check_out)
                snapshot = tools.extract(stay)
                snapshot = Snapshot.model_validate_json(snapshot.model_dump_json())
                if snapshot.stay != stay:
                    raise ValueError("Extraction differs from approved plan")
                return {"snapshot": snapshot, "record_count": len(snapshot.listings)}

            await self.step("extract", action)

        @listen(extract)
        async def save(self):
            await self.step("save", lambda: {"run_id": tools.save(self.state["snapshot"])})

        @listen(save)
        async def export(self):
            await self.step("export", lambda: {"export_path": tools.export(self.state["run_id"])})

        @listen(export)
        async def evaluate(self):
            await self.step(
                "evaluate",
                lambda: {
                    "evaluation": tools.evaluate(
                        self.state["run_id"], Rules.model_validate(self.state["effective_rules"])
                    )
                },
            )

        @listen(evaluate)
        async def publish(self):
            if self.state.get("evaluation", {}).get("matched", 0):
                await self.step(
                    "publish", lambda: {"delivery": tools.publish(self.state["run_id"])}
                )

        @listen(publish)
        async def receive(self):
            if self.state.get("evaluation", {}).get("matched", 0):
                await self.step("receive", lambda: {"consumer": tools.receive()})

        @listen(receive)
        async def verify(self):
            def action():
                delivery = tools.status(self.state["run_id"])
                expected = {item["event_id"] for item in delivery["events"]}
                received = {item["event_id"] for item in delivery["receipts"]}
                confirmed = len(expected & received)
                valid = (
                    len(expected) == self.state["evaluation"]["matched"]
                    and not delivery["pending"]
                    and delivery["published"] == len(expected)
                    and expected.issubset(received)
                )
                return {
                    "status": "completed" if valid else "delivery_unconfirmed",
                    "delivery": delivery,
                    "receipts_verified": confirmed,
                    "guidance": "Run-specific delivery verified."
                    if valid
                    else "Inspect events-status for this run; do not re-extract.",
                }

            await self.step("verify", action)

    flow = HotelFlow(tracing=False, suppress_flow_events=True)
    flow.kickoff()
    state = flow.state
    metadata = getattr(planner, "metadata", {})
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
    return {
        "framework": "crewai",
        "mode": mode,
        "model_used": bool(metadata.get("response_received", False)),
        "model_api_attempted": bool(metadata.get("api_attempted", False)),
        "model": metadata,
        "workflow_verified": state["status"] == "completed",
        **{key: state[key] for key in fields if key in state},
    }
