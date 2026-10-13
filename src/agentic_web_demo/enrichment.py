"""Deterministic reconciliation of already-verified index and detail records.

No fetches, model calls or guessed source facts. URL matches, not topic/title
similarity, connect records. Every filled field keeps its own source evidence.
"""

from copy import deepcopy

from agentic_web_demo.capture import clean_url
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.record_identity import identity_field
from agentic_web_demo.source_fields import normalized

URL_FIELDS = (
    "article_url",
    "hotel_url",
    "listing_url",
    "product_url",
    "property_url",
    "item_url",
    "article_link",
    "detail_url",
    "url",
    "link_url",
)


def safe_url(value):
    try:
        return clean_url(value) if isinstance(value, str) else None
    except (WebsiteError, ValueError):
        return None


def record_target(row, page, names):
    """A declared URL, or one unique URL from the identity's source group."""
    urls = {url for field in URL_FIELDS if field in names and (url := safe_url(row.get(field)))}
    if urls:
        return next(iter(urls)) if len(urls) == 1 else None
    identity = identity_field(names)
    quote = row.get("evidence", {}).get(identity)
    if not quote:
        return None
    matching = [b for b in page.get("blocks", []) if normalized(quote) in normalized(b["text"])]
    groups = {b["group_id"] for b in matching if b.get("group_id")}
    urls = {
        url
        for b in page.get("blocks", [])
        if (b in matching or b.get("group_id") in groups) and (url := safe_url(b.get("href")))
    }
    return next(iter(urls)) if len(urls) == 1 else None


def provenance(row, page):
    return {
        field: {
            "source_url": page["url"],
            "block_ids": [
                block["id"]
                for block in page.get("blocks", [])
                if normalized(quote) in normalized(block["text"] + " " + (block.get("href") or ""))
            ],
        }
        for field, quote in row.get("evidence", {}).items()
        if quote and row.get(field) is not None
    }


