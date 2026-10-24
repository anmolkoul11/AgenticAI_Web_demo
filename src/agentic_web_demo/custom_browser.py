"""Visible browser with default restricted or explicitly selected normal networking."""

import copy
import os
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from queue import Queue
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4

from openai import APIError
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright
from pydantic import ValidationError

from agentic_web_demo.authentication import assess_authentication, authentication_expired
from agentic_web_demo.browser_agent import (
    BrowserAgent,
    DOMBrowserTools,
    OpenAIBrowserDecider,
    safe_browser_diagnostics,
)
from agentic_web_demo.browser_links import approved_links, inspect_links, propose_links
from agentic_web_demo.browser_navigation import (
    execute_navigation,
    inspect_search_controls,
    observe_navigation_result,
    propose_navigation,
)
from agentic_web_demo.browser_proxy import GuardedProxy
from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_fetch import (
    USER_AGENT,
    WebsiteError,
    fetch,
    origin,
    public_url,
)
from agentic_web_demo.hotel_search import (
    HotelSearchDriver,
    prepare_hotel_search,
    run_hotel_search,
)

CAPTURE_GUIDANCE = {
    "insufficient_content": "Too little source content survived capture. Open relevant content "
    "or a loaded results page before trying again; no extraction call ran.",
    "page_changed": "The page changed during capture. Review the tab and retry capture once "
    "when it is stable; no extraction call ran.",
    "closed": "The browser or tab closed during capture. Start a new session.",
    "timeout": "Page capture timed out. Review the loaded page before another capture.",
    "invalid_capture": "Captured source structure was invalid. No data was sent for extraction.",
    "preparation_failed": "Content preparation failed before capture. Review the browser "
    "before trying again; no extraction call ran.",
    "collector_exception": "The source collector failed on this page. Review capture diagnostics; "
    "repeating model decisions cannot repair a collector error. No extraction call ran.",
}


class BrowserCaptureError(WebsiteError):
    """Safe collector failure facts, never raw DOM, URLs or credential exceptions."""

    def __init__(self, code, **facts):
        if code not in CAPTURE_GUIDANCE:
            raise ValueError("Unknown capture failure code")
        super().__init__(CAPTURE_GUIDANCE[code])
        self.code = code
        self.capture_diagnostics = {"code": code}
        if facts.get("phase") in {"prepare", "collect", "validate"}:
            self.capture_diagnostics["phase"] = facts["phase"]
        for key in ("block_count", "captured_text_chars", "main_status"):
            value = facts.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000:
                self.capture_diagnostics[key] = value


def capture_failure(error, phase="collect"):
    """Classify a driver error without exposing its message to the model or UI."""
    message = str(error).lower()
    code = (
        "insufficient_content"
        if "capture_insufficient_content" in message or "too little visible content" in message
        else "timeout"
        if isinstance(error, PlaywrightTimeout)
        else "closed"
        if "closed" in message or "crash" in message
        else "page_changed"
        if "execution context" in message or "detached" in message
        else "preparation_failed"
        if phase == "prepare"
        else "collector_exception"
    )
    return BrowserCaptureError(code, phase=phase)


def remember_capture_failure(control, error, stage="capture"):
    with control.lock:
        control.browser_error = {"stage": stage, **error.capture_diagnostics}


