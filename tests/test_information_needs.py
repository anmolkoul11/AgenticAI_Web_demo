"""Synthetic source/decision fixtures; no website, browser or model connection."""

import copy

import pytest

from agentic_web_demo.browser_agent import (
    BrowserAgent,
    BrowserCollectionGoal,
    BrowserDecision,
    BrowserInformationNeed,
)
from agentic_web_demo.browser_task import TaskLedger, information_role, request_collection_scope


def goal(prompt, mode="current_page", *, needs=(), partial_reason=""):
    return BrowserCollectionGoal(
        mode=mode, request_quote=prompt, reason="Collect requested source information.",
        information_needs=list(needs), partial_reason=partial_reason,
    )


def decision(action, *, field=None, value="", collection_goal=None):
    return BrowserDecision(
        action=action, control_id=field, value=value,
        explanation="Collect requested information from the observed source.",
        evidence="Visible source content and its actual record link.",
        purpose="navigate" if action == "click" else "collect",
        collection_goal=collection_goal,
    )


class Sources:
    def __init__(self, *, detail_on_start=False, author=True, authentication=False):
        self.url = "https://example.org/index"
        self.pages, self.references, self.events = [], {}, []
        self.secrets, self.collection_context = (), None
        self.detail_on_start, self.author = detail_on_start, author
        self.authentication = authentication
        self.user_pause = lambda: False

    def guard(self):
        return None

    def blocks(self):
        blocks = [{
            "id": "b1", "kind": "heading", "text": "Soccer research explained",
            "href": "https://example.org/story", "association": "record", "group_id": "g1",
        }]
        full = self.detail_on_start or self.url.endswith("story")
        blocks.append({
            "id": "b2", "kind": "paragraph", "association": "record", "group_id": "g1",
            "text": "The researchers studied soccer training and player performance. " * (8 if full else 1),
            "content_role": "body" if full else "other",
        })
        if full:
            blocks.append({"id": "b3", "kind": "text", "text": "Published October 14, 2026"})
            if self.author:
                blocks.append({"id": "b4", "kind": "text", "text": "By Jane Reporter"})
        return blocks

    def observe(self):
        fields = [{
            "id": "0:story", "tag": "A", "label": "Soccer research explained",
            "href": "https://example.org/story",
        }]
        self.references = {item["id"]: (None, None, item) for item in fields}
        return {
            "url": self.url, "document_id": self.url,
            "frames": [{"text": " ".join(block["text"] for block in self.blocks()),
                        "controls": fields, "password_or_code_visible": self.authentication}],
        }

    def execute(self, action):
        self.events.append(action.action)
        if action.action == "capture":
            return self.capture(action.value or "page")
        if action.action == "click":
            self.url = "https://example.org/story"
        return {"status": "action_performed"}

    def capture(self, kind="page"):
        self.events.append("capture:" + kind)
        existing = next((page for page in self.pages if page["url"] == self.url), None)
        if existing:
            existing["source_kind"] = kind
        else:
            blocks = self.blocks()
            self.pages.append({
                "url": self.url, "text": " ".join(block["text"] for block in blocks),
                "blocks": blocks, "source_kind": kind,
            })
        return {"status": "captured", "url": self.url}


class Decisions:
    def __init__(self, *actions):
        self.actions, self.payloads = iter(actions), []

    def decide(self, payload, timeout):
        self.payloads.append(copy.deepcopy(payload))
        return next(self.actions)


def test_generic_headline_request_does_not_add_metadata_or_navigation():
    prompt = "Find relevant sports headlines."
    tools = Sources()
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["task_checklist"]["information_needs"] == []
    assert len(tools.pages) == 1
    assert "click" not in tools.events


@pytest.mark.parametrize("prompt", [
    "Get articles related to authors.",
    "Include headlines; do not include authors.",
    "Extract the visible records and include price context.",
])
def test_topics_negated_metadata_and_price_context_do_not_create_detail_work(prompt):
    tools = Sources()
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["task_checklist"]["information_coverage"]["detail_needed_fields"] == []
    assert report["task_checklist"]["information_needs"] == []
    assert "click" not in tools.events


