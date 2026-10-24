"""Selected-tab adapter fixtures; no real browser, network or provider calls."""

import copy
import hashlib
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PlaywrightError

from agentic_web_demo.browser_agent import BrowserDecision, DOMBrowserTools
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.extension_browser import ExtensionBrowserDecider, ExtensionBrowserTools, observation_diagnostics, safe_tab_url
from agentic_web_demo import extension_browser
from agentic_web_demo.extension_channel import ExtensionCommandError
from agentic_web_demo.stay_scope import observed_result_scope


URL = "https://example.org/searchresults.html"
QUERY = "?checkin=2026-10-28&checkout=2026-10-30&group_adults=4&no_rooms=2"
TOKEN = "document_token_a"


class Channel:
    def __init__(self, replies=(), url=URL + QUERY):
        self.approved_origin = "https://example.org"
        self.initial_url, self.tab_id = url, 27
        self.cancel, self.pause_requested = threading.Event(), threading.Event()
        self.replies, self.calls = list(replies), []

    def guard(self):
        if self.cancel.is_set():
            raise WebsiteError("Cancelled")

    def call(self, operation, payload=None, timeout=30):
        self.calls.append((operation, copy.deepcopy(payload)))
        expected, result = self.replies.pop(0)
        assert expected == operation
        return copy.deepcopy(result)


def control(**changes):
    return {"id": "0", "tag": "INPUT", "type": "text", "role": "combobox",
            "name": "destination", "label": "Destination", "text": "", "value": "New York",
            "href": "", "submits_form": False, "form_scope": "0", "option_ids": ["1"],
            **changes}


def observation(token=TOKEN, url=URL + QUERY, controls=None, **frame_changes):
    return {"url": url, "document_token": token, "frame": {
        "title": "Search results", "text": "Returned hotel listings are visible on the website.",
        "controls": controls if controls is not None else [control()],
        "results": {"record_count": 1, "busy": False},
        "widgets": [], "password_or_code_visible": False,
        **frame_changes,
    }}


def capture():
    return {"version": 1, "url": URL, "captured_at": datetime.now(timezone.utc).isoformat(),
            "truncated": False, "blocks": [
                {"id": "b1", "kind": "heading", "text": "New York: 372 properties found",
                 "association": "page", "heading_level": 1},
                {"id": "b2", "kind": "heading", "text": "Example Hotel New York",
                 "association": "record", "group_id": "g1"},
                {"id": "b3", "kind": "text", "text": "$259", "association": "record",
                 "group_id": "g1", "value_context": {"quote": "Per night $259", "label": "Per night",
                    "relation": "local_container", "struck_through": False}},
                {"id": "b4", "kind": "paragraph", "text": "Breakfast included. Free WiFi. Two nights, four adults.",
                 "association": "record", "group_id": "g1"},
            ]}


def tools(replies, **changes):
    channel = Channel(replies, **changes)
    return ExtensionBrowserTools(channel, BrowserControl(), SimpleNamespace(browser_scroll_steps=0)), channel


def decision(action="fill", **changes):
    return BrowserDecision(action=action, control_id="0:0", value="New York",
                           explanation="Fill the destination", evidence="Destination field", **changes)


def test_observation_prefixes_references_but_keeps_exact_href_out_of_model_view():
    href = "https://example.org/hotel?item_id=42&session_token=private"
    adapter, _ = tools([("observe", observation(controls=[control(href=href)]))])
    state = adapter.observe()
    item = state["frames"][0]["controls"][0]
    assert item["id"] == "0:0" and item["form_scope"] == "0:form:0"
    assert item["option_ids"] == ["0:1"]
    assert item["href"] == "https://example.org/hotel"
    assert adapter.references["0:0"][2]["href"] == href
    assert state["stay_url_values"]["rooms"] == [2]
    assert "?" not in state["url"]