class BrowserControl:
    def __init__(self, alive=lambda: True):
        self.lock = threading.Lock()
        self.capture = threading.Event()
        self.cancel = threading.Event()
        self.review_open = threading.Event()
        self.close_requested = threading.Event()
        self.worker_closed = threading.Event()
        self.owner_thread = None
        self.on_closed = None
        self.snapshot_frozen = False
        self.alive = alive
        self.state = "starting"
        self.message = "Opening a dedicated Chromium window. No model call yet."
        self.blocked_origins = set()
        self.blocked_resources = {}
        self.blocked_main_navigation = None
        self.network_failures = {}
        self.navigation_requested = threading.Event()
        self.navigation_approved = threading.Event()
        self.navigation_plan = None
        self.navigation_controls = []
        self.navigation_page_url = None
        self.navigation_model = None
        self.link_requested = threading.Event()
        self.link_approved = threading.Event()
        self.link_selection = None
        self.link_candidates = []
        self.link_selected_ids = []
        self.link_page_url = None
        self.link_model = None
        self.section_hops = 0
        self.capture_failures = []
        self.page_health = {}
        self.browser_mode = "restricted"
        self.browser_channel = "chromium"
        self.content_preparation = {}
        self.link_coverage = {}
        self.browser_error = None
        self.navigation_result = None
        self.navigation_history = []
        self.authentication = {"status": "not_requested", "verified": False}
        self.resume_login_requested = threading.Event()
        self.hotel_requested = threading.Event()
        self.hotel_approved = threading.Event()
        self.hotel_plan = None
        self.hotel_page_url = None
        self.hotel_capture_after = False
        self.hotel_revision = None
        self.agent_requested = threading.Event()
        self.agent_report = None
        self.on_agent_diagnostics = None
        self.agent_visual_enabled = False
        self.agent_pause_requested = threading.Event()
        self.workflow_mode = "manual"
        self.automatic_start = "disabled"
        self.initial_agent_confirmed = False
        self.initial_agent_visual_confirmed = False
        self.initial_signin_required = False
        self.startup_timing = {}

    def configure_workflow(self, values):
        """Keep the initial authorization local to this browser/session control."""
        with self.lock:
            self.workflow_mode = values.workflow_mode
            self.automatic_start = "pending" if values.workflow_mode == "automatic" else "disabled"
            self.initial_agent_confirmed = values.agent_confirmed
            self.initial_agent_visual_confirmed = values.agent_visual_confirmed
            self.initial_signin_required = values.login_mode != "none"

    def maybe_auto_start(self):
        """Consume initial consent once, only after readiness and sign-in handoff."""
        if not self.alive():
            return False
        with self.lock:
            if (
                self.workflow_mode != "automatic"
                or self.automatic_start != "pending"
                or self.state != "waiting"
                or self.agent_report is not None
                or not self.initial_agent_confirmed
                or self.cancel.is_set()
                or self.authentication["status"]
                not in (
                    {"authenticated", "operator_confirmed"}
                    if self.initial_signin_required
                    else {"not_requested", "authenticated", "operator_confirmed"}
                )
            ):
                return False
            self.automatic_start = "starting"
            visual_confirmed = self.initial_agent_visual_confirmed
        # Use the same command validation as the manual agent button. Never hold
        # the control lock while invoking command or the caller's alive callback.
        try:
            self.command(
                "agent_start",
                agent_confirmed=True,
                agent_visual_confirmed=visual_confirmed,
                automatic_start_only=True,
            )
        except WebsiteError:
            # A simultaneous cancel/manual command wins; never re-arm initial consent.
            return False
        return True

    def update(self, state, message):
        with self.lock:
            self.state, self.message = state, message

    def snapshot(self):
        with self.lock:
            return {
                "state": self.state,
                "guidance": self.message,
                "inspection": {
                    "active": self.review_open.is_set() and not self.worker_closed.is_set(),
                    "snapshot_frozen": self.snapshot_frozen,
                },
                "blocked_origins": sorted(self.blocked_origins),
                "blocked_resources": [
                    {"origin": host, "type": kind, "count": count}
                    for (host, kind), count in sorted(self.blocked_resources.items())
                ],
                "blocked_main_navigation": self.blocked_main_navigation,
                "network_failures": [
                    {"origin": host, "type": kind, "count": count}
                    for (host, kind), count in sorted(self.network_failures.items())
                ],
                "navigation_plan": (
                    self.navigation_plan.model_dump() if self.navigation_plan else None
                ),
                "navigation_controls": [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "kind",
                            "type",
                            "label",
                            "options",
                            "frame_index",
                            "current_value",
                            "date_value",
                            "readonly",
                            "name",
                            "placeholder",
                            "purpose",
                            "form_kind",
                            "date_values",
                        )
                        if key in item
                    }
                    for item in self.navigation_controls
                ],
                "navigation_model": self.navigation_model,
                "hotel_plan": self.hotel_plan.model_dump() if self.hotel_plan else None,
                "hotel_capture_after": self.hotel_capture_after,
                "hotel_revision": self.hotel_revision,
                "agent_report": copy.deepcopy(self.agent_report),
                "workflow_mode": self.workflow_mode,
                "automatic_start": self.automatic_start,
                "startup_timing": dict(self.startup_timing),
                "navigation_result": copy.deepcopy(self.navigation_result),
                "navigation_history": copy.deepcopy(self.navigation_history),
                "browser_error": dict(self.browser_error) if self.browser_error else None,
                "authentication": dict(self.authentication),
                "link_selection": (
                    self.link_selection.model_dump() if self.link_selection else None
                ),
                "link_candidates": [
                    {
                        key: item[key]
                        for key in ("id", "title", "context", "url", "role_hint")
                        if key in item
                    }
                    for item in self.link_candidates
                    if self.link_selection and item["id"] in self.link_selection.selected_ids
                ],
                "link_model": self.link_model,
                "section_hops": self.section_hops,
                "capture_failures": list(self.capture_failures),
                "page_health": dict(self.page_health),
                "browser_mode": self.browser_mode,
                "browser_channel": self.browser_channel,
                "content_preparation": dict(self.content_preparation),
                "link_coverage": (
                    {
                        **self.link_coverage,
                        "links": [dict(item) for item in self.link_coverage.get("links", [])],
                    }
                    if self.link_coverage
                    else {}
                ),
            }

    def set_page_health(self, health):
        with self.lock:
            self.page_health = health

    def require_authentication(self, message, *, expired=False):
        with self.lock:
            self.authentication.update(
                status="reauthentication_required" if expired else "awaiting_user",
                verified=False,
                verification=None,
            )
            self.capture.clear()
            self.navigation_requested.clear()
            self.navigation_approved.clear()
            self.link_requested.clear()
            self.link_approved.clear()
            self.navigation_plan = None
            self.hotel_requested.clear()
            self.hotel_approved.clear()
            self.hotel_plan = None
            self.hotel_page_url = None
            self.hotel_capture_after = False
            self.hotel_revision = None
            self.agent_requested.clear()
            self.link_selection = None
            self.state, self.message = "authentication_pending", message

    def set_navigation_result(self, result):
        with self.lock:
            self.navigation_result = copy.deepcopy(result)
            if (
                result.get("execution_id")
                and self.navigation_history
                and self.navigation_history[-1].get("execution_id") == result["execution_id"]
            ):
                self.navigation_history[-1] = copy.deepcopy(result)
            else:
                self.navigation_history.append(copy.deepcopy(result))
            self.navigation_history = self.navigation_history[-20:]

    def set_agent_report(self, report):
        with self.lock:
            self.agent_report = copy.deepcopy(report)
            self.state = (
                "agent_paused"
                if report["status"] == "paused"
                else "agent_pausing"
                if self.agent_pause_requested.is_set()
                else "agent_running"
            )
            self.message = (
                "Pause requested. An in-flight model call may finish; no new action will run."
                if self.state == "agent_pausing"
                else report["guidance"]
            )
            callback = self.on_agent_diagnostics
            diagnostics = {
                key: copy.deepcopy(report.get(key))
                for key in (
                    "run_id",
                    "prompt_version",
                    "status",
                    "calls",
                    "decision_diagnostics",
                    "failure",
                )
            }
            if report.get("counter_diagnostics"):
                diagnostics["counter_diagnostics"] = copy.deepcopy(report["counter_diagnostics"])
            if isinstance(report.get("observation_diagnostics"), dict):
                diagnostics["observation_diagnostics"] = copy.deepcopy(report["observation_diagnostics"])
            checklist = report.get("task_checklist") or {}
            transition = checklist.get("search_transition") or {}
            if isinstance(transition, dict) and "attempted" in transition:
                diagnostics["search_transition"] = {
                    "attempted": transition.get("attempted") is True,
                    "confirmed": transition.get("confirmed") is True,
                    "response_pending": checklist.get("search_response_pending") is True,
                    "attempt_status": transition.get("attempt_status")
                    if transition.get("attempt_status")
                    in {"not_attempted", "attempted_unconfirmed", "transition_confirmed"}
                    else "unknown",
                    "dispatch_status": transition.get("dispatch_status")
                    if transition.get("dispatch_status")
                    in {
                        "not_attempted",
                        "attempted",
                        "action_completed",
                        "outcome_unknown",
                        "not_dispatched",
                    }
                    else "unknown",
                }
            browser_facts = safe_browser_diagnostics(report.get("browser_diagnostics"))
            if browser_facts:
                diagnostics["browser_diagnostics"] = browser_facts
                if report["status"] == "paused" and not browser_facts.get("recovered"):
                    self.browser_error = {
                        "stage": browser_facts["operation"],
                        **browser_facts,
                    }
                elif browser_facts.get("recovered"):
                    self.browser_error = None

            def counts(values, keys):
                return {
                    key: values[key]
                    for key in keys
                    if isinstance(values.get(key), (int, float))
                    and not isinstance(values[key], bool)
                    and 0 <= values[key] <= 100_000_000
                }

            if report.get("usage"):
                diagnostics["usage"] = counts(
                    report["usage"],
                    ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"),
                )
            performance = report.get("performance") or {}
            if performance:
                phases = ("observe", "context", "screenshot", "model", "action", "capture")
                diagnostics["performance"] = {
                    key: counts(performance.get(key) or {}, phases)
                    for key in ("phase_seconds", "phase_calls")
                }
                diagnostics["performance"]["navigation_context"] = [
                    {
                        **counts(item, ("call", "text_chars")),
                        "screenshot_sent": item.get("screenshot_sent") is True,
                        "section_chars": counts(
                            item.get("section_chars") or {},
                            ("observation", "task_checklist", "recent_actions"),
                        ),
                    }
                    for item in (performance.get("navigation_context") or [])[-30:]
                    if isinstance(item, dict)
                ]
        # Never acquire the service lock while holding the browser-control lock.
        if callback:
            callback(diagnostics)

    def blocked(self, remote, kind="other"):
        with self.lock:
            if len(self.blocked_origins) < 20:
                self.blocked_origins.add(remote)
            key = remote, kind
            if key in self.blocked_resources or len(self.blocked_resources) < 30:
                self.blocked_resources[key] = self.blocked_resources.get(key, 0) + 1

    def blocked_navigation(self, remote):
        with self.lock:
            self.blocked_main_navigation = remote

    def failed(self, remote, kind="other"):
        with self.lock:
            key = remote, kind
            if key in self.network_failures or len(self.network_failures) < 30:
                self.network_failures[key] = self.network_failures.get(key, 0) + 1

    def set_navigation(self, plan, controls, page_url, model):
        with self.lock:
            self.navigation_plan = plan
            self.navigation_controls = controls
            self.navigation_page_url = page_url
            self.navigation_model = model
            self.state = "navigation_review"
            self.message = "Review the proposed search actions in the dashboard. Nothing clicked."

    def set_links(self, selection, candidates, page_url, model):
        with self.lock:
            self.link_selection = selection
            self.link_candidates = candidates
            self.link_page_url = page_url
            self.link_model = model
            self.state = "link_review"
            self.message = "Review the proposed content links. No link has been opened."

    def set_hotel_plan(self, plan, page_url):
        with self.lock:
            self.hotel_plan, self.hotel_page_url = plan, page_url
            self.hotel_capture_after = False
            self.hotel_revision = uuid4().hex
            self.state = "hotel_review"
            self.message = (
                "Review the complete hotel search targets. Approval permits bounded "
                "form interactions and one Search submission, never a reservation or payment. "
                "Preparation used no model calls."
            )

    def command(
        self,
        action,
        selected_ids=None,
        *,
        hotel_revision=None,
        hotel_confirmed=False,
        agent_confirmed=False,
        agent_visual_confirmed=False,
        automatic_start_only=False,
    ):
        with self.lock:
            if action == "close":
                if not self.review_open.is_set():
                    raise WebsiteError("No captured verification browser is open.")
                self.close_requested.set()
                self.state = "review_closing"
                self.message = "Closing the verification browser. Captured results are unchanged."
            elif action == "cancel" and self.review_open.is_set():
                # Older clients may still label the button Cancel. Once the
                # snapshot is handed off, window closure must not cancel its
                # independent extraction/save job.
                self.close_requested.set()
                self.state = "review_closing"
                self.message = "Closing the verification browser. Captured results are unchanged."
            elif self.review_open.is_set():
                raise WebsiteError(
                    "This browser is open for verification only. Start a new run to collect again."
                )
            elif action == "cancel":
                self.cancel.set()
            elif action == "resume_login" and self.state == "authentication_pending":
                self.state = "checking_authentication"
                self.resume_login_requested.set()
            elif action == "capture" and self.state == "waiting":
                self.state = "capturing"
                self.capture.set()
            elif action in {"agent_start", "agent_resume"} and self.state in {
                "waiting",
                "agent_paused",
            }:
                if automatic_start_only and self.automatic_start != "starting":
                    raise WebsiteError("Initial automatic start was cancelled or taken over.")
                if not agent_confirmed:
                    raise WebsiteError("Authorize the paid browser-agent loop before running it.")
                if action == "agent_start" and self.agent_report is not None:
                    raise WebsiteError(
                        "This session already has an agent run. Resume it or start a new session."
                    )
                if action == "agent_resume" and self.agent_report is None:
                    raise WebsiteError("Start the browser agent before resuming it.")
                if self.cancel.is_set():
                    raise WebsiteError("Browser session cancelled. No agent start.")
                self.agent_pause_requested.clear()
                self.agent_visual_enabled = bool(agent_visual_confirmed)
                if self.workflow_mode == "automatic" and self.automatic_start in {
                    "pending",
                    "starting",
                }:
                    self.automatic_start = "started"
                self.state = "agent_running"
                self.message = (
                    "Starting the observe, decide, act and verify loop. "
                    "Paid API calls are authorized."
                )
                self.agent_requested.set()
            elif action == "agent_pause" and self.state == "agent_running":
                self.agent_pause_requested.set()
                self.state = "agent_pausing"
                self.message = (
                    "Pause requested. An in-flight model call may finish; no new action will run."
                )
            elif action == "agent_collect" and self.state == "agent_paused":
                if not agent_confirmed:
                    raise WebsiteError("Authorize extraction of the agent's captured pages first.")
                if not self.agent_report or not self.agent_report.get("captured_pages"):
                    raise WebsiteError("No agent captures are available yet.")
                self.state = "agent_collecting"
                self.agent_requested.set()
            elif action == "agent_manual" and self.state in {"waiting", "agent_paused"}:
                self.agent_requested.clear()
                self.automatic_start = "manual" if self.workflow_mode == "automatic" else "disabled"
                self.state = "waiting"
                self.message = (
                    "Agent paused. Continue manually or use the other collection options."
                )
            elif action == "hotel_plan" and self.state == "waiting":
                self.hotel_plan = None
                self.hotel_capture_after = False
                self.hotel_revision = None
                self.state = "hotel_preparing"
                self.message = (
                    "Reading the hotel request for a complete search review. No model call."
                )
                self.hotel_requested.set()
            elif action in {"hotel_approve", "hotel_extract"} and self.state == "hotel_review":
                if self.hotel_plan is None:
                    raise WebsiteError("Prepare a hotel search review first.")
                if (
                    not hotel_confirmed
                    or not hotel_revision
                    or hotel_revision != self.hotel_revision
                ):
                    raise WebsiteError("Confirm the current hotel search review before running it.")
                self.hotel_capture_after = action == "hotel_extract"
                self.state = "hotel_running"
                self.message = "Running the reviewed hotel form workflow. No extra planning calls."
                self.hotel_approved.set()
            elif action == "hotel_dismiss" and self.state == "hotel_review":
                self.hotel_plan = None
                self.hotel_page_url = None
                self.hotel_capture_after = False
                self.hotel_revision = None
                self.state = "waiting"
                self.message = "Hotel search review dismissed. No actions ran."
            elif action == "plan" and self.state == "waiting":
                self.state = "planning_navigation"
                self.message = "Inspecting visible search controls for one paid planning call."
                self.navigation_plan = None
                self.navigation_controls = []
                self.navigation_model = None
                self.navigation_requested.set()
            elif action == "approve" and self.state == "navigation_review":
                self.state = "navigating"
                self.message = "Running approved search actions in the original tab."
                self.navigation_approved.set()
            elif action == "dismiss" and self.state == "navigation_review":
                self.navigation_plan = None
                self.navigation_controls = []
                self.navigation_page_url = None
                self.navigation_model = None
                self.state = "waiting"
                self.message = "Search plan dismissed. Navigate manually or request a new plan."
            elif action == "discover" and self.state == "waiting":
                self.state = "discovering_links"
                self.message = "Inspecting visible links for one paid discovery call."
                self.link_selection = None
                self.link_candidates = []
                self.link_model = None
                self.link_requested.set()
            elif action == "approve_links" and self.state == "link_review":
                approved_links(selected_ids, self.link_selection, self.link_candidates)
                self.link_selected_ids = list(selected_ids)
                if self.link_selection.kind == "section":
                    self.state = "opening_section"
                    self.message = "Opening one approved section; no article extraction yet."
                else:
                    self.state = "capturing_articles"
                    self.message = "Opening approved pages and capturing source evidence."
                self.link_approved.set()
            elif action == "dismiss_links" and self.state == "link_review":
                self.link_selection = None
                self.link_candidates = []
                self.link_page_url = None
                self.link_model = None
                self.state = "waiting"
                self.message = "Article proposal dismissed. Navigate manually or capture this page."
            else:
                raise WebsiteError("The browser is not ready to capture. Check its current state.")
            if self.workflow_mode == "automatic" and action in {
                "capture",
                "hotel_plan",
                "hotel_approve",
                "hotel_extract",
                "hotel_dismiss",
                "plan",
                "approve",
                "dismiss",
                "discover",
                "approve_links",
                "dismiss_links",
            }:
                # Only a valid, accepted manual command consumes initial automation.
                # Review dismissal returning to waiting must not restart the agent.
                self.automatic_start = "manual"
                self.agent_requested.clear()


