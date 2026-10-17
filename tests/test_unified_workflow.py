"""Automatic workflow contracts; no browser, model, or account requests."""

import pytest
from pydantic import ValidationError

from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_extract import WebsiteInput
from agentic_web_demo.custom_fetch import WebsiteError


def automatic_input(**changes):
    values = {
        "source": "browser",
        "workflow_mode": "automatic",
        "urls": ["https://example.org/"],
        "instructions": "Find relevant records and include their source URLs.",
        "login_mode": "none",
        "agent_confirmed": True,
        "authorized": True,
        "allow_model_api": True,
        **changes,
    }
    return WebsiteInput.model_validate(values)


def ready_control(**changes):
    control = BrowserControl()
    control.configure_workflow(automatic_input(**changes))
    control.update("waiting", "Ready")
    return control


def test_manual_contract_remains_default_and_does_not_start_an_agent():
    values = WebsiteInput(urls=["https://example.org/"], authorized=True, allow_model_api=True)
    control = BrowserControl()
    control.configure_workflow(values)
    control.update("waiting", "Ready")
    assert values.workflow_mode == "manual"
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()
    assert control.snapshot()["automatic_start"] == "disabled"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"agent_confirmed": False}, "explicit paid agent consent"),
        ({"instructions": "   "}, "complete task"),
        ({"source": "public"}, "LangGraph browser source"),
        ({"source": "paste"}, "LangGraph browser source"),
        ({"framework": "crewai"}, "LangGraph browser source"),
    ],
)
def test_automatic_mode_requires_supported_source_task_and_consent(changes, message):
    with pytest.raises(ValidationError, match=message):
        automatic_input(**changes)


@pytest.mark.parametrize("field", ["agent_confirmed", "agent_visual_confirmed"])
def test_manual_submission_cannot_silently_authorize_an_initial_agent(field):
    with pytest.raises(ValidationError, match="Initial agent authorization"):
        WebsiteInput(
            urls=["https://example.org/"],
            authorized=True,
            allow_model_api=True,
            **{field: True},
        )


def test_automatic_start_reuses_authorization_once_and_preserves_visual_choice():
    control = ready_control(agent_visual_confirmed=True)
    assert control.maybe_auto_start()
    assert control.agent_requested.is_set()
    assert control.agent_visual_enabled
    snapshot = control.snapshot()
    assert snapshot["state"] == "agent_running"
    assert snapshot["workflow_mode"] == "automatic"
    assert snapshot["automatic_start"] == "started"
    assert not control.maybe_auto_start()


def test_automatic_start_waits_for_explicit_authentication_handoff():
    control = ready_control(login_mode="manual")
    assert not control.maybe_auto_start()
    control.require_authentication("Complete sign-in in the original browser")
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()
    control.command("resume_login")
    assert not control.maybe_auto_start()
    control.authentication.update(status="operator_confirmed", verified=False)
    control.update("waiting", "Operator confirmed sign-in")
    assert control.maybe_auto_start()
    assert control.authentication["verified"] is False


@pytest.mark.parametrize("state", ["starting", "verification_required", "link_review"])
def test_automatic_start_waits_until_browser_is_ready(state):
    control = ready_control()
    control.update(state, "Not ready")
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()


def test_automatic_consent_does_not_resume_after_pause_or_manual_takeover():
    control = ready_control()
    assert control.maybe_auto_start()
    control.agent_requested.clear()
    control.set_agent_report({"status": "paused", "guidance": "Choose a value", "calls": 4})
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()
    control.command("agent_manual")
    assert control.snapshot()["automatic_start"] == "manual"
    assert not control.maybe_auto_start()
    assert control.agent_report["calls"] == 4


def test_manual_takeover_before_initial_start_consumes_pending_automation():
    control = ready_control()
    control.command("agent_manual")
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()


@pytest.mark.parametrize("action", ["capture", "hotel_plan", "plan", "discover"])
def test_accepted_manual_collection_command_consumes_initial_automation(action):
    control = ready_control()
    control.command(action)
    assert control.snapshot()["automatic_start"] == "manual"
    control.update("waiting", "Manual action finished or review dismissed")
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()


@pytest.mark.parametrize("action", ["approve", "hotel_approve", "approve_links"])
def test_invalid_manual_command_does_not_consume_initial_automation(action):
    control = ready_control()
    with pytest.raises(WebsiteError):
        control.command(action)
    assert control.snapshot()["automatic_start"] == "pending"
    assert control.maybe_auto_start()


def test_invalid_review_authorization_does_not_consume_initial_automation():
    control = ready_control()
    control.update("hotel_review", "Not a confirmed review")
    with pytest.raises(WebsiteError, match="Prepare a hotel search"):
        control.command("hotel_approve")
    assert control.snapshot()["automatic_start"] == "pending"


def test_manual_takeover_wins_if_it_races_automatic_command(monkeypatch):
    control = ready_control()
    original_command = control.command

    def take_over_then_start(action, **kwargs):
        original_command("agent_manual")
        return original_command(action, **kwargs)

    monkeypatch.setattr(control, "command", take_over_then_start)
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()
    assert control.snapshot()["automatic_start"] == "manual"


@pytest.mark.parametrize("condition", ["cancelled", "expired"])
def test_cancelled_or_expired_session_does_not_start_automatic_agent(condition):
    control = ready_control()
    if condition == "cancelled":
        control.cancel.set()
    else:
        control.alive = lambda: False
    assert not control.maybe_auto_start()
    assert not control.agent_requested.is_set()


def test_pause_waits_for_safe_boundary_and_resume_keeps_report_budget():
    control = ready_control()
    assert control.maybe_auto_start()
    control.command("agent_pause")
    assert control.agent_pause_requested.is_set()
    assert control.snapshot()["state"] == "agent_pausing"
    control.set_agent_report({"status": "running", "guidance": "Model returned", "calls": 5})
    assert control.snapshot()["state"] == "agent_pausing"
    control.set_agent_report({"status": "paused", "guidance": "Paused by user", "calls": 5})
    with pytest.raises(WebsiteError, match="Authorize"):
        control.command("agent_resume")
    control.command("agent_resume", agent_confirmed=True)
    assert not control.agent_pause_requested.is_set()
    assert control.agent_report["calls"] == 5
    assert not control.agent_visual_enabled


def test_browser_controls_do_not_share_initial_consent_or_pause_state():
    first = ready_control(agent_visual_confirmed=True)
    second = BrowserControl()
    first.maybe_auto_start()
    first.command("agent_pause")
    second.update("waiting", "Other account's source")
    assert not second.maybe_auto_start()
    assert not second.agent_pause_requested.is_set()
    assert not second.agent_visual_enabled
