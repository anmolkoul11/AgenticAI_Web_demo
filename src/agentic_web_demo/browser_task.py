"""Request-derived form evidence and bounded context for a dynamic browser agent.

No website selectors or action recipes: only literal request grounding, fresh
control values and submission evidence. Form evidence is not listing availability.
"""

import copy
import json
import re
from datetime import date
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from agentic_web_demo.browser_dates import resolve_stay_dates
from agentic_web_demo.browser_navigation import (
    HOTEL_REQUEST,
    age_control,
    guest_component,
    guest_counts,
    occupancy_summary_values,
    requested_dates,
    requested_destination,
    requested_stay_dates,
)
from agentic_web_demo.browser_runtime import bound_controls, controls, identity
from agentic_web_demo.capture import clean_url, query_identity_omitted
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.stay_scope import STAY_FIELDS, observed_calendar_endpoints, observed_result_scope, requested_stay

OBSERVATION_BUDGET = 24000


def site_search_behavior(url, *, stay_request=False):
    """A transition policy, never a site-specific selector or form recipe."""
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
    site = next((name for name in ("booking.com", "tripadvisor.com")
                 if host == name or host.endswith("." + name)), host or "unknown")
    mode = ("explicit_submit" if site == "booking.com" else "live_update"
            if site == "tripadvisor.com" else "observed") if stay_request else "observed"
    reason = {
        "explicit_submit": "Apply stay edits with Search before collecting the returned hotel list.",
        "live_update": "Stay controls can refresh this list; fresh applied result evidence is required.",
        "observed": "Use the request's collection goal and observed form/result transitions.",
    }[mode]
    return {"site": site, "search_mode": mode, "reason": reason}


def normalized(value):
    return " ".join(str(value).casefold().split())


def calendar_page(observation):
    return observation.get("page_id") or observation.get("document_id", observation.get("url"))


class MissingFormValue(WebsiteError):
    """A model declaration cannot supply a missing user value."""

    def __init__(self, field, label=None):
        self.field = field
        self.label = label or field.replace('_', ' ')
        super().__init__(
            f"Please enter {self.label} in the website, then press Resume. "
            "Your request did not provide a verified value for this field. No value was entered."
        )


def explicit_age_values(text):
    """Only age phrases supply ages; occupancy/date numbers do not."""
    found = {}
    patterns = (
        r"\b(?:ages?|aged)\s*(?:of\s+(?:the\s+)?(?:child|kid)(?:\s+\d+)?\s*)?(?:is|are|:|=)?\s*"
        r"(\d{1,2}(?:\s*(?:,|and|&)\s*\d{1,2})*)\b(?!\s*[-–]\s*\d)",
        r"\b(\d{1,2})\s*[- ]?\s*(?:years?|yrs?)\s*[- ]?\s*old\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, str(text), re.I):
            prefix = str(text)[max(0, match.start() - 40):match.start()]
            if re.search(r"\b(?:under|over|at least|at most|minimum|maximum|younger than|older than|not|avoid)\s*$", prefix, re.I):
                continue
            for value in re.finditer(r"\d{1,2}", match.group(1)):
                found[match.start(1) + value.start()] = str(int(value.group()))
    return [value for _, value in sorted(found.items())]


def query_field_name(name):
    return name == "destination" or bool(re.search(
        r"(?:^|_)(?:search|query|keywords?)(?:_|$)", name, re.I
    ))


def literal_form_value(requirement, control):
    """A new form field needs both its meaning and value in the request quote."""
    quote = normalized(requirement.get("request_quote", ""))
    expected = normalized(requirement.get("expected", ""))
    if control and age_control({}, requirement["name"]) and not age_control(control):
        return False
    if age_control(control, requirement["name"]):
        return expected in explicit_age_values(quote)
    if not expected:
        return False
    meaning = " ".join(str(control.get(key) or "") for key in ("label", "name"))
    meaning = meaning or requirement["name"].replace("_", " ")
    terms = set(re.findall(r"[a-z]{3,}", meaning.casefold())) - {
        "the", "your", "enter", "select", "choose", "please", "field", "value", "required", "input",
        "number", "count", "counter", "option", "options", "selection", "information", "details", "form", "control"
    }
    semantic = any(re.search(rf"\b{re.escape(term)}s?\b", quote) for term in terms)
    literal = bool(re.search(rf"(?<!\w){re.escape(expected)}(?!\w)", quote))
    if discovery_query_control(control) and literal and query_field_name(requirement["name"]):
        # A generic query accepts literal request text; the user's request
        # need not contain the UI caption "Search" to ground that value.
        return True
    if expected in {"true", "false"}:
        polarity = r"\b(?:with|include|including|yes|need|want)\b" if expected == "true" else r"\b(?:without|exclude|no|not)\b"
        literal |= bool(re.search(polarity, quote))
    return semantic and literal


def widget_control(facts):
    """A form widget is not a retrieval submit, whatever purpose the model says."""
    label = normalized(" ".join(str(facts.get(key, "")) for key in ("label", "text")))
    search_label = bool(re.search(r"^(?:search|find)\b|\bsearch with ai\b", label))
    native_submit = (
        facts.get("tag") in {"BUTTON", "INPUT"}
        and facts.get("type") in {"submit", "image"}
        and (facts.get("form_scope") or facts.get("submits_form"))
    )
    confirm_label = any(
        re.fullmatch(r"apply|update|confirm|ok", normalized(facts.get(key, "")))
        for key in ("label", "text")
    )
    return bool(
        facts.get("role") in {"option", "gridcell", "checkbox", "radio", "spinbutton"}
        or facts.get("counter")
        or facts.get("date_navigation") in {"next", "previous"} and facts.get("date_widget_id")
        or facts.get("date")
        or facts.get("widget_scope") in {"counter", "choice"}
        or any(
            re.fullmatch(r"done|close|dismiss|cancel", normalized(facts.get(key, "")))
            for key in ("label", "text")
        )
        or confirm_label
        and not native_submit
        or re.search(
            r"check.?in|check.?out|\bcalendar\b|\bselect dates\b|\bnext month\b|\bprevious month\b",
            label,
        )
        or not search_label
        and (facts.get("expanded") in {"true", "false"} or facts.get("haspopup"))
    )


def navigation_choice(facts, owners=()):
    """Popup ownership alone does not turn a navigation link/tab into a value."""
    if any(age_control(owner) for owner in owners) or age_control(facts):
        return False
    if facts.get("role") in {"option", "checkbox", "radio", "gridcell", "spinbutton"}:
        return False
    return bool(
        facts.get("role") == "tab"
        or facts.get("tag") == "A" and facts.get("href")
    )


def requested_listing_category(instructions):
    return "hotels" if HOTEL_REQUEST.search(str(instructions)) else None


def listing_category_control(control, category):
    """Recognize an observed category, never a hotel title or guessed URL."""
    if category != "hotels" or control.get("enabled", True) is False or age_control(control):
        return False
    if control.get("role") in {"option", "checkbox", "radio", "gridcell", "spinbutton"}:
        return False
    actionable = control.get("tag") == "A" and control.get("href") or (
        control.get("tag") == "BUTTON" or control.get("role") in {"button", "tab"}
    )
    label = normalized(control.get("label") or control.get("text") or "")
    return bool(actionable and re.fullmatch(
        r"(?:hotels?|stays?|places to stay|accommodations?)(?:\s+(?:in|near|around)\s+.{1,90})?",
        label,
    ))


def discovery_query_control(control):
    words = " ".join(str(control.get(key) or "") for key in ("label", "name"))
    return bool(
        control.get("enabled", True) is not False and not control.get("readonly")
        and not age_control(control)
        and (control.get("tag") in {"INPUT", "TEXTAREA"} or control.get("role") in {"combobox", "textbox"})
        and control.get("type", "text") in {"", "text", "search", "textarea"}
        and (control.get("type") == "search" or re.search(r"\b(?:search|query)\b|^q$", words, re.I))
    )


def search_opener(control):
    """An observed popup opener does not dispatch either kind of Search."""
    return bool(
        not control.get("form_scope") and not control.get("submits_form")
        and control.get("type") not in {"submit", "image"}
        and (control.get("tag") == "BUTTON" or control.get("role") == "button")
        and re.fullmatch(r"(?:open\s+)?search", normalized(control.get("label") or control.get("text") or ""))
        and (control.get("haspopup") not in {None, "", "false"}
             or control.get("expanded") in {"true", "false"})
    )


def calendar_day(control):
    """Return one observed day choice, never the date mentioned by an opener."""
    if control.get("date_kind") in {"opener", "date_opener"}:
        return None
    label = " ".join(str(control.get(key) or "") for key in ("label", "text"))
    if re.search(
        r"\b(?:enter|change|edit|choose|select)\s+(?:the\s+)?(?:check.?in|check.?out|arrival|departure|dates?)\b"
        r"|\bthe selected date is\b", label, re.I,
    ):
        return None
    if control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"} and not (
        control.get("tag") == "INPUT"
        and control.get("type") in {"checkbox", "radio", "button"}
        and (control.get("date_kind") == "day_choice" or control.get("date_owner_id"))
    ):
        return None
    try:
        dates = requested_dates(" ".join(str(control.get(key) or "") for key in ("date", "label", "text")))
    except WebsiteError:
        return None
    if len(dates) != 1:
        return None
    if control.get("date_kind") == "day_choice" or control.get("date") or control.get("role") == "gridcell":
        return dates[0]
    # Older observations have no date metadata. A direct full-date button is
    # still a day; surrounding prose mentioning a date is not an action recipe.
    direct = re.sub(r"^(?:selected\s+)?(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*)?", "", label.strip(), flags=re.I)
    try:
        return dates[0] if requested_dates(direct) == dates and re.fullmatch(
            r"(?:\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+[,]?\s+\d{4})", direct, re.I,
        ) else None
    except WebsiteError:
        return None


def destination_tokens(value):
    """Ignore presentation punctuation, not words, ordering or missing qualifiers."""
    return tuple(re.findall(r"\w+", str(value).casefold()))


def occupancy_components(label):
    """Return distinct named quantities, including unrequested summary fields."""
    return [
        field
        for field, pattern in (
            ("adults", r"\badults?\b"),
            ("children", r"\b(?:children|child|kids?)\b"),
            ("rooms", r"\brooms?\b"),
        )
        if re.search(pattern, str(label), re.I)
    ]


def occupancy_component(label):
    """Resolve one named quantity, never a mixed occupancy summary."""
    return guest_component({"label": label})


def occupancy_widget_action(observation, checklist):
    """Close a completed guest widget using fresh controls, not site Search."""
    checks = [item for item in checklist.get("requirements", [])
              if item.get("field") in {"adults", "children", "rooms"}
              and item.get("application") == "form"]
    if not checks or any(item.get("status") != "verified"
                         and item.get("next_action") != "confirm_or_close_widget" for item in checks):
        return None
    available = controls(observation)
    if any(item.get("date_kind") == "day_choice" and item.get("date_widget_id") for item in available):
        return None  # Finish the calendar before closing another widget.
    by_id = {item.get("id"): item for item in available}
    for missing in checklist.get("unresolved_form_fields", []):
        field = by_id.get(missing.get("control_id"), {})
        if (not discovery_query_control(field)
                or normalized(field.get("label") or field.get("name") or "") not in {"search", "query", "q"}):
            return None  # Missing ages and other dependent values still block Update.
    rows = []
    for check in checks:
        ids = {item["control_id"] for item in check.get("counter_controls", [])}
        ids.add(check.get("control_id"))
        for item in available:
            counter = item.get("counter") or {}
            field = occupancy_component(counter.get("label", "")) if counter else occupancy_component(
                " ".join(str(item.get(key) or "") for key in ("label", "name")))
            numeric = counter or item.get("tag") in {"INPUT", "SELECT", "TEXTAREA"} or item.get("role") == "spinbutton"
            if (numeric and not age_control(item) and field == check["field"]
                    and (item.get("id") in ids or str(item.get("value", "")) == str(check["expected"]))
                    and str(counter.get("value", item.get("value", ""))) == str(check["expected"])):
                rows.append(item)
    openers = [item for item in available if item.get("expanded") == "true"
               and (item.get("tag") == "BUTTON" or item.get("role") == "button")
               and not item.get("counter") and not item.get("submits_form")
               and len(occupancy_summary_values(str(item.get("label") or "") + " " + str(item.get("text") or ""))) >= 2]
    anchors = rows or openers
    frames = {identity(item)["frame"] for item in anchors}
    scopes = {item["form_scope"] for item in anchors if item.get("form_scope")}
    if len(frames) != 1 or len(scopes) > 1:
        return None

    def associated(item):
        return (item.get("id") and item.get("enabled", True) is not False
                and identity(item)["frame"] in frames
                and (not scopes or not item.get("form_scope") or item["form_scope"] in scopes))

    # widget_scope is a type (counter/choice), not a popup identity. A button
    # beside the rows may legitimately carry a different type or none at all.
    confirm = [item for item in available if rows and associated(item)
               and (item.get("tag") == "BUTTON" or item.get("role") == "button")
               and item.get("tag") != "A" and not item.get("submits_form")
               and item.get("type") not in {"submit", "image"}
               and any(re.fullmatch(r"update|apply|done|confirm|ok|close", str(item.get(key) or "").strip(), re.I)
                       for key in ("label", "text"))]
    if len(confirm) == 1:
        return {"action": "click", "control_id": confirm[0]["id"], "value": ""}
    if confirm:
        return None  # Multiple confirmation controls need further observation.
    openers = [item for item in openers if associated(item)]
    if len(openers) == 1 and all(item.get("status") == "verified" for item in checks):
        # Auto-applying widgets may have no Update button. Dismiss without an
        # edit, then independently read the closed summary and returned scope.
        return {"action": "press", "control_id": openers[0]["id"], "value": "Escape"}
    return None


INFORMATION_ROLES = {
    "author": r"(?:^|_)(?:author|authors|byline)(?:_|$)",
    "published_time": r"(?:^|_)(?:published|publication|publish_date|"
    r"published_time|published_date)(?:_|$)",
    "body": r"^(?:body|context|full_context|full_text|full_content|article_body|"
    r"article_context|article_excerpt|content_body|main_content)$",
    "specifications": r"(?:^|_)(?:specifications|facilities|amenities)(?:_|$)",
}


def information_role(field):
    return next(
        (role for role, pattern in INFORMATION_ROLES.items() if re.search(pattern, field)),
        "other",
    )


def positive_information_request(instructions):
    """Mask topic phrases and exclusions without changing original quote positions."""
    # This is only a small positive-field hint, never a rewrite of the task.
    # A topic containing "authors" is not a request for bylines, and explicitly
    # excluded metadata must not create browser work. Preserve positions so the
    # retained request quotes still come from the original user instruction.
    positive = instructions
    clause_end = r"(?=\b(?:but|and)\s+(?:include|return|provide|show)\b|[.;!?\n]|$)"
    for pattern in (
        r"\b(?:do not|don't|without|exclude|excluding|omit|not|no)\s+[^.;!?\n]*?" + clause_end,
        r"\b(?:about|related\s+to|concerning|regarding|on\s+the\s+topic\s+of)\s+"
        r"[^.;!?\n]*?(?=\b(?:include|return|provide|show)\b|[.;!?\n]|$)",
    ):
        positive = re.sub(pattern, lambda match: " " * len(match[0]), positive, flags=re.I)
    return positive


def requested_information_needs(instructions, output_fields=()):
    """Depth-driving requested content, not a mandatory genre-specific output schema."""
    result = {
        field: {"field": field, "role": information_role(field), "request_quote": "",
                "status": "unknown", "evidence": "", "explicit_output_field": True}
        for field in output_fields
    }
    positive = positive_information_request(instructions)
    patterns = (
        (
            "author", r"\b(?:include|extract|give|get|return|provide|show)\b"
            r"[^.!?\n]{0,80}\b(?:authors?|bylines?)\b",
        ),
        ("published_time", r"\b(?:publication|published|publish)\s+(?:dates?|times?)\b"),
        (
            "body", r"\b(?:full\s+(?:context|content|text)|article\s+(?:body|content)|"
            r"actual\s+articles?|in.depth\s+context)\b",
        ),
        ("body", r"\b(?:get|include|extract|give|return|provide|show)\s+"
         r"(?:(?:the|their|full)\s+)?context\b"),
        ("body", r"\b(?:include|extract|return|provide|show)\b[^.!?\n]{0,80}\bbody\b"),
        ("specifications", r"\b(?:specifications|facilities|amenities)\b"),
    )
    for role, pattern in patterns:
        match = re.search(pattern, positive, re.I)
        if match and not any(need["role"] == role for need in result.values()):
            result[role] = {
                "field": role, "role": role,
                "request_quote": instructions[match.start():match.end()][:200],
                "status": "unknown", "evidence": "", "explicit_output_field": False,
            }
    if (
        not HOTEL_REQUEST.search(instructions)
        and not any(need["role"] == "published_time" for need in result.values())
    ):
        match = re.search(
            r"\b(?:include|return|provide|show)\b[^.!?\n]{0,80}\bdates?\b", positive, re.I
        )
        if match:
            result["published_time"] = {
                "field": "published_time", "role": "published_time",
                "request_quote": instructions[match.start():match.end()][:200],
                "status": "unknown", "evidence": "", "explicit_output_field": False,
            }
    return result