def capture_url(value, expected_origin):
    value = public_url(value)
    if expected_origin is not None and origin(value) != expected_origin:
        raise WebsiteError("Return to the approved website in the original browser tab.")
    return value


def safe_source_url(value):
    parts = urlsplit(value)
    # Authentication codes/tokens may appear in callback query strings and fragments.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def request_allowed(
    remote,
    approved,
    resources,
    verification,
    *,
    navigation,
    main_frame,
    method,
    locked_login=False,
    auth_origins=frozenset(),
):
    """Only user-approved identity origins can receive a login redirect or POST."""
    if not remote.startswith("https://") or remote not in {
        approved,
        *resources,
        *verification,
        *auth_origins,
    }:
        return False
    if locked_login and remote not in {approved, *auth_origins}:
        return False
    if navigation:
        if main_frame and remote not in {approved, *auth_origins}:
            return False
        if not main_frame and remote not in {approved, *verification, *auth_origins}:
            return False
    if method not in {"GET", "HEAD", "OPTIONS"}:
        return remote == approved or (method == "POST" and remote in {*verification, *auth_origins})
    return True


def access_challenge(text):
    # Heuristic, not proof of access authorization; inspect only the start of visible text.
    sample = " ".join(text.lower().split())[:2000]
    return any(
        marker in sample
        for marker in (
            "verify you are human",
            "checking your browser",
            "access denied",
            "complete the captcha",
            "unusual traffic",
            "please enable js and disable any ad blocker",
            "please enable javascript and disable any ad blocker",
        )
    )


VERIFICATION_GUIDANCE = (
    "Website verification or access restriction detected; extraction is paused. "
    "Complete any offered verification yourself in Chromium. No model call has run. "
    "If the site keeps denying access, cancel; this browser cannot bypass its restrictions."
)


def check_robots(url):
    _, status, _, body = fetch(origin(url) + "/robots.txt")
    robot = RobotFileParser()
    if status == 404:
        robot.parse([])
    elif status == 200:
        robot.parse(body.decode("utf-8", errors="replace").splitlines())
    else:
        raise WebsiteError(
            "Could not verify robots.txt for this page. Capture was not sent to the model."
        )
    if not robot.can_fetch(USER_AGENT, url):
        raise WebsiteError(
            "robots.txt disallows this reader on the current page. No model call was made."
        )


