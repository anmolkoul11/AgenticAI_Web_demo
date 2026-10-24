"""Destination choices from real DOM metadata; no external websites or paid calls."""

import copy
import json

import pytest
from test_browser_agent import FakeDecider, FakeTools, controls, decision, tools_for
from test_browser_agent import agent_page as shared_agent_page
from test_destination_selection import autocomplete_markup

from agentic_web_demo.browser_agent import AGENT_OBSERVATION, BrowserAgent
from agentic_web_demo.browser_task import TaskLedger


@pytest.fixture
def agent_page(request):
    yield from shared_agent_page.__wrapped__(request)


@pytest.mark.parametrize("primary", [
    "<span style='display:block'>New York</span><span>New York, United States of America</span>",
    "<span style='display:block'><strong>New</strong> York</span><span>New York, United States of America</span>",
    "<span><span style='display:block'>New York</span><span>New York, United States of America</span></span>",
])
def test_visible_complete_option_label_precedes_aggregate_accessible_name(agent_page, primary):
    agent_page.set_content(
        """<form><input name=destination role=combobox aria-label=Destination
          aria-controls=destinations aria-expanded=true value='New York'>
        <ul id=destinations role=listbox>
          <li role=option aria-label='New York New York, United States of America'
            onclick="document.querySelector('input').value=
              'New York, New York, United States of America';
              document.querySelector('input').setAttribute('aria-expanded','false');
              document.querySelector('ul').hidden=true">
            """
        + primary
        + """
          </li></ul></form>"""
    )
    tools = tools_for(agent_page)
    before = tools.observe()
    field = next(item for item in controls(before) if item["role"] == "combobox")
    option = next(item for item in controls(before) if item["role"] == "option")
    assert option["id"] in field["option_ids"]
    assert option["option_primary"] == "New York"
    assert "United States of America" in option["label"]

    task = TaskLedger("Find hotels in New York")
    task.observe(before)
    action = decision("click", option["id"], purpose="set_field")
    task.before_action(option, action, before)
    outcome = tools.execute(action)
    task.remember_action(option, outcome, action, before)
    after = tools.observe()
    task.observe(after)
    check = next(item for item in task.checks if item["field"] == "destination")
    assert check["status"] == "verified"
    assert check["observed"] == "New York, New York, United States of America"
    assert check.get("next_action") != "fill"


@pytest.mark.parametrize("parent", [False, True])
def test_existing_leading_text_option_keeps_primary_and_commits_canonical_value(agent_page, parent):
    agent_page.set_content(autocomplete_markup(parent, canonical=True))
    tools = tools_for(agent_page)
    before = tools.observe()
    field = next(item for item in controls(before) if item.get("name") == "destination")
    option = next(item for item in controls(before) if item["id"] in field["option_ids"])
    assert option["option_primary"] == "New York"
    task = TaskLedger("Find hotels in New York")
    task.observe(before)
    action = decision("click", option["id"], purpose="set_field")
    task.before_action(option, action, before)
    task.remember_action(option, tools.execute(action), action, before)
    task.observe(tools.observe())
    check = next(item for item in task.checks if item["field"] == "destination")
    assert check["status"] == "verified"
    assert check["observed"] == "New York, New York, United States of America"


@pytest.mark.parametrize(
    "markup,expected",
    [
        (
            "<span style='display:block'>JFK <strong>New York</strong> Airport</span><span>United States</span>",
            "JFK New York Airport",
        ),
        ("<strong>New</strong> York Airport", "New York Airport"),
        (
            "<span style='display:block'><strong>New</strong> York Central Park</span><span>United States</span>",
            "New York Central Park",
        ),
    ],
)
def test_partial_search_highlights_do_not_become_the_primary_option(agent_page, markup, expected):
    agent_page.set_content(
        "<input role=combobox aria-label=Destination aria-expanded=true aria-controls=choices>"
        "<ul id=choices role=listbox><li role=option>" + markup + "</li></ul>"
    )
    option = next(item for item in controls(tools_for(agent_page).observe())
                  if item["role"] == "option")
    assert option["option_primary"] == expected
    assert option["option_primary"] not in {"New", "New York"}


