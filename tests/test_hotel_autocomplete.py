"""Autocomplete selection regressions; no external website or paid model calls."""

import copy
from types import SimpleNamespace

import pytest
from test_complete_hotel_search import DYNAMIC_FORM, REQUEST
from test_dashboard_live_updates import live_ui as shared_ui
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo import hotel_search
from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.hotel_search import (
    HotelSearchDriver,
    match_destination_suggestions,
    place_matches,
    prepare_hotel_search,
    run_hotel_search,
)


def option(identifier, name, *, kind="unknown"):
    return {
        "id": str(identifier),
        "primary": name,
        "name_candidates": [name],
        "kind": kind,
        "text": name,
        "enabled": True,
    }


@pytest.mark.parametrize("name", ["New York", "New York City", "NYC", "New\u00a0York"])
def test_explicit_city_aliases_are_not_substring_matching(name):
    assert place_matches(name, "New York")
    assert not place_matches("New York-New York Las Vegas", "New York")
    assert not place_matches("New York JFK Airport", "New York")
    assert not place_matches("New", "New York")


def test_matching_city_takes_precedence_over_same_named_region():
    city, region = option(1, "New York City", kind="city"), option(2, "New York", kind="region")
    chosen, diagnostics = match_destination_suggestions([region, city], "New York")
    assert chosen == city
    assert diagnostics["matching_count"] == 2 and diagnostics["preferred_count"] == 1


def test_distinct_untyped_rows_and_distinct_cities_remain_ambiguous():
    for kind in ("unknown", "city"):
        first, second = option(1, "New York", kind=kind), option(2, "New York", kind=kind)
        chosen, diagnostics = match_destination_suggestions([first, second], "New York")
        assert chosen is None and diagnostics["reason"] == "ambiguous_matches"


def test_disabled_and_nonmatching_suggestions_are_not_selected():
    disabled = {**option(1, "New York"), "enabled": False}
    chosen, diagnostics = match_destination_suggestions(
        [disabled, option(2, "New York-New York Las Vegas")], "New York"
    )
    assert chosen is None and diagnostics["matching_count"] == 0


def fake_driver(monkeypatch, options):
    clock, events = [0.0], []
    monkeypatch.setattr(hotel_search.time, "monotonic", lambda: clock[0])
    page = SimpleNamespace(
        url="https://example.org/",
        wait_for_timeout=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000),
    )
    driver = HotelSearchDriver(page, "https://example.org")
    driver.booking = True
    state = {
        "destination": {"value": ""},
        "suggestions": [],
        "destination_selected": False,
        "destination_diagnostics": {"matching_fields": 1},
    }

    def inventory():
        if events and not state["destination_selected"]:
            state["suggestions"] = options(clock[0])
        return state

    def act(control, value=None):
        if value is not None:
            events.append(("fill", value))
            state["destination"]["value"] = value
        else:
            events.append(("choose", control["primary"]))
            state.update(destination_selected=True, suggestions=[])
            state["destination"]["value"] = control["primary"]

    driver.inventory, driver.act = inventory, act
    return driver, events


def test_async_suggestions_settle_without_repeating_fill_or_click(monkeypatch):
    driver, events = fake_driver(
        monkeypatch,
        lambda now: [
            option(1, "New York City", kind="city") if now >= 0.3 else option(2, "Newark")
        ],
    )
    assert driver.destination("New York") == "New York City"
    assert events == [("fill", "New York"), ("choose", "New York City")]
    assert driver.destination_suggestions["selected"]["primary"] == "New York City"


def test_ambiguous_selection_keeps_verified_text_separate_from_selected_location(monkeypatch):
    driver, events = fake_driver(
        monkeypatch, lambda _: [option(1, "New York"), option(2, "New York")]
    )
    with pytest.raises(WebsiteError, match="ambiguous") as caught:
        run_hotel_search(driver, prepare_hotel_search(REQUEST))
    report = caught.value.navigation_result
    assert events == [("fill", "New York")]
    assert report["destination_suggestions"]["preferred_count"] == 2
    assert report["destination_input_observation"]["observed"] == "New York"
    assert not report["destination_input_observation"]["selection_confirmed"]
    assert report["actions"][0]["status"] == "input_verified"
    assert report["requirements"][0]["status"] == "unconfirmed"
    assert not report["submitted"] and report["stage"] == "destination"