def automatic_login(page, login, expected_origin, permitted=lambda: True, *, normal_network=False):
    """Submit one credential flow, with identity-origin checks in restricted mode.

    Credentials never enter the model. A submit is not proof of authentication;
    the operator still reviews the resulting page before capture.
    """

    trusted_origins = (
        {expected_origin} if isinstance(expected_origin, str) else set(expected_origin)
    )

    def check_page():
        if not permitted() or not page.url.startswith("https://"):
            raise WebsiteError("Automatic sign-in was cancelled or left HTTPS.")
        if not normal_network and origin(page.url) not in trusted_origins:
            raise WebsiteError("Sign-in moved to an unapproved origin. Finish it manually.")

    def visible_one(selector):
        items = [
            item for item in page.locator(selector).all() if item.is_visible() and item.is_enabled()
        ]
        if len(items) > 1:
            raise WebsiteError("Login controls are ambiguous. Finish sign-in manually.")
        return items[0] if items else None

    def valid_field(item, field_type):
        if item is None:
            return False
        return item.evaluate(
            """(el, kind) => el.tagName === 'INPUT' &&
            (kind === 'username' ? ['text', 'email', 'tel'].includes(el.type) :
            el.type === 'password')""",
            field_type,
        )

    def open_visible_login_entry():
        """Click one unambiguous sign-in entry, never a model-selected control."""
        candidates = []
        unapproved = set()
        for item in page.locator("a, button").all()[:500]:
            if not item.is_visible() or not item.is_enabled():
                continue
            label = " ".join(
                (item.get_attribute("aria-label") or item.inner_text()).lower().split()
            )
            if label not in {"login", "log in", "sign in", "sign-in"}:
                continue
            href = item.get_attribute("href")
            if href is not None:
                destination = urljoin(page.url, href)
                try:
                    destination_origin = origin(destination)
                except WebsiteError:
                    continue
                if not destination.startswith("https://"):
                    continue
                if not normal_network and destination_origin not in trusted_origins:
                    unapproved.add(destination_origin)
                    continue
            candidates.append((item, label, href))
        if len(candidates) != 1:
            detail = (
                " Review this sign-in origin before a new session: " + ", ".join(sorted(unapproved))
                if unapproved
                else ""
            )
            entry = (
                "No unique sign-in entry" if normal_network else "No unique, trusted sign-in entry"
            )
            raise WebsiteError(f"{entry} is visible. Provide its URL or open it manually." + detail)
        item, label, href = candidates[0]
        identity = (page.url, label, href)
        if identity in opened_entries:
            raise WebsiteError("The sign-in entry did not reveal a login form. Finish manually.")
        opened_entries.add(identity)
        check_page()
        item.click(timeout=10000)

    opened_entries = set()

    def find_username():
        for attempt in range(2):
            for _ in range(40):
                check_page()
                field = visible_one(login.username_selector)
                if field is not None:
                    return field
                page.wait_for_timeout(250)
            if attempt == 0:
                open_visible_login_entry()
        raise WebsiteError("Sign-in entry opened, but no username field appeared. Finish manually.")

    def submit_step(field):
        check_page()
        button = visible_one(login.submit_selector)
        if button is None:
            raise WebsiteError("No unique login/continue button is visible. Finish manually.")
        # Do not submit credentials via native GET, even in normal-network mode.
        valid = field.evaluate(
            """(el, config) => {
                const {selector, trusted, normal} = config;
                const buttons = [...document.querySelectorAll(selector)].filter(b =>
                    b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden' &&
                    !b.disabled);
                if (buttons.length !== 1) return false;
                const b = buttons[0], f = el.form;
                if (!(b.tagName === 'BUTTON' && ['button', 'submit'].includes(b.type)) &&
                    !(b.tagName === 'INPUT' && ['button', 'submit'].includes(b.type)))
                    return false;
                if (!f) return !b.form;
                if (b.form !== f) return false;
                const action = b.getAttribute('formaction') || f.action;
                const method = b.getAttribute('formmethod') || f.method;
                const target = b.getAttribute('formtarget') || f.target;
                const destination = new URL(action, location.href);
                return destination.protocol === 'https:' &&
                    (normal || trusted.includes(destination.origin)) &&
                    (b.type === 'button' || method.toLowerCase() === 'post') &&
                    (!target || target === '_self');
            }""",
            {
                "selector": login.submit_selector,
                "trusted": sorted(trusted_origins),
                "normal": normal_network,
            },
        )
        if not valid:
            raise WebsiteError(
                "This login form is not a trusted-origin POST or supported JavaScript button. "
                "Finish sign-in manually."
            )
        check_page()
        button.click(timeout=10000)

    check_page()
    user = find_username()
    if login.method == "email_verification":
        if not valid_field(user, "username"):
            raise WebsiteError("No unique email field is visible. Finish sign-in manually.")
        user.fill(login.username.get_secret_value())
        if not user.evaluate("(el) => el.checkValidity()"):
            raise WebsiteError("The website rejected the email format. Check it before sign-in.")
        submit_step(user)
        # Exactly one email request. Codes/links are completed only by the account holder.
        return False
    password = visible_one(login.password_selector)
    if user is None or not valid_field(user, "username"):
        raise WebsiteError("No unique username/email field is visible. Finish sign-in manually.")
    if password is not None and not valid_field(password, "password"):
        raise WebsiteError("The visible password control is unsupported. Finish manually.")
    if password is not None:
        same_form = user.evaluate(
            """(el, selector) => {
                const matches = [...document.querySelectorAll(selector)].filter(p =>
                    p.getClientRects().length && !p.disabled);
                return matches.length === 1 && matches[0].form === el.form;
            }""",
            login.password_selector,
        )
        if not same_form:
            raise WebsiteError("Login fields belong to different forms. Finish manually.")
    check_page()
    user.fill(login.username.get_secret_value())
    if not user.evaluate("(el) => el.checkValidity()"):
        raise WebsiteError(
            "The website rejected the username/email field format. Check the value before sign-in."
        )
    if password is None:
        # Email-first sign-in: one continue click, then wait for a password field.
        submit_step(user)
        for _ in range(40):
            check_page()
            password = visible_one(login.password_selector)
            if password is not None:
                break
            page.wait_for_timeout(250)
        if password is None:
            raise WebsiteError(
                "Email step submitted, but no password field appeared. "
                "Complete any email link or identity-provider step manually."
            )
        if not valid_field(password, "password"):
            raise WebsiteError("The next password control is unsupported. Finish manually.")
    check_page()
    password.fill(login.password.get_secret_value())
    submit_step(password)
    if not login.success_selector:
        return False
    for _ in range(40):
        check_page()
        success = visible_one(login.success_selector)
        if success is not None:
            return True
        page.wait_for_timeout(250)
    raise WebsiteError(
        "Credentials were submitted, but the configured signed-in indicator did not appear. "
        "Inspect the browser before capture."
    )


EXTRACT_TEXT = """(limit) => {
    const root = document.body;
    if (!root) return {text: '', truncated: false};
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const parts = []; let size = 0, visited = 0, truncated = false, node;
    while ((node = walker.nextNode())) {
        if (++visited > 50000) { truncated = true; break; }
        const parent = node.parentElement;
        const excluded = 'script,style,noscript,template,form,input,textarea,select,' +
            '[contenteditable],[hidden],[aria-hidden="true"]';
        if (!parent || parent.closest(excluded)) continue;
        const style = getComputedStyle(parent);
        if (style.display === 'none' || style.visibility === 'hidden' ||
            !parent.getClientRects().length) continue;
        const value = node.textContent.replace(/\\s+/g, ' ').trim();
        if (!value) continue;
        if (size + value.length + 1 > limit) {
            parts.push(value.slice(0, Math.max(0, limit - size))); truncated = true; break;
        }
        parts.push(value); size += value.length + 1;
    }
    return {text: parts.join('\\n'), truncated};
}"""


PAGE_HEALTH = """() => ({
    ready_state: document.readyState,
    visible_text_chars: document.body?.innerText?.length || 0
})"""


def refresh_page_health(page, control, main_status):
    """Report bounded render indicators, never page text or form values."""
    health = page.evaluate(PAGE_HEALTH)
    control.set_page_health(
        {
            "ready_state": health["ready_state"],
            "visible_text_chars": min(health["visible_text_chars"], 1_000_000),
            "frame_count": len(page.frames),
            "main_status": main_status[0],
        }
    )


CONTENT_METRICS = """() => {
    const text = document.body?.innerText || '';
    const sample = text.slice(0, 6000) + text.slice(-6000);
    let signature = 0;
    for (let i = 0; i < sample.length; i++) signature = ((signature * 31) +
        sample.charCodeAt(i)) >>> 0;
    return {ready: document.readyState, chars: Math.min(text.length, 1000000),
        links: Math.min(document.querySelectorAll('a[href]').length, 10000), signature,
        height: Math.min(document.documentElement.scrollHeight, 10000000),
        at_end: scrollY + innerHeight >= document.documentElement.scrollHeight - 4};
}"""


def wait_for_initial_content(page):
    """Wait for useful DOM, not ads/media or a full load/network-idle event.

    This only gates initial operator handoff. Capture retains its separate
    bounded stability/scrolling checks, and the agent re-observes dynamic widgets.
    """
    try:
        page.wait_for_function(
            """() => ['interactive','complete'].includes(document.readyState) &&
            !!document.body && ((document.body.innerText || '').trim().length >= 80 ||
              [...document.querySelectorAll('input,button,[role="button"]')].some(e =>
                !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'))""",
            timeout=1500,
        )
        return "useful_dom_visible"
    except PlaywrightTimeout:
        return "readiness_pending"


def prepare_browser_content(page, control, scroll_steps=3):
    """Bounded stability sampling and scrolling, without clicks or model calls.

    This does not assert full app readiness. Virtualized/infinite content and
    closed shadow/iframe content may remain outside the final DOM snapshot.
    """
    original_url = page.url
    if page.locator('input[type="password"]:visible').count():
        raise WebsiteError("A password form is still visible. Finish login before collection.")
    position = page.evaluate("() => ({x: scrollX, y: scrollY})")

    def check():
        if control.cancel.is_set() or not control.alive():
            raise WebsiteError("Content collection cancelled before any model call.")
        if page.url != original_url:
            raise WebsiteError(
                "The page changed while preparing content. Review it before retrying."
            )

    def settle(samples):
        previous, stable, metrics = None, 0, {}
        for _ in range(samples):
            check()
            metrics = page.evaluate(CONTENT_METRICS)
            fingerprint = (
                metrics["chars"],
                metrics["links"],
                metrics["height"],
                metrics["signature"],
            )
            stable = stable + 1 if fingerprint == previous else 0
            previous = fingerprint
            if stable >= 2 and metrics["ready"] == "complete" and metrics["chars"] >= 80:
                return True, metrics
            page.wait_for_timeout(250)
        return False, metrics

    completed = 0
    try:
        settled, metrics = settle(12)
        if scroll_steps:
            check()
            page.evaluate("() => window.scrollTo(0, 0)")
            settled, metrics = settle(4)
        for _ in range(scroll_steps):
            if metrics.get("at_end"):
                break
            check()
            page.evaluate("() => window.scrollBy(0, Math.max(200, innerHeight * 0.85))")
            completed += 1
            settled, metrics = settle(4)
        at_end = bool(metrics.get("at_end"))
    finally:
        if not page.is_closed() and page.url == original_url:
            page.evaluate("p => window.scrollTo(p.x, p.y)", position)
    settled, _ = settle(4)
    result = {
        "scroll_steps": completed,
        "at_page_end": at_end,
        "content_settled": settled,
        "preparation": "bounded_browser",
    }
    with control.lock:
        control.content_preparation = result
    return result


