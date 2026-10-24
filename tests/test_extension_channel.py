"""Offline command-transport fixtures; no real browser, server or provider calls."""

import threading
from types import SimpleNamespace

import pytest

from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.extension_api import ExtensionStart
from agentic_web_demo.extension_channel import (
    ExtensionChannel, ExtensionCommandError, ExtensionRuns, bounded_json,
)


def channel(**changes):
    return ExtensionChannel(
        tab_id=7, url="https://example.org/listings?sid=secret", control=BrowserControl(),
        alive=lambda: True, **changes,
    )


def pending_call(link, operation="observe"):
    ready = threading.Event()
    original = link.condition.wait

    def wait(timeout=None):
        ready.set()
        return original(timeout)

    link.condition.wait = wait
    output = {}

    def invoke():
        try:
            output["result"] = link.call(operation, {"focus": "task"}, timeout=2)
        except WebsiteError as error:
            output["error"] = str(error)
            output["failure"] = error

    worker = threading.Thread(target=invoke)
    worker.start()
    assert ready.wait(1)
    return worker, output


def test_commands_are_claimed_once_and_identical_ack_is_idempotent():
    link = channel()
    worker, output = pending_call(link)
    command = link.claim()
    assert command["operation"] == "observe"
    assert link.claim() is None
    result = {"url": "https://example.org/listings", "document_token": "doc-1", "frame": {}}
    assert link.acknowledge(command["request_id"], ok=True, result=result) == "acknowledged"
    worker.join(1)
    assert not worker.is_alive()
    assert output["result"] == result
    assert link.acknowledge(command["request_id"], ok=True, result=result) == "already_acknowledged"
    assert link.claim() is None
    with pytest.raises(ValueError):
        link.acknowledge(command["request_id"], ok=True, result={"different": True})
    assert "secret" not in link.initial_url


def test_ack_before_dispatch_and_unknown_ids_are_rejected():
    link = channel()
    worker, output = pending_call(link)
    request_id = link.pending["request_id"]
    with pytest.raises(ValueError):
        link.acknowledge(request_id, ok=True, result={})
    with pytest.raises(ValueError):
        link.acknowledge("0" * 32, ok=True, result={})
    link.stop()
    worker.join(1)
    assert not worker.is_alive()
    assert "cancelled" in output["error"]


def test_session_revocation_and_cancel_release_blocked_worker():
    active = [True]
    link = ExtensionChannel(tab_id=9, url="https://example.org/", control=BrowserControl(),
                            alive=lambda: active[0])
    worker, output = pending_call(link)
    assert link.claim()
    active[0] = False
    worker.join(1)
    assert not worker.is_alive()
    assert link.cancel.is_set()
    assert "expired" in output["error"]


@pytest.mark.parametrize("error_code", ["delivery_unknown", "origin_changed", "permission_required", "tab_closed"])
def test_claimed_action_error_preserves_dispatch_uncertainty(error_code):
    link = channel()
    worker, output = pending_call(link, "execute")
    command = link.claim()
    link.acknowledge(command["request_id"], ok=False, error=error_code)
    worker.join(1)
    assert not worker.is_alive()
    assert isinstance(output["failure"], ExtensionCommandError)
    assert output["failure"].dispatched is True
    assert output["failure"].code == error_code
    assert link.claim() is None


def test_pause_prevents_dispatch_of_queued_action_and_requires_explicit_resume():
    link = channel()
    link.control.update("agent_running", "Working")
    worker, output = pending_call(link, "execute")
    link.request_control("pause")
    worker.join(1)
    assert link.claim() is None
    assert "cancelled" in output["error"]
    assert link.pause_requested.is_set()
    link.control.update("agent_paused", "Paused")
    link.request_control("resume")
    assert link.wait_for_resume() == "resume"
    assert not link.pause_requested.is_set()


def test_run_is_bound_to_account_session_and_shutdown_unblocks():
    manager = ExtensionRuns("instance")
    link, account = channel(), object()
    manager.add(sid="session-one", current=account, service=None, channel=link)
    assert manager.owned(link.run_id, "session-one", account)["channel"] is link
    with pytest.raises(KeyError):
        manager.owned(link.run_id, "session-two", account)
    with pytest.raises(KeyError):
        manager.owned(link.run_id, "session-one", object())
    worker, _ = pending_call(link)
    manager.close()
    worker.join(1)
    assert not worker.is_alive()
    assert link.cancel.is_set()


def test_explicit_cancel_snapshot_wins_worker_completion_race():
    manager, link = ExtensionRuns("instance"), channel()
    service = SimpleNamespace(read=lambda _: {"status": "needs_input", "result": {"guidance": "Cancelled"}})
    item = manager.add(sid="session", current=object(), service=service, channel=link)
    item["job_id"] = "fixture-job"
    link.request_control("cancel")
    assert manager.snapshot(item)["state"] == "cancelled"


@pytest.mark.parametrize("bad", [float("nan"), {"x": object()}, "x" * 400_001])
def test_packets_are_bounded_finite_json(bad):
    with pytest.raises(ValueError):
        bounded_json(bad)


def test_extension_start_requires_explicit_consent_and_rejects_screenshots():
    values = {"url": "https://example.org/", "tab_id": 9, "instructions": "Get records",
              "agent_confirmed": True, "authorized": True, "allow_model_api": True}
    assert ExtensionStart(**values).record_limit == 25
    for field in ("agent_confirmed", "authorized", "allow_model_api"):
        with pytest.raises(ValueError):
            ExtensionStart(**{**values, field: False})
        with pytest.raises(ValueError):
            ExtensionStart(**{**values, field: "true"})
    with pytest.raises(ValueError):
        ExtensionStart(**{**values, "agent_visual_confirmed": True})
