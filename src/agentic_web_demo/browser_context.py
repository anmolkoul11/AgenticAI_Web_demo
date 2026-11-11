"""Small, self-contained model context, separate from complete browser evidence.

Only navigation requests are projected here. Live tool references, source capture,
the user's instructions and the saved action report are never edited in place.
"""

import copy
import hashlib
import json
import re

from agentic_web_demo.browser_task import discovery_query_control, occupancy_widget_action

NAVIGATION_CONTEXT_CHARS = 14000
OBSERVATION_CONTEXT_CHARS = 8000
FOCUSED_CONTEXT_CHARS = 6500
FOCUSED_OBSERVATION_CHARS = 3500
_FORM_HINTS = re.compile(
    r"\b(?:destination|search|check.?in|check.?out|arrival|departure|dates?|calendar|"
    r"next month|previous month|adults?|children|rooms?|guests?|travel[el]ers?|"
    r"done|apply|update|confirm|close|dismiss|filters?|currency|price|rating|sort|load more|next page)\b",
    re.I,
)
_QUERY_FILLER = set(
    "a an and all about as at be by collect content current data details detail extract find "
    "for from get give in include is it links list me of on open or page pages please records "
    "related relevant that the their them these this to website with articles headlines".split()
)


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _short(value, limit):
    return str(value)[:limit]


def _nonempty(value):
    return value not in (None, "", [], {})


def _terms(value):
    words = {word.casefold() for word in re.findall(r"[\w-]{3,}", str(value))}
    return words | {word[:-1] for word in words if len(word) > 4 and word.endswith("s")}


def _requirements(checklist):
    keys = (
        "field",
        "expected",
        "application",
        "status",
        "observed",
        "control_id",
        "next_action",
        "selection_pending",
        "summary_confirmation_pending",
    )
    result = []
    for item in checklist.get("requirements", []):
        kept = {key: copy.deepcopy(item[key]) for key in keys if _nonempty(item.get(key))}
        if "observed" in item:
            kept["observed"] = copy.deepcopy(item["observed"])
        # A request-derived value is not shortened. It is needed for exact actions.
        if item.get("model_interpreted"):
            kept["model_interpreted"] = True
            kept["interpretation"] = _short(item.get("interpretation", ""), 140)
        if item.get("status") != "verified" and item.get("evidence"):
            kept["reason"] = _short(item["evidence"], 140)
        result.append(kept)
    return result


def _affordance(item):
    tag, role = item.get("tag"), item.get("role")
    if item.get("enabled") is False:
        return [], "Disabled."
    if item.get("readonly"):
        return ["click"], "Read-only: no fill; widget click only."
    if tag == "SELECT":
        return ["select"], "Native select: exact enabled option."
    if role == "option":
        return ["click"], "Custom option: click, not select."
    if tag == "A" and item.get("href"):
        return ["click"], "Navigation link, not prepared form submit."
    if item.get("counter"):
        return ["set_counter"], "Set absolute count."
    if item.get("date_kind") in {"opener", "date_opener"}:
        return ["click"], "Date field opener: inspect its calendar without reselecting verified dates."
    if item.get("date") or role == "gridcell":
        return ["click"], "Calendar choice: click."
    if tag == "INPUT" and item.get("type") in {"checkbox", "radio"}:
        return ["check", "click"], "Check true/false."
    if role in {"checkbox", "radio"}:
        return ["click"], "Custom choice: click, then read state."
    if (
        tag == "TEXTAREA"
        or item.get("editable")
        or tag == "INPUT"
        and item.get("type", "text")
        not in {
            "button",
            "submit",
            "image",
            "reset",
            "range",
            "color",
            "file",
        }
    ):
        return ["fill", "press", "click"], (
            "Fill directly; then click owned option. No focus click."
            if item.get("selection_required")
            else "Fill directly; no focus click."
        )
    return ["click"], ""


def _submission_controls(observation, checklist):
    items = [item for frame in observation.get("frames", []) for item in frame.get("controls", [])]
    declared = checklist.get("submission_candidates")
    ids = {item.get("control_id") for item in declared or []}
    scopes = {
        item.get("form_scope")
        for item in items
        if item.get("form_scope")
        and item.get("id") in {req.get("control_id") for req in checklist.get("requirements", [])}
    }
    return [
        item
        for item in items
        if item.get("enabled", True)
        and item.get("tag") in {"BUTTON", "INPUT"}
        and item.get("role") != "option"
        and not (item.get("counter") or item.get("date"))
        and (
            item.get("id") in ids
            if declared is not None
            else (item.get("submits_form") or item.get("type") == "submit")
            and re.fullmatch(
                r"search|find|show results|show availability", str(item.get("label", "")), re.I
            )
            and (not scopes or item.get("form_scope") in scopes)
        )
    ]


def _navigation_stage(observation, checklist):
    """Project the ledger's current discovery targets, never stale page handles."""
    stage = checklist.get("navigation_stage") or {}
    if stage.get("phase") not in {
        "discover_category", "discover_location", "prepare_stay", "collect_results", "await_response"
    }:
        return {}
    available = {
        item.get("id") for frame in observation.get("frames", [])
        for item in frame.get("controls", []) if item.get("enabled", True)
    }
    return {
        "phase": stage["phase"],
        "category": _short(stage.get("category", ""), 40),
        "stay_form_visible": bool(stage.get("stay_form_visible")),
        **{
            key: list(dict.fromkeys(cid for cid in stage.get(key, []) if cid in available))[:limit]
            for key, limit in (("control_ids", 6), ("category_control_ids", 6), ("query_control_ids", 3))
        },
        "hint": _short(stage.get("hint", ""), 220),
    }


