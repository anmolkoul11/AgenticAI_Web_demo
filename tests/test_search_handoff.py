"""Search handoff regressions use synthetic tools only; no browser or paid calls."""

import copy
import json
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from test_submission_scope import FormTools, Model, decision, goal, search_step

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserRequirement,
    browser_error_diagnostics,
    safe_browser_diagnostics,
)
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError


class HandoffTools(FormTools):
    """Expose a transition whose first observation may fail during navigation."""

    def __init__(self, *, error=None, failures=0, unchanged=False, mfa=False):
        super().__init__()
        self.error = error
        self.failures = failures
        self.unchanged = unchanged
        self.mfa = mfa
        self.cancelled = False
        self.cancel_during_wait = False
        self.post_search_observations = 0
        self.read_only_waits = []
        self.execute_error = None
        self.pre_dispatch_error = None
        self.pending_at_click = None
        self.agent = None
        self.page = SimpleNamespace(wait_for_timeout=self.passive_wait)

    def guard(self):
        if self.cancelled:
            raise WebsiteError("Cancelled by user")

    def passive_wait(self, milliseconds):
        self.read_only_waits.append(milliseconds)
        if self.cancel_during_wait:
            self.cancelled = True

    def observe(self):
        if self.searched:
            self.post_search_observations += 1
            if self.failures:
                self.failures -= 1
                raise self.error
            if self.unchanged:
                self.searched = False
                try:
                    observation = super().observe()
                    observation["url"] = "https://example.org/"
                    observation["document_id"] = "https://example.org/"
                finally:
                    self.searched = True
            else:
                observation = super().observe()
            if self.mfa:
                observation["frames"][0]["password_or_code_visible"] = True
            return observation
        return super().observe()

    def execute(self, item):
        if item.control_id == "0:search":
            # The invariant must hold at the instant Search is attempted, not
            # after an observation that may fail on the resulting document.
            assert self.agent is not None
            self.pending_at_click = copy.deepcopy(self.agent.task.pending_submission)
            assert self.pending_at_click is not None
            if self.pre_dispatch_error:
                raise self.pre_dispatch_error
        result = super().execute(item)
        if item.control_id == "0:search" and self.execute_error:
            raise self.execute_error
        return result


def search_decision():
    return decision(
        "click",
        "0:search",
        purpose="submit_search",
        collection_goal=goal("search_results", "Search for soccer"),
        requirements=[
            BrowserRequirement(
                name="query",
                expected="soccer",
                application="form",
                request_quote="soccer",
                control_id="0:query",
            )
        ],
    )


def make_agent(tools, *, model_search=False):
    model = Model(search_decision() if model_search else search_step())
    agent = BrowserAgent(tools, model, "Search for soccer")
    tools.agent = agent
    return agent, model


def search_entry(report):
    return next(entry for entry in report["actions"] if entry.get("control") == "Search")


@pytest.mark.parametrize("model_search", [False, True], ids=["runtime", "model"])
@pytest.mark.parametrize(
    ("error_message", "error_code"),
    [
        ("Execution context was destroyed, most likely by navigation", "navigation_context"),
        ("Frame was detached during navigation", "detached_frame"),
        ("AGENT_DOM_NOT_READY", "dom_not_ready"),
    ],
)
def test_transient_post_search_observation_recovers_then_captures_without_another_call(
    model_search,
    error_message,
    error_code,
):
    tools = HandoffTools(
        error=PlaywrightError(error_message),
        failures=1,
    )
    agent, model = make_agent(tools, model_search=model_search)
    report = agent.run()

    assert report["status"] == "ready"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.events.count("capture") == len(tools.pages) == 1
    assert report["task_checklist"]["search_response_pending"] is False
    assert report["task_checklist"]["search_transition"]["confirmed"] is True
    assert tools.pending_at_click["submission_provenance"]["actor"] == "agent"
    assert tools.pending_at_click["submission_provenance"]["action"] == "click"
    diagnostics = search_entry(report)["browser_diagnostics"]
    assert diagnostics["code"] == error_code
    assert diagnostics["transient"] is True
    assert diagnostics["recovered"] is True
    assert diagnostics["recovery_attempts"] == 1
    assert len(tools.read_only_waits) == 1