def test_missing_requested_context_author_and_date_follow_actual_record_link():
    prompt = "Find sports articles; include author, publication date and full context."
    tools = Sources()
    decider = Decisions(
        decision("finish", collection_goal=goal(prompt)),
        decision("click", field="0:story"),
        decision("finish", value="detail"),
    )
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 3
    assert [(page["url"], page["source_kind"]) for page in tools.pages] == [
        ("https://example.org/index", "index"), ("https://example.org/story", "detail"),
    ]
    coverage = report["task_checklist"]["information_coverage"]
    assert coverage["detail_needed_fields"] == []
    assert set(coverage["fields_with_source_evidence"]) == {"author", "published_time", "body"}
    assert all("search" not in event for event in tools.events)


def test_requested_information_already_on_current_page_does_not_force_opening():
    prompt = "Extract full context and include author and publication date."
    tools = Sources(detail_on_start=True)
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert "click" not in tools.events
    assert report["task_checklist"]["information_coverage"]["missing_fields"] == []


def test_explicit_current_page_only_wins_over_missing_body_request():
    prompt = "Extract full context from this page only."
    tools = Sources()
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["collection_outcome"] == "partial_information"
    assert report["task_checklist"]["information_coverage"]["detail_needed_fields"] == ["body"]
    assert len(tools.pages) == 1
    assert "click" not in tools.events


def test_actual_body_not_teaser_required_even_when_model_claims_it_is_visible():
    prompt = "Include full context from this page only."
    tools = Sources()
    teaser = tools.blocks()[1]["text"]
    need = BrowserInformationNeed(field="body", status="visible", evidence=teaser)
    decider = Decisions(decision("finish", collection_goal=goal(prompt, needs=[need])))
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    coverage = report["task_checklist"]["information_coverage"]
    assert coverage["fields_with_source_evidence"] == []
    assert report["collection_outcome"] == "partial_information"


def test_missing_author_can_finish_as_explicit_partial_after_real_detail_capture():
    prompt = "Include author and full context for relevant sports stories."
    tools = Sources(author=False)
    decider = Decisions(
        decision("finish", collection_goal=goal(prompt)),
        decision("click", field="0:story"),
        decision("finish", value="detail", collection_goal=goal(
            prompt, "linked_details", partial_reason="The captured detail has no source byline."
        )),
    )
    report = BrowserAgent(tools, decider, prompt).run()
    assert report["status"] == "ready"
    assert report["collection_outcome"] == "partial_information"
    assert report["task_checklist"]["information_coverage"]["missing_fields"] == ["author"]


def test_last_consented_call_retains_partial_source_without_an_extra_decision():
    prompt = "Include full context for sports stories."
    tools = Sources()
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(tools, decider, prompt, max_calls=1).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["collection_outcome"] == "partial_information"
    assert len(tools.pages) == 1


def test_basic_output_fields_do_not_force_details_when_unclassified():
    prompt = "Extract the hotel records visible here."
    tools = Sources()
    decider = Decisions(decision("finish", collection_goal=goal(prompt)))
    report = BrowserAgent(
        tools, decider, prompt, output_fields=["hotel_name", "price", "rating", "listing_url"]
    ).run()
    assert report["status"] == "ready"
    assert report["calls"] == 1
    assert report["task_checklist"]["information_coverage"]["detail_needed_fields"] == []
    assert "click" not in tools.events


def test_advanced_requested_field_needs_no_duplicate_quote_in_prompt():
    prompt = "Find relevant records."
    task = TaskLedger(prompt, output_fields=["author"])
    task.declare_collection_goal(goal(prompt, needs=[
        BrowserInformationNeed(field="author", status="needs_detail")
    ]), Sources().observe())
    assert task.collection_mode == "linked_details"


