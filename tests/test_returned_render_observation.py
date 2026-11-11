"""Returned hotel markup and scope cases; browser fixtures remain explicitly opt-in."""

from pathlib import Path
from datetime import date, timedelta

import pytest
from test_navigation_verification import local_page as shared_local_page

from agentic_web_demo.browser_agent import AGENT_OBSERVATION
from agentic_web_demo.browser_navigation import guest_counts, occupancy_summary_values
from agentic_web_demo.stay_scope import observed_result_scope


REQUESTED = {"destination": "New Jersey", "check_in": "2026-11-28",
             "check_out": "2026-11-30", "adults": 3, "rooms": 2, "nights": 2}


@pytest.fixture
def render_page(request):
    yield from shared_local_page.__wrapped__(request)


@pytest.fixture(params=["python_observer", "extension_observer"])
def render_observe(request, render_page):
    def observe(markup):
        render_page.set_content(markup)
        if request.param == "python_observer":
            return render_page.evaluate(AGENT_OBSERVATION, "form")
        source = (Path(__file__).resolve().parents[1] / "extensions" /
                  "page-capture" / "agent_observe.js").read_text(encoding="utf-8")
        return render_page.evaluate("() => {\n" + source +
                                    "\nreturn globalThis.agenticObserve('form');\n}")

    return observe


@pytest.mark.parametrize("hide_background", [False, True])
def test_large_calendar_keeps_committed_stay_anchors_and_selected_day(render_observe, hide_background):
    cells = []
    for offset in range(92):
        day = date(2026, 11, 1) + timedelta(days=offset)
        selected = day == date(2026, 12, 28)
        label = ("Selected " if selected else "") + day.strftime("%B %d, %Y")
        cells.append(f'<div role="gridcell" aria-label="{label}"><button data-date="{day.isoformat()}" '
                     f'aria-label="{label}" aria-selected="{str(selected).lower()}">{day.day}</button></div>')
    result = render_observe(f'<section aria-hidden="{str(hide_background).lower()}"><input aria-label="Search" value="New York">'
        '<button aria-label="Enter the date. The selected date is November 28, 2026.">Check In</button>'
        '<button aria-label="Enter the date. The selected date is November 30, 2026.">Check Out</button>'
        '<button aria-expanded="false" aria-label="Enter the number of rooms and then enter the number of guests. '
        'The selected number of rooms is 3 and the selected number of guests is 5.">Rooms/Guests 3 Rooms, 5 Guests</button></section>'
        '<div role="dialog"><div role="grid">' + ''.join(cells) + '</div></div>')
    fields = result["controls"]
    assert result["controls_truncated"] and len(fields) <= 140
    assert {item.get("date_endpoint") for item in fields if item.get("date_kind") == "opener"} == {"check_in", "check_out"}
    assert any("selected number of rooms" in item.get("label", "") for item in fields)
    assert any(item.get("date") == "2026-12-28" and item.get("selected") == "true" for item in fields)


@pytest.mark.parametrize("attribute", ["data-testid", "data-test-target", "data-automation"])
@pytest.mark.parametrize("marker", ["hotel-card", "HotelCard", "hotel-listing", "Hotel-List-Item"])
def test_explicit_hotel_record_markers_count_cards_and_exclude_card_headings(render_observe, attribute, marker):
    frame = render_observe('<main itemscope itemtype="https://schema.org/SearchResultsPage">'
                           '<h1>New Jersey Hotels</h1><div ' + attribute + '="' + marker + '">'
                           '<h2>Boston Hotels</h2><a href="/hotel/one">Hotel One</a>'
                           '<p>Displayed room details, USD 300 per night and current hotel links.</p>'
                           '</div></main>')
    assert frame["results"]["record_count"] == 1
    assert frame["results"]["headings"] == [{"text": "New Jersey Hotels", "level": 1}]


def test_hotel_record_markers_keep_leaf_and_public_content_checks(render_observe):
    frame = render_observe('<main><div data-test-target="hotel-listing">'
                           '<div data-automation="HotelCard"><a href="/hotel/one">Hotel One</a>'
                           '<p>Displayed hotel description and current USD 300 price.</p></div></div>'
                           '<nav><div data-test-target="hotel-list-item"><a href="/hotel/two">Hotel Two</a>'
                           '<p>Navigation hotel descriptions do not establish rendered results.</p></div></nav>'
                           '<div data-test-target="hotel-listing"><a href="/hotel/three">Short</a></div>'
                           '<div data-test-target="hotel-listing">Long enough description with a price '
                           'but no actual record link cannot establish a hotel result.</div></main>')
    assert frame["results"]["record_count"] == 1