@pytest.mark.parametrize("markup", [
    "<span>New York</span><span> Central Park</span>",
    "New York <span>Central Park</span>",
    "<span><span>New York</span><span> Central Park</span></span>",
])
@pytest.mark.parametrize("label", ["", " aria-label='New York Central Park'"])
def test_inline_name_continuations_are_not_invented_subtitle_boundaries(agent_page, markup, label):
    agent_page.set_content(
        "<input role=combobox aria-label=Destination aria-expanded=true aria-controls=choices>"
        "<ul id=choices role=listbox><li role=option" + label + ">" + markup + "</li></ul>"
    )
    option = next(item for item in controls(tools_for(agent_page).observe())
                  if item["role"] == "option")
    assert option["option_primary"] == "New York Central Park"


class DestinationTools(FakeTools):
    def __init__(self, value="New York", expanded="true"):
        super().__init__()
        self.value, self.expanded = value, expanded

    def observe(self):
        self.events.append("observe")
        field = {
            "id": "0:destination", "tag": "INPUT", "type": "text", "role": "combobox",
            "name": "destination", "label": "Destination", "value": self.value,
            "selection_required": True, "expanded": self.expanded, "option_ids": [],
        }
        self.references = {field["id"]: (None, None, field)}
        return {
            "url": "https://example.org/", "document_id": "start",
            "frames": [{"controls": [field], "text": "Destination search"}],
        }


def test_repeated_same_value_fills_do_not_run_or_erase_selection_state():
    tools = DestinationTools()
    model = FakeDecider([decision("fill", "0:destination", "New York") for _ in range(3)])
    agent = BrowserAgent(tools, model, "Find hotels in New York")
    report = agent.run()
    assert report["status"] == "paused" and report["calls"] == 3
    assert tools.events.count("fill") == 0
    skipped = [item for item in report["actions"] if item["status"] == "fill_skipped"]
    assert len(skipped) == 2
    assert all(item["observed"] == "New York" for item in skipped)
    assert "Repeated fill" in report["guidance"]


def test_different_unverified_destination_can_still_be_filled():
    tools = DestinationTools("Boston", "false")
    model = FakeDecider([
        decision("fill", "0:destination", "New York"),
        decision("pause", evidence="Inspect the destination suggestions"),
    ])
    report = BrowserAgent(tools, model, "Find hotels in New York").run()
    assert tools.events.count("fill") == 1
    assert report["actions"][0]["status"] != "fill_skipped"


def test_verified_canonical_destination_is_not_overwritten_by_original_short_request():
    tools = DestinationTools("New York, New York, United States of America", "false")
    model = FakeDecider([
        decision("fill", "0:destination", "New York"),
        decision("pause", evidence="Inspect the remaining controls"),
    ])
    agent = BrowserAgent(tools, model, "Find hotels in New York")
    before = tools.observe()
    typed = copy.deepcopy(before)
    field = typed["frames"][0]["controls"][0]
    field.update(value="New York", expanded="true", option_ids=["0:choice"])
    option = {
        "id": "0:choice", "tag": "LI", "role": "option", "option_primary": "New York",
        "label": "New York New York, United States of America",
        "text": "New York New York, United States of America",
    }
    typed["frames"][0]["controls"].append(option)
    agent.task.observe(typed)
    choice = decision("click", "0:choice", purpose="set_field")
    agent.task.remember_action(option, {"status": "action_performed"}, choice, typed)
    agent.task.observe(before)
    report = agent.run()
    assert tools.events.count("fill") == 0
    assert report["actions"][0]["status"] == "fill_skipped"
    check = next(item for item in report["task_checklist"]["requirements"]
                 if item["field"] == "destination")
    assert check["status"] == "verified"
    assert check["observed"] == tools.value


def test_autocomplete_diagnostics_report_ownership_and_focus_without_source_values(agent_page):
    agent_page.set_content("""<input name=destination role=combobox aria-label=Destination
      aria-expanded=true aria-controls=places value='private-entered-value'>
      <ul id=places role=listbox><li role=option>Private choice label</li></ul>
      <ul role=listbox><li role=option>Unrelated private choice</li></ul>""")
    agent_page.locator("input").focus()
    observed = agent_page.evaluate(AGENT_OBSERVATION, "form")
    diagnostics = observed["autocomplete_diagnostics"]
    field = next(item for item in observed["controls"] if item["name"] == "destination")
    assert diagnostics["field_count"] == 1
    assert diagnostics["visible_listbox_count"] == 2
    assert diagnostics["visible_option_count"] == 2
    assert diagnostics["owned_option_count"] == 1
    assert diagnostics["fields"] == [{
        "control_id": field["id"], "focused": True, "expanded": "true",
        "controlled_popup_count": 1, "visible_controlled_popup_count": 1,
        "owned_option_count": 1, "association": "explicit_aria",
    }]
    assert len(field["option_ids"]) == 1
    serialized = json.dumps(diagnostics)
    assert "private" not in serialized.casefold()
    assert "Destination" not in serialized
    assert "value" not in serialized and "label" not in serialized


