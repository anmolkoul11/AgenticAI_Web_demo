"""Independent, bounded evidence for a returned stay search.

Request dates may use the disclosed request-year policy. Website dates never do:
only fresh full dates, named occupancy and allowlisted URL values are evidence.
An actual results heading can independently establish the returned destination.
Neither this scope nor a prepared form proves individual room availability.
"""

import copy
import re
from datetime import date
from urllib.parse import parse_qsl, urlsplit

from agentic_web_demo.browser_dates import resolve_stay_dates
from agentic_web_demo.browser_navigation import (
    HOTEL_REQUEST,
    guest_counts,
    requested_dates,
    requested_destination,
)
from agentic_web_demo.custom_fetch import WebsiteError

STAY_FIELDS = ("destination", "check_in", "check_out", "adults", "children", "rooms")
URL_FIELDS = {
    "checkin": "check_in",
    "check_in": "check_in",
    "check-in": "check_in",
    "arrival": "check_in",
    "arrival_date": "check_in",
    "arrivaldate": "check_in",
    "checkout": "check_out",
    "check_out": "check_out",
    "check-out": "check_out",
    "departure": "check_out",
    "departure_date": "check_out",
    "departuredate": "check_out",
    "adults": "adults",
    "adult": "adults",
    "num_adults": "adults",
    "numadults": "adults",
    "group_adults": "adults",
    "rooms": "rooms",
    "room": "rooms",
    "num_rooms": "rooms",
    "numrooms": "rooms",
    "no_rooms": "rooms",
    "room_count": "rooms",
    "children": "children",
    "num_children": "children",
    "group_children": "children",
}


def requested_stay(instructions, reference_date=None):
    """Return literal/canonical stay values, never derive checkout from night prose."""
    if not HOTEL_REQUEST.search(instructions):
        return {}
    result = {}
    destination = requested_destination(instructions)
    if destination:
        result["destination"] = destination
    try:
        dates, _ = resolve_stay_dates(instructions, reference_date)
        if len(dates) == 2:
            result.update(check_in=dates[0], check_out=dates[1])
            nights = (date.fromisoformat(dates[1]) - date.fromisoformat(dates[0])).days
            if nights > 0:
                result["nights"] = nights
            else:
                result["request_error"] = "Check-out must follow check-in."
        counts = guest_counts(instructions)
        if counts is None:
            result["request_error"] = "Requested occupancy has conflicting named counts."
        else:
            result.update(counts)
    except WebsiteError as exc:
        result["request_error"] = str(exc)
    return result


def url_stay_values(value):
    """Project only normalized full dates/counts; never retain a URL or arbitrary query."""
    result = {}
    try:
        pairs = parse_qsl(urlsplit(value).query, keep_blank_values=False, max_num_fields=100)
    except (ValueError, TypeError):
        return result
    for raw_key, raw_value in pairs:
        key = URL_FIELDS.get(raw_key.casefold())
        if key is None:
            continue
        if key in {"check_in", "check_out"}:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_value):
                continue
            try:
                parsed = date.fromisoformat(raw_value).isoformat()
            except ValueError:
                continue
        else:
            if not re.fullmatch(r"\d{1,3}", raw_value):
                continue
            parsed = int(raw_value)
        result.setdefault(key, [])
        if parsed not in result[key]:
            result[key].append(parsed)
    return result


def _normal(value):
    return " ".join(str(value).casefold().split())


def destination_matches(expected, observed):
    """Allow a site's regional suffix, never a different place containing the city."""
    expected, observed = _normal(expected), _normal(observed)
    if not expected or not observed:
        return False
    return observed == expected or (
        "," not in expected and observed.split(",", 1)[0].strip() == expected
    )


def _date_values(text):
    try:
        return requested_dates(text)
    except WebsiteError:
        return []


