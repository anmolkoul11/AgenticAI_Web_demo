"""Synthetic owner-thread contracts; no browser, server or model calls."""

import threading
from types import SimpleNamespace

import pytest

from agentic_web_demo import custom_browser
from agentic_web_demo.custom_browser import BrowserControl, read_browser
from agentic_web_demo.custom_fetch import WebsiteError


class ReviewPage:
    def __init__(self):
        self.closed = threading.Event()
        self.pumped = threading.Event()
        self.pump_threads = []

    def is_closed(self):
        return self.closed.is_set()

    def wait_for_timeout(self, _milliseconds):
        self.pump_threads.append(threading.get_ident())
        self.pumped.set()
        self.closed.wait(0.005)


class ReviewBrowser:
    def __init__(self):
        self.connected = True
        self.close_thread = None

    def is_connected(self):
        return self.connected

    def close(self):
        self.close_thread = threading.get_ident()
        self.connected = False


@pytest.fixture
def owner_fixture(monkeypatch):
    controls = []

    def install(*, alive=lambda: True, failure=None, after_handoff_failure=False):
        control = BrowserControl(alive)
        controls.append(control)
        page, browser = ReviewPage(), ReviewBrowser()
        source = [{"url": "https://example.org/results", "blocks": [{"text": "Hotel A"}]}]
        owner_threads, callbacks = [], []

        def on_closed():
            # The callback may acquire the service registry lock. It must not
            # run while holding the browser-control lock.
            acquired = control.lock.acquire(blocking=False)
            callbacks.append(acquired)
            if acquired:
                control.lock.release()

        control.on_closed = on_closed

        def fake_owned(values, owned_control, settings, *, handoff):
            owner_threads.append(threading.get_ident())
            try:
                if failure is not None:
                    raise failure
                handoff(source, page, browser, None)
                if after_handoff_failure:
                    raise WebsiteError("Synthetic post-capture cleanup error")
            finally:
                browser.close()

        monkeypatch.setattr(custom_browser, "_read_browser_owned", fake_owned)
        return SimpleNamespace(
            control=control, page=page, browser=browser, source=source,
            owner_threads=owner_threads, callbacks=callbacks,
        )

    yield install
    for control in controls:
        control.close_requested.set()
        worker = control.owner_thread
        if worker is not None and worker.ident is not None:
            worker.join(timeout=2)
            assert not worker.is_alive(), "Synthetic browser owner was not cleaned up"


def test_capture_returns_frozen_snapshot_before_verification_window_closes(owner_fixture):
    fixture = owner_fixture()
    caller_thread = threading.get_ident()
    captured = read_browser(SimpleNamespace(), fixture.control, object())
    assert captured == fixture.source
    assert captured is not fixture.source
    assert captured[0]["blocks"] is not fixture.source[0]["blocks"]
    fixture.source[0]["blocks"][0]["text"] = "Changed manually after capture"
    assert captured[0]["blocks"][0]["text"] == "Hotel A"
    assert fixture.control.snapshot()["inspection"] == {
        "active": True, "snapshot_frozen": True,
    }
    assert fixture.control.owner_thread.is_alive()
    assert fixture.page.pumped.wait(2)
    assert fixture.owner_threads[0] != caller_thread
    assert set(fixture.page.pump_threads) == set(fixture.owner_threads)


@pytest.mark.parametrize("action", ["close", "cancel"])
def test_close_after_capture_does_not_cancel_extraction(owner_fixture, action):
    fixture = owner_fixture()
    captured = read_browser(SimpleNamespace(), fixture.control)
    fixture.control.command(action)
    assert not fixture.control.cancel.is_set()
    assert fixture.control.close_requested.is_set()
    assert fixture.control.worker_closed.wait(2)
    fixture.control.owner_thread.join(timeout=2)
    assert captured[0]["blocks"][0]["text"] == "Hotel A"
    assert fixture.control.snapshot()["inspection"] == {
        "active": False, "snapshot_frozen": True,
    }
    assert fixture.browser.close_thread == fixture.owner_threads[0]
    assert fixture.callbacks == [True]


def test_review_phase_rejects_new_automation_commands(owner_fixture):
    fixture = owner_fixture()
    read_browser(SimpleNamespace(), fixture.control)
    for action in ("capture", "plan", "discover", "agent_start", "hotel_plan"):
        with pytest.raises(WebsiteError, match="verification only"):
            fixture.control.command(action, agent_confirmed=True)
    assert not fixture.control.capture.is_set()
    assert not fixture.control.agent_requested.is_set()
    assert not fixture.control.navigation_requested.is_set()


@pytest.mark.parametrize("reason", ["logout", "manual_window", "shutdown"])
def test_owner_closes_on_logout_manual_window_or_service_shutdown(owner_fixture, reason):
    alive = threading.Event()
    alive.set()
    fixture = owner_fixture(alive=alive.is_set)
    captured = read_browser(SimpleNamespace(), fixture.control)
    if reason == "logout":
        alive.clear()
    elif reason == "manual_window":
        fixture.page.closed.set()
    else:
        fixture.control.cancel.set()
    assert fixture.control.worker_closed.wait(2)
    fixture.control.owner_thread.join(timeout=2)
    assert fixture.control.snapshot()["state"] == "closed"
    assert captured[0]["blocks"][0]["text"] == "Hotel A"
    assert fixture.callbacks == [True]


def test_precapture_website_error_reaches_caller_and_cleans_owner(owner_fixture):
    fixture = owner_fixture(failure=WebsiteError("Synthetic capture was not ready"))
    with pytest.raises(WebsiteError, match="Synthetic capture was not ready"):
        read_browser(SimpleNamespace(), fixture.control)
    assert fixture.control.worker_closed.is_set()
    assert not fixture.control.review_open.is_set()
    assert not fixture.control.snapshot_frozen
    assert fixture.callbacks == [True]


def test_precapture_unexpected_error_is_sanitized(owner_fixture):
    fixture = owner_fixture(failure=RuntimeError("fixture-secret-never-serialize"))
    with pytest.raises(WebsiteError) as raised:
        read_browser(SimpleNamespace(), fixture.control)
    assert "fixture-secret-never-serialize" not in str(raised.value)
    assert fixture.control.worker_closed.is_set()


def test_owner_abort_before_capture_unblocks_caller_and_cleans_resources(owner_fixture):
    fixture = owner_fixture(failure=KeyboardInterrupt("fixture-abort-never-serialize"))
    with pytest.raises(WebsiteError) as raised:
        read_browser(SimpleNamespace(), fixture.control)
    assert "fixture-abort-never-serialize" not in str(raised.value)
    assert fixture.control.worker_closed.is_set()
    assert not fixture.control.review_open.is_set()


def test_postcapture_cleanup_error_does_not_replace_snapshot(owner_fixture):
    fixture = owner_fixture(after_handoff_failure=True)
    captured = read_browser(SimpleNamespace(), fixture.control)
    fixture.control.command("close")
    assert fixture.control.worker_closed.wait(2)
    fixture.control.owner_thread.join(timeout=2)
    assert captured[0]["blocks"][0]["text"] == "Hotel A"
    assert not fixture.control.cancel.is_set()


def test_close_before_capture_does_not_cancel_or_queue_a_command():
    control = BrowserControl()
    with pytest.raises(WebsiteError, match="No captured verification browser"):
        control.command("close")
    assert not control.close_requested.is_set()
    assert not control.cancel.is_set()


def test_cancel_before_capture_still_cancels_the_collection():
    control = BrowserControl()
    control.command("cancel")
    assert control.cancel.is_set()
    assert not control.close_requested.is_set()
