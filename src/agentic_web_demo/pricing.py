"""Source-bound stay pricing. Raw prices are never overwritten or guessed.

A returned search scope describes the requested stay, not availability. A price
must also belong to one unique captured record group and disclose its own basis.
"""

import re
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from agentic_web_demo.custom_constraints import (
    NUMBER, PRICE_NAME, QUALIFICATION_NAME, requested_constraints,
)
from agentic_web_demo.record_identity import identity_field
from agentic_web_demo.source_fields import normalized, quote_in_block
from agentic_web_demo.stay_scope import destination_matches, requested_stay

CONTRACT_VERSION = "stay-pricing-v2"
COMPUTED_FIELDS = (
    "pricing_combined_nightly",
    "pricing_basis",
    "pricing_taxes",
    "pricing_fees",
    "pricing_currency",
    "pricing_budget_status",
    "pricing_observed_amounts",
)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?![\w.])")
_MONEY = re.compile(
    rf"(?:US\$|CA\$|AU\$|[$€£]|USD|EUR|GBP|CAD|AUD|JPY)\s*({NUMBER})"
    rf"|({NUMBER})\s*(?:USD|EUR|GBP|CAD|AUD|JPY)\b",
    re.I,
)
_CHARGE_LIST = (
    r"(?:tax(?:es)?|fees?|charges?)"
    r"(?:\s*(?:,|and|&)\s*(?:tax(?:es)?|fees?|charges?))*"
)
_CURRENCIES = {
    "USD": r"\bUSD\b|US\$|\bU\.?S\.?\s+dollars?\b",
    "EUR": r"\bEUR\b|\beuros?\b|€",
    "GBP": r"\bGBP\b|\bpounds?\b|£",
    "CAD": r"\bCAD\b|CA\$|\bCanadian dollars?\b",
    "AUD": r"\bAUD\b|AU\$|\bAustralian dollars?\b",
    "JPY": r"\bJPY\b|\byen\b",
}
_LABELS = {
    "all_rooms_per_night": "Per night, all requested rooms",
    "per_room_per_night": "Per room, per night",
    "stay_total_all_rooms": "Full-stay total, all requested rooms",
    "stay_total_per_room": "Full-stay total, per room",
    "starting_from": "Starting price; requested-stay price unverified",
    "unknown": "Price basis unverified",
}