def _heading_destinations(observation):
    """Read only bounded, structured top-level result-count headings, not prose."""
    count = r"(?:\d{1,3}(?:[,\u00a0 ]\d{3})+|\d+)\+?"
    records = r"(?:propert(?:y|ies)|hotels?|accommodations?|stays?|results?)"
    total = rf"(?:over |more than |about )?{count}\s+{records}(?:\s+(?:found|available))?"
    patterns = (
        rf"(?P<destination>.+?)(?::|\s+[–—-])\s*{total}",
        rf"{total}\s+in\s+(?P<destination>.+)",
    )
    headings = (observation.get("results") or {}).get("headings") or []
    if not isinstance(headings, list):
        return
    for item in headings[:8]:
        if not isinstance(item, dict) or item.get("level") not in (1, 2):
            continue
        text = " ".join(str(item.get("text", "")).split())
        if not text or len(text) > 240:
            continue
        for pattern in patterns:
            match = re.fullmatch(pattern, text, re.I)
            if match:
                destination = match["destination"].strip()
                if destination and len(destination) <= 120:
                    yield destination, text
                break


def reconcile_captured_result_scope(scope, blocks, *, document_id):
    """Add literal returned-result headings captured after content preparation.

    The caller must bind the capture to the live returned document. Dates and
    occupancy remain independently observed facts: neither the requested stay
    nor record prose can fill them in. A later heading never erases a conflict.
    """
    result = copy.deepcopy(scope)
    if (
        not isinstance(result, dict) or result.get("source") != "returned_page"
        or not isinstance(document_id, str) or not document_id
        or result.get("document_id") != document_id
        or not isinstance(blocks, list)
    ):
        return result
    requested = result.get("requested") or {}
    if not isinstance(requested, dict) or not requested.get("destination"):
        return result
    headings = []
    for block in blocks[:600]:
        if (
            not isinstance(block, dict) or block.get("kind") != "heading"
            or block.get("association") != "page" or block.get("group_id") is not None
            or block.get("heading_level") not in (1, 2)
            or not re.fullmatch(r"b\d{1,4}", str(block.get("id", "")))
        ):
            continue
        for value, quote in _heading_destinations({
            "results": {"headings": [{"level": block["heading_level"], "text": block.get("text", "")}]}
        }):
            headings.append({"value": value, "quote": quote, "block_ids": [block["id"]]})
        if len(headings) >= 8:
            break
    if not headings:
        return result
    fields = result.get("fields")
    if not isinstance(fields, list) or any(not isinstance(item, dict) for item in fields):
        return result
    destination_fields = [item for item in fields if item.get("field") == "destination"]
    if len(destination_fields) > 1:
        return result
    destination = destination_fields[0] if destination_fields else {
        "field": "destination", "expected": requested["destination"],
        "status": "unverified", "observed": None, "method": "none", "evidence": "",
    }
    if not destination_fields:
        fields.append(destination)
    observed = result.get("observed")
    if not isinstance(observed, dict):
        return copy.deepcopy(scope)
    previous = destination.get("observed")
    previous_observed = observed.get("destination")
    values = list(dict.fromkeys(
        str(value) for value in (previous, previous_observed, *(item["value"] for item in headings))
        if value not in (None, "")
    ))
    matched = all(destination_matches(requested["destination"], value) for value in values)
    destination["status"] = (
        "mismatch" if destination.get("status") == "mismatch" or not matched else "verified"
    )
    destination["observed"] = values[0] if matched else "; ".join(values)
    observed["destination"] = destination["observed"]
    methods = {
        method.strip() for method in str(destination.get("method", "")).split(",")
        if method.strip() and method.strip() != "none"
    }
    methods.add("captured_results_heading")
    destination["method"] = ", ".join(sorted(methods))
    previous_evidence = str(destination.get("evidence", ""))
    if previous_evidence == "No fresh returned-page value.":
        previous_evidence = ""
    destination["evidence"] = " | ".join(dict.fromkeys(
        quote for quote in [previous_evidence, *(item["quote"] for item in headings)] if quote
    ))
    destination["block_ids"] = list(dict.fromkeys([
        *(destination.get("block_ids") or []),
        *(block_id for item in headings for block_id in item["block_ids"]),
    ]))
    captured = destination.setdefault("captured_evidence", [])
    for item in headings:
        evidence = {"method": "captured_results_heading", **item}
        if evidence not in captured:
            captured.append(evidence)

    wanted = {field: value for field, value in requested.items() if field in STAY_FIELDS}
    returned_methods = {
        "returned_url", "returned_control", "returned_selected_date",
        "returned_results_heading", "captured_results_heading",
    }

    def verified_field(field, expected):
        matches = [item for item in fields if item.get("field") == field]
        if len(matches) != 1:
            return False
        item = matches[0]
        methods = {method.strip() for method in str(item.get("method", "")).split(",")}
        value = item.get("observed")
        if (
            item.get("status") != "verified" or value in (None, "")
            or not methods or not methods <= returned_methods
            or observed.get(field) in (None, "")
        ):
            return False
        if field == "destination":
            return destination_matches(expected, value) and destination_matches(expected, observed[field])
        return _normal(value) == _normal(expected) == _normal(observed[field])

    contradictions = result.get("contradictions") or []
    mismatch = result.get("status") == "mismatch" or any(
        item.get("status") == "mismatch" for item in fields if item.get("field") in wanted
    ) or any(
        isinstance(item, dict) and item.get("code") != "catalog_starting_price"
        for item in contradictions
    )
    verified = (
        bool(wanted) and not contradictions and not requested.get("request_error")
        and all(verified_field(field, expected) for field, expected in wanted.items())
    )
    result["status"] = "mismatch" if mismatch else "verified" if verified else "unverified"
    result["availability_verified"] = False
    return result