@pytest.mark.parametrize("prompt", [
    "Get stories related to authors; include headlines.",
    "Include headlines; do not include authors.",
    "Show headlines without author information.",
])
def test_model_cannot_add_author_work_from_topic_or_excluded_field(prompt):
    task = TaskLedger(prompt)
    assert not task.information_needs
    notes = task.declare_collection_goal(goal(prompt, needs=[
        BrowserInformationNeed(
            field="author", status="needs_detail", request_quote=prompt,
        )
    ]), Sources().observe())
    assert notes == [{
        "field": "author", "status": "ignored", "reason": "not_requested_navigation_need",
    }]
    assert not task.information_needs
    assert task.collection_scope["allowed_modes"] == ["current_page"]
    assert task.collection_goal["mode"] == "current_page"
    assert task.snapshot()["information_need_feedback"] == notes


def test_model_can_ground_new_field_in_its_positive_requested_field_clause():
    prompt = "Extract product records; include warranty."
    task = TaskLedger(prompt)
    task.declare_collection_goal(goal(prompt, needs=[
        BrowserInformationNeed(
            field="warranty", status="needs_detail", request_quote="include warranty",
        )
    ]), Sources().observe())
    assert task.information_needs["warranty"]["status"] == "needs_detail"
    assert task.collection_mode == "linked_details"


def test_advanced_field_remains_authority_when_not_spelled_out_in_prompt():
    prompt = "Extract the relevant records."
    task = TaskLedger(prompt, output_fields=["article_author"])
    task.declare_collection_goal(goal(prompt, needs=[
        BrowserInformationNeed(field="article_author", status="needs_detail")
    ]), Sources().observe())
    assert task.information_needs["article_author"]["status"] == "needs_detail"
    assert task.collection_mode == "linked_details"


@pytest.mark.parametrize("field", ["price_context", "room_context", "tax_context"])
def test_pricing_context_fields_are_not_full_body_requests(field):
    assert information_role(field) == "other"
    task = TaskLedger("Extract visible hotel records.", output_fields=[field])
    assert task.information_coverage()["detail_needed_fields"] == []


def test_unclassified_generic_detail_body_requires_its_own_literal_long_quote():
    prompt = "Include full context for the relevant product."
    paragraph = "This product includes replaceable components and a documented warranty. " * 4
    task = TaskLedger(prompt)
    detail = {
        "url": "https://example.org/product-one", "source_kind": "detail", "text": paragraph,
        "blocks": [{"id": "b1", "kind": "paragraph", "text": paragraph,
                    "content_role": "other", "association": "record", "group_id": "g1"}],
    }
    task.note_sources([detail])
    assert task.information_coverage()["detail_needed_fields"] == ["body"]
    task.declare_collection_goal(goal(prompt, "linked_details", needs=[
        BrowserInformationNeed(field="body", status="visible", evidence=paragraph[:180])
    ]), {"frames": [{"text": paragraph, "controls": []}]})
    task.note_sources([detail])
    assert task.information_coverage()["detail_needed_fields"] == []
    index = {**detail, "source_kind": "index"}
    task.note_sources([index])
    assert task.information_coverage()["detail_needed_fields"] == ["body"]


def test_section_and_unrequested_search_do_not_replace_record_enrichment():
    prompt = "Include full context for relevant stories."
    task = TaskLedger(prompt)
    task.declare_collection_goal(goal(prompt, "linked_details"))
    tools = Sources()
    tools.capture("index")
    task.note_sources(tools.pages)
    click = decision("click", field="0:story")
    assert task.scope_problem(click, {"href": "https://example.org/story", "tag": "A"}) is None
    assert task.scope_problem(click, {"href": "https://example.org/sports", "tag": "A"})
    assert task.scope_problem(click, {"tag": "BUTTON", "type": "submit", "label": "Search"})


@pytest.mark.parametrize("fields", [[], ["author", "body", "published_date"]])
def test_explicit_page_only_scope_is_not_upgraded_by_output_fields(fields):
    scope = request_collection_scope("Extract this page only.", fields)
    assert scope["allowed_modes"] == ["current_page"]


def test_mfa_does_not_handoff_retained_sources_or_make_model_calls():
    tools = Sources(authentication=True)
    tools.capture("index")
    decider = Decisions()
    report = BrowserAgent(tools, decider, "Include full context.", max_calls=0).run()
    assert report["status"] == "paused"
    assert report["calls"] == 0
    assert report.get("collection_outcome") != "partial_information"