def test_persistent_transient_error_pauses_with_attempted_submission_retained():
    tools = HandoffTools(
        error=PlaywrightError("Execution context was destroyed, most likely by navigation"),
        failures=100,
    )
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert "capture" not in tools.events and not tools.pages
    proof = report["task_checklist"]["search_transition"]
    assert proof["attempted"] is True and proof["confirmed"] is False
    assert proof["attempt_status"] == "attempted_unconfirmed"
    assert report["task_checklist"]["search_response_pending"] is True
    assert agent.task.pending_submission is not None
    diagnostics = search_entry(report)["browser_diagnostics"]
    assert diagnostics["code"] == "navigation_context"
    assert diagnostics["transient"] is True and diagnostics["recovered"] is False
    assert 0 < diagnostics["recovery_attempts"] <= 4
    assert len(tools.read_only_waits) <= 4


def test_resume_observes_pending_search_without_clicking_or_calling_the_model_again():
    tools = HandoffTools(
        error=PlaywrightError("Execution context was destroyed, most likely by navigation"),
        failures=100,
    )
    agent, model = make_agent(tools)
    paused = agent.run()
    assert paused["status"] == "paused"
    assert agent.task.pending_submission is not None

    tools.failures = 0
    resumed = agent.run()

    assert resumed["status"] == "ready"
    assert resumed["run_id"] == paused["run_id"]
    assert resumed["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.events.count("capture") == 1
    assert resumed["task_checklist"]["search_submitted"] is True
    assert resumed["task_checklist"]["search_response_pending"] is False


@pytest.mark.parametrize("model_search", [False, True], ids=["runtime", "model"])
def test_unchanged_page_is_not_search_confirmation_and_does_not_spend_more_calls(model_search):
    tools = HandoffTools(unchanged=True)
    agent, model = make_agent(tools, model_search=model_search)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert "capture" not in tools.events
    assert report["task_checklist"]["search_submitted"] is False
    assert report["task_checklist"]["search_response_pending"] is True
    assert report["task_checklist"]["search_transition"]["confirmed"] is False


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("Unexpected browser evaluation failure", "browser_error"),
        ("TypeError: Cannot read properties of null", "script_type_error"),
        ("ReferenceError: missingVariable is not defined", "script_reference_error"),
        ("SyntaxError: Unexpected token in collector", "script_syntax_error"),
    ],
)
def test_nontransient_browser_failure_is_not_retried_as_navigation(message, code):
    tools = HandoffTools(error=PlaywrightError(message), failures=1)
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.post_search_observations == 1
    assert not tools.read_only_waits
    assert "capture" not in tools.events
    assert report["task_checklist"]["search_response_pending"] is True
    diagnostics = search_entry(report)["browser_diagnostics"]
    assert diagnostics["code"] == code
    assert diagnostics["transient"] is False
    assert diagnostics["recovered"] is False
    assert diagnostics["recovery_attempts"] == 0


