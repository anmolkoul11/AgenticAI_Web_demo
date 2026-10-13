"""Compact dashboard regressions. No real model/site requests; browsers are opt-in."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS


def workspace_navigation_source():
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    declaration = "function showView("
    # The function also has an indented data-view loop. Stop only at the
    # top-level event binding after the complete function, not its inner loop.
    boundary = '\nfor (const button of document.querySelectorAll("[data-view]")) button.onclick'
    assert declaration in script, "Workspace navigation function was not found"
    body, separator, _ = script.split(declaration, 1)[1].partition(boundary)
    assert separator, "Workspace navigation event-binding boundary was not found"
    assert body.rstrip().endswith("}"), "Workspace navigation function is incomplete"
    return declaration + body


def test_motion_toggle_is_removed_and_active_animation_is_unconditional():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    helper = (ASSETS / "ui_updates.js").read_text(encoding="utf-8")
    assert "web-motion" not in html + helper
    assert "refreshProgressMotion" not in helper
    assert "if (running)" in helper and "element.animate(" in helper


def test_workspace_navigation_does_not_scroll_to_a_heading_or_background_message():
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    navigation = workspace_navigation_source()
    assert "scrollIntoView" not in navigation
    assert "focus({preventScroll: true})" in navigation
    assert 'window.scrollTo({top: 0, left: 0, behavior: "instant"})' in navigation
    message = script.split('function message(text = "")', 1)[1].split("async function api", 1)[0]
    assert "scroll" not in message


@pytest.fixture
def compact_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_only_one_task_surface_is_visible_and_settings_are_closed(compact_ui):
    result = compact_ui.evaluate("""() => ({
      visible:[...studioPanels].filter(([,p]) => !p.hidden).map(([name]) => name),
      selected:[...studioTabButtons].filter(([,b]) => b.getAttribute('aria-selected')==='true')
        .map(([name]) => name),
      settings:advanced.open, browser:advanced.contains($('web-browser-mode')),
      fields:advanced.contains($('web-output-fields')),
      permissionOutside:!advanced.contains($('web-normal-confirm')),
      reviewSettings:reviewDetails.open, warnings:reviewWarnings.open
    })""")
    assert result == {
        "visible": ["source"],
        "selected": ["source"],
        "settings": False,
        "browser": True,
        "fields": True,
        "permissionOutside": True,
        "reviewSettings": False,
        "warnings": False,
    }


def test_step_navigation_preserves_inputs_and_makes_no_api_calls(compact_ui):
    compact_ui.fill("#web-urls", "https://news.example.org/")
    compact_ui.fill("#web-request", "Find sports records")
    compact_ui.get_by_role("tab", name="2. Workflow").click()
    compact_ui.get_by_role("tab", name="3. Results").click()
    compact_ui.get_by_role("button", name="Back to source setup", exact=True).click()
    assert compact_ui.input_value("#web-urls") == "https://news.example.org/"
    assert compact_ui.input_value("#web-request") == "Find sports records"
    assert compact_ui.evaluate("studioStep") == "source"
    assert compact_ui.evaluate("window.fixtureCalls") == []


def test_keyboard_tabs_and_background_progress_do_not_replace_user_view(compact_ui):
    compact_ui.get_by_role("tab", name="1. Source").focus()
    compact_ui.keyboard.press("End")
    assert compact_ui.evaluate("studioStep") == "results"
    compact_ui.evaluate("""() => renderWorkflow({kind:'custom-plan',status:'running',
      stages:[{stage:'extract_content'}]},{state:'captured'})""")
    assert compact_ui.evaluate("studioStep") == "results"
    compact_ui.keyboard.press("Home")
    assert compact_ui.evaluate("studioStep") == "source"
    assert compact_ui.evaluate("window.fixtureCalls") == []


def test_preview_results_and_back_to_review_are_local_actions(compact_ui):
    compact_ui.evaluate("""() => {
      webTable([{listing_id:'record-1',name:'Source record',source_url:'https://news.example.org/'}],
        ['listing_id','name','source_url']);
      setStudioStep('work');
    }""")
    compact_ui.get_by_role("button", name="Preview results", exact=True).click()
    assert compact_ui.locator(".record-card").is_visible()
    compact_ui.get_by_role("button", name="Back to review", exact=True).click()
    assert compact_ui.evaluate("studioStep") == "work"
    assert compact_ui.evaluate("window.fixtureCalls") == []


def test_invalid_required_setting_opens_its_disclosure(compact_ui):
    compact_ui.evaluate("""() => {
      setStudioStep('work'); $('web-limit').dispatchEvent(new Event('invalid'));
    }""")
    assert compact_ui.evaluate("studioStep") == "source"
    assert compact_ui.evaluate("advanced.open") is True


@pytest.mark.parametrize("view", ["studio", "history", "connection"])
def test_workspace_tabs_open_at_the_top_not_below_navigation(compact_ui, view):
    script_errors = []
    compact_ui.on("pageerror", lambda error: script_errors.append(str(error)))
    compact_ui.add_script_tag(
        content="let activeView='custom',isAdmin=false; "
        + workspace_navigation_source()
        + "document.querySelectorAll('[data-view]').forEach(b => "
        + "b.onclick=() => showView(b.dataset.view,true));"
    )
    assert compact_ui.evaluate("typeof showView") == "function", script_errors
    assert not script_errors, script_errors
    compact_ui.evaluate("window.scrollTo(0,300)")
    compact_ui.locator(f'[data-view="{view}"]').click()
    assert not script_errors, script_errors
    assert compact_ui.evaluate("window.scrollY") == 0
    assert compact_ui.locator(f'[data-page="{view}"]').is_visible()
    assert compact_ui.evaluate("window.fixtureCalls") == []
