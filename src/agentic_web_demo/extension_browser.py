"""Selected-tab transport for the existing browser agent, not another planner.

Only the extension executes packaged DOM inspections and browser-level input in
the selected tab. This adapter sends bounded commands through the signed-in local
relay; it never reads a browser profile, cookies or an open debugger port. The
selected tab stays open when its frozen sources are returned.
"""

import copy
import hashlib
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    DOMBrowserTools,
    OpenAIBrowserDecider,
    display_url,
    rendered_results_ready,
)
from agentic_web_demo.browser_runtime import bound_controls
from agentic_web_demo.capture import Capture, clean_url
from agentic_web_demo.custom_browser import access_challenge
from agentic_web_demo.custom_fetch import WebsiteError, origin, public_url
from agentic_web_demo.extension_channel import ExtensionCommandError
from agentic_web_demo.stay_scope import URL_FIELDS, url_stay_values


def requires_manual_verification(text):
    sample = " ".join(str(text).lower().split())[:2000]
    return access_challenge(sample) or any(marker in sample for marker in (
        "access is temporarily restricted", "unusual activity", "slide to verify",
    ))


def safe_tab_url(value):
    """Keep record identity and literal stay values, never arbitrary query data."""
    value = public_url(value)
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise WebsiteError("The selected website must use HTTPS.")
    try:
        pairs = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=100)
    except ValueError:
        raise WebsiteError("The selected tab URL has too many query fields.") from None
    retained = parse_qsl(urlsplit(clean_url(value)).query, keep_blank_values=True)
    for key, content in pairs:
        if key.casefold() in {"ss", "dest_id", "dest_type"} and len(content) <= 128 and not (
            "://" in content or "@" in content or any(ord(char) < 32 for char in content)
        ):
            retained.append((key, content))
        if key.casefold() in URL_FIELDS and url_stay_values(
            "https://example.org/?" + urlencode([(key, content)])
        ):
            retained.append((key, content))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(retained), ""))


def observation_diagnostics(reply):
    """Keep popup/focus counts for debugging, never field values or page text."""
    frame = reply.get("frame")
    frame = frame if isinstance(frame, dict) else {}
    autocomplete = frame.get("autocomplete_diagnostics")
    if not isinstance(autocomplete, dict):
        autocomplete = {}
    tab_state = reply.get("tab_state")
    tab_state = tab_state if isinstance(tab_state, dict) else {}
    input_driver = reply.get("input_driver")
    input_driver = (
        input_driver
        if isinstance(input_driver, str) and input_driver in {"native_cdp", "dom"}
        else "unknown"
    )

    def version(name):
        value = reply.get(name)
        return value if isinstance(value, str) and re.fullmatch(r"[0-9.]{1,20}", value) else "unknown"

    def counts(value):
        return {
            key: value[key]
            for key in ("field_count", "visible_listbox_count", "visible_option_count",
                        "controlled_popup_count", "visible_controlled_popup_count", "owned_option_count")
            if isinstance(value.get(key), int) and not isinstance(value[key], bool)
            and 0 <= value[key] <= 10_000
        }

    fields = []
    inventory = autocomplete.get("fields", [])
    for item in (inventory if isinstance(inventory, list) else [])[:8]:
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9]{1,5}", str(item.get("control_id", ""))):
            continue
        fields.append({
            "control_id": "0:" + str(item["control_id"]),
            "focused": item.get("focused") is True,
            "expanded": item.get("expanded") if isinstance(item.get("expanded"), str)
            and item["expanded"] in {"true", "false"} else "unknown",
            "association": item.get("association") if isinstance(item.get("association"), str)
            and item["association"] in {"explicit_aria", "single_expanded_listbox", "unresolved"} else "unknown",
            **counts(item),
        })
    return {
        "adapter": (
            "selected_tab_native_cdp" if input_driver == "native_cdp"
            else "selected_tab_dom" if input_driver == "dom" else "selected_tab_unknown"
        ),
        "observation": "dom",
        "input": input_driver,
        "worker_version": version("worker_version"),
        "input_protocol": reply["input_protocol"]
        if isinstance(reply.get("input_protocol"), int)
        and not isinstance(reply["input_protocol"], bool)
        and 0 <= reply["input_protocol"] <= 100 else "unknown",
        "native_attached": reply["native_attached"]
        if isinstance(reply.get("native_attached"), bool) else "unknown",
        "tab_state": {
            **({"visibility": tab_state["visibility"]}
               if isinstance(tab_state.get("visibility"), str)
               and tab_state["visibility"] in {"visible", "hidden", "prerender"} else {}),
            **({"has_focus": tab_state["has_focus"]}
               if isinstance(tab_state.get("has_focus"), bool) else {}),
        },
        "executor_version": version("executor_version"),
        "control_count": len(frame["controls"]) if isinstance(frame.get("controls"), list) else 0,
        "autocomplete": {**counts(autocomplete), "fields": fields},
    }