def test_uncertain_search_click_timeout_retains_attempt_for_read_only_resume():
    tools = HandoffTools()
    tools.execute_error = PlaywrightTimeout("Timeout while clicking Search")
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert agent.task.pending_submission is not None
    assert report["task_checklist"]["search_transition"]["attempted"] is True
    assert report["task_checklist"]["search_transition"]["confirmed"] is False
    assert "capture" not in tools.events

    tools.execute_error = None
    resumed = agent.run()
    assert resumed["status"] == "ready"
    assert resumed["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.events.count("capture") == 1


def test_known_preclick_rejection_is_not_dispatch_or_confirmed_by_unrelated_navigation():
    tools = HandoffTools()
    tools.pre_dispatch_error = WebsiteError("The reviewed Search control changed before click")
    agent, model = make_agent(tools, model_search=True)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert "0:search" not in tools.events
    assert "capture" not in tools.events and not tools.pages
    proof = report["task_checklist"]["search_transition"]
    assert proof["attempted"] is True and proof["confirmed"] is False
    assert proof["dispatch_status"] == "not_dispatched"
    assert report["task_checklist"]["search_response_pending"] is False
    assert agent.task.pending_submission["dispatch_status"] == "not_dispatched"

    unrelated = {
        "url": "https://example.org/manually-opened-results",
        "document_id": "https://example.org/manually-opened-results",
        "frames": [{"text": "Different visible content after unrelated manual navigation."}],
        "results": {"record_count": 2, "busy": False, "no_results": False},
    }
    assert agent.task.confirm_pending_submission(unrelated) is False
    assert agent.task.submission is None


def test_mfa_after_search_stops_before_capture_and_another_paid_decision():
    tools = HandoffTools(mfa=True)
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert "capture" not in tools.events and not tools.pages
    assert "MFA" in report["guidance"]
    assert report["task_checklist"]["search_transition"]["confirmed"] is False
    assert report["task_checklist"]["search_response_pending"] is True


def test_cancellation_during_passive_retry_stops_without_another_observation_or_action():
    tools = HandoffTools(
        error=PlaywrightError("Execution context was destroyed, most likely by navigation"),
        failures=100,
    )
    tools.cancel_during_wait = True
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "paused"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.post_search_observations == 1
    assert len(tools.read_only_waits) == 1
    assert "capture" not in tools.events and not tools.pages
    assert "Cancelled" in report["guidance"]


def test_browser_diagnostics_do_not_persist_exception_text_urls_or_credentials():
    secret = "fixture-unregistered-private-value"
    tools = HandoffTools(
        error=PlaywrightError(
            "Execution context was destroyed; "
            f"cookie={secret}; https://private.example/path?token={secret}"
        ),
        failures=100,
    )
    # Deliberately not registered for ordinary redaction: the diagnostics
    # contract itself must exclude raw exception strings and arbitrary facts.
    assert not tools.secrets
    agent, _ = make_agent(tools)
    report = agent.run()

    encoded = json.dumps(report, sort_keys=True)
    assert report["status"] == "paused"
    assert secret not in encoded
    assert "private.example" not in encoded
    assert "Execution context was destroyed" not in encoded
    diagnostics = search_entry(report)["browser_diagnostics"]
    assert set(diagnostics) <= {
        "code",
        "operation",
        "transient",
        "recovery_attempts",
        "recovered",
    }
    assert diagnostics["code"] == "navigation_context"


class RedirectTools(HandoffTools):
    """The first changed URL is only a busy redirect, not the final result."""

    def __init__(self):
        super().__init__()
        self.final_results = False
        self.result_waits = 0

    def observe(self):
        observation = super().observe()
        if self.searched and not self.final_results:
            observation["url"] = "https://example.org/search/redirect"
            observation["document_id"] = "https://example.org/search/redirect"
            observation["results"] = {
                "record_count": 0,
                "busy": True,
                "no_results": False,
            }
        return observation

    def wait_for_results(self, initial, *, max_seconds):
        assert max_seconds > 0
        assert initial["results"]["busy"] is True
        self.result_waits += 1
        self.final_results = True
        self.url = "https://example.org/results/final"
        return self.observe()


def test_intermediate_search_redirect_does_not_bind_proof_before_final_result_wait():
    tools = RedirectTools()
    agent, model = make_agent(tools)
    report = agent.run()

    assert report["status"] == "ready"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events.count("0:search") == 1
    assert tools.events.count("capture") == len(tools.pages) == 1
    assert tools.result_waits == 1
    assert report["task_checklist"]["search_transition"]["confirmed"] is True
    assert report["task_checklist"]["search_response_pending"] is False
    assert report["task_checklist"]["search_transition"]["result_document_id"] == (
        "https://example.org/results/final"
    )
    assert tools.pages[0]["url"] == "https://example.org/results/final"
    assert agent.task.submission["result_url"] == "https://example.org/results/final"


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("page.evaluate: TypeError: Cannot read properties of null", "script_type_error"),
        ("page.evaluate: ReferenceError: widget is not defined", "script_reference_error"),
        ("page.evaluate: SyntaxError: Unexpected token", "script_syntax_error"),
    ],
)
def test_javascript_errors_are_safe_categories_not_transient_navigation(message, code):
    diagnostics = browser_error_diagnostics(PlaywrightError(message), "post_submit_observe")
    assert diagnostics == {
        "code": code,
        "operation": "post_submit_observe",
        "transient": False,
        "recovery_attempts": 0,
        "recovered": False,
    }


