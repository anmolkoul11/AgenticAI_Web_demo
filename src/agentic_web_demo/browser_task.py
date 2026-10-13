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
from agentic_web_demo.custom_fetch import WebsiteError

OBSERVATION_BUDGET = 24000


def normalized(value):
    return " ".join(str(value).casefold().split())


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
    def __init__(self, instructions, reference_date=None):
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
        self.document_id = None
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
                        re.search(r"\bdetails?\b|\bamenities\b", instructions, re.I)
                        or re.search(
                            r"\b(?:open|follow|visit|read|enrich)\b[^.!?\n]{0,160}"
                            r"\b(?:links?|urls?|pages?|hotels?|properties)\b",
                            instructions,
                            re.I,
                        )
                        or re.search(
                            r"\b(?:full|detailed)\b[^.!?\n]{0,80}"
                            r"\b(?:rooms?|facilities|descriptions?|information|context)\b",
                            instructions,
                            re.I,
                        )
                    )
                    self.collection_mode = (
                        "linked_details" if details_requested else "listing_results"
                    )
            except WebsiteError as exc:
                self.request_error = str(exc)

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
        field["form_scope"] = control.get("form_scope")
        if field["name"]:
            field.pop("label")
            field.pop("role")
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
        self.document_id = document
        self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        if (self.submission or self.pending_submission) and any(
            c["status"] == "mismatch" for c in self.checks
        ):
            self.submission = None
            self.pending_submission = None
            self.checks = [self.verify(item, observation) for item in self.requirements.values()]
        self.visible_date_choices = []
        pending_dates = {
            item["expected"]: item["field"]
            for item in self.checks
            if item["field"] in {"check_in", "check_out"} and item["status"] != "verified"
        }
        for control in controls(observation):
            if control.get("tag") in {"INPUT", "SELECT", "TEXTAREA"}:
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
                self.visible_date_choices.append(
                    {
                        "field": pending_dates[dates[0]],
                        "date": dates[0],
                        "control_id": control.get("id"),
                        "label": control.get("label", ""),
                    }
                )
        self.submission_candidates = self.find_submission_candidates(observation)
        return self.snapshot()

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
                or control.get("role") == "option"
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
        if not any(item["application"] == "form" for item in self.requirements.values()):
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
        if decision.purpose == "submit_search":
            return True
        if decision.action == "press" and decision.value == "Enter":
            if facts.get("selection_required") and (
                facts.get("expanded") == "true" or facts.get("option_ids")
            ):
                # Accepting a highlighted autocomplete option is not a Search.
                # This does not verify its selection; the clicked-option flow does.
                return False
            return True
        search_label = bool(re.search(r"^(?:search|find)\b|\bsearch with ai\b", label))
        if not search_label and (
            facts.get("role") in {"option", "gridcell", "checkbox", "radio", "spinbutton"}
            or facts.get("expanded") in {"true", "false"}
            or facts.get("haspopup")
            or facts.get("counter")
            or facts.get("date")
            or re.search(
                r"check.?in|check.?out|\bcalendar\b|\bselect dates\b|"
                r"\bnext month\b|\bprevious month\b",
                label,
            )
        ):
            # Widget buttons can have default type=submit even when their site's
            # handler opens/changes a widget. Unexpected navigation is checked
            # after acting; a calendar choice is not automatically Search.
            return False
        # Do not rely on the model's purpose or an exact accessible label.
        # Native submits and decorated search actions are still submissions.
        if facts.get("submits_form") or (
            facts.get("tag") == "INPUT" and facts.get("type") in {"submit", "image"}
        ):
            return True
        if re.search(r"\bsearch with ai\b", label):
            return True
        return (
            decision.action == "click"
            and (facts.get("tag") in {"BUTTON", "A"} or facts.get("role") == "button")
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

    def submitted(self, before, after, source_url):
        required = {r["name"] for r in self.requirements.values() if r["application"] == "form"}
        checked = {c["field"] for c in self.checks if c["status"] == "verified"}
        if not required <= checked:
            return False
        self.pending_submission = {
            "before": copy.deepcopy(before),
            "source_url": source_url,
            "requirements": copy.deepcopy(self.checks),
        }
        return self.confirm_pending_submission(after)

    def confirm_pending_submission(self, after):
        if not self.pending_submission:
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
                "source_url": self.pending_submission["source_url"],
                "result_url": after.get("url"),
                "result_document_id": after.get("document_id", after.get("url")),
                "requirements": self.pending_submission["requirements"],
                "scope": "form_values_and_submission_only",
            }
            self.pending_submission = None
        return changed

    def snapshot(self):
        return {
            "requirements": copy.deepcopy(self.checks),
            "pending_fields": self.pending(),
            "search_submitted": bool(self.submission),
            "search_response_pending": bool(self.pending_submission),
            "request_error": self.request_error,
            "date_resolution": copy.deepcopy(self.date_resolution),
            "visible_date_choices": copy.deepcopy(self.visible_date_choices),
            "collection_mode": self.collection_mode,
            "submission_candidates": copy.deepcopy(self.submission_candidates),
            "search_transition": {
                "attempted": bool(self.pending_submission or self.submission),
                "confirmed": bool(self.submission),
                "result_document_id": self.submission["result_document_id"]
                if self.submission
                else None,
                "scope": "form_values_and_submission_only",
            },
            "note": "Form read-back/submission is not independent proof of listing "
            "availability, price basis or coverage.",
        }

    def completion_problem(self):
        if self.pending_submission:
            return (
                "Search was clicked but its response is not confirmed yet. Wait and "
                "inspect the results, or pause; do not submit again or finish."
            )
        if self.pending():
            return (
                "Requested form values are still unconfirmed: "
                + ", ".join(self.pending())
                + ". Continue setting and reading back the controls, or pause. Do not finish."
            )
        if (
            any(r["application"] == "form" for r in self.requirements.values())
            and not self.submission
        ):
            return (
                "Requested form values must be verified and Search must produce an "
                "observed page change before finishing. A city catalog is not a "
                "completed stay search."
            )
        return None

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
        }