def test_autocomplete_diagnostics_distinguish_hidden_popup_from_missing_association(agent_page):
    agent_page.set_content("""<input name=destination role=combobox aria-label=Destination
      aria-expanded=false aria-controls=places value='New York'>
      <ul id=places role=listbox hidden><li role=option>New York</li></ul>""")
    observed = agent_page.evaluate(AGENT_OBSERVATION, "form")
    diagnostics = observed["autocomplete_diagnostics"]
    assert diagnostics["visible_listbox_count"] == 0
    assert diagnostics["visible_option_count"] == 0
    assert diagnostics["owned_option_count"] == 0
    assert diagnostics["fields"][0]["controlled_popup_count"] == 1
    assert diagnostics["fields"][0]["visible_controlled_popup_count"] == 0
    assert diagnostics["fields"][0]["association"] == "explicit_aria"

    agent_page.locator("input").evaluate("e=>e.removeAttribute('aria-controls')")
    unowned = agent_page.evaluate(AGENT_OBSERVATION, "form")
    assert unowned["autocomplete_diagnostics"]["fields"][0]["association"] == "unresolved"
    assert unowned["autocomplete_diagnostics"]["fields"][0]["controlled_popup_count"] == 0


def test_autocomplete_diagnostics_follow_focused_field_into_open_shadow_root(agent_page):
    agent_page.set_content("<div id=host></div>")
    agent_page.evaluate("""() => {
      const root=document.getElementById('host').attachShadow({mode:'open'});
      const field=document.createElement('input');
      field.name='destination'; field.setAttribute('role','combobox');
      field.setAttribute('aria-controls','places'); field.setAttribute('aria-expanded','true');
      const choices=document.createElement('ul'); choices.id='places';
      choices.setAttribute('role','listbox');
      const option=document.createElement('li'); option.setAttribute('role','option');
      option.textContent='New York'; choices.append(option);
      root.append(field,choices); field.focus();
    }""")
    observed = agent_page.evaluate(AGENT_OBSERVATION, "form")
    field = next(item for item in observed["controls"] if item["name"] == "destination")
    diagnostics = observed["autocomplete_diagnostics"]
    assert diagnostics["field_count"] == diagnostics["owned_option_count"] == 1
    assert diagnostics["fields"][0]["focused"]
    assert diagnostics["fields"][0]["association"] == "explicit_aria"
    assert len(field["option_ids"]) == 1


def test_fresh_observation_removes_old_references_from_newly_hidden_choices(agent_page):
    agent_page.set_content("""<input name=destination role=combobox aria-label=Destination
      aria-expanded=true aria-controls=places value='New York'>
      <ul id=places role=listbox><li role=option>New York</li></ul>
      <button id=hidden data-agentic-loop-id=0 hidden>Old hidden button</button>""")
    before = agent_page.evaluate(AGENT_OBSERVATION, "form")
    assert len(next(item for item in before["controls"]
                    if item["name"] == "destination")["option_ids"]) == 1
    assert agent_page.locator("#hidden").get_attribute("data-agentic-loop-id") is None
    agent_page.locator("ul").evaluate("e=>e.hidden=true")
    after = agent_page.evaluate(AGENT_OBSERVATION, "form")
    assert not next(item for item in after["controls"]
                    if item["name"] == "destination")["option_ids"]
    assert agent_page.locator('[role="option"]').get_attribute("data-agentic-loop-id") is None
    current_ids = agent_page.locator("[data-agentic-loop-id]").evaluate_all(
        "nodes=>nodes.map(e=>e.getAttribute('data-agentic-loop-id'))"
    )
    assert len(current_ids) == len(set(current_ids)) == len(after["controls"])