def test_safe_browser_diagnostics_excludes_arbitrary_error_facts_and_bounds_retry_count():
    supplied = {
        "code": "navigation_context",
        "operation": "post_submit_observe",
        "transient": True,
        "recovery_attempts": 100,
        "recovered": False,
        "message": "private exception text",
        "url": "https://private.example/",
        "password": "private-password",
    }
    safe = safe_browser_diagnostics(supplied)
    assert safe == {
        "code": "navigation_context",
        "operation": "post_submit_observe",
        "transient": True,
        "recovery_attempts": 0,
        "recovered": False,
    }
    assert safe_browser_diagnostics({**supplied, "operation": "arbitrary_operation"}) is None


def test_browser_control_persists_paused_diagnostics_and_clears_error_after_recovery():
    control = BrowserControl()
    persisted = []
    control.on_agent_diagnostics = persisted.append
    diagnostics = {
        "code": "navigation_context",
        "operation": "post_submit_observe",
        "transient": True,
        "recovery_attempts": 4,
        "recovered": False,
    }
    paused = {
        "run_id": "synthetic-handoff",
        "prompt_version": "browser-agent-v18.1",
        "status": "paused",
        "guidance": "Search attempted; resume for a passive re-check.",
        "calls": 1,
        "browser_diagnostics": diagnostics,
        "failure": {"code": "browser_error", "stage": "post_submit_observe"},
        "task_checklist": {
            "search_response_pending": True,
            "search_transition": {
                "attempted": True,
                "confirmed": False,
                "attempt_status": "attempted_unconfirmed",
                "dispatch_status": "action_completed",
                "private_url": "https://private.example/",
            },
        },
    }
    control.set_agent_report(paused)
    assert len(persisted) == 1
    assert persisted[0]["browser_diagnostics"] == diagnostics
    assert persisted[0]["search_transition"] == {
        "attempted": True,
        "confirmed": False,
        "response_pending": True,
        "attempt_status": "attempted_unconfirmed",
        "dispatch_status": "action_completed",
    }
    assert control.snapshot()["browser_error"] == {
        "stage": "post_submit_observe",
        **diagnostics,
    }

    recovered = {**diagnostics, "recovered": True, "recovery_attempts": 1}
    control.set_agent_report(
        {
            **paused,
            "status": "ready",
            "guidance": "Rendered source collected after passive recovery.",
            "failure": None,
            "browser_diagnostics": recovered,
            "task_checklist": {
                "search_response_pending": False,
                "search_transition": {
                    "attempted": True,
                    "confirmed": True,
                    "attempt_status": "transition_confirmed",
                    "dispatch_status": "action_completed",
                },
            },
        }
    )
    assert len(persisted) == 2
    assert persisted[-1]["browser_diagnostics"] == recovered
    assert persisted[-1]["search_transition"]["confirmed"] is True
    assert persisted[-1]["search_transition"]["response_pending"] is False
    assert control.snapshot()["browser_error"] is None
    assert control.snapshot()["agent_report"]["browser_diagnostics"] == recovered
