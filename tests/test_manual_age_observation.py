"""Opt-in local DOM cases for manual age readback; no paid API/site calls."""

from pathlib import Path

import pytest
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo.browser_agent import AGENT_OBSERVATION


@pytest.fixture
def age_page(request):
    yield from shared_local_page.__wrapped__(request)


@pytest.fixture(params=["python_observer", "extension_observer"])
def age_observe(request, age_page):
    def observe(html):
        age_page.set_content("<main>" + html + "</main>")
        if request.param == "python_observer":
            return age_page.evaluate(AGENT_OBSERVATION, "form")
        source = (Path(__file__).resolve().parents[1] / "extensions" /
                  "page-capture" / "agent_observe.js").read_text(encoding="utf-8")
        return age_page.evaluate("() => {\n" + source +
                                 "\nreturn globalThis.agenticObserve('form');\n}")

    return observe


@pytest.mark.parametrize("markup,value,source", [
    ('<button role="combobox" aria-label="Age of child 1" '
     'aria-valuetext="7 years" aria-valuenow="7">Choose age</button>',
     "7 years", "aria-valuetext"),
    ('<button role="combobox" aria-label="Age of child 1" aria-valuenow="0"></button>',
     "0", "aria-valuenow"),
    ('<button role="combobox" aria-label="Age of child 1"><span>7 years</span>'
     '<span aria-hidden="true">Open options</span></button>', "7 years", "rendered_text"),
    ('<div role="combobox" aria-label="Age of child 1"><div role="listbox">'
     '<div role="option" aria-selected="true">7 years</div>'
     '<div role="option" aria-selected="false">8 years</div></div></div>',
     "7 years", "selected_option"),
    ('<button role="combobox" aria-label="Age of child 1" aria-controls="ages"></button>'
     '<div id="ages" role="listbox"><div role="option" aria-selected="true" '
     'aria-label="7 years"><span>7 years</span><span>Extra option description</span>'
     '</div></div>', "7 years", "selected_option"),
    ('<button role="combobox" aria-label="Age of child 1" aria-owns="selected"></button>'
     '<div id="selected" role="option" aria-selected="true">0 years old</div>',
     "0 years old", "selected_option"),
])
def test_custom_age_reads_only_observed_value(age_observe, markup, value, source):
    field = next(item for item in age_observe(markup)["controls"]
                 if item["role"] == "combobox")
    assert field["value"] == value
    assert field["selected_label"] == value
    assert field["value_source"] == source
    assert field["selection_placeholder"] is False


@pytest.mark.parametrize("markup", [
    '<button role="combobox" aria-label="Age of child 1">Select age</button>'
    '<div role="listbox"><div role="option" aria-selected="true">7 years</div></div>',
    '<button role="combobox" aria-label="Age of child 1" aria-controls="ages" '
    'aria-activedescendant="highlighted"></button><div id="ages" role="listbox">'
    '<div id="highlighted" role="option" aria-selected="false">7 years</div></div>',
    '<div role="combobox" aria-label="Age of child 1">'
    '<div role="option" aria-selected="true">7 years</div>'
    '<div role="option" aria-selected="true">8 years</div></div>',
    '<div role="combobox" aria-label="Age of child 1">'
    '<div role="option" aria-selected="true">7 years is the recommended age</div></div>',
    '<button role="combobox" aria-label="Age of child 1">7 years is recommended</button>',
    '<div role="combobox" aria-label="Age of child 1">'
    '<input type="password" value="private-password"><input type="email" '
    'value="private@example.org"><div role="option">7 years</div></div>',
])
def test_unknown_custom_age_does_not_use_highlight_or_option_prose(age_observe, markup):
    observation = age_observe(markup.replace('role="combobox"',
                                              'role="combobox" aria-required="true"', 1))
    field = next(item for item in observation["controls"] if item["role"] == "combobox")
    assert field["value"] == "" and field["value_source"] == ""
    assert field["selected_label"] == ""
    assert field["value_missing"] is True and field["selection_placeholder"] is True
    assert "private-password" not in str(observation)
    assert "private@example.org" not in str(observation)


def test_custom_age_validation_preserves_invalid_state(age_observe):
    field = age_observe('<button role="combobox" aria-label="Age of child 1" '
                        'aria-invalid="true" aria-required="true" '
                        'aria-valuetext="7 years">7 years</button>')["controls"][0]
    assert field["value"] == "7 years" and field["invalid"] is True


def test_unrelated_combobox_keeps_existing_value_behavior(age_observe):
    field = age_observe('<button role="combobox" aria-label="Destination" '
                        'aria-valuetext="7 years">7 years</button>')["controls"][0]
    assert field["value"] == "" and "value_source" not in field


@pytest.mark.parametrize("value,label,placeholder", [
    ("-1", "Select age", True), ("unknown", "Age required", True),
    ("0", "0 years old", False), ("7", "7 years old", False),
])
def test_native_age_select_retains_option_readback(age_observe, value, label, placeholder):
    field = age_observe('<label>Age of child 1<select required><option value="' + value +
                        '" selected>' + label + '</option></select></label>')["controls"][0]
    assert field["value"] == value and field["selected_label"] == label
    assert field["selection_placeholder"] is placeholder
    assert "value_source" not in field
