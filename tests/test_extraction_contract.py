"""Offline source-bound URL repairs and literal query-coverage regressions."""

from pathlib import Path

import pytest
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.custom_constraints import (
    constraint_coverage,
    requested_constraints,
    unverified_constraints,
)
from agentic_web_demo.custom_extract import (
    Extraction,
    WebsiteInput,
    prepare_extraction,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.dashboard.service import DashboardService


def source(instructions="Get the visible hotels", **changes):
    return WebsiteInput(
        source="paste",
        urls=["https://example.org/results"],
        page_text="North Hotel has an available listing. The displayed nightly price is "
        "300 USD per night, with guest rating 4.5 out of 5. Review the source information.",
        instructions=instructions,
        authorized=True,
        allow_model_api=True,
        **changes,
    )


def candidate(*, filters=True, price="300", basis="per night"):
    cells = {
        "hotel_name": ("North Hotel", "North Hotel"),
        "hotel_url": ("https://example.org/hotels/north", "North Hotel"),
        "price": (price, f"{price} USD" if price else ""),
        "currency": ("USD", "USD"),
        "price_basis": (basis, basis or ""),
    }
    return Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "hotels",
            "interpretation": "Visible hotel records",
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {
                    "name": name,
                    "kind": "number" if name == "price" else "text",
                    "unit": "USD" if name == "price" else "",
                    "description": name,
                }
                for name in cells
            ],
            "filters": [
                {"field": "price", "operator": "gte", "value": "250"},
                {"field": "price", "operator": "lte", "value": "350"},
            ]
            if filters
            else [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": name, "value": value, "evidence": quote}
                        for name, (value, quote) in cells.items()
                    ],
                }
            ],
        }
    )


def page(*, other_link=False, grouped=False):
    blocks = [
        {
            "id": "b1",
            "kind": "heading",
            "text": "North Hotel",
            "href": None,
            "group_id": "g1",
            "association": "record",
        },
        {
            "id": "b2",
            "kind": "link",
            "text": "View listing" if grouped else "North Hotel",
            "href": "https://example.org/hotels/north",
            "group_id": "g1",
            "association": "record",
        },
        {
            "id": "b3",
            "kind": "paragraph",
            "text": "300 USD per night",
            "href": None,
            "group_id": "g1",
            "association": "record",
        },
    ]
    if other_link:
        blocks.append(
            {
                "id": "b4",
                "kind": "link",
                "text": "North Hotel",
                "href": "https://example.org/other/north",
                "group_id": "g1",
                "association": "record",
            }
        )
    # URL repair is authorized by the exact href structure even if text excludes it.
    return {
        "url": "https://example.org/results",
        "blocks": blocks,
        "text": "\n".join(block["text"] for block in blocks),
        "truncated": False,
    }


@pytest.mark.parametrize("grouped", [False, True])
def test_correct_url_with_name_quote_is_repaired_only_from_unique_identity_binding(grouped):
    model, values, _ = prepare_extraction(candidate(filters=False), source())
    repairs, issues = [], []
    rows, _ = validate_extraction(
        model,
        values,
        [page(grouped=grouped)],
        rejected=[],
        field_issues=issues,
        field_repairs=repairs,
    )
    assert rows[0]["hotel_url"] == "https://example.org/hotels/north"
    assert rows[0]["evidence"]["hotel_url"] == rows[0]["hotel_url"]
    assert not issues
    assert repairs[0]["issues"][0]["old_value"] == rows[0]["hotel_url"]


def test_ambiguous_identity_links_do_not_repair_null_or_badly_quoted_urls():
    model = candidate(filters=False)
    model.rows[0].cells[1].value = None
    model.rows[0].cells[1].evidence = ""
    model, values, _ = prepare_extraction(model, source())
    rows, _ = validate_extraction(
        model, values, [page(other_link=True)], rejected=[], field_issues=[]
    )
    assert rows[0]["hotel_url"] is None


