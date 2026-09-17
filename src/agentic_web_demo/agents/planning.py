"""Provider-neutral planning contract and explicitly scripted test scenarios."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from agentic_web_demo.listings import Stay
from agentic_web_demo.rules import Rules

ClarificationField = Literal["city", "check_in", "check_out", "max_price", "min_rating", "request"]
Reason = Literal[
    "none", "unsupported_task", "unsupported_currency", "unsupported_filter", "ambiguous_request"
]


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    city: str | None = Field(default=None, max_length=100)
    check_in: date | None = None
    check_out: date | None = None
    max_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    min_rating: Decimal | None = Field(default=None, ge=0, le=5)
    currency: Literal["USD"] = "USD"
    rating_scale: Literal[5] = 5
    price_basis: Literal["per_night_taxes_included"] = "per_night_taxes_included"

    def missing(self) -> list[str]:
        return [
            name
            for name in ("city", "check_in", "check_out", "max_price", "min_rating")
            if getattr(self, name) is None
        ]


class Planner(Protocol):
    def plan(self, request: str, today: date) -> dict:
        """Return structured candidate fields; graph validation remains authoritative."""
        ...


class Candidate(Plan):
    """Provider-neutral planner output. Missing values never acquire search defaults."""

    outcome: Literal["ready", "needs_input", "unsupported"] = "ready"
    clarification_fields: list[ClarificationField] = Field(default_factory=list, max_length=6)
    reason: Reason = "none"


class PlanningError(Exception):
    """Only an allowlisted code crosses the model/graph boundary, never raw API errors."""

    def __init__(self, code: str):
        self.code = code if code in PLANNER_ERRORS else "provider_error"
        super().__init__(self.code)


PLANNER_ERRORS = {
    "local_connection": "Cannot connect to local Ollama. Start Ollama and check port 11434.",
    "local_model_missing": "Local model not found. Pull the configured model using Ollama first.",
    "local_service_error": "Local Ollama request failed. Check Ollama version, model and memory.",
    "authentication": "Model authentication failed. Check local API credentials and access.",
    "rate_limit": "Model rate or quota limit reached. Check API budget and retry later.",
    "timeout": "Model request timed out. No browser tools ran; retry explicitly if desired.",
    "connection": "Model connection failed. Check approved network/proxy configuration.",
    "invalid_response": "Model output was unusable. No tools ran; review model compatibility.",
    "refusal": "The model declined the request. No tools ran.",
    "incomplete": "Model response was incomplete. No tools ran; review output-token limits.",
    "request_invalid": "Use a nonempty synthetic request of at most 2000 characters.",
    "provider_error": "Model request failed. Check provider configuration and service status.",
}


def validate_candidate(candidate: dict, today: date, policy: Rules | None = None) -> dict:
    """Shared deterministic gate for either framework and plan-only evaluation."""
    parsed = Candidate.model_validate(candidate)
    if parsed.outcome == "unsupported":
        return {
            "status": "unsupported",
            "reason": parsed.reason,
            "guidance": "Only listing searches on the local USD/night demo portal are supported. "
            "No tools ran. Rephrase using supported fields; booking/payment is not available.",
        }
    missing = list(dict.fromkeys(parsed.missing() + parsed.clarification_fields))
    if missing or parsed.outcome == "needs_input" or parsed.reason != "none":
        missing = missing or ["request"]
        return {
            "status": "needs_input",
            "missing_fields": missing,
            "guidance": "Provide explicit values for: "
            + ", ".join(missing)
            + ". Resubmit the complete request; no tools ran.",
        }
    plan = Plan.model_validate(
        parsed.model_dump(exclude={"outcome", "clarification_fields", "reason"})
    )
    stay = Stay(city=plan.city, check_in=plan.check_in, check_out=plan.check_out)
    if stay.check_in < today:
        raise ValueError("Past stay")
    if policy and (plan.max_price > policy.max_price or plan.min_rating < policy.min_rating):
        return {
            "status": "policy_rejected",
            "policy": policy.model_dump(mode="json"),
            "guidance": "Requested thresholds conflict with configured policy. "
            "Use a price at or below the policy maximum and rating at or above its minimum. "
            "The request was not silently changed; no tools ran.",
        }
    return {"plan": plan.model_dump(mode="json"), "status": "running"}


SCENARIOS = {
    "new-york": (
        "Find New York stays seven days from today for two nights, "
        "at most USD 200 per night and rating at least 4 out of 5."
    ),
    "boston": (
        "Find Boston stays seven days from today for two nights, "
        "at most USD 200 per night and rating at least 4 out of 5."
    ),
    "all-cities": (
        "Find stays in all cities seven days from today for two nights, "
        "at most USD 200 per night and rating at least 4 out of 5."
    ),
    "no-matches": (
        "Find New York stays seven days from today for two nights, "
        "at most USD 50 per night and rating at least 4 out of 5."
    ),
    "empty-results": (
        "Find Unknown City stays seven days from today for two nights, "
        "at most USD 200 per night and rating at least 4 out of 5."
    ),
    "missing-city": (
        "Find stays seven days from today for two nights, "
        "at most USD 200 per night and rating at least 4 out of 5."
    ),
}


class SimulatedPlanner:
    """Exact fixture lookup, NOT a language model or a general natural-language parser."""

    def plan(self, request: str, today: date) -> dict:
        scenario = next((key for key, text in SCENARIOS.items() if text == request), None)
        if scenario is None:
            raise ValueError("Simulated planner only supports bundled scenarios")
        city = {
            "new-york": "New York",
            "boston": "Boston",
            "all-cities": "",
            "no-matches": "New York",
            "empty-results": "Unknown City",
            "missing-city": None,
        }[scenario]
        return {
            "city": city,
            "check_in": (today + timedelta(days=7)).isoformat(),
            "check_out": (today + timedelta(days=9)).isoformat(),
            "max_price": "50" if scenario == "no-matches" else "200",
            "min_rating": "4",
        }