def reconcile_records(records, pages, columns, link_coverage, *, protected_fields=()):
    """Fill missing index fields only; disclose conflicts and unmatched details.

    Returns records before user filters and a reviewable coverage report. Missing
    model rows are reported, never manufactured from a selected headline.
    """
    names = [column.name for column in columns]
    index = next((page for page in pages if page.get("source_kind") == "index"), None)
    if index is None:
        return records, None
    page_by_url = {page["url"]: page for page in pages}
    index_rows, detail_rows = [], []
    for original in records:
        row = deepcopy(original)
        page = page_by_url[row["source_url"]]
        row["evidence_sources"] = provenance(row, page)
        row["enrichment_conflicts"] = {}
        if page.get("source_kind") == "detail":
            urls = {
                url for field in URL_FIELDS if field in names and (url := safe_url(row.get(field)))
            }
            target = next(iter(urls)) if len(urls) == 1 else page["url"] if not urls else None
        else:
            target = record_target(row, page, names)
        row["record_url"] = target
        if page.get("source_kind") == "index":
            row["detail_status"] = "not_opened"
            index_rows.append(row)
        else:
            row["detail_status"] = "detail_only"
            detail_rows.append(row)
    attempts = deepcopy(link_coverage.get("links", []))
    by_target = {}
    for row in index_rows:
        if row["record_url"]:
            by_target.setdefault(row["record_url"], []).append(row)
    for row in index_rows:
        attempt = next((a for a in attempts if a["url"] == row["record_url"]), None)
        if attempt:
            row["detail_status"] = "failed" if attempt["status"] == "failed" else "not_extracted"
    primary_detail_counts = {}
    for row in detail_rows:
        page = page_by_url[row["source_url"]]
        if row["record_url"] in {safe_url(page.get("requested_url")), safe_url(page["url"])}:
            primary_detail_counts[page["url"]] = primary_detail_counts.get(page["url"], 0) + 1
    unmatched, merged = [], 0
    for detail in detail_rows:
        page = page_by_url[detail["source_url"]]
        requested = safe_url(page.get("requested_url"))
        actual = safe_url(page["url"])
        counterparts = by_target.get(requested, [])
        identity = identity_field(names)
        primary_heading = next(
            (b for b in page.get("blocks", []) if b.get("kind") == "heading"), None
        )
        explicit_url = any(
            safe_url(detail.get(field)) in {requested, actual}
            for field in URL_FIELDS
            if field in names and detail.get(field)
        )
        primary_quote = detail.get("evidence", {}).get(identity)
        heading_match = bool(
            primary_heading
            and primary_quote
            and normalized(primary_quote) in normalized(primary_heading["text"])
        )
        # A detail row pointing at a sidebar/another property is not the main
        # record requested by the approved link, even though its quote is real.
        if (
            page.get("parent_url") != index["url"]
            or detail["record_url"] not in {requested, actual}
            or len(counterparts) != 1
            or primary_detail_counts.get(page["url"]) != 1
            or not (explicit_url or heading_match)
        ):
            unmatched.append(detail)
            continue
        baseline = counterparts[0]
        for field in names:
            incoming = detail.get(field)
            existing = baseline.get(field)
            if incoming is None:
                continue
            if existing is None:
                baseline[field] = incoming
                baseline["evidence"][field] = detail["evidence"].get(field, "")
                baseline["evidence_sources"][field] = detail["evidence_sources"].get(field, {})
            elif normalized(existing) != normalized(incoming):
                baseline["enrichment_conflicts"][field] = {
                    "retained_value": existing,
                    "retained_quote": baseline["evidence"].get(field, ""),
                    "retained_source": baseline["evidence_sources"].get(field, {}),
                    "detail_value": incoming,
                    "detail_source": detail["evidence_sources"].get(field, {}),
                    "detail_quote": detail["evidence"].get(field, ""),
                }
        baseline["detail_status"] = "conflict" if baseline["enrichment_conflicts"] else "enriched"
        if set(baseline["enrichment_conflicts"]).intersection(protected_fields):
            # A conflicting price/rating used by the query must not disappear
            # because an index value was preferred. Keep both source variants
            # so filters/rules evaluate each actual observed value separately.
            detail["detail_status"] = "conflict"
            detail["enrichment_conflicts"] = deepcopy(baseline["enrichment_conflicts"])
            unmatched.append(detail)
        merged += 1
    rows = index_rows + unmatched
    represented = {row["record_url"] for row in rows if row["record_url"]}
    for attempt in attempts:
        targets = by_target.get(attempt["url"], [])
        attempt["record_status"] = (
            targets[0]["detail_status"]
            if len(targets) == 1
            else "ambiguous_index_match"
            if len(targets) > 1
            else "detail_only"
            if attempt["url"] in represented or attempt.get("source_url") in represented
            else "no_verified_record"
        )
    report = {
        "index_url": index["url"],
        "index_retained": True,
        "verified_index_records": len(index_rows),
        "merged_counterparts": merged,
        "enriched_records": sum(row["detail_status"] == "enriched" for row in index_rows),
        "index_only_records": sum(
            row["detail_status"] not in {"enriched", "conflict"} for row in index_rows
        ),
        "detail_only_records": len(unmatched),
        "conflicting_records": sum(bool(row["enrichment_conflicts"]) for row in index_rows),
        "approved": len(attempts),
        "captured": sum(a["status"] == "captured" for a in attempts),
        "failed": sum(a["status"] == "failed" for a in attempts),
        "links": attempts,
        "model_coverage_gap": not index_rows
        or any(
            a["record_status"] in {"no_verified_record", "ambiguous_index_match", "not_extracted"}
            for a in attempts
        ),
    }
    return rows, report


def evidence_block_ids(records, pages):
    """Block IDs are page-local; expose URLs alongside them in evidence_sources."""
    result = {}
    for row in records:
        result[row["listing_id"]] = {}
        for field, quote in row.get("evidence", {}).items():
            source = (
                row.get("evidence_sources", {}).get(field, {}).get("source_url", row["source_url"])
            )
            result[row["listing_id"]][field] = [
                block["id"]
                for page in pages
                if page["url"] == source
                for block in page.get("blocks", [])
                if quote
                and normalized(quote) in normalized(block["text"] + " " + (block.get("href") or ""))
            ]
    return result