class ExtensionBrowserDecider(OpenAIBrowserDecider):
    """Keep the existing model adapter, accurately describe this executor's tools."""

    def decide(self, payload, timeout):
        focused = copy.deepcopy(payload)
        focused["browser_capabilities"] = {
            "adapter": "selected_tab_native_cdp",
            "scope": "selected top-level document; cross-origin frames unsupported",
            "observation": "dom",
            "input": "native_cdp",
            "keyboard": ["Enter", "Escape"],
            "screenshots": False,
            "events": "Browser-level mouse/keyboard input; read-back must verify its effect. Pause rather than repeat an unchanged action.",
        }
        return super().decide(focused, timeout)


class ExtensionBrowserTools(DOMBrowserTools):
    """Reuse collection/source checks, replacing only browser-bound operations."""

    def __init__(self, channel, control, values):
        super().__init__(
            None,
            channel.approved_origin,
            self._capture_page,
            lambda: not channel.cancel.is_set() and control.alive(),
            lambda: False,
            visual_enabled=False,
            user_pause=channel.pause_requested.is_set,
        )
        self.channel, self.control = channel, control
        self.scroll_steps = values.browser_scroll_steps
        self._url = safe_tab_url(channel.initial_url)
        self.document_token = None
        self.observation_diagnostics = {}

    @property
    def current_url(self):
        return self._url

    @property
    def current_document_id(self):
        if self.document_token is None:
            raise WebsiteError("Observe the selected tab before collecting source content.")
        return hashlib.sha256(
            (self._url + "\n" + self.document_token).encode("utf-8")
        ).hexdigest()

    def guard(self):
        self.channel.guard()
        if self.user_pause():
            raise WebsiteError("You paused the browser agent. Review the tab before resuming.")
        if origin(self._url) != self.approved_origin:
            raise WebsiteError("The selected tab moved to another website. Start a new run there.")

    def observe(self):
        self.guard()
        reply = self.channel.call("observe", {"focus": self.focus})
        if not isinstance(reply, dict):
            raise WebsiteError("The extension returned an invalid page observation.")
        self.observation_diagnostics = observation_diagnostics(reply)
        if reply.get("input_driver") != "native_cdp":
            diagnostics = self.observation_diagnostics
            raise WebsiteError(
                "Browser-level input readiness was not confirmed "
                f"(worker {diagnostics['worker_version']}, "
                f"executor {diagnostics['executor_version']}, driver {diagnostics['input']}). "
                "Reload Browser Companion 0.5.2, refresh the website and reconnect. "
                "No model decision ran from this observation."
            )
        url = safe_tab_url(reply.get("url", ""))
        token, frame = reply.get("document_token"), reply.get("frame")
        if (
            origin(url) != self.approved_origin
            or not isinstance(token, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,160}", token)
            or not isinstance(frame, dict)
            or not isinstance(frame.get("controls"), list)
            or len(frame["controls"]) > 140
        ):
            raise WebsiteError("The selected tab or its observation changed. Review it manually.")
        if (
            frame.get("manual_verification_required") or frame.get("access_restriction")
            or requires_manual_verification(frame.get("text", ""))
        ):
            raise WebsiteError(
                "Complete the website verification yourself, then press Resume. "
                "The agent cannot solve challenges or bypass an access denial."
            )
        snapshot, references = copy.deepcopy(frame), {}
        for item in snapshot["controls"]:
            if (
                not isinstance(item, dict)
                or not re.fullmatch(r"[0-9]{1,5}", str(item.get("id", "")))
            ):
                raise WebsiteError("The extension returned an invalid control reference.")
            local_id = str(item["id"])
            item["id"] = "0:" + local_id
            if item["id"] in references:
                raise WebsiteError("The extension returned duplicate control references.")
            if item.get("form_scope") is not None:
                item["form_scope"] = "0:form:" + str(item["form_scope"])
            item["option_ids"] = ["0:" + str(value) for value in item.get("option_ids", [])]
            if item.get("date_owner_id") is not None:
                owner_id = str(item["date_owner_id"])
                if not re.fullmatch(r"[0-9]{1,5}", owner_id):
                    raise WebsiteError("The extension returned an invalid calendar reference.")
                item["date_owner_id"] = "0:" + owner_id
            # Keep exact observed href privately for semantic action preflight;
            # the model receives only its query-free display form.
            references[item["id"]] = (None, local_id, copy.deepcopy(item))
            item["href"] = display_url(item["href"]) if item.get("href") else ""
        validation = snapshot.get("form_validation")
        if isinstance(validation, dict):
            by_id = {item["id"]: item for item in snapshot["controls"]}
            fields = validation.get("fields")
            validation["fields"] = []
            for field in (fields if isinstance(fields, list) else [])[:12]:
                public_id = "0:" + str(field.get("control_id")) if isinstance(field, dict) else ""
                if public_id in by_id:
                    validation["fields"].append({**field, "control_id": public_id,
                        "form_scope": by_id[public_id].get("form_scope")})
            alerts = validation.get("alerts")
            validation["alerts"] = []
            for alert in (alerts if isinstance(alerts, list) else [])[:4]:
                if not isinstance(alert, dict):
                    continue
                ids, scope = alert.get("control_ids"), str(alert.get("form_scope", ""))
                validation["alerts"].append({**alert,
                    "form_scope": "0:form:" + scope if re.fullmatch(r"[0-9]{1,5}", scope) else None,
                    "control_ids": ["0:" + str(i) for i in (ids if isinstance(ids, list) else [])
                                    if "0:" + str(i) in by_id]})
        self._url, self.document_token = url, token
        self.observed_url = url
        self.references = references
        if not self.navigation_stack or self.navigation_stack[-1] != url:
            self.navigation_stack = (self.navigation_stack + [url])[-20:]
        self.guard()
        return {
            "url": display_url(url),
            "document_id": self.current_document_id,
            "frames": [snapshot],
            "results": snapshot.get("results", {}),
            "stay_url_values": url_stay_values(url),
            "captured_urls": [display_url(page["url"]) for page in self.pages],
        }

    def _passive_wait(self, seconds):
        self.channel.cancel.wait(seconds)
        self.guard()

    def wait_for_results(self, observation, *, max_seconds=5):
        deadline, previous, stable = time.monotonic() + max_seconds, None, 0
        while True:
            self.guard()
            if any(frame.get("password_or_code_visible") for frame in observation["frames"]):
                return observation
            signature = (observation["document_id"], observation.get("results", {}).get("record_count"))
            stable = stable + 1 if signature == previous else 0
            if rendered_results_ready(observation) and stable >= 1 or time.monotonic() >= deadline:
                return observation
            previous = signature
            self._passive_wait(0.15)
            observation = self.observe()

    def settle_autocomplete(self, observation, pending, *, max_seconds=1.1):
        deadline, previous, stable = time.monotonic() + max_seconds, None, 0
        while True:
            self.guard()
            if any(frame.get("password_or_code_visible") for frame in observation["frames"]):
                return observation
            fields = bound_controls(pending["binding"], observation)
            if len(fields) != 1 or fields[0].get("value") != pending["value"]:
                return observation
            field = fields[0]
            option_ids = set(field.get("option_ids", []))
            options = [item for frame in observation["frames"] for item in frame["controls"]
                       if item.get("id") in option_ids]
            signature = tuple(tuple(item.get(key, "") for key in ("option_primary", "label", "text"))
                              for item in options)
            matching = any(str(item.get("option_primary", "")).casefold() == pending["value"].casefold()
                           for item in options)
            stable = stable + 1 if signature == previous else 0
            if signature and (signature != pending["before_options"] or matching) and stable >= 1:
                return observation
            previous = signature
            if time.monotonic() >= deadline:
                field["suggestions_pending"] = True
                return observation
            self._passive_wait(0.12)
            observation = self.observe()

    def viewport_image(self):
        raise WebsiteError(
            "Viewport screenshots are unavailable in selected-tab mode. "
            "This version uses visible page text and controls only."
        )

    def execute(self, decision):
        self.guard()
        if self.document_token is None:
            raise WebsiteError("Observe the selected tab before acting.")
        if decision.action == "inspect":
            if decision.value not in {"form", "dialog", "all"}:
                raise WebsiteError("Inspect focus must be form, dialog or all.")
            self.focus = decision.value
            return {"status": "inventory_focus_changed", "focus": self.focus}
        if decision.action == "capture":
            return self.capture(decision.value or "page")
        facts = {}
        if decision.action == "back":
            if len(self.navigation_stack) < 2:
                raise WebsiteError("No previously observed same-site page is available.")
            facts = {"previous_url": self.navigation_stack[-2]}
        elif decision.action not in {"wait", "scroll"}:
            reference = self.references.get(decision.control_id)
            if reference is None:
                raise WebsiteError("The selected control is stale. Observe before acting.")
            facts = copy.deepcopy(reference[2])
            if facts.get("href") and origin(facts["href"]) != self.approved_origin:
                raise WebsiteError("This link leaves the selected website; review it manually.")
        if decision.action == "press" and decision.value not in {"Enter", "Escape"}:
            raise WebsiteError(
                "Selected-tab mode supports browser-level Enter and Escape only. "
                "Use a visible option/button instead of a simulated keyboard sequence."
            )
        try:
            reply = self.channel.call("execute", {
                "decision": decision.model_dump(), "facts": facts,
                "document_token": self.document_token,
            })
        except ExtensionCommandError as exc:
            if exc.dispatched and exc.code in {
                "command_timeout", "delivery_unknown", "execution_failed",
                "origin_changed", "tab_closed", "permission_required",
                "session_changed", "payload_too_large", "access_restriction",
                "native_input_unavailable", "native_input_detached",
                "website_focus_required", "extension_update_required",
            }:
                # The existing runtime's browser-error path preserves an
                # attempted Search as outcome_unknown. A WebsiteError here
                # would incorrectly mark a potentially completed click as
                # not_dispatched. Reuse that contract without replaying it.
                if exc.code in {
                    "native_input_unavailable", "native_input_detached", "website_focus_required",
                    "extension_update_required",
                }:
                    raise PlaywrightError(
                        "Browser focus or native input was interrupted while processing this action. "
                        "Its outcome is unknown; inspect the tab before explicitly resuming. "
                        "No action was replayed."
                    ) from None
                raise PlaywrightError(
                    "Selected-tab action acknowledgement was lost. Its outcome is unknown; "
                    "inspect the tab before resuming. No action was replayed."
                ) from None
            raise
        if not isinstance(reply, dict) or reply.get("status") not in {
            "action_performed", "value_verified", "value_mismatch", "counter_verified",
            "counter_unconfirmed", "counter_step_observed", "waited", "scrolled",
            "returned_to_observed_page",
            "validation_blocked",
        }:
            raise PlaywrightError(
                "The extension did not confirm this action. Inspect the tab before resuming; "
                "an uncertain action is not automatically repeated."
            )
        if decision.action == "back":
            self.navigation_stack = self.navigation_stack[:-1]
        self.guard()
        return reply

    def _capture_page(self):
        self.guard()
        if self.document_token is None:
            raise WebsiteError("Observe the selected tab before capturing.")
        token, url = self.document_token, self._url
        reply = self.channel.call("capture", {
            "document_token": token, "scroll_steps": self.scroll_steps,
        }, timeout=45)
        self.guard()
        if (
            not isinstance(reply, dict) or reply.get("document_token") != token
            or safe_tab_url(reply.get("url", "")) != url
        ):
            raise WebsiteError("The selected document changed during capture. No source was retained.")
        try:
            captured = Capture.model_validate(reply.get("capture")).page()
        except ValidationError:
            raise WebsiteError("The extension source capture was invalid. No extraction ran.") from None
        if captured["url"] != clean_url(url) or origin(captured["url"]) != self.approved_origin:
            raise WebsiteError("The captured source does not match the selected document.")
        if requires_manual_verification(captured["text"]):
            raise WebsiteError("The captured page requires website verification. No extraction ran.")
        return captured