def capture_rendered_page(page, approved, redactions, main_status, *, preparation=None):
    """Capture one current page after access checks; preserve per-page provenance."""
    current = capture_url(page.url, approved)
    if main_status[0] in {401, 403, 429}:
        raise WebsiteError(VERIFICATION_GUIDANCE)
    if page.locator('input[type="password"]:visible').count():
        raise WebsiteError("A password form is still visible. Finish login before capture.")
    if page.locator(
        'input[autocomplete="one-time-code"]:visible, input[name*="otp" i]:visible, '
        'input[name*="verification" i]:visible, input[name="code" i]:visible, '
        'input[id*="otp" i]:visible'
    ).count():
        raise WebsiteError(
            "A verification-code form is still visible. Finish sign-in "
            "in the original browser before capture."
        )
    script = (Path(__file__).parent / "dashboard" / "static" / "capture_dom.js").read_text(
        encoding="utf-8"
    )
    try:
        capture = page.evaluate("(" + script + ")", {})
    except PlaywrightError as exc:
        raise capture_failure(exc) from None
    if preparation and capture.get("coverage"):
        capture["coverage"].update(preparation)
    for secret in redactions:
        if secret:
            for block in capture["blocks"]:
                block["text"] = block["text"].replace(secret, "[redacted]")
                if block.get("href"):
                    block["href"] = block["href"].replace(secret, "redacted")
    if capture.get("coverage"):
        capture["coverage"]["captured_text_chars"] = sum(
            len(block["text"]) for block in capture["blocks"]
        )
    try:
        captured = Capture.model_validate(capture).page()
    except ValidationError:
        raise BrowserCaptureError("invalid_capture", phase="validate") from None
    if len(captured["text"].strip()) < 80:
        raise BrowserCaptureError(
            "insufficient_content",
            block_count=len(captured["blocks"]),
            captured_text_chars=len(captured["text"].strip()),
            main_status=main_status[0],
        )
    if access_challenge(captured["text"]):
        raise WebsiteError(VERIFICATION_GUIDANCE)
    check_robots(current)
    return captured


def collect_approved_details(
    page, control, selected, approved, redactions, main_status, scroll_steps=3
):
    """Retain the index before visiting reviewed links; disclose every attempt.

    Does not call a model. Cancellation aborts the entire collection. A failed
    detail does not delete the starting-page evidence or other successful pages.
    """
    if not selected or len(selected) > 5:
        raise WebsiteError("Select one to five reviewed detail links before collection.")
    preparation = prepare_browser_content(page, control, scroll_steps)
    index = capture_rendered_page(page, approved, redactions, main_status, preparation=preparation)
    index["source_kind"] = "index"
    pages, failures = [index], []
    links = [
        {"url": safe_source_url(item["url"]), "title": item["title"], "status": "pending"}
        for item in selected
    ]

    def publish_coverage():
        with control.lock:
            control.capture_failures = list(failures)
            control.link_coverage = {
                "index_url": index["url"],
                "index_retained": True,
                "approved": len(selected),
                "captured": len(pages) - 1,
                "failed": len(failures),
                "links": [dict(item) for item in links],
            }

    publish_coverage()
    for offset, item in enumerate(selected):
        if control.cancel.is_set() or not control.alive():
            raise WebsiteError("Linked-page collection cancelled. No extraction call was made.")
        url = item["url"]
        links[offset]["status"] = "opening"
        control.update(
            "opening_links",
            f"Starting page retained. Opening approved detail {offset + 1} of {len(selected)}.",
        )
        publish_coverage()
        try:
            check_robots(url)
            main_status[0] = None
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response is None or response.status >= 400:
                raise WebsiteError("Linked page denied access or did not load successfully.")
            main_status[0] = response.status
            try:
                page.wait_for_load_state("load", timeout=8000)
            except PlaywrightError:
                pass  # Report actual coverage rather than claiming full app readiness.
            preparation = prepare_browser_content(page, control, scroll_steps)
            detail = capture_rendered_page(
                page, approved, redactions, main_status, preparation=preparation
            )
            if any(previous["url"] == detail["url"] for previous in pages):
                raise WebsiteError(
                    "The detail link returned an already captured page. No duplicate capture kept."
                )
            detail.update(
                source_kind="detail",
                parent_url=index["url"],
                requested_url=safe_source_url(url),
            )
            pages.append(detail)
            links[offset].update(status="captured", source_url=detail["url"])
        except (WebsiteError, PlaywrightError, ValidationError) as exc:
            if control.cancel.is_set() or not control.alive():
                raise WebsiteError(
                    "Linked-page collection cancelled. No extraction call was made."
                ) from None
            reason = (
                str(exc) if isinstance(exc, WebsiteError) else "Detail navigation/capture failed."
            )
            failures.append({"url": safe_source_url(url), "reason": reason})
            links[offset].update(status="failed", reason=reason)
        publish_coverage()
    if control.cancel.is_set() or not control.alive():
        raise WebsiteError("Linked-page collection cancelled. No extraction call was made.")
    return pages


def browser_launch_options(values, proxy=None):
    """Normal mode deliberately installs no app proxy or networking flags."""
    options = {"headless": False, "chromium_sandbox": True}
    if values.browser_channel != "chromium":
        options["channel"] = values.browser_channel
    if values.browser_mode == "restricted":
        if proxy is None:
            raise WebsiteError("Restricted browser requires its network proxy.")
        options.update(
            proxy=proxy.settings,
            args=[
                "--disable-quic",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ],
        )
    return options


def browser_context_options(values):
    normal = values.browser_mode == "normal"
    return {
        "java_script_enabled": True,
        "service_workers": "allow" if normal else "block",
        "accept_downloads": normal,
        "permissions": [],
        "ignore_https_errors": False,
    }


def install_browser_guards(context, page, route, browser_mode):
    """Do not register request/WebSocket/popup handlers in normal mode."""
    if browser_mode == "normal":
        return
    context.route("**/*", route)
    context.route_web_socket("**/*", lambda socket_route: socket_route.close())
    context.on("page", lambda extra: extra.close() if extra != page else None)
    page.on("dialog", lambda dialog: dialog.dismiss())


def browser_error_message(control, error, stage):
    """Classify driver errors without exposing raw URLs, DOM, or credentials."""
    if isinstance(error, BrowserCaptureError):
        remember_capture_failure(control, error, stage)
        return str(error)
    text = str(error).lower()
    code = (
        "timeout"
        if isinstance(error, PlaywrightTimeout)
        else "closed"
        if "closed" in text or "crash" in text
        else "page_changed"
        if "execution context" in text or "detached" in text
        else "collector_script"
        if "evaluate" in text
        else "browser_operation"
    )
    with control.lock:
        control.browser_error = {"stage": stage, "code": code}
    if stage == "launch":
        return (
            "Browser launch failed. Check the selected browser installation and desktop access. "
            "No automatic engine fallback."
        )
    if code == "closed":
        return "The browser or tab closed during " + stage + ". Start a new session."
    if stage in {"capture", "linked_capture"}:
        return (
            "Page capture failed after the browser opened (" + code + "). "
            "Review the original tab and retry capture when the page is stable. "
            "No extraction model call ran for this capture."
        )
    return (
        "Browser operation failed during " + stage + " (" + code + "). "
        "Review the browser and start a new session if needed. No automatic retry."
    )


def _wait_for_browser_review(page, browser, proxy, control):
    """Pump the original owner thread without collecting or making model calls."""
    try:
        while (
            not control.close_requested.is_set()
            and not control.cancel.is_set()
            and control.alive()
            and browser.is_connected()
            and not page.is_closed()
            and not (proxy is not None and proxy.stopped.is_set())
        ):
            page.wait_for_timeout(250)
    except Exception:
        # Window closure, lost connection or logout cannot invalidate the
        # already handed-off snapshot. Resource cleanup stays with its owner.
        pass


def read_browser(values, control, model_settings=None):
    """Return one frozen capture while its tracked Playwright owner stays alive."""
    result = Queue(maxsize=1)
    handed_off = False

    def handoff(pages, page, browser, proxy):
        nonlocal handed_off, model_settings
        if handed_off:
            raise WebsiteError("This browser already supplied its captured snapshot.")
        frozen = copy.deepcopy(pages)
        with control.lock:
            control.snapshot_frozen = True
            control.review_open.set()
            control.state = "reviewing"
            control.message = (
                "Source snapshot captured. The browser stays open for you to verify it while "
                "extraction continues. Manual browsing does not update the captured results."
            )
        handed_off = True
        model_settings = None
        result.put(("captured", frozen))
        _wait_for_browser_review(page, browser, proxy, control)
        return pages

    def owner_closed():
        with control.lock:
            if control.worker_closed.is_set():
                return
            control.review_open.clear()
            control.state = "closed"
            control.message = (
                "Verification browser closed. Captured results are unchanged."
                if control.snapshot_frozen
                else "Browser session ended."
            )
            control.worker_closed.set()
            callback = control.on_closed
        if callback is not None:
            try:
                callback()
            except Exception:
                pass  # Registry cleanup must not hide the capture or its original failure.

    def own_browser():
        try:
            _read_browser_owned(values, control, model_settings, handoff=handoff)
            if not handed_off:
                raise WebsiteError("Browser session ended before a source snapshot was captured.")
        except BaseException as exc:
            # Even an owner-thread abort must release the waiting job. Never
            # serialize unexpected driver/abort text into a user-visible result.
            if not handed_off:
                error = (
                    WebsiteError(str(exc))
                    if isinstance(exc, WebsiteError)
                    else WebsiteError(
                        "Browser session could not complete. Inspect the browser configuration "
                        "before starting a new run. No automatic retry."
                    )
                )
                result.put(("error", error))
        finally:
            owner_closed()

    with control.lock:
        if control.owner_thread is not None:
            raise WebsiteError("This browser control already has an owner.")
        worker = threading.Thread(
            target=own_browser,
            name="demo-browser-" + uuid4().hex[:10],
            daemon=False,
        )
        control.owner_thread = worker
    try:
        worker.start()
    except Exception:
        owner_closed()
        raise WebsiteError("The browser worker could not start. No browser action ran.") from None
    kind, payload = result.get()
    if kind == "error":
        worker.join()
        raise payload
    return payload