@pytest.mark.parametrize("date_attribute", ["data-date", "datetime"])
def test_date_openers_retain_actual_full_date_and_endpoint(render_observe, date_attribute):
    frame = render_observe('<main><button type="button" aria-haspopup="dialog" aria-label="Check-in" '
                           + date_attribute + '="2026-11-28">Nov 28</button>'
                           '<button type="button" aria-haspopup="dialog" aria-label="Check-out" '
                           + date_attribute + '="2026-11-30">Nov 30</button></main>')
    fields = {item["label"]: item for item in frame["controls"]}
    assert fields["Check-in"]["date_kind"] == fields["Check-out"]["date_kind"] == "opener"
    assert fields["Check-in"]["date"] == "2026-11-28"
    assert fields["Check-in"]["date_endpoint"] == "check_in"
    assert fields["Check-out"]["date"] == "2026-11-30"
    assert fields["Check-out"]["date_endpoint"] == "check_out"


def test_date_openers_do_not_borrow_requested_year_or_guess_endpoint(render_observe):
    frame = render_observe('<main><button aria-haspopup="dialog" aria-label="Check-in">Nov 28</button>'
                           '<button aria-haspopup="dialog" aria-label="Dates" data-date="2026-11-30">'
                           'Nov 30</button></main>')
    fields = {item["label"]: item for item in frame["controls"]}
    assert fields["Check-in"]["date"] == ""
    assert fields["Dates"]["date"] == "2026-11-30"
    assert fields["Dates"].get("date_endpoint", "") == ""


@pytest.mark.parametrize("label,rendered,date,endpoint", [
    ("Enter the check-in date November 28, 2026", "Check In Sat, Nov 28", "2026-11-28", "check_in"),
    ("Enter the date. The selected date is Saturday, November 28, 2026.",
     "Check In Sat, Nov 28", "2026-11-28", "check_in"),
    ("Enter the check-out date: November 30, 2026.", "Nov 30", "2026-11-30", "check_out"),
    ("Enter the date; the selected date is: Monday, November 30, 2026.",
     "Check Out Mon, Nov 30", "2026-11-30", "check_out"),
])
def test_real_date_opener_accessible_labels_keep_full_source_date(render_observe, label, rendered, date, endpoint):
    field = render_observe('<main><button type="button" aria-haspopup="dialog" aria-label="' + label +
                           '"><span>' + rendered + '</span></button></main>')["controls"][0]
    assert field["date_kind"] == "opener"
    assert field["date"] == date and field["date_endpoint"] == endpoint
    assert field["selected"] == ""


@pytest.mark.parametrize("label", [
    "Enter the date. The selected date is Saturday, November 28.",
    "Enter the date. Hotel deals are available November 28, 2026.",
])
def test_date_opener_does_not_extract_year_from_missing_date_or_unrelated_prose(render_observe, label):
    field = render_observe('<main><button type="button" aria-haspopup="dialog" aria-label="' + label +
                           '"><span>Check In Sat, Nov 28</span></button></main>')["controls"][0]
    assert field["date_kind"] == "opener" and field["date"] == ""
    assert field["date_endpoint"] == "check_in"


@pytest.mark.parametrize("rendered", ["Nov 28", "Check In / Check Out Nov 28"])
def test_date_opener_endpoint_does_not_borrow_parent_or_choose_ambiguous_own_text(render_observe, rendered):
    field = render_observe('<main><section aria-label="Check-out"><p>Check-out</p>'
                           '<button type="button" aria-haspopup="dialog" '
                           'aria-label="Enter the date. The selected date is Saturday, November 28, 2026.">'
                           '<span>' + rendered + '</span></button></section></main>')["controls"][0]
    assert field["date_kind"] == "opener" and field["date"] == "2026-11-28"
    assert field.get("date_endpoint", "") == ""


def test_actual_generic_aria_date_openers_verify_the_correct_returned_endpoints(render_observe):
    frame = render_observe('<main><h1>New Jersey Hotels</h1>'
                           '<button aria-haspopup="dialog" '
                           'aria-label="Enter the date. The selected date is Saturday, November 28, 2026.">'
                           '<span>Check In Sat, Nov 28</span></button>'
                           '<button aria-haspopup="dialog" '
                           'aria-label="Enter the date. The selected date is Monday, November 30, 2026.">'
                           '<span>Check Out Mon, Nov 30</span></button>'
                           '<button aria-label="Adults 3, Children 0, Rooms 2">3 adults, 2 rooms</button>'
                           '<div data-test-target="hotel-listing"><a href="/hotel/one">Hotel One</a>'
                           '<p>Displayed hotel description, USD 300 per night and current links.</p></div></main>')
    scope = observed_result_scope(REQUESTED, {"document_id": "same-results",
                                           "frames": [frame], "results": frame["results"]})
    assert scope["status"] == "verified"
    assert scope["observed"]["check_in"] == "2026-11-28"
    assert scope["observed"]["check_out"] == "2026-11-30"


def test_single_unidentified_date_opener_never_defaults_to_checkout():
    page = returned()
    for control in page["frames"][0]["controls"][1:3]:
        control.update(label="Enter the date. The selected date is November 28, 2026.",
                       date="2026-11-28", date_endpoint="", text="Nov 28")
    scope = observed_result_scope(REQUESTED, page)
    assert scope["observed"]["check_in"] is None and scope["observed"]["check_out"] is None


