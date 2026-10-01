"""Visible browser with default restricted or explicitly selected normal networking."""

import os
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from openai import APIError
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pydantic import ValidationError

from agentic_web_demo.browser_links import approved_links, inspect_links, propose_links
from agentic_web_demo.browser_navigation import (
    execute_navigation,
    inspect_search_controls,
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


class BrowserControl:
    def __init__(self, alive=lambda: True):
        self.lock = threading.Lock()
        self.capture = threading.Event()
        self.cancel = threading.Event()
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

    def update(self, state, message):
        with self.lock:
            self.state, self.message = state, message

    def snapshot(self):
        with self.lock:
            return {
                "state": self.state,
                "guidance": self.message,
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
                        for key in ("id", "kind", "type", "label", "options", "frame_index")
                        if key in item
                    }
                    for item in self.navigation_controls
                ],
                "navigation_model": self.navigation_model,
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
            }

    def set_page_health(self, health):
        with self.lock:
            self.page_health = health

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

    def command(self, action, selected_ids=None):
        with self.lock:
            if action == "cancel":
                self.cancel.set()
            elif action == "capture" and self.state == "waiting":
                self.state = "capturing"
                self.capture.set()
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


def capture_rendered_page(page, approved, redactions, main_status):
    """Capture one current page after access checks; preserve per-page provenance."""
    current = capture_url(page.url, approved)
    if main_status[0] in {403, 429}:
        raise WebsiteError(VERIFICATION_GUIDANCE)
    if page.locator('input[type="password"]:visible').count():
        raise WebsiteError("A password form is still visible. Finish login before capture.")
    script = (Path(__file__).parent / "dashboard" / "static" / "capture_dom.js").read_text(
        encoding="utf-8"
    )
    capture = page.evaluate("(" + script + ")")
    for secret in redactions:
        if secret:
            for block in capture["blocks"]:
                block["text"] = block["text"].replace(secret, "[redacted]")
                if block.get("href"):
                    block["href"] = block["href"].replace(secret, "redacted")
    captured = Capture.model_validate(capture).page()
    if len(captured["text"].strip()) < 80:
        raise WebsiteError("Too little text. Navigate to content before capture.")
    if access_challenge(captured["text"]):
        raise WebsiteError(VERIFICATION_GUIDANCE)
    check_robots(current)
    return captured


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


def read_browser(values, control, model_settings=None):
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
        [login.username.get_secret_value(), login.password.get_secret_value()] if login else []
    )
    # Inherited Playwright debugging can log fill() values. Disable it before driver startup.
    os.environ.pop("DEBUG", None)
    os.environ.pop("PWDEBUG", None)
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
                try:
                    response = page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_load_state("load", timeout=8000)
                    except PlaywrightError:
                        # Some sites keep loading ads/analytics; the operator can
                        # inspect the page and request planning when it settles.
                        pass
                    if response is not None and response.status in {401, 403, 429}:
                        notice = VERIFICATION_GUIDANCE
                    else:
                        notice = (
                            "No website sign-in selected. Navigate to the content, "
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
                        notice = (
                            "Configured signed-in indicator appeared. Navigate to content "
                            "and review before capture."
                            if verified
                            else "One credential flow submitted. Verify sign-in in Chromium; "
                            "complete MFA manually, navigate to content, then capture."
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
                            execute_navigation(
                                page,
                                plan,
                                controls,
                                origin(planned_url) if normal_network else approved,
                                permitted=lambda: not control.cancel.is_set() and control.alive(),
                                allow_origin_redirects=normal_network,
                            )
                            try:
                                page.wait_for_load_state("load", timeout=8000)
                            except PlaywrightError:
                                pass
                            page.wait_for_timeout(1000)
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
                                    "reviewed plan."
                                    if plan.coverage == "partial_form"
                                    else ""
                                )
                            )
                            control.update(
                                "waiting",
                                "Approved search actions ran. Wait for visible results and "
                                "inspect the page before capture." + coverage_note,
                            )
                        except (WebsiteError, PlaywrightError) as exc:
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
                        pages, failures = [], []
                        try:
                            if page.url != planned_url:
                                raise WebsiteError(
                                    "The page changed since article discovery. "
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
                            for item in selected:
                                if control.cancel.is_set() or not control.alive():
                                    raise WebsiteError(
                                        "Linked-page capture cancelled. "
                                        "No extraction call was made."
                                    )
                                url = item["url"]
                                try:
                                    check_robots(url)
                                    main_status[0] = None
                                    response = page.goto(
                                        url, wait_until="domcontentloaded", timeout=30000
                                    )
                                    if response is None or response.status in {401, 403, 429}:
                                        raise WebsiteError(
                                            "Linked page denied access or did not load."
                                        )
                                    try:
                                        page.wait_for_load_state("load", timeout=8000)
                                    except PlaywrightError:
                                        # Some sites keep analytics or media requests open.
                                        # Capture the currently rendered page and disclose
                                        # its coverage instead of claiming a full load.
                                        pass
                                    page.wait_for_timeout(600)
                                    pages.append(
                                        capture_rendered_page(
                                            page,
                                            None if normal_network else approved,
                                            redactions,
                                            main_status,
                                        )
                                    )
                                except (WebsiteError, PlaywrightError, ValidationError) as exc:
                                    failures.append(
                                        {
                                            "url": safe_source_url(url),
                                            "reason": (
                                                str(exc)
                                                if isinstance(exc, WebsiteError)
                                                else "Article navigation or capture failed."
                                            ),
                                        }
                                    )
                            if pages:
                                with control.lock:
                                    control.capture_failures = failures
                                control.update(
                                    "captured",
                                    f"Captured {len(pages)} approved pages; "
                                    f"{len(failures)} failed. Chromium is closing.",
                                )
                                return pages
                            control.update(
                                "waiting",
                                "No approved linked pages could be captured. "
                                "Inspect the browser or choose another source.",
                            )
                        except WebsiteError as exc:
                            control.update("waiting", str(exc))
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
                            captured = capture_rendered_page(
                                page,
                                None if normal_network else approved,
                                redactions,
                                main_status,
                            )
                            control.update(
                                "captured",
                                "Content captured. Chromium is closing before model extraction.",
                            )
                            return [captured]
                        except WebsiteError as exc:
                            control.update("waiting", str(exc))
                    page.wait_for_timeout(250)
                raise WebsiteError(
                    "The ten-minute browser session expired. No model call was made."
                )
            finally:
                browser.close()
    except PlaywrightError:
        engine = {
            "chromium": "Bundled Chromium",
            "chrome": "Google Chrome",
            "msedge": "Microsoft Edge",
        }[values.browser_channel]
        raise WebsiteError(
            f"{engine} could not complete this session. Check that the selected browser "
            "is installed and desktop access is available. No automatic retry or engine fallback."
        ) from None
    finally:
        values.login = None
        redactions.clear()