def request_collection_scope(instructions, output_fields=()):
    """Bound navigation depth by the request, not a website genre or model quote.

    A request to find/list relevant records does not itself authorize searching
    another section or opening every result. Start with the supplied page; the
    extraction step assesses relevance. Explicit interactions or detail fields
    may require more depth, using the same existing decision call.
    """
    request = normalized(instructions)
    page_only = bool(
        re.search(r"\b(?:current|this|starting|main)\s+page\s+only\b", request)
        or re.search(r"\b(?:do not|don't|without)\s+(?:open|opening|follow|following)\b", request)
    )
    explicit_links = bool(
        re.search(
            r"\b(?:open|follow|visit|read|enrich)\b[^.!?\n]{0,160}"
            r"\b(?:links?|urls?|pages?|articles?|stories|records?|products?|properties)\b",
            request,
        )
    )
    details = bool(
        explicit_links
        or re.search(
            r"\b(?:context|full content|full text|specifications|facilities|amenities)\b", request
        )
        or re.search(
            r"\b(?:detailed|full)\s+(?:information|description|details|summary)\b", request
        )
        or any(
            re.search(
                r"(?:^|_)(?:context|body|full_text|full_content|specifications|facilities)(?:_|$)",
                field,
            )
            for field in output_fields
        )
    )
    search = bool(
        re.search(r"\bsearch\b", request)
        or re.search(
            r"\b(?:enter|fill|type|submit|set|select|adjust)\b[^.!?\n]{0,80}"
            r"\b(?:form|fields?|query|destination|dates?|guests?|rooms?|filters?)\b",
            request,
        )
        or re.search(r"\b\d{1,2}\s+(?:adults?|children|rooms?|guests?)\b", request)
        or re.search(r"\b(?:check.?in|check.?out|arrival|departure)\b", request)
        or re.search(r"\b(?:origin|destination)\s+(?!urls?\b|links?\b)[a-z]", request)
    )
    if page_only:
        default, allowed, basis = "current_page", ["current_page"], "explicit_page_only"
    elif explicit_links:
        default, allowed, basis = "linked_details", ["linked_details"], "requested_detail_content"
    elif details or output_fields or any(
        need["role"] != "other"
        for need in requested_information_needs(instructions, output_fields).values()
    ):
        default = "search_results" if search else "current_page"
        allowed = [default, "linked_details"]
        basis = "requested_information_needs"
    elif search:
        default, allowed, basis = "search_results", ["search_results"], "explicit_search"
    else:
        default, allowed, basis = "current_page", ["current_page"], "starting_page_records"
    return {"default_mode": default, "allowed_modes": allowed, "basis": basis}


def destination_controls(observation):
    """Prefer destination semantics; only use an unambiguous generic textbox.

    Sites often implement dates and occupancy as type=text. Input type alone
    therefore cannot identify a destination. Empty explicit fields still take
    precedence over a filled, unrelated site-search box.
    """
    explicit, generic = [], []
    for item in controls(observation):
        tag = item.get("tag")
        if tag not in {"INPUT", "SELECT", "TEXTAREA"}:
            continue
        if tag == "INPUT" and item.get("type", "text") not in {"text", "search"}:
            continue
        label = " ".join(str(item.get(k, "")) for k in ("label", "name"))
        if re.search(r"\bdestination\b|where .*going|\blocation\b|\bcity\b", label, re.I):
            explicit.append(item)
        elif not re.search(
            r"check.?in|check.?out|arrival|departure|\bdates?\b|calendar|"
            r"\badults?\b|\bchildren\b|\brooms?\b|\bguests?\b|travel[el]ers?|"
            r"\bprice\b|\bbudget\b|\brating\b|\bcurrency\b|"
            r"\bemail\b|e-mail|newsletter|\bphone\b|\bpassword\b|\bcoupon\b",
            label,
            re.I,
        ):
            if tag == "INPUT":
                generic.append(item)
    if explicit:
        return explicit, False
    return (generic, False) if len(generic) <= 1 else ([], True)


def known_value_control(name, control):
    """Optional rebinding must address a value, not the widget's next actuator."""
    tag, role = control.get("tag"), control.get("role")
    kind = control.get("type", "text")
    if age_control(control) and not age_control({}, name):
        return False
    if age_control({}, name) and not age_control(control):
        return False
    native = tag in {"INPUT", "SELECT", "TEXTAREA"} and kind not in {
        "button",
        "submit",
        "reset",
        "image",
        "file",
        "hidden",
    }
    if name == "destination":
        return (
            native
            and role not in {"option", "gridcell"}
            and (tag != "INPUT" or kind in {"", "text", "search"})
        )
    if name in {"check_in", "check_out"}:
        return (
            native
            and kind not in {"checkbox", "radio"}
            and role not in {"option", "gridcell", "checkbox", "radio"}
        )
    if name in {"adults", "children", "rooms"}:
        quantity_label = " ".join(str(control.get(key) or "") for key in ("label", "name"))
        quantity_label += " " + str((control.get("counter") or {}).get("label") or "")
        quantity_label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", quantity_label).replace("_", " ")
        if occupancy_component(quantity_label) != name:
            return False
        if native and kind not in {"checkbox", "radio"} and role not in {"option", "gridcell"}:
            return True
        counter = control.get("counter")
        if counter:
            component = occupancy_component(counter.get("label", ""))
            return (
                component == name
                and len(occupancy_components(counter.get("label", ""))) <= 1
            )
        return role == "spinbutton"
    return (
        native
        or bool(control.get("counter"))
        or bool(control.get("editable"))
        or role in {"spinbutton", "checkbox", "radio"}
    )


def compact_observation(observation, budget=OBSERVATION_BUDGET):
    """Keep fresh IDs; drop duplicate/empty metadata, then explicitly bound context.

    Internal tool references retain full facts for stale-reference verification.
    This compaction is for navigation only, never the final source capture.
    """
    result = copy.deepcopy(observation)
    limit = max(1000, budget - 600)  # Reserve space for the compaction disclosure.
    for frame in result.get("frames", []):
        frame["text"] = frame.get("text", "")[:4500]
        frame["title"] = frame.get("title", "")[:180]
        compact = []
        for item in frame.get("controls", []):
            kept = {}
            for key, value in item.items():
                if key == "numeric_probe":
                    continue  # Diagnostic-only metadata must not consume navigation context.
                if value in ("", None, [], {}) or (key == "enabled" and value is True):
                    continue
                if key == "readonly" and value is False:
                    continue
                if isinstance(value, str):
                    value = value[: 180 if key in {"label", "context", "text"} else 240]
                if key in {"text", "context"} and value == item.get("label"):
                    continue
                if key == "options":
                    value = [
                        {"value": o["value"], "label": o["label"][:100], "disabled": o["disabled"]}
                        for o in value[:20]
                    ]
                kept[key] = value
            compact.append(kept)
        frame["controls"] = compact

    def size():
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    # Keep control evidence ahead of general body text. Preserve a disclosure when
    # body text, option lists or low-priority controls have to be omitted.
    for frame in reversed(result.get("frames", [])):
        if size() <= limit:
            break
        frame["text"] = frame["text"][: max(0, len(frame["text"]) - (size() - limit))]
    if size() > limit:
        for item in controls(result):
            item.pop("context", None)
            if item.get("text") == item.get("label"):
                item.pop("text", None)
    while size() > limit:
        frame = next((f for f in reversed(result.get("frames", [])) if f.get("controls")), None)
        if frame is None:
            break
        frame["controls"].pop()
        frame["controls_truncated"] = True
    result["navigation_context_compacted"] = True
    result["navigation_context_limit_chars"] = budget
    result["omission_notice"] = (
        "Navigation context is bounded; omitted text/options/controls are not proof of absence. "
        "Open a widget, scroll or pause if a required control is not supplied."
    )
    return result


