"""Useful display fields selected from validated rows, never a fixed website template.

This is a local projection, not another model call. Source assessment still uses
the original schema; explicit fields and rule/filter dependencies cannot disappear.
"""

import re
from copy import deepcopy

from agentic_web_demo.enrichment import URL_FIELDS, safe_url
from agentic_web_demo.record_identity import identity_field
from agentic_web_demo.result_presentation import field_family, presentation_contract


def primary_url_field(names, rows):
    """Presentation only: prefer a known link or one unambiguous custom URL slot."""
    populated = {
        name for name in names
        if any(safe_url(row.get(name)) for row in rows)
    }
    known = next((name for name in URL_FIELDS if name in populated), None)
    if known:
        return known
    custom = [name for name in names if name.endswith("_url") and name in populated]
    if len(custom) == 1:
        return custom[0]
    return None


def select_output_contract(candidate, business_rules, rows):
    explicit = set(getattr(candidate, "_explicit_output_fields", ()))
    protected = explicit | set(candidate.requested_fields)
    dependencies = {
        item.field for item in candidate.filters + list(business_rules)
    } | {
        item.field for rule in candidate.query_rules for item in rule.conditions
    }
    protected.update(dependencies)
    selected, omitted = [], []
    coverage = []
    for column in candidate.columns:
        populated = sum(row.get(column.name) not in (None, "") for row in rows)
        if column.name in protected or populated:
            selected.append(column)
            coverage.append({
                "field": column.name,
                "requested": column.name in explicit,
                "populated": populated,
                "missing": len(rows) - populated,
            })
        else:
            omitted.append(column.name)
    selected_names = [column.name for column in selected]
    description = next(
        (column.name for column in selected if field_family(column) == "overview"
         and re.search(r"(?:description|snippet|excerpt|context|summary|overview)$", column.name)),
        None,
    )
    return selected, {
        "version": "dynamic-fields-v1",
        "selection": "User intent and source-verified captured content; no fixed site template.",
        "content_type": candidate.content_type,
        "requested_fields": [column.name for column in candidate.columns if column.name in explicit],
        "dependency_fields": [column.name for column in candidate.columns if column.name in dependencies],
        "selected_fields": selected_names,
        "identity_field": identity_field(selected_names) if selected_names else None,
        "description_field": description,
        "url_field": primary_url_field(selected_names, rows),
        "presentation": presentation_contract(selected),
        "omitted_inferred_fields": omitted,
        "field_coverage": coverage,
        "missing_requested_fields": [
            item["field"] for item in coverage if item["requested"] and item["missing"]
        ],
        "note": "Missing means not source-verified in this capture, not absent from the website.",
    }


def project_output_records(rows, source_columns, selected_columns):
    """Remove only empty optional source slots; preserve server-owned metadata."""
    omitted = {column.name for column in source_columns} - {
        column.name for column in selected_columns
    }
    if not omitted:
        return rows
    projected = deepcopy(rows)
    for row in projected:
        for field in omitted:
            row.pop(field, None)
            for key in ("evidence", "evidence_sources", "enrichment_conflicts"):
                if isinstance(row.get(key), dict):
                    row[key].pop(field, None)
    return projected