def test_url_from_another_record_is_not_replaced_or_approved():
    model = candidate(filters=False)
    model.rows[0].cells[1].value = "https://example.org/hotels/south"
    model, values, _ = prepare_extraction(model, source())
    issues = []
    rows, _ = validate_extraction(model, values, [page()], rejected=[], field_issues=issues)
    assert rows[0]["hotel_url"] is None
    assert issues[0]["issues"][0]["field"] == "hotel_url"


@pytest.mark.parametrize("url_value", [None, "https://example.org/article"])
@pytest.mark.parametrize("explicit_href", [False, True])
def test_identity_truncated_page_url_is_not_fallback_evidence_but_explicit_href_remains_valid(
    url_value,
    explicit_href,
):
    title = "Researchers publish a new battery result"
    body = "The team tested a new battery with repeated charge cycles and published its findings."
    page_url = "https://example.org/article"
    model = Extraction.model_validate(
        {
            "outcome": "ready",
            "guidance": "Review",
            "content_type": "articles",
            "interpretation": "Current article",
            "requested_fields": ["article_excerpt"],
            "warnings": [],
            "more_records_available": False,
            "columns": [
                {"name": name, "kind": "text", "unit": "", "description": name}
                for name in ("article_title", "article_url")
            ],
            "filters": [],
            "rows": [
                {
                    "page_index": 0,
                    "cells": [
                        {"field": "article_title", "value": title, "evidence": title},
                        {"field": "article_url", "value": url_value, "evidence": url_value or ""},
                    ],
                }
            ],
        }
    )
    blocks = [
        {
            "id": "b1",
            "kind": "heading",
            "text": title,
            "href": page_url if explicit_href else None,
            "heading_level": 1,
            "content_role": "headline",
            "group_id": "g1",
            "association": "record",
        },
        {
            "id": "b2",
            "kind": "paragraph",
            "text": body,
            "href": None,
            "content_role": "body",
            "group_id": "g1",
            "association": "record",
        },
    ]
    captured = {
        "url": page_url,
        "source_kind": "detail",
        "text": title + "\n" + body,
        "blocks": blocks,
        "coverage": {"page_url_identity_omitted": True},
    }
    model, values, _ = prepare_extraction(
        model, source("Extract the current article and include its article excerpt")
    )
    rows, _ = validate_extraction(model, values, [captured], rejected=[], field_issues=[])
    assert rows[0]["article_url"] == (page_url if explicit_href else None)
    assert rows[0]["article_title"] == title
    assert rows[0]["article_excerpt"] == body


@pytest.mark.parametrize(
    "wording",
    [
        "Hotels priced between 250-350 USD nightly",
        "Prices between 250 USD and 350 USD nightly",
        "Products with price ranging from 250 to 350 USD",
        "Hotels between 250 and 350 USD; flag below 280 as preferred",
    ],
)
def test_literal_ranges_preserve_both_bounds_without_default_policy(wording):
    constraints = requested_constraints(wording)
    assert constraints[0]["kind"] == "price"
    assert constraints[0]["conditions"] == [
        {"operator": "gte", "value": "250"},
        {"operator": "lte", "value": "350"},
    ]
    assert len(constraints) == 1


def test_dates_occupancy_and_flagging_are_not_price_filters():
    assert requested_constraints("Check in October 29-31, 2026 for 3 adults and 2 rooms") == []
    assert requested_constraints("Get all hotels; flag price below 280 USD as preferred") == []
    assert requested_constraints("") == []
    comparisons = requested_constraints("Price between 250 and 350 USD and dates from 29-31")
    assert len(comparisons) == 1


@pytest.mark.parametrize(
    "wording",
    [
        "Price min 150 USD max 250 USD nightly",
        "Hotels priced min 150 USD max at 250 USD per night",
        "Price minimum 150 maximum 250 USD",
    ],
)
def test_paired_minimum_and_maximum_prices_are_both_retained(wording):
    comparisons = requested_constraints(wording)
    assert len(comparisons) == 1
    assert comparisons[0]["conditions"] == [
        {"operator": "gte", "value": "150"},
        {"operator": "lte", "value": "250"},
    ]