def _decimal(value):
    try:
        text = str(value).replace(",", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", text):
            return None
        result = Decimal(text)
        return result if result.is_finite() and 0 <= result < Decimal("1e18") else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _render(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _column(column, key):
    return column.get(key) if isinstance(column, dict) else getattr(column, key)


def _price_fields(columns):
    return [
        _column(column, "name") for column in columns
        if _column(column, "kind") == "number"
        and PRICE_NAME.search(_column(column, "name"))
        and not QUALIFICATION_NAME.search(_column(column, "name"))
    ]


def _price_field(columns, nightly=False):
    fields = [
        name for name in _price_fields(columns)
        if not re.search(r"(?:^|_)(?:original|old|list|previous|crossed_out)(?:_|$)", name)
    ]
    if "price" in fields:
        return "price"
    if nightly:
        specific = [name for name in fields if re.search(r"nightly|per_night", name)]
        if len(specific) == 1:
            return specific[0]
    return fields[0] if len(fields) == 1 else None


def _source_group(record, pages, field, columns):
    """Bind record context before validating an independently optional amount."""
    names = [_column(column, "name") for column in columns]
    identity = identity_field(names) if names else None
    quote = record.get("evidence", {}).get(field, "")
    sources = record.get("evidence_sources", {})
    provenance = sources.get(field) or sources.get(identity) or {}
    source_url = provenance.get("source_url", record.get("source_url"))
    matches = [page for page in pages if page.get("url") == source_url]
    if len(matches) != 1:
        return None, [], "price_source_unavailable"
    page = matches[0]
    blocks = [
        block for block in page.get("blocks", [])
        if block.get("association") != "ambiguous"
    ]
    identity_quote = record.get("evidence", {}).get(identity, "")
    identity_value = record.get(identity)
    identities = {
        block.get("group_id")
        for block in blocks
        if block.get("group_id")
        and block.get("kind") in {"heading", "link", "table_row"}
        and identity_quote
        and normalized(identity_quote) in normalized(block["text"])
        and normalized(identity_value) in normalized(block["text"])
    }
    # Missing or malformed price output must not erase a trustworthy returned
    # stay, currency setting, or record-local raw quote. None establishes a
    # price match until the independent amount/quote checks below also pass.
    if len(identities) != 1:
        return page, [], "price_record_binding_unverified"
    group_id = next(iter(identities))
    context = [block for block in blocks if block.get("group_id") == group_id]
    if field is None:
        return page, context, "missing_or_ambiguous_price_field"
    if not quote:
        return page, context, "price_quote_unavailable"
    price_groups = {
        block.get("group_id")
        for block in blocks
        if block.get("group_id") and quote_in_block(quote, block)
    }
    # A repeated identity or quote in multiple records is not a unique binding.
    groups = identities.intersection(price_groups)
    if len(groups) != 1:
        return page, context, "price_record_binding_unverified"
    amount = _decimal(record.get(field))
    if amount is None or not (
        any(_decimal(value) == amount for value in _NUMBER.findall(quote))
        or amount in _money_amounts(quote)
    ):
        return page, context, "price_amount_quote_unverified"
    return page, context, None


def _currency(blocks, page):
    text = " ".join(block["text"] for block in blocks)
    currencies = {
        code for code, pattern in _CURRENCIES.items() if re.search(pattern, text, re.I)
    }
    if not currencies:
        # Only an explicit displayed currency setting applies globally. A bare $
        # or an unrelated footer mentioning a currency does not establish USD.
        currency_settings = " ".join(
            block["text"]
            for block in page.get("blocks", [])
            if block.get("content_role") == "currency_setting"
            and block.get("association") == "page"
        )
        currencies = {
            code
            for code, pattern in _CURRENCIES.items()
            if re.search(pattern, currency_settings, re.I)
        }
    return next(iter(currencies)) if len(currencies) == 1 else None


def _currency_evidence(blocks, page, currency):
    if currency is None:
        return {"source_url": page.get("url"), "block_ids": [], "quote": ""}
    matching = [
        block for block in blocks if re.search(_CURRENCIES[currency], block["text"], re.I)
    ]
    if not matching:
        matching = [
            block for block in page.get("blocks", [])
            if block.get("content_role") == "currency_setting"
            and block.get("association") == "page"
            and re.search(_CURRENCIES[currency], block["text"], re.I)
        ]
    return {
        "source_url": page.get("url"),
        "block_ids": [block["id"] for block in matching],
        "quote": " | ".join(block["text"] for block in matching)[:1000],
    }


def _charge_disclosure(text, label):
    facts = []
    for match in re.finditer(
        rf"\b(?P<qualifier>includes?|including|with|excludes?|excluding|before)"
        rf"\s+(?P<labels>{_CHARGE_LIST})\b", text, re.I,
    ):
        if re.search(label, match["labels"], re.I):
            excluded = match["qualifier"].casefold().startswith("excl") or match["qualifier"].casefold() == "before"
            facts.append(("excluded" if excluded else "included", match.group()))
    for match in re.finditer(
        rf"\b(?P<labels>{_CHARGE_LIST})\s+(?:are\s+)?"
        rf"(?P<qualifier>not included|included|excluded|extra)\b", text, re.I,
    ):
        if re.search(label, match["labels"], re.I):
            facts.append(("included" if match["qualifier"].casefold() == "included" else "excluded", match.group()))
    for match in re.finditer(
        rf"\+\s*(?:(?:US\$|CA\$|AU\$|[$€£]|USD|EUR|GBP|CAD|AUD|JPY)?"
        rf"\s*{NUMBER}\s*(?:in\s+)?)?(?P<labels>{_CHARGE_LIST})\b", text, re.I,
    ):
        if re.search(label, match["labels"], re.I):
            facts.append(("excluded", match.group()))
    statuses = {status for status, _ in facts}
    return {
        "status": next(iter(statuses)) if len(statuses) == 1 else "unknown",
        "quotes": list(dict.fromkeys(quote for _, quote in facts))[:8],
    }


def _literal_scope(text, requested):
    observed = {}
    for field, label in (("check_in", r"check[- ]?in"), ("check_out", r"check[- ]?out")):
        values = re.findall(
            rf"\b{label}(?:\s+date)?\s*[:=]?\s*(\d{{4}}-\d{{2}}-\d{{2}})\b",
            text, re.I,
        )
        if len(set(values)) == 1:
            observed[field] = values[0]
    for field in ("adults", "children", "rooms"):
        label = r"(?:child|children)" if field == "children" else field[:-1] + "s?"
        values = re.findall(rf"\b(\d+)\s+{label}\b", text, re.I)
        if len(set(values)) == 1:
            observed[field] = int(values[0])
    if requested.get("destination") and re.search(
        rf"(?<!\w){re.escape(str(requested['destination']))}(?!\w)", text, re.I
    ):
        observed["destination"] = requested["destination"]
    return observed


def _equal(field, expected, observed):
    if observed is None:
        return False
    if field == "destination":
        return destination_matches(expected, observed)
    return normalized(expected).casefold() == normalized(observed).casefold()


def _scope(page, blocks, requested):
    meaningful_stay = any(
        requested.get(field) is not None
        for field in ("check_in", "check_out", "adults", "children", "rooms")
    )
    relevant = {
        field: requested[field]
        for field in ("check_in", "check_out", "adults", "children", "rooms", "destination")
        if meaningful_stay and requested.get(field) is not None
    }
    if not relevant:
        return {
            "status": "not_requested", "requested": {}, "observed": {},
            "issues": [], "availability_verified": False,
        }
    browser = (page.get("browser_task_context") or {}).get("result_scope") or {}
    observed = (
        (browser.get("observed") or {})
        if browser.get("source") == "returned_page" else {}
    )
    verified = (
        browser.get("status") == "verified"
        and browser.get("source") == "returned_page"
        and all(
            _equal(field, expected, observed.get(field)) for field, expected in relevant.items()
        )
    )
    text = " ".join(block["text"] for block in blocks)
    literal = _literal_scope(text, requested)
    contradictions = [
        field for field, value in literal.items()
        if field in relevant and not _equal(field, relevant[field], value)
    ]
    for field in ("adults", "children", "rooms"):
        label = r"(?:child|children)" if field == "children" else field[:-1] + "s?"
        values = re.findall(rf"\b(\d+)\s+{label}\b", text, re.I)
        if requested.get(field) is not None and any(
            int(value) != requested[field] for value in values
        ):
            contradictions.append(field)
    nights = set(re.findall(r"\b(\d+)\s+nights?\b", text, re.I))
    if requested.get("nights") is not None and nights and nights != {str(requested["nights"])}:
        contradictions.append("nights")
    if contradictions or browser.get("status") == "mismatch":
        return {
            "status": "mismatch", "requested": relevant,
            "observed": {**observed, **literal}, "issues": ["requested_stay_mismatch"],
            "availability_verified": False,
        }
    if not verified:
        verified = all(
            _equal(field, expected, literal.get(field)) for field, expected in relevant.items()
        )
        # Keep partial returned-page facts for diagnostics, but do not promote
        # their union with literal record text into a verified stay.
        observed = {**observed, **literal}
    return {
        "status": "verified" if verified else "unverified",
        "requested": relevant,
        "observed": observed,
        "issues": [] if verified else ["requested_stay_scope_unverified"],
        "availability_verified": False,
    }


def _basis_from_text(text, scope, requested):
    if re.search(
        r"\b(?:price\s+from|starting\s+(?:from|at)|from\s+(?:US\$|USD|EUR|GBP|\$))",
        text, re.I,
    ):
        return "starting_from"
    per_room = bool(re.search(
        r"\bper room\b|/\s*room\b|\bfor (?:each|one|1) room\b", text, re.I,
    ))
    nightly = bool(re.search(r"\bper night\b|\bnightly\b|/\s*night\b", text, re.I))
    total = bool(re.search(
        r"\b(?:stay total|total(?:\s+(?:price|cost))?|price\s+for\s+\d+\s+nights?)\b",
        text, re.I,
    ))
    if nightly and total:
        return "unknown"
    if nightly:
        if per_room:
            return "per_room_per_night"
        explicit_combined = re.search(r"\b(?:all|both|combined|requested)\s+rooms?\b", text, re.I)
        if (
            explicit_combined or scope["status"] in {"verified", "not_requested"}
            or requested.get("rooms") == 1
        ):
            return "all_rooms_per_night"
    if total:
        if per_room:
            return "stay_total_per_room"
        if scope["status"] == "verified" or re.search(
            r"\b(?:all|both|combined)\s+rooms?\b", text, re.I,
        ):
            return "stay_total_all_rooms"
    return "unknown"


def _money_amounts(text):
    return {
        amount
        for first, second in _MONEY.findall(text)
        if (amount := _decimal(first or second)) is not None
    }


def _price_amounts(text):
    """Explicit add-on tax/fee amounts are not competing room-price quotes."""
    amounts = set()
    for match in _MONEY.finditer(text):
        before = text[max(0, match.start() - 32):match.start()]
        after = text[match.end():match.end() + 48]
        tax_label = re.match(r"\s*(?:in\s+)?(?:tax(?:es)?|fees?|charges?)\b", after, re.I)
        inclusion = re.match(r"\s*(?:tax(?:es)?|fees?|charges?)\s+(?:are\s+)?included\b", after, re.I)
        auxiliary = (
            bool(tax_label and not inclusion)
            and bool(re.search(r"\+\s*$", before) or re.search(r"\b(?:tax|fee|charge)\b", before, re.I))
        ) or bool(re.search(r"\b(?:tax(?:es)?|fees?|charges?)\s*[:=]?\s*$", before, re.I))
        if not auxiliary and (amount := _decimal(match.group(1) or match.group(2))) is not None:
            amounts.add(amount)
    return amounts


def _basis(blocks, quote, amount, scope, requested):
    """Prefer the price's own label; unrelated/struck-through amounts cannot relabel it."""
    if amount is None:
        return "unknown"

    def owns_amount(text):
        money = _price_amounts(text)
        # Currency can be an independently captured selected setting. A literal
        # scalar with its own basis label need not repeat the currency symbol.
        numbers = {_decimal(value) for value in _NUMBER.findall(text)}
        return money == {amount} or (not money and numbers == {amount})

    if owns_amount(quote):
        direct = _basis_from_text(quote, scope, requested)
        if direct != "unknown":
            return direct
    owners = [
        block for block in blocks
        if quote_in_block(quote, block)
        and len(block["text"]) <= 320
    ]
    if len(owners) == 1 and owns_amount(owners[0]["text"]):
        direct = _basis_from_text(owners[0]["text"], scope, requested)
        if direct != "unknown":
            return direct
    compact = [
        block for block in blocks
        if (block in owners or block.get("kind") in {"text", "table_row"})
        and len(block["text"]) <= 320
    ]
    money = set().union(*(_price_amounts(block["text"]) for block in compact))
    # Without a direct label, multiple monetary amounts may be room variants,
    # strike-through prices or fees. Do not attach one amount's label to another.
    if money != {amount}:
        return "unknown"
    labels = [
        block["text"] for block in compact
        if re.fullmatch(
            r"\s*(?:(?:price|cost|rate|stay)\s+)?(?:total|nightly|per night|"
            r"per room(?:\s*[,/]?\s*per night)?|price from|starting from)\s*[:.]?\s*",
            block["text"], re.I,
        )
    ]
    context = " ".join(labels)
    contextual = _basis_from_text(context, scope, requested)
    if contextual != "unknown":
        return contextual
    if scope["status"] != "verified":
        return "unknown"
    # This compact pricing summary explicitly states the stay being priced.
    # It is not a paragraph mentioning a suggested trip duration or room policy.
    summary_pattern = re.compile(
        r"\s*(?:price\s+for\s+)?(\d+)\s+nights?\s*[,·]?\s*"
        r"(\d+)\s+adults?(?:\s*[,·]?\s*(\d+)\s+rooms?)?\s*",
        re.I,
    )
    summaries = [
        match.groups() for block in compact
        if (match := summary_pattern.fullmatch(block["text"]))
    ]
    all_compact = " ".join(block["text"] for block in compact)
    if re.search(r"\bnightly\b|\bper night\b|/\s*night\b|\bper room\b", all_compact, re.I):
        return "unknown"
    if len(summaries) == 1:
        nights, adults, rooms = summaries[0]
        if (
            int(nights) == requested.get("nights")
            and int(adults) == requested.get("adults")
            and (rooms is None or int(rooms) == requested.get("rooms"))
        ):
            return "stay_total_all_rooms"
    return "unknown"


def _local_value_context(block):
    context = block.get("value_context") or {}
    quote, label = context.get("quote"), context.get("label", "")
    if (
        context.get("relation") != "local_container"
        or not isinstance(quote, str) or not quote or len(quote) > 500
        or not isinstance(label, str) or len(label) > 160
        or (label and normalized(label) not in normalized(quote))
        or not isinstance(context.get("struck_through"), bool)
        or normalized(block["text"]) not in normalized(quote)
    ):
        return None
    return context


def _plain_context_amount(block, context):
    """A numeric rating/count is not money merely because the page uses USD."""
    label = normalized(context.get("label", ""))
    if not label or not (
        re.search(r"\b(?:price|cost|total|nightly|per night|per room)\b", label, re.I)
        or re.fullmatch(r"\d+\s+nights?\s*[,·]?\s*\d+\s+adults?(?:\s*[,·]?\s*\d+\s+rooms?)?", label, re.I)
    ):
        return None

    def scalar(text):
        text = normalized(text)
        if text.startswith(label):
            text = text[len(label):]
        elif text.endswith(label):
            text = text[:-len(label)]
        text = re.sub(r"^(?:price|cost|amount|rate)\s*:?\s*", "", text.strip(), flags=re.I)
        return _decimal(text.strip(" :;"))

    amount = scalar(block["text"])
    return amount if amount is not None and scalar(context["quote"]) == amount else None


def _observed_prices(record, page, blocks, scope, requested, columns):
    """Keep each literal amount; only amount-specific source labels establish basis."""
    currency = _currency(blocks, page)
    observations = []
    for block in blocks:
        context = _local_value_context(block)
        amounts = [
            (_decimal(match.group(1) or match.group(2)), match.group().strip())
            for match in _MONEY.finditer(block["text"])
        ]
        plain = _plain_context_amount(block, context) if context and not amounts else None
        if plain is not None:
            amounts.append((plain, block["text"]))
        for amount, raw in amounts:
            if amount is None:
                continue
            quote = context["quote"] if context else block["text"]
            label = context["label"] if context else ""
            original = bool(context and context["struck_through"]) or bool(
                re.search(r"\b(?:original|previous|list price|was)\b", quote, re.I)
                and _money_amounts(quote) == {amount}
            )
            # Even a known original elsewhere cannot remove an equal current
            # amount from this quote. Ambiguous outer containers stay unknown.
            owns = _price_amounts(quote) == {amount} or plain == amount
            kind = _basis_from_text(quote, scope, requested) if owns else "unknown"
            if (
                context and owns and kind == "unknown" and scope["status"] == "verified"
                and len(quote) <= 320
                and not re.search(r"\b(?:per night|nightly|per room)\b|/\s*(?:night|room)\b", quote, re.I)
            ):
                summary = re.search(
                    r"\b(\d+)\s+nights?\s*[,·]?\s*(\d+)\s+adults?"
                    r"(?:\s*[,·]?\s*(\d+)\s+rooms?)?\b", quote, re.I,
                )
                if summary and (
                    int(summary[1]) == requested.get("nights")
                    and int(summary[2]) == requested.get("adults")
                    and (summary[3] is None or int(summary[3]) == requested.get("rooms"))
                ):
                    kind = "stay_total_all_rooms"
            observations.append({
                "amount": _render(amount), "raw": raw,
                "currency": currency, "kind": kind,
                "role": "original" if original else "current" if context else "unknown",
                "label": label, "quote": quote, "source_url": page.get("url"),
                "block_ids": [block["id"]], "selected": False,
                "evidence_method": "local_container" if context else "literal_quote",
                "_eligible": bool(owns and kind != "unknown" and not original),
                "_fields": [],
            })
    # Old captures retain the strict single-amount/source-quote checks. Neither
    # an alias such as nightly_price nor a model-provided basis is source proof.
    for field in _price_fields(columns):
        _, field_blocks, error = _source_group(record, [page], field, columns)
        if error or not field_blocks:
            continue
        amount = _decimal(record.get(field))
        quote = record.get("evidence", {}).get(field, "")
        kind = _basis(blocks, quote, amount, scope, requested)
        matching = [item for item in observations if _decimal(item["amount"]) == amount]
        if not matching:
            original_field = bool(re.search(
                r"(?:^|_)(?:original|old|list|previous|crossed_out)(?:_|$)", field,
            ))
            original_field = original_field or any(
                context["struck_through"]
                for block in field_blocks if quote_in_block(quote, block)
                if (context := _local_value_context(block))
            )
            matching = [{
                "amount": _render(amount), "raw": str(record[field]), "currency": currency,
                "kind": kind, "role": "original" if original_field else "unknown", "label": "", "quote": quote,
                "source_url": page.get("url"),
                "block_ids": [block["id"] for block in blocks if quote_in_block(quote, block)],
                "selected": False, "evidence_method": "record_context",
                "_eligible": kind != "unknown" and not original_field, "_fields": [],
            }]
            observations.extend(matching)
        for item in matching:
            if normalized(quote) in normalized(item["quote"]) or normalized(item["quote"]) in normalized(quote):
                item["_fields"].append(field)
                if item["role"] != "original" and not re.search(
                    r"(?:^|_)(?:original|old|list|previous|crossed_out)(?:_|$)", field,
                ) and kind != "unknown":
                    item["_eligible"] = True
                    if item["kind"] == "unknown":
                        item["kind"] = kind
    return observations


def _select_price(observations, nightly, comparison_scope):
    eligible = [item for item in observations if item["_eligible"] and item["role"] != "original"]
    room_kinds = (
        {"per_room_per_night", "stay_total_per_room"}
        if comparison_scope == "per_room" else {"all_rooms_per_night", "stay_total_all_rooms"}
    )
    compatible = [item for item in eligible if item["kind"] in room_kinds]
    if compatible:
        eligible = compatible
    preferred = (
        [item for item in eligible if item["kind"].endswith("per_night")]
        if nightly else [item for item in eligible if item["kind"].startswith("stay_total")]
    )
    if preferred:
        eligible = preferred
    alternatives = {(item["amount"], item["kind"]) for item in eligible}
    return (eligible[0], False) if len(alternatives) == 1 else (None, len(alternatives) > 1)


def _budget(pricing, constraints):
    prices = [item for item in constraints if item["kind"] == "price"]
    if not prices:
        return "not_requested"
    if pricing["status"] != "verified":
        return "unverified"
    for item in prices:
        amount = _decimal(
            pricing["comparison_amount"]
            if item.get("basis") == "nightly"
            else pricing["displayed_amount"]
        )
        if amount is None:
            return "unverified"
        if item.get("currency") and item["currency"] != pricing["currency"]:
            return "unverified"
        for condition in item["conditions"]:
            target = Decimal(condition["value"])
            matches = {
                "gte": amount >= target, "lte": amount <= target,
                "gt": amount > target, "lt": amount < target,
            }
            if not matches.get(condition["operator"], False):
                return "outside_target"
    return "within_target"


def assess_pricing(records, pages, instructions, columns):
    """Assess source-verified rows only; never manufacture a missing quote or price."""
    requested = requested_stay(instructions)
    constraints = requested_constraints(instructions)
    names = [_column(column, "name") for column in columns]
    nightly = any(item.get("basis") == "nightly" for item in constraints) or bool(
        re.search(r"\bnightly\b|\bper night\b|/\s*night\b", instructions, re.I)
    )
    stay = any(
        requested.get(field) is not None
        for field in ("check_in", "check_out", "adults", "children", "rooms")
    )
    hotel_fields = any(re.search(r"hotel|property|room|accommodation", name) for name in names)
    hotel_context = hotel_fields or bool(
        re.search(r"\b(?:hotels?|properties|lodging|accommodations?|rooms?)\b", instructions, re.I)
    )
    applicable = hotel_context and (
        nightly
        or (stay and (
            any(PRICE_NAME.search(name) for name in names)
            or any(item["kind"] == "price" for item in constraints)
        ))
    )
    primary_field = _price_field(columns, nightly)
    rows, assessments, scopes = [], [], []
    for original in records:
        row = deepcopy(original)
        for owned in ("pricing", *COMPUTED_FIELDS):
            row.pop(owned, None)
        if not applicable:
            rows.append(row)
            continue
        field = primary_field
        page, blocks, binding_error = _source_group(row, pages, field, columns)
        text = " ".join(block["text"] for block in blocks)
        scope = _scope(page or {}, blocks, requested)
        scopes.append(scope)
        amount = _decimal(row.get(field))
        kind = (
            _basis(blocks, row.get("evidence", {}).get(field, ""), amount, scope, requested)
            if blocks and not binding_error else "unknown"
        )
        currency = _currency(blocks, page) if page else None
        request_scopes = {
            item.get("room_scope") for item in constraints
            if item["kind"] == "price" and item.get("room_scope")
        }
        comparison_scope = "per_room" if request_scopes == {"per_room"} else "all_rooms"
        observations = _observed_prices(row, page, blocks, scope, requested, columns) if page and blocks else []
        selected, ambiguous = _select_price(observations, nightly, comparison_scope)
        if selected:
            selected["selected"] = True
            amount, kind = _decimal(selected["amount"]), selected["kind"]
            selected_fields = selected["_fields"]
            # The canonical scalar is a query projection only. Raw total and
            # original fields are retained exactly as extracted for display.
            field = primary_field or next(iter(selected_fields), None)
            if nightly and field and re.search(r"(?:^|_)(?:total|stay)(?:_|$)", field):
                field = next((
                    name for name in selected_fields if re.search(r"nightly|per_night", name)
                ), None)
            elif not nightly and field and re.search(r"nightly|per_night", field):
                field = next((
                    name for name in selected_fields
                    if re.search(r"(?:^|_)(?:total|stay)(?:_|$)", name)
                ), None)
            binding_error = None
        elif ambiguous:
            kind = "unknown"
            binding_error = "price_observation_ambiguous"
        elif any(_decimal(item["amount"]) == amount for item in observations) and all(
            item["role"] == "original" for item in observations if _decimal(item["amount"]) == amount
        ):
            kind = "unknown"
            binding_error = "original_price_not_current_quote"
        issues = list(scope["issues"])
        if requested.get("request_error"):
            issues.append("requested_stay_ambiguous")
        if binding_error:
            issues.append(binding_error)
        if currency is None:
            issues.append("price_currency_unverified")
        requested_currencies = {
            item["currency"] for item in constraints
            if item["kind"] == "price" and item.get("currency")
        }
        if requested_currencies and requested_currencies != {currency}:
            issues.append("requested_currency_unverified")
        tax_disclosure = _charge_disclosure(text, r"\btax(?:es)?\b")
        fee_disclosure = _charge_disclosure(text, r"\b(?:fees?|charges?)\b")
        taxes = tax_disclosure["status"]
        fees = fee_disclosure["status"]
        if any(item.get("taxes_requested") == "included" for item in constraints):
            if taxes != "included":
                issues.append("requested_taxes_unverified")
        if any(item.get("fees_requested") == "included" for item in constraints):
            if fees != "included":
                issues.append("requested_fees_unverified")
        if kind == "starting_from":
            issues.append("starting_price_not_requested_stay_quote")
        elif kind == "unknown":
            issues.append("price_basis_unverified")
        if len(request_scopes) > 1:
            issues.append("requested_room_price_scope_ambiguous")
        if (
            kind in {"per_room_per_night", "stay_total_per_room"}
            and comparison_scope != "per_room"
        ):
            issues.append("combined_room_price_unverified")
        if (
            kind in {"all_rooms_per_night", "stay_total_all_rooms"}
            and comparison_scope == "per_room"
        ):
            issues.append("per_room_price_unverified")
        comparison = None
        calculation = None
        if amount is not None and kind.endswith("per_night"):
            comparison = amount
        elif amount is not None and kind.startswith("stay_total"):
            nights = requested.get("nights")
            if scope["status"] == "verified" and isinstance(nights, int) and nights > 0:
                comparison = amount / Decimal(nights)
                displayed_average = comparison.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                calculation = {
                    "operation": "stay_total / nights", "source_amount": _render(amount),
                    "nights": nights, "result": _render(displayed_average),
                    "comparison_value": _render(comparison),
                    "label": "Average per night",
                }
            else:
                issues.append("stay_total_night_count_unverified")
        if comparison is None:
            issues.append("nightly_comparison_unverified")
        issues = list(dict.fromkeys(issues))
        pricing = {
            "status": "unverified" if issues else "verified",
            "scope_status": scope["status"],
            "price_field": field,
            "displayed_amount": selected["amount"] if selected else row.get(field),
            "currency": currency,
            "kind": kind,
            "source_basis": kind,
            "basis_label": _LABELS[kind],
            "comparison_scope": comparison_scope,
            "comparison_basis": "nightly" if nightly else "displayed",
            "comparison_amount": (
                _render(comparison) if comparison is not None and not issues else None
            ),
            "combined_nightly": (
                _render(comparison.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if comparison is not None and not issues and comparison_scope == "all_rooms"
                else None
            ),
            "calculation": calculation,
            "taxes": taxes,
            "taxes_status": taxes,
            "fees_status": fees,
            "tax_disclosure": {
                "taxes": tax_disclosure["quotes"], "fees": fee_disclosure["quotes"],
            },
            "issues": issues,
            "observations": [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in observations
            ],
            "comparison_fields": list(dict.fromkeys(
                ([field] if field else []) + [
                    name for name in (selected["_fields"] if selected else [])
                    if re.search(r"nightly|per_night", name)
                    and kind.endswith("per_night")
                ]
            )),
            "evidence": {
                "source_url": page.get("url") if page else row.get("source_url"),
                "block_ids": selected["block_ids"] if selected else [block["id"] for block in blocks],
                "quote": selected["quote"] if selected else row.get("evidence", {}).get(field, ""),
            },
            "currency_evidence": _currency_evidence(blocks, page or {}, currency),
            "source_context": {
                "record_group_verified": bool(blocks),
                "stay_scope": scope,
                # These are raw candidates, not a silently repaired scalar or
                # a claim that any amount is the current nightly quote.
                "price_candidates": [
                    {"block_id": block["id"], "quote": block["text"][:1000]}
                    for block in blocks if _price_amounts(block["text"])
                ][:8],
            },
        }
        if calculation:
            pricing["basis_label"] += "; average per night calculated from full-stay total"
        elif kind == "all_rooms_per_night" and scope["status"] == "not_requested":
            pricing["basis_label"] = "Per night; room count not specified"
        pricing["budget_status"] = _budget(pricing, constraints)
        row["pricing"] = pricing
        row.update({
            "pricing_combined_nightly": pricing["combined_nightly"],
            "pricing_basis": pricing["basis_label"], "pricing_taxes": pricing["taxes"],
            "pricing_fees": pricing["fees_status"],
            "pricing_currency": pricing["currency"],
            "pricing_budget_status": pricing["budget_status"],
        })
        rows.append(row)
        assessments.append({
            "record_id": row.get("listing_id"), "source_url": row.get("source_url"),
            "issues": [{"field": field or "price", "reason": issue} for issue in issues],
        })
    scope_status = (
        "mismatch" if any(scope["status"] == "mismatch" for scope in scopes)
        else "unverified" if any(scope["status"] == "unverified" for scope in scopes)
        else "verified" if any(scope["status"] == "verified" for scope in scopes)
        else "not_requested"
    )
    return {
        "records": rows,
        "assessments": assessments,
        "stay_scope": {
            "status": scope_status, "requested": requested, "availability_verified": False,
        },
        "summary": {
            "contract_version": CONTRACT_VERSION, "applicable": applicable,
            "applicable_count": len(assessments),
            "verified": sum(row.get("pricing", {}).get("status") == "verified" for row in rows),
            "unverified": sum(
                row.get("pricing", {}).get("status") == "unverified" for row in rows
            ),
            "within_target": sum(
                row.get("pricing", {}).get("budget_status") == "within_target" for row in rows
            ),
            "outside_target": sum(
                row.get("pricing", {}).get("budget_status") == "outside_target" for row in rows
            ),
        },
    }


def pricing_comparison_record(row):
    """A query-only view. Display/export retains the original source price."""
    pricing = row.get("pricing", {})
    amount = (
        pricing.get("comparison_amount")
        if pricing.get("comparison_basis", "nightly") == "nightly"
        else pricing.get("displayed_amount")
    )
    if pricing.get("status") != "verified" or amount is None:
        return row
    result = dict(row)
    for field in pricing.get("comparison_fields") or [pricing.get("price_field")]:
        if field:
            result[field] = amount
    return result