def test_observation_diagnostics_preserve_counts_but_not_entered_values():
    reply = observation()
    reply["executor_version"] = "0.4.1"
    reply["frame"]["autocomplete_diagnostics"] = {
        "field_count": 1, "visible_listbox_count": 1, "visible_option_count": 5,
        "owned_option_count": 5, "text": "must not be retained",
        "fields": [{"control_id": "0", "focused": True, "expanded": "true",
                    "controlled_popup_count": 1, "visible_controlled_popup_count": 1,
                    "owned_option_count": 5, "association": "explicit_aria",
                    "value": "private-entered-value", "label": "private-label"}],
    }
    summary = observation_diagnostics(reply)
    assert summary["executor_version"] == "0.4.1"
    assert summary["autocomplete"]["visible_option_count"] == 5
    assert summary["autocomplete"]["fields"][0]["control_id"] == "0:0"
    assert summary["autocomplete"]["fields"][0]["association"] == "explicit_aria"
    assert "private" not in repr(summary) and "must not be retained" not in repr(summary)


@pytest.mark.parametrize("diagnostics", [None, False, [], {"fields": False}])
def test_optional_popup_diagnostics_do_not_break_observation(diagnostics):
    reply = observation()
    reply["frame"]["autocomplete_diagnostics"] = diagnostics
    assert observation_diagnostics(reply)["autocomplete"]["fields"] == []


def test_tab_visibility_diagnostics_keep_only_observed_safe_flags():
    reply = observation()
    reply["tab_state"] = {"visibility": "hidden", "has_focus": False,
                          "page_text": "must not be retained"}
    result = observation_diagnostics(reply)
    assert result["tab_state"] == {"visibility": "hidden", "has_focus": False}
    assert "must not be retained" not in repr(result)


@pytest.mark.parametrize("tab_state", [None, [], {"visibility": ["hidden"], "has_focus": 1}])
def test_invalid_optional_tab_diagnostics_do_not_break_observation(tab_state):
    reply = observation()
    reply["tab_state"] = tab_state
    assert observation_diagnostics(reply)["tab_state"] == {}


def test_control_persists_safe_extension_observation_diagnostics():
    panel = BrowserControl()
    summaries = []
    panel.on_agent_diagnostics = summaries.append
    summary = observation_diagnostics(observation())
    panel.set_agent_report({"status": "paused", "guidance": "Review the tab",
                            "observation_diagnostics": summary})
    assert summaries[-1]["observation_diagnostics"] == summary


def test_same_url_new_document_gets_new_identity():
    adapter, _ = tools([("observe", observation()), ("observe", observation(token="document_token_b"))])
    old, new = adapter.observe(), adapter.observe()
    assert old["url"] == new["url"]
    assert old["document_id"] != new["document_id"]
    assert new["document_id"] == hashlib.sha256((safe_tab_url(URL + QUERY) + "\ndocument_token_b").encode()).hexdigest()


def test_calendar_owner_references_are_prefixed_without_changing_the_live_target():
    day = control(id="7", tag="SPAN", role="checkbox", date_owner_id="6",
                  label="Saturday, November 28, 2026", name="", value="")
    adapter, _ = tools([("observe", observation(controls=[day]))])
    state = adapter.observe()
    assert state["frames"][0]["controls"][0]["date_owner_id"] == "0:6"
    assert adapter.references["0:7"][1] == "7"
    assert adapter.references["0:7"][2]["date_owner_id"] == "0:6"


@pytest.mark.parametrize("owner", ["0:6", "not-a-reference", "6]button"])
def test_invalid_calendar_owner_reference_is_rejected(owner):
    adapter, _ = tools([("observe", observation(controls=[control(date_owner_id=owner)]))])
    with pytest.raises(WebsiteError, match="invalid calendar reference"):
        adapter.observe()


@pytest.mark.parametrize("frame_change", [{"access_restriction": True}, {"manual_verification_required": True},
                                          {"text": "Access is temporarily restricted. Unusual activity."}])
def test_challenge_observation_stops_before_any_action_or_model(frame_change):
    adapter, channel = tools([("observe", observation(**frame_change))])
    with pytest.raises(WebsiteError, match="Complete the website verification"):
        adapter.observe()
    assert len(channel.calls) == 1 and not adapter.references