@pytest.mark.parametrize(
    "wording",
    [
        "Get hotels; flag price below 180 as preferred; keep price at most 250 USD",
        "Get hotels; flag price below 180 as preferred and return price at most 250 USD",
    ],
)
def test_selection_after_flagging_is_not_silently_discarded(wording):
    comparisons = requested_constraints(wording)
    assert len(comparisons) == 1
    assert comparisons[0]["conditions"] == [{"operator": "lte", "value": "250"}]


def test_adjacent_rating_then_price_range_has_separate_semantics():
    comparisons = requested_constraints("Minimum rating 4.2 out of 5 and price between 250-350 USD")
    assert {item["kind"] for item in comparisons} == {"price", "rating"}


def test_missing_price_schema_and_filters_preserve_null_dependencies_but_cannot_approve():
    model = candidate(filters=False)
    model.columns = model.columns[:2]
    model.rows[0].cells = model.rows[0].cells[:2]
    model, _, _ = prepare_extraction(model, source("Hotels priced between 250-350 USD nightly"))
    assert {c.name for c in model.columns} >= {"price", "currency", "price_basis"}
    assert all(cell.value is None for cell in model.rows[0].cells[2:])
    coverage = constraint_coverage(model._requested_constraints, model.columns, model.filters)
    assert {issue["operator"] for issue in coverage["issues"]} == {"gte", "lte"}


def test_model_cannot_silently_change_requested_thresholds():
    model, _, _ = prepare_extraction(candidate(), source("Price between 250 and 350 USD"))
    model.filters[1].value = "300"
    coverage = constraint_coverage(model._requested_constraints, model.columns, model.filters)
    assert coverage["issues"][0]["value"] == "350"


def test_equivalent_decimal_bounds_are_not_rejected_as_different_strings():
    model, _, _ = prepare_extraction(candidate(), source("Price between 250.0 and 350.00 USD"))
    assert (
        constraint_coverage(model._requested_constraints, model.columns, model.filters)["issues"]
        == []
    )


def test_currency_and_nightly_basis_require_record_evidence_not_schema_units():
    model, _, _ = prepare_extraction(candidate(), source("Price between 250 and 350 USD nightly"))
    coverage = constraint_coverage(model._requested_constraints, model.columns, model.filters)
    record = {
        "price": "300",
        "currency": "USD",
        "price_basis": "per night",
        "evidence": {"price": "300", "currency": "", "price_basis": ""},
    }
    assert {item["reason"] for item in unverified_constraints(record, coverage)} == {
        "requested_currency_unverified",
        "requested_nightly_basis_unverified",
    }
    record["evidence"]["price"] = "US$300 per night"
    assert unverified_constraints(record, coverage) == []


def test_rating_scale_is_not_converted_or_guessed():
    model = candidate(filters=False)
    model.columns[2].name = "guest_rating"
    model.columns[2].unit = "out of 5"
    model.filters = []
    constraints = requested_constraints("Guest rating at least 4.2 out of 5")
    coverage = constraint_coverage(constraints, model.columns, model.filters)
    record = {"guest_rating": "4.5", "evidence": {"guest_rating": "4.5 out of 10"}}
    assert (
        unverified_constraints(record, coverage)[0]["reason"] == "requested_rating_scale_unverified"
    )


def test_detail_nightly_basis_cannot_relabel_an_index_stay_total():
    model, _, _ = prepare_extraction(candidate(), source("Price between 250 and 350 USD nightly"))
    coverage = constraint_coverage(model._requested_constraints, model.columns, model.filters)
    record = {
        "price": "300",
        "price_basis": "per night",
        "source_url": "https://example.org/index",
        "evidence": {"price": "300 USD total", "price_basis": "per night"},
        "evidence_sources": {
            "price": {"source_url": "https://example.org/index"},
            "price_basis": {"source_url": "https://example.org/hotels/north"},
        },
    }
    assert (
        unverified_constraints(record, coverage)[0]["reason"]
        == "requested_nightly_basis_unverified"
    )


@pytest.fixture
def service(tmp_path):
    instance = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    yield instance
    instance.close()