class TaskLedger:
    def __init__(self, instructions, reference_date=None, output_fields=()):
        self.instructions = instructions
        self.reference_date = reference_date or date.today()
        self.date_resolution = None
        self.requirements = {}
        self.bindings = {}
        self.request_error = None
        self.checks = []
        self.submission = None
        self.pending_submission = None
        self.unresolved_form_fields = []
        self.last_validation_rejection = None
        self.date_choices = {}
        self.date_destination = None
        self.calendar_actions = {}
        self.calendar_progress = None
        self.calendar_resume_requested = False
        self.destination_selections = {}
        self.visible_date_choices = []
        self.submission_candidates = []
        self.collection_mode = "model_decides"
        self.collection_scope = request_collection_scope(instructions, output_fields)
        self.collection_goal = None
        self.collection_sources = []
        self.collection_search = None
        self.information_needs = requested_information_needs(instructions, output_fields)
        self.information_evidence = {}
        self.information_need_feedback = []
        self.partial_reason = ""
        self.detail_candidates = []
        self.document_id = None
        self.requested_stay = requested_stay(instructions, self.reference_date)
        self.result_scope = None
        self.catalog_followup_used = False
        self.catalog_followup = None
        self.navigation_stage = None
        self.result_refresh = None
        self.result_handoff = None
        self.site_behavior = site_search_behavior("", stay_request=bool(self.requested_stay))
        self.stay_edit_context = None
        self.occupancy_recheck_context = None
        if HOTEL_REQUEST.search(instructions):
            try:
                destination = requested_destination(instructions)
                dates, self.date_resolution = resolve_stay_dates(instructions, self.reference_date)
                guests = guest_counts(instructions)
                if guests is None:
                    raise WebsiteError("Clarify the conflicting adults/children/rooms counts.")
                if requested_stay_dates(instructions) and len(dates) != 2:
                    raise WebsiteError(
                        "Provide both stay dates. Use full years if the current-year default "
                        "cannot resolve the range. Cancel this browser and start a new session "
                        "with the corrected request; Resume keeps the original request."
                    )
                if len(dates) == 2 and dates[0] >= dates[1]:
                    raise WebsiteError("Check-out must follow check-in. Correct the request.")
                known = {"destination": destination} if destination else {}
                if len(dates) == 2:
                    known.update(check_in=dates[0], check_out=dates[1])
                known.update({key: str(value) for key, value in (guests or {}).items()})
                self.requirements = {
                    key: {
                        "name": key,
                        "expected": value,
                        "application": "form",
                        "request_quote": instructions[:500],
                    }
                    for key, value in known.items()
                }
                if {"destination", "check_in", "check_out"} <= known.keys():
                    details_requested = bool(
                        re.search(
                            r"\b(?:open|follow|visit|read|enrich)\b[^.!?\n]{0,160}"
                            r"\b(?:links?|urls?|pages?|hotels?|properties)\b",
                            instructions,
                            re.I,
                        )
                    )
                    self.collection_mode = (
                        "linked_details" if details_requested else "listing_results"
                    )
            except WebsiteError as exc:
                self.request_error = str(exc)
        self.search_authorized = (
            "search_results" in self.collection_scope["allowed_modes"]
            or any(item["application"] == "form" for item in self.requirements.values())
        )
        self.set_output_fields(output_fields)

    def set_output_fields(self, output_fields):
        self.collection_scope = request_collection_scope(self.instructions, output_fields)
        for field, need in requested_information_needs(self.instructions, output_fields).items():
            self.information_needs.setdefault(field, need)
        if self.collection_scope["basis"] == "explicit_page_only":
            self.collection_mode = "current_page"
            for requirement in self.requirements.values():
                requirement["application"] = "extraction"
            return
        if any(item["application"] == "form" for item in self.requirements.values()):
            # Existing literal form grounding takes precedence over the generic
            # starting-page default. This is not a site-specific selector recipe.
            linked_required = self.collection_mode == "linked_details" or (
                self.collection_scope["default_mode"] == "linked_details"
                and self.collection_scope["allowed_modes"] == ["linked_details"]
            )
            allowed = ["linked_details"] if linked_required else ["search_results"]
            if not linked_required and "linked_details" in self.collection_scope["allowed_modes"]:
                allowed.append("linked_details")
            self.collection_scope = {
                "default_mode": "linked_details" if linked_required else "search_results",
                "allowed_modes": allowed,
                "basis": "requested_form_values",
            }
        elif self.collection_scope["default_mode"] == "linked_details":
            self.collection_mode = "linked_details"

    def declare_collection_goal(self, goal, observation=None):
        """Commit a valid collection goal, independently of optional field hints.

        Inferred output fields are handled by extraction, not mandatory browser
        prerequisites. Unsupported hints cannot block a valid action or authorize
        extra navigation. Core scope/quote errors still reject the declaration.
        """
        if goal is None:
            return []
        declared = goal.model_dump()
        quote = normalized(declared["request_quote"])
        if not quote or quote not in normalized(self.instructions):
            raise WebsiteError("The collection goal lacks a quote from your request.")
        needs = copy.deepcopy(self.information_needs)
        scope = copy.deepcopy(self.collection_scope)
        notes = []
        declared_needs = declared.get("information_needs", [])
        accepted_needs = []
        for item in declared_needs:
            field = item["field"]
            known = needs.get(field)
            quote = normalized(item.get("request_quote", ""))
            if known is None:
                role = information_role(field)
                same_role = next(
                    (
                        need for need in needs.values()
                        if role != "other" and need["role"] == role
                    ),
                    None,
                )
                named_field = normalized(field.replace("_", " "))
                # A field name in the topic or an exclusion is not authority
                # to collect it. Keep the positive field cue in the same clause
                # and match full words, not e.g. "author" inside "authors".
                explicitly_named = bool(re.search(
                    r"\b(?:include|return|provide|show|get|give|extract|fields?|columns?)\b"
                    r"[^.;!?\n]{0,160}(?<!\w)" + re.escape(named_field) + r"(?!\w)",
                    positive_information_request(normalized(self.instructions)), re.I,
                ))
                if not quote or quote not in normalized(self.instructions) or (
                    same_role is None and not explicitly_named
                ):
                    notes.append({
                        "field": field, "status": "ignored",
                        "reason": "request_quote_unverified"
                        if not quote or quote not in normalized(self.instructions)
                        else "not_requested_navigation_need",
                    })
                    continue
                known = same_role or {
                    "field": field, "role": role, "request_quote": item["request_quote"],
                    "status": "unknown", "evidence": "", "explicit_output_field": False,
                }
                needs.setdefault(known["field"], known)
                if (
                    scope["basis"] != "explicit_page_only"
                    and "linked_details" not in scope["allowed_modes"]
                ):
                    scope["allowed_modes"].append("linked_details")
            accepted_needs.append(item)
            evidence = item.get("evidence", "")
            visible_text = " ".join(
                str(frame.get("text", "")) + " " + " ".join(
                    " ".join(str(control.get(key, "")) for key in ("label", "text", "value"))
                    for control in frame.get("controls", [])
                )
                for frame in (observation or {}).get("frames", [])
            )
            if item["status"] in {"visible", "captured"} and (
                not evidence or normalized(evidence) not in normalized(visible_text)
            ):
                # Model claims cannot create source proof. Keep the need and
                # inspect retained captures after the actual collection action.
                known.update(status="unknown", evidence="")
            else:
                known.update(
                    status="visible" if item["status"] == "captured" else item["status"],
                    evidence=evidence[:220],
                )
        mode = declared["mode"]
        if (
            self.collection_mode == "linked_details"
            and (
                scope["allowed_modes"] == ["linked_details"]
                or any(page["kind"] == "detail" for page in self.collection_sources)
            )
            and mode != "linked_details"
        ):
            raise WebsiteError("Requested linked details cannot be replaced by a page-only goal.")
        if self.collection_mode == "listing_results" and mode == "current_page":
            raise WebsiteError("Complete the requested search before collecting its results.")
        if mode not in scope["allowed_modes"]:
            raise WebsiteError(
                "The collection goal requests a scope outside the user's task: " + mode
                + ". Use " + ", ".join(scope["allowed_modes"]) + "."
            )
        if any(
            item["status"] == "needs_detail" and not self.information_evidence.get(field)
            for field, item in needs.items()
        ):
            if "linked_details" in scope["allowed_modes"]:
                mode = declared["mode"] = "linked_details"
        if mode not in scope["allowed_modes"]:
            raise WebsiteError(
                "The request calls for "
                + scope["default_mode"]
                + "; a matching quote alone does not authorize another collection scope. "
                "Collect the supplied page unless the request explicitly asks for search "
                "or linked detail content."
            )
        # Nothing above mutates live state until all hard goal checks pass.
        declared["information_needs"] = accepted_needs
        self.information_needs = needs
        self.collection_scope = scope
        self.partial_reason = declared.get("partial_reason", "")[:220]
        self.collection_goal = declared
        self.collection_mode = mode
        for note in notes:
            if note not in self.information_need_feedback:
                self.information_need_feedback.append(note)
        self.information_need_feedback = self.information_need_feedback[-8:]
        return notes

    def note_sources(self, pages):
        """Retain small capture facts, not source text or invented detail coverage."""
        self.collection_sources = [
            {"url": page["url"], "kind": page.get("source_kind", "page")} for page in pages
        ]
        self.detail_candidates = []
        for page in pages:
            if page.get("source_kind") != "index":
                continue
            for block in page.get("blocks", []):
                href = block.get("href")
                if (
                    href and block.get("association") == "record"
                    and block.get("kind") in {"heading", "link"}
                    and not query_identity_omitted(href)
                    and not any(item["url"] == href for item in self.detail_candidates)
                ):
                    self.detail_candidates.append({"url": href, "label": block.get("text", "")[:120]})
        self.detail_candidates = self.detail_candidates[:100]
        self.information_evidence = {}
        for field, need in self.information_needs.items():
            evidence = []
            for page in pages:
                blocks = page.get("blocks", [])
                candidates = []
                quote = normalized(need.get("evidence", ""))
                for block in blocks:
                    text = block.get("text", "")
                    role = need["role"]
                    if role == "body":
                        paragraph = block.get("kind") == "paragraph"
                        supported = paragraph and block.get("content_role") == "body"
                        if (
                            not supported and paragraph and page.get("source_kind") == "detail"
                            and block.get("association") != "ambiguous"
                            and len(quote) >= 80 and len(text) >= 160
                            and quote in normalized(text)
                        ):
                            # Unfamiliar non-article layouts may lack a DOM body
                            # role. Keep only a model-identified literal long
                            # detail paragraph, never an index teaser or inferred
                            # complete page. Semantic accuracy remains reviewed.
                            supported = True
                    elif quote:
                        supported = quote in normalized(text)
                    elif role == "author":
                        supported = bool(re.search(
                            r"^\s*(?:by\s+\S|author\s*:|written by\b)", text, re.I
                        ))
                    elif role == "published_time":
                        try:
                            supported = bool(
                                re.search(r"\b(?:published|posted|updated)\b", text, re.I)
                                and requested_dates(text)
                            )
                        except WebsiteError:
                            supported = False
                    elif role == "specifications":
                        supported = bool(re.search(
                            r"\b(?:specifications|facilities|amenities)\s*:\s*\S", text, re.I
                        ))
                    elif field.endswith("url") or field in {"url", "link", "listing_url"}:
                        supported = bool(block.get("href"))
                    else:
                        supported = False
                    if supported:
                        candidates.append(block)
                if candidates:
                    evidence.append({
                        "source_url": page["url"], "source_kind": page.get("source_kind", "page"),
                        "block_ids": [block["id"] for block in candidates[:3] if block.get("id")],
                        "quote": candidates[0].get("text", "")[:180],
                    })
            self.information_evidence[field] = evidence[:6]
        # Result-page form proof may support later detail collection, but never
        # proves a detail page's availability, prices or extracted values.
        if self.collection_mode == "linked_details":
            self.collection_search = None
            for page in pages:
                context = page.get("browser_task_context") or {}
                if context.get("status") not in {
                    "form_verified_search_submitted", "observed_matching_results"
                }:
                    continue
                expected = {
                    name: normalized(item["expected"])
                    for name, item in self.requirements.items()
                    if item["application"] == "form"
                }
                checked = {
                    item["field"]: normalized(item["expected"])
                    for item in context.get("requirements", [])
                    if item.get("application") == "form" and item.get("status") == "verified"
                }
                if expected and expected == checked and context.get("result_url") == page["url"]:
                    if (
                        not self.requested_stay
                        or (context.get("result_scope") or {}).get("status") == "verified"
                    ):
                        self.collection_search = copy.deepcopy(context)

    def collection_progress(self):
        return {
            "sources": copy.deepcopy(self.collection_sources),
            "captured_pages": len(self.collection_sources),
            "detail_pages": sum(p["kind"] == "detail" for p in self.collection_sources),
            "max_pages": 6,
            "max_detail_pages": 5,
            "coverage": "Captured sources only; not proof of website completeness.",
            "information_coverage": self.information_coverage(),
            "detail_candidates": copy.deepcopy(self.detail_candidates[:20]),
        }

    def information_coverage(self):
        covered = [field for field in self.information_needs if self.information_evidence.get(field)]
        pending = [field for field in self.information_needs if field not in covered]
        detail_needed = [
            field for field in pending
            if self.information_needs[field]["status"] == "needs_detail"
            or (
                self.information_needs[field]["role"] != "other"
                and self.information_needs[field]["status"] != "unavailable"
            )
        ]
        status = (
            "not_requested" if not self.information_needs else "partial"
            if pending or self.partial_reason else "source_evidence_available"
        )
        return {
            "status": status,
            "requested_fields": list(self.information_needs), "fields_with_source_evidence": covered,
            "missing_fields": pending, "partial_reason": self.partial_reason,
            "detail_needed_fields": detail_needed,
            "note": "Evidence occurs in some captured sources, sometimes a bounded detail "
            "paragraph. Per-record completeness and semantic accuracy require extraction review.",
        }

    def scope_problem(self, decision, facts):
        """Stop unrequested cross-page wandering while retaining page preparation."""
        if (
            self.collection_mode == "linked_details"
            and decision.action == "click"
            and facts.get("href")
            and not any(page["kind"] == "index" for page in self.collection_sources)
        ):
            return (
                "Retain the actual starting/results index before opening a detail link. "
                "Capture the current page as index, then choose its relevant links."
            )
        if (
            self.collection_mode == "linked_details" and decision.action == "click"
            and facts.get("href")
        ):
            target = facts["href"]
            if query_identity_omitted(target) or clean_url(target) not in {
                clean_url(item["url"]) for item in self.detail_candidates
            }:
                return (
                    "Choose an actual record link from the retained index for the missing "
                    "information. Section/navigation/search links do not provide its detail context. "
                    "If no relevant record link is available, finish with a partial_reason."
                )
        label = normalized(facts.get("label") or facts.get("text") or "")
        search_button = (
            (facts.get("tag") in {"BUTTON", "INPUT"} or facts.get("role") == "button")
            and not widget_control(facts)
            and (
                facts.get("submits_form")
                or facts.get("type") in {"submit", "image"}
                or re.search(r"^(?:search|find)\b", label)
            )
        )
        if (
            "search_results" not in self.collection_scope["allowed_modes"]
            and not self.search_authorized
            and (search_button or decision.action in {"fill", "select", "set_counter"})
        ):
            return (
                "Requested information may be collected from this page and relevant same-site "
                "detail links. An unrelated website search was not requested."
            )
        if self.collection_scope["allowed_modes"] != ["current_page"]:
            if (
                decision.action == "click" and facts.get("href")
                and self.collection_mode != "linked_details"
                and "linked_details" in self.collection_scope["allowed_modes"]
            ):
                return (
                    "Declare which requested information needs this same-site detail link, "
                    "and retain the useful current page as index before opening it."
                )
            return None
        if (
            decision.action in {"fill", "select", "check", "set_counter", "back"}
            or decision.action == "press"
            and decision.value != "Escape"
            or decision.action == "click"
            and (facts.get("href") or search_button)
        ):
            return (
                "This request collects relevant records from the starting page. "
                "Capture/finish that page for extraction; no section, search or detail "
                "navigation was requested."
            )
        return None

    def collection_problem(self, current_url, finish_kind):
        if self.collection_mode == "search_results" and not self.submission:
            return (
                "The search-results goal needs a confirmed Search transition. Complete "
                "the requested search and observe its results before finishing. If all "
                "requested data was already visible without searching, use current_page."
            )
        if self.collection_mode != "linked_details":
            return None
        indexes = {p["url"] for p in self.collection_sources if p["kind"] == "index"}
        if not indexes:
            return "Retain the useful starting/index page before opening its relevant links."
        details = {
            p["url"]
            for p in self.collection_sources
            if p["kind"] == "detail" and p["url"] not in indexes
        }
        if (
            not details and not (finish_kind == "detail" and current_url not in indexes)
            and not self.partial_reason
        ):
            return (
                "The request needs linked details, but no distinct detail page has been "
                "captured. Open a relevant same-site link and collect its actual content, "
                "or pause if unavailable. Headlines alone do not complete this goal."
            )
        missing = self.information_coverage()["detail_needed_fields"]
        current_detail_pending_capture = (
            finish_kind == "detail" and current_url not in indexes
            and not any(page["url"] == current_url for page in self.collection_sources)
        )
        if (
            missing and not self.partial_reason and len(self.collection_sources) < 6
            and not current_detail_pending_capture
        ):
            return (
                "Requested information still lacks captured source evidence: " + ", ".join(missing)
                + ". Capture the current relevant detail or open another relevant same-site "
                "link. If it is unavailable, finish with an explicit partial_reason; do not "
                "claim those fields were collected."
            )
        return None

    def declare(self, requirements, observation=None):
        """Atomically declare new grounding or optionally bind known, unchanged values.

        Existing values already have request evidence, including canonical dates
        which need not occur verbatim in the request. Redundant model metadata may
        not replace that grounding or bind a known value to an option/opener.
        """
        staged_requirements = copy.deepcopy(self.requirements)
        staged_bindings = copy.deepcopy(self.bindings)
        ignored = []
        for item in requirements or ():
            requirement = item.model_dump()
            name = requirement["name"]
            known = self.requirements.get(name)
            actual = next((control for control in controls(observation or {})
                           if control.get("id") == requirement.get("control_id")), {})
            destination = staged_requirements.get("destination")
            same_destination = bool(destination and normalized(requirement["expected"]) == normalized(destination["expected"]))
            if (HOTEL_REQUEST.search(self.instructions) and name not in STAY_FIELDS
                    and requirement["application"] == "form" and destination
                    and discovery_query_control(actual) and (query_field_name(name) or same_destination)):
                reason = "destination_already_grounded" if same_destination else "query_is_navigation"
                staged_requirements.pop(name, None)
                staged_bindings.pop(name, None)
                ignored.append({"field": name, "reason": reason})
                continue  # Query action arguments are not persistent stay criteria.
            previous = staged_requirements.get(name)
            if previous and any(
                normalized(previous[k]) != normalized(requirement[k])
                for k in ("expected", "application")
            ):
                raise WebsiteError(
                    f"The agent changed the requested {name}. Observe and correct it."
                )
            if not known:
                quote = normalized(requirement["request_quote"])
                if not quote or quote not in normalized(self.instructions):
                    if requirement["application"] == "form":
                        raise MissingFormValue(name, actual.get("label"))
                    raise WebsiteError("A task requirement lacks a quote from your request.")
                interpreted = normalized(requirement["expected"]) not in quote
                if requirement["application"] == "form" and not literal_form_value(requirement, actual):
                    raise MissingFormValue(name, actual.get("label"))
                if actual and age_control(actual) and normalized(requirement["expected"]) not in self.allowed_age_values(actual, observation or {}):
                    raise MissingFormValue(name, actual.get("label"))
                if interpreted and not requirement.get("interpretation"):
                    raise WebsiteError(
                        "A new form/filter expectation must use an explicit value "
                        "from your request."
                    )
                if name not in staged_requirements and len(staged_requirements) >= 16:
                    raise WebsiteError("Too many task requirements; narrow the request.")
                staged_requirements[name] = requirement
                staged_requirements[name]["model_interpreted"] = interpreted
            if requirement.get("control_id"):
                candidates = [
                    c
                    for c in controls(observation or {})
                    if c.get("id") == requirement["control_id"]
                ]
                if requirement["application"] != "form" or len(candidates) != 1:
                    if known:
                        continue  # Redundant metadata cannot create a fresh association.
                    raise WebsiteError("Bind a form requirement to one fresh observed control ID.")
                if known and not known_value_control(name, candidates[0]):
                    continue  # A legitimate click still runs; its optional binding is unnecessary.
                if age_control(candidates[0]) and normalized(requirement["expected"]) not in self.allowed_age_values(candidates[0], observation):
                    raise MissingFormValue(name, candidates[0].get("label"))
                staged_bindings[name] = {
                    "document": observation.get("document_id", observation.get("url")),
                    "identity": identity(candidates[0]),
                    "counter_label": (candidates[0].get("counter") or {}).get("label"),
                }
        destination = staged_requirements.get("destination")
        if destination and HOTEL_REQUEST.search(self.instructions):
            for name, binding in list(staged_bindings.items()):
                requirement = staged_requirements.get(name) or {}
                if (name not in STAY_FIELDS and requirement.get("application") == "form"
                        and discovery_query_control(binding.get("identity") or {})
                        and (query_field_name(name) or normalized(requirement.get("expected")) == normalized(destination["expected"]))):
                    staged_requirements.pop(name, None)
                    staged_bindings.pop(name, None)
                    ignored.append({"field": name, "reason": "query_is_navigation"})
        self.requirements = staged_requirements
        self.bindings = staged_bindings
        destination = self.requirements.get("destination")
        if (HOTEL_REQUEST.search(self.instructions) and destination and destination["application"] == "form"
                and not self.requested_stay.get("destination")):
            # A grounded model interpretation can supply a literal place that
            # the lightweight parser missed. Never replace an existing value.
            self.requested_stay["destination"] = destination["expected"]
            if self.collection_mode == "model_decides" and {"check_in", "check_out"} <= self.requested_stay.keys():
                self.collection_mode = "listing_results"
        return ignored

    def counter_field(self, control):
        """Resolve requested numeric fields from live labels/bindings, not site names."""
        if age_control(control):
            return None
        label = (control.get("counter") or {}).get("label", control.get("label", ""))
        if len(occupancy_components(label)) > 1:
            # Do not let generic name/binding fallback turn a mixed opener into
            # one row just because only one requested field happens to match.
            return None
        component = occupancy_component(label)
        if component in self.requirements and self.requirements[component]["application"] == "form":
            return component
        found = []
        for name, requirement in self.requirements.items():
            if requirement["application"] != "form" or not str(requirement["expected"]).isdigit():
                continue
            binding = self.bindings.get(name)
            if (
                binding
                and (
                    binding["identity"] == identity(control)
                    or (
                        binding.get("counter_label")
                        and binding["counter_label"] == label
                        and binding["identity"]["frame"] == identity(control)["frame"]
                    )
                )
            ) or re.search(rf"\b{re.escape(name.replace('_', ' '))}\b", label, re.I):
                found.append(name)
        return found[0] if len(found) == 1 else None

    def occupancy_recheck(self, observation, *, include_verified=False):
        """Describe a unique closed opener when independent counts need read-back.

        This is navigation evidence only. A matching combined guest total does
        not verify its adult/child split, and old popup rows are never retained
        as proof of the committed form.
        """
        if self.pending_submission or self.submission and not include_verified:
            return None
        if not include_verified and (any(
                check["field"] in {"destination", "check_in", "check_out"}
                and check["application"] == "form" and check["status"] != "verified"
                for check in self.checks
        ) or any(field["field"] in {"destination", "check_in", "check_out"} and field["status"] == "mismatch"
                 for field in (self.result_scope or {}).get("fields", []))):
            return None  # Correct the place/dates before reopening guests for readback.
        pending = [
            check["field"] for check in self.checks
            if check["field"] in {"adults", "children", "rooms"}
            and check["application"] == "form" and check["status"] != "verified"
        ]
        if not pending and not include_verified:
            return None
        expected = {
            name: int(requirement["expected"]) for name, requirement in self.requirements.items()
            if name in {"adults", "children", "rooms"} and requirement["application"] == "form"
            and str(requirement["expected"]).isdigit()
        }
        if not expected:
            return None
        frames = {
            self.bindings[name]["identity"]["frame"] for name in expected if name in self.bindings
            and self.bindings[name]["document"] == observation.get("document_id", observation.get("url"))
        }
        openers = []
        available = controls(observation)
        for control in available:
            if (not control.get("id") or control.get("enabled", True) is False or control.get("counter") or age_control(control)
                    or control.get("tag") != "BUTTON" and control.get("role") != "button"
                    or control.get("expanded") == "true"
                    or frames and identity(control)["frame"] not in frames):
                continue
            label = " ".join(str(control.get(key) or "") for key in ("label", "text"))
            if (control.get("submits_form") or control.get("type") == "submit"
                    or re.search(r"\b(?:search|find|reserve|book|add|remove|increase|decrease)\b", label, re.I)):
                continue
            counts = occupancy_summary_values(label)
            if not (control.get("expanded") == "false"
                    or control.get("haspopup") not in {None, "", "false"}
                    or counts.get("rooms") and counts.get("guests")):
                continue
            if not re.search(r"\badults?\b|\bchildren\b|\bchild\b|\bkids?\b|\brooms?\b|\bguests?\b|\btravell?ers?\b", label, re.I):
                continue
            widget_controls = [
                item for item in available if identity(item)["frame"] == identity(control)["frame"]
                and not (control.get("form_scope") and item.get("form_scope")
                         and item["form_scope"] != control["form_scope"])
            ]
            if any(item.get("counter") and occupancy_components(item["counter"].get("label", ""))
                   for item in widget_controls) and any(
                item.get("enabled", True) is not False
                and (item.get("tag") in {"BUTTON", "INPUT"} or item.get("role") == "button")
                and any(re.fullmatch(r"update|apply|done|confirm|ok|close", normalized(item.get(key) or ""))
                        for key in ("label", "text"))
                for item in widget_controls
            ):
                continue  # A visible row/confirmation pair still describes an open widget.
            openers.append((control, label))
        if len(openers) != 1:
            return None
        control, label = openers[0]
        counts = occupancy_summary_values(label)
        total = expected["adults"] + expected["children"] if {"adults", "children"} <= expected.keys() else None
        return {
            "document_id": observation.get("document_id", observation.get("url")),
            "summary": label[:1600],
            "pending_fields": pending,
            "field_statuses": {
                check["field"]: {"status": check["status"], "observed": check.get("observed")}
                for check in self.checks if check["field"] in {"adults", "children", "rooms"}
                and check["application"] == "form"
            },
            "opener": {
                "control_id": control.get("id"), "label": str(control.get("label") or label)[:600],
                "frame": identity(control)["frame"], "form_scope": control.get("form_scope"),
                "identity": identity(control),
            },
            "observed_counts": {name: values for name, values in counts.items() if name != "guests"},
            "expected_counts": expected,
            "observed_total_guests": counts.get("guests", []),
            "expected_total_guests": total,
            "note": "Open the observed occupancy widget and read each requested row independently. "
                    "A combined guest total is not an adult or child count.",
        }

    def confirm_occupancy_inspection(self, observation, closed_diagnostic):
        """Compare committed rooms/total with fresh independent popup rows.

        The caller witnesses the read-only reopen after Update. This method
        neither retains hidden rows nor proves that result cards refreshed.
        """
        document = observation.get("document_id", observation.get("url"))
        if (not isinstance(closed_diagnostic, dict) or not isinstance(document, str) or not document
                or closed_diagnostic.get("document_id") != document):
            return None
        expected = {
            name: int(requirement["expected"]) for name, requirement in self.requirements.items()
            if name in {"adults", "children", "rooms"} and requirement["application"] == "form"
            and str(requirement["expected"]).isdigit()
        }
        if not expected:
            return None
        closed_opener = closed_diagnostic.get("opener")
        if not isinstance(closed_opener, dict) or not isinstance(closed_opener.get("identity"), dict):
            return None
        committed = occupancy_summary_values(closed_diagnostic.get("summary") or closed_opener.get("label", ""))
        if not committed or any(len(values) != 1 for values in committed.values()):
            return None
        if any(field in committed and committed[field] != [value] for field, value in expected.items()):
            return None
        if {"adults", "children"} <= expected.keys() and committed.get("guests") not in (
            None, [expected["adults"] + expected["children"]]
        ):
            return None
        main_controls = (observation.get("frames") or [{}])[0].get("controls", [])
        prior_identity = closed_opener["identity"]
        openers = []
        for control in main_controls:
            if (not control.get("id") or control.get("enabled", True) is False or control.get("counter")
                    or age_control(control) or control.get("tag") != "BUTTON" and control.get("role") != "button"
                    or any(identity(control).get(key, "") != prior_identity.get(key, "")
                           for key in ("frame", "tag", "type", "role", "name"))
                    or closed_opener.get("form_scope") and control.get("form_scope")
                    and closed_opener["form_scope"] != control["form_scope"]):
                continue
            text = " ".join(str(control.get(key) or "") for key in ("label", "text"))
            counts = occupancy_summary_values(text)
            if all(counts.get(field) == values for field, values in committed.items()):
                openers.append((control, counts))
        if len(openers) != 1:
            return None
        opener, current_summary = openers[0]
        if any(field in current_summary and current_summary[field] != [value]
               for field, value in expected.items()):
            return None
        # Requested counts are targets. Other visible rows are read only to
        # cross-check the site's committed summary, never to invent defaults.
        readings = {field: [] for field in ("adults", "children", "rooms")}
        for control in main_controls:
            if (not control.get("id") or age_control(control) or control.get("invalid") is True
                    or control.get("value_missing") is True or control.get("selection_placeholder") is True
                    or identity(control)["frame"] != identity(opener)["frame"]
                    or opener.get("form_scope") and control.get("form_scope")
                    and opener["form_scope"] != control["form_scope"]):
                continue
            counter = control.get("counter") or {}
            if counter:
                field, value = occupancy_component(counter.get("label", "")), counter.get("value")
                evidence = counter.get("evidence") or str(counter.get("label", "")) + " " + str(value)
            elif control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}:
                label = " ".join(str(control.get(key) or "") for key in ("label", "name"))
                field, value = occupancy_component(label), control.get("value")
                evidence = label + " " + str(value)
            else:
                continue
            if field in readings and not isinstance(value, bool) and re.fullmatch(r"\d{1,3}", str(value)):
                readings[field].append((int(value), control["id"], str(evidence)[:300]))
        if any({value for value, _, _ in readings[field]} != {expected[field]} for field in expected):
            return None
        observed = {field: {value for value, _, _ in entries} for field, entries in readings.items() if entries}
        if any(len(values) != 1 for values in observed.values()):
            return None
        if any(field in observed and observed[field] != set(values) for field, values in committed.items()
               if field != "guests"):
            return None
        if committed.get("guests") and {"adults", "children"} <= observed.keys():
            total = next(iter(observed["adults"])) + next(iter(observed["children"]))
            if committed["guests"] != [total]:
                return None
        by_id = {control.get("id"): control for control in main_controls}
        for entries in readings.values():
            row_controls = [by_id[control_id] for control_id in dict.fromkeys(item[1] for item in entries)]
            native = [control for control in row_controls if not control.get("counter")
                      or control.get("counter", {}).get("method") in {"number_input", "spinbutton"}]
            directions = [control["counter"].get("direction") for control in row_controls
                          if control.get("counter") and control not in native]
            if len(native) > 1 or len(directions) > 2 or any(
                directions.count(direction) > 1 for direction in ("increase", "decrease", "both")
            ):
                return None  # Repeated per-room rows are not a verified overall count.
        return {
            "document_id": document,
            "method": "post_commit_readback",
            "closed_diagnostic": copy.deepcopy(closed_diagnostic),
            "checked_counts": expected,
            "readings": {
                field: {"value": expected[field], "status": "verified",
                        "control_ids": list(dict.fromkeys(control_id for _, control_id, _ in entries)),
                        "evidence": "; ".join(dict.fromkeys(evidence for _, _, evidence in entries))[:600]}
                for field, entries in readings.items() if field in expected
            },
            "opener": {
                "control_id": opener["id"], "label": str(opener.get("label") or "")[:600],
                "frame": identity(opener)["frame"], "form_scope": opener.get("form_scope"),
                "identity": identity(opener),
            },
        }

    def allowed_age_values(self, control, observation):
        """Keep a supplied child's age from being reused for an unknown sibling."""
        ages = explicit_age_values(self.instructions)
        label = " ".join(str(control.get(key) or "") for key in ("label", "name")).replace("_", " ")
        ordinal = re.search(r"\b(?:child|kid)\s*(?:age\s*)?(?:number\s*|#\s*)?(\d+)\b", label, re.I)
        if ordinal:
            index = int(ordinal.group(1)) - 1
            return ages[index:index + 1] if index >= 0 else []
        children = str((self.requirements.get("children") or {}).get("expected", "0"))
        count = int(children) if children.isdigit() else 0
        fields = [item for item in controls(observation)
                  if identity(item)["frame"] == identity(control)["frame"]
                  and (item.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
                       or item.get("role") in {"combobox", "textbox", "spinbutton"})
                  and age_control(item)]
        return ages if len(ages) == 1 and max(count, len(fields)) <= 1 else []

    def action_value_problem(self, facts, decision, observation, *, structured=False):
        """Authorize actual edits, never a model's unsupported choice of a value."""
        action, value = decision.action, str(decision.value)
        day = calendar_day(facts)
        if day and action in {"click", "check"}:
            requested = {
                item["expected"] for item in self.requirements.values()
                if item["name"] in {"check_in", "check_out"} and item["application"] == "form"
            }
            if requested and day not in requested:
                raise WebsiteError("That calendar day is not a requested stay date. No click was sent. "
                                   "Use the requested full date and inspect the calendar month before choosing.")
            # A native checkbox can be a calendar's day actuator. Its date is
            # the supplied value; an unrelated checkbox still needs its own
            # explicit request. Never authorize unchecking a selected day.
            if day in requested and (action == "click" or normalized(value) == "true"):
                return None
        available = controls(observation)
        owners = [item for item in available if facts.get("id") in item.get("option_ids", [])
                  and identity(item)["frame"] == identity(facts)["frame"]]
        if action == "click" and (navigation_choice(facts, owners)
                                  or self.discovery_navigation(decision, facts, observation)):
            # A search popup may also contain category tabs or actual links.
            # Opening one does not enter a missing value into its search field.
            return None
        owner = owners[0] if action == "click" and len(owners) == 1 else facts
        option_click = action == "click" and (bool(owners) or facts.get("role") == "option")
        choice = facts.get("type") in {"checkbox", "radio"} or facts.get("role") in {"checkbox", "radio"}
        changing_key = action == "press" and value not in {"Enter", "Escape", "Tab", "Shift+Tab"} and (
            owner.get("tag") in {"INPUT", "TEXTAREA", "SELECT"}
            or owner.get("role") in {"combobox", "spinbutton", "checkbox", "radio", "textbox"}
        ) and not self.is_submit(decision, facts)
        if not (action in {"fill", "select", "check", "set_counter"}
                or action == "click" and (option_click or choice or facts.get("counter"))
                or changing_key):
            return None
        label = str(owner.get("label") or owner.get("name") or "the required field")[:180]
        missing_error = MissingFormValue(label, label)
        missing = missing_error if structured else str(missing_error)
        if option_click and len(owners) != 1:
            error = MissingFormValue("unidentified_choice", "the field associated with this choice")
            return error if structured else str(error)

        def matches(expected):
            if action == "select":
                options = [option for option in owner.get("options", [])
                           if str(option.get("value", "")) == value or normalized(option.get("label", "")) == normalized(value)]
                return any(not option.get("disabled") and (
                    normalized(option.get("value", "")) == normalized(expected)
                    or normalized(option.get("label", "")) == normalized(expected)
                    or str(expected).isdigit() and re.fullmatch(
                        rf"{re.escape(str(expected))}\s*(?:years?(?:\s+old)?)?", normalized(option.get("label", ""))
                    )
                ) for option in options)
            if option_click:
                return normalized(expected) in {
                    normalized(facts.get(key, "")) for key in ("value", "option_primary", "label", "text")
                }
            if action == "click" and choice:
                return normalized(expected) == ("false" if facts.get("selected") == "true" else "true")
            if action == "click" and facts.get("counter"):
                counter = facts["counter"]
                return str(expected).isdigit() and isinstance(counter.get("value"), int) and (
                    counter.get("direction") == "increase" and counter["value"] < int(expected)
                    or counter.get("direction") == "decrease" and counter["value"] > int(expected)
                )
            return not changing_key and normalized(expected) == normalized(value)

        # An age can never borrow a seeded occupancy count or an incidental date.
        if age_control(owner):
            ages = self.allowed_age_values(owner, observation)
            return None if ages and any(matches(age) for age in ages) and not changing_key else missing

        if action == "fill" and HOTEL_REQUEST.search(self.instructions) and discovery_query_control(owner):
            destination = self.requirements.get("destination")
            if not destination or normalized(value) != normalized(destination["expected"]):
                # A literal number in the request is not a destination query.
                # Reject the model's action rather than asking the user to fill
                # a fictitious missing Search field or overwriting a city with
                # a guest count/date through the generic literal-query fallback.
                raise WebsiteError(
                    "The hotel Search field accepts the requested destination, not guest counts or stay dates. "
                    "Use the separate date/guest controls; no new Search value is needed from the user. "
                    "No value was entered."
                )

        grounded = []
        for name, requirement in self.requirements.items():
            if requirement["application"] != "form" or not known_value_control(name, owner):
                continue
            binding = self.bindings.get(name)
            bound = bound_controls(binding, observation) if binding else []
            checked = any(check.get("field") == name and check.get("control_id") == owner.get("id") for check in self.checks)
            counter = action == "set_counter" and self.counter_field(owner) == name
            if any(item.get("id") == owner.get("id") for item in bound) or checked or counter:
                grounded.append(requirement)
        for requirement in grounded:
            if option_click and requirement["name"] == "destination":
                return None  # Existing owned-destination selection checks verify this choice.
            if matches(requirement["expected"]):
                return None
        search_field = owner.get("type") == "search" or bool(re.search(
            r"\b(?:search|query)\b|^q$", str(owner.get("label", "")) + " " + str(owner.get("name", "")), re.I
        ))
        if action == "fill" and search_field and value.strip() and re.search(
            rf"(?<!\w){re.escape(normalized(value))}(?!\w)", normalized(self.instructions)
        ):
            return None
        return missing

    def destination_key(self, control, observation):
        """Track a field, not the ephemeral handle assigned to each observation."""
        field = identity(control)
        # form_scope is an inventory index, not a persistent form identity.
        # An unrelated promo/form insertion must not erase a committed option
        # on the same uniquely named input. Ambiguous/unnamed inputs still
        # retain their scope; verify() must independently bind one live field.
        named = [
            item for item in controls(observation)
            if all(identity(item)[key] == field[key] for key in ("frame", "tag", "type", "name"))
        ] if field["name"] else []
        if len(named) == 1:
            field.pop("label")
            field.pop("role")
        else:
            field["form_scope"] = control.get("form_scope")
        return (
            observation.get("document_id", observation.get("url")),
            json.dumps(field, sort_keys=True),
        )

    @staticmethod
    def destination_options(control, observation):
        ids = set(control.get("option_ids", []))
        frame = identity(control)["frame"]
        return [
            item
            for item in controls(observation)
            if item.get("id") in ids
            and identity(item)["frame"] == frame
            and item.get("enabled", True)
            and not navigation_choice(item, [control])
        ]

    def before_action(self, facts, decision, observation):
        """Invalidate tentative proof before an action, including uncertain outcomes."""
        action = getattr(decision, "action", "click")
        day = calendar_day(facts) if action in {"click", "check"} else None
        field = next((name for name in ("check_in", "check_out")
                      if (self.requirements.get(name) or {}).get("expected") == day), None) if day else None
        destination_fields = destination_controls(observation)[0] if "destination" in self.requirements else []
        changes_destination = (
            action == "fill" and any(facts.get("id") == owner.get("id") for owner in destination_fields)
            or action == "click" and any(
                facts.get("id") in {item.get("id") for item in self.destination_options(owner, observation)}
                for owner in destination_fields
            )
        )
        edits_stay = bool(changes_destination or day or action == "click" and facts.get("counter")
                          or action in {"fill", "select", "check", "set_counter"}
                          and self.stay_form_control(facts))
        same_counter = action == "set_counter" and str((facts.get("counter") or {}).get("value")) == str(getattr(decision, "value", ""))
        same_text = action == "fill" and str(facts.get("value", "")) == str(getattr(decision, "value", ""))
        if self.requested_stay and edits_stay and not (same_counter or same_text):
            self.stay_edit_context = {
                "document_id": observation.get("document_id", observation.get("url")),
                "url": observation.get("url"),
            }
        if changes_destination or day and field != "check_out" or (
            action in {"fill", "select"} and facts.get("date_kind") in {"opener", "date_opener"}
        ):
            # Year evidence belongs to the current stay selection. Opening or
            # closing its picker is passive; editing a day/location is not.
            self.date_choices.clear()
        elif day:
            self.date_choices.pop(day, None)
        if field and field not in self.calendar_actions:
            if field == "check_in":
                self.calendar_actions.pop("check_out", None)
            self.calendar_actions[field] = {
                "date": day, "page_id": calendar_page(observation),
                "frame": identity(facts)["frame"], "widget_id": facts.get("date_widget_id"),
                "status": "attempted",
            }
        if action not in {"wait", "inspect", "scroll"}:
            # An unrelated later click must not turn an ineffective option click
            # into proof merely by dismissing its still-open suggestions.
            for selection in self.destination_selections.values():
                if selection["pending"]:
                    selection.pop("choice", None)
                selection["pending"] = False
        if action == "fill":
            # Retyping the SAME text also clears a site's committed location ID.
            selection = self.destination_selections.get(self.destination_key(facts, observation))
            if selection:
                selection.update(selected=False, pending=False)
                selection.pop("choice", None)

    def calendar_action_problem(self, facts, decision, observation):
        if decision.action not in {"click", "check"}:
            return None
        day = calendar_day(facts)
        page = calendar_page(observation)
        if day and any(item["page_id"] == page and item["date"] == day
                       for item in self.calendar_actions.values()):
            return (f"Selection of {day} was already attempted in this calendar session. "
                    "No repeat was sent. Inspect the selected start/end dates before Resume.")
        return None

    def calendar_reselection_required(self, facts, observation):
        """An old range interior needs a new click only with full summary proof."""
        day = calendar_day(facts)
        if not day or facts.get("selected") != "true":
            return False
        if (self.calendar_progress and self.calendar_progress.get("next_field") == "check_out"
                and day == (self.requirements.get("check_out") or {}).get("expected")
                and "check_out" not in self.calendar_actions):
            return True  # One new end selection after a confirmed draft start.
        if self.calendar_actions:
            return False
        endpoints = {name: set() for name in ("check_in", "check_out")}
        for item in controls(observation):
            field = item.get("date_endpoint")
            if item.get("date_kind") not in {"opener", "date_opener"} or field not in endpoints:
                continue
            try:
                dates = requested_dates(str(item.get("date") or item.get("value") or ""))
            except WebsiteError:
                dates = []
            endpoints[field].update(dates if len(dates) == 1 else [])
        if any(len(values) != 1 for values in endpoints.values()):
            return False
        start, end = (next(iter(endpoints[name])) for name in ("check_in", "check_out"))
        field = next((name for name in endpoints if (self.requirements.get(name) or {}).get("expected") == day), None)
        return bool(field and start < end and start <= day <= end and day not in endpoints[field])

    def observed_calendar_progress(self, observation):
        """Draft picks advance the picker; they never verify the committed stay."""
        if not all((self.requirements.get(field) or {}).get("application") == "form"
                   for field in ("check_in", "check_out")):
            return None
        document = observation.get("document_id", observation.get("url"))
        if self.document_id == document and all(any(
            item["field"] == field and item["status"] == "verified"
            and item.get("method") in {"visible_form", "visible_returned_field", "bound_control_readback"}
            and item["expected"] == self.requirements[field]["expected"]
            for item in self.checks
        ) for field in ("check_in", "check_out")):
            # A stale selected-day marker can remain in an open picker after
            # both actual date fields have committed. Its older draft action
            # must not redirect the runtime back to selecting those dates.
            return None
        picked = {}
        for field, action in self.calendar_actions.items():
            if (action["page_id"] != calendar_page(observation) or not action.get("widget_id")
                    or action.get("status") not in {"selected", "action_performed", "value_verified"}):
                continue
            live = [item for item in controls(observation)
                    if item.get("date_kind") == "day_choice" and item.get("selected") == "true"
                    and calendar_day(item) == action["date"] and identity(item)["frame"] == action["frame"]
                    and item.get("date_widget_id") == action["widget_id"]]
            if live:
                picked[field] = {**action, "control_ids": [item["id"] for item in live]}
        if not picked:
            return None
        start = picked.get("check_in")
        end = picked.get("check_out")
        ready = bool(start and end and start["widget_id"] == end["widget_id"] and start["frame"] == end["frame"])
        ready |= bool(not start and end and any(item["field"] == "check_in" and item["status"] == "verified"
                                                for item in self.checks))
        anchor = start or end
        return {"status": "awaiting_commit" if ready else "check_in_selected" if start else "selection_unconfirmed",
                "next_field": None if ready else "check_out" if start else "check_in",
                "document_id": document, "frame": anchor["frame"], "widget_id": anchor["widget_id"],
                "picked_dates": {field: item["date"] for field, item in picked.items()},
                "control_ids": [cid for item in picked.values() for cid in item["control_ids"]],
                "note": "Draft calendar progress only; commit/close and read the full stay summary."}

    def remember_result_action(self, facts, outcome, decision, observation):
        """Remember an actual criteria edit, never infer a Search from its label."""
        if (not self.requested_stay or self.pending_submission
                or outcome.get("status") not in {"action_performed", "value_verified", "counter_verified"}
                or not self.has_stay_form(observation)):
            return
        action = getattr(decision, "action", "click")
        value_edit = action in {"fill", "select", "check", "set_counter"}
        field = self.stay_form_control(facts) or any(
            item.get("control_id") == facts.get("id")
            and item.get("field") == "destination" for item in self.checks
        )
        date_choice = action == "click" and calendar_day(facts) is not None
        counter_change = action == "click" and facts.get("counter")
        widget_commit = action == "click" and any(re.fullmatch(
            r"update|apply|done|confirm|ok", normalized(facts.get(key) or "")) for key in ("label", "text")) and any(
            identity(item)["frame"] == identity(facts)["frame"]
            and self.stay_form_control(item)
            and (item.get("expanded") == "true" or item.get("counter") or age_control(item)
                 or item.get("date"))
            for item in controls(observation)
        )
        if not (value_edit and field or date_choice or counter_change or widget_commit):
            return
        if action in {"fill", "select"} and str(facts.get("value", "")) == str(getattr(decision, "value", "")):
            return
        if action == "set_counter" and str((facts.get("counter") or {}).get("value")) == str(getattr(decision, "value", "")):
            return
        previous = self.result_refresh
        if (widget_commit and previous
                and previous["document_id"] == observation.get("document_id", observation.get("url"))):
            # Auto-apply pages can refresh before Done/Update merely closes the
            # widget. Preserve the real edit baseline; final returned criteria
            # and rendered records are still checked before adoption.
            self.result_refresh = {**previous, "application_action": True}
            return
        self.result_refresh = {
            "document_id": observation.get("document_id", observation.get("url")),
            "before_results": {
                key: copy.deepcopy(observation.get("results", {}).get(key))
                for key in ("result_signature", "record_count", "no_results", "busy")
            },
            "busy_seen": False,
            "application_action": bool(widget_commit),
            "criteria_changed": bool(value_edit and field or date_choice or counter_change),
            "action": action,
            "control": {key: copy.deepcopy(facts[key]) for key in ("id", "label", "tag", "type", "role") if key in facts},
        }

    @staticmethod
    def result_render_changed(before, after):
        """Compare result structure/content only; ads and form text are irrelevant."""
        old, new = before.get("results") or {}, after.get("results") or {}
        old_signature, new_signature = old.get("result_signature"), new.get("result_signature")
        if (isinstance(old_signature, str) and isinstance(new_signature, str)
                and re.fullmatch(r"[0-9a-f]{8}", old_signature)
                and re.fullmatch(r"[0-9a-f]{8}", new_signature)
                and old_signature != new_signature):
            return True
        old_count, new_count = old.get("record_count", 0), new.get("record_count", 0)
        valid_counts = all(isinstance(value, int) and not isinstance(value, bool) for value in (old_count, new_count))
        return bool(valid_counts and old_count != new_count or old.get("no_results") is not True and new.get("no_results") is True)

    def committed_result_summary(self, observation, scope, inspection=None):
        """Read applied summaries beside records, without requiring action history."""
        if scope.get("status") != "verified":
            return None
        main = (observation.get("frames") or [{}])[0].get("controls", [])
        diagnostic = self.occupancy_recheck(observation, include_verified=True)
        counts = (diagnostic or {}).get("observed_counts") or {}
        witnesses = []
        for field in scope.get("fields", []):
            name, expected = field["field"], str(field["expected"])
            methods = {method.strip() for method in field.get("method", "").split(",")}
            evidence = None
            if name == "destination" and "returned_results_heading" in methods:
                headings = field.get("evidence_by_method", {}).get("returned_results_heading", [])
                if headings:
                    evidence = headings[0]["evidence"]
            elif "returned_url" in methods:
                evidence = field["evidence"]
            elif name in {"check_in", "check_out"}:
                dates = [control for control in main
                         if control.get("expanded") != "true" and (
                             control.get("date_kind") in {"opener", "date_opener"}
                             and control.get("date_endpoint") == name and control.get("date") == expected
                             or control.get("tag") == "INPUT" and control.get("type") == "date"
                             and control.get("readonly") is True and control.get("value") == expected
                             and re.search(r"check.?in|arrival" if name == "check_in" else r"check.?out|departure",
                                           " ".join(str(control.get(key) or "") for key in ("label", "name")), re.I)
                         )]
                if dates:
                    evidence = str(dates[0].get("label") or name) + " " + expected
            elif name in {"adults", "children", "rooms"}:
                if inspection and str(inspection["checked_counts"].get(name)) == expected:
                    evidence = inspection["readings"][name]["evidence"]
                elif counts.get(name) == [int(expected)]:
                    evidence = diagnostic["summary"]
            if evidence is None:
                return None
            witnesses.append({"field": name, "observed": field["observed"],
                              "status": "verified", "evidence": str(evidence)[:600]})
        return {"document_id": observation.get("document_id", observation.get("url")),
                "method": "committed_results_summary", "fields": witnesses} if witnesses else None

    def adopt_matching_results(self, observation, *, ages_confirmed=False, post_commit_inspection=None):
        """Accept applied stay results without inventing a witnessed Search click.

        Matching draft fields beside old cards are insufficient. Returned URL
        criteria, a witnessed refresh or committed result summaries establish
        the current page independently of whether the agent operated it.
        This path never releases an uncertain submission or verifies card prices.
        """
        if self.submission:
            return False
        self.result_handoff = {"ready": False, "reason": "checking",
                               "record_count": observation.get("results", {}).get("record_count", 0)}

        def blocked(reason, **details):
            self.result_handoff.update(reason=reason, **details)
            return False

        if (self.pending_submission or self.request_error
                or not {"destination", "check_in", "check_out"} <= self.requested_stay.keys()
                or self.collection_mode == "current_page"
                or any(frame.get("password_or_code_visible") for frame in observation.get("frames", []))):
            return blocked("response_pending" if self.pending_submission else "request_or_session_not_ready")
        results = observation.get("results") or {}
        count = results.get("record_count", 0)
        if (not isinstance(count, int) or isinstance(count, bool) or count < 0
                or results.get("no_results") is True and count > 0):
            return blocked("invalid_result_state")
        rendered = (isinstance(count, int) and not isinstance(count, bool) and count > 0) or results.get("no_results") is True
        if results.get("busy") or not rendered:
            return blocked("results_loading" if results.get("busy") else "no_record_markers")
        available = controls(observation)
        inspection = self.confirm_occupancy_inspection(
            observation, post_commit_inspection.get("closed_diagnostic")
        ) if isinstance(post_commit_inspection, dict) else None
        unresolved = self.required_form_fields(observation)
        if any(item.get("date_kind") == "day_choice" and item.get("date_widget_id") for item in available):
            return blocked("calendar_open")
        passive_queries = {
            item.get("id") for item in available
            if discovery_query_control(item) and not str(item.get("value", "")).strip()
            and normalized(item.get("label") or item.get("name") or "") in {"search", "query", "q"}
        }
        if any(item["control_id"] not in passive_queries for item in unresolved) or any(
            item.get("application") == "form" and item.get("field") not in STAY_FIELDS
            and item.get("status") != "verified" for item in self.checks
        ):
            return blocked("required_website_values", fields=[item["label"] for item in unresolved if item["control_id"] not in passive_queries][:6])
        opened = [item for item in available if self.stay_form_control(item) and item.get("expanded") == "true"
                  and (not inspection or item.get("id") != inspection["opener"]["control_id"])]
        if opened:
            return blocked("stay_widget_open", widget_control_ids=[item["id"] for item in opened][:4],
                           occupancy_status=[{"field": item["field"], "status": item["status"],
                                              "next_action": item.get("next_action")}
                                             for item in self.checks if item["field"] in {"adults", "children", "rooms"}],
                           widget_completion=occupancy_widget_action(observation, {
                               "requirements": self.checks, "unresolved_form_fields": unresolved}))
        if any(item.get("counter") for item in available) and any(
            item.get("enabled", True) is not False
            and item.get("tag") in {"BUTTON", "INPUT"}
            and any(re.fullmatch(r"update|apply|done|confirm|ok|close", normalized(item.get(key) or ""))
                    for key in ("label", "text"))
            for item in available
        ) and not inspection:
            return blocked("occupancy_widget_open")
        for item in available:
            if (item.get("enabled", True) is False or not age_control(item)
                    or item.get("tag") not in {"INPUT", "SELECT", "TEXTAREA"}
                    and item.get("role") not in {"combobox", "textbox", "spinbutton"}):
                continue
            value = str(item.get("value", ""))
            if not value.strip() or item.get("selection_placeholder") is True:
                return blocked("child_age_unconfirmed")
            allowed = self.allowed_age_values(item, observation)
            if not allowed:
                if not ages_confirmed:
                    return blocked("child_age_unconfirmed")
                continue
            option = next((option for option in item.get("options", [])
                           if str(option.get("value", "")) == value), {})
            label = normalized(option.get("label") or item.get("selected_label") or value)
            if not any(normalized(value) == age or re.fullmatch(
                rf"{re.escape(age)}\s*(?:years?(?:\s+old)?)?", label
            ) for age in allowed):
                return blocked("child_age_mismatch")
        scope = observed_result_scope(self.requested_stay, observation)
        if scope.get("status") != "verified":
            return blocked("returned_scope_unverified", scope_status=scope.get("status"),
                           unverified_fields=[item["field"] for item in scope["fields"] if item["status"] == "unverified"],
                           mismatched_fields=[item["field"] for item in scope["fields"] if item["status"] == "mismatch"],
                           contradictions=[item["code"] for item in scope.get("contradictions", [])][:6])
        document = observation.get("document_id", observation.get("url"))
        if not isinstance(document, str) or not document:
            return blocked("unbound_document")
        scope["document_id"] = document
        returned_url = all(
            "returned_url" in {method.strip() for method in item.get("method", "").split(",")}
            for item in scope["fields"] if item["field"] != "destination"
        )
        behavior = site_search_behavior(observation.get("url"), stay_request=bool(self.requested_stay))
        if behavior["search_mode"] == "explicit_submit":
            edited_here = bool(self.stay_edit_context
                               and self.stay_edit_context["document_id"] == document
                               and self.stay_edit_context["url"] == observation.get("url"))
            # Booking can show old cards beside edited form controls. A label,
            # Update or matching form summary is not its Search transition.
            # An already-applied result URL may still be reused on arrival, or
            # after a separately observed navigation into that actual result.
            if edited_here or not returned_url:
                return blocked("search_submit_required", site=behavior["site"],
                               search_mode=behavior["search_mode"], scope_status=scope["status"])
        refresh = self.result_refresh
        old_signature = (refresh or {}).get("before_results", {}).get("result_signature")
        new_signature = results.get("result_signature")
        signature_changed = bool(
            isinstance(old_signature, str) and isinstance(new_signature, str)
            and (re.fullmatch(r"[0-9a-f]{8}", old_signature)
                 or old_signature == "empty" and refresh["before_results"].get("no_results") is True)
            and (re.fullmatch(r"[0-9a-f]{8}", new_signature)
                 or new_signature == "empty" and results.get("no_results") is True)
            and old_signature != new_signature
        )
        refreshed = bool(
            refresh and refresh["document_id"] == document
            and (refresh["busy_seen"] or signature_changed
                 and (refresh["application_action"] or refresh.get("criteria_changed")))
        )
        summary = self.committed_result_summary(observation, scope, inspection)
        if not returned_url and not refreshed and not summary:
            return blocked("applied_state_unverified", scope_status=scope["status"])
        applied_method = "returned_url" if returned_url else "observed_result_refresh" if refreshed else "committed_results_summary"
        requirements = [{
            **copy.deepcopy(item), "application": "form", "model_interpreted": False,
        } for item in scope["fields"]]
        self.submission = {
            "kind": "observed_matching_results",
            "before_document_id": document,
            "source_url": observation.get("url"),
            "result_url": observation.get("url"),
            "result_document_id": document,
            "requirements": requirements,
            "submission_provenance": {
                "actor": "website", "action": None,
                "evidence_method": "post_commit_readback" if inspection else
                                   applied_method,
                **({"applied_evidence_method": applied_method,
                    "occupancy_inspection": copy.deepcopy(inspection)} if inspection else {}),
                **({"committed_summary": copy.deepcopy(summary)} if summary else {}),
                "criteria_action": copy.deepcopy(refresh) if refreshed else None,
            },
            "dispatch_status": "not_attempted",
            "result_state": "empty" if results.get("no_results") is True else "observed",
            "scope": "observed_matching_results_only",
            "result_scope": copy.deepcopy(scope),
        }
        self.result_scope = scope
        self.unresolved_form_fields = [item for item in unresolved if item["control_id"] not in passive_queries]
        self.result_refresh = None
        self.last_validation_rejection = None
        self.submission_candidates = []
        self.navigation_stage = self.discovery_context(observation)
        self.result_handoff.update(ready=True, reason="ready", scope_status="verified", evidence_method=applied_method)
        return True

    def remember_action(self, facts, outcome, decision=None, observation=None):
        observation = observation or {}
        # Idempotent for the live pre-action call; also supports direct fixture calls.
        self.before_action(facts, decision, observation)
        action = getattr(decision, "action", "click")
        day = calendar_day(facts) if action in {"click", "check"} else None
        calendar = outcome.get("calendar") or {}
        for field, pending in list(self.calendar_actions.items()):
            if day != pending["date"]:
                continue
            if calendar.get("dispatched") is False and calendar.get("status") != "already_selected":
                self.calendar_actions.pop(field, None)
            else:
                pending["status"] = calendar.get("status") or outcome.get("status", "unknown")
        self.remember_result_action(facts, outcome, decision, observation)
        if action == "click" and outcome.get("status") == "action_performed":
            requirement = self.requirements.get("destination")
            if requirement:
                binding = self.bindings.get("destination")
                fields = (
                    bound_controls(binding, observation)
                    if binding
                    else destination_controls(observation)[0]
                )
                matching = [
                    field
                    for field in fields
                    if field.get("tag") in {"INPUT", "TEXTAREA"}
                    and facts.get("id")
                    in {option.get("id") for option in self.destination_options(field, observation)}
                ]
                primary = normalized(facts.get("option_primary", ""))
                text = " ".join(str(facts.get(k, "")) for k in ("label", "text"))
                if (
                    len(matching) == 1
                    and primary == normalized(requirement["expected"])
                    and not re.search(r"\bsearch\s+(?:with\s+)?ai\b", text, re.I)
                    and (
                        not re.search(r"\bairport\b", text, re.I)
                        or re.search(r"\bairport\b", requirement["expected"], re.I)
                    )
                ):
                    self.destination_selections[self.destination_key(matching[0], observation)] = {
                        "required": True,
                        "selected": False,
                        "pending": True,
                        "value": requirement["expected"],
                        # A site can commit a fuller canonical destination label
                        # after selection. Preserve only this actually clicked,
                        # associated option; never infer qualifiers from a prefix.
                        "choice": {
                            key: str(facts.get(key, ""))
                            for key in ("option_primary", "label", "text")
                        },
                    }
        if action != "click" or outcome.get("status") != "action_performed":
            return
        calendar = outcome.get("calendar")
        if isinstance(calendar, dict) and calendar.get("status") not in {
            "selected", "already_selected"
        }:
            # A changed calendar is not necessarily a selected date. Keep the
            # year only after explicit selection read-back; this is still not
            # verification of the requested form summary or result availability.
            return
        text = " ".join(str(facts.get(k, "")) for k in ("date", "label", "text"))
        try:
            dates = requested_dates(text)
        except WebsiteError:
            return
        if len(dates) == 1:
            self.date_choices[dates[0]] = text[:400]

    def observe(self, observation):
        self.site_behavior = site_search_behavior(observation.get("url"), stay_request=bool(self.requested_stay))
        self.confirm_pending_submission(observation)
        document = observation.get("document_id", observation.get("url"))
        if self.result_refresh:
            if self.result_refresh["document_id"] != document:
                self.result_refresh = None
            elif (observation.get("results", {}).get("busy")
                  or observation.get("results", {}).get("busy_seen_during_wait") is True):
                self.result_refresh["busy_seen"] = True
        if self.document_id is not None and self.document_id != document:
            self.date_choices.clear()
            if any(item["page_id"] != calendar_page(observation) for item in self.calendar_actions.values()):
                self.calendar_actions.clear()
            self.destination_selections.clear()
            self.last_validation_rejection = None
            if self.submission and self.submission["result_document_id"] != document:
                self.submission = None
                self.result_scope = None
        self.document_id = document
        destination_fields = destination_controls(observation)[0] if "destination" in self.requirements else []
        destination_state = (document, tuple(sorted(
            str(item.get("value") or "").strip().casefold() for item in destination_fields
        ))) if destination_fields else None
        if destination_state is not None:
            if self.date_destination is not None and self.date_destination != destination_state:
                self.date_choices.clear()
            self.date_destination = destination_state
        # A click can close/rerender the calendar before its immediate executor
        # readback. A later fresh, explicitly selected full-year endpoint is
        # equally valid year evidence for the SAME document's short summary.
        # The summary must still independently show its requested month/day.
        selected_dates = {}
        for endpoint in observed_calendar_endpoints(observation):
            selected_dates.setdefault(endpoint["field"], []).append(endpoint)
        for field, endpoints in selected_dates.items():
            expected = (self.requirements.get(field) or {}).get("expected")
            if expected and {item["date"] for item in endpoints} == {expected}:
                self.date_choices[expected] = endpoints[0]["evidence"][:400]
            elif expected:
                self.date_choices.pop(expected, None)
        if not self.submission:
            results = observation.get("results") or {}
            self.result_scope = observed_result_scope(self.requested_stay, observation) if self.requested_stay and (
                results.get("record_count", 0) > 0 or results.get("no_results") is True
            ) else None
        self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        self.calendar_progress = self.observed_calendar_progress(observation)
        if self.calendar_resume_requested:
            picked = (self.calendar_progress or {}).get("picked_dates", {})
            verified = {item["field"] for item in self.checks if item["status"] == "verified"}
            self.calendar_actions = {field: item for field, item in self.calendar_actions.items()
                                     if field in picked or field in verified}
            self.calendar_resume_requested = False
        retained_search = self.collection_search
        if (
            self.collection_mode == "linked_details"
            and retained_search
            and retained_search["result_document_id"] != document
            and not any(
                check["application"] == "form" and check["status"] == "mismatch"
                for check in self.checks
            )
        ):
            saved = {item["field"]: item for item in retained_search["requirements"]}
            for index, check in enumerate(self.checks):
                previous = saved.get(check["field"])
                if (
                    check["application"] == "form"
                    and previous
                    and normalized(check["expected"]) == normalized(previous["expected"])
                ):
                    self.checks[index] = {
                        **copy.deepcopy(previous),
                        "method": "retained_search_context",
                        "evidence": "Verified on captured search results at "
                        + retained_search["result_url"]
                        + "; not a claim about this detail page's availability or price.",
                    }
        if (
            self.submission and not self.requested_stay
            and any(c["status"] == "mismatch" for c in self.checks)
        ):
            self.submission = None
            # Fresh result mismatches invalidate confirmed form proof. A
            # pending attempt must survive temporary/default loading fields.
            self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        self.visible_date_choices = []
        date_groups = {}
        pending_dates = {
            item["expected"]: item["field"]
            for item in self.checks
            if item["field"] in {"check_in", "check_out"} and item["status"] != "verified"
        }
        if self.calendar_progress:
            field = self.calendar_progress["next_field"]
            pending_dates = {(self.requirements[field])["expected"]: field} if field else {}
        for index, control in enumerate(controls(observation)):
            owner = control.get("date_owner_id")
            if control.get("enabled", True) is False:
                continue
            day = calendar_day(control)
            if day in pending_dates:
                if (control.get("selected") == "true"
                        and control.get("date_endpoint") == pending_dates[day]):
                    continue
                choice = {
                    "field": pending_dates[day],
                    "date": day,
                    "control_id": control.get("id"),
                    "label": control.get("label", ""),
                }
                # Only an observed gridcell ancestor proves these controls
                # belong to the same day. Do not merge equal dates in separate
                # widgets, frames, or older observations without ownership.
                key = (
                    (str(control.get("id", "")).partition(":")[0], owner, day)
                    if isinstance(owner, str) and owner else ("unowned", index)
                )
                priority = (
                    0 if control.get("tag") in {"BUTTON", "INPUT"}
                    else 1 if control.get("role") in {"button", "checkbox", "radio"} else 2
                )
                date_groups.setdefault(key, []).append((priority, index, choice))
        canonical = []
        for group in date_groups.values():
            best = min(item[0] for item in group)
            # Equally actionable choices remain ambiguous, never guessed.
            canonical.extend(item for item in group if item[0] == best)
        self.visible_date_choices = [item[2] for item in sorted(canonical, key=lambda item: item[1])]
        if self.submission and self.submission["result_document_id"] == document:
            results = observation.get("results", {})
            if results.get("busy"):
                self.submission["result_state"] = "loading"
            elif results.get("no_results"):
                self.submission["result_state"] = "empty"
            elif results.get("record_count", 0) > 0:
                self.submission["result_state"] = "observed"
            elif self.submission.get("kind") == "observed_matching_results":
                self.submission["result_state"] = "unobserved"
            self.result_scope = observed_result_scope(self.requested_stay, observation)
            if self.submission.get("kind") == "observed_matching_results":
                self.result_scope["document_id"] = document
            self.submission["result_scope"] = copy.deepcopy(self.result_scope)
            provenance = self.submission.get("submission_provenance") or {}
            inspection = self.confirm_occupancy_inspection(observation,
                provenance.get("occupancy_inspection", {}).get("closed_diagnostic"))
            summary_required = (provenance.get("applied_evidence_method") or provenance.get("evidence_method")) == "committed_results_summary"
            summary = self.committed_result_summary(observation, self.result_scope, inspection) if summary_required else None
            summary_invalid = summary_required and not summary
            if summary:
                provenance["committed_summary"] = summary
            if inspection:
                provenance["occupancy_inspection"] = inspection
            if (self.submission.get("kind") == "observed_matching_results"
                    and (self.result_scope.get("status") != "verified" or summary_invalid
                         or self.submission.get("submission_provenance", {}).get("evidence_method") == "post_commit_readback"
                         and not self.confirm_occupancy_inspection(observation,
                             self.submission["submission_provenance"].get("occupancy_inspection", {}).get("closed_diagnostic")))):
                # Adopted results have no pre-submit fallback. Fresh wrong or
                # missing stay evidence immediately withdraws their handoff.
                self.submission = None
                self.checks = [self.verify(item, observation) for item in self.requirements.values()]
            if self.prepare_catalog_followup(observation):
                # This is a different, observed catalog document, not a retry
                # of an uncertain dispatch. Discard old form bindings/year
                # proof and prepare its actual form once from fresh controls.
                self.bindings.clear()
                self.date_choices.clear()
                self.destination_selections.clear()
                self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        self.unresolved_form_fields = self.required_form_fields(observation)
        self.occupancy_recheck_context = self.occupancy_recheck(observation)
        self.submission_candidates = self.find_submission_candidates(observation)
        self.navigation_stage = self.discovery_context(observation)
        return self.snapshot()

    def prepare_catalog_followup(self, observation):
        submission = self.submission
        if not submission or self.catalog_followup_used or not self.requested_stay:
            return False
        scope = submission.get("result_scope") or {}
        document = observation.get("document_id", observation.get("url"))
        codes = {item.get("code") for item in scope.get("contradictions", [])}
        catalog = "catalog_starting_price" in codes and (
            bool(codes & {"price_context_occupancy_mismatch", "price_context_nights_mismatch"})
            or any(item.get("status") != "verified" for item in scope.get("fields", []))
        )
        native_search = any(
            item.get("tag") in {"BUTTON", "INPUT"}
            and item.get("form_scope")
            and (item.get("type") == "submit" or item.get("submits_form"))
            and item.get("enabled", True)
            and not widget_control(item)
            and re.search(r"^(?:search|find)\b", str(item.get("label", "")), re.I)
            for item in controls(observation)
        )
        if (
            not catalog or not native_search
            or document == submission.get("before_document_id")
            or observation.get("results", {}).get("busy")
        ):
            return False
        self.catalog_followup_used = True
        self.catalog_followup = {
            "status": "preparing_fresh_catalog_form",
            "document_id": document,
            "previous_result_scope": copy.deepcopy(scope),
            "note": "A different catalog page shows starting prices. One new search may run "
            "only after its own form is verified.",
        }
        self.submission = None
        return True

    def required_form_fields(self, observation, control=None):
        """Visible missing/invalid inputs belonging to the retrieval form.

        These are website requirements, not values invented from the request.
        Keep a separate checklist so a newly revealed field cannot disappear
        behind already-verified destination/date/occupancy counts.
        """
        available = controls(observation)
        # A results page's separate site-wide query is not a missing stay
        # parameter. Keep validation when that query is explicitly targeted.
        rendered = (observation.get("results", {}).get("record_count", 0) > 0
                    or observation.get("results", {}).get("no_results") is True)
        returned_destination = any(
            field.get("field") == "destination" and field.get("status") == "verified"
            and (rendered or "returned_results_heading" in field.get("method", ""))
            for field in observed_result_scope(self.requested_stay, observation).get("fields", [])
        ) if control is None and self.requested_stay else False
        result_stay_frames = {
            identity(item)["frame"] for item in available
            if self.stay_form_control(item) and identity(item)["frame"] == "0"
        } if returned_destination else set()
        stay_action_frames = {
            identity(item)["frame"] for item in available
            if self.stay_search_control(item, observation)
        } if self.requested_stay else set()
        targeted_stay_action = control is not None and self.stay_search_control(control, observation)
        destination_binding = self.bindings.get("destination")
        bound_destination_ids = {
            item.get("id") for item in bound_controls(destination_binding, observation)
        } if destination_binding else set()
        retrieval_scopes = {
            (identity(item)["frame"], item.get("form_scope") or "")
            for item in available
            if not widget_control(item)
            and item.get("enabled", True) is not False
            and (item.get("tag") in {"BUTTON", "INPUT"} or item.get("role") == "button")
            and re.search(
                r"^(?:search|find)\b|^(?:show|see|view)\s+(?:\d+\s+)?"
                r"(?:hotels|stays|results|availability)\b",
                str(item.get("label") or item.get("text") or "").strip(), re.I,
            )
        }
        if control is None and self.requested_stay:
            stay_scopes = {
                (identity(item)["frame"], item["form_scope"])
                for item in available if item.get("form_scope")
                and (identity(item)["frame"], item["form_scope"]) in retrieval_scopes
                and self.has_stay_form(observation, item)
            }
            if stay_scopes:
                # The global query is optional for a different, positively
                # identified stay form; its empty field cannot block that form.
                retrieval_scopes = stay_scopes
            else:
                # JavaScript stay widgets need not belong to an HTML form.
                # A separate one-field site query is still not their required
                # destination. Keep its validation when that exact submit is
                # targeted, but do not aggregate it into the stay checklist.
                unowned_stay_frames = {
                    identity(item)["frame"] for item in available
                    if not item.get("form_scope") and self.stay_form_control(item)
                }
                destination_binding = self.bindings.get("destination")
                bound_destination_ids = {
                    item.get("id")
                    for item in bound_controls(destination_binding, observation)
                } if destination_binding else set()
                separate_query_scopes = set()
                for frame, scope in retrieval_scopes:
                    if not scope or frame not in unowned_stay_frames:
                        continue
                    members = [item for item in available
                               if identity(item)["frame"] == frame
                               and item.get("form_scope") == scope]
                    fields = [item for item in members
                              if item.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
                              and item.get("type") not in {"hidden", "submit", "button", "image", "reset"}]
                    if len(fields) != 1 or not discovery_query_control(fields[0]):
                        continue
                    query = fields[0]
                    words = " ".join(str(query.get(key) or "") for key in ("label", "name"))
                    if (query.get("id") in bound_destination_ids and frame not in result_stay_frames
                            or re.search(r"destination|location|\bcity\b|where .*going", words, re.I)
                            or any(self.stay_form_control(item) for item in members)):
                        continue
                    separate_query_scopes.add((frame, scope))
                if separate_query_scopes:
                    retrieval_scopes -= separate_query_scopes
                retrieval_scopes.update((frame, "") for frame in unowned_stay_frames)
        scopes = {(identity(control)["frame"], control.get("form_scope") or "")} if control is not None else retrieval_scopes
        result = []
        for item in available:
            frame = identity(item)["frame"]
            if (not item.get("form_scope") and (item.get("id") not in bound_destination_ids
                                               or control is None and frame in result_stay_frames)
                    and discovery_query_control(item)
                    and normalized(item.get("label") or item.get("name") or "") in {"search", "query", "q"}
                    and (control is None and frame in stay_action_frames
                         or control is None and frame in result_stay_frames
                         or targeted_stay_action and frame == identity(control)["frame"])):
                # Only a positively associated stay action can isolate an
                # unowned global query before results exist. Targeting that
                # global Search itself still validates its required input.
                continue
            if (control is None and (self.submission or {}).get("kind") == "observed_matching_results"
                    and self.submission.get("result_document_id") == observation.get("document_id", observation.get("url"))
                    and (self.result_scope or {}).get("status") == "verified"
                    and discovery_query_control(item) and not str(item.get("value", "")).strip()
                    and normalized(item.get("label") or item.get("name") or "") in {"search", "query", "q"}):
                # Applied matching results do not require a new global query.
                # A targeted submit still validates that exact field normally.
                continue
            owned = (frame, item.get("form_scope") or "") in scopes
            # Portalled widgets can lack an HTML form owner. Adopt their
            # required inputs only when the observed frame has one search form.
            unowned_widget = (
                not item.get("form_scope")
                and item.get("widget_scope") in {"counter", "choice", "dialog"}
                and len({scope for owner, scope in retrieval_scopes if owner == frame}) == 1
                and bool(scopes & retrieval_scopes)
                and not discovery_query_control(item)
            )
            if (
                not (owned or unowned_widget)
                or item.get("enabled", True) is False
                or item.get("readonly") is True
                or not item.get("id")
                or item.get("tag") not in {"INPUT", "SELECT", "TEXTAREA"}
                and item.get("role") not in {"combobox", "textbox", "checkbox", "radio", "spinbutton"}
                or item.get("type") in {"hidden", "button", "submit", "image", "reset"}
            ):
                continue
            placeholder_label = str(item.get("selected_label") or "")
            visible_required = (
                item.get("selection_placeholder") is True
                and re.search(r"\b(?:required|needed)\b", placeholder_label, re.I)
                and not re.search(r"\b(?:optional|not|no|if)\b", placeholder_label, re.I)
            )
            # Some portals declare a requirement in the placeholder instead of
            # the HTML required attribute. Explicit wording is evidence; a
            # generic optional "Select..." prompt alone is not.
            required = item.get("required") is True or bool(visible_required)
            missing = item.get("value_missing") is True or item.get("selection_placeholder") is True
            if required and "value_missing" not in item and item.get("type") in {"checkbox", "radio"}:
                missing = missing or item.get("selected") != "true"
            elif required and "value_missing" not in item and not str(item.get("value", "")).strip():
                missing = True
            invalid = item.get("invalid") is True
            if not (invalid or required and missing):
                continue
            result.append({
                "control_id": item["id"],
                "label": str(item.get("label") or item.get("name") or "Required field")[:180],
                "form_scope": item.get("form_scope"),
                "required": required,
                "invalid": invalid,
                "value_missing": missing,
                "validation_message": str(item.get("validation_message") or "")[:240],
            })
            if len(result) >= 12:
                break
        return result

    def required_form_problem(self, observation, control=None):
        fields = self.required_form_fields(observation, control)
        if not fields:
            return None
        names = ", ".join(dict.fromkeys(item["label"] for item in fields[:4]))
        return (
            "The website still requires: " + names + ". Complete these fields before Search. "
            "Use values from the request; if a value was not provided, enter it in the website "
            "and press Resume. No missing value should be guessed."
        )

    def reject_pending_submission(self, after, outcome):
        """Release only an explicitly prevented, same-form submit preflight.

        A timeout, unchanged page or an invalid field observed after a click is
        not proof of rejection and must retain the unknown-response guard.
        """
        pending = self.pending_submission
        validation = outcome.get("validation") if isinstance(outcome, dict) else None
        if (
            not pending or not isinstance(validation, dict)
            or outcome.get("status") != "validation_blocked"
            or outcome.get("submitted") is not False
            or outcome.get("dispatch_status") != "not_dispatched"
        ):
            return False
        before = pending["before"]
        provenance = pending.get("submission_provenance", {})
        submit = provenance.get("control", {})
        scope = submit.get("form_scope")
        fields = validation.get("fields")
        if (
            before.get("document_id", before.get("url")) != after.get("document_id", after.get("url"))
            or not isinstance(scope, str) or not scope
            or validation.get("form_scope") != scope
            or not isinstance(fields, list) or not fields
        ):
            return False
        unresolved = self.required_form_fields(after, submit)
        reported = [item for item in fields[:12] if isinstance(item, dict)]
        if not any(
            item.get("control_id") == current["control_id"]
            or item.get("label") and normalized(item["label"]) == normalized(current["label"])
            for item in reported for current in unresolved
        ):
            return False
        self.last_validation_rejection = {
            "dispatch_status": "not_dispatched",
            "status": "validation_blocked",
            "form_scope": scope,
            "fields": copy.deepcopy(unresolved),
            "submission_provenance": copy.deepcopy(provenance),
        }
        self.pending_submission = None
        self.unresolved_form_fields = unresolved
        return True

    def find_submission_candidates(self, observation):
        """Find retrieval submits whose actual form independently holds every value.

        No page link or inferred selector is a substitute for a native submit.
        Reuse the current ledger's selected-option/full-date evidence, but only
        the fresh controls associated with the candidate's actual DOM form.
        """
        if (
            self.collection_mode == "model_decides"
            or self.request_error
            or not self.checks
            or self.pending()
            or self.pending_submission
            or self.submission
            or (self.collection_mode == "linked_details" and self.collection_search)
            or any(frame.get("password_or_code_visible") for frame in observation.get("frames", []))
        ):
            return []
        requirements = [
            item for item in self.requirements.values() if item["application"] == "form"
        ]
        counter_ids = {
            item.get("control_id")
            for check in self.checks
            for item in check.get("counter_controls", [])
            if item.get("control_id")
        }
        result = []
        owned_options = {
            control_id
            for item in controls(observation)
            for control_id in item.get("option_ids", [])
        }
        for control in controls(observation):
            scope = control.get("form_scope")
            label = str(control.get("label") or control.get("text") or control.get("value") or "")
            if (
                control.get("tag") not in {"BUTTON", "INPUT"}
                or widget_control(control)
                or control.get("id") in owned_options
                or control.get("counter")
                or control.get("date")
                or not (control.get("type") == "submit" or control.get("submits_form"))
                or control.get("enabled", True) is False
                or not isinstance(scope, str)
                or not scope
                or not control.get("id")
                or not re.search(
                    r"^(?:search|find)\b|^(?:show|see|view)\s+(?:\d+\s+)?"
                    r"(?:hotels|stays|results|availability)\b",
                    label.strip(),
                    re.I,
                )
                or re.search(
                    r"\b(?:pay|payment|reserve|reservation|book|subscribe|subscription|buy|purchase)\b",
                    label,
                    re.I,
                )
            ):
                continue
            if self.required_form_fields(observation, control):
                continue
            frame_id = identity(control)["frame"]
            associated = [
                item
                for item in controls(observation)
                if identity(item)["frame"] == frame_id
                and item.get("form_scope") in {None, "", scope}
            ]
            if any(item.get("id") in counter_ids for item in associated) and any(
                item.get("enabled", True)
                and (item.get("tag") in {"BUTTON", "INPUT"} or item.get("role") == "button")
                and re.fullmatch(r"done|apply|update|confirm|ok|close", str(item.get("label", "")), re.I)
                for item in associated
            ):
                # Some popovers omit aria-expanded. A visible confirmation for
                # the requested live counter rows still precedes Search. Rows
                # with a different actual form owner are not adopted here.
                continue
            scoped = {
                "url": observation.get("url"),
                "document_id": observation.get("document_id", observation.get("url")),
                "frames": [
                    {
                        "text": "",
                        "controls": [
                            item
                            for item in frame.get("controls", [])
                            if item.get("form_scope") == scope
                            and identity(item)["frame"] == frame_id
                        ],
                    }
                    for frame in observation.get("frames", [])
                ],
            }
            if any(item.get("expanded") == "true" for item in controls(scoped)):
                continue
            if all(self.verify(item, scoped)["status"] == "verified" for item in requirements):
                result.append(
                    {"control_id": control["id"], "label": label[:240], "form_scope": scope}
                )
        return result

    def selected_calendar_dates(self, observation, field):
        return [(item["date"], item["evidence"]) for item in observed_calendar_endpoints(observation)
                if item["field"] == field]

    def verify(self, requirement, observation):
        name, expected = requirement["name"], requirement["expected"]
        base = {
            "field": name,
            "expected": expected,
            "application": requirement["application"],
            "status": "pending",
            "observed": None,
            "evidence": "",
            "method": "visible_form",
            "model_interpreted": requirement.get("model_interpreted", False),
            "interpretation": requirement.get("interpretation", ""),
        }
        if requirement["application"] == "extraction":
            return {**base, "status": "deferred_to_extraction"}
        live_counts = name in {"adults", "children", "rooms"} and any(
            occupancy_component((control.get("counter") or {}).get("label", "")) == name
            or control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
            and not age_control(control)
            and occupancy_component(" ".join(str(control.get(key) or "") for key in ("label", "name"))) == name
            for control in controls(observation)
        )
        if (name in STAY_FIELDS and not live_counts
                and (observation.get("results", {}).get("record_count", 0) > 0
                     or observation.get("results", {}).get("no_results") is True)):
            fresh = observed_result_scope(self.requested_stay, observation)
            field = next((field for field in fresh.get("fields", [])
                          if field["field"] == name and field["status"] == "verified"), None)
            if field:
                return {**base, **field, "method": "visible_returned_field"}
        binding = self.bindings.get(name)
        bound = bound_controls(binding, observation) if binding else []
        missing_occupancy = (
            binding
            and not bound
            and name in {"adults", "children", "rooms"}
            and binding["document"] == observation.get("document_id", observation.get("url"))
        )
        if binding and len(bound) != 1:
            if not missing_occupancy and self.submission and self.submission["result_document_id"] == observation.get(
                "document_id", observation.get("url")
            ):
                saved = next(
                    (c for c in self.submission["requirements"] if c["field"] == name), None
                )
                if saved:
                    return {**saved, "method": "observed_result_scope"
                            if self.submission.get("kind") == "observed_matching_results"
                            else "verified_pre_submit_form"}
            if not missing_occupancy:
                return {
                    **base,
                    "evidence": "Bound control is absent or ambiguous; rebind from "
                    "the fresh page. A previous value is not verification on this document.",
                }
        if name == "destination":
            fields, ambiguous = (bound, False) if binding else destination_controls(observation)
            if ambiguous:
                return {
                    **base,
                    "evidence": "Multiple generic textboxes are visible; "
                    "destination is unconfirmed.",
                }
            if len(fields) > 1:
                values = {
                    normalized(field["value"])
                    for field in fields
                    if field.get("value") not in {None, ""}
                }
                return {
                    **base,
                    "status": "mismatch" if values - {normalized(expected)} else "pending",
                    "observed": "; ".join(sorted(values)) if values else None,
                    "evidence": "Multiple destination fields are visible; rebind "
                    "the intended input from the fresh page.",
                }
            if fields:
                return self.verify_destination(base, fields[0], observation)
        if len(bound) == 1 and name not in {"adults", "rooms", "children"}:
            control = bound[0]
            seen = control.get("value", "")
            if control.get("counter"):
                seen = str(control["counter"]["value"])
            if control.get("type") in {"checkbox", "radio"} or control.get("role") in {
                "checkbox",
                "radio",
            }:
                seen = control.get("selected", "")
            if control.get("tag") == "SELECT":
                choice = next((o for o in control.get("options", []) if o["value"] == seen), None)
                if choice and normalized(choice["label"]) == normalized(expected):
                    seen = choice["label"]
            if not seen and control.get("selected") == "true":
                seen = control.get("label", "")
            if not seen and normalized(control.get("text", "")) == normalized(expected):
                seen = control["text"]
            if seen != "":
                return {
                    **base,
                    "status": "verified"
                    if normalized(seen) == normalized(expected)
                    else "mismatch",
                    "observed": str(seen),
                    "evidence": (control.get("label", "") + " " + str(seen))[:600],
                    "method": "bound_control_readback",
                    "control_id": control.get("id"),
                }
        candidates = self.selected_calendar_dates(observation, name) if name in {"check_in", "check_out"} else []
        counter_candidates = []
        counter_options = []
        total_guest_candidates = []
        native_occupancy_controls = []
        bound_occupancy = bound[0] if len(bound) == 1 and name in {"adults", "rooms", "children"} else None
        if (bound_occupancy and not bound_occupancy.get("counter")
                and bound_occupancy.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
                and str(bound_occupancy.get("value", "")).isdigit()):
            candidates.append((str(bound_occupancy["value"]),
                               str(bound_occupancy.get("label", "")) + " " + str(bound_occupancy["value"])))
            native_occupancy_controls.append(bound_occupancy)
        # Destination inputs were handled above; absence uses the common saved
        # pre-submit fallback below, never arbitrary unrelated input values.
        relevant_controls = [] if name == "destination" else controls(observation)
        if missing_occupancy:
            relevant_controls = [
                control
                for control in relevant_controls
                if identity(control)["frame"] == binding["identity"]["frame"]
            ]
        for control in relevant_controls:
            label = " ".join(str(control.get(k, "")) for k in ("label", "name"))
            text = " ".join(str(control.get(k, "")) for k in ("label", "text", "value"))
            value = control.get("value", "")
            if control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}:
                text = label + " " + str(value)
            if name in {"adults", "rooms", "children"}:
                if age_control(control):
                    continue
                counter = control.get("counter")
                if counter and occupancy_component(counter["label"]) == name:
                    counter_candidates.append((str(counter["value"]), counter["evidence"]))
                    counter_options.append(
                        {
                            "control_id": control.get("id"),
                            "direction": counter["direction"],
                            "enabled": control.get("enabled", True),
                        }
                    )
                seen = occupancy_summary_values(text) if not counter else {}
                candidates.extend((str(count), text) for count in seen.get(name, []))
                if (control.get("expanded") in {"true", "false"}
                        or control.get("haspopup") not in {None, "", "false"}
                        or control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
                        and re.search(r"\bguests?\b|\btravell?ers?\b", label, re.I)):
                    total_guest_candidates.extend((count, text) for count in seen.get("guests", []))
                if occupancy_component(label) == name and str(value).isdigit():
                    candidates.append((str(value), text))
                    if control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}:
                        native_occupancy_controls.append(control)
            elif name in {"check_in", "check_out"}:
                if calendar_day(control):
                    # Individual calendar choices are not the committed form
                    # summary. Explicit selections were handled as a range.
                    continue
                date_hint = re.search(
                    r"check.?in|check.?out|arrival|departure|\bdates?\b|calendar", label, re.I
                )
                endpoint = control.get("date_endpoint")
                if endpoint and endpoint != name or not date_hint and endpoint != name:
                    continue
                # Unselected calendar choices are NOT read-back evidence.
                specific = r"check.?in|arrival" if name == "check_in" else r"check.?out|departure"
                combined = bool(
                    re.search(r"dates|calendar", label, re.I)
                    or (
                        re.search(r"check.?in|arrival", label, re.I)
                        and re.search(r"check.?out|departure", label, re.I)
                    )
                )
                if not combined and not re.search(specific, label, re.I) and endpoint != name:
                    continue
                try:
                    dates = requested_dates(text)
                except WebsiteError:
                    dates = []
                if dates:
                    position = 0 if name == "check_in" else -1
                    candidates.append((dates[position], text))
                elif expected in self.date_choices and self.month_day_visible(expected, text):
                    candidates.append(
                        (expected, text + " | Selected full date: " + self.date_choices[expected])
                    )
            else:
                words = set(re.findall(r"[a-z]+", name.casefold()))
                hints = set(re.findall(r"[a-z]+", label.casefold()))
                field_match = bool(words & hints)
                if field_match and value:
                    candidates.append((str(value), text))
        expected_total = None
        if name in {"adults", "children"}:
            quantities = [self.requirements.get(field, {}) for field in ("adults", "children")]
            if all(item.get("application") == "form" and str(item.get("expected", "")).isdigit() for item in quantities):
                expected_total = sum(int(item["expected"]) for item in quantities)
        total_conflict = expected_total is not None and any(count != expected_total for count, _ in total_guest_candidates)
        if counter_candidates:
            counter_values = {normalized(value) for value, _ in counter_candidates}
            summary_values = {normalized(value) for value, _ in candidates}
            counter_match = counter_values == {normalized(expected)}
            summary_conflict = bool(summary_values - {normalized(expected)}) or total_conflict
            return {
                **base,
                "status": "verified" if counter_match and not summary_conflict else "pending",
                "observed": "; ".join(sorted(counter_values)),
                "evidence": counter_candidates[0][1][:600],
                "method": "visible_counter",
                "counter_controls": counter_options,
                "next_action": "confirm_or_close_widget" if counter_match else "set_counter",
                "summary_confirmation_pending": counter_match and summary_conflict,
                "total_guest_conflict": total_conflict,
            }
        values = {normalized(value) for value, _ in candidates}
        matched = candidates and values == {normalized(expected)}
        native_values = {normalized(control.get("value", "")) for control in native_occupancy_controls}
        native_widget_open = any(
            opener.get("expanded") == "true"
            and (opener.get("tag") == "BUTTON" or opener.get("role") == "button")
            and re.search(r"\badults?\b|\bchildren\b|\bchild\b|\bkids?\b|\brooms?\b|\bguests?\b|\btravell?ers?\b",
                          str(opener.get("label") or opener.get("text") or ""), re.I)
            and any(identity(control)["frame"] == identity(opener)["frame"]
                    and not (control.get("form_scope") and opener.get("form_scope")
                             and control["form_scope"] != opener["form_scope"])
                    for control in native_occupancy_controls)
            for opener in relevant_controls
        )
        if (native_widget_open and native_values == {normalized(expected)}
                and (values - {normalized(expected)} or total_conflict)):
            return {
                **base, "observed": str(expected),
                "evidence": str(native_occupancy_controls[0].get("label", "")) + " " + str(expected),
                "next_action": "confirm_or_close_widget", "summary_confirmation_pending": True,
                "total_guest_conflict": total_conflict,
            }
        if total_conflict:
            return {
                **base, "observed": "; ".join(sorted(values)) if values else None,
                "evidence": total_guest_candidates[0][1][:600],
                "total_guest_conflict": True,
                "next_action": "read_independent_occupancy_rows",
            }
        if matched:
            return {
                **base,
                "status": "verified",
                "observed": expected,
                "evidence": candidates[0][1][:600],
                **({"method": "bound_control_readback", "control_id": bound_occupancy.get("id")}
                   if bound_occupancy and not bound_occupancy.get("counter") else {}),
            }
        if candidates:
            return {
                **base,
                "status": "mismatch",
                "observed": "; ".join(sorted(values)),
                "evidence": "; ".join(dict.fromkeys(text for _, text in candidates))[:600],
            }
        if self.submission and self.submission["result_document_id"] == observation.get(
            "document_id", observation.get("url")
        ):
            saved = next((c for c in self.submission["requirements"] if c["field"] == name), None)
            if saved:
                return {**saved, "method": "observed_result_scope"
                        if self.submission.get("kind") == "observed_matching_results"
                        else "verified_pre_submit_form"}
        return base

    def verify_destination(self, base, field, observation):
        if field.get("tag") not in {"INPUT", "TEXTAREA", "SELECT"}:
            return {**base, "evidence": "Bind destination to its input, not a suggestion."}
        if "value" not in field or field["value"] is None:
            return {
                **base,
                "evidence": "Destination input is present; its current value is unavailable.",
                "method": "destination_value_unavailable",
                "control_id": field.get("id"),
            }
        seen = str(field["value"])
        if field.get("tag") == "SELECT":
            choice = next((o for o in field.get("options", []) if o["value"] == seen), None)
            if choice:
                seen = choice["label"]
        matched = normalized(seen) == normalized(base["expected"])
        evidence = (field.get("label", "") + " " + seen)[:600]
        options = self.destination_options(field, observation)
        required = field.get("tag") != "SELECT" and (
            field.get("selection_required", False) or bool(options)
        )
        key = self.destination_key(field, observation)
        selection = self.destination_selections.setdefault(
            key, {"required": required, "selected": False, "pending": False, "value": seen}
        )
        selection["required"] |= required
        choice = selection.get("choice", {})
        choice_matched = bool(
            (selection["pending"] or selection["selected"])
            and destination_tokens(seen)
            and any(
                destination_tokens(seen) == destination_tokens(choice.get(part, ""))
                for part in ("option_primary", "label", "text")
            )
        )
        matched |= choice_matched
        if not matched or (
            normalized(selection["value"]) != normalized(seen) and not choice_matched
        ):
            selection.update(selected=False, pending=False, value=seen)
            selection.pop("choice", None)
        opened = field.get("expanded") == "true" or bool(options)
        value_action = "fill"
        if field.get("enabled", True) is False:
            value_action = "inspect"
        elif field.get("tag") == "SELECT":
            value_action = "select"
        elif field.get("readonly"):
            value_action = "open_suggestions" if required or field.get("haspopup") else "inspect"
        if selection["pending"] and matched and not opened:
            selection.update(selected=True, pending=False, value=seen)
        elif opened and not selection["pending"]:
            selection["selected"] = False
            selection.pop("choice", None)
        if selection["required"] and not selection["selected"]:
            if (
                not opened
                and self.submission
                and self.submission["result_document_id"]
                == observation.get("document_id", observation.get("url"))
            ):
                saved = next(
                    (
                        check
                        for check in self.submission["requirements"]
                        if check["field"] == "destination" and check["status"] == "verified"
                    ),
                    None,
                )
                if saved and (
                    matched
                    or (
                        destination_tokens(seen)
                        and destination_tokens(seen) == destination_tokens(saved.get("observed"))
                    )
                ):
                    return {**saved, "method": "observed_result_scope"
                            if self.submission.get("kind") == "observed_matching_results"
                            else "verified_pre_submit_form"}
            if not matched:
                next_action = value_action
                note = (
                    "Destination input is empty; enter the requested destination before choosing."
                    if not seen
                    else "Current destination text does not match the requested value; replace it."
                )
            elif field.get("suggestions_pending") or selection["pending"]:
                next_action = "wait_suggestions"
                note = "Wait for the destination suggestions/selected value to finish updating."
            elif options:
                next_action = "select_option"
                note = "Matching typed text needs one fresh, associated destination choice."
            elif opened:
                next_action = "wait_suggestions"
                note = (
                    "Matching text is entered; suggestions are open but no owned choice is visible."
                )
            else:
                next_action = "open_suggestions"
                note = (
                    "Matching text is entered; open its suggestions to commit a destination choice."
                )
            return {
                **base,
                "status": "pending" if matched or not seen else "mismatch",
                "observed": seen,
                "evidence": evidence + " | " + note,
                "method": "autocomplete_selection_pending"
                if matched
                else "destination_fill_pending",
                "selection_pending": True,
                "next_action": next_action,
                "control_id": field.get("id"),
                "selection_options": [
                    {
                        "control_id": option.get("id"),
                        "primary": option.get("option_primary", ""),
                        "label": option.get("label", ""),
                        "text": option.get("text", ""),
                    }
                    for option in options[:12]
                    if next_action == "select_option"
                ],
            }
        return {
            **base,
            "status": "verified" if matched else "mismatch" if seen else "pending",
            "observed": seen,
            "evidence": evidence
            + (
                " | Destination input is empty; enter the requested destination."
                if not seen
                else ""
            ),
            "method": "autocomplete_selection_readback"
            if selection["required"]
            else "visible_form",
            "control_id": field.get("id"),
            **({"next_action": value_action} if not matched else {}),
        }

    @staticmethod
    def month_day_visible(expected, text):
        day = date.fromisoformat(expected)
        month = rf"(?:{day.strftime('%B')}|{day.strftime('%b')})"
        number = rf"0?{day.day}(?:st|nd|rd|th)?"
        return bool(re.search(rf"\b(?:{month}\s+{number}|{number}\s+{month})\b", text, re.I))

    @staticmethod
    def stay_form_control(item):
        """Recognize one observed stay control without borrowing its siblings."""
        if item.get("enabled", True) is False or item.get("tag") == "A" or item.get("role") == "tab":
            return False
        label = " ".join(str(item.get(key) or "") for key in ("label", "name"))
        return bool(
            item.get("date") or item.get("type") == "date" or age_control(item)
            or item.get("counter") and occupancy_components(item["counter"].get("label", ""))
            or re.search(r"check.?in|check.?out|\bselect dates\b|\barrival\b|\bdeparture\b", label, re.I)
            or re.search(r"\badults?\b|\bchildren\b|\bguests?\b|\brooms?\b|\btravelers?\b", label, re.I)
            and (
                item.get("tag") in {"INPUT", "SELECT"} or item.get("role") == "spinbutton"
                or (item.get("tag") == "BUTTON" or item.get("role") == "button")
                and (item.get("expanded") in {"true", "false"}
                     or item.get("haspopup") not in {None, "", "false"}
                     or bool(occupancy_summary_values(label)))
            )
        )

    def has_stay_form(self, observation, control=None):
        """Use actual date/occupancy controls, not seeded request requirements."""
        for item in controls(observation):
            if control is not None:
                if identity(item)["frame"] != identity(control)["frame"]:
                    continue
                scope = control.get("form_scope")
                if scope and item.get("form_scope") != scope and not (
                    not item.get("form_scope") and item.get("widget_scope") in {"counter", "choice", "dialog"}
                ):
                    continue
            if self.stay_form_control(item):
                return True
        return False

    def stay_search_control(self, control, observation):
        """Classify this action from observed ownership or explicit stay words."""
        if (search_opener(control) or widget_control(control)
                or control.get("enabled", True) is False):
            return False
        label = normalized(control.get("label") or control.get("text") or "")
        if not (
            (control.get("tag") == "BUTTON" or control.get("role") == "button"
             or control.get("tag") == "INPUT" and control.get("type") in {"submit", "image"})
            and re.search(r"^(?:search|find)\b|^(?:show|see|view)\s+(?:\d+\s+)?(?:hotels|stays|results|availability)\b", label)
        ):
            return False
        if control.get("form_scope"):
            return any(
                item.get("form_scope") == control["form_scope"]
                and identity(item)["frame"] == identity(control)["frame"]
                and self.stay_form_control(item) for item in controls(observation)
            )
        return bool(
            re.search(
                r"^(?:search|find)\s+(?:for\s+)?(?:hotels?|stays?|availability)\b"
                r"|^(?:show|see|view)\s+(?:\d+\s+)?(?:hotels|stays|results|availability)\b", label,
            )
            and self.has_stay_form(observation, control)
        )

    def discovery_context(self, observation):
        category = requested_listing_category(self.instructions)
        if not category:
            return None
        available = controls(observation)
        stay_form = self.has_stay_form(observation)
        categories = [item["id"] for item in available if item.get("id") and listing_category_control(item, category)][:6]
        queries = [item["id"] for item in available if item.get("id") and discovery_query_control(item)][:3]
        locations = [item["id"] for item in available if item.get("id")
                     and self.location_discovery_control(item)][:6]
        phase = "await_response" if self.pending_submission else "collect_results" if self.submission else (
            "prepare_stay" if stay_form else "discover_category" if categories else "discover_location"
        )
        return {
            "phase": phase, "category": category, "stay_form_visible": stay_form,
            "control_ids": categories if phase == "discover_category" else
                list(dict.fromkeys(locations + queries))[:6] if phase == "discover_location" else [],
            "category_control_ids": categories, "query_control_ids": queries,
            "hint": "Open the requested listing category before individual results; location discovery is not the completed stay search."
            if phase in {"discover_category", "discover_location"} else
            "Use the actual stay form and newly required fields before its final search; returned listings need their own source evidence.",
        }

    def discovery_navigation(self, decision, facts, observation):
        """Distinguish requested location/category navigation from a stay submit."""
        if (requested_listing_category(self.instructions) and not self.pending_submission
                and not self.submission and decision.action == "click" and search_opener(facts)
                and any(item.get("id") == facts.get("id") and identity(item) == identity(facts)
                        for item in controls(observation))):
            return True
        scope = self.result_scope or {}
        if (not self.pending_submission and not self.submission and decision.action == "click"
                and self.location_discovery_control(facts)
                and any(field["field"] == "destination" and field["status"] == "mismatch"
                        and "returned_results_heading" in field.get("method", "")
                        for field in scope.get("fields", []))
                and any(item.get("id") == facts.get("id") and identity(item) == identity(facts)
                        for item in controls(observation))):
            # A requested city link can leave the previous city's hotel page.
            # Its old date widgets do not make that link a completed stay search.
            return True
        if (not requested_listing_category(self.instructions) or self.pending_submission or self.submission
                or decision.action not in {"click", "press"} or not facts.get("id")
                or facts.get("enabled", True) is False or self.has_stay_form(observation, facts)):
            return False
        available = controls(observation)
        if not any(item.get("id") == facts["id"] and identity(item) == identity(facts) for item in available):
            return False
        query_ids = {item.get("id") for item in available if discovery_query_control(item)}
        if any(item["control_id"] not in query_ids for item in self.required_form_fields(observation, facts)):
            return False  # A real dependent value still requires user input.
        if self.discovery_search(decision, facts, observation):
            return True
        if decision.action != "click":
            return False
        if listing_category_control(facts, "hotels") or discovery_query_control(facts):
            return True
        if self.location_discovery_control(facts):
            return True
        label = normalized(facts.get("label") or facts.get("text") or "")
        return bool(
            re.fullmatch(r"(?:open\s+)?search", label) and not facts.get("submits_form")
            and facts.get("type") not in {"submit", "image"} and not facts.get("form_scope")
            and (facts.get("haspopup") not in {None, "", "false"} or facts.get("expanded") in {"true", "false"})
        )

    def location_discovery_control(self, facts):
        """Keep request-matching destination results, not individual hotels."""
        if facts.get("enabled", True) is False or facts.get("role") in {
            "checkbox", "radio", "gridcell", "spinbutton"
        } or age_control(facts):
            return False
        label = normalized(facts.get("label") or facts.get("text") or "")
        expected = normalized((self.requirements.get("destination") or {}).get("expected", ""))
        requested = bool(expected and re.search(rf"(?<!\w){re.escape(expected)}(?!\w)", label))
        if requested and (facts.get("tag") in {"A", "BUTTON"} or facts.get("role") == "button") and re.search(r"^(?:see|show|view)\s+(?:all\s+)?results\b", label):
            return True
        if requested and navigation_choice(facts):
            primary = normalized(facts.get("option_primary", ""))
            return bool(primary == expected or re.match(rf"^destination\s+{re.escape(expected)}(?:\b|,)", label)
                        or len(label) <= 180 and re.match(rf"^{re.escape(expected)}(?:\b|,)", label)
                        and not re.search(r"\bhotel\b|\breviews?\b|\bbubbles\b|\bstars?\b", label))
        return False

    def is_submit(self, decision, facts, observation=None):
        if decision.action not in {"click", "press"}:
            return False
        if search_opener(facts):
            return False
        if observation is not None and self.discovery_navigation(decision, facts, observation):
            return False
        if not any(
            item["application"] == "form" for item in self.requirements.values()
        ) and self.collection_mode not in {"search_results", "linked_details"}:
            return False
        label = normalized(" ".join(str(facts.get(k, "")) for k in ("label", "text")))
        if decision.action == "click" and not re.search(r"\bsearch with ai\b", label):
            scoped_options = {
                option["control_id"]
                for check in self.checks
                if check["field"] == "destination"
                for option in check.get("selection_options", [])
            }
            if facts.get("id") in scoped_options:
                # Native buttons default to type=submit even inside listboxes.
                # A fresh field-associated choice is selection, not Search.
                return False
        if widget_control(facts):
            # Actual widget semantics always override the model's purpose. A
            # Done/calendar/choice click cannot create a pending Search response.
            return False
        if decision.action == "press":
            if decision.value != "Enter" or facts.get("tag") not in {"INPUT", "TEXTAREA"}:
                return False
            if facts.get("selection_required") and (
                facts.get("expanded") == "true" or facts.get("option_ids")
            ):
                return False
            return bool(facts.get("form_scope") or facts.get("submits_form"))
        # Do not rely on the model's purpose or an exact accessible label.
        # Native submits and decorated search actions are still submissions.
        if facts.get("tag") in {"BUTTON", "INPUT"} and (
            facts.get("submits_form") or facts.get("type") in {"submit", "image"}
        ):
            return True
        return (
            decision.action == "click"
            and (facts.get("tag") == "BUTTON" or facts.get("role") == "button")
            and bool(
                re.search(
                    r"^(?:search|find)\b|^(?:show|see|view)\s+(?:\d+\s+)?"
                    r"(?:hotels|stays|results|availability)\b",
                    label,
                )
            )
        )

    def discovery_search(self, decision, facts, observation):
        """A positively identified query-only search is navigation, not a stay quote.

        Hotel dates and occupancy may exist only after a location/category search.
        Native form ownership isolates forms when present. A JavaScript search
        without a native form needs exactly one grounded query in its frame and
        no date/occupancy controls; model purpose alone never grants an exemption.
        """
        scope = facts.get("form_scope")
        if not self.requested_stay or not self.is_submit(decision, facts) or self.has_stay_form(observation, facts):
            return False
        same_form = [item for item in controls(observation)
                     if item.get("form_scope") == scope
                     and identity(item)["frame"] == identity(facts)["frame"]]
        if not any(item.get("id") == facts.get("id") for item in same_form):
            return False
        fields = [item for item in same_form
                  if item.get("tag") in {"INPUT", "TEXTAREA", "SELECT"}
                  and item.get("type") not in {"hidden", "submit", "button", "image", "reset"}]
        if len(fields) != 1:
            return False
        query = fields[0]
        words = " ".join(str(query.get(key) or "") for key in ("label", "name"))
        if (
            query.get("tag") not in {"INPUT", "TEXTAREA"}
            or query.get("type", "text") not in {"", "text", "search", "textarea"}
            or not (query.get("type") == "search" or re.search(r"\b(?:search|query)\b|^q$", words, re.I))
            or age_control(query)
            or not str(query.get("value") or "").strip()
        ):
            return False
        query_value = normalized(query["value"])
        if not re.search(rf"(?<!\w){re.escape(query_value)}(?!\w)", normalized(self.instructions)) and not any(
            check.get("field") == "destination" and check.get("status") == "verified"
            and check.get("control_id") == query.get("id") for check in self.checks
        ):
            return False
        # A single text input can still share its form with date/guest openers.
        # Those observed controls identify a stay search, even while closed.
        return not any(
            item.get("counter") or item.get("date")
            or re.search(r"check.?in|check.?out|\bdates?\b|\bcalendar\b|\badults?\b|\bchildren\b|\bguests?\b|\brooms?\b",
                         " ".join(str(item.get(key) or "") for key in ("label", "name")), re.I)
            for item in same_form
        )

    def pending(self):
        return [
            c["field"]
            for c in self.checks
            if c["application"] == "form" and c["status"] != "verified"
        ]

    def begin_submission(
        self, before, source_url, *, control=None, action=None, decision_origin=None
    ):
        """Record dispatch intent before interacting; this is not proof of a click."""
        if self.pending_submission or self.submission:
            return False
        if self.required_form_fields(before, control):
            return False
        required = {r["name"] for r in self.requirements.values() if r["application"] == "form"}
        checked = {c["field"] for c in self.checks if c["status"] == "verified"}
        if not required <= checked:
            return False
        self.last_validation_rejection = None
        self.pending_submission = {
            "dispatch_status": "attempted",
            "before": copy.deepcopy(before),
            "source_url": source_url,
            "requirements": copy.deepcopy(self.checks),
            "submission_provenance": {
                "actor": "agent" if control is not None and action is not None else "unspecified",
                "action": action,
                "decision_origin": decision_origin,
                "control": {
                    key: copy.deepcopy(control[key])
                    for key in ("id", "label", "tag", "type", "role", "form_scope")
                    if control is not None and key in control
                },
            },
        }
        return True

    def submitted(
        self, before, after, source_url, *, control=None, action=None, decision_origin=None
    ):
        """Compatibility path for callers that already have both observations."""
        if not self.pending_submission and not self.begin_submission(
            before,
            source_url,
            control=control,
            action=action,
            decision_origin=decision_origin,
        ):
            return False
        return self.confirm_pending_submission(after)

    def confirm_pending_submission(self, after):
        if not self.pending_submission:
            return False
        if self.pending_submission.get("dispatch_status") == "not_dispatched":
            return False
        results = after.get("results")
        if isinstance(results, dict):
            count = results.get("record_count", 0)
            has_records = isinstance(count, int) and not isinstance(count, bool) and count > 0
            needs_results = self.collection_mode in {"listing_results", "search_results"} or (
                self.collection_mode == "linked_details"
                and any(item["application"] == "form" for item in self.requirements.values())
            )
            if results.get("busy") or needs_results and not (
                has_records or results.get("no_results") is True
            ):
                if results.get("busy"):
                    self.pending_submission["result_busy_seen"] = True
                # A loading redirect is not the result document. Keep the
                # attempt until rendered records or an explicit empty result.
                return False
        before = self.pending_submission["before"]
        # A click is insufficient. Require a changed document URL or visible main
        # content, then bind the pre-submit evidence to that resulting page only.
        before_text = before.get("frames", [{}])[0].get("text", "")
        after_text = after.get("frames", [{}])[0].get("text", "")
        changed = before.get("document_id", before.get("url")) != after.get(
            "document_id", after.get("url")
        ) or bool(
            after_text
            and SequenceMatcher(None, before_text[:4500], after_text[:4500]).ratio() < 0.8
        )
        if not changed and self.requested_stay:
            # A SPA can refresh only its result cards below unchanged chrome.
            # A recorded submit plus matching returned scope and an actual
            # render change/busy cycle proves this response without a URL move.
            scope = observed_result_scope(self.requested_stay, after)
            changed = scope.get("status") == "verified" and bool(
                self.pending_submission.get("result_busy_seen")
                or self.result_render_changed(before, after)
            )
        if changed:
            self.submission = {
                "before_document_id": before.get("document_id", before.get("url")),
                "source_url": self.pending_submission["source_url"],
                "result_url": after.get("url"),
                "result_document_id": after.get("document_id", after.get("url")),
                "requirements": self.pending_submission["requirements"],
                "submission_provenance": self.pending_submission["submission_provenance"],
                "dispatch_status": self.pending_submission.get("dispatch_status", "attempted"),
                "result_state": "empty"
                if after.get("results", {}).get("no_results")
                and not after.get("results", {}).get("busy")
                else "observed",
                "scope": "form_values_and_submission_only",
                "result_scope": observed_result_scope(self.requested_stay, after),
            }
            self.result_scope = copy.deepcopy(self.submission["result_scope"])
            self.pending_submission = None
        return changed

    def snapshot(self):
        result_context = self.submission or self.collection_search or {}
        matching_results = result_context.get("kind") == "observed_matching_results"
        search_confirmed = bool(result_context) and not matching_results
        result_scope = self.result_scope
        if not self.submission and self.collection_mode == "linked_details" and self.collection_search:
            result_scope = self.collection_search.get("result_scope")
        return {
            "navigation_stage": copy.deepcopy(self.navigation_stage),
            "requirements": copy.deepcopy(self.checks),
            "pending_fields": self.pending(),
            "unresolved_form_fields": copy.deepcopy(self.unresolved_form_fields),
            "validation_rejection": copy.deepcopy(self.last_validation_rejection),
            "result_handoff": copy.deepcopy(self.result_handoff),
            "search_submitted": search_confirmed,
            "matching_results_observed": matching_results,
            "search_response_pending": bool(
                self.pending_submission
                and self.pending_submission.get("dispatch_status") != "not_dispatched"
            ),
            "request_error": self.request_error,
            "date_resolution": copy.deepcopy(self.date_resolution),
            "visible_date_choices": copy.deepcopy(self.visible_date_choices),
            "calendar_progress": copy.deepcopy(self.calendar_progress),
            "site_behavior": copy.deepcopy(self.site_behavior),
            "collection_mode": self.collection_mode,
            "collection_goal": copy.deepcopy(self.collection_goal),
            "collection_scope": copy.deepcopy(self.collection_scope),
            "collection_progress": self.collection_progress(),
            "information_needs": [
                {
                    **copy.deepcopy(need),
                    "status": "captured" if self.information_evidence.get(field)
                    else need["status"],
                    "source_evidence": copy.deepcopy(self.information_evidence.get(field, [])),
                }
                for field, need in self.information_needs.items()
            ],
            "information_coverage": self.information_coverage(),
            "submission_candidates": copy.deepcopy(self.submission_candidates),
            "information_need_feedback": copy.deepcopy(self.information_need_feedback),
            "result_scope": copy.deepcopy(result_scope),
            "catalog_followup": copy.deepcopy(self.catalog_followup),
            "occupancy_recheck": copy.deepcopy(self.occupancy_recheck_context),
            "search_transition": {
                "attempted": bool(
                    self.pending_submission or search_confirmed
                    or self.last_validation_rejection
                ),
                "confirmed": search_confirmed,
                "attempt_status": "matching_results_observed" if matching_results
                else "transition_confirmed"
                if search_confirmed
                else "attempted_unconfirmed"
                if self.pending_submission
                else "validation_blocked"
                if self.last_validation_rejection
                else "not_attempted",
                "dispatch_status": (
                    self.submission or self.pending_submission or self.collection_search
                    or self.last_validation_rejection or {}
                ).get("dispatch_status", "not_attempted"),
                "result_document_id": (self.submission or self.collection_search)[
                    "result_document_id"
                ]
                if self.submission or self.collection_search
                else None,
                "scope": result_context.get("scope", "form_values_and_submission_only"),
                "result_state": result_context.get("result_state"),
                "retained_for_linked_details": bool(
                    self.collection_mode == "linked_details" and not self.submission
                    and self.collection_search
                ),
                "submission_provenance": copy.deepcopy(
                    (
                        self.submission or self.pending_submission or self.collection_search
                        or self.last_validation_rejection or {}
                    ).get("submission_provenance", {})
                ),
            },
            "note": "Form read-back/submission is not independent proof of listing "
            "availability, price basis or coverage.",
        }

    def completion_problem(self):
        if self.pending_submission:
            if self.pending_submission.get("dispatch_status") == "not_dispatched":
                return (
                    "Search was not dispatched. Review the stale/disabled control "
                    "or start a fresh session; no automatic retry."
                )
            return (
                "Search was attempted but its dispatch/response is not confirmed yet. Wait and "
                "inspect the results, or pause; do not submit again or finish."
            )
        if self.unresolved_form_fields and not self.submission:
            names = ", ".join(dict.fromkeys(item["label"] for item in self.unresolved_form_fields[:4]))
            return (
                "The website still requires: " + names + ". Complete the missing website "
                "fields and press Resume. No missing value should be guessed."
            )
        if self.pending() and not (
            self.source_preview_ready()
            or self.submission and (self.result_scope or {}).get("status") == "verified"
        ):
            return (
                "Requested form values are still unconfirmed: "
                + ", ".join(self.pending())
                + ". Continue setting and reading back the controls, or pause. Do not finish."
            )
        if (
            any(r["application"] == "form" for r in self.requirements.values())
            and not self.submission
            and not (self.collection_mode == "linked_details" and self.collection_search)
        ):
            return (
                "Requested form values must be verified and Search must produce an "
                "observed page change before finishing. A city catalog is not a "
                "completed stay search."
            )
        return None

    def source_preview_ready(self):
        """Completed navigation can yield sources without requested-stay proof."""
        return bool(
            self.submission and self.requested_stay
            and (self.submission.get("result_scope") or {}).get("status") != "verified"
            and not self.pending_submission
        )

    def capture_context(self, observation):
        if self.completion_problem() or not self.submission:
            return None
        if self.submission["result_document_id"] != observation.get(
            "document_id", observation.get("url")
        ):
            return None
        return {
            "status": "observed_matching_results"
            if self.submission.get("kind") == "observed_matching_results"
            else "form_verified_search_submitted",
            **copy.deepcopy(self.submission),
            "requirements": copy.deepcopy(self.submission["requirements"])
            if self.submission.get("kind") == "observed_matching_results"
            else copy.deepcopy(self.checks),
            "availability_verified": False,
            "record_values_verified": False,
            "date_resolution": copy.deepcopy(self.date_resolution),
            "result_scope": copy.deepcopy(self.result_scope),
            "requested_stay_verified": (self.result_scope or {}).get("status") == "verified",
            "source_preview_only": self.source_preview_ready(),
        }
