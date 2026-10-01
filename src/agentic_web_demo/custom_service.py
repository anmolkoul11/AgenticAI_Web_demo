"""Private proposals, human approval, local records and optional summary events."""

import asyncio
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from openai import APIError

from agentic_web_demo.browser_links import safe_display_url
from agentic_web_demo.custom_browser import (
    BrowserControl,
    access_challenge,
    read_browser,
)
from agentic_web_demo.custom_extract import (
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
from agentic_web_demo.messaging import Broker, connect


def now():
    return datetime.now(UTC).isoformat()


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
    """Keep only non-secret load indicators after the visible browser closes."""
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
            "truncated": bool(page.get("truncated")),
        }
        for page in pages
    ]


def plan(service, values, model_settings, *, session_alive=lambda: True):
    if model_settings is None:
        raise WebsiteError("Configure your account API key before inspecting a custom website.")
    control = BrowserControl(session_alive) if values.source == "browser" else None

    def operation(progress):
        context = {}

        def inspect():
            context["pages"] = (
                read_browser(values, control, model_settings)
                if control
                else (
                    [values.capture.page()]
                    if values.source == "capture"
                    else read_pages(values.urls)
                    if values.source == "public"
                    else [{"url": values.urls[0], "text": values.page_text, "truncated": False}]
                )
            )
            context["captured_at"] = (
                values.capture.captured_at.isoformat() if values.capture else now()
            )
            context["captured_pages"] = capture_summary(context["pages"])
            context["browser_diagnostics"] = browser_diagnostics(control)
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
            try:
                candidate, metadata = interpret(values, context["pages"], model_settings)
            except APIError:
                raise WebsiteError(
                    "Model call failed. Check account access, quota and model settings. "
                    "No automatic retry; the provider may have incurred usage."
                ) from None
            context.update(candidate=candidate, model=metadata)

        def review():
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
            schema_issues = {}
            candidate, effective, repairs = prepare_extraction(
                candidate, values, schema_issues=schema_issues
            )
            rows, excluded = validate_extraction(
                candidate,
                effective,
                context["pages"],
                rejected=rejected,
                schema_issues=schema_issues,
                field_issues=field_issues,
            )
            if rejected and not rows:
                return {
                    "status": "needs_input",
                    "rejected_records": rejected,
                    "field_issues": field_issues,
                    "model": context["model"],
                    "captured_pages": context.get("captured_pages", []),
                    "browser_diagnostics": context.get("browser_diagnostics"),
                    "guidance": "No source-verified records remain after validation and filters. "
                    "Review rejected fields or capture more relevant content. No results saved.",
                }
            rows = apply_query_rules(rows, candidate.query_rules)
            warnings = list(candidate.warnings) + repairs
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
            index_preview = len(context["pages"]) == 1 and (
                unopened_article_links
                or (candidate.content_type.lower().startswith("article") and len(rows) > 1)
            )
            if index_preview:
                warnings.append(
                    "Current-page capture only: linked article pages were not opened. "
                    "Article-body context cannot be verified from their URLs. "
                    "Use 'Find relevant links' in Chromium to open detail pages."
                )
            source_failures = control.snapshot()["capture_failures"] if control else []
            for failure in source_failures:
                warnings.append(
                    "Approved linked page not captured: " + failure["url"] + " - " + failure["reason"]
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
            if any(page["truncated"] for page in context["pages"]):
                warnings.append(
                    "Source text was capped at 24,000 characters per page; coverage is partial."
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
                "captured_at": context["captured_at"],
                "created_at": now(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "interpretation": candidate.interpretation,
                "content_type": candidate.content_type,
                "columns": [c.model_dump() for c in candidate.columns]
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
                "semantic_selection": (
                    candidate.semantic_selection.model_dump()
                    if candidate.semantic_selection
                    else None
                ),
                "business_rules": [c.model_dump() for c in effective.business_rules],
                "query_rules": [r.model_dump() for r in candidate.query_rules],
                "publish_event": values.publish_event,
                "records": rows,
                "rejected_records": rejected,
                "field_issues": field_issues,
                "partial": bool(rejected or field_issues or source_failures),
                "source_blocks": [page.get("blocks", []) for page in context["pages"]],
                "evidence_block_ids": {
                    row["listing_id"]: {
                        field: [
                            block["id"]
                            for page in context["pages"]
                            if page["url"] == row["source_url"]
                            for block in page.get("blocks", [])
                            if quote
                            and " ".join(quote.split())
                            in " ".join((block["text"] + " " + (block.get("href") or "")).split())
                        ]
                        for field, quote in row["evidence"].items()
                    }
                    for row in rows
                },
                "excluded_by_filters": excluded,
                "record_limit": values.record_limit,
                "warnings": warnings,
                "model": context["model"],
                "captured_pages": context.get("captured_pages", []),
                "browser_diagnostics": context.get("browser_diagnostics"),
                "navigation_model": control.snapshot()["navigation_model"] if control else None,
                "discovery_model": control.snapshot()["link_model"] if control else None,
            }
            write_json(service.data_dir / "website-plans" / f"{proposal['plan_id']}.json", proposal)
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
            }
        except APIError:
            return {
                "status": "failed",
                "guidance": "Model call failed. Check account access, quota "
                "and model settings. No automatic retry; the provider may have incurred usage.",
            }
        finally:
            if control:
                control.update("closed", "Browser session ended.")
                with service.lock:
                    service.browser_controls.pop(job_id, None)

    # Hold the same lock used by job startup so the control is registered before the worker runs.
    with service.lock:
        job_id = service.submit("custom-plan", values.framework, operation)
        if control:
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
                + ["source_url", "extracted_at", "evidence"],
                "source": proposal["source"],
                "records": rows,
                "captured_at": proposal["captured_at"],
                "filters": proposal["filters"],
                "semantic_selection": proposal.get("semantic_selection"),
                "warnings": proposal["warnings"],
                "partial": proposal.get("partial", False),
                "rejected_count": len(proposal.get("rejected_records", [])),
                "field_issues": proposal.get("field_issues", []),
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
            evaluated_rows = apply_query_rules(context["records"], query_rules)

            def qualifies(row):
                return all(matches(row, rule) for rule in rules) and (
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
                            if not matches(row, rule)
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
                        event_path, {"status": "acknowledged", "event": event, "delivery": delivery}
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
            return {"status": "failed", "guidance": str(exc), "run_id": context.get("run_id")}
        except Exception:
            return {
                "status": "failed",
                "run_id": context.get("run_id"),
                "guidance": "Execution stopped. Inspect this run's saved files before retrying. "
                "The approval is consumed; no automatic replay.",
            }

    return service.submit("custom-execute", proposal["framework"], operation, plan_id)