def observed_matching_results_ready(checklist, *, empty=False, document_id=None):
    """Accept the ledger's independently observed results without inventing Search."""
    scope = checklist.get("result_scope") or {}
    transition = checklist.get("search_transition") or {}
    provenance = transition.get("submission_provenance") or {}
    inspection = provenance.get("occupancy_inspection") or {}
    requested_counts = {field for field in ("adults", "children", "rooms")
                        if field in (scope.get("requested") or {})}
    fields = scope.get("fields") or []
    document = transition.get("result_document_id")
    summary = provenance.get("committed_summary") or {}
    summary_fields = {field.get("field"): field for field in summary.get("fields", [])}
    summary_verified = bool(
        summary.get("method") == "committed_results_summary" and summary.get("document_id") == document
        and fields and set(summary_fields) == {field.get("field") for field in fields}
        and all(summary_fields[field["field"]].get("status") == "verified"
                and str(summary_fields[field["field"]].get("observed")) == str(field.get("observed"))
                for field in fields)
    )
    form = [item for item in checklist.get("requirements", []) if item.get("application") == "form"]
    retained_details = bool(
        checklist.get("collection_mode") == "linked_details"
        and transition.get("retained_for_linked_details") is True
        and form and all(
            item.get("status") == "verified" and item.get("method") == "retained_search_context"
            for item in form
        )
    )
    return bool(
        checklist.get("matching_results_observed") is True
        and checklist.get("search_submitted") is False
        and checklist.get("search_response_pending") is False
        and not checklist.get("unresolved_form_fields")
        and not checklist.get("request_error")
        and scope.get("status") == "verified"
        and scope.get("source") == "returned_page"
        and not scope.get("contradictions")
        and fields and all(item.get("status") == "verified" for item in fields)
        and document and scope.get("document_id") == document
        and (document_id is None or document_id == document or retained_details)
        and transition.get("scope") == "observed_matching_results_only"
        and transition.get("attempted") is False
        and transition.get("confirmed") is False
        and transition.get("attempt_status") == "matching_results_observed"
        and transition.get("dispatch_status") == "not_attempted"
        and transition.get("result_state") in ({"empty"} if empty else {"observed", "empty"})
        and provenance.get("actor") == "website"
        and provenance.get("action") is None
        and (
            provenance.get("evidence_method") in {"returned_url", "observed_result_refresh"}
            or provenance.get("evidence_method") == "committed_results_summary" and summary_verified
            or provenance.get("evidence_method") == "post_commit_readback"
            and (provenance.get("applied_evidence_method") in {"returned_url", "observed_result_refresh"}
                 or provenance.get("applied_evidence_method") == "committed_results_summary" and summary_verified)
            and inspection.get("method") == "post_commit_readback"
            and inspection.get("document_id") == document
            and requested_counts
            and set(inspection.get("checked_counts") or {}) == requested_counts
            and all(
                isinstance(inspection.get("checked_counts", {}).get(field), int)
                and not isinstance(inspection["checked_counts"][field], bool)
                and inspection["checked_counts"][field] >= 0
                and str(inspection.get("checked_counts", {}).get(field)) == str(scope.get("requested", {}).get(field))
                and (inspection.get("readings", {}).get(field) or {}).get("status") == "verified"
                and str(inspection["readings"][field].get("value")) == str(scope.get("requested", {}).get(field))
                for field in requested_counts
            )
        )
    )


def calendar_navigation(observation, checklist):
    """Choose one observed month arrow, then require a fresh calendar window."""
    pending = [item for item in checklist.get("requirements", [])
               if item.get("field") in {"check_in", "check_out"} and item.get("status") != "verified"]
    next_field = (checklist.get("calendar_progress") or {}).get("next_field")
    if next_field == "check_out":
        pending = [item for item in checklist.get("requirements", []) if item.get("field") == next_field]
    if not pending or (checklist.get("calendar_progress") or {}).get("status") == "awaiting_commit":
        return None
    field = next((item for item in pending if item["field"] == "check_in"), pending[0])
    target = str(field.get("expected") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target):
        return None
    available = [item for frame in observation.get("frames", []) for item in frame.get("controls", [])]
    days = [item for item in available if item.get("date_kind") == "day_choice"
            and item.get("date_widget_id") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item.get("date") or ""))]
    owners = {(str(item.get("id")).partition(":")[0], item["date_widget_id"]) for item in days}
    if len(owners) != 1 or len({item["date"] for item in days}) < 7:
        return None
    months = {}
    for item in days:
        months.setdefault(item["date"][:7], set()).add(item["date"])
    # Adjacent-month spillover cells are not another displayed month panel.
    panels = [month for month, values in months.items() if len(values) >= 15]
    if not panels:
        return None
    first, last = min(panels), max(panels)
    direction = "next" if target[:7] > last else "previous" if target[:7] < first else None
    if not direction:
        return None  # Never skip an in-window disabled/unavailable requested date.
    frame, widget = next(iter(owners))
    arrows = [item for item in available if item.get("date_navigation") == direction
              and item.get("date_widget_id") == widget and item.get("enabled", True)
              and str(item.get("id")).partition(":")[0] == frame]
    if len(arrows) != 1:
        return None
    return {"phase": "navigate_calendar", "fields": [field["field"]],
            "control_ids": [arrows[0]["id"]], "visible_months": [first, last],
            "next_action": {"action": "click", "control_id": arrows[0]["id"], "value": ""},
            "hint": f"Requested {target}; visible calendar months {first} through {last}. "
                    f"Click the observed {direction}-month arrow once, then observe the new dates."}


