"""Source-only regression cases for hotel Search value grounding."""

from datetime import date
from types import SimpleNamespace

import pytest

from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_fetch import WebsiteError


REQUEST = "Find hotels in Durham from January 28-30 2027 for 4 adults and 2 rooms."


def query_observation():
    field = {"id": "0:query", "tag": "INPUT", "type": "search", "role": "textbox",
             "name": "q", "label": "Search", "value": "Durham", "enabled": True}
    return field, {"url": "https://example.org/hotels", "document_id": "doc-1",
                   "frames": [{"controls": [field]}]}


@pytest.mark.parametrize("value", ["4", "2", "28", "2027", "January", "January 28-30 2027"])
def test_hotel_query_rejects_other_literal_prompt_values_without_requesting_user_input(value):
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 8))
    field, observed = query_observation()
    with pytest.raises(WebsiteError, match="requested destination"):
        task.action_value_problem(field, SimpleNamespace(action="fill", value=value), observed, structured=True)


def test_hotel_query_keeps_literal_destination_discovery():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 8))
    field, observed = query_observation()
    assert task.action_value_problem(field, SimpleNamespace(action="fill", value="Durham"), observed) is None


def test_nonhotel_query_can_still_search_literal_request_content():
    task = TaskLedger("Find articles related to sports", reference_date=date(2026, 11, 8))
    field, observed = query_observation()
    assert task.action_value_problem(field, SimpleNamespace(action="fill", value="sports"), observed) is None


def test_hotel_adults_field_remains_separately_authorized():
    task = TaskLedger(REQUEST, reference_date=date(2026, 11, 8))
    field, observed = query_observation()
    field.update(label="Adults", name="adults", type="number", role="spinbutton", value="2")
    task.observe(observed)
    assert task.action_value_problem(field, SimpleNamespace(action="fill", value="4"), observed) is None
