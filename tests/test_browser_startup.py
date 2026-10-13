"""Offline startup readiness checks: no launched browsers or external websites."""

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from agentic_web_demo.custom_browser import BrowserControl, wait_for_initial_content


class Page:
    def __init__(self, timeout=False):
        self.timeout = timeout
        self.calls = []

    def wait_for_function(self, expression, **kwargs):
        self.calls.append((expression, kwargs))
        if self.timeout:
            raise PlaywrightTimeout("fixture")

    def wait_for_load_state(self, *_args, **_kwargs):
        raise AssertionError("Initial readiness must not await ads/media or network idle")


def test_initial_handoff_waits_for_useful_dom_with_a_short_cap():
    page = Page()
    assert wait_for_initial_content(page) == "useful_dom_visible"
    expression, settings = page.calls[0]
    assert settings["timeout"] == 1500
    assert "interactive" in expression and "getClientRects" in expression


def test_slow_initial_dom_is_pending_not_a_claim_of_failed_browser_launch():
    assert wait_for_initial_content(Page(timeout=True)) == "readiness_pending"


def test_startup_timings_are_available_without_exposing_browser_secrets():
    control = BrowserControl()
    control.startup_timing = {"launch_seconds": 0.8, "navigation_seconds": 1.2}
    assert control.snapshot()["startup_timing"] == control.startup_timing