def calendar_completion(observation, checklist):
    dates = {item.get("field"): item for item in checklist.get("requirements", [])
             if item.get("field") in {"check_in", "check_out"}}
    progress = checklist.get("calendar_progress") or {}
    draft_ready = (progress.get("status") == "awaiting_commit"
                   and progress.get("document_id") == observation.get("document_id", observation.get("url")))
    if set(dates) != {"check_in", "check_out"} or (
        not draft_ready and any(item.get("status") != "verified" for item in dates.values())
    ):
        return None
    items = [item for frame in observation.get("frames", []) for item in frame.get("controls", [])]
    widgets = {(str(item.get("id")).partition(":")[0], item["date_widget_id"])
               for item in items if item.get("date_kind") == "day_choice" and item.get("date_widget_id")}
    if len(widgets) != 1:
        # Roleless/two-pane pickers may expose zero or multiple day scopes.
        # Do not combine their selection proof or click an unowned Apply. A
        # uniquely expanded date opener can still close its OWN form popup.
        openers = [item for item in items if item.get("date_kind") == "opener"
                   and item.get("expanded") == "true" and item.get("enabled", True)]
        if len(openers) != 1 or any(item.get("status") != "verified" for item in dates.values()):
            return None
        opener = openers[0]
        frame = str(opener.get("id")).partition(":")[0]
        scope = opener.get("form_scope")
        days = [item for item in items if item.get("date_kind") == "day_choice"]
        if not scope or not days or any(
            item.get("form_scope") != scope or str(item.get("id")).partition(":")[0] != frame
            for item in days
        ):
            return None
        action = {"action": "click", "control_id": opener["id"], "value": ""}
        return {"phase": "confirm_calendar", "fields": ["check_in", "check_out"],
                "control_ids": [opener["id"]], "widget_id": "opener:" + opener["id"], "frame": frame,
                "close_actions": [action], "next_action": action,
                "evidence_control_ids": [days[0]["id"]],
                "hint": "Both form dates are verified. Toggle the unique expanded date opener once, "
                        "then inspect its closed summary; do not merge unrelated calendar scopes."}
    frame, widget = next(iter(widgets))
    if draft_ready and (progress.get("widget_id") != widget or progress.get("frame") != frame):
        return None
    by_id = {item.get("id"): item for item in items}
    for field in checklist.get("unresolved_form_fields", []):
        control = by_id.get(field.get("control_id"), {})
        if (str(control.get("label") or control.get("name") or "").strip().casefold() not in {"search", "query", "q"}
                or control.get("date_widget_id") == widget):
            return None
    available = [item for item in items if item.get("enabled", True)
                 and str(item.get("id")).partition(":")[0] == frame]
    confirms = [item["id"] for item in available if item.get("date_widget_id") == widget
                and not item.get("submits_form")
                and (item.get("tag") == "BUTTON" or item.get("role") == "button")
                and re.fullmatch(r"done|apply|update|close|confirm|ok", str(item.get("label") or ""), re.I)]
    openers = [item["id"] for item in available if item.get("date_kind") == "opener"]
    fallback = [item["id"] for item in available if item.get("date_widget_id") == widget
                and item.get("date_kind") != "opener"
                and (item.get("tag") == "BUTTON" or item.get("role") == "button")]
    expanded_openers = [item["id"] for item in available if item.get("date_kind") == "opener"
                        and item.get("expanded") == "true"
                        and (not item.get("date_widget_id") or item.get("date_widget_id") == widget)]
    # Some sites ignore Escape on the form opener. An explicitly expanded,
    # unique opener is a reversible toggle; do not click a closed/unknown one.
    toggles = expanded_openers if len(expanded_openers) == 1 else []
    targets = confirms or toggles or fallback or openers
    if not targets:
        return None
    witnesses = [item["id"] for item in items if item.get("date_kind") == "day_choice"
                 and item.get("date_widget_id") == widget and str(item.get("id")).partition(":")[0] == frame]
    actions = []
    if len(confirms) == 1:
        actions.append({"action": "click", "control_id": confirms[0], "value": ""})
    if not confirms or len(confirms) == 1:
        actions.extend({"action": "click", "control_id": cid, "value": ""} for cid in toggles)
        actions.append({"action": "press", "control_id": (toggles or fallback or openers or targets)[0], "value": "Escape"})
    action = actions[0] if actions else None
    return {"phase": "confirm_calendar", "fields": ["check_in", "check_out"], "control_ids": targets[:3],
            "widget_id": widget, "frame": frame, "close_actions": actions,
            "evidence_control_ids": list(dict.fromkeys(progress.get("control_ids", []) + witnesses[:1])),
            **({"next_action": action} if action else {}),
            "hint": ("The requested days are selected in the draft calendar; the committed form still needs readback. "
                     if draft_ready else "Both requested dates are already verified in the open calendar. ")
            + ("Use its observed Done/Apply/Close control once. " if confirms else
               "Toggle the uniquely expanded date opener once. " if toggles else
               "Press Escape on one listed calendar control once to dismiss it without changing a day. ")
            + "Do not reselect dates or open global Search; then inspect the stay summary and results."}