@pytest.mark.parametrize("framework", ["langgraph", "crewai"])
def test_dropped_requested_price_filters_stop_before_a_savable_proposal(
    service, monkeypatch, framework
):
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(filters=False), {}))
    job = finished(
        service,
        custom_service.plan(
            service,
            source("Hotels priced between 250-350 USD nightly", framework=framework),
            object(),
        ),
    )
    assert job["status"] == "needs_input"
    assert job["result"]["review_outcome"] == "constraint_unresolved"
    assert job["result"]["review_counts"]["matched"] == 0
    assert job["result"]["unverified_preview"][0]["hotel_name"] == "North Hotel"
    assert "proposal" not in job["result"]
    assert not list((service.data_dir / "website-plans").glob("*.json"))


def test_unavailable_price_basis_is_unverified_not_filtered_out(service, monkeypatch):
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(basis=None), {}))
    job = finished(
        service,
        custom_service.plan(
            service,
            source("Hotels priced between 250-350 USD nightly"),
            object(),
        ),
    )
    assert job["status"] == "needs_input"
    assert job["result"]["review_counts"]["constraint_unverified"] == 1
    assert job["result"]["review_counts"]["filtered_out"] == 0
    assert job["result"]["review_outcome"] == "constraint_unresolved"
    assert job["result"]["unverified_preview"][0]["price"] == "300"
    assert "proposal" not in job["result"]


def test_unverified_preview_never_includes_fabricated_identity(service, monkeypatch):
    model = candidate(filters=False)
    model.rows[0].cells[0].value = "Invented Hotel"
    model.rows[0].cells[0].evidence = "Invented Hotel"
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model, {}))
    job = finished(
        service,
        custom_service.plan(
            service,
            source("Hotels priced between 250-350 USD nightly"),
            object(),
        ),
    )
    assert job["result"]["unverified_preview"] == []
    assert job["result"]["review_counts"]["invalid"] == 1
    assert "proposal" not in job["result"]


def test_readonly_preview_is_bounded_but_never_labels_candidates_matched(service, monkeypatch):
    model = candidate(filters=False)
    second = model.rows[0].model_copy(deep=True)
    second.cells[0].value, second.cells[0].evidence = "East Hotel", "East Hotel"
    model.rows.append(second)
    values = source("Hotels priced between 250-350 USD nightly", record_limit=1)
    values.page_text += " East Hotel also displays 300 USD per night."
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (model, {}))
    job = finished(service, custom_service.plan(service, values, object()))
    assert len(job["result"]["unverified_preview"]) == 1
    assert job["result"]["unverified_preview_more_available"] is True
    assert job["result"]["review_counts"]["matched"] == 0
    assert job["result"]["review_counts"]["constraint_unverified"] == 2
    assert "proposal" not in job["result"]


def test_old_unfiltered_preview_cannot_bypass_contract_during_save(monkeypatch):
    model = candidate(filters=False)
    proposal = {
        "request": "Hotels priced between 250-350 USD nightly",
        "columns": [c.model_dump() for c in model.columns],
        "filters": [],
        "records": [],
    }
    monkeypatch.setattr(custom_service, "load", lambda *_: proposal)
    with pytest.raises(WebsiteError, match="fresh preview"):
        custom_service.execute(object(), "old", custom_service.digest(proposal))


def test_confirmed_empty_search_skips_extraction_and_does_not_create_preview(service, monkeypatch):
    values = WebsiteInput(
        source="browser",
        urls=["https://example.org/search"],
        instructions="Search for unusual shoes",
        authorized=True,
        allow_model_api=True,
        login_mode="none",
    )

    def empty_search(_values, control, _settings):
        control.set_agent_report(
            {
                "status": "ready",
                "collection_outcome": "empty_results",
                "task_checklist": {"search_submitted": True, "search_response_pending": False},
            }
        )
        return []

    def unexpected_extraction(*_):
        pytest.fail("An empty confirmed search must not incur an extraction call")

    monkeypatch.setattr(custom_service, "read_browser", empty_search)
    monkeypatch.setattr(custom_service, "interpret", unexpected_extraction)
    job = finished(service, custom_service.plan(service, values, object()))
    assert job["status"] == "needs_input"
    assert job["result"]["review_outcome"] == "no_matches"
    assert job["result"]["record_count"] == 0
    assert job["result"]["model"] == {}
