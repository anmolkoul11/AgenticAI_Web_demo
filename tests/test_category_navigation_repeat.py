"""Source-only regressions: a category reload is not task progress."""

import copy

import pytest

from agentic_web_demo.browser_agent import (
    BrowserAgent, category_navigation_routes, category_navigation_transition,
)
from test_browser_agent import FakeDecider, FakeTools, decision


def category_page(document="doc-1", url="https://example.org/Hotels"):
    control = {"id": "0:hotels", "tag": "A", "role": "", "type": "", "name": "",
               "label": "Hotels", "href": "https://example.org/Hotels", "enabled": True}
    return {"url": url, "document_id": document,
            "frames": [{"controls": [control], "widgets": [], "viewport": {"scroll_y": 0}}]}


def test_new_document_token_alone_is_not_progress_on_the_same_category_route():
    before, after = category_page(), category_page("doc-2")
    effect = category_navigation_transition(before, after)
    assert effect["status"] == "no_observable_change"
    assert effect["document_reloaded"] and not effect["document_changed"]


def test_first_category_visit_and_query_pagination_remain_distinct_routes():
    page = category_page(url="https://example.org/")
    control = page["frames"][0]["controls"][0]
    assert len(set(category_navigation_routes(decision("click", control["id"]), control, page))) == 2
    page["url"] = "https://example.org/Hotels?page=2&sort=price"
    assert len(set(category_navigation_routes(decision("click", control["id"]), control, page))) == 2


@pytest.mark.parametrize("changes", [
    {"tag": "BUTTON", "submits_form": True}, {"role": "tab"}, {"role": "button"},
    {"href": "https://example.org/Hotels#guests"}, {"haspopup": "true"},
])
def test_category_guard_does_not_intercept_forms_or_widgets(changes):
    page = category_page()
    control = {**page["frames"][0]["controls"][0], **changes}
    assert category_navigation_routes(decision("click", control["id"]), control, page) is None


def test_repeated_current_category_choice_never_dispatches_a_reload():
    class ReloadingIdentity(FakeTools):
        def observe(self):
            self.version += 1
            page = category_page(f"doc-{self.version}")
            self.references = {item["id"]: (None, None, copy.deepcopy(item))
                               for item in page["frames"][0]["controls"]}
            return page

    tools = ReloadingIdentity()
    report = BrowserAgent(tools, FakeDecider([
        decision("click", "0:hotels"), decision("click", "0:hotels"),
    ]), "Collect visible information").run()
    assert report["status"] == "paused" and report["calls"] == 2
    assert not tools.events
    assert all(item["status"] == "navigation_not_needed" for item in report["actions"])