def _interaction_focus(observation, checklist):
    items = {
        item.get("id"): item
        for frame in observation.get("frames", [])
        for item in frame.get("controls", [])
    }
    requirements = checklist.get("requirements", [])
    navigation = _navigation_stage(observation, checklist)
    discovering = navigation.get("phase") in {"discover_category", "discover_location"} and not navigation.get("stay_form_visible")
    base = "Guidance only: do not refill verified fields or reopen an expanded widget. "
    scope_fields = (checklist.get("result_scope") or {}).get("fields", [])
    location_has_results = observation.get("results", {}).get("record_count", 0) > 0 and any(
        field.get("field") == "destination" and field.get("status") == "verified"
        and "returned_results_heading" in field.get("method", "") for field in scope_fields
    )
    if location_has_results:
        base += "Hotel cards for the requested location are already here. Use its date/guest controls; do not reopen or refill the separate site Search. "
    if checklist.get("collection_scope", {}).get("allowed_modes") == ["current_page"]:
        return {
            "phase": "collect_starting_page",
            "fields": [],
            "control_ids": [],
            "hint": "Capture/finish the supplied page. Extraction will select relevant records; "
            "no section, search or detail navigation was requested.",
        }
    if checklist.get("search_response_pending"):
        return {
            "phase": "awaiting_results",
            "fields": [],
            "control_ids": [],
            "hint": "Search submitted: wait/inspect the response. Do not submit/navigate again.",
        }
    if observed_matching_results_ready(
        checklist, document_id=observation.get("document_id", observation.get("url"))
    ):
        retained = checklist["search_transition"]["result_document_id"] != observation.get(
            "document_id", observation.get("url")
        )
        return {
            "phase": "collect_results",
            "fields": [],
            "control_ids": [],
            "hint": (
                "The captured results independently verified the requested stay criteria. "
                "This detail page's availability and prices still need source evidence; "
                if retained else
                "The website already displays results with independently verified requested stay criteria; "
            )
            + (
                "continue collecting requested linked pages. "
                if checklist.get("collection_mode") == "linked_details"
                else "collect the requested results/sources. "
            )
            + "Do not refill the form or submit Search again. No Search click was recorded.",
        }
    completed_calendar = calendar_completion(observation, checklist)
    if completed_calendar:
        return completed_calendar
    guest_completion = occupancy_widget_action(observation, checklist)
    if guest_completion:
        return {
            "phase": "confirm_widget",
            "fields": [item["field"] for item in requirements
                       if item.get("field") in {"adults", "children", "rooms"}],
            "control_ids": [guest_completion["control_id"]],
            "next_action": guest_completion,
            "hint": "Guest values match. " + (
                "Use the observed confirmation button once. " if guest_completion["action"] == "click"
                else "Press Escape on the expanded guest opener without editing any count. "
            ) + "Then read the closed summary and updated listings below. Do not use site Search.",
        }
    unresolved = checklist.get("unresolved_form_fields") or []
    open_stay_widget = (checklist.get("result_handoff") or {}).get("reason") in {
        "stay_widget_open", "occupancy_widget_open"
    }
    if open_stay_widget:
        unresolved = [item for item in unresolved
                      if not (discovery_query_control(items.get(item.get("control_id"), {}))
                              and str(item.get("label") or "").strip().casefold() in {"search", "query", "q"})]
    if discovering:
        # An empty generic site query must not prevent opening the requested
        # category. Actual required dependent fields (including child ages)
        # remain ahead of discovery; only ledger-identified query fields yield.
        queries = set(navigation.get("query_control_ids", []))
        unresolved = [item for item in unresolved if item.get("control_id") not in queries]
    if unresolved:
        return {
            "phase": "complete_required_fields",
            "fields": [item.get("label", "Required field") for item in unresolved[:12]],
            "control_ids": [item["control_id"] for item in unresolved[:12]
                            if item.get("control_id") in items],
            "hint": "The website revealed required or invalid fields. Complete them from the "
            "request before closing the widget or Search. If a needed value is absent, "
            "pause and ask the user to enter it in the website, then Resume. Never guess.",
        }
    form = [item for item in requirements if item.get("application") == "form"]
    ready = bool(form) and all(item.get("status") == "verified" for item in form)
    if (
        checklist.get("search_submitted")
        and (
            not checklist.get("pending_fields") and (not form or ready)
            or (checklist.get("result_scope") or {}).get("status") in {"unverified", "mismatch"}
        )
    ):
        if (checklist.get("result_scope") or {}).get("status") in {"unverified", "mismatch"}:
            return {
                "phase": "collect_source_preview",
                "fields": [], "control_ids": [],
                "hint": "Search changed the page, but its returned stay scope is unverified. "
                "Capture source evidence for a read-only preview; do not claim requested "
                "dates/occupancy or matching nightly prices from pre-search form proof.",
            }
        return {
            "phase": "collect_results",
            "fields": [],
            "control_ids": [],
            "hint": "Search response is confirmed; "
            + (
                "continue collecting requested linked pages. "
                if checklist.get("collection_mode") == "linked_details"
                else "collect the requested results/sources. "
            )
            + "Do not refill the form or replace it with a catalogue link.",
        }
    for requirement in requirements:
        field = items.get(requirement.get("control_id"), {})
        if requirement.get("status") == "verified" or not field:
            continue
        options = [option for option in field.get("option_ids", []) if option in items]
        action = requirement.get("next_action")
        if field.get("suggestions_pending") or action == "wait_suggestions":
            return {
                "phase": "wait_suggestions",
                "fields": [requirement["field"]],
                "control_ids": [field["id"]],
                "hint": base
                + "Suggestions are still updating; wait/inspect, not select an old row.",
            }
        if (
            requirement.get("status") != "verified"
            and requirement.get("next_action") == "select_option"
            and options
        ):
            return {
                "phase": "choose_option",
                "fields": [requirement["field"]],
                "control_ids": options[:6],
                "hint": base + "Choose the matching owned suggestion before switching widgets.",
            }
    month_navigation = calendar_navigation(observation, checklist)
    if month_navigation:
        return month_navigation
    dates = [
        item
        for item in checklist.get("visible_date_choices", [])
        if item.get("control_id") in items
    ]
    if dates:
        dates.sort(key=lambda item: item.get("field") != "check_in")
        first = dates[0]["field"]
        return {
            "phase": "set_dates",
            "fields": [first],
            "control_ids": [item["control_id"] for item in dates if item["field"] == first],
            "hint": base + (
                "The draft check-in is selected; choose check-out without selecting check-in again."
                if (checklist.get("calendar_progress") or {}).get("next_field") == "check_out"
                else "Finish this open calendar: check-in before check-out."
            ),
        }
    core_pending = [item["field"] for item in form
                    if item.get("field") in {"destination", "check_in", "check_out"}
                    and item.get("status") != "verified"]
    if (checklist.get("calendar_progress") or {}).get("next_field") == "check_out":
        core_pending = [field for field in core_pending if field != "check_in"]
        if "check_out" not in core_pending:
            core_pending.append("check_out")
    guest_rows_visible = any(item.get("counter") or item.get("widget_scope") == "counter"
                             for item in items.values())
    if core_pending and navigation.get("stay_form_visible") and not guest_rows_visible:
        targets = [item.get("control_id") for item in form if item.get("field") in core_pending
                   and item.get("control_id") in items]
        for item in items.values():
            if "destination" in core_pending and discovery_query_control(item):
                targets.append(item["id"])
            if set(core_pending) & {"check_in", "check_out"} and (
                (item.get("date_kind") in {"opener", "date_opener"} or item.get("type") == "date")
                and (not item.get("date_endpoint") or item["date_endpoint"] in core_pending)
                or re.search(r"\b(?:next|previous|prev)\s+month\b", str(item.get("label") or ""), re.I)
            ):
                targets.append(item["id"])
        return {
            "phase": "prepare_stay", "fields": core_pending,
            "control_ids": list(dict.fromkeys(targets))[:8],
            "hint": "The existing place/dates are not yet verified for this request. Correct the destination "
            "and full requested date range before reopening guests for readback. Use the stay date controls; "
            "if the calendar is open, navigate to the requested month. Existing hotel cards may belong to the previous search.",
        }
    returned_core_mismatch = [field["field"] for field in scope_fields
                              if field.get("field") in {"destination", "check_in", "check_out"}
                              and field.get("status") == "mismatch"]
    if returned_core_mismatch and not core_pending and not guest_rows_visible:
        return {
            "phase": "await_applied_stay", "fields": returned_core_mismatch, "control_ids": [],
            "hint": "The form values match, but returned place/date evidence differs. Wait for the website's "
            "update and inspect the applied criteria. Do not reselect correct dates, reopen guests, or claim these cards match yet.",
        }
    rows = []
    for requirement in requirements:
        ids = [
            option["control_id"]
            for option in requirement.get("counter_controls", [])
            if option.get("control_id") in items
            and items[option["control_id"]].get("enabled", True)
        ]
        bound = items.get(requirement.get("control_id"), {})
        if bound.get("counter"):
            ids.append(bound["id"])
        if ids:
            rows.append((requirement, ids))
    pending = [
        (requirement, ids) for requirement, ids in rows
        if requirement.get("status") != "verified"
        and requirement.get("next_action") != "confirm_or_close_widget"
    ]
    if pending:
        return {
            "phase": "set_counters",
            "fields": [item[0]["field"] for item in pending],
            "control_ids": list(dict.fromkeys(cid for _, ids in pending for cid in ids))[:8],
            "hint": base + "Finish all visible pending rows before closing/switching widgets.",
        }
    if discovering and navigation.get("control_ids"):
        return {
            "phase": navigation["phase"],
            "fields": [],
            "control_ids": navigation["control_ids"],
            "hint": navigation["hint"] or (
                "Open the requested listing category before individual records. "
                "Location discovery is navigation; it is not a completed stay search."
            ),
        }
    for requirement in form:
        field = items.get(requirement.get("control_id"), {})
        if requirement.get("status") == "verified" or not field:
            continue
        actions, _ = _affordance(field)
        action = requirement.get("next_action")
        known_text = "value" in field and isinstance(field["value"], str)
        different = known_text and " ".join(field["value"].casefold().split()) != " ".join(
            str(requirement.get("expected", "")).casefold().split()
        )
        # The ledger knows whether a qualified autocomplete value is a
        # committed choice. Raw string differences must not override its
        # wait/select/inspect guidance and erase a site's selected entity.
        if known_text and "fill" in actions and (
            action == "fill" or not action and different
        ):
            return {
                "phase": "fill_fields",
                "fields": [requirement["field"]],
                "control_ids": [field["id"]],
                "hint": "Fill the requested literal value directly; clicking/focusing alone "
                "does not enter it. Then inspect owned suggestions if required.",
            }
        if action == "open_suggestions":
            return {
                "phase": "open_suggestions",
                "fields": [requirement["field"]],
                "control_ids": [field["id"]],
                "hint": "Matching text is uncommitted: open its suggestions once, then inspect.",
            }
    if open_stay_widget:
        return {
            "phase": "inspect_stay_widget", "fields": list(checklist.get("pending_fields", [])),
            "control_ids": [cid for cid in (checklist.get("result_handoff") or {}).get("widget_control_ids", []) if cid in items],
            "hint": "The stay widget is already open. Inspect form/dialog to read its values and confirmation control. "
            "Close the completed widget, then collect the updated hotel cards below. Do not reopen the widget or use site Search.",
        }
    submit = (
        _submission_controls(observation, checklist)
        if (ready and checklist.get("submission_ready", True))
        else []
    )
    if len(submit) == 1:
        return {
            "phase": "submit_search",
            "fields": [],
            "control_ids": [submit[0]["id"]],
            "hint": "Requested form values are verified; submit the actual search control once. "
            "An ordinary catalogue link does not submit the prepared form.",
        }
    information = checklist.get("information_coverage") or {}
    if checklist.get("information_needs") and (not form or ready):
        linked = checklist.get("collection_mode") == "linked_details"
        retained_index = any(
            item.get("kind") == "index"
            for item in checklist.get("collection_progress", {}).get("sources", [])
        )
        return {
            "phase": "collect_needed_details" if linked and retained_index else "inspect_information",
            "fields": list(information.get("detail_needed_fields", [])),
            "control_ids": [],
            "hint": "Inspect whether requested information is already visible. If absent, "
            "retain the current index and open its relevant same-site record links, not "
            "section/search links. Do not add unrequested metadata. Finish with partial_reason "
            "when fields are unavailable or budgets cannot provide them.",
        }
    return {
        "phase": "continue",
        "fields": list(checklist.get("pending_fields", [])),
        "control_ids": [],
        "hint": base + "Use fresh controls; no opener was inferred.",
    }