def _read_browser_owned(values, control, model_settings=None, *, handoff):
    control.configure_workflow(values)
    target = values.urls[0]
    approved = origin(target)
    verification = set(values.verification_origins)
    login = values.login
    auth_origins = set(login.auth_origins) if login else set()
    allowed = {approved, *values.resource_origins, *verification, *auth_origins}
    normal_network = values.browser_mode == "normal"
    # Network mode is immutable for this run; it cannot be switched on a live context.
    with control.lock:
        control.browser_mode = values.browser_mode
        control.browser_channel = values.browser_channel
    redactions = (
        [
            login.username.get_secret_value(),
            login.password.get_secret_value() if login.password else "",
        ]
        if login
        else []
    )
    auth_requested = login is not None or (
        values.workflow_mode == "automatic" and values.login_mode == "manual"
    )
    auth_success_selector = login.success_selector if login else ""
    auth_method = login.method if login else "manual"
    agent = None  # Lives only in this browser worker; never serialized or shared between users.
    if auth_requested:
        with control.lock:
            control.authentication.update(status="signing_in", method=auth_method)
    # Inherited Playwright debugging can log fill() values. Disable it before driver startup.
    os.environ.pop("DEBUG", None)
    os.environ.pop("PWDEBUG", None)
    session_stage = "launch"
    startup_started = time.monotonic()

    def handoff_pages(pages, page, browser, proxy):
        nonlocal agent, login, model_settings
        # Collection is finished. Release credential/model references before
        # retaining the window, and never resume automation on this context.
        if agent is not None:
            try:
                agent.decider.close()
            except Exception:
                pass
            agent = None
        values.login = None
        login = None
        redactions.clear()
        model_settings = None
        return handoff(pages, page, browser, proxy)

    try:
        if control.cancel.is_set() or not control.alive():
            raise WebsiteError("Browser session cancelled before opening. No model call.")
        with (
            (
                nullcontext(None)
                if normal_network
                else GuardedProxy({urlsplit(item).hostname for item in allowed})
            ) as proxy,
            sync_playwright() as pw,
        ):
            browser = pw.chromium.launch(**browser_launch_options(values, proxy))
            with control.lock:
                control.startup_timing["launch_seconds"] = round(
                    time.monotonic() - startup_started, 3
                )
            session_stage = "session_setup"
            try:
                context = browser.new_context(**browser_context_options(values))
                context.set_default_timeout(10000)
                page = context.new_page()
                locked_login = [False]

                def route(request_route):
                    request = request_route.request
                    try:
                        # Never permit a site's JavaScript to put this password
                        # into a GET URL, even when the request stays on-site.
                        if (
                            request.method == "GET"
                            and len(redactions) > 1
                            and bool(redactions[1])
                            and redactions[1] in unquote(request.url)
                        ):
                            request_route.abort()
                            return
                        remote = origin(request.url)
                        navigation = request.is_navigation_request()
                        main_frame = request.frame == page.main_frame if navigation else False
                        # Missing frame information fails closed via the exception handler.
                        permit = request_allowed(
                            remote,
                            approved,
                            set(values.resource_origins),
                            verification,
                            navigation=navigation,
                            main_frame=main_frame,
                            method=request.method,
                            locked_login=locked_login[0],
                            auth_origins=auth_origins,
                        )
                        if permit:
                            request_route.continue_()
                        else:
                            if navigation and main_frame and remote != approved:
                                control.blocked_navigation(remote)
                            control.blocked(remote, request.resource_type)
                            request_route.abort()
                    except Exception:
                        request_route.abort()

                install_browser_guards(context, page, route, values.browser_mode)
                main_status = [None]

                def record_response(response):
                    try:
                        if (
                            response.request.is_navigation_request()
                            and response.request.frame == page.main_frame
                        ):
                            main_status[0] = response.status
                    except PlaywrightError:
                        pass

                page.on("response", record_response)

                def record_failure(request):
                    try:
                        control.failed(origin(request.url), request.resource_type)
                    except WebsiteError:
                        pass

                page.on("requestfailed", record_failure)
                start_url = login.url if login else target
                session_stage = "navigation"
                try:
                    navigation_started = time.monotonic()
                    response = page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                    navigation_seconds = time.monotonic() - navigation_started
                    readiness_started = time.monotonic()
                    readiness = wait_for_initial_content(page)
                    with control.lock:
                        control.startup_timing.update(
                            navigation_seconds=round(navigation_seconds, 3),
                            readiness_seconds=round(time.monotonic() - readiness_started, 3),
                            readiness=readiness,
                        )
                    if response is not None and response.status in {401, 403, 429}:
                        notice = VERIFICATION_GUIDANCE
                    else:
                        notice = (
                            "Website opened. The agent continues when the page and "
                            "any requested sign-in are ready."
                            if values.workflow_mode == "automatic"
                            else "No website sign-in selected. Navigate to the content, "
                            "then click Capture current page here."
                            if values.login_mode == "none"
                            else "Sign in if needed, navigate to the content, "
                            "then click Capture current page here."
                        )
                except PlaywrightError:
                    notice = (
                        "Navigation did not finish. Check the browser and "
                        "resource-origin settings, or cancel."
                    )
                try:
                    refresh_page_health(page, control, main_status)
                except PlaywrightError:
                    pass
                if login and main_status[0] not in {401, 403, 429}:
                    try:
                        locked_login[0] = True
                        verified = automatic_login(
                            page,
                            login,
                            {approved, *auth_origins},
                            lambda: not control.cancel.is_set() and control.alive(),
                            normal_network=normal_network,
                        )
                        with control.lock:
                            control.authentication["automatic_step_completed"] = True
                        notice = (
                            "Configured signed-in indicator appeared. Navigate to content "
                            "and review before capture."
                            if verified
                            else "One credential flow submitted. Verify sign-in in Chromium; "
                            "complete MFA manually, navigate to content, then capture."
                        )
                        if auth_method == "email_verification":
                            notice = (
                                "One email step submitted. Check your inbox and complete the "
                                "code or login link in this original browser. No automatic resend."
                            )
                    except WebsiteError as exc:
                        notice = f"Automatic sign-in stopped: {exc} No retry was attempted."
                    except PlaywrightError:
                        notice = (
                            "Automatic sign-in could not safely complete. No retry. "
                            "Finish manually in Chromium, then capture."
                        )
                    finally:
                        locked_login[0] = False
                        values.login = None
                        login = None
                notice = (
                    "Normal browser networking: no application origin/request filters. "
                    if normal_network
                    else "Restricted browser networking. "
                ) + notice
                control.update("waiting", notice)
                if auth_requested:
                    control.require_authentication(
                        notice + " Complete sign-in or any required verification in the original "
                        "browser. Return to the selected website, then click "
                        "'I completed sign-in — continue'. No inbox access or code storage."
                    )
                session_stage = "session"

                def agent_sources():
                    pages = agent.captured_sources() if agent else []
                    index = next((p for p in pages if p.get("source_kind") == "index"), None)
                    details = [p for p in pages if p.get("source_kind") == "detail"]
                    failed = [
                        {
                            "url": item["source_url"],
                            "reason": item.get("guidance", "Capture failed."),
                        }
                        for item in (agent.history if agent else [])
                        if item["action"] == "capture"
                        and item["status"] in {"not_completed", "outcome_unknown"}
                    ]
                    with control.lock:
                        control.capture_failures = failed
                        if index:
                            control.link_coverage = {
                                "index_url": index["url"],
                                "index_retained": True,
                                "approved": len(details) + len(failed),
                                "captured": len(details),
                                "failed": len(failed),
                                "collection_method": "browser_agent",
                                "links": [
                                    {
                                        "url": p["url"],
                                        "title": safe_source_url(p["url"]),
                                        "status": "captured",
                                        "source_url": p["url"],
                                    }
                                    for p in details
                                ]
                                + [dict(f, status="failed") for f in failed],
                            }
                    return pages

                deadline = time.monotonic() + 600
                next_inspection = 0
                while time.monotonic() < deadline:
                    if control.cancel.is_set() or not control.alive():
                        raise WebsiteError(
                            "Browser session cancelled or dashboard session expired. No model call."
                        )
                    if page.is_closed() or (proxy is not None and proxy.stopped.is_set()):
                        raise WebsiteError(
                            "Browser closed or network budget reached. No model call."
                        )
                    if control.resume_login_requested.is_set():
                        control.resume_login_requested.clear()
                        try:
                            result = assess_authentication(page, approved, auth_success_selector)
                            if control.cancel.is_set() or not control.alive():
                                raise WebsiteError("Sign-in confirmation cancelled.")
                            with control.lock:
                                control.authentication.update(result)
                            control.update(
                                "waiting",
                                "Signed-in indicator verified. Continue with search or capture."
                                if result["verified"]
                                else "You confirmed sign-in; the app has no independent signed-in "
                                "indicator. Review the account and content before capture.",
                            )
                        except (WebsiteError, PlaywrightError) as exc:
                            control.require_authentication(
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "Could not inspect authentication. "
                                "Review the tab and confirm again."
                            )
                    if auth_requested:
                        status = control.snapshot()["authentication"]["status"]
                        if status in {"authenticated", "operator_confirmed"}:
                            try:
                                expired = main_status[0] == 401 or authentication_expired(
                                    page, approved
                                )
                            except (PlaywrightError, WebsiteError):
                                expired = True
                            if expired:
                                control.require_authentication(
                                    "Sign-in may have expired or the page is still verifying. "
                                    "Complete it manually and confirm again. No automatic resend.",
                                    expired=True,
                                )
                        if control.snapshot()["state"] in {
                            "authentication_pending",
                            "checking_authentication",
                        }:
                            try:
                                refresh_page_health(page, control, main_status)
                            except PlaywrightError:
                                pass
                            page.wait_for_timeout(250)
                            continue  # No navigation/discovery/capture/model calls during handoff.
                    control.maybe_auto_start()
                    if control.agent_requested.is_set():
                        control.agent_requested.clear()
                        try:
                            if values.framework != "langgraph":
                                raise WebsiteError(
                                    "Browser-agent execution is implemented for LangGraph first. "
                                    "Use a new LangGraph session."
                                )
                            if model_settings is None or not values.instructions.strip():
                                raise WebsiteError(
                                    "Add the complete task and configure "
                                    "your account API key first."
                                )
                            if control.snapshot()["state"] == "agent_collecting":
                                pages = agent_sources()
                                if not pages:
                                    raise WebsiteError(
                                        "No source pages captured. "
                                        "Resume or use current-page extraction."
                                    )
                                control.update(
                                    "captured",
                                    "Using the agent's captured pages for the approved "
                                    "extraction. The browser will stay open for verification.",
                                )
                                return handoff_pages(pages, page, browser, proxy)
                            if agent is None:

                                def agent_capture():
                                    try:
                                        try:
                                            preparation = prepare_browser_content(
                                                page, control, values.browser_scroll_steps
                                            )
                                        except PlaywrightError as exc:
                                            raise capture_failure(exc, phase="prepare") from None
                                        return capture_rendered_page(
                                            page,
                                            None if normal_network else approved,
                                            redactions,
                                            main_status,
                                            preparation=preparation,
                                        )
                                    except BrowserCaptureError as exc:
                                        remember_capture_failure(control, exc)
                                        raise

                                tools = DOMBrowserTools(
                                    page,
                                    origin(page.url),
                                    agent_capture,
                                    permitted=lambda: (
                                        not control.cancel.is_set() and control.alive()
                                    ),
                                    restricted=lambda: (
                                        main_status[0] in {401, 403, 429}
                                        or access_challenge(
                                            page.evaluate(EXTRACT_TEXT, 3000)["text"]
                                        )
                                    ),
                                    secrets=redactions,
                                    visual_enabled=control.agent_visual_enabled,
                                    user_pause=lambda: control.agent_pause_requested.is_set(),
                                )
                                agent = BrowserAgent(
                                    tools,
                                    OpenAIBrowserDecider(model_settings),
                                    values.instructions,
                                    progress=control.set_agent_report,
                                    output_fields=values.output_fields,
                                    collection_goal_required=values.workflow_mode == "automatic",
                                )
                            agent.tools.visual_enabled = control.agent_visual_enabled
                            report = agent.run()
                            if control.cancel.is_set() or not control.alive():
                                raise WebsiteError(
                                    "Browser agent cancelled. No extraction request sent."
                                )
                            if report["status"] == "ready":
                                pages = agent_sources()
                                checklist = report.get("task_checklist") or {}
                                if (
                                    report.get("collection_outcome") == "empty_results"
                                    and checklist.get("search_submitted")
                                    and not checklist.get("search_response_pending")
                                ):
                                    control.update(
                                        "captured",
                                        "The confirmed search displayed no results. "
                                        "The browser stays open; no extraction call is needed.",
                                    )
                                    return handoff_pages(pages, page, browser, proxy)
                                if not pages:
                                    raise WebsiteError(
                                        "Agent finished without source captures. "
                                        "Review the browser."
                                    )
                                control.update(
                                    "captured",
                                    "Agent collected source content. The browser stays open; "
                                    "extraction and validation follow.",
                                )
                                return handoff_pages(pages, page, browser, proxy)
                            control.update("agent_paused", report["guidance"])
                        except (WebsiteError, PlaywrightError) as exc:
                            control.update(
                                "agent_paused",
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "Browser interaction failed. Inspect the tab before "
                                "resuming; no automatic retry.",
                            )
                    if control.navigation_requested.is_set():
                        control.navigation_requested.clear()
                        try:
                            if model_settings is None or not values.instructions.strip():
                                raise WebsiteError(
                                    "Add a search request and API key before planning navigation."
                                )
                            if main_status[0] in {403, 429} or access_challenge(
                                page.evaluate(EXTRACT_TEXT, 3000)["text"]
                            ):
                                control.update(
                                    "verification_required",
                                    "The site is restricting access. No navigation call was made.",
                                )
                            else:
                                try:
                                    page.wait_for_load_state("load", timeout=8000)
                                except PlaywrightError:
                                    pass
                                controls = inspect_search_controls(page)
                                if not controls:
                                    raise WebsiteError(
                                        "No visible supported search controls were found. "
                                        "Check page loading diagnostics, wait for the form, "
                                        "or search manually in Chromium. No model call was made."
                                    )
                                plan, metadata = propose_navigation(
                                    controls, values.instructions, model_settings
                                )
                                if not control.cancel.is_set() and control.alive():
                                    control.set_navigation(plan, controls, page.url, metadata)
                        except (WebsiteError, APIError, PlaywrightError, ValidationError) as exc:
                            detail = (
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "The model or browser could not plan this search. "
                                "No actions ran; the model request may have incurred usage."
                            )
                            control.update("waiting", detail)
                    if control.hotel_requested.is_set():
                        control.hotel_requested.clear()
                        try:
                            if main_status[0] in {403, 429} or access_challenge(
                                page.evaluate(EXTRACT_TEXT, 3000)["text"]
                            ):
                                raise WebsiteError(
                                    "Resolve the website access restriction "
                                    "before preparing a hotel search."
                                )
                            recipe = prepare_hotel_search(values.instructions)
                            control.set_hotel_plan(recipe, page.url)
                        except (WebsiteError, PlaywrightError) as exc:
                            control.update(
                                "waiting",
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "Could not inspect the hotel form. "
                                "No actions or model calls ran.",
                            )
                    if control.hotel_approved.is_set():
                        control.hotel_approved.clear()
                        with control.lock:
                            recipe, planned_url = control.hotel_plan, control.hotel_page_url
                            capture_after = control.hotel_capture_after
                        try:
                            if recipe is None or page.url != planned_url:
                                raise WebsiteError(
                                    "The page changed after the hotel review. "
                                    "Prepare a fresh review; no actions ran."
                                )
                            if capture_after and model_settings is None:
                                raise WebsiteError(
                                    "Configure the API connection before approving "
                                    "search and extraction."
                                )

                            def hotel_progress(report):
                                control.set_navigation_result(report)
                                control.update(
                                    "hotel_running",
                                    "Hotel search: "
                                    + report["stage"].replace("_", " ")
                                    + ". "
                                    + (
                                        "Search submitted; waiting for listing results."
                                        if report["submitted"]
                                        else "Applying reviewed fields; "
                                        "search is not yet completed."
                                    ),
                                )

                            driver = HotelSearchDriver(
                                page,
                                origin(planned_url),
                                permitted=lambda: not control.cancel.is_set() and control.alive(),
                                restricted=lambda: (
                                    main_status[0] in {403, 429}
                                    or access_challenge(page.evaluate(EXTRACT_TEXT, 3000)["text"])
                                ),
                            )
                            run_hotel_search(driver, recipe, on_progress=hotel_progress)
                            control.update(
                                "waiting",
                                "Hotel search submitted and listing elements appeared. "
                                "Price/rating filters remain for source-based extraction; "
                                "actual result criteria still need review.",
                            )
                            if capture_after:
                                control.capture.set()
                                control.update(
                                    "capturing",
                                    "Reviewed hotel search completed. Capturing listing results "
                                    "for the paid extraction you approved.",
                                )
                        except (WebsiteError, PlaywrightError) as exc:
                            if hasattr(exc, "navigation_result"):
                                control.set_navigation_result(exc.navigation_result)
                            control.update(
                                "waiting",
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "Hotel browser interaction failed. Inspect the tab; "
                                "no automatic retry or extraction.",
                            )
                        finally:
                            with control.lock:
                                control.hotel_plan = None
                                control.hotel_page_url = None
                                control.hotel_capture_after = False
                                control.hotel_revision = None
                    if control.link_requested.is_set():
                        control.link_requested.clear()
                        try:
                            if model_settings is None or not values.instructions.strip():
                                raise WebsiteError(
                                    "Describe the content and configure an API key first."
                                )
                            if main_status[0] in {403, 429} or access_challenge(
                                page.evaluate(EXTRACT_TEXT, 3000)["text"]
                            ):
                                raise WebsiteError(
                                    "The site is restricting access. No discovery call was made."
                                )
                            prepare_browser_content(page, control, values.browser_scroll_steps)
                            candidates = inspect_links(
                                page, origin(page.url) if normal_network else approved
                            )
                            selection, metadata = propose_links(
                                candidates,
                                values.instructions,
                                model_settings,
                                allow_section=control.snapshot()["section_hops"] < 2,
                            )
                            if not control.cancel.is_set() and control.alive():
                                control.set_links(selection, candidates, page.url, metadata)
                        except (WebsiteError, APIError, PlaywrightError, ValidationError) as exc:
                            detail = (
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "The model or browser could not discover content links. "
                                "No links opened; the model request may have incurred usage."
                            )
                            control.update("waiting", detail)
                    if control.navigation_approved.is_set():
                        control.navigation_approved.clear()
                        with control.lock:
                            plan = control.navigation_plan
                            controls = control.navigation_controls
                            planned_url = control.navigation_page_url
                        try:
                            if plan is None or page.url != planned_url:
                                raise WebsiteError(
                                    "The page changed since planning. No actions ran; "
                                    "request a new plan."
                                )
                            navigation_result = execute_navigation(
                                page,
                                plan,
                                controls,
                                origin(planned_url) if normal_network else approved,
                                permitted=lambda: not control.cancel.is_set() and control.alive(),
                                allow_origin_redirects=normal_network,
                                instructions=values.instructions,
                            )
                            control.set_navigation_result(
                                {
                                    key: value
                                    for key, value in navigation_result.items()
                                    if key != "before_page"
                                }
                            )
                            try:
                                page.wait_for_load_state("load", timeout=8000)
                            except PlaywrightError:
                                pass
                            page.wait_for_timeout(1000)
                            control.set_navigation_result(
                                observe_navigation_result(page, navigation_result)
                            )
                            capture_url(page.url, None if normal_network else approved)
                            try:
                                refresh_page_health(page, control, main_status)
                            except PlaywrightError:
                                pass
                            coverage_note = (
                                " Text search is discovery only; it has not applied "
                                "structured filters."
                                if plan.coverage == "text_search"
                                else (
                                    " These were intermediate form actions, not a completed "
                                    "search. Inspect newly visible controls and request another "
                                    "reviewed plan in this same browser session."
                                    if plan.coverage == "partial_form"
                                    else ""
                                )
                            )
                            pending = navigation_result.get("pending_fields", [])
                            if pending:
                                coverage_note += (
                                    " Still pending: "
                                    + ", ".join(field.replace("_", " ") for field in pending)
                                    + "."
                                )
                            if plan.missing_fields:
                                coverage_note += (
                                    " Add missing values to the request, cancel this browser "
                                    "and start a new session. "
                                    "This session retains its original request. Missing: "
                                    + ", ".join(
                                        field.replace("_", " ") for field in plan.missing_fields
                                    )
                                    + "."
                                )
                            control.update(
                                "waiting",
                                "Reviewed actions ran; entered values were read back where "
                                "possible. Result filters are not yet verified. Inspect the "
                                "navigation evidence and rendered results before capture."
                                + coverage_note,
                            )
                        except (WebsiteError, PlaywrightError) as exc:
                            if hasattr(exc, "navigation_result"):
                                control.set_navigation_result(exc.navigation_result)
                            detail = (
                                str(exc)
                                if isinstance(exc, WebsiteError)
                                else "A search control changed or timed out. "
                                "No further actions ran."
                            )
                            control.update("waiting", detail)
                        finally:
                            with control.lock:
                                control.navigation_plan = None
                                control.navigation_controls = []
                                control.navigation_page_url = None
                    if control.link_approved.is_set():
                        control.link_approved.clear()
                        with control.lock:
                            selection = control.link_selection
                            candidates = list(control.link_candidates)
                            selected_ids = list(control.link_selected_ids)
                            planned_url = control.link_page_url
                        try:
                            if page.url != planned_url:
                                raise WebsiteError(
                                    "The page changed since link discovery. "
                                    "No linked pages opened; request a new proposal."
                                )
                            selected = approved_links(selected_ids, selection, candidates)
                            if selection.kind == "section":
                                if control.snapshot()["section_hops"] >= 2:
                                    raise WebsiteError(
                                        "Section navigation limit reached. Select detail links."
                                    )
                                if control.cancel.is_set() or not control.alive():
                                    raise WebsiteError("Section navigation cancelled.")
                                url = selected[0]["url"]
                                check_robots(url)
                                main_status[0] = None
                                response = page.goto(
                                    url, wait_until="domcontentloaded", timeout=30000
                                )
                                if response is None or response.status in {401, 403, 429}:
                                    raise WebsiteError(
                                        "Section page denied access or did not load."
                                    )
                                capture_url(page.url, None if normal_network else approved)
                                try:
                                    page.wait_for_load_state("load", timeout=8000)
                                except PlaywrightError:
                                    pass
                                try:
                                    refresh_page_health(page, control, main_status)
                                except PlaywrightError:
                                    pass
                                with control.lock:
                                    control.section_hops += 1
                                control.update(
                                    "waiting",
                                    "Approved section opened. Inspect the rendered page, "
                                    "then suggest relevant links again. No extraction ran.",
                                )
                                continue
                            pages = collect_approved_details(
                                page,
                                control,
                                selected,
                                None if normal_network else approved,
                                redactions,
                                main_status,
                                values.browser_scroll_steps,
                            )
                            coverage = control.snapshot()["link_coverage"]
                            control.update(
                                "captured",
                                f"Starting page retained; {coverage['captured']} detail pages "
                                f"captured, {coverage['failed']} failed. "
                                "The browser stays open for verification.",
                            )
                            return handoff_pages(pages, page, browser, proxy)
                        except WebsiteError as exc:
                            if isinstance(exc, BrowserCaptureError):
                                remember_capture_failure(control, exc)
                            control.update("waiting", str(exc))
                        except (PlaywrightError, ValidationError) as exc:
                            detail = (
                                browser_error_message(control, exc, "linked_capture")
                                if isinstance(exc, PlaywrightError)
                                else "Captured page structure was invalid. "
                                "Review the page and retry."
                            )
                            control.update("waiting", detail)
                        finally:
                            with control.lock:
                                control.link_selection = None
                                control.link_candidates = []
                                control.link_selected_ids = []
                                control.link_page_url = None
                    if time.monotonic() >= next_inspection:
                        next_inspection = time.monotonic() + 2
                        try:
                            refresh_page_health(page, control, main_status)
                            visible = page.evaluate(EXTRACT_TEXT, 3000)["text"]
                            restricted = main_status[0] in {403, 429} or access_challenge(visible)
                            state = control.snapshot()["state"]
                            if restricted and state in {"waiting", "verification_required"}:
                                control.update("verification_required", VERIFICATION_GUIDANCE)
                            elif not restricted and state == "verification_required":
                                control.update(
                                    "waiting",
                                    "Verification page cleared. Review the content "
                                    "in Chromium before capture.",
                                )
                        except PlaywrightError:
                            pass  # Navigation in progress; do not change the current state.
                    if control.capture.is_set():
                        control.capture.clear()
                        try:
                            preparation = prepare_browser_content(
                                page, control, values.browser_scroll_steps
                            )
                            captured = capture_rendered_page(
                                page,
                                None if normal_network else approved,
                                redactions,
                                main_status,
                                preparation=preparation,
                            )
                            control.update(
                                "captured",
                                "Content captured. The browser stays open during model extraction.",
                            )
                            return handoff_pages([captured], page, browser, proxy)
                        except WebsiteError as exc:
                            if isinstance(exc, BrowserCaptureError):
                                remember_capture_failure(control, exc)
                            control.update("waiting", str(exc))
                        except (PlaywrightError, ValidationError) as exc:
                            detail = (
                                browser_error_message(control, exc, "capture")
                                if isinstance(exc, PlaywrightError)
                                else "Captured page structure was invalid. "
                                "Review the page and retry."
                            )
                            control.update("waiting", detail)
                    page.wait_for_timeout(250)
                report = control.snapshot().get("agent_report") or {}
                detail = (
                    "The agent was paused: " + report["guidance"][:400]
                    if report.get("status") == "paused" and report.get("guidance")
                    else "Check action evidence for any model calls already attempted."
                )
                browser_facts = safe_browser_diagnostics(report.get("browser_diagnostics"))
                if browser_facts and not browser_facts.get("recovered"):
                    detail += (
                        " Browser diagnostic: "
                        + browser_facts["code"]
                        + " during "
                        + browser_facts["operation"]
                        + ". No repeat Search was attempted."
                    )
                raise WebsiteError("The ten-minute browser session expired. " + detail)
            finally:
                try:
                    browser.close()
                except PlaywrightError:
                    pass  # Cleanup must not hide a completed capture or the original failure.
    except PlaywrightError as exc:
        raise WebsiteError(browser_error_message(control, exc, session_stage)) from None
    finally:
        if agent is not None:
            try:
                agent.decider.close()
            except Exception:
                pass  # Client cleanup must not hide captured data or the original failure.
        values.login = None
        redactions.clear()