def test_cross_origin_observation_is_not_accepted():
    adapter, _ = tools([("observe", observation(url="https://elsewhere.example/"))])
    with pytest.raises(WebsiteError, match="selected tab"):
        adapter.observe()


def test_execute_sends_only_observed_facts_and_current_document_token_once():
    adapter, channel = tools([("observe", observation()), ("execute", {
        "status": "value_verified", "expected": "New York", "observed": "New York",
    })])
    adapter.observe()
    result = adapter.execute(decision())
    operation, payload = channel.calls[-1]
    assert operation == "execute" and payload["document_token"] == TOKEN
    assert payload["facts"]["name"] == "destination"
    assert payload["decision"]["control_id"] == "0:0"
    assert result["status"] == "value_verified"


def test_uncertain_execute_is_not_replayed():
    adapter, channel = tools([("observe", observation()), ("execute", {"status": "unknown"})])
    adapter.observe()
    with pytest.raises(PlaywrightError, match="not automatically repeated"):
        adapter.execute(decision())
    assert [item[0] for item in channel.calls] == ["observe", "execute"]


@pytest.mark.parametrize("code", ["command_timeout", "delivery_unknown", "execution_failed",
                                 "origin_changed", "tab_closed", "permission_required",
                                 "session_changed", "payload_too_large", "access_restriction"])
def test_dispatched_transport_uncertainty_uses_runtime_attempted_action_path(code):
    adapter, channel = tools([("observe", observation())])
    adapter.observe()

    def uncertain(operation, payload=None, timeout=30):
        channel.calls.append((operation, payload))
        raise ExtensionCommandError("Fixture transport uncertainty", code=code, dispatched=True)

    channel.call = uncertain
    with pytest.raises(PlaywrightError, match="outcome is unknown"):
        adapter.execute(decision())
    assert [item[0] for item in channel.calls] == ["observe", "execute"]


def test_known_control_preflight_rejection_does_not_claim_a_dispatched_action():
    adapter, channel = tools([("observe", observation())])
    adapter.observe()

    def stale(operation, payload=None, timeout=30):
        raise ExtensionCommandError("Fixture stale control", code="control_changed", dispatched=True)

    channel.call = stale
    with pytest.raises(WebsiteError):
        adapter.execute(decision())


def test_typed_capture_preserves_record_local_price_evidence_and_uses_shared_capture_logic():
    raw = capture()
    adapter, _ = tools([("observe", observation()), ("capture", {"capture": raw, "document_token": TOKEN, "url": URL + QUERY})])
    adapter.observe()
    result = adapter.capture()
    assert result["status"] == "captured"
    assert adapter.pages[0]["blocks"][2]["value_context"]["label"] == "Per night"
    assert adapter.pages[0]["source_kind"] == "page"
    assert ExtensionBrowserTools.capture is DOMBrowserTools.capture


@pytest.mark.parametrize("change", ["token", "url", "capture_source"])
def test_changed_document_or_source_is_rejected_without_retaining_capture(change):
    raw = capture()
    if change == "capture_source":
        raw["url"] = "https://example.org/different"
    reply = {"capture": raw, "document_token": "different_token" if change == "token" else TOKEN,
             "url": URL + "?checkin=2026-11-01" if change == "url" else URL + QUERY}
    adapter, _ = tools([("observe", observation()), ("capture", reply)])
    adapter.observe()
    with pytest.raises(WebsiteError):
        adapter.capture()
    assert not adapter.pages


def test_capture_reuses_independent_returned_stay_and_prepared_heading_reconciliation():
    raw = capture()
    adapter, _ = tools([("observe", observation(controls=[])),
                        ("capture", {"capture": raw, "document_token": TOKEN, "url": URL + QUERY}),
                        ("observe", observation(controls=[]))])
    state = adapter.observe()
    requested = {"destination": "New York", "check_in": "2026-10-28", "check_out": "2026-10-30",
                 "adults": 4, "rooms": 2, "nights": 2}
    scope = observed_result_scope(requested, state)
    assert scope["status"] == "unverified"
    adapter.collection_context = {"result_document_id": state["document_id"], "result_scope": scope}
    adapter.capture()
    context = adapter.pages[0]["browser_task_context"]
    assert context["result_scope"]["status"] == "verified"
    assert context["requested_stay_verified"] and not context["source_preview_only"]


