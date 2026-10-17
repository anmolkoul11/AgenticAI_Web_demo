"""Optional collection metadata regressions; synthetic tools and model decisions only.

These fixtures do not connect to a browser, website or model service. The file is
authored for user-run validation; no fixture execution is required to edit it.
"""

import copy

import pytest
from test_information_needs import Decisions, Sources, decision, goal
from test_submission_scope import FormTools

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserInformationNeed,
    BrowserRequirement,
)
from agentic_web_demo.browser_task import TaskLedger
from agentic_web_demo.custom_fetch import WebsiteError


def inferred_need(field, *, quote="", status="visible", evidence=""):
    return BrowserInformationNeed(
        field=field, request_quote=quote, status=status, evidence=evidence,
    )


def ignored(field, reason="not_requested_navigation_need"):
    return {"field": field, "status": "ignored", "reason": reason}


@pytest.mark.parametrize("capture_first", [False, True])
def test_generic_news_capture_and_finish_ignore_inferred_navigation_metadata(capture_first):
    prompt = "Get me articles related to world politics."
    tools = Sources()
    hints = [
        inferred_need("article_title", quote=prompt),
        inferred_need("article_url", quote=prompt),
    ]
    first = decision(
        "capture" if capture_first else "finish", value="page",
        collection_goal=goal(prompt, needs=hints),
    )
    model = Decisions(first, *([decision("finish", value="page")] if capture_first else []))
    agent = BrowserAgent(tools, model, prompt, collection_goal_required=True)
    report = agent.run()

    assert report["status"] == "ready"
    assert report["calls"] == len(model.payloads) == (2 if capture_first else 1)
    assert len(agent.captured_sources()) == 1
    assert report["task_checklist"]["collection_goal"]["mode"] == "current_page"
    assert report["task_checklist"]["information_needs"] == []
    assert report["task_checklist"]["collection_scope"]["allowed_modes"] == ["current_page"]
    assert report["actions"][0]["information_need_notes"] == [
        ignored("article_title"), ignored("article_url"),
    ]
    assert all(item["status"] != "requirement_rejected" for item in report["actions"])
    assert "click" not in tools.events


class DoneSources(Sources):
    def __init__(self):
        super().__init__()
        self.closed = False

    def observe(self):
        fresh = super().observe()
        if not self.closed:
            control = {"id": "0:done", "tag": "BUTTON", "type": "button", "label": "Done"}
            fresh["frames"][0]["controls"].append(control)
            self.references[control["id"]] = (None, None, control)
        return fresh

    def execute(self, action):
        if action.action == "click" and action.control_id == "0:done":
            self.events.append("click:done")
            self.closed = True
            return {"status": "action_performed"}
        return super().execute(action)


def test_optional_inferred_fields_do_not_block_an_ordinary_done_click():
    prompt = "Get me articles related to world politics."
    tools = DoneSources()
    model = Decisions(
        decision("click", field="0:done", collection_goal=goal(prompt, needs=[
            inferred_need("author", quote=prompt, status="needs_detail"),
        ])),
        decision("finish", value="page"),
    )
    report = BrowserAgent(tools, model, prompt, collection_goal_required=True).run()

    assert report["status"] == "ready" and report["calls"] == 2
    assert tools.closed and tools.events.count("click:done") == 1
    assert report["actions"][0]["information_need_notes"] == [ignored("author")]
    assert report["actions"][0]["status"] == "action_performed"
    assert report["task_checklist"]["information_coverage"]["detail_needed_fields"] == []
    assert tools.url == "https://example.org/index"


HOTEL_PROMPT = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms."
)