def returned(occupancy="Adults 3, Children 0, Rooms 2, Guests 3"):
    return {"document_id": "same-rendered-results", "frames": [{"controls": [
        {"tag": "INPUT", "type": "text", "label": "Destination", "value": "New Jersey"},
        {"tag": "BUTTON", "label": "Check-in", "text": "Nov 28", "date_kind": "opener",
         "date": "2026-11-28", "date_endpoint": "check_in"},
        {"tag": "BUTTON", "label": "Check-out", "text": "Nov 30", "date_kind": "opener",
         "date": "2026-11-30", "date_endpoint": "check_out"},
        {"tag": "BUTTON", "label": occupancy, "expanded": "false"},
    ]}], "results": {"record_count": 2, "price_contexts": []}}


def test_returned_scope_uses_current_date_controls_and_label_before_count():
    scope = observed_result_scope(REQUESTED, returned())
    assert scope["status"] == "verified"
    dates = [item for item in scope["fields"] if item["field"] in {"check_in", "check_out"}]
    assert all(item["method"] == "returned_date_control" for item in dates)
    assert scope["observed"]["adults"] == "3" and scope["observed"]["rooms"] == "2"


def test_returned_total_guests_does_not_supply_an_adult_or_child_count():
    scope = observed_result_scope(REQUESTED, returned("Rooms 2, Guests 3"))
    assert scope["status"] == "unverified"
    assert scope["observed"]["rooms"] == "2" and scope["observed"]["adults"] is None


def test_returned_conflicting_named_counts_are_not_silently_ignored():
    scope = observed_result_scope(REQUESTED, returned("Adults 3, Rooms 2, 4 adults, Guests 4"))
    assert scope["status"] == "mismatch"
    assert scope["observed"]["adults"] == "3; 4"


def test_returned_date_control_does_not_erase_a_conflicting_full_visible_date():
    page = returned()
    page["frames"][0]["controls"][1]["label"] = "Check-in November 29, 2026"
    assert observed_result_scope(REQUESTED, page)["status"] == "mismatch"


def test_returned_date_control_needs_full_source_year_and_explicit_endpoint():
    page = returned()
    page["frames"][0]["controls"][1]["date"] = ""
    page["frames"][0]["controls"][2]["date_endpoint"] = ""
    scope = observed_result_scope(REQUESTED, page)
    assert scope["status"] == "unverified"
    assert scope["observed"]["check_in"] is None and scope["observed"]["check_out"] is None


def test_shared_observed_summary_parser_keeps_prompt_count_semantics():
    assert occupancy_summary_values("Adults 3 Children 0 Rooms 2 Guests 3") == {
        "adults": [3], "children": [0], "rooms": [2], "guests": [3],
    }
    assert guest_counts("Rooms 2, Guests 3") == {}
    assert guest_counts("3 adults and 2 rooms") == {"adults": 3, "rooms": 2}


def test_returned_price_context_keeps_label_before_count_contradictions():
    page = returned()
    page["results"]["price_contexts"] = ["USD 300 for Adults 4, Rooms 2, 2 nights"]
    scope = observed_result_scope(REQUESTED, page)
    assert scope["status"] == "mismatch"
    assert any(item["code"] == "price_context_occupancy_mismatch" for item in scope["contradictions"])


def test_returned_scope_keeps_actual_heading_quote_separate_from_input_quote():
    page = returned()
    page["results"]["headings"] = [{"level": 1, "text": "New Jersey Hotels"}]
    destination = next(item for item in observed_result_scope(REQUESTED, page)["fields"]
                       if item["field"] == "destination")
    assert destination["evidence_by_method"]["returned_results_heading"] == [
        {"value": "New Jersey", "evidence": "New Jersey Hotels"},
    ]
    assert destination["evidence_by_method"]["returned_control"] == [
        {"value": "New Jersey", "evidence": "Destination New Jersey"},
    ]
    assert destination["evidence"] == "Destination New Jersey"


def test_returned_scope_source_evidence_is_bounded_and_deduplicated():
    page = returned()
    page["results"]["headings"] = [
        {"level": 1, "text": "New Jersey Hotels"},
        {"level": 1, "text": "New Jersey Hotels"},
        {"level": 1, "text": "Hotels in New Jersey"},
        {"level": 1, "text": "New Jersey: 25 hotels found"},
    ]
    for field in observed_result_scope(REQUESTED, page)["fields"]:
        sources = field["evidence_by_method"]
        assert len(sources) <= 8
        assert all(len(entries) <= 2 for entries in sources.values())
        assert all(len(item["value"]) <= 300 and len(item["evidence"]) <= 240
                   for entries in sources.values() for item in entries)
    destination = next(item for item in observed_result_scope(REQUESTED, page)["fields"]
                       if item["field"] == "destination")
    assert destination["evidence_by_method"]["returned_results_heading"] == [
        {"value": "New Jersey", "evidence": "New Jersey Hotels"},
        {"value": "New Jersey", "evidence": "Hotels in New Jersey"},
    ]
