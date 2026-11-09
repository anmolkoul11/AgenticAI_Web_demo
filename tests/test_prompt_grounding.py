"""Literal locations must survive temporal typos and query-field aliases."""

from datetime import date

import pytest

from agentic_web_demo.browser_agent import BrowserAgent, BrowserRequirement
from agentic_web_demo.browser_navigation import requested_destination
from agentic_web_demo.browser_task import MissingFormValue, TaskLedger, literal_form_value
from test_browser_agent import FakeDecider, FakeTools, decision


REQUEST = "find hotels in new jersey form 28-30 November 2026, with 4 adults and 3 rooms"


def search_form():
    return {"url": "https://example.org/hotels", "document_id": "hotel-form", "frames": [{"controls": [
        {"id": "0:query", "tag": "INPUT", "type": "search", "label": "Search", "value": ""},
        {"id": "0:guests", "tag": "BUTTON", "type": "button", "label": "4 adults, 0 children, 3 rooms"},
    ]}]}


def test_exact_reported_prompt_keeps_destination_dates_and_original_wording():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 7))
    assert requested_destination(REQUEST) == "new jersey"
    assert task.requirements["destination"]["expected"] == "new jersey"
    assert task.requested_stay["destination"] == "new jersey"
    assert task.requested_stay["check_in"] == "2026-11-28"
    assert task.requested_stay["check_out"] == "2026-11-30"
    assert task.requested_stay["adults"] == 4 and task.requested_stay["rooms"] == 3
    assert "children" not in task.requirements
    assert task.instructions == REQUEST and task.request_error is None


@pytest.mark.parametrize("dates", ["2026-11-28 to 2026-11-30", "November 28-30, 2026"])
def test_temporal_form_is_bounded_to_a_following_date(dates):
    assert requested_destination("Find hotels in New Jersey form " + dates) == "New Jersey"
    assert requested_destination("Find hotels in New Jersey Form Museum with 4 adults") == "New Jersey Form Museum"


def test_redundant_query_alias_does_not_become_a_new_form_prerequisite():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 7))
    ignored = task.declare([BrowserRequirement(name="location_query", expected="New Jersey", application="form",
                                               request_quote="", control_id="0:query")], search_form())
    assert ignored == [{"field": "location_query", "reason": "destination_already_grounded"}]
    assert "location_query" not in task.requirements and "location_query" not in task.bindings
    assert task.requirements["destination"]["expected"] == "new jersey"


def test_category_query_is_navigation_without_removing_stay_requirements():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 7))
    original = task.requirements.copy()
    ignored = task.declare([BrowserRequirement(name="search_query", expected="hotels", application="form",
                                               request_quote="hotels", control_id="0:query")], search_form())
    assert ignored == [{"field": "search_query", "reason": "query_is_navigation"}]
    assert task.requirements == original


def test_later_canonical_destination_releases_earlier_navigation_query():
    wording = "Find hotels New Jersey from 28-30 November 2026 with 4 adults and 3 rooms"
    task = TaskLedger(wording, reference_date=date(2026, 11, 7))
    task.declare([BrowserRequirement(name="query", expected="New Jersey", application="form",
                                    request_quote="New Jersey", control_id="0:query")], search_form())
    assert "query" in task.requirements and "query" in task.bindings
    ignored = task.declare([BrowserRequirement(name="destination", expected="New Jersey", application="form",
                                               request_quote="New Jersey", control_id="0:query")], search_form())
    assert ignored == [{"field": "query", "reason": "query_is_navigation"}]
    assert "query" not in task.requirements and "query" not in task.bindings
    assert task.requested_stay["destination"] == "New Jersey"


def test_model_can_ground_a_literal_canonical_place_when_parser_cannot():
    wording = "Find hotels New Jersey from 28-30 November 2026 with 4 adults and 3 rooms"
    task = TaskLedger(wording, reference_date=date(2026, 11, 7))
    assert requested_destination(wording) is None
    task.declare([BrowserRequirement(name="destination", expected="New Jersey", application="form",
                                    request_quote="New Jersey", control_id="0:query")], search_form())
    assert task.requested_stay["destination"] == "New Jersey"
    assert task.collection_mode == "listing_results"
    assert task.instructions == wording


def test_query_grounding_does_not_authorize_a_rating_from_an_adult_count():
    field = search_form()["frames"][0]["controls"][0]
    assert not literal_form_value({"name": "rating_min", "expected": "4", "request_quote": "4 adults"}, field)
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 7))
    with pytest.raises(MissingFormValue):
        task.declare([BrowserRequirement(name="rating_min", expected="4", application="form",
                                        request_quote="4 adults", control_id="0:query")], search_form())
    assert "rating_min" not in task.requirements


def test_missing_value_retains_semantic_name_and_actual_label_separately():
    error = MissingFormValue("location_query", "Search")
    assert error.field == "location_query" and error.label == "Search"


def test_pre_action_declaration_failure_does_not_request_already_provided_search_data():
    class QueryTools(FakeTools):
        def observe(self):
            observation = search_form()
            self.references = {control["id"]: (None, None, control)
                               for control in observation["frames"][0]["controls"]}
            return observation

    invalid_alias = BrowserRequirement(name="rating_min", expected="unprovided words", application="form",
                                       request_quote=REQUEST, control_id="0:query")
    model = FakeDecider([decision("fill", "0:query", "New Jersey", requirements=[invalid_alias]), decision("pause")])
    tools = QueryTools()
    report = BrowserAgent(tools, model, REQUEST).run()
    first = report["actions"][0]
    assert first["missing_requirement"] == {"field": "rating_min", "label": "Search"}
    assert first["status"] == "query_not_needed"
    assert "awaiting_user_input" not in report
    assert "fill" not in tools.events


def test_ignored_query_metadata_does_not_authorize_an_unprovided_action_value():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 7))
    observation = search_form()
    task.declare([BrowserRequirement(name="search_query", expected="invented value", application="form",
                                    request_quote="", control_id="0:query")], observation)
    problem = task.action_value_problem(observation["frames"][0]["controls"][0],
                                        decision("fill", "0:query", "invented value"), observation, structured=True)
    assert isinstance(problem, MissingFormValue) and problem.label == "Search"


def test_redundant_query_metadata_does_not_prevent_opening_the_guest_panel():
    class FormTools(FakeTools):
        def observe(self):
            observation = search_form()
            self.references = {control["id"]: (None, None, control)
                               for control in observation["frames"][0]["controls"]}
            return observation

    alias = BrowserRequirement(name="location_query", expected="New Jersey", application="form",
                               request_quote="", control_id="0:query")
    tools = FormTools()
    model = FakeDecider([decision("click", "0:guests", requirements=[alias]), decision("pause")])
    report = BrowserAgent(tools, model, REQUEST).run()
    assert report["actions"][0]["status"] == "action_performed"
    assert report["actions"][0]["ignored_form_requirements"][0]["reason"] == "destination_already_grounded"
    assert tools.events == ["click"]
