"""Private proposals, human approval, local records and optional summary events."""

import asyncio
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from openai import APIError

from agentic_web_demo.browser_links import safe_display_url
from agentic_web_demo.custom_browser import (
    BrowserControl,
    access_challenge,
    read_browser,
)
from agentic_web_demo.custom_constraints import (
    constraint_coverage,
    requested_constraints,
    unverified_constraints,
)
from agentic_web_demo.custom_extract import (
    Column,
    Condition,
    QueryRule,
    apply_query_rules,
    interpret,
    matches,
    prepare_extraction,
    validate_extraction,
)
from agentic_web_demo.custom_fetch import WebsiteError, read_pages
from agentic_web_demo.custom_workflow import run_steps
from agentic_web_demo.enrichment import evidence_block_ids, reconcile_records
from agentic_web_demo.messaging import Broker, connect
from agentic_web_demo.output_contract import project_output_records, select_output_contract
from agentic_web_demo.result_presentation import annotate_source_coverage
from agentic_web_demo.pricing import (
    CONTRACT_VERSION as PRICING_CONTRACT_VERSION,
    assess_pricing,
    pricing_comparison_record,
)


PRICING_COLUMNS = [
    {
        "name": "pricing_combined_nightly",
        "kind": "number",
        "unit": "source currency, all requested rooms / night",
        "description": "Computed comparison; average per night only for verified stay totals",
        "computed": True,
    },
    {
        "name": "pricing_currency",
        "kind": "text",
        "unit": "",
        "description": "Source-assessed price currency; not assumed from a bare dollar symbol",
        "computed": True,
    },
    {
        "name": "pricing_basis",
        "kind": "text",
        "unit": "",
        "description": "Server-assessed displayed price basis, not an invented source quote",
        "computed": True,
    },
    {
        "name": "pricing_taxes",
        "kind": "text",
        "unit": "",
        "description": "Source-backed taxes inclusion, exclusion or unknown",
        "computed": True,
    },
    {
        "name": "pricing_fees",
        "kind": "text",
        "unit": "",
        "description": "Source-backed fees inclusion, exclusion or unknown, separate from taxes",
        "computed": True,
    },
    {
        "name": "pricing_budget_status",
        "kind": "text",
        "unit": "",
        "description": "Computed target assessment; outside soft targets is not a hard exclusion",
        "computed": True,
    },
    {
        "name": "pricing_observed_amounts",
        "kind": "text",
        "unit": "",
        "description": "Captured amount roles/labels; originals and unknowns are not budget matches",
        "computed": True,
    },
]


def criteria_issues_summary(records):
    """Count actual per-record blockers, not every possible missing criterion."""
    labels = {
        "price_basis_unverified": "Price basis or room scope could not be confirmed",
        "nightly_comparison_unverified": "The requested nightly comparison cannot be confirmed",
        "price_observation_ambiguous": "More than one current amount could satisfy this price basis",
        "original_price_not_current_quote": "The supported amount is crossed out, not a current quote",
        "price_currency_unverified": "Source currency is unverified",
        "requested_currency_unverified": "The requested currency is unverified",
        "requested_stay_scope_unverified": "Returned stay details could not be fully verified",
        "requested_stay_mismatch": "Returned stay details conflict with the request",
        "price_amount_quote_unverified": "The amount is not supported by its source quote",
        "price_record_binding_unverified": "The price is not uniquely tied to this record",
        "price_quote_unavailable": "No source quote supports the selected amount",
        "missing_or_ambiguous_price_field": "A primary numeric price field is missing or ambiguous",
        "requested_rating_scale_unverified": "The requested rating scale is unverified",
    }
    counts = Counter(
        reason for record in records
        for reason in {issue.get("reason") for issue in record.get("issues", []) if issue.get("reason")}
    )
    return [
        {"reason": reason, "count": count, "label": labels.get(reason, reason.replace("_", " "))}
        for reason, count in sorted(counts.items())
    ]


def observed_amounts_text(observations):
    """Flat exports keep every captured price, not only the comparison scalar."""
    return " | ".join(
        f"{item.get('raw') or item.get('amount', '')} — "
        f"{item.get('label') or str(item.get('kind', 'unknown')).replace('_', ' ')}"
        + ("; original/crossed out" if item.get("role") == "original" else "")
        + ("; selected for comparison" if item.get("selected") else "")
        for item in observations
    ) or None


def pricing_columns(columns, rows):
    source = [column.model_dump() for column in columns]
    applicable = any(
        row.get("pricing") and row["pricing"].get("status") != "not_applicable"
        for row in rows
    )
    return source + (PRICING_COLUMNS if applicable else [])


def pricing_field_statuses(reports, rows):
    """Computed fields do not gain forged source quotes or source-verified labels."""
    by_id = {row["listing_id"]: row for row in rows}
    for report in reports:
        row = by_id[report["record_id"]]
        if row.get("pricing"):
            report["fields"].update(
                {
                    column["name"]: {
                        "status": "computed"
                        if row.get(column["name"]) is not None else "unverified",
                        "reason": "Derived from reviewed source pricing and returned stay scope.",
                    }
                    for column in PRICING_COLUMNS
                }
            )
    return reports


def apply_pricing_rules(rows, rules):
    compared = apply_query_rules([pricing_comparison_record(row) for row in rows], rules)
    return [
        {**row, **{f"rule_{rule.name}": result[f"rule_{rule.name}"] for rule in rules}}
        for row, result in zip(rows, compared, strict=True)
    ]


def pricing_source_pages(pages):
    """Persist assessment inputs, not a stale model conclusion, without duplicate bodies."""
    return [
        {
            "url": page["url"],
            "blocks": page.get("blocks", []),
            **({"text": page.get("text", "")} if not page.get("blocks") else {}),
            **(
                {"browser_task_context": page["browser_task_context"]}
                if page.get("browser_task_context")
                else {}
            ),
            **({"source_kind": page["source_kind"]} if page.get("source_kind") else {}),
        }
        for page in pages
    ]


