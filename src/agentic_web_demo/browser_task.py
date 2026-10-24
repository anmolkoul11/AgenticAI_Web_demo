"""Request-derived form evidence and bounded context for a dynamic browser agent.

No website selectors or action recipes: only literal request grounding, fresh
control values and submission evidence. Form evidence is not listing availability.
"""

import copy
import json
import re
from datetime import date
from difflib import SequenceMatcher

from agentic_web_demo.browser_dates import resolve_stay_dates
from agentic_web_demo.browser_navigation import (
    HOTEL_REQUEST,
    guest_counts,
    requested_dates,
    requested_destination,
    requested_stay_dates,
)
from agentic_web_demo.browser_runtime import bound_controls, controls, identity
from agentic_web_demo.capture import clean_url, query_identity_omitted
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.stay_scope import observed_result_scope, requested_stay

OBSERVATION_BUDGET = 24000


def normalized(value):
    return " ".join(str(value).casefold().split())


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
        re.fullmatch(r"apply|confirm|ok", normalized(facts.get(key, "")))
        for key in ("label", "text")
    )
    return bool(
        facts.get("role") in {"option", "gridcell", "checkbox", "radio", "spinbutton"}
        or facts.get("counter")
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
    found = occupancy_components(label)
    return found[0] if len(found) == 1 else None


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
        if native and kind not in {"checkbox", "radio"} and role not in {"option", "gridcell"}:
            return True
        counter = control.get("counter")
        if counter:
            component = occupancy_component(counter.get("label", ""))
            return (
                component in {None, name}
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
        self.date_choices = {}
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
                if context.get("status") != "form_verified_search_submitted":
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
        if not requirements:
            return
        staged_requirements = copy.deepcopy(self.requirements)
        staged_bindings = copy.deepcopy(self.bindings)
        for item in requirements:
            requirement = item.model_dump()
            name = requirement["name"]
            known = self.requirements.get(name)
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
                    raise WebsiteError("A task requirement lacks a quote from your request.")
                interpreted = normalized(requirement["expected"]) not in quote
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
                staged_bindings[name] = {
                    "document": observation.get("document_id", observation.get("url")),
                    "identity": identity(candidates[0]),
                    "counter_label": (candidates[0].get("counter") or {}).get("label"),
                }
        self.requirements = staged_requirements
        self.bindings = staged_bindings

    def counter_field(self, control):
        """Resolve requested numeric fields from live labels/bindings, not site names."""
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
        ]

    def before_action(self, facts, decision, observation):
        """Invalidate tentative proof before an action, including uncertain outcomes."""
        action = getattr(decision, "action", "click")
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

    def remember_action(self, facts, outcome, decision=None, observation=None):
        observation = observation or {}
        # Idempotent for the live pre-action call; also supports direct fixture calls.
        self.before_action(facts, decision, observation)
        action = getattr(decision, "action", "click")
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
        self.confirm_pending_submission(observation)
        document = observation.get("document_id", observation.get("url"))
        if self.document_id is not None and self.document_id != document:
            self.date_choices.clear()
            self.destination_selections.clear()
            if self.submission and self.submission["result_document_id"] != document:
                self.submission = None
                self.result_scope = None
        self.document_id = document
        self.checks = [self.verify(item, observation) for item in self.requirements.values()]
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
        for index, control in enumerate(controls(observation)):
            owner = control.get("date_owner_id")
            if control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"} and not (
                isinstance(owner, str) and owner
                and control.get("tag") == "INPUT"
                and control.get("type") in {"checkbox", "radio", "button"}
            ):
                continue
            if control.get("enabled", True) is False:
                continue
            try:
                dates = requested_dates(
                    " ".join(str(control.get(k, "")) for k in ("date", "label", "text"))
                )
            except WebsiteError:
                continue
            if len(dates) == 1 and dates[0] in pending_dates:
                choice = {
                    "field": pending_dates[dates[0]],
                    "date": dates[0],
                    "control_id": control.get("id"),
                    "label": control.get("label", ""),
                }
                # Only an observed gridcell ancestor proves these controls
                # belong to the same day. Do not merge equal dates in separate
                # widgets, frames, or older observations without ownership.
                key = (
                    (str(control.get("id", "")).partition(":")[0], owner, dates[0])
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
            if not results.get("busy") and results.get("no_results"):
                self.submission["result_state"] = "empty"
            elif results.get("busy") or results.get("record_count", 0) > 0:
                self.submission["result_state"] = "observed"
            self.result_scope = observed_result_scope(self.requested_stay, observation)
            self.submission["result_scope"] = copy.deepcopy(self.result_scope)
            if self.prepare_catalog_followup(observation):
                # This is a different, observed catalog document, not a retry
                # of an uncertain dispatch. Discard old form bindings/year
                # proof and prepare its actual form once from fresh controls.
                self.bindings.clear()
                self.date_choices.clear()
                self.destination_selections.clear()
                self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        self.submission_candidates = self.find_submission_candidates(observation)
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
                and re.fullmatch(r"done|apply|close", str(item.get("label", "")), re.I)
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
        binding = self.bindings.get(name)
        bound = bound_controls(binding, observation) if binding else []
        missing_occupancy = (
            binding
            and not bound
            and name in {"adults", "children", "rooms"}
            and binding["document"] == observation.get("document_id", observation.get("url"))
        )
        if binding and len(bound) != 1:
            if self.submission and self.submission["result_document_id"] == observation.get(
                "document_id", observation.get("url")
            ):
                saved = next(
                    (c for c in self.submission["requirements"] if c["field"] == name), None
                )
                if saved:
                    return {**saved, "method": "verified_pre_submit_form"}
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
        if len(bound) == 1 and not (
            name in {"adults", "rooms", "children"} and bound[0].get("counter")
        ):
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
        candidates = []
        counter_candidates = []
        counter_options = []
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
                seen = guest_counts(text) if not counter else None
                if seen and name in seen:
                    candidates.append((str(seen[name]), text))
                if re.search(rf"\b{name}\b", label, re.I) and str(value).isdigit():
                    candidates.append((str(value), text))
            elif name in {"check_in", "check_out"}:
                if control.get("date") and control.get("tag") not in {"INPUT", "SELECT"}:
                    # Individual calendar choices are not the committed form
                    # summary, even when they happen to match the requested day.
                    continue
                date_hint = re.search(
                    r"check.?in|check.?out|arrival|departure|dates|calendar", label, re.I
                )
                if not date_hint:
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
                if not combined and not re.search(specific, label, re.I):
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
        if counter_candidates:
            counter_values = {normalized(value) for value, _ in counter_candidates}
            summary_values = {normalized(value) for value, _ in candidates}
            counter_match = counter_values == {normalized(expected)}
            summary_conflict = bool(summary_values - {normalized(expected)})
            return {
                **base,
                "status": "verified" if counter_match and not summary_conflict else "pending",
                "observed": "; ".join(sorted(counter_values)),
                "evidence": counter_candidates[0][1][:600],
                "method": "visible_counter",
                "counter_controls": counter_options,
                "next_action": "confirm_or_close_widget" if counter_match else "set_counter",
                "summary_confirmation_pending": counter_match and summary_conflict,
            }
        values = {normalized(value) for value, _ in candidates}
        matched = candidates and values == {normalized(expected)}
        if matched:
            return {
                **base,
                "status": "verified",
                "observed": expected,
                "evidence": candidates[0][1][:600],
            }
        if candidates:
            return {
                **base,
                "status": "mismatch",
                "observed": "; ".join(sorted(values)),
                "evidence": candidates[0][1][:600],
            }
        if self.submission and self.submission["result_document_id"] == observation.get(
            "document_id", observation.get("url")
        ):
            saved = next((c for c in self.submission["requirements"] if c["field"] == name), None)
            if saved:
                return {**saved, "method": "verified_pre_submit_form"}
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
                    return {**saved, "method": "verified_pre_submit_form"}
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

    def is_submit(self, decision, facts):
        if decision.action not in {"click", "press"}:
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
        required = {r["name"] for r in self.requirements.values() if r["application"] == "form"}
        checked = {c["field"] for c in self.checks if c["status"] == "verified"}
        if not required <= checked:
            return False
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
        return {
            "requirements": copy.deepcopy(self.checks),
            "pending_fields": self.pending(),
            "search_submitted": bool(self.submission or self.collection_search),
            "search_response_pending": bool(
                self.pending_submission
                and self.pending_submission.get("dispatch_status") != "not_dispatched"
            ),
            "request_error": self.request_error,
            "date_resolution": copy.deepcopy(self.date_resolution),
            "visible_date_choices": copy.deepcopy(self.visible_date_choices),
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
            "result_scope": copy.deepcopy(self.result_scope),
            "catalog_followup": copy.deepcopy(self.catalog_followup),
            "search_transition": {
                "attempted": bool(
                    self.pending_submission or self.submission or self.collection_search
                ),
                "confirmed": bool(self.submission or self.collection_search),
                "attempt_status": "transition_confirmed"
                if self.submission or self.collection_search
                else "attempted_unconfirmed"
                if self.pending_submission
                else "not_attempted",
                "dispatch_status": (
                    self.submission or self.pending_submission or self.collection_search or {}
                ).get("dispatch_status", "not_attempted"),
                "result_document_id": (self.submission or self.collection_search)[
                    "result_document_id"
                ]
                if self.submission or self.collection_search
                else None,
                "scope": "form_values_and_submission_only",
                "submission_provenance": copy.deepcopy(
                    (
                        self.submission or self.pending_submission or self.collection_search or {}
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
            "status": "form_verified_search_submitted",
            **copy.deepcopy(self.submission),
            "requirements": copy.deepcopy(self.checks),
            "availability_verified": False,
            "record_values_verified": False,
            "date_resolution": copy.deepcopy(self.date_resolution),
            "result_scope": copy.deepcopy(self.result_scope),
            "requested_stay_verified": (self.result_scope or {}).get("status") == "verified",
            "source_preview_only": self.source_preview_ready(),
        }
