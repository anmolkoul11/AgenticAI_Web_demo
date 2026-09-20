"""Opt-in real-model semantic evaluations. Skipped without explicit permission flags."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from agentic_web_demo.rules import Rules


class NoTools:
    def __getattr__(self, name):
        raise AssertionError("Plan-only evaluations must not access tools")


@pytest.mark.parametrize(
    "case,expected",
    [
        ("complete", "planned"),
        ("missing-city", "needs_input"),
        ("ambiguous-dates", "needs_input"),
        ("booking", "unsupported"),
        ("currency", "unsupported"),
        ("amenity", "unsupported"),
        ("policy-price", "policy_rejected"),
        ("policy-rating", "policy_rejected"),
        ("invalid-dates", "failed"),
        ("no-matches", "planned"),
        ("all-cities", "planned"),
        ("strict-boundary", "needs_input"),
    ],
)
def test_real_model_interpretation(live_planner, case, expected, record_property, model_workflow):
    today = date.today()
    check_in = (today + timedelta(days=7)).isoformat()
    check_out = (today + timedelta(days=9)).isoformat()
    criteria = "at most USD 200 per night including taxes and rating at least 4 out of 5"
    prompt = f"Find hotels in New York from {check_in} to {check_out}, {criteria}."
    if case == "missing-city":
        prompt = f"Find hotels from {check_in} to {check_out}, {criteria}."
    elif case == "ambiguous-dates":
        prompt = f"Find hotels in New York next weekend, {criteria}."
    elif case == "booking":
        prompt = "Book and pay for the cheapest hotel using a saved credit card."
    elif case == "currency":
        prompt = prompt.replace("USD", "EUR")
    elif case == "amenity":
        prompt += " Only include hotels with a swimming pool."
    elif case == "policy-price":
        prompt = prompt.replace("200", "300")
    elif case == "policy-rating":
        prompt = prompt.replace("at least 4", "at least 3")
    elif case == "invalid-dates":
        prompt = f"Find New York hotels from {check_out} to {check_in}, {criteria}."
    elif case == "no-matches":
        prompt = prompt.replace("200", "50")
    elif case == "all-cities":
        prompt = prompt.replace("in New York", "in all cities")
    elif case == "strict-boundary":
        prompt = prompt.replace("at most", "strictly under")
    result = model_workflow(
        prompt, live_planner, NoTools(), policy=Rules(), plan_only=True, today=today
    )
    record_property("model", live_planner.settings.model)
    record_property("prompt_version", result["model"].get("prompt_version", ""))
    record_property("status", result["status"])
    record_property("total_tokens", result["model"].get("usage", {}).get("total_tokens", 0))
    assert result["status"] == expected
    assert result["model_used"] and not result["workflow_verified"]
    assert "run_id" not in result
    assert all(item.split(":")[0] in {"plan_request", "validate_plan"} for item in result["trace"])
    if expected == "planned":
        assert result["plan"]["city"] == ("" if case == "all-cities" else "New York")
        assert result["plan"]["check_in"] == check_in
        assert result["plan"]["check_out"] == check_out
        assert Decimal(result["plan"]["max_price"]) == (50 if case == "no-matches" else 200)
        assert Decimal(result["plan"]["min_rating"]) == 4
    if case == "missing-city":
        assert "city" in result["missing_fields"]
    if case == "invalid-dates":
        assert result["failed_stage"] == "validate_plan"


# Keep the original acceptance cases above unchanged. These independent variants
# measure generalization, rather than modifying prompts to fit observed answers.
VARIANTS = [
    ("nyc-alias", "Find NYC hotels {dates}, {criteria}.", "planned", "New York"),
    ("boston", "Find Boston hotels {dates}, {criteria}.", "planned", "Boston"),
    (
        "unknown-city",
        "Find Atlantis hotels {dates}, {criteria}.",
        "planned",
        "Atlantis",
    ),
    (
        "all-cities-explicit",
        "Search hotels across all cities {dates}, {criteria}.",
        "planned",
        "",
    ),
    (
        "inclusive-reworded",
        "Find New York hotels {dates}, no more than USD 200 per night including "
        "taxes, rated no less than 4 out of 5.",
        "planned",
        "New York",
    ),
    (
        "relative-dates",
        "Find New York hotels checking in seven days from today and checking out nine "
        "days from today, {criteria}.",
        "planned",
        "New York",
    ),
    (
        "missing-city-reworded",
        "I need somewhere to stay {dates}, {criteria}.",
        "needs_input",
        "city",
    ),
    (
        "missing-city-no-default",
        "Find hotels {dates}, {criteria}. I have not selected a city yet.",
        "needs_input",
        "city",
    ),
    (
        "missing-check-in",
        "Find New York hotels checking out on {check_out}, {criteria}.",
        "needs_input",
        "check_in",
    ),
    (
        "missing-check-out",
        "Find New York hotels checking in on {check_in}, {criteria}.",
        "needs_input",
        "check_out",
    ),
    (
        "missing-price",
        "Find New York hotels {dates}, rated at least 4 out of 5. Prices are nightly "
        "USD including taxes; I have not specified a budget.",
        "needs_input",
        "max_price",
    ),
    (
        "missing-rating",
        "Find New York hotels {dates}, at most USD 200 per night including taxes. I "
        "have not specified a minimum rating.",
        "needs_input",
        "min_rating",
    ),
    (
        "strict-price-reworded",
        "Find New York hotels {dates}, less than USD 200 per night including taxes, "
        "rated at least 4 out of 5.",
        "needs_input",
        "max_price",
    ),
    (
        "strict-rating",
        "Find New York hotels {dates}, at most USD 200 per night including taxes, "
        "rated strictly above 4 out of 5.",
        "needs_input",
        "min_rating",
    ),
    (
        "euros-reworded",
        "Find New York hotels {dates}, at most 200 euros per night including taxes, "
        "rated at least 4 out of 5.",
        "unsupported",
        "unsupported_currency",
    ),
    (
        "gbp",
        "Find New York hotels {dates}, at most GBP 150 per night including taxes, "
        "rated at least 4 out of 5.",
        "unsupported",
        "unsupported_currency",
    ),
    (
        "wifi-filter",
        "Find New York hotels {dates}, {criteria}. Free Wi-Fi is required.",
        "unsupported",
        "unsupported_filter",
    ),
    (
        "pool-reworded",
        "Find New York hotels {dates}, {criteria}. Exclude properties without a pool.",
        "unsupported",
        "unsupported_filter",
    ),
    (
        "sorting",
        "Find New York hotels {dates}, {criteria}. Sort the results by distance to the airport.",
        "unsupported",
        "unsupported_filter",
    ),
    (
        "booking-reworded",
        "Reserve and pay for a New York hotel {dates}, {criteria}.",
        "unsupported",
        None,
    ),
    (
        "external-site",
        "Search Expedia for New York hotels {dates}, {criteria}.",
        "unsupported",
        None,
    ),
    (
        "trip-budget",
        "Find New York hotels {dates}, a total budget of USD 200 for the whole stay "
        "including taxes, rated at least 4 out of 5.",
        "unsupported",
        None,
    ),
    (
        "ten-point-rating",
        "Find New York hotels {dates}, at most USD 200 per night including taxes, "
        "rated at least 8 out of 10.",
        "unsupported",
        None,
    ),
    (
        "price-policy-cent",
        "Find New York hotels {dates}, at most USD 200.01 per night including taxes, "
        "rated at least 4 out of 5.",
        "policy_rejected",
        None,
    ),
    (
        "rating-policy-decimal",
        "Find New York hotels {dates}, at most USD 200 per night including taxes, "
        "rated at least 3.9 out of 5.",
        "policy_rejected",
        None,
    ),
    (
        "same-day-checkout",
        "Find New York hotels checking in on {check_in} and checking out on "
        "{check_in}, {criteria}.",
        "failed",
        None,
    ),
    (
        "external-site-tripadvisor",
        "Search TripAdvisor for New York hotels {dates}, {criteria}.",
        "unsupported",
        "unsupported_task",
    ),
    (
        "external-site-url",
        "Use https://hotels.example.org to find New York hotels {dates}, {criteria}.",
        "unsupported",
        "unsupported_task",
    ),
    (
        "rating-scale-slash",
        "Find New York hotels {dates}, at most USD 200 per night including taxes, "
        "rated at least 8/10.",
        "unsupported",
        "unsupported_filter",
    ),
    (
        "rating-scale-hundred",
        "Find New York hotels {dates}, at most USD 200 per night including taxes, "
        "rated at least 80 out of 100.",
        "unsupported",
        "unsupported_filter",
    ),
    (
        "local-source-explicit",
        "Search only the local demo portal for New York hotels {dates}, {criteria}.",
        "planned",
        "New York",
    ),
    (
        "external-site-negated",
        "Do not search Expedia. Search only the local demo portal for New York "
        "hotels {dates}, {criteria}.",
        "planned",
        "New York",
    ),
]


@pytest.mark.parametrize(
    "case,template,expected,detail", VARIANTS, ids=[item[0] for item in VARIANTS]
)
def test_real_model_wording_variants(
    live_planner, case, template, expected, detail, model_workflow
):
    today = date.today()
    check_in = (today + timedelta(days=7)).isoformat()
    check_out = (today + timedelta(days=9)).isoformat()
    prompt = template.format(
        dates=f"from {check_in} to {check_out}",
        check_in=check_in,
        check_out=check_out,
        criteria="at most USD 200 per night including taxes and rating at least 4 out of 5",
    )
    result = model_workflow(
        prompt, live_planner, NoTools(), policy=Rules(), plan_only=True, today=today
    )
    # Only synthetic inputs and sanitized workflow fields are included in failures.
    diagnostic = json.dumps(
        {
            "case": case,
            "request": prompt,
            "expected": expected,
            "actual": result["status"],
            "plan": result.get("plan"),
            "missing_fields": result.get("missing_fields"),
            "reason": result.get("reason"),
            "failed_stage": result.get("failed_stage"),
            "guidance": result.get("guidance"),
            "error_code": result.get("error_code"),
            "model": result.get("model"),
            "trace": result.get("trace"),
        },
        indent=2,
    )
    assert result["status"] == expected, diagnostic
    assert result["model_used"] and not result["workflow_verified"], diagnostic
    assert "run_id" not in result, diagnostic
    assert all(
        item.split(":")[0] in {"plan_request", "validate_plan"} for item in result["trace"]
    ), diagnostic
    if expected == "planned":
        assert result["plan"]["city"] == detail, diagnostic
        assert result["plan"]["check_in"] == check_in, diagnostic
        assert result["plan"]["check_out"] == check_out, diagnostic
        assert Decimal(result["plan"]["max_price"]) == 200, diagnostic
        assert Decimal(result["plan"]["min_rating"]) == 4, diagnostic
        assert result["plan"]["currency"] == "USD", diagnostic
        assert result["plan"]["rating_scale"] == 5, diagnostic
        assert result["plan"]["price_basis"] == "per_night_taxes_included", diagnostic
    elif expected == "needs_input":
        assert detail in result["missing_fields"], diagnostic
    elif expected == "unsupported" and detail:
        assert result["reason"] == detail, diagnostic
    elif expected == "failed":
        assert result["failed_stage"] == "validate_plan", diagnostic