def _control(item, expected_values=(), *, focused=False, include_geometry=True):
    keys = (
        "id",
        "tag",
        "role",
        "type",
        "name",
        "label",
        "value",
        "selected",
        "expanded",
        "haspopup",
        "selection_required",
        "suggestions_pending",
        "submits_form",
        "form_scope",
        "widget_scope",
        "date",
        "date_kind",
        "date_endpoint",
        "date_widget_id",
        "date_navigation",
        "pagination",
        "href",
        "option_primary",
        "editable",
        "required",
        "invalid",
        "value_missing",
        "selection_placeholder",
        "selected_label",
        "validation_message",
    )
    actions, hint = _affordance(item)
    if (item.get("date_kind") == "opener" or item.get("date_widget_id")) and item.get("enabled", True):
        if "press" not in actions:
            actions.append("press")
    result = {"supported_actions": actions}
    if item.get("date_kind") == "opener" or item.get("date_widget_id"):
        result["supported_keys"] = ["Escape"]
    if hint:
        result["action_hint"] = hint
    for key in keys:
        value = item.get(key)
        if not _nonempty(value) or value is False:
            continue
        # Preserve values, hrefs and exact IDs; shorten presentation labels only.
        result[key] = _short(value, 180) if key in {
            "label", "option_primary", "selected_label", "validation_message"
        } else value
    if "value" in item and "fill" in actions:
        result["value"] = copy.deepcopy(item["value"])
    if item.get("enabled") is False:
        result["enabled"] = False
    if item.get("readonly"):
        result["readonly"] = True
    if include_geometry and item.get("rect"):
        result["rect"] = {
            key: item["rect"][key] for key in ("x", "y", "width", "height") if key in item["rect"]
        }
    if item.get("counter"):
        result["counter"] = {
            key: value
            for key, value in item["counter"].items()
            if key in {"label", "value", "direction", "method"} and _nonempty(value)
        }
    if (
        not focused
        or item.get("role") in {"option", "button", "gridcell"}
        or item.get("tag") == "BUTTON"
        or item.get("date")
        or _FORM_HINTS.search(str(item.get("label", "")))
    ) and item.get("text") != item.get("label"):
        if item.get("text"):
            result["text"] = _short(item["text"], 180)
    if not item.get("label") and item.get("context"):
        result["context"] = _short(item["context"], 120)
    if item.get("option_ids"):
        result["option_ids"] = list(item["option_ids"])
    if item.get("options"):
        selected = str(item.get("value", ""))
        options = list(item["options"])
        expected = {str(value).casefold() for value in expected_values}
        options.sort(
            key=lambda option: (
                str(option.get("value", "")) != selected,
                not bool(
                    expected
                    & {
                        str(option.get("value", "")).casefold(),
                        str(option.get("label", "")).casefold(),
                    }
                ),
            )
        )
        result["options"] = [
            {
                "value": option.get("value", ""),
                "label": _short(option.get("label", ""), 100),
                **({"disabled": True} if option.get("disabled") else {}),
            }
            for option in options[:12]
        ]
        if len(options) > 12:
            result["options_omitted"] = len(options) - 12
    return result


