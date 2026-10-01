"""Offline article discovery guards; no model or website requests."""

import pytest

from agentic_web_demo.browser_links import (
    ArticleSelection,
    approved_links,
    exclude_sections_from_detail_proposal,
    inspect_links,
    validate_selection,
)
from agentic_web_demo.custom_browser import BrowserControl
from agentic_web_demo.custom_fetch import WebsiteError


class FakePage:
    def evaluate(self, script):
        return [
            {
                "id": 0,
                "title": "A new battery research result",
                "context": "Published in the research section",
                "url": "https://news.example.org/technology/battery-study",
            },
            {
                "id": 1,
                "title": "Technology market analysis",
                "context": "A second article",
                "url": "https://news.example.org/technology/market?ref=home",
            },
            {
                "id": 2,
                "title": "Should never cross the origin",
                "context": "An external link",
                "url": "https://elsewhere.example.org/article",
            },
            {
                "id": 3,
                "title": "Should not expose account tokens",
                "context": "A tokenized link",
                "url": "https://news.example.org/article?token=secret",
            },
        ]


def test_link_inspection_keeps_only_safe_same_origin_candidates():
    candidates = inspect_links(FakePage(), "https://news.example.org")
    assert [item["id"] for item in candidates] == [0, 1]
    assert candidates[1]["url"].endswith("?ref=home")
    assert candidates[1]["display_url"].endswith("/technology/market")
    assert "token" not in str(candidates)


def test_navigation_sections_are_excluded_before_detail_review():
    class Links:
        def evaluate(self, script):
            return [
                {
                    "title": "World",
                    "context": "",
                    "url": "https://news.example.org/world",
                    "navigation": True,
                },
                {
                    "title": "Foreign policy",
                    "context": "",
                    "url": "https://news.example.org/category/politics/foreign-policy",
                },
                {
                    "title": "World leaders meet",
                    "context": "Summit report",
                    "url": "https://news.example.org/world/leaders-meet",
                },
            ]

    candidates = inspect_links(Links(), "https://news.example.org")
    assert [item["role_hint"] for item in candidates] == ["section", "section", "unknown"]
    proposed = ArticleSelection(
        outcome="ready",
        kind="articles",
        guidance="Relevant politics coverage",
        selected_ids=[0, 1, 2],
    )
    reviewed = exclude_sections_from_detail_proposal(proposed, candidates)
    assert reviewed.selected_ids == [2]
    assert "2 navigation/section" in reviewed.guidance
    assert [item["id"] for item in approved_links([2], reviewed, candidates)] == [2]
    with pytest.raises(WebsiteError, match="navigation section"):
        validate_selection(proposed, candidates)
    with pytest.raises(WebsiteError, match="Only navigation or section links"):
        exclude_sections_from_detail_proposal(
            proposed.model_copy(update={"selected_ids": [0, 1]}), candidates
        )


def test_article_selection_structured_output_requires_kind():
    assert "kind" in ArticleSelection.model_json_schema()["required"]


def test_link_inspection_includes_same_origin_frames_without_duplicates():
    class Frame:
        def __init__(self, url, links):
            self.url, self.links = url, links

        def evaluate(self, script):
            return self.links

    article = {
        "title": "Boston sports analysis",
        "context": "Match report",
        "url": "https://news.example.org/sport/match-report",
    }

    class Page:
        frames = [
            Frame("https://news.example.org/", [article]),
            Frame("https://news.example.org/embedded", [article]),
            Frame("https://other.example.org/embedded", [{**article, "url": "https://other.example.org/x"}]),
            Frame("about:blank", []),
        ]

    candidates = inspect_links(Page(), "https://news.example.org")
    assert [item["url"] for item in candidates] == [article["url"]]


def test_operator_can_approve_subset_of_proposed_article_links():
    candidates = inspect_links(FakePage(), "https://news.example.org")
    proposal = ArticleSelection(
        outcome="ready", kind="articles", guidance="Relevant links", selected_ids=[0, 1]
    )
    assert [item["id"] for item in approved_links([1], proposal, candidates)] == [1]
    with pytest.raises(WebsiteError, match="Only proposed"):
        approved_links([0, 2], proposal, candidates)
    with pytest.raises(WebsiteError, match="distinct"):
        approved_links([1, 1], proposal, candidates)


def test_model_cannot_select_unknown_or_duplicate_links():
    candidates = inspect_links(FakePage(), "https://news.example.org")
    for ids in ([0, 0], [42]):
        with pytest.raises(WebsiteError, match="unavailable or repeated"):
            validate_selection(
                ArticleSelection(
                    outcome="ready", kind="articles", guidance="", selected_ids=ids
                ),
                candidates,
            )


def test_section_hop_requires_one_reviewed_link_and_does_not_capture_articles():
    candidates = inspect_links(FakePage(), "https://news.example.org")
    with pytest.raises(WebsiteError, match="exactly one"):
        validate_selection(
            ArticleSelection(
                outcome="ready", kind="section", guidance="Open a topic", selected_ids=[0, 1]
            ),
            candidates,
        )
    selection = ArticleSelection(
        outcome="ready", kind="section", guidance="Open a topic", selected_ids=[0]
    )
    control = BrowserControl()
    control.set_links(selection, candidates, "https://news.example.org/", {"model": "fixture"})
    control.command("approve_links", [0])
    assert control.snapshot()["state"] == "opening_section"
    assert control.link_approved.is_set()


def test_article_proposal_requires_explicit_approval():
    control = BrowserControl()
    control.update("waiting", "Ready")
    control.command("discover")
    assert control.link_requested.is_set()
    assert not control.link_approved.is_set()
    with pytest.raises(WebsiteError):
        control.command("capture")
    candidates = inspect_links(FakePage(), "https://news.example.org")
    selection = ArticleSelection(
        outcome="ready", kind="articles", guidance="Review", selected_ids=[0, 1]
    )
    control.set_links(selection, candidates, "https://news.example.org/", {"model": "fixture"})
    with pytest.raises(WebsiteError):
        control.command("approve_links", [42])
    control.command("approve_links", [1])
    assert control.link_approved.is_set()
    assert control.link_selected_ids == [1]
