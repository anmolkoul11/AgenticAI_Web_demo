"""Bounded request obligations and preferences; never infer source values.

This recognizer covers explicit price/rating comparisons, not arbitrary natural-language
semantics. The extraction model still interprets the full request in the existing call.
"""

import re
from decimal import Decimal

NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?"
CURRENCY = r"USD|EUR|GBP|CAD|AUD|JPY|US\$|U\.S\. dollars|US dollars|euros|pounds"
PRICE_NAME = re.compile(r"(?:^|_)(?:price|cost|amount)(?:_|$)|nightly_rate|rate_per_night")
RATING_NAME = re.compile(r"(?:^|_)(?:rating|score)(?:_|$)")
QUALIFICATION_NAME = re.compile(
    r"(?:^|_)(?:basis|currency|scale|context|description|label|range|unit|policy|wording|"
    r"id|identifier|reference|code)(?:_|$)"
)
ORIGINAL_PRICE_NAME = re.compile(r"(?:^|_)(?:original|previous|old|list|crossed|struck|savings)(?:_|$)")
CURRENCY_ALIASES = {
    "USD": r"\bUSD\b|US\$|\bU\.?S\.? dollars?\b",
    "EUR": r"\bEUR\b|€|\beuros?\b",
    "GBP": r"\bGBP\b|£|\bpounds?\b",
    "CAD": r"\bCAD\b|CA\$|\bCanadian dollars?\b",
    "AUD": r"\bAUD\b|AU\$|\bAustralian dollars?\b",
    "JPY": r"\bJPY\b|\byen\b",
}


def _selection(instructions):
    parts = []
    for clause in re.split(r"[;\n]", instructions):
        flagged = re.split(r"\b(?:flag|classify|mark|label)\b", clause, maxsplit=1, flags=re.I)
        parts.append(flagged[0])
        if len(flagged) == 2:
            # A subsequent explicitly introduced selection is not part of the flag.
            continuation = re.split(
                r"\b(?:and|but|then)\s+(?=(?:keep|filter|return|select|find|get)\b)",
                flagged[1],
                maxsplit=1,
                flags=re.I,
            )
            if len(continuation) == 2:
                parts.append(continuation[1])
    return "; ".join(parts)


def _constraint(kind, match, conditions, neighborhood, after):
    currency = re.search(rf"\b({CURRENCY})\b|US\$", neighborhood, re.I)
    scale = re.search(rf"(?:out of|/|of)\s*({NUMBER})", after, re.I)
    soft = kind == "price" and bool(
        re.search(r"\b(?:around|about|roughly|approximately|prefer\w*|try)\b", neighborhood, re.I)
    )
    strict = bool(re.search(r"\b(?:only|must|strictly|require|filter|keep)\b", neighborhood, re.I))
    nightly = kind == "price" and bool(
        re.search(r"\bnightly\b|\bper night\b|/\s*night\b", neighborhood, re.I)
    )
    return {
        "kind": kind,
        "request_quote": match.group(),
        "conditions": conditions,
        "currency": _currency(currency.group()) if kind == "price" and currency else None,
        "basis": "nightly" if nightly else None,
        "scale": _number(scale.group(1)) if kind == "rating" and scale else None,
        "enforcement": "preference" if soft and not strict else "hard",
        "room_scope": "per_room"
        if kind == "price" and re.search(r"\bper room\b|/\s*room\b", neighborhood, re.I)
        else "all_rooms"
        if nightly
        else None,
        "taxes_requested": "included"
        if kind == "price" and re.search(
            r"\b(?:including|includes?|with)\s+tax(?:es)?\b", neighborhood, re.I
        )
        else None,
        "fees_requested": "included"
        if kind == "price" and re.search(
            r"\b(?:including|includes?|with)\s+(?:tax(?:es)?\s*(?:and|&)\s*)?"
            r"(?:fees?|charges?)\b", neighborhood, re.I
        )
        else None,
    }