def _observation(observation, checklist, budget, task, *, focused=False, include_geometry=True):
    required_ids = {
        item.get("control_id")
        for item in checklist.get("requirements", [])
        if item.get("control_id")
    }
    date_ids = {
        item.get("control_id")
        for item in checklist.get("visible_date_choices", [])
        if item.get("control_id")
    }
    option_ids = {
        option.get("control_id")
        for item in checklist.get("requirements", [])
        for option in item.get("selection_options", [])
        if option.get("control_id")
    }
    option_ids.update(
        option_id
        for frame in observation.get("frames", [])
        for item in frame.get("controls", [])
        if item.get("selection_required")
        for option_id in item.get("option_ids", [])
    )
    observed_ids = {
        item.get("id")
        for frame in observation.get("frames", [])
        for item in frame.get("controls", [])
    }
    submit_ids = {item["id"] for item in _submission_controls(observation, checklist)}
    form_required = any(
        item.get("application") == "form" for item in checklist.get("requirements", [])
    )
    mandatory_ids = (
        required_ids | date_ids | (submit_ids if form_required else set())
        | {item.get("control_id") for item in checklist.get("unresolved_form_fields", [])}
        | set((checklist.get("calendar_progress") or {}).get("control_ids", []))
    ) & observed_ids
    navigation = _navigation_stage(observation, checklist)
    if navigation.get("phase") in {"discover_category", "discover_location"} and not navigation.get("stay_form_visible"):
        # Category links are actionable discovery controls, not background
        # record links to discard merely because stay fields are still pending.
        mandatory_ids.update(navigation.get("control_ids", []))
        mandatory_ids.update(navigation.get("category_control_ids", []))
        mandatory_ids.update(navigation.get("query_control_ids", []))
    focus = _interaction_focus(observation, checklist)
    focus_ids = set(focus["control_ids"])
    mandatory_ids |= set(focus.get("evidence_control_ids", [])) & observed_ids
    if focused:
        counters = {
            item.get("control_id")
            for check in checklist.get("requirements", [])
            for item in check.get("counter_controls", [])
            if item.get("control_id") in observed_ids
        }
        confirms = {
            item.get("id")
            for frame in observation.get("frames", [])
            for item in frame.get("controls", [])
            if re.fullmatch(r"done|apply|update|confirm|ok|close", str(item.get("label", "")), re.I)
            and item.get("enabled", True)
        }
        mandatory_ids |= focus_ids | (option_ids & observed_ids) | counters | confirms
    expected_values = [item.get("expected") for item in checklist.get("requirements", [])]
    query_terms = _terms(task) - _QUERY_FILLER
    for item in checklist.get("requirements", []):
        query_terms.update(_terms(item.get("expected", "")) - _QUERY_FILLER)
    form_pending = bool(checklist.get("pending_fields") or checklist.get("unresolved_form_fields"))
    result = {
        key: copy.deepcopy(observation[key])
        for key in ("url", "document_id", "version", "captured_urls")
        if key in observation
    }
    result["frames"] = []
    ranked = []
    total_controls = 0
    total_text = 0
    for frame_index, frame in enumerate(observation.get("frames", [])):
        text = str(frame.get("text", ""))
        total_text += len(text)
        kept_frame = {
            key: copy.deepcopy(frame[key])
            for key in (
                "url",
                "title",
                "password_or_code_visible",
                "controls_truncated",
                "visible_control_count",
                "focus",
                *(("viewport",) if include_geometry else ()),
            )
            if _nonempty(frame.get(key))
        }
        if "title" in kept_frame:
            kept_frame["title"] = _short(kept_frame["title"], 120)
        kept_frame["frame_index"] = frame_index
        kept_frame["text"] = "" if focused else text[: 400 if form_pending else 1400]
        if frame.get("widgets"):
            kept_frame["widgets"] = [
                {
                    "role": widget.get("role", ""),
                    "label": _short(widget.get("label", ""), 80),
                    "text": _short(widget.get("text", ""), 48 if focused else 160),
                }
                for widget in frame["widgets"][:4]
            ]
        kept_frame["controls"] = []
        result["frames"].append(kept_frame)
        for index, item in enumerate(frame.get("controls", [])):
            total_controls += 1
            label = str(item.get("label", ""))
            if (
                focused
                and item.get("id") not in mandatory_ids
                and (
                    item.get("href")
                    or item.get("role") in {"gridcell", "checkbox"}
                    or not (
                        item.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}
                        or item.get("submits_form")
                        or (
                            item.get("tag") in {"BUTTON", "INPUT"}
                            and item.get("type") in {"submit", "image"}
                        )
                        or item.get("counter")
                        or _FORM_HINTS.search(label)
                    )
                )
            ):
                continue
            if item.get("id") in mandatory_ids:
                rank = 0
            elif item.get("id") in option_ids:
                primary = str(item.get("option_primary", item.get("label", ""))).casefold()
                rank = 1 if primary in {str(value).casefold() for value in expected_values} else 2
            elif item.get("counter") or item.get("role") == "option":
                rank = 1
            elif item.get("expanded") == "true" or item.get("tag") in {
                "INPUT",
                "SELECT",
                "TEXTAREA",
            }:
                rank = 2
            elif (_FORM_HINTS.search(label) and not item.get("href")) or item.get("submits_form"):
                rank = 3
            elif item.get("role") in {"gridcell", "checkbox"} and item.get("date"):
                rank = 4
            elif item.get("href"):
                words = _terms(
                    " ".join(str(item.get(key, "")) for key in ("label", "text", "href"))
                )
                rank = 6 if form_pending else 4 if query_terms & words else 6
            else:
                rank = 5
            ranked.append(
                (
                    rank,
                    frame_index,
                    index,
                    _control(
                        item, expected_values, focused=focused, include_geometry=include_geometry
                    ),
                )
            )
    ranked.sort(key=lambda entry: entry[:3])
    # Context text yields to current actionable controls, not the other way round.
    reserve = 550
    for frame in result["frames"]:
        if _size(result) > budget - reserve:
            frame["text"] = ""
    included = []
    for rank, frame_index, index, item in ranked:
        target = result["frames"][frame_index]["controls"]
        target.append(item)
        if _size(result) > budget - reserve:
            target.pop()
            continue
        included.append((rank, frame_index, index, item))
    ids = {item.get("id") for _, _, _, item in included}
    if mandatory_ids - ids:
        raise ValueError(
            "Requested fields or date choices could not fit in the navigation context. "
            "Focus the required form/widget before continuing; no paid decision was sent."
        )
    for _, _, _, item in included:
        if item.get("option_ids"):
            omitted = [option_id for option_id in item["option_ids"] if option_id not in ids]
            item["option_ids"] = [option_id for option_id in item["option_ids"] if option_id in ids]
            if omitted:
                item["option_ids_omitted"] = len(omitted)
    result["context_coverage"] = {
        "controls_observed": total_controls,
        "controls_included": len(included),
        "controls_omitted": total_controls - len(included),
        "requested_controls_omitted": len(mandatory_ids - ids),
        "associated_options_omitted": len(option_ids - ids),
        "text_chars_omitted": total_text - sum(len(frame["text"]) for frame in result["frames"]),
        "notice": "Navigation context only; omitted controls/text are not absent. "
        "Inspect a widget or scroll when needed. Complete extraction capture is separate.",
    }
    return result