def saved_pricing_pages(proposal):
    stored = proposal.get("pricing_sources")
    if stored:
        return [
            {
                **page,
                "text": page.get("text")
                or "\n".join(block.get("text", "") for block in page.get("blocks", [])),
            }
            for page in stored
        ]
    # Legacy pending previews have only capture summaries plus source blocks. They
    # must pass current verification; a pre-submit checklist is not returned scope.
    return [
        {
            **page,
            "url": proposal.get("urls", [])[index]
            if index < len(proposal.get("urls", []))
            else page["source_url"],
            "blocks": proposal.get("source_blocks", [])[index]
            if index < len(proposal.get("source_blocks", []))
            else [],
            "text": "\n".join(
                block.get("text", "")
                for block in (
                    proposal.get("source_blocks", [])[index]
                    if index < len(proposal.get("source_blocks", []))
                    else []
                )
            ),
        }
        for index, page in enumerate(proposal.get("captured_pages", []))
    ]


def now():
    return datetime.now(UTC).isoformat()


def output_field_statuses(rows, columns, model_columns, field_issues):
    """Explain nulls without claiming the original website lacks a value."""
    reports = []
    for row in rows:
        issues = {
            issue["field"]: issue["reason"]
            for item in field_issues
            if item["record_id"] == row["listing_id"]
            for issue in item["issues"]
        }
        fields = {}
        for column in columns:
            name = column.name
            populated = row.get(name) not in (None, "")
            status = (
                "source_verified"
                if populated
                else "validation_failed"
                if name in issues
                else ("model_not_returned" if name not in model_columns else "not_extracted")
            )
            fields[name] = {
                "status": status,
                "reason": issues.get(
                    name,
                    (
                        "No value extracted; source availability is unconfirmed."
                        if not populated
                        else ""
                    ),
                ),
            }
        reports.append({"record_id": row["listing_id"], "fields": fields})
    return reports


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def write_json(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2)
    if len(content.encode()) > 3_500_000:
        raise WebsiteError(
            "Extraction exceeds the local snapshot limit. Request fewer records/fields."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def browser_diagnostics(control):
    """Keep non-secret capture-time indicators, not later manual browser changes."""
    if control is None:
        return None
    status = control.snapshot()
    return {
        key: status[key]
        for key in (
            "page_health",
            "blocked_resources",
            "blocked_main_navigation",
            "network_failures",
            "section_hops",
            "browser_mode",
            "browser_channel",
            "content_preparation",
            "link_coverage",
            "browser_error",
            "navigation_result",
            "navigation_history",
            "authentication",
            "agent_report",
        )
    }


def capture_summary(pages):
    """Report whether approved pages yielded article-sized content, without body text."""
    return [
        {
            "source_url": safe_display_url(page["url"]),
            "visible_text_chars": len(page.get("text", "")),
            "blocks": len(page.get("blocks", [])),
            "paragraph_blocks": sum(
                block.get("kind") == "paragraph" for block in page.get("blocks", [])
            ),
            **(
                {
                    "headline_blocks": sum(
                        block.get("kind") == "heading"
                        and (
                            block.get("heading_level") == 1
                            or block.get("content_role") == "headline"
                        )
                        for block in page.get("blocks", [])
                    ),
                    "body_paragraph_blocks": sum(
                        block.get("kind") == "paragraph" and block.get("content_role") == "body"
                        for block in page.get("blocks", [])
                    ),
                }
                if any(block.get("content_role") is not None for block in page.get("blocks", []))
                else {}
            ),
            "truncated": bool(page.get("truncated")),
            **({"coverage": page["coverage"]} if page.get("coverage") else {}),
            **({"source_kind": page["source_kind"]} if page.get("source_kind") else {}),
            **({"parent_url": page["parent_url"]} if page.get("parent_url") else {}),
            **({"requested_url": page["requested_url"]} if page.get("requested_url") else {}),
            **(
                {"browser_task_context": page["browser_task_context"]}
                if page.get("browser_task_context")
                else {}
            ),
        }
        for page in pages
    ]


def plan(
    service, values, model_settings, *, session_alive=lambda: True,
    extension_reader=None, browser_control=None,
):
    if model_settings is None:
        raise WebsiteError("Configure your account API key before inspecting a custom website.")
    if values.source == "extension":
        if extension_reader is None or browser_control is None:
            raise WebsiteError("Start an extension workflow from the connected browser side panel.")
        control = browser_control
    else:
        if extension_reader is not None or browser_control is not None:
            raise WebsiteError("Extension controls require an extension source.")
        control = BrowserControl(session_alive) if values.source == "browser" else None

    def operation(progress):
        context = {}

        def inspect():
            if control:
                control.on_agent_diagnostics = lambda diagnostics: (
                    service.remember_agent_diagnostics(job_id, diagnostics)
                )
            context["pages"] = (
                extension_reader(values, control, model_settings)
                if values.source == "extension"
                else read_browser(values, control, model_settings)
                if control
                else (
                    [values.capture.page()]
                    if values.source == "capture"
                    else read_pages(values.urls)
                    if values.source == "public"
                    else [
                        {
                            "url": values.urls[0],
                            "text": values.page_text,
                            "truncated": False,
                        }
                    ]
                )
            )
            context["captured_at"] = (
                values.capture.captured_at.isoformat() if values.capture else now()
            )
            context["captured_pages"] = capture_summary(context["pages"])
            context["source_fingerprint"] = digest(
                [
                    {
                        key: page.get(key)
                        for key in ("url", "text", "blocks", "source_kind", "browser_task_context")
                    }
                    for page in context["pages"]
                ]
            )
            context["browser_diagnostics"] = browser_diagnostics(control)
            report = control.snapshot().get("agent_report") if control else None
            checklist = report.get("task_checklist", {}) if report else {}
            if (
                report
                and report.get("status") == "ready"
                and report.get("collection_outcome") == "empty_results"
                and checklist.get("search_submitted") is True
                and checklist.get("search_response_pending") is False
            ):
                context["empty_results"] = True
                context["model"] = {}
                return
            if not context["pages"]:
                raise WebsiteError("No content was captured. No extraction request was sent.")
            if any(access_challenge(page["text"]) for page in context["pages"]):
                raise WebsiteError(
                    "Captured text appears to be an access restriction. "
                    "Open accessible content before extraction. No model call."
                )

        def extract():
            if (control and control.cancel.is_set()) or not session_alive():
                raise WebsiteError(
                    "Session cancelled before the model call. No extraction request sent."
                )
            if context.get("empty_results"):
                return
            try:
                candidate, metadata = interpret(values, context["pages"], model_settings)
            except APIError:
                raise WebsiteError(
                    "Model call failed. Check account access, quota and model settings. "
                    "No automatic retry; the provider may have incurred usage."
                ) from None
            context.update(
                candidate=candidate,
                model=metadata,
                model_columns={column.name for column in candidate.columns},
            )

        def review():
            if context.get("empty_results"):
                return {
                    "status": "needs_input",
                    "review_outcome": "no_matches",
                    "record_count": 0,
                    "request": values.instructions,
                    "model": {},
                    "review_counts": {"candidates": 0, "matched": 0},
                    "captured_pages": [],
                    "browser_diagnostics": context.get("browser_diagnostics"),
                    "guidance": "The confirmed website search displayed no results. "
                    "No extraction call ran and no records were saved. This describes "
                    "that search response, not every record on the website.",
                }
            candidate = context["candidate"]
            if candidate.outcome != "ready":
                return {
                    "status": candidate.outcome,
                    "guidance": candidate.guidance,
                    "model": context["model"],
                    "captured_pages": context.get("captured_pages", []),
                    "browser_diagnostics": context.get("browser_diagnostics"),
                }
            rejected = []
            field_issues = []
            field_repairs = []
            review_counts = {}
            schema_issues = {}
            candidate, effective, repairs = prepare_extraction(
                candidate, values, schema_issues=schema_issues
            )
            request_coverage = constraint_coverage(
                candidate._requested_constraints, candidate.columns, candidate.filters
            )
            context["request_constraint_coverage"] = request_coverage
            linked = any(page.get("source_kind") == "index" for page in context["pages"])
            rows, excluded = validate_extraction(
                candidate,
                effective,
                context["pages"],
                rejected=rejected,
                schema_issues=schema_issues,
                field_issues=field_issues,
                apply_filters=False,
                enforce_limit=False,
                preserve_sources=linked,
                review_counts=review_counts,
                field_repairs=field_repairs,
            )
            enrichment = None
            if linked:
                rows, enrichment = reconcile_records(
                    rows,
                    context["pages"],
                    candidate.columns,
                    control.snapshot()["link_coverage"] if control else {},
                    protected_fields={c.field for c in candidate.filters + effective.business_rules}
                    | {c.field for rule in candidate.query_rules for c in rule.conditions},
                )
                for link in enrichment["links"]:
                    relevant_issues = [
                        issue
                        for record in rejected
                        if record["source_url"] in {link["url"], link.get("source_url")}
                        for issue in record["issues"]
                    ]
                    if relevant_issues:
                        link["validation_issues"] = relevant_issues
                        if link.get("record_status") == "no_verified_record":
                            link["record_status"] = "validation_failed"
                enrichment["truncated_captures"] = sum(
                    bool(page.get("truncated")) for page in context["pages"]
                )
                context["enrichment"] = enrichment
            pricing_review = assess_pricing(
                rows, context["pages"], values.instructions, candidate.columns
            )
            rows = pricing_review["records"]
            for row in rows:
                if row.get("pricing"):
                    row["pricing_observed_amounts"] = observed_amounts_text(
                        row["pricing"].get("observations", [])
                    )
            pricing_summary = pricing_review["summary"]
            pricing_summary["unknown_reasons"] = criteria_issues_summary(
                pricing_review.get("assessments", [])
            )
            context["pricing_summary"] = pricing_summary
            pricing_metadata = (
                {
                    "pricing_summary": pricing_summary,
                    "criteria_issues_summary": pricing_summary["unknown_reasons"],
                    "stay_scope": pricing_review["stay_scope"],
                    "request_preferences": [
                        item
                        for item in candidate._requested_constraints
                        if item.get("enforcement") == "preference"
                    ],
                }
                if pricing_summary.get("applicable")
                else {}
            )
            report = (context.get("browser_diagnostics") or {}).get("agent_report") or {}
            checklist = report.get("task_checklist") or {}
            information_coverage = (checklist.get("collection_progress") or {}).get(
                "information_coverage"
            )
            collection_coverage = {
                "scope": "captured_pages_only",
                "whole_website_verified": False,
                "captured_pages": len(context["pages"]),
                "detail_pages": sum(
                    page.get("source_kind") == "detail" for page in context["pages"]
                ),
                "truncated_pages": sum(
                    bool(page.get("truncated")) for page in context["pages"]
                ),
                "reported_omitted_text_chars": sum(
                    (page.get("coverage") or {}).get("omitted_text_chars", 0)
                    for page in context["pages"]
                ),
                "information_coverage": information_coverage,
                "information_needs": checklist.get("information_needs", []),
            }
            source_verified_rows = rows
            result_columns = pricing_columns(candidate.columns, rows)

            def readonly_preview(records):
                bounded = records[: values.record_limit]
                selected, contract = select_output_contract(
                    candidate, effective.business_rules, bounded
                )
                bounded = project_output_records(bounded, candidate.columns, selected)
                bounded = annotate_source_coverage(bounded, context["pages"], selected)
                return {
                    "columns": pricing_columns(selected, bounded),
                    "output_contract": contract,
                    "collection_coverage": collection_coverage,
                    "unverified_preview": bounded,
                    "unverified_preview_more_available": len(records) > len(bounded),
                    "field_statuses": pricing_field_statuses(
                        output_field_statuses(
                            bounded,
                            selected,
                            context.get("model_columns", set()),
                            field_issues,
                        ),
                        bounded,
                    ),
                    "source_blocks": [page.get("blocks", []) for page in context["pages"]],
                }

            if request_coverage["issues"]:
                review_counts.update(matched=0, constraint_unverified=len(rows))
                return {
                    "status": "needs_input",
                    "review_outcome": "constraint_unresolved",
                    "request": values.instructions,
                    "review_counts": review_counts,
                    "columns": result_columns,
                    "filters": [c.model_dump() for c in candidate.filters],
                    "request_constraint_coverage": request_coverage,
                    "rejected_records": rejected,
                    "field_issues": field_issues,
                    "field_repairs": field_repairs,
                    **pricing_metadata,
                    **readonly_preview(rows),
                    "model": context["model"],
                    "captured_pages": context.get("captured_pages", []),
                    "browser_diagnostics": context.get("browser_diagnostics"),
                    **({"enrichment": enrichment} if enrichment else {}),
                    "guidance": "The extraction did not preserve every explicit requested "
                    "price/rating comparison. The source-verified preview is read-only, "
                    "not approved against your criteria. Requested bounds remain in constraint "
                    "diagnostics. No unfiltered records were saved; capture the required "
                    "values or revise the request.",
                }
            constraint_unverified = []
            eligible = []
            for row in rows:
                issues = unverified_constraints(row, request_coverage)
                if row.get("pricing", {}).get("status") == "unverified":
                    issues += [
                        {"field": row["pricing"].get("price_field") or "price", "reason": reason}
                        for reason in row["pricing"].get(
                            "issues", ["requested_stay_price_unverified"]
                        )
                    ]
                if issues:
                    constraint_unverified.append(
                        {
                            "record_id": row["listing_id"],
                            "source_url": row["source_url"],
                            "issues": issues,
                        }
                    )
                else:
                    eligible.append(row)
            criteria_summary = criteria_issues_summary(constraint_unverified)
            pricing_metadata["criteria_issues_summary"] = criteria_summary
            accepted = [
                row
                for row in eligible
                if all(
                    matches(pricing_comparison_record(row), condition)
                    for condition in candidate.filters
                )
            ]
            excluded += len(eligible) - len(accepted)
            review_counts["filtered_out"] += len(eligible) - len(accepted)
            review_counts["constraint_unverified"] = len(constraint_unverified)
            rows = accepted
            if enrichment:
                enrichment["excluded_after_enrichment"] = excluded
                enrichment["preview_records"] = len(rows)
            if len(rows) > values.record_limit:
                raise WebsiteError(
                    f"{len(rows)} {'merged' if linked else 'source-verified'} matching records "
                    f"exceed your preview limit of {values.record_limit}. "
                    "Nothing was truncated or saved. Narrow the query or increase "
                    "Maximum records for a new paid run."
                )
            review_counts["matched"] = len(rows)
            review_counts["linked_sources_merged"] = linked
            if pricing_summary.get("applicable"):
                pricing_summary.update(
                    ready_for_review=len(rows),
                    within_target_ready=sum(
                        row.get("pricing", {}).get("budget_status") == "within_target"
                        for row in rows
                    ),
                    outside_target_ready=sum(
                        row.get("pricing", {}).get("budget_status") == "outside_target"
                        for row in rows
                    ),
                )
            if not rows:
                topic = candidate.semantic_selection.topic if candidate.semantic_selection else None
                attention = (
                    review_counts["invalid"] or review_counts["uncertain"] or constraint_unverified
                )
                if constraint_unverified:
                    reasons = "; ".join(
                        f"{item['label']} ({item['count']} records)" for item in criteria_summary
                    )
                    guidance = (
                        f"{len(constraint_unverified)} source-verified candidates need attention: "
                        f"{reasons}. Captured amounts remain in the read-only preview. "
                        "They were not labelled matches or saved. An unknown criterion is "
                        "not a confirmed out-of-range result."
                    )
                elif attention:
                    guidance = (
                        "No records are ready for review: "
                        f"{review_counts['invalid']} failed source/required-field checks and "
                        f"{review_counts['uncertain']} have uncertain topic relevance. "
                        "Unrelated records are counted separately. Review the issues below; "
                        "this does not prove the website has no matching content. No results saved."
                    )
                else:
                    guidance = (
                        f"No {topic} matches found in the captured content. "
                        if topic
                        else "No records match the requested filters in the captured content. "
                        if review_counts["filtered_out"]
                        else "No records were extracted from the captured content. "
                    ) + (
                        "This is limited to the submitted pages, "
                        "not a search of the whole website. "
                        "Start a new browser session and use 'Find relevant links' to review "
                        "relevant pages before extracting. No results saved."
                    )
                return {
                    "status": "needs_input",
                    "review_outcome": "constraint_unresolved"
                    if constraint_unverified
                    else "needs_attention"
                    if attention
                    else "no_matches",
                    "review_counts": review_counts,
                    "request": values.instructions,
                    "columns": result_columns,
                    "filters": [c.model_dump() for c in candidate.filters],
                    "request_constraint_coverage": request_coverage,
                    "constraint_unverified_records": constraint_unverified,
                    **pricing_metadata,
                    **(
                        readonly_preview(
                            [
                                row
                                for row in source_verified_rows
                                if any(
                                    issue["record_id"] == row["listing_id"]
                                    for issue in constraint_unverified
                                )
                            ]
                        )
                        if constraint_unverified
                        else {}
                    ),
                    "semantic_selection": candidate.semantic_selection.model_dump()
                    if candidate.semantic_selection
                    else None,
                    "source_urls": [safe_display_url(page["url"]) for page in context["pages"]],
                    "next_step": "capture_required_fields"
                    if constraint_unverified
                    else "open_browser_for_links",
                    "rejected_records": rejected,
                    "field_issues": field_issues,
                    "field_repairs": field_repairs,
                    "model": context["model"],
                    "captured_pages": context.get("captured_pages", []),
                    "browser_diagnostics": context.get("browser_diagnostics"),
                    **({"enrichment": enrichment} if enrichment else {}),
                    "guidance": guidance,
                }
            output_columns, output_contract = select_output_contract(
                candidate, effective.business_rules, rows
            )
            rows = project_output_records(rows, candidate.columns, output_columns)
            rows = annotate_source_coverage(rows, context["pages"], output_columns)
            result_columns = pricing_columns(output_columns, rows)
            rows = apply_pricing_rules(rows, candidate.query_rules)
            warnings = list(candidate.warnings) + repairs
            if output_contract["omitted_inferred_fields"]:
                warnings.append(
                    "Omitted empty optional inferred fields: "
                    + ", ".join(output_contract["omitted_inferred_fields"])
                    + ". Their availability on the original website is unconfirmed."
                )
            if output_contract["missing_requested_fields"]:
                warnings.append(
                    "Requested fields remain visible but have missing source-verified values: "
                    + ", ".join(output_contract["missing_requested_fields"])
                    + ". Review per-record reasons and capture coverage."
                )
            if pricing_summary.get("applicable"):
                warnings.append(
                    "An unqualified nightly budget is combined for all requested rooms. "
                    "Displayed source amounts remain unchanged; computed nightly amounts "
                    "are labelled and do not prove room availability or quote validity."
                )
                if (
                    pricing_summary.get("outside_target_ready")
                    and pricing_metadata["request_preferences"]
                ):
                    warnings.append(
                        f"{pricing_summary['outside_target_ready']} ready prices are outside the "
                        "approximate target. Verified alternatives may remain visible; "
                        "they are not labelled budget matches."
                    )
            if constraint_unverified:
                warnings.append(
                    f"{len(constraint_unverified)} candidates were excluded because requested "
                    "numeric constraints or their units/basis could not be verified. "
                    "They are not counted as confirmed out-of-range results."
                )
            if enrichment:
                warnings.append(
                    "Starting-page records retained and reconciled with verified detail records. "
                    "Each filled field keeps its source URL; unopened details remain incomplete."
                )
                if enrichment["conflicting_records"]:
                    warnings.append(
                        f"{enrichment['conflicting_records']} records have index/detail conflicts. "
                        "Starting-page values were retained, not silently overwritten. "
                        "Review the alternative values and quotes before accepting partial results."
                    )
                if enrichment["model_coverage_gap"]:
                    warnings.append(
                        "Some captured sources have no safely matched verified record. "
                        "Review linked-page coverage; missing model rows were not invented."
                    )
            if len(candidate.rows) > values.record_limit:
                warnings.append(
                    f"The model proposed {len(candidate.rows)} candidate records; "
                    f"{len(rows)} remained after source checks, deduplication and filters. "
                    "No accepted record was truncated to meet the preview limit."
                )
            unopened_article_links = sum(
                bool(row.get("article_url") and row["article_url"] != row["source_url"])
                for row in rows
            )
            index_preview = (
                not linked
                and len(context["pages"]) == 1
                and (
                    unopened_article_links
                    or (candidate.content_type.lower().startswith("article") and len(rows) > 1)
                )
            )
            if index_preview:
                warnings.append(
                    "Current-page capture only: linked pages were not opened. "
                    "Detail-page content cannot be verified from URLs alone. "
                    "Use 'Find relevant links' in Chromium to open detail pages."
                )
            source_failures = control.snapshot()["capture_failures"] if control else []
            agent_report = control.snapshot().get("agent_report") if control else None
            agent_partial = bool(agent_report and agent_report["status"] != "ready")
            if agent_report:
                warnings.append(
                    "Browser-agent source collection is bounded and AI-directed; "
                    "it does not prove every requested website criterion was applied. "
                    "Review its action evidence and the extracted source fields."
                )
            if agent_partial:
                warnings.append(
                    "The agent paused before completing its task. Only retained captures "
                    "are included; partial-result approval is required."
                )
            for failure in source_failures:
                warnings.append(
                    "Approved linked page not captured: "
                    + failure["url"]
                    + " - "
                    + failure["reason"]
                )
            if candidate.query_rules:
                warnings.append(
                    "Rule columns are computed from reviewed conditions, not quoted "
                    "source facts. Missing required values produce unknown outcomes."
                )
            if values.source == "capture":
                warnings.append(
                    "User-supplied browser snapshot, not an independently verified "
                    "live fetch. Only the captured top-frame content is covered."
                )
            if rejected:
                warnings.append(
                    f"Partial results: {len(rejected)} records rejected. They will not be "
                    "exported, evaluated or published. Explicit partial-result approval required."
                )
            if field_issues:
                warnings.append(
                    f"Partial fields: {len(field_issues)} records had unsupported optional "
                    "values replaced with null. Review each affected field before approval."
                )
            if field_repairs:
                warnings.append(
                    f"Source-backed field corrections: {len(field_repairs)} records. "
                    "Unique captured values or evidence spans were corrected; review the "
                    "original and corrected evidence. No value was invented from a URL."
                )
            if any(page["truncated"] for page in context["pages"]):
                warnings.append(
                    "Source collection reached a text, block or scan limit; coverage is partial."
                )
            for page in context["pages"]:
                coverage = page.get("coverage")
                if not coverage:
                    continue
                omitted = coverage.get("omitted_text_chars", 0)
                if omitted:
                    warnings.append(
                        f"{omitted} visible content characters were omitted by capture limits."
                    )
                if coverage.get("candidate_limit_reached"):
                    warnings.append("The source inventory exceeds the 100-link discovery window.")
                if coverage.get("frames_excluded"):
                    warnings.append(
                        "Embedded frame content was not included in this page's text capture."
                    )
                if not coverage.get("content_settled"):
                    warnings.append("Page content stability was not confirmed before capture.")
                if not coverage.get("at_page_end"):
                    warnings.append(
                        "The collection did not reach the page end; "
                        "additional lazy-loaded content may remain."
                    )
            if candidate.more_records_available:
                warnings.append("The model reports additional records beyond this preview.")
            if candidate.semantic_selection is not None:
                warnings.append(
                    "Topic relevance is an AI assessment supported by a source "
                    "quote, not a deterministic keyword match. Review it."
                )
                if not rows and not rejected:
                    warnings.append("No matching records were found in the captured content.")
            warnings.append(
                "Matching quotes support provenance, not semantic accuracy. "
                "Review every constraint."
            )
            proposal = {
                "plan_id": str(uuid4()),
                "framework": values.framework,
                "kind": "custom-website",
                "source": values.source,
                "urls": [page["url"] for page in context["pages"]] if control else values.urls,
                "request": values.instructions,
                "output_fields": values.output_fields,
                "captured_at": context["captured_at"],
                "source_fingerprint": context.get("source_fingerprint"),
                "created_at": now(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "interpretation": candidate.interpretation,
                "content_type": candidate.content_type,
                "output_contract": output_contract,
                "collection_coverage": collection_coverage,
                "source_columns": [column.model_dump() for column in candidate.columns],
                "columns": result_columns
                + (
                    [
                        {
                            "name": "topic_relevance",
                            "kind": "text",
                            "unit": "",
                            "description": "AI topic selection; source quote attached",
                        },
                        {
                            "name": "relevance_reason",
                            "kind": "text",
                            "unit": "",
                            "description": "AI explanation of topic relevance",
                        },
                    ]
                    if candidate.semantic_selection is not None
                    else []
                )
                + [
                    {
                        "name": f"rule_{rule.name}",
                        "kind": "text",
                        "unit": "",
                        "description": rule.description + " (computed rule outcome)",
                    }
                    for rule in candidate.query_rules
                ],
                "filters": [c.model_dump() for c in candidate.filters],
                "request_constraint_coverage": request_coverage,
                **pricing_metadata,
                **(
                    {"pricing_sources": pricing_source_pages(context["pages"])}
                    if pricing_summary.get("applicable")
                    else {}
                ),
                "constraint_unverified_records": constraint_unverified,
                "semantic_selection": (
                    candidate.semantic_selection.model_dump()
                    if candidate.semantic_selection
                    else None
                ),
                "business_rules": [c.model_dump() for c in effective.business_rules],
                "query_rules": [r.model_dump() for r in candidate.query_rules],
                "publish_event": values.publish_event,
                "records": rows,
                "review_counts": review_counts,
                "rejected_records": rejected,
                "field_issues": field_issues,
                "field_repairs": field_repairs,
                "field_statuses": pricing_field_statuses(
                    output_field_statuses(
                        rows,
                        output_columns,
                        context.get("model_columns", set()),
                        field_issues,
                    ),
                    rows,
                ),
                "partial": bool(
                    rejected
                    or constraint_unverified
                    or field_issues
                    or field_repairs
                    or source_failures
                    or agent_partial
                    or output_contract["missing_requested_fields"]
                    or information_coverage and (
                        information_coverage.get("detail_needed_fields")
                        or information_coverage.get("partial_reason")
                    )
                    or any(page.get("truncated") for page in context["pages"])
                    or enrichment
                    and (
                        enrichment["conflicting_records"]
                        or enrichment["model_coverage_gap"]
                        or enrichment["truncated_captures"]
                    )
                ),
                **({"enrichment": enrichment} if enrichment else {}),
                "source_blocks": [page.get("blocks", []) for page in context["pages"]],
                "evidence_block_ids": evidence_block_ids(rows, context["pages"]),
                "excluded_by_filters": excluded,
                "record_limit": values.record_limit,
                "warnings": warnings,
                "model": context["model"],
                "captured_pages": context.get("captured_pages", []),
                "browser_diagnostics": context.get("browser_diagnostics"),
                "navigation_model": control.snapshot()["navigation_model"] if control else None,
                "discovery_model": control.snapshot()["link_model"] if control else None,
            }
            write_json(
                service.data_dir / "website-plans" / f"{proposal['plan_id']}.json",
                proposal,
            )
            return {
                "status": "awaiting_review",
                "proposal": proposal,
                "revision": digest(proposal),
                "guidance": "Review fields, filters, source evidence and preview rows. "
                "Approval saves this exact snapshot; no fresh page fetch or model call.",
            }

        try:
            return run_steps(
                values.framework,
                [
                    ("inspect_website", inspect),
                    ("extract_content", extract),
                    ("review_content", review),
                ],
                progress,
            )
        except WebsiteError as exc:
            return {
                "status": "needs_input",
                "guidance": str(exc),
                "trace": getattr(exc, "workflow_trace", []),
                "model": context.get("model", {}),
                "captured_pages": context.get("captured_pages", []),
                "browser_diagnostics": context.get("browser_diagnostics")
                or browser_diagnostics(control),
                **({"enrichment": context["enrichment"]} if context.get("enrichment") else {}),
                **(
                    {"request_constraint_coverage": context["request_constraint_coverage"]}
                    if context.get("request_constraint_coverage")
                    else {}
                ),
            }
        except APIError:
            return {
                "status": "failed",
                "guidance": "Model call failed. Check account access, quota "
                "and model settings. No automatic retry; the provider may have incurred usage.",
            }
        finally:
            if control and values.source != "extension":
                control.on_agent_diagnostics = None
                # A retained verification browser has its own owning thread.
                # Finishing extraction must not close it or hide its Close action.
                if control.owner_thread is None:  # Non-browser adapters/fixtures.
                    control.update("closed", "Browser session ended.")
                    forget_browser()
                elif control.worker_closed.is_set():
                    forget_browser()
            elif control:
                control.on_agent_diagnostics = None

    def forget_browser():
        with service.lock:
            if service.browser_controls.get(job_id) is control:
                service.browser_controls.pop(job_id, None)

    # Hold the same lock used by job startup so the control is registered before the worker runs.
    with service.lock:
        job_id = service.submit(
            "custom-plan", values.framework, operation,
            **({"source": "extension"} if values.source == "extension" else {}),
        )
        if control and values.source != "extension":
            control.on_closed = forget_browser
            service.browser_controls[job_id] = control
    return job_id


def load(service, plan_id):
    path = service.data_dir / "website-plans" / f"{UUID(str(plan_id))}.json"
    if path.stat().st_size > 3_500_000:
        raise WebsiteError("Proposal exceeds the allowed size.")
    proposal = json.loads(path.read_text(encoding="utf-8"))
    if proposal["plan_id"] != str(UUID(str(plan_id))):
        raise WebsiteError("Proposal identity mismatch.")
    return proposal


async def publish_summary(service, event):
    """A separate schema/stream; one summary per run, no article bodies or credentials."""
    from nats.js.api import StorageType, StreamConfig
    from nats.js.errors import NotFoundError

    stream = service.broker_stream + "_WEB"
    broker = Broker(url=os.environ.get("NATS_URL", "nats://127.0.0.1:4222"), stream=stream)
    subject = stream.lower() + ".records.matched.v1"
    nc = await connect(broker)
    try:
        js = nc.jetstream(timeout=3)
        try:
            info = await js.stream_info(stream)
            if info.config.subjects != [subject]:
                raise WebsiteError("Custom event stream has incompatible subjects.")
        except NotFoundError:
            await js.add_stream(
                config=StreamConfig(
                    name=stream,
                    subjects=[subject],
                    storage=StorageType.FILE,
                    max_age=86400,
                    max_msgs=10000,
                    max_bytes=50_000_000,
                    duplicate_window=120,
                )
            )
        ack = await js.publish(
            subject,
            json.dumps(event).encode(),
            headers={"Nats-Msg-Id": event["event_id"]},
            timeout=3,
        )
        return {
            "published": 1,
            "event_id": event["event_id"],
            "subject": subject,
            "stream_sequence": ack.seq,
            "broker_acknowledged": True,
            "consumer_receipt_verified": False,
        }
    finally:
        await nc.close()


def execute(service, plan_id, approval, *, accept_partial=False):
    proposal = load(service, plan_id)
    if digest(proposal) != approval:
        raise WebsiteError("Proposal changed. Review a fresh proposal before approval.")
    if proposal.get("partial") and not accept_partial:
        raise WebsiteError("Explicit approval of partial results is required.")
    # Previously created previews must not bypass newly enforced request coverage.
    source_columns = [
        Column.model_validate({key: item[key] for key in ("name", "kind", "unit", "description")})
        for item in proposal.get("source_columns", proposal["columns"])
        if not item["name"].startswith(("rule_", "pricing_"))
        and not item.get("computed")
    ]
    request_coverage = constraint_coverage(
        requested_constraints(proposal.get("request", "")),
        source_columns,
        [Condition.model_validate(item) for item in proposal["filters"]],
    )
    pricing_review = assess_pricing(
        proposal["records"],
        saved_pricing_pages(proposal),
        proposal.get("request", ""),
        source_columns,
    )
    for row in pricing_review["records"]:
        if row.get("pricing"):
            row["pricing_observed_amounts"] = observed_amounts_text(
                row["pricing"].get("observations", [])
            )
    if not pricing_review["summary"].get("applicable") and any(
        "pricing" in row or any(column["name"] in row for column in PRICING_COLUMNS)
        for row in proposal["records"]
    ):
        raise WebsiteError(
            "This preview contains stale pricing metadata. Create a fresh preview; "
            "no records were saved or events published."
        )
    if pricing_review["summary"].get("applicable"):
        pricing_keys = ("pricing",) + tuple(column["name"] for column in PRICING_COLUMNS)
        if (
            proposal.get("pricing_summary", {}).get("contract_version") != PRICING_CONTRACT_VERSION
            or any(
                row.get("pricing", {}).get("status") != "verified"
                for row in pricing_review["records"]
            )
            or any(
                any(original.get(key) != assessed.get(key) for key in pricing_keys)
                for original, assessed in zip(
                    proposal["records"], pricing_review["records"], strict=True
                )
            )
        ):
            raise WebsiteError(
                "This preview does not independently verify the returned stay and price basis. "
                "Create a fresh preview; no records were saved or events published."
            )
    if request_coverage["issues"] or any(
        unverified_constraints(row, request_coverage) for row in pricing_review["records"]
    ):
        raise WebsiteError(
            "This preview does not verify every requested numeric criterion or its units/basis. "
            "Create a fresh preview; no records were saved or events published."
        )

    def operation(progress):
        context = {}

        def validate():
            latest = load(service, plan_id)
            if digest(latest) != approval or datetime.fromisoformat(
                latest["expires_at"]
            ) <= datetime.now(UTC):
                raise WebsiteError("Proposal expired or changed. Create a new preview.")
            marker = service.data_dir / "website-plans" / f"{UUID(plan_id)}.attempt"
            try:
                with marker.open("x", encoding="utf-8") as handle:
                    handle.write(now())
            except FileExistsError:
                raise WebsiteError(
                    "This proposal already had an execution attempt. Inspect history."
                ) from None
            context["run_id"] = str(uuid4())

        def save():
            rows = [{**row, "extracted_at": proposal["captured_at"]} for row in proposal["records"]]
            snapshot = {
                "run_id": context["run_id"],
                "columns": ["listing_id"]
                + [c["name"] for c in proposal["columns"]]
                + (
                    [
                        "record_url",
                        "detail_status",
                        "evidence_sources",
                        "enrichment_conflicts",
                    ]
                    if proposal.get("enrichment")
                    else []
                )
                + ["source_url", "extracted_at", "evidence"],
                "source": proposal["source"],
                "records": rows,
                "captured_at": proposal["captured_at"],
                "filters": proposal["filters"],
                "request_constraint_coverage": request_coverage,
                "output_contract": proposal.get("output_contract"),
                "collection_coverage": proposal.get("collection_coverage"),
                **(
                    {
                        "pricing_summary": proposal["pricing_summary"],
                        "stay_scope": proposal.get("stay_scope"),
                        "request_preferences": proposal.get("request_preferences", []),
                        "computed_columns": PRICING_COLUMNS,
                    }
                    if proposal.get("pricing_summary", {}).get("applicable")
                    else {}
                ),
                "constraint_unverified_records": proposal.get("constraint_unverified_records", []),
                "semantic_selection": proposal.get("semantic_selection"),
                "warnings": proposal["warnings"],
                **({"enrichment": proposal["enrichment"]} if proposal.get("enrichment") else {}),
                "captured_pages": proposal.get("captured_pages", []),
                "partial": proposal.get("partial", False),
                "rejected_count": len(proposal.get("rejected_records", [])),
                "field_issues": proposal.get("field_issues", []),
                "field_repairs": proposal.get("field_repairs", []),
                "field_statuses": proposal.get("field_statuses", []),
                "output_fields": proposal.get("output_fields", []),
                "source_fingerprint": proposal.get("source_fingerprint"),
                "review_counts": proposal.get("review_counts"),
                "query_rules": proposal.get("query_rules", []),
                "business_rules": proposal["business_rules"],
            }
            # Parameters only, no model-generated SQL. Full typed JSON remains the source of truth.
            with sqlite3.connect(service.data_dir / "website-records.sqlite3") as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS website_runs "
                    "(run_id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)"
                )
                db.execute(
                    "INSERT INTO website_runs VALUES (?, ?)",
                    (context["run_id"], json.dumps(snapshot, ensure_ascii=False)),
                )
            write_json(service.data_dir / "exports" / f"{context['run_id']}.json", snapshot)
            context["records"] = rows
            return {
                "run_id": context["run_id"],
                "record_count": len(rows),
                "framework": proposal["framework"],
            }

        def evaluate():
            rules = [Condition.model_validate(item) for item in proposal["business_rules"]]
            query_rules = [
                QueryRule.model_validate(item) for item in proposal.get("query_rules", [])
            ]
            evaluated_rows = apply_pricing_rules(context["records"], query_rules)

            def qualifies(row):
                return all(matches(pricing_comparison_record(row), rule) for rule in rules) and (
                    not query_rules
                    or any(row[f"rule_{rule.name}"] == "matched" for rule in query_rules)
                )

            decisions = (
                [
                    {
                        "listing_id": row["listing_id"],
                        "matched": qualifies(row),
                        "reasons": [
                            f"{rule.field} {rule.operator} {rule.value}"
                            for rule in rules
                            if not matches(pricing_comparison_record(row), rule)
                        ]
                        + [
                            f"{rule.name}: {row[f'rule_{rule.name}']}"
                            for rule in query_rules
                            if row[f"rule_{rule.name}"] != "matched"
                        ],
                        "query_rules": {
                            rule.name: row[f"rule_{rule.name}"] for rule in query_rules
                        },
                    }
                    for row in evaluated_rows
                ]
                if rules or query_rules
                else []
            )
            context["matched_ids"] = (
                [d["listing_id"] for d in decisions if d["matched"]]
                if rules or query_rules
                else [r["listing_id"] for r in context["records"]]
            )
            return {
                "evaluation": {
                    "enabled": bool(rules or query_rules),
                    "decisions": decisions,
                    "matched": len(context["matched_ids"]) if rules or query_rules else None,
                    "event_selection": "Any matched query rule AND all manual conditions; "
                    "without rules, all accepted records qualify.",
                }
            }

        def publish():
            delivery = {"published": 0, "enabled": proposal["publish_event"]}
            if proposal["publish_event"] and context["matched_ids"]:
                event = {
                    "type": "website.records.matched.v1",
                    "event_id": str(uuid4()),
                    "run_id": context["run_id"],
                    "created_at": now(),
                    "record_ids": context["matched_ids"],
                    "count": len(context["matched_ids"]),
                }
                event_path = service.data_dir / "website-events" / f"{context['run_id']}.json"
                write_json(event_path, {"status": "pending", "event": event})
                try:
                    delivery = asyncio.run(publish_summary(service, event))
                    write_json(
                        event_path,
                        {
                            "status": "acknowledged",
                            "event": event,
                            "delivery": delivery,
                        },
                    )
                except Exception:
                    return {
                        "status": "failed",
                        "failed_stage": "publish",
                        "delivery": delivery,
                        "guidance": "Records are saved. Event delivery is unconfirmed; inspect the "
                        "saved event and broker before any retry. No automatic replay.",
                    }
            return {
                "status": "completed",
                "delivery": delivery,
                "workflow_verified": False,
                "guidance": "Approved snapshot saved and optional rules evaluated. "
                "Any event count represents broker acknowledgement, not consumer receipt. "
                "Extraction accuracy and site completeness still require human review.",
            }

        try:
            return run_steps(
                proposal["framework"],
                [
                    ("validate_plan", validate),
                    ("save", save),
                    ("evaluate", evaluate),
                    ("publish", publish),
                ],
                progress,
            )
        except WebsiteError as exc:
            return {
                "status": "failed",
                "guidance": str(exc),
                "run_id": context.get("run_id"),
            }
        except Exception:
            return {
                "status": "failed",
                "run_id": context.get("run_id"),
                "guidance": "Execution stopped. Inspect this run's saved files before retrying. "
                "The approval is consumed; no automatic replay.",
            }

    return service.submit(
        "custom-execute", proposal["framework"], operation, plan_id,
        **({"source": "extension"} if proposal.get("source") == "extension" else {}),
    )
