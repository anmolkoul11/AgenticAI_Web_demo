"""Session-bound, one-shot commands to one explicitly selected browser tab.

No socket, CORS endpoint, browser-cookie reader or provider credential is exposed.
The signed-in dashboard remains the same-origin relay. A dispatched action is
never replayed by polling, even if its acknowledgement is lost.
"""

import hashlib
import json
import math
import threading
import time
from uuid import uuid4

from agentic_web_demo.capture import clean_url
from agentic_web_demo.custom_fetch import WebsiteError, origin

OPERATIONS = frozenset({"observe", "execute", "capture", "viewport_image"})
ERROR_CODES = frozenset({
    "stale_document", "control_changed", "unsupported", "access_restriction",
    "permission_required", "tab_closed", "origin_changed", "delivery_unknown",
    "execution_failed", "payload_too_large", "session_changed", "cancelled",
    "command_timeout",
})
RUN_TTL = 900


class ExtensionCommandError(WebsiteError):
    """Safe delivery facts; a claimed command may already have affected the page."""

    def __init__(self, message, *, code, dispatched):
        super().__init__(message)
        self.code, self.dispatched = code, bool(dispatched)


def bounded_json(value, *, maximum=400_000):
    """Reject deep/non-JSON packets before adapters inspect their contents."""
    nodes = 0

    def walk(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 18 or nodes > 30_000:
            raise ValueError("Extension packet exceeds structural limits")
        if item is None or isinstance(item, (bool, int, str)):
            if isinstance(item, str) and len(item) > maximum:
                raise ValueError("Extension packet string too large")
            return
        if isinstance(item, float) and math.isfinite(item):
            return
        if isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for key, child in item.items():
                if len(key) > 160:
                    raise ValueError("Extension packet key too large")
                walk(child, depth + 1)
            return
        raise ValueError("Extension packet is not JSON")

    walk(value)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode()
    if len(encoded) > maximum:
        raise ValueError("Extension packet exceeds byte limit")
    return encoded


class ExtensionChannel:
    def __init__(self, *, tab_id, url, control, alive, clock=time.monotonic):
        self.tab_id = tab_id
        self.initial_url = clean_url(url)
        self.approved_origin = origin(self.initial_url)
        self.control, self.alive, self.clock = control, alive, clock
        self.cancel = control.cancel
        self.pause_requested = control.agent_pause_requested
        self.run_id = uuid4().hex
        self.created = clock()
        self.condition = threading.Condition()
        self.pending = None
        self.last_ack = None
        self.resume_action = None

    def guard(self):
        if self.cancel.is_set() or not self.alive() or self.clock() - self.created > RUN_TTL:
            self.stop()
            raise WebsiteError("Extension workflow cancelled or expired. The website tab stays open.")

    def stop(self):
        self.cancel.set()
        with self.condition:
            self.condition.notify_all()

    def call(self, operation, payload=None, timeout=30):
        self.guard()
        if operation not in OPERATIONS:
            raise WebsiteError("Unsupported extension operation.")
        packet = payload or {}
        bounded_json(packet, maximum=32_000)
        if operation == "viewport_image":
            raise WebsiteError("Viewport images are not supported by the first extension workflow.")
        timeout = min(max(float(timeout), 0.01), 60)
        deadline = self.clock() + timeout
        command = {
            "request_id": uuid4().hex, "operation": operation, "payload": packet,
            "claimed": False, "ack": None,
        }
        with self.condition:
            if self.pause_requested.is_set():
                raise WebsiteError("The extension agent is paused. Review the selected tab before resuming.")
            if self.pending is not None:
                raise WebsiteError("Another extension command is still outstanding.")
            self.pending = command
            try:
                while command["ack"] is None:
                    self.guard()
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        self.pause_requested.set()
                        raise ExtensionCommandError(
                            "The extension did not confirm the command. Its outcome is unknown; "
                            "it was not replayed. Inspect the tab before resuming.",
                            code="command_timeout", dispatched=command["claimed"],
                        )
                    self.condition.wait(min(remaining, 0.25))
                ack = command["ack"]
                if not ack["ok"]:
                    code = ack["error"]
                    if code in {"access_restriction", "permission_required"}:
                        raise ExtensionCommandError(
                            "The website requires your attention or verification. "
                            "Complete it in the selected tab, then resume manually.",
                            code=code, dispatched=command["claimed"],
                        )
                    raise ExtensionCommandError(
                        f"Extension operation stopped ({code}). Inspect the selected tab before resuming.",
                        code=code, dispatched=command["claimed"],
                    )
                return ack["result"]
            finally:
                if self.pending is command:
                    self.pending = None

    def claim(self):
        self.guard()
        with self.condition:
            if self.pause_requested.is_set():
                return None
            command = self.pending
            if command is None or command["claimed"] or command["ack"] is not None:
                return None
            command["claimed"] = True
            return {key: command[key] for key in ("request_id", "operation", "payload")}

    def acknowledge(self, request_id, *, ok, result=None, error=None):
        self.guard()
        if not isinstance(ok, bool) or (ok and not isinstance(result, dict)):
            raise ValueError("Invalid extension acknowledgement")
        if not ok and error not in ERROR_CODES:
            raise ValueError("Unknown extension error code")
        ack = {"ok": ok, "result": result if ok else None, "error": None if ok else error}
        fingerprint = hashlib.sha256(bounded_json(ack)).hexdigest()
        with self.condition:
            if self.last_ack and self.last_ack[0] == request_id:
                if self.last_ack[1] != fingerprint:
                    raise ValueError("Conflicting duplicate acknowledgement")
                return "already_acknowledged"
            command = self.pending
            if (
                command is None or command["request_id"] != request_id
                or not command["claimed"] or command["ack"] is not None
            ):
                raise ValueError("No matching dispatched command")
            command["ack"] = ack
            self.last_ack = (request_id, fingerprint)
            self.condition.notify_all()
            return "acknowledged"

    def request_control(self, action):
        self.guard()
        with self.condition:
            if action == "cancel":
                self.stop()
                self.control.update("cancelled", "Extension workflow cancelled. The website tab stays open.")
            elif action == "pause":
                self.pause_requested.set()
                if self.pending and not self.pending["claimed"]:
                    self.pending["ack"] = {"ok": False, "result": None, "error": "cancelled"}
                if self.control.snapshot()["state"] != "agent_paused":
                    self.control.update("agent_pausing", "Pausing after the current decision or action. No new action will be dispatched.")
            elif action in {"resume", "collect"}:
                if self.control.snapshot()["state"] != "agent_paused":
                    raise ValueError("The extension agent is not paused")
                self.pause_requested.clear()
                self.resume_action = action
                self.control.update("agent_running", "Resuming from a fresh page observation.")
            else:
                raise ValueError("Unsupported extension control")
            self.condition.notify_all()

    def wait_for_resume(self):
        with self.condition:
            while self.resume_action is None:
                self.guard()
                self.condition.wait(0.25)
            action, self.resume_action = self.resume_action, None
            return action


class ExtensionRuns:
    """In-memory ownership; revoked sessions cancel waiters without closing tabs."""

    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.lock = threading.RLock()
        self.runs = {}

    def add(self, *, sid, current, service, channel):
        self.prune()
        with self.lock:
            if len(self.runs) >= 20:
                raise ValueError("Extension session capacity reached")
            item = {"sid": sid, "current": current, "service": service,
                    "channel": channel, "job_id": None}
            self.runs[channel.run_id] = item
            return item

    def owned(self, run_id, sid, current):
        with self.lock:
            item = self.runs.get(run_id)
            if not item or item["sid"] != sid or item["current"] is not current:
                raise KeyError("Extension run unavailable")
        item["channel"].guard()
        return item

    def snapshot(self, item):
        channel = item["channel"]
        status = channel.control.snapshot()
        state, guidance = status["state"], status["guidance"]
        if item["job_id"]:
            job = item["service"].read(item["job_id"])
            if job["status"] not in {"queued", "running"}:
                state = job["status"]
                guidance = (job.get("result") or {}).get("guidance") or job.get("guidance") or guidance
        if status["state"] == "cancelled":
            # Explicit tab cancellation wins the race with the worker's generic
            # needs_input completion. Clients must discard an in-flight ACK.
            state, guidance = "cancelled", status["guidance"]
        with channel.condition:
            pending = channel.pending is not None and channel.pending["ack"] is None
        return {
            "run_id": channel.run_id, "job_id": item["job_id"], "state": state,
            "guidance": guidance, "agent_report": status["agent_report"],
            "command_pending": pending, "instance_id": self.instance_id,
        }

    def prune(self):
        with self.lock:
            for run_id, item in list(self.runs.items()):
                channel = item["channel"]
                if not channel.alive() or channel.clock() - channel.created > RUN_TTL:
                    channel.stop()
                    self.runs.pop(run_id, None)

    def close(self):
        with self.lock:
            for item in self.runs.values():
                item["channel"].stop()
            self.runs.clear()