class HotelFormTools(FormTools):
    """Prepared form, a final Done control and independent returned stay fields."""

    def observe(self):
        fields = [
            {"id": "0:destination", "tag": "INPUT", "type": "text", "name": "destination",
             "label": "Destination", "value": "New York", "form_scope": "retrieval"},
            {"id": "0:check-in", "tag": "INPUT", "type": "date", "label": "Check-in",
             "value": "2026-10-28", "form_scope": "retrieval"},
            {"id": "0:check-out", "tag": "INPUT", "type": "date", "label": "Check-out",
             "value": "2026-10-30", "form_scope": "retrieval"},
            {"id": "0:adults", "tag": "INPUT", "type": "number", "label": "Adults",
             "value": "4", "form_scope": "retrieval"},
            {"id": "0:rooms", "tag": "INPUT", "type": "number", "label": "Rooms",
             "value": "2", "form_scope": "retrieval"},
        ]
        if not self.searched:
            fields.append(
                {"id": "0:done", "tag": "BUTTON", "type": "button", "label": "Done"}
                if not self.closed else
                {"id": "0:search", "tag": "BUTTON", "type": "submit", "label": "Search",
                 "form_scope": "retrieval", "submits_form": True}
            )
        self.references = {item["id"]: (None, None, item) for item in fields}
        observation = {
            "url": self.url, "document_id": self.url,
            "frames": [{"text": "Visible New York hotel records and displayed nightly prices. " * 4,
                        "controls": fields}],
        }
        if self.searched:
            observation["results"] = {"no_results": False, "record_count": 2, "busy": False}
        return observation

    def capture(self, kind="page"):
        result = super().capture(kind)
        self.pages[-1]["browser_task_context"] = copy.deepcopy(self.collection_context)
        return result


def test_hotel_search_runtime_handoff_is_not_blocked_by_inferred_name_and_price():
    tools = HotelFormTools()
    model = Decisions(decision(
        "click", field="0:done",
        collection_goal=goal(HOTEL_PROMPT, "search_results", needs=[
            inferred_need("hotel_name", quote=HOTEL_PROMPT),
            inferred_need("price", quote=HOTEL_PROMPT),
        ]),
    ))
    agent = BrowserAgent(tools, model, HOTEL_PROMPT, collection_goal_required=True)
    report = agent.run()

    assert report["status"] == "ready"
    assert report["calls"] == len(model.payloads) == 1
    assert tools.events == ["0:done", "0:search", "capture"]
    assert report["actions"][0]["information_need_notes"] == [
        ignored("hotel_name"), ignored("price"),
    ]
    assert report["actions"][-1]["decision_origin"] == "runtime"
    assert report["actions"][-1]["status"] == "source_collection_ready"
    assert report["task_checklist"]["search_submitted"] is True
    assert report["task_checklist"]["result_scope"]["status"] == "verified"
    assert len(agent.captured_sources()) == 1
    assert agent.captured_sources()[0]["url"] == "https://example.org/results"


def test_one_unsupported_need_does_not_discard_a_requested_author_need():
    prompt = "Get articles related to world politics; include author."
    task = TaskLedger(prompt)
    notes = task.declare_collection_goal(goal(prompt, needs=[
        inferred_need("hotel_name", quote=prompt, status="needs_detail"),
        inferred_need("author", status="needs_detail"),
    ]), Sources().observe())

    assert notes == [ignored("hotel_name")]
    assert set(task.information_needs) == {"author"}
    assert task.information_needs["author"]["status"] == "needs_detail"
    assert task.collection_goal["mode"] == task.collection_mode == "linked_details"


def test_an_explicit_advanced_field_remains_authority_with_no_duplicate_prompt_quote():
    prompt = "Get the relevant product records."
    task = TaskLedger(prompt, output_fields=["warranty"])
    notes = task.declare_collection_goal(goal(prompt, needs=[
        inferred_need("warranty", status="needs_detail"),
    ]), Sources().observe())

    assert notes == []
    assert task.information_needs["warranty"]["explicit_output_field"] is True
    assert task.information_needs["warranty"]["status"] == "needs_detail"
    assert task.collection_mode == "linked_details"
    assert task.snapshot()["information_need_feedback"] == []


def test_bad_optional_quote_does_not_authorize_more_navigation_or_block_the_goal():
    prompt = "Extract the product records; include warranty."
    task = TaskLedger(prompt)
    notes = task.declare_collection_goal(goal(prompt, needs=[
        inferred_need("warranty", quote="Use an unrelated request", status="needs_detail"),
    ]), Sources().observe())

    assert notes == [ignored("warranty", "request_quote_unverified")]
    assert not task.information_needs
    assert task.collection_goal["mode"] == task.collection_mode == "current_page"
    assert task.collection_scope["allowed_modes"] == ["current_page"]