def _build_navigation_context(
    payload,
    *,
    max_chars=NAVIGATION_CONTEXT_CHARS,
    observation_chars=OBSERVATION_CONTEXT_CHARS,
    focused=False,
    include_geometry=True,
):
    """Project a complete current decision into a bounded JSON-text envelope.

    This is not a delta stream: each request carries the original instructions,
    request-derived values, current field statuses, fresh IDs and remaining budget.
    The entire task is retained or rejected explicitly; it is never truncated.
    """
    if max_chars < 3000 or observation_chars < 1000:
        raise ValueError("Navigation context budget is too small.")
    checklist = payload.get("task_checklist") or {}
    compact_checklist = {
        "requirements": _requirements(checklist),
        "pending_fields": list(checklist.get("pending_fields", [])),
        "search_submitted": bool(checklist.get("search_submitted")),
        "matching_results_observed": observed_matching_results_ready(
            checklist,
            document_id=(payload.get("observation") or {}).get(
                "document_id", (payload.get("observation") or {}).get("url")
            ),
        ),
        "search_response_pending": bool(checklist.get("search_response_pending")),
    }
    navigation = _navigation_stage(payload.get("observation") or {}, checklist)
    if navigation:
        compact_checklist["navigation_stage"] = navigation
    if checklist.get("result_handoff"):
        compact_checklist["result_handoff"] = {
            key: copy.deepcopy(checklist["result_handoff"][key])
            for key in ("ready", "reason", "scope_status", "record_count", "unverified_fields", "mismatched_fields")
            if key in checklist["result_handoff"]
        }
    if checklist.get("unresolved_form_fields"):
        compact_checklist["unresolved_form_fields"] = [
            {key: _short(item[key], 180) if key in {"label", "validation_message"}
             else copy.deepcopy(item[key])
             for key in ("control_id", "label", "required", "invalid", "value_missing",
                         "validation_message") if _nonempty(item.get(key))}
            for item in checklist["unresolved_form_fields"][:12]
        ]
    if checklist.get("collection_mode") in {
        "model_decides",
        "linked_details",
        "listing_results",
        "search_results",
        "current_page",
    }:
        compact_checklist["collection_mode"] = checklist["collection_mode"]
    if checklist.get("collection_goal"):
        compact_checklist["collection_goal"] = {
            "mode": checklist["collection_goal"]["mode"],
            "reason": _short(checklist["collection_goal"].get("reason", ""), 160),
        }
    if checklist.get("collection_scope"):
        compact_checklist["collection_scope"] = copy.deepcopy(checklist["collection_scope"])
    if isinstance(checklist.get("site_behavior"), dict):
        compact_checklist["site_behavior"] = {
            key: _short(checklist["site_behavior"][key], 180)
            for key in ("site", "search_mode", "reason")
            if isinstance(checklist["site_behavior"].get(key), str)
        }
    if checklist.get("information_need_feedback"):
        compact_checklist["information_need_feedback"] = copy.deepcopy(
            checklist["information_need_feedback"][-3:]
        )
    if checklist.get("information_needs"):
        compact_checklist["information_needs"] = [
            {
                "field": item["field"], "role": item.get("role", "other"),
                "status": item.get("status", "unknown"),
                "evidence": _short(item.get("evidence", ""), 120),
                "captured_sources": len(item.get("source_evidence", [])),
            }
            for item in checklist["information_needs"][:16]
        ]
        coverage = checklist.get("information_coverage") or {}
        compact_checklist["information_coverage"] = {
            key: copy.deepcopy(coverage[key])
            for key in (
                "status", "missing_fields", "detail_needed_fields",
                "fields_with_source_evidence", "partial_reason",
            )
            if key in coverage
        }
    if checklist.get("result_scope"):
        scope = checklist["result_scope"]
        compact_checklist["result_scope"] = {
            "status": scope.get("status"),
            "source": "returned_page",
            "document_id": scope.get("document_id"),
            "fields": [
                {key: copy.deepcopy(item[key]) for key in ("field", "expected", "observed", "status") if key in item}
                for item in scope.get("fields", [])[:6]
            ],
            "contradictions": [
                {"code": item.get("code"), "evidence": _short(item.get("evidence", ""), 120)}
                for item in scope.get("contradictions", [])[:3]
            ],
            "note": "Independent returned context; pre-search checks are not availability proof.",
        }
    if checklist.get("catalog_followup"):
        compact_checklist["catalog_followup"] = {
            "status": checklist["catalog_followup"].get("status"),
            "limit": 1,
            "note": "Different observed catalog document; verify its fresh form before one new Search.",
        }
    if checklist.get("collection_progress"):
        progress = checklist["collection_progress"]
        sources = []
        for source in progress.get("sources", [])[:6]:
            url = str(source.get("url", ""))
            # Do not turn shortened URLs into apparent navigation targets.
            sources.append(
                {
                    "kind": source.get("kind"),
                    **(
                        {"url": url}
                        if len(url) <= 300
                        else {
                            "url_omitted": True,
                            "url_fingerprint": hashlib.sha256(url.encode()).hexdigest()[:16],
                        }
                    ),
                }
            )
        compact_checklist["collection_progress"] = {
            "sources": sources,
            **{
                key: progress[key]
                for key in (
                    "captured_pages",
                    "detail_pages",
                    "max_pages",
                    "max_detail_pages",
                )
                if key in progress
            },
            "coverage": _short(progress.get("coverage", ""), 160),
            "detail_candidates": [
                {"label": _short(item.get("label", ""), 100), **(
                    {"url": item["url"]} if len(item.get("url", "")) <= 300
                    else {"url_omitted": True}
                )}
                for item in progress.get("detail_candidates", [])[:8]
            ],
        }
    if "submission_ready" in checklist:
        compact_checklist["submission_ready"] = bool(checklist["submission_ready"])
    if checklist.get("search_transition"):
        compact_checklist["search_transition"] = {
            key: copy.deepcopy(checklist["search_transition"][key])
            for key in (
                "attempted",
                "confirmed",
                "attempt_status",
                "dispatch_status",
                "result_state",
                "retained_for_linked_details",
                "scope",
                "status",
                "method",
                "source_url",
                "result_url",
                "result_document_id",
            )
            if key in checklist["search_transition"]
        }
        if compact_checklist["matching_results_observed"]:
            provenance = checklist["search_transition"]["submission_provenance"]
            compact_checklist["search_transition"]["submission_provenance"] = {
                key: copy.deepcopy(provenance[key])
                for key in ("actor", "action", "evidence_method") if key in provenance
            }
    for key in ("request_error", "date_resolution", "calendar_progress"):
        if _nonempty(checklist.get(key)):
            compact_checklist[key] = copy.deepcopy(checklist[key])
    dates = checklist.get("visible_date_choices", [])
    if dates:
        compact_checklist["visible_date_choices"] = [
            {key: item[key] for key in ("field", "date", "control_id") if key in item}
            for item in dates
        ]
    result = {
        "task": copy.deepcopy(payload.get("task", "")),
        **({"collection_goal_required": True} if payload.get("collection_goal_required") else {}),
        **(
            {"requested_output_fields": list(payload["requested_output_fields"])}
            if payload.get("requested_output_fields")
            else {}
        ),
        "reference_date": payload.get("reference_date"),
        "task_checklist": compact_checklist,
        "budget": copy.deepcopy(payload.get("budget", {})),
        "interaction_focus": _interaction_focus(payload.get("observation") or {}, checklist),
        "previous_decision_failure": None,
        "loop_contract": {
            "fresh_observation": True,
            "observation_refresh_needs_human": False,
            "unchanged_refresh_limit": 2,
            "action_history_bounded": True,
        },
    }
    if _size(result) > max_chars - 1500:
        raise ValueError(
            "The complete request and its required values exceed the navigation context budget. "
            "Shorten the request; no instructions were silently truncated."
        )
    actions = payload.get("recent_actions") or []
    result["recent_actions"] = [
        {
            key: _short(item[key], 120) if isinstance(item[key], str) else item[key]
            for key in ("step", "action", "control", "status", "expected", "observed", "guidance")
            if _nonempty(item.get(key))
        }
        for item in actions[-3:]
    ]
    transition = payload.get("last_transition") or {}
    if transition:
        result["last_transition"] = {
            key: copy.deepcopy(transition[key])
            for key in ("status", "document_changed", "widget_changed", "scrolled")
            if key in transition
        }
    failure = payload.get("previous_decision_failure") or {}
    if failure.get("error_code"):
        result["previous_decision_failure"] = {
            key: copy.deepcopy(failure[key])
            for key in ("error_code", "call", "decision_valid", "response_status")
            if key in failure
        }
    # Reserve room for focus guidance and numeric metrics, not just observation.
    available = max_chars - _size(result) - 1000
    while available < 1200 and result["recent_actions"]:
        result["recent_actions"].pop(0)
        available = max_chars - _size(result) - 1000
    result["observation"] = _observation(
        payload.get("observation") or {},
        checklist,
        min(observation_chars, available),
        result["task"],
        focused=focused,
        include_geometry=include_geometry,
    )
    # Focus IDs must also be present in the model's bounded current inventory.
    result["interaction_focus"] = _interaction_focus(result["observation"], checklist)
    if "navigation_stage" in compact_checklist:
        compact_checklist["navigation_stage"] = _navigation_stage(result["observation"], checklist)
    # Explicit count metrics are content-free and support before/after comparison.
    result["context_metrics"] = {
        "raw_chars": _size(
            {key: value for key, value in payload.items() if key != "viewport_image"}
        ),
        "limit_chars": max_chars,
        "sections": {key: _size(result[key]) for key in result},
    }
    result["context_metrics"]["packed_chars"] = 0
    for _ in range(3):
        result["context_metrics"]["packed_chars"] = _size(result)
    if _size(result) > max_chars:
        raise ValueError("Navigation context could not fit without losing required request values.")
    return result