@pytest.fixture
def autocomplete_page(request):
    yield from shared_local_page.__wrapped__(request)


def test_nested_row_wrapper_and_option_are_one_candidate(autocomplete_page):
    markup = DYNAMIC_FORM.replace(
        '<li role=option onclick="selectCity(this)">',
        '<li data-testid=autocomplete-result data-dest-type=city onclick="selectCity(this)">'
        "<div role=option>",
    ).replace(
        "<strong>New York</strong><span>United States</span></li>",
        "<span data-testid=autocomplete-result-label><strong>New</strong> York</span>"
        "<span>New York, United States of America</span></div></li>",
    )
    autocomplete_page.set_content(markup)
    autocomplete_page.evaluate("options.hidden=false")
    driver = HotelSearchDriver(autocomplete_page, "https://example.org")
    driver.booking = True
    state = driver.inventory()
    assert len(state["suggestions"]) == 1
    assert state["suggestions"][0]["primary"] == "New York"
    assert "New" not in state["suggestions"][0]["name_candidates"]
    report = run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert report["status"] == "search_completed"
    assert report["destination_suggestions"]["selected"]["kind"] == "city"


def test_input_owned_popup_excludes_unrelated_page_options(autocomplete_page):
    autocomplete_page.set_content(DYNAMIC_FORM + "<div role=option>New York</div>")
    autocomplete_page.locator("[name=ss]").evaluate("e=>e.setAttribute('aria-controls','options')")
    autocomplete_page.evaluate("options.hidden=false")
    state = HotelSearchDriver(autocomplete_page, "https://example.org").inventory()
    assert state["suggestion_scope"] == "input_popup"
    assert len(state["suggestions"]) == 1


def test_partial_bold_text_does_not_turn_airport_name_into_city(autocomplete_page):
    autocomplete_page.set_content("""<form>
      <input name=ss aria-label=Destination aria-controls=results>
      <ul id=results><li role=option data-dest-type=airport>
        <span data-testid=autocomplete-result-label>JFK <strong>New York</strong> Airport</span>
      </li></ul><button>Search</button>
    </form>""")
    state = HotelSearchDriver(autocomplete_page, "https://example.org").inventory()
    chosen, diagnostics = match_destination_suggestions(state["suggestions"], "New York")
    assert chosen is None and diagnostics["matching_count"] == 0


def test_alias_is_retained_through_preflight_and_result_observation(autocomplete_page):
    markup = DYNAMIC_FORM.replace("<strong>New York</strong>", "<strong>New York City</strong>")
    markup = markup.replace(".value='New York';", ".value='New York City';")
    autocomplete_page.set_content(markup)
    driver = HotelSearchDriver(autocomplete_page, "https://example.org")
    driver.booking = True
    report = run_hotel_search(driver, prepare_hotel_search(REQUEST))
    assert report["status"] == "search_completed"
    assert report["actions"][0]["observed"] == "New York City"


@pytest.fixture
def autocomplete_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_ui_shows_actual_choices_and_match_counts(autocomplete_ui):
    _, diagnostics = match_destination_suggestions([option(1, "Newark")], "New York")
    autocomplete_ui.evaluate(
        """matching => {
      showNavigationEvidence({navigation_result:{status:'needs_review',actions:[],requirements:[],
        destination_suggestions:matching},navigation_history:[]});setStudioStep('work');
    }""",
        copy.deepcopy(diagnostics),
    )
    autocomplete_ui.get_by_text("Destination suggestion matching", exact=True).click()
    assert autocomplete_ui.get_by_text(
        "Newark (unknown) — name did not match", exact=False
    ).is_visible()
    assert autocomplete_ui.get_by_text("0 name match(es)", exact=False).is_visible()
    assert autocomplete_ui.evaluate("window.fixtureCalls") == []