def observed_result_scope(requested, observation):
    """Read returned-page evidence independently of pre-submit ledger/bindings."""
    wanted = {key: value for key, value in requested.items() if key in STAY_FIELDS}
    candidates = {key: [] for key in wanted}

    def add(field, value, method, evidence):
        if field in candidates and value not in (None, ""):
            candidates[field].append((str(value), method, str(evidence)[:240]))

    for field, values in (observation.get("stay_url_values") or {}).items():
        if field in STAY_FIELDS and isinstance(values, list):
            for value in values[:4]:
                # Normalized facts only. Untrusted fixture/client values are not
                # allowed to inject arbitrary query text into stored evidence.
                if field in {"check_in", "check_out"}:
                    dates = _date_values(str(value))
                    if len(dates) == 1 and dates[0] == str(value):
                        add(field, value, "returned_url", f"{field}={value}")
                elif field != "destination" and re.fullmatch(r"\d{1,3}", str(value)):
                    add(field, value, "returned_url", f"{field}={value}")
    # Only the actual top-level document's controls establish returned context.
    # Promotional frames, arbitrary body prose and calendar choices do not.
    main = (observation.get("frames") or [{}])[0]
    controls = main.get("controls", [])
    destination_inputs = []
    for item in controls:
        tag, role = item.get("tag"), item.get("role")
        native = tag in {"INPUT", "SELECT", "TEXTAREA"}
        label = " ".join(str(item.get(key, "")) for key in ("label", "name"))
        if item.get("date") and not native or role in {"gridcell", "checkbox", "radio"}:
            if item.get("selected") in {True, "true"}:
                full_dates = _date_values(label + " " + str(item.get("date", "")))
                if len(full_dates) == 1:
                    for field, hint in (
                        ("check_in", r"check.?in|arrival"),
                        ("check_out", r"check.?out|departure"),
                    ):
                        if re.search(hint, label, re.I):
                            add(field, full_dates[0], "returned_selected_date", label)
            continue
        if role == "option":
            continue
        value = str(item.get("value", ""))
        text = " ".join(str(item.get(key, "")) for key in ("label", "text", "value"))
        if native:
            text = label + " " + value
        if native and (
            tag in {"SELECT", "TEXTAREA"}
            or item.get("type", "text") in {"text", "search", ""}
        ):
            excluded = re.search(
                r"check.?in|check.?out|arrival|departure|dates?|adults?|children|rooms?|"
                r"guests?|email|password|phone|newsletter|price|rating|currency",
                label,
                re.I,
            )
            if not excluded:
                destination_inputs.append(item)
        for field in ("adults", "children", "rooms"):
            counter = item.get("counter") or {}
            if re.fullmatch(field.rstrip("s") + "s?", str(counter.get("label", "")), re.I):
                add(field, counter.get("value"), "returned_control", counter.get("evidence", ""))
            counts = guest_counts(text)
            if counts and field in counts:
                add(field, counts[field], "returned_control", text)
            if native and re.search(rf"\b{field}\b", label, re.I) and value.isdigit():
                add(field, value, "returned_control", text)
        if not re.search(r"check.?in|check.?out|arrival|departure|dates?|calendar", label, re.I):
            continue
        dates = _date_values(text)
        if not dates:
            continue  # A month/day label must not borrow the old selected year.
        both = bool(
            re.search(r"\bdates\b|\bcalendar\b|\bdate range\b", label, re.I)
            or (
                re.search(r"check.?in|arrival", label, re.I)
                and re.search(r"check.?out|departure", label, re.I)
            )
        )
        if both and len(dates) == 2:
            add("check_in", dates[0], "returned_control", text)
            add("check_out", dates[1], "returned_control", text)
        elif not both and len(dates) == 1:
            field = "check_in" if re.search(r"check.?in|arrival", label, re.I) else "check_out"
            add(field, dates[0], "returned_control", text)
    explicit = [
        item for item in destination_inputs
        if re.search(
            r"destination|location|\bcity\b|where .*going",
            str(item.get("label", "")),
            re.I,
        )
    ]
    inputs = explicit or (destination_inputs if len(destination_inputs) == 1 else [])
    for item in inputs:
        if item.get("expanded") != "true" and not item.get("suggestions_pending"):
            value = str(item.get("value", ""))
            if item.get("tag") == "SELECT":
                option = next(
                    (option for option in item.get("options", []) if str(option.get("value")) == value),
                    None,
                )
                if option:
                    value = str(option.get("label", value))
            add("destination", value, "returned_control", str(item.get("label", "")) + " " + value)
    # Do not let a matching input conceal a conflicting results heading. These
    # are fresh DOM facts, never the requested value or a pre-submit ledger.
    for value, evidence in _heading_destinations(observation):
        add("destination", value, "returned_results_heading", evidence)
    fields, observed = [], {}
    for field, expected in wanted.items():
        values = {_normal(value) for value, _, _ in candidates[field]}
        matched = bool(values) and (
            all(destination_matches(expected, value) for value in values)
            if field == "destination" else values == {_normal(expected)}
        )
        status = "verified" if matched else "mismatch" if values else "unverified"
        observed[field] = (
            candidates[field][0][0] if matched else "; ".join(sorted(values)) if values else None
        )
        fields.append(
            {
                "field": field,
                "expected": expected,
                "observed": observed[field],
                "status": status,
                "method": ", ".join(sorted({method for _, method, _ in candidates[field]})) or "none",
                "evidence": candidates[field][0][2]
                if candidates[field] else "No fresh returned-page value.",
            }
        )
    contradictions = []
    for text in (observation.get("results", {}).get("price_contexts") or [])[:12]:
        if not isinstance(text, str):
            continue
        if re.search(r"\bprice\s+from\b|\bstarting\s+(?:at|from)\b", text, re.I):
            contradictions.append({"code": "catalog_starting_price", "evidence": text[:300]})
        counts = guest_counts(text)
        if counts and any(
            field in wanted and str(counts[field]) != str(wanted[field]) for field in counts
        ):
            contradictions.append({"code": "price_context_occupancy_mismatch", "evidence": text[:300]})
        nights = {int(match[1]) for match in re.finditer(r"\b(\d{1,3})\s+nights?\b", text, re.I)}
        if nights and requested.get("nights") and nights != {requested["nights"]}:
            contradictions.append({"code": "price_context_nights_mismatch", "evidence": text[:300]})
    contradictions = list(
        {(item["code"], item["evidence"]): item for item in contradictions}.values()
    )[:12]
    has_mismatch = any(item["status"] == "mismatch" for item in fields) or any(
        item["code"] != "catalog_starting_price" for item in contradictions
    )
    verified = (
        bool(fields) and all(item["status"] == "verified" for item in fields)
        and not contradictions
    )
    status = (
        "not_requested" if not wanted else "verified" if verified
        else "mismatch" if has_mismatch else "unverified"
    )
    return {
        "status": status,
        "requested": dict(requested),
        "observed": observed,
        "fields": fields,
        "contradictions": contradictions,
        "document_id": observation.get("document_id"),
        "source": "returned_page",
        "availability_verified": False,
    }