def build_navigation_context(
    payload,
    *,
    max_chars=NAVIGATION_CONTEXT_CHARS,
    observation_chars=OBSERVATION_CONTEXT_CHARS,
    include_geometry=None,
):
    """Use a smaller recognizable-form view; retain rich browsing or fall back safely."""
    focus = _interaction_focus(
        payload.get("observation") or {}, payload.get("task_checklist") or {}
    )
    focused = focus["phase"] in {
        "discover_category",
        "discover_location",
        "fill_fields",
        "open_suggestions",
        "wait_suggestions",
        "choose_option",
        "set_dates",
        "prepare_stay",
        "await_applied_stay",
        "set_counters",
        "confirm_widget",
        "inspect_stay_widget",
        "submit_search",
        "awaiting_results",
    }
    attempts = [("rich_fallback" if focused else "rich", max_chars, observation_chars)]
    if focused:
        attempts.insert(
            0,
            (
                "focused",
                min(max_chars, FOCUSED_CONTEXT_CHARS),
                min(observation_chars, FOCUSED_OBSERVATION_CHARS),
            ),
        )
    for index, (tier, limit, observation_limit) in enumerate(attempts):
        try:
            result = _build_navigation_context(
                payload,
                max_chars=limit,
                observation_chars=observation_limit,
                focused=focused,
                include_geometry=True
                if include_geometry is None and not focused
                else bool(include_geometry),
            )
            metrics = result["context_metrics"]
            metrics.update(tier=tier, observation_limit_chars=observation_limit)
            for _ in range(3):
                metrics["packed_chars"] = _size(result)
            if _size(result) > limit:
                raise ValueError("Navigation context exceeds its configured hard upper limit.")
            return result
        except ValueError:
            if index == len(attempts) - 1:
                raise


def screenshot_selection(
    observation, checklist=None, transition=None, previous_fingerprints=(), *, decision_index=0
):
    """Choose an optional fresh image; never store pixels or repeat an unchanged UI.

    Consent is enforced by the caller. Recognized DOM fields/calendar/counter
    actions need no image every turn. An unfamiliar layout, a genuinely ambiguous
    foreground actuator or stalled progress can benefit from one visual decision.
    """
    checklist = checklist or {}
    transition = transition or {}
    items = [item for frame in observation.get("frames", []) for item in frame.get("controls", [])]
    signature = {
        "url": observation.get("url"),
        "document_id": observation.get("document_id"),
        "frames": [
            {
                "url": frame.get("url"),
                "viewport": frame.get("viewport"),
                "widgets": frame.get("widgets"),
                "controls": [
                    {
                        key: item.get(key)
                        for key in (
                            "label",
                            "tag",
                            "role",
                            "type",
                            "value",
                            "expanded",
                            "selected",
                            "rect",
                        )
                    }
                    | {
                        "counter": {
                            key: item.get("counter", {}).get(key)
                            for key in ("label", "value", "direction", "method")
                        }
                        if item.get("counter")
                        else None
                    }
                    for item in frame.get("controls", [])
                ],
            }
            for frame in observation.get("frames", [])
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    reason = "dom_sufficient"
    if fingerprint in previous_fingerprints:
        reason = "unchanged"
    elif any(frame.get("password_or_code_visible") for frame in observation.get("frames", [])):
        reason = "authentication_visible"
    elif transition.get("status") == "no_observable_change":
        reason = "no_progress"
    elif any(
        item.get("counter")
        and (
            item["counter"].get("value") is None
            or item["counter"].get("direction") not in {"increase", "decrease"}
            and item["counter"].get("method") == "button"
        )
        for item in items
    ):
        reason = "ambiguous_controls"
    elif any(
        not item.get("label")
        and not item.get("text")
        and item.get("enabled", True)
        and (
            item.get("haspopup")
            or item.get("submits_form")
            or item.get("role") in {"option", "gridcell", "spinbutton"}
        )
        for item in items
    ):
        reason = "ambiguous_controls"
    elif (
        decision_index == 0
        and not any(
            item.get("tag") in {"INPUT", "SELECT", "TEXTAREA"} or item.get("counter")
            for item in items
        )
        and not checklist.get("visible_date_choices")
    ):
        reason = "first_layout"
    return {
        "send": reason
        not in {
            "dom_sufficient",
            "unchanged",
            "authentication_visible",
        },
        "reason": reason,
        "fingerprint": fingerprint,
    }