def read_extension(values, control, model_settings, channel):
    """Run/resume the existing agent; freeze sources for the normal review path."""
    if values.framework != "langgraph" or model_settings is None:
        raise WebsiteError("Selected-tab execution requires LangGraph and a configured API connection.")
    tools = ExtensionBrowserTools(channel, control, values)
    decider = ExtensionBrowserDecider(model_settings)

    def progress(report):
        control.set_agent_report({
            **report, "observation_diagnostics": copy.deepcopy(tools.observation_diagnostics),
        })

    agent = BrowserAgent(
        tools, decider, values.instructions, output_fields=values.output_fields,
        collection_goal_required=True, progress=progress,
    )
    try:
        while True:
            control.update("agent_running", "Observing and operating your selected browser tab.")
            report = agent.run()
            channel.guard()
            if report["status"] == "ready":
                pages = agent.captured_sources()
                checklist = report.get("task_checklist") or {}
                if pages or (
                    report.get("collection_outcome") == "empty_results"
                    and checklist.get("search_submitted")
                    and not checklist.get("search_response_pending")
                ):
                    break
                control.update("agent_paused", "No source content was captured. Review the selected tab.")
            else:
                control.update("agent_paused", report["guidance"])
            while True:
                action = channel.wait_for_resume()
                if action != "collect":
                    break
                tools.guard()
                pages = agent.captured_sources()
                if pages:
                    break
                control.update("agent_paused", "There are no retained sources to extract. Resume collection first.")
            if action == "collect" and pages:
                break
            if action != "resume":
                raise WebsiteError("Selected-tab workflow ended before source collection completed.")
        with control.lock:
            control.snapshot_frozen = True
            control.state = "reviewing"
            control.message = (
                "Selected-tab source snapshot captured. The browser tab stays open; "
                "extraction continues and the dashboard provides review and saving."
            )
        return copy.deepcopy(pages)
    finally:
        decider.close()
