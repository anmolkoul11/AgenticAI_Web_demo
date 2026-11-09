"""Offline passive-wait readback cases; no browser, site, or API is invoked."""

import copy
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_agent import DOMBrowserTools
from agentic_web_demo.extension_browser import ExtensionBrowserTools


def observation(document="document-a", *, busy=False, inherited_hint=False):
    return {
        "document_id": document, "frames": [],
        "results": {"record_count": 2, "result_signature": "1234abcd", "busy": busy,
                    **({"busy_seen_during_wait": True} if inherited_hint else {})},
    }


def passive_wait(tools_class, readings, *, max_seconds=5):
    tools = object.__new__(tools_class)
    pending = iter(readings[1:])
    tools.guard = lambda: None
    tools.observe = lambda: next(pending)
    tools.page = SimpleNamespace(wait_for_timeout=lambda milliseconds: None)
    tools._passive_wait = lambda seconds: None
    return tools.wait_for_results(readings[0], max_seconds=max_seconds)


@pytest.mark.parametrize("tools_class", [DOMBrowserTools, ExtensionBrowserTools])
def test_passive_wait_retains_observed_busy_cycle_with_unchanged_final_results(tools_class):
    readings = [observation(), observation(busy=True), observation()]
    before = copy.deepcopy(readings)
    result = passive_wait(tools_class, readings)
    assert result["results"]["busy"] is False
    assert result["results"]["busy_seen_during_wait"] is True
    assert result["results"]["result_signature"] == "1234abcd"
    assert readings == before


@pytest.mark.parametrize("tools_class", [DOMBrowserTools, ExtensionBrowserTools])
@pytest.mark.parametrize("inherited_hint", [False, True])
def test_passive_wait_does_not_infer_busy_from_idle_or_reuse_old_hint(tools_class, inherited_hint):
    readings = [observation(inherited_hint=inherited_hint), observation(inherited_hint=inherited_hint)]
    before = copy.deepcopy(readings)
    result = passive_wait(tools_class, readings)
    assert "busy_seen_during_wait" not in result["results"]
    assert readings == before


@pytest.mark.parametrize("tools_class", [DOMBrowserTools, ExtensionBrowserTools])
@pytest.mark.parametrize("readings", [
    [observation(busy=True), observation("document-b"), observation("document-b")],
    [observation(), observation("document-b", busy=True), observation("document-b")],
])
def test_passive_wait_does_not_transfer_busy_evidence_to_another_document(tools_class, readings):
    result = passive_wait(tools_class, readings)
    assert result["document_id"] == "document-b"
    assert "busy_seen_during_wait" not in result["results"]


@pytest.mark.parametrize("tools_class", [DOMBrowserTools, ExtensionBrowserTools])
@pytest.mark.parametrize("busy", ["true", 1])
def test_passive_wait_requires_literal_observed_busy_boolean(tools_class, busy):
    result = passive_wait(tools_class, [observation(busy=busy), observation()])
    assert "busy_seen_during_wait" not in result["results"]


@pytest.mark.parametrize("tools_class", [DOMBrowserTools, ExtensionBrowserTools])
def test_passive_wait_preserves_witnessed_busy_at_deadline(tools_class):
    result = passive_wait(tools_class, [observation(busy=True)], max_seconds=0)
    assert result["results"]["busy_seen_during_wait"] is True
    assert result["results"]["busy"] is True
