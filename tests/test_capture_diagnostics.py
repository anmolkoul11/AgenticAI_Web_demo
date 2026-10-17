"""Safe capture diagnostics; no browser, application server or model calls."""

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from agentic_web_demo.custom_browser import (
    BrowserCaptureError,
    BrowserControl,
    capture_failure,
    capture_rendered_page,
    remember_capture_failure,
)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PlaywrightError("CAPTURE_INSUFFICIENT_CONTENT private-page-text"), "insufficient_content"),
        (PlaywrightError("Execution context was destroyed private-page-text"), "page_changed"),
        (PlaywrightError("Target closed private-page-text"), "closed"),
        (PlaywrightTimeout("private-page-text"), "timeout"),
        (PlaywrightError("TypeError private-page-text token=secret"), "collector_exception"),
    ],
)
def test_capture_failure_is_classified_without_raw_exception_text(error, expected):
    failure = capture_failure(error)
    assert failure.code == expected
    assert failure.capture_diagnostics == {"code": expected, "phase": "collect"}
    assert "private-page-text" not in str(failure)
    assert "secret" not in str(failure)


def test_preparation_and_collection_failures_remain_distinct():
    failure = capture_failure(PlaywrightError("private scroll exception"), phase="prepare")
    assert failure.code == "preparation_failed"
    assert failure.capture_diagnostics["phase"] == "prepare"


def test_capture_error_facts_are_bounded_and_session_local():
    first, second = BrowserControl(), BrowserControl()
    failure = BrowserCaptureError(
        "insufficient_content",
        block_count=2,
        captured_text_chars=32,
        main_status=200,
        password="never log",
        token="never log",
        url="https://private/",
    )
    remember_capture_failure(first, failure)
    assert first.snapshot()["browser_error"] == {
        "stage": "capture",
        "code": "insufficient_content",
        "block_count": 2,
        "captured_text_chars": 32,
        "main_status": 200,
    }
    assert second.snapshot()["browser_error"] is None


def test_rendered_collector_error_becomes_actionable_failure_not_raw_driver_error():
    class Locator:
        def count(self):
            return 0

    class Page:
        url = "https://example.org/"

        def locator(self, _selector):
            return Locator()

        def evaluate(self, *_args):
            raise PlaywrightError("CAPTURE_INSUFFICIENT_CONTENT sensitive query")

    with pytest.raises(BrowserCaptureError, match="Too little source content") as failure:
        capture_rendered_page(Page(), "https://example.org", [], [200])
    assert failure.value.code == "insufficient_content"


def test_ambiguous_query_identity_cannot_merge_into_a_fake_detail_target():
    from agentic_web_demo.enrichment import safe_url

    assert safe_url("https://example.org/view?opaque=one") is None
    assert safe_url("https://example.org/article?id=one") != safe_url(
        "https://example.org/article?id=two"
    )


def test_normalized_page_address_does_not_restore_an_omitted_record_key():
    from agentic_web_demo.enrichment import page_target_urls

    page = {
        "url": "https://example.org/view",
        "requested_url": "https://example.org/view?id=one",
        "coverage": {"page_url_identity_omitted": True},
    }
    assert page_target_urls(page) == (None, None)
    assert page_target_urls({"url": "https://example.org/story/one"}) == (
        None,
        "https://example.org/story/one",
    )