def _number(value):
    rendered = format(Decimal(value.replace(",", "")), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _currency(value):
    lowered = value.lower()
    if lowered in {"us$", "us dollars", "u.s. dollars"}:
        return "USD"
    return {"euros": "EUR", "pounds": "GBP"}.get(lowered, value.upper())


def requested_constraints(instructions):
    """Recognize literal selection comparisons, excluding explicit flagging clauses."""
    constraints = []
    # A requested flag is a query_rule, not an additional selection constraint.
    selection = _selection(instructions)
    range_pattern = re.compile(
        rf"\b(?:(?:between|from|range(?:d|s)?(?:\s+(?:of|from))?|"
        rf"around|about|approximately|roughly|prefer(?:ably)?)\s*)?"
        rf"(?:{CURRENCY})?\s*({NUMBER})\s*(?:{CURRENCY})?\s*(?:and|to|[-–—])\s*"
        rf"(?:{CURRENCY})?\s*({NUMBER})(?:\s*({CURRENCY}))?",
        re.I,
    )
    for match in range_pattern.finditer(selection):
        before = re.split(r"[;\n]", selection[max(0, match.start() - 70) : match.start()])[-1]
        after = selection[match.end() : match.end() + 50]
        neighborhood = before + match.group() + after
        labels = re.findall(
            r"\b(?:price|prices|priced|cost|costs|budget|rating|ratings|score|"
            r"dates?|check[- ]?in|check[- ]?out|adults?|rooms?|nights?)\b",
            before,
            re.I,
        )
        label = labels[-1].lower() if labels else ""
        # Currency on this range establishes monetary intent even without 'price'.
        # The nearest label matters: an earlier rating must not absorb a price range,
        # and an earlier price must not turn subsequent date/occupancy ranges into prices.
        kind = (
            "price"
            if re.search(CURRENCY, match.group(), re.I)
            else "rating"
            if label in {"rating", "ratings", "score"}
            else "price"
            if label in {"price", "prices", "priced", "cost", "costs", "budget"}
            else None
        )
        if not kind:
            continue
        lower, upper = _number(match.group(1)), _number(match.group(2))
        strict_range = bool(re.search(r"\bexclusive\b|\bstrictly between\b", neighborhood, re.I))
        constraints.append(
            _constraint(
                kind,
                match,
                [
                    {"operator": "gt" if strict_range else "gte", "value": lower},
                    {"operator": "lt" if strict_range else "lte", "value": upper},
                ],
                neighborhood,
                after,
            )
        )
    paired_bounds = re.compile(
        rf"\b(?:price|prices|priced|cost|costs|budget)\b\s*"
        rf"(?P<low>min(?:imum)?|at least)\s*(?:of|at|as)?\s*(?:{CURRENCY})?\s*"
        rf"(?P<lower>{NUMBER})\s*(?:{CURRENCY})?\s*(?:and|,)?\s*"
        rf"(?P<high>max(?:imum)?|at most)\s*(?:of|at|as)?\s*(?:{CURRENCY})?\s*"
        rf"(?P<upper>{NUMBER})\s*(?:{CURRENCY})?",
        re.I,
    )
    paired_spans = []
    for match in paired_bounds.finditer(selection):
        paired_spans.append(match.span())
        after = selection[match.end() : match.end() + 50]
        constraints.append(
            _constraint(
                "price",
                match,
                [
                    {"operator": "gte", "value": _number(match["lower"])},
                    {"operator": "lte", "value": _number(match["upper"])},
                ],
                match.group() + after,
                after,
            )
        )
    bound_pattern = re.compile(
        rf"\b(?P<label>price|prices|cost|budget|rating|ratings|score)\b"
        rf"\s*(?:of|as|is|at|must be)?\s*(?P<op>at least|at most|above|below|"
        rf"over|under|minimum(?: of)?|maximum(?: of)?|min(?:imum)?|max(?:imum)?)"
        rf"\s*(?:of|at|as)?\s*(?:{CURRENCY})?\s*(?P<value>{NUMBER})",
        re.I,
    )
    leading_pattern = re.compile(
        rf"\b(?P<op>minimum|max(?:imum)?|min|at least|at most)\s+"
        rf"(?P<label>price|prices|cost|budget|rating|ratings|score)\b"
        rf"\s*(?:of|as|is|at)?\s*(?:{CURRENCY})?\s*(?P<value>{NUMBER})",
        re.I,
    )
    for pattern in (bound_pattern, leading_pattern):
        for match in pattern.finditer(selection):
            if any(start <= match.start() < end for start, end in paired_spans):
                continue
            kind = "rating" if match["label"].lower() in {"rating", "ratings", "score"} else "price"
            op = match["op"].lower()
            operator = (
                "gt"
                if op in {"above", "over"}
                else "lt"
                if op in {"below", "under"}
                else "lte"
                if op.startswith("max") or op == "at most"
                else "gte"
            )
            nearby = selection[match.start() : match.end() + 50]
            constraint = _constraint(
                kind,
                match,
                [{"operator": operator, "value": _number(match["value"])}],
                nearby,
                selection[match.end() : match.end() + 50],
            )
            if constraint not in constraints:
                constraints.append(constraint)
    return constraints


def _primary_field(kind, columns, *, nightly=False, numeric_only=True):
    pattern = PRICE_NAME if kind == "price" else RATING_NAME
    candidates = [
        column.name for column in columns
        if (not numeric_only or column.kind == "number") and pattern.search(column.name)
        and not QUALIFICATION_NAME.search(column.name)
        and not (kind == "price" and ORIGINAL_PRICE_NAME.search(column.name))
    ]
    if kind == "price" and "price" in candidates:
        return "price"  # primary query slot; source assessment still proves its basis
    if kind == "price" and nightly:
        matching = [name for name in candidates if re.search(r"night|nightly", name)]
        if len(matching) == 1:
            return matching[0]
        candidates = [name for name in candidates if not re.search(r"(?:^|_)(?:total|stay)(?:_|$)", name)]
    return candidates[0] if len(candidates) == 1 else None


def constraint_fields(constraints, columns):
    """Select only unambiguous semantic fields; ambiguous price variants need review."""
    fields = {}
    for kind in {item["kind"] for item in constraints}:
        fields[kind] = _primary_field(
            kind, columns,
            nightly=any(item["kind"] == kind and item.get("basis") == "nightly" for item in constraints),
        )
    return fields


def constraint_dependencies(constraints, columns):
    fields = constraint_fields(constraints, columns)
    dependencies = {}
    names = [column.name for column in columns]
    for item in constraints:
        # A numeric dependency also defines the type of an existing, unambiguous
        # field. Do not add an empty `price` beside a populated text `displayed_price`.
        field = fields[item["kind"]] or _primary_field(
            item["kind"], columns, nightly=item.get("basis") == "nightly", numeric_only=False
        ) or item["kind"]
        dependencies[field] = "number"
        for key, fallback in (
            ("currency", "currency"),
            ("basis", "price_basis"),
            ("scale", "rating_scale"),
        ):
            if item[key]:
                for name in [name for name in names if key in name] or [fallback]:
                    dependencies[name] = "text"
    return dependencies


def constraint_coverage(constraints, columns, filters):
    """Check literal bounds survived interpretation; stricter/looser bounds are not equivalent."""
    fields = constraint_fields(constraints, columns)
    issues = []
    for item in constraints:
        if item.get("enforcement") == "preference":
            continue
        field = fields[item["kind"]]
        if field is None:
            issues.append({"field": item["kind"], "reason": "missing_or_ambiguous_numeric_field"})
            continue
        for condition in item["conditions"]:
            if not any(
                c.field == field
                and c.operator == condition["operator"]
                and _number(c.value) == condition["value"]
                for c in filters
                if re.fullmatch(NUMBER, c.value)
            ):
                issues.append(
                    {
                        "field": field,
                        "reason": "requested_filter_not_preserved",
                        **condition,
                        "request_quote": item["request_quote"],
                    }
                )
    return {
        "recognized": constraints,
        "fields": fields,
        "issues": issues,
        "recognition_scope": (
            "Literal price/rating bounds and price preferences; not arbitrary query semantics."
        ),
    }


def unverified_constraints(record, coverage):
    """Per-record quotes—not schema units or browser search scope—must establish basis."""
    issues = []
    evidence = record.get("evidence", {})
    provenance = record.get("evidence_sources", {})
    for item in coverage["recognized"]:
        if item.get("enforcement") == "preference":
            continue
        field = coverage["fields"][item["kind"]]
        pricing = record.get("pricing")
        if (
            item["kind"] == "price" and pricing is not None
            and pricing.get("status") != "not_applicable"
        ):
            if pricing.get("status") != "verified":
                issues.append({"field": field, "reason": "requested_pricing_unverified"})
                continue
            if item["currency"] and pricing.get("currency") != item["currency"]:
                issues.append({"field": field, "reason": "requested_currency_unverified"})
            if item["basis"] and pricing.get("comparison_amount") is None:
                issues.append({"field": field, "reason": "requested_nightly_basis_unverified"})
            if item.get("room_scope") and pricing.get("comparison_scope") != item["room_scope"]:
                issues.append({"field": field, "reason": "requested_room_price_scope_unverified"})
            if item.get("taxes_requested") and pricing.get("taxes") != item["taxes_requested"]:
                issues.append({"field": field, "reason": "requested_taxes_unverified"})
            if item.get("fees_requested") and pricing.get("fees_status") != item["fees_requested"]:
                issues.append({"field": field, "reason": "requested_fees_unverified"})
            continue
        if record.get(field) is None:
            issues.append({"field": field, "reason": "required_constraint_value_unavailable"})
            continue
        literal = evidence.get(field, "")
        value_source = provenance.get(field, {}).get("source_url", record.get("source_url"))

        def bound_auxiliary(keyword, source=value_source):
            return [
                name
                for name in record
                if keyword in name
                and evidence.get(name)
                and provenance.get(name, {}).get("source_url", record.get("source_url")) == source
            ]

        if item["currency"]:
            currency_text = (
                literal + " " + " ".join(evidence[name] for name in bound_auxiliary("currency"))
            )
            if not re.search(CURRENCY_ALIASES[item["currency"]], currency_text, re.I):
                issues.append({"field": field, "reason": "requested_currency_unverified"})
        if item["basis"]:
            basis_text = (
                literal + " " + " ".join(evidence[name] for name in bound_auxiliary("basis"))
            )
            if not re.search(r"\bnightly\b|\bper night\b|/\s*night\b", basis_text, re.I):
                issues.append({"field": field, "reason": "requested_nightly_basis_unverified"})
        if item["scale"]:
            scale_text = (
                literal + " " + " ".join(evidence[name] for name in bound_auxiliary("scale"))
            )
            scales = re.findall(rf"(?:out of|/|\bof)\s*({NUMBER})", scale_text, re.I)
            standalone = [record[name] for name in bound_auxiliary("scale") if record[name]]
            if not any(
                re.fullmatch(NUMBER, value) and _number(value) == item["scale"]
                for value in scales + standalone
            ):
                issues.append({"field": field, "reason": "requested_rating_scale_unverified"})
    return issues
