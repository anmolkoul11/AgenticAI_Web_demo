"""All-results collection fixtures; source only, no live sites or model calls."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.custom_fetch import WebsiteError
from agentic_web_demo.result_collection import ResultCollector, record_groups


URL = "https://example.org/results"


class ResultTools:
    approved_origin = "https://example.org"
    collection_context = None

    def __init__(self, pages, *, stuck=False, virtual=False):
        self.data, self.index, self.events = pages, 0, []
        self.stuck, self.virtual = stuck, virtual

    def guard(self):
        pass

    def observe(self):
        next_page = self.index + 1 < len(self.data)
        controls = [] if not next_page or self.virtual else [{
            "id": "0:next", "tag": "A", "href": URL + f"?page={self.index + 2}",
            "label": "Next page", "pagination": "next", "enabled": True,
        }]
        return {"url": URL, "document_id": f"doc-{0 if self.virtual else self.index}",
                "results": {"record_count": len(self.data[self.index]), "result_signature": f"{self.index + 1:08x}"},
                "frames": [{"controls": controls, "viewport": {
                    "at_page_end": not next_page if self.virtual else True,
                    "scroll_y": self.index * 650 if self.virtual else 0, "document_height": 5000,
                }}]}

    def capture_records(self, offset):
        self.events.append(("capture", self.index, offset))
        ids = self.data[self.index][offset:offset + 10]
        blocks = [{"id": "b1", "kind": "heading", "text": "Available listings", "association": "page"}]
        for number, identity in enumerate(ids):
            blocks.extend([
                {"id": f"b{number * 2 + 2}", "kind": "heading", "text": f"Hotel {identity}",
                 "href": f"https://example.org/hotel/{identity}", "association": "record", "group_id": f"g{number + 1}"},
                {"id": f"b{number * 2 + 3}", "kind": "text", "text": f"USD {100 + identity}",
                 "association": "record", "group_id": f"g{number + 1}"},
            ])
        return {"url": URL, "blocks": blocks, "text": "Captured source listings", "truncated": False,
                "coverage": {"record_window": True, "records_selected": len(ids), "records_detected": len(self.data[self.index])}}

    def execute(self, action):
        self.events.append((action.action, action.control_id, action.value))
        if not self.stuck and (action.action == "click" or action.action == "scroll" and self.virtual):
            delta = -1 if action.action == "scroll" and action.value == "up" else 1
            self.index = max(0, min(self.index + delta, len(self.data) - 1))
        return {"status": "action_performed"}


def collector(tools, limit=5000):
    return ResultCollector(tools, SimpleNamespace(instructions="Collect listings", record_limit=limit), [], lambda _: None)


def test_collects_sixty_loaded_listings_and_deduplicates_overlapping_next_page():
    tools = ResultTools([list(range(60)), list(range(50, 90))])
    result = collector(tools)
    pages = result.run()
    assert result.summary()["records_collected"] == 90 and result.complete
    assert sum(len(record_groups(page)) for page in pages) == 90
    assert len([event for event in tools.events if event[0] == "click"]) == 1
    ids = [block["id"] for page in pages for block in page["blocks"]]
    assert len(ids) == len(set(ids))
    assert len({page["capture_id"] for page in pages}) == len(pages)


def test_virtualized_cards_are_retained_before_the_next_scroll_removes_them():
    tools = ResultTools([list(range(start, start + 10)) for start in range(0, 60, 10)], virtual=True)
    result = collector(tools)
    pages = result.run()
    assert result.complete and sum(len(record_groups(page)) for page in pages) == 60
    assert len([event for event in tools.events if event[0] == "scroll"]) == 5


def test_collection_rewinds_a_previously_scrolled_virtualized_list():
    tools = ResultTools([list(range(start, start + 10)) for start in range(0, 60, 10)], virtual=True)
    tools.index = 3
    result = collector(tools)
    result.run()
    assert result.complete and len(result.seen) == 60
    assert len([event for event in tools.events if event[0] == "scroll" and event[2] == "up"]) == 3


def test_record_cap_is_partial_and_never_silently_claims_all_listings():
    result = collector(ResultTools([list(range(60))]), limit=25)
    pages = result.run()
    assert result.reason == "record_limit" and not result.complete
    assert sum(len(record_groups(page)) for page in pages) == 25
    assert all(page["result_collection"]["complete"] is False for page in pages)


def test_unconfirmed_pagination_is_not_clicked_twice_and_manual_progress_can_resume():
    tools = ResultTools([list(range(10)), list(range(10, 20))], stuck=True)
    result = collector(tools)
    with pytest.raises(WebsiteError, match="unconfirmed"):
        result.run()
    assert len([event for event in tools.events if event[0] == "click"]) == 1
    tools.index = 1  # Operator confirmed the next page manually.
    pages = result.run()
    assert result.complete and sum(len(record_groups(page)) for page in pages) == 20
    assert len([event for event in tools.events if event[0] == "click"]) == 1


def test_external_next_link_is_not_followed():
    tools = ResultTools([list(range(10)), list(range(10, 20))])
    original = tools.observe
    def observed():
        page = deepcopy(original())
        page["frames"][0]["controls"][0]["href"] = "https://other.example/results"
        return page
    tools.observe = observed
    result = collector(tools)
    result.run()
    assert result.reason == "external_pagination" and not result.complete
    assert not any(event[0] == "click" for event in tools.events)


def test_late_price_fields_replace_the_earlier_sparse_card_without_duplicate_rows():
    result = collector(ResultTools([list(range(10))]))
    earlier = result.tools.capture_records(0)
    earlier["blocks"] = [block for block in earlier["blocks"] if block["kind"] == "heading"]
    result.retain(earlier)
    result.retain(result.tools.capture_records(0))
    assert len(result.seen) == 10 and len(result.pages) == 1
    assert sum(len(record_groups(page)) for page in result.pages) == 10
    assert any(block["text"] == "USD 100" for block in result.pages[0]["blocks"])