@pytest.mark.parametrize("failure", ["mode", "quote"])
def test_invalid_core_goal_is_hard_rejected_without_partial_need_or_scope_mutation(failure):
    prompt = "Include author from this page only."
    task = TaskLedger(prompt)
    before = {
        "needs": copy.deepcopy(task.information_needs),
        "scope": copy.deepcopy(task.collection_scope),
        "goal": copy.deepcopy(task.collection_goal),
        "mode": task.collection_mode,
        "partial_reason": task.partial_reason,
        "feedback": task.snapshot()["information_need_feedback"],
    }
    proposal = goal(
        prompt, "linked_details" if failure == "mode" else "current_page",
        needs=[inferred_need("author", status="needs_detail")],
        partial_reason="A proposed change must not survive an invalid core goal.",
    )
    if failure == "quote":
        proposal = proposal.model_copy(update={"request_quote": "This quote is not in the request"})

    with pytest.raises(WebsiteError):
        task.declare_collection_goal(proposal, Sources().observe())

    assert task.information_needs == before["needs"]
    assert task.collection_scope == before["scope"]
    assert task.collection_goal == before["goal"]
    assert task.collection_mode == before["mode"]
    assert task.partial_reason == before["partial_reason"]
    assert task.snapshot()["information_need_feedback"] == before["feedback"]


def test_changed_real_requirement_remains_hard_rejected_before_any_capture():
    prompt = "Get the visible records where category is sports."
    tools = Sources()
    changed = BrowserRequirement(
        name="category", expected="politics", application="extraction", request_quote="sports",
    )
    actions = [decision("finish", collection_goal=goal(prompt, needs=[
        inferred_need("article_title", quote=prompt),
    ])).model_copy(update={"requirements": [changed]}) for _ in range(3)]
    model = Decisions(*actions)
    agent = BrowserAgent(tools, model, prompt, collection_goal_required=True)
    agent.task.declare([BrowserRequirement(
        name="category", expected="sports", application="extraction", request_quote="sports",
    )])
    report = agent.run()

    assert report["status"] == "paused" and report["calls"] == 3
    assert all(item["status"] == "requirement_rejected" for item in report["actions"])
    assert all("changed the requested category" in item["guidance"] for item in report["actions"])
    assert agent.task.requirements["category"]["expected"] == "sports"
    assert not tools.pages and not tools.events


def test_requested_detail_need_cannot_hide_a_forbidden_core_search_mode():
    prompt = "Include author."
    task = TaskLedger(prompt)
    before = copy.deepcopy(task.snapshot())
    proposal = goal(prompt, "search_results", needs=[
        inferred_need("author", status="needs_detail"),
    ])
    with pytest.raises(WebsiteError, match="scope outside the user's task"):
        task.declare_collection_goal(proposal, Sources().observe())
    assert task.snapshot() == before


def test_optional_feedback_is_deduplicated_and_bounded_without_creating_needs():
    prompt = "Get articles related to world politics."
    task = TaskLedger(prompt)
    for index in range(12):
        task.declare_collection_goal(goal(prompt, needs=[
            inferred_need(f"extra_field_{index}", quote=prompt, status="needs_detail"),
        ]), Sources().observe())

    feedback = task.snapshot()["information_need_feedback"]
    assert len(feedback) == 8
    assert len({(item["field"], item["reason"]) for item in feedback}) == 8
    repeated = feedback[-1]["field"]
    returned = task.declare_collection_goal(goal(prompt, needs=[
        inferred_need(repeated, quote=prompt, status="needs_detail"),
    ]), Sources().observe())
    assert returned == [ignored(repeated)]
    assert task.snapshot()["information_need_feedback"] == feedback
    assert not task.information_needs
    assert task.collection_scope["allowed_modes"] == ["current_page"]