def test_no_screenshots_or_sensitive_query_memory_in_selected_tab_v1():
    adapter, channel = tools([])
    assert not adapter.visual_enabled
    with pytest.raises(WebsiteError, match="unavailable"):
        adapter.viewport_image()
    assert not channel.calls
    url = safe_tab_url(URL + QUERY + "&access_token=private&email=a%40example.org")
    assert "access_token" not in url and "email" not in url
    assert "checkin=2026-10-28" in url


def test_managed_capture_identity_hook_preserves_existing_raw_url_hash():
    page = SimpleNamespace(url=URL + QUERY)
    managed = DOMBrowserTools(page, "https://example.org", None, lambda: True, lambda: False)
    assert managed.current_url == page.url
    assert managed.current_document_id == hashlib.sha256(page.url.encode()).hexdigest()


def test_reader_resumes_same_agent_without_recreating_budget_and_leaves_tab_open(monkeypatch):
    channel = Channel([])
    events = []

    class Decider:
        def __init__(self, settings):
            events.append("decider_created")

        def close(self):
            events.append("decider_closed")

    class Agent:
        def __init__(self, *args, **kwargs):
            self.calls = 0
            events.append("agent_created")

        def run(self):
            self.calls += 1
            return {"status": "paused" if self.calls == 1 else "ready", "guidance": "Review tab"}

        def captured_sources(self):
            return [{"url": URL, "text": "Frozen source", "blocks": []}]

    channel.wait_for_resume = lambda: "resume"
    monkeypatch.setattr(extension_browser, "ExtensionBrowserDecider", Decider)
    monkeypatch.setattr(extension_browser, "BrowserAgent", Agent)
    review = BrowserControl()
    values = SimpleNamespace(framework="langgraph", browser_scroll_steps=0,
                             instructions="Get visible records", output_fields=[])
    pages = extension_browser.read_extension(values, review, object(), channel)
    assert len(pages) == 1 and review.snapshot_frozen and review.state == "reviewing"
    assert events == ["decider_created", "agent_created", "decider_closed"]
    assert not channel.cancel.is_set() and not channel.calls


def test_reader_keeps_confirmed_empty_search_for_existing_no_extraction_branch(monkeypatch):
    channel = Channel([])

    class Decider:
        def __init__(self, settings):
            pass

        def close(self):
            pass

    class Agent:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return {"status": "ready", "guidance": "No results", "collection_outcome": "empty_results",
                    "task_checklist": {"search_submitted": True, "search_response_pending": False}}

        def captured_sources(self):
            return []

    monkeypatch.setattr(extension_browser, "ExtensionBrowserDecider", Decider)
    monkeypatch.setattr(extension_browser, "BrowserAgent", Agent)
    review = BrowserControl()
    values = SimpleNamespace(framework="langgraph", browser_scroll_steps=0,
                             instructions="Find matching records", output_fields=[])
    assert extension_browser.read_extension(values, review, object(), channel) == []
    assert review.snapshot_frozen


def test_selected_tab_capabilities_use_existing_decider_without_advertising_arrow_keys(monkeypatch):
    received = []

    def decide(self, payload, timeout):
        received.append(payload)
        return "fixture decision"

    monkeypatch.setattr(extension_browser.OpenAIBrowserDecider, "decide", decide)
    adapter = object.__new__(ExtensionBrowserDecider)
    payload = {"task": "Search", "observation": {"frames": [{"controls": [
        {"id": "0:0", "supported_actions": ["fill", "press", "click"]},
    ]}]}}
    assert adapter.decide(payload, 10) == "fixture decision"
    assert received[0]["observation"]["frames"][0]["controls"][0]["supported_actions"] == ["fill", "click"]
    assert received[0]["browser_capabilities"]["screenshots"] is False
    assert payload["observation"]["frames"][0]["controls"][0]["supported_actions"] == ["fill", "press", "click"]
