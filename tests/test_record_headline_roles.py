"""Source-role choices are grounded by block/group/URL, never heading rank."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.source_fields import (
    ambiguous_linked_headline,
    linked_headline,
    selected_record_headline,
)

URL = "https://news.example.org/episode-one"


def source():
    return {"blocks": [
        {"id": "b1", "kind": "heading", "heading_level": 2, "text": "Morning Briefing",
         "href": URL, "association": "record", "group_id": "g1"},
        {"id": "b2", "kind": "heading", "heading_level": 3,
         "text": "The coach discusses the team's championship win", "href": URL,
         "association": "record", "group_id": "g1"},
        {"id": "b3", "kind": "text", "text": "Audio", "href": None,
         "association": "record", "group_id": "g1"},
        {"id": "b4", "kind": "heading", "heading_level": 3, "text": "Another episode",
         "href": "https://news.example.org/episode-two", "association": "record", "group_id": "g2"},
    ]}


def selection(headline="b2", labels=("b1", "b3")):
    return SimpleNamespace(headline_block_id=headline, label_block_ids=list(labels))


def test_programme_and_audio_labels_remain_separate_from_the_actual_episode_heading():
    page = source()
    assert linked_headline(page, URL) is None
    assert ambiguous_linked_headline(page, URL)
    block, issues = selected_record_headline(selection(), page, [URL])
    assert not issues
    assert block == page["blocks"][1]
    assert page["blocks"][0]["text"] == "Morning Briefing"
    assert page["blocks"][2]["text"] == "Audio"


def test_article_h2_can_be_selected_over_a_longer_h3_subheading():
    page = source()
    page["blocks"][0]["text"] = "Team wins final"
    block, issues = selected_record_headline(selection("b1", ()), page, [URL])
    assert not issues and block == page["blocks"][0]


def test_legacy_rows_without_role_metadata_keep_the_existing_path():
    assert selected_record_headline(SimpleNamespace(), source(), [URL]) == (None, [])
    single = {"blocks": [deepcopy(source()["blocks"][0])]}
    assert not ambiguous_linked_headline(single, URL)
    assert linked_headline(single, URL) == single["blocks"][0]


@pytest.mark.parametrize("headline,labels,urls,reason", [
    ("b999", (), [URL], "headline_selection_not_captured"),
    ("b3", (), [URL], "headline_selection_not_heading_or_link"),
    ("b4", (), [URL], "headline_selection_url_mismatch"),
    ("b2", ("b4",), [URL], "headline_label_cross_record"),
    ("b2", ("b999",), [URL], "headline_label_not_captured"),
    ("b2", ("b2",), [URL], "headline_selection_is_label"),
    (None, ("b1",), [URL], "headline_selection_missing"),
    ("b2", (), [URL, "https://news.example.org/episode-two"], "headline_selection_url_ambiguous"),
])
def test_invalid_or_cross_record_role_choices_never_become_headlines(headline, labels, urls, reason):
    block, issues = selected_record_headline(selection(headline, labels), source(), urls)
    assert block is None and reason in issues


def test_duplicate_source_id_and_page_navigation_are_not_role_proof():
    page = source()
    page["blocks"].append(deepcopy(page["blocks"][1]))
    assert selected_record_headline(selection(), page, [URL])[1] == ["headline_selection_not_captured"]
    page = source()
    page["blocks"][1]["association"] = "page"
    assert selected_record_headline(selection(), page, [URL])[1] == ["headline_selection_not_record_bound"]


def test_unlinked_heading_must_bind_the_declared_url_through_its_own_record_group():
    page = source()
    page["blocks"][1]["href"] = None
    assert selected_record_headline(selection(), page, [URL])[0] == page["blocks"][1]
    page["blocks"][1]["group_id"] = "g2"
    assert selected_record_headline(selection("b2", ()), page, [URL])[1] == ["headline_selection_url_mismatch"]


def test_legacy_ungrouped_sources_require_the_same_exact_href_for_labels():
    page = source()
    for block in page["blocks"]:
        block.pop("group_id")
    assert selected_record_headline(selection("b2", ("b1",)), page, [URL])[0] == page["blocks"][1]
    assert selected_record_headline(selection("b2", ("b4",)), page, [URL])[1] == ["headline_label_cross_record"]


def test_declared_label_alias_cannot_be_selected_as_the_headline():
    page = source()
    page["blocks"].append({**deepcopy(page["blocks"][1]), "id": "b5"})
    assert selected_record_headline(selection("b2", ("b5",)), page, [URL])[1] == ["headline_selection_is_label"]


@pytest.mark.parametrize("source_kind,role", [("detail", "other"), ("page", "headline")])
def test_native_primary_detail_heading_can_bind_its_page_without_a_group(source_kind, role):
    page = {"url": URL, "requested_url": URL + "?id=redirect", "source_kind": source_kind,
            "blocks": [{"id": "b1", "kind": "heading", "heading_level": 1,
                        "content_role": role, "text": "A literal primary story headline",
                        "association": "page", "href": None, "group_id": None}]}
    block, issues = selected_record_headline(selection("b1", ()), page, [URL, page["requested_url"]])
    assert block == page["blocks"][0] and not issues


def test_generic_index_h1_does_not_promote_a_page_heading_to_a_record():
    page = {"url": URL, "source_kind": "index", "blocks": [
        {"id": "b1", "kind": "heading", "heading_level": 1, "content_role": "headline",
         "text": "Latest coverage", "association": "page", "href": None},
    ]}
    assert selected_record_headline(selection("b1", ()), page, [URL])[1] == ["headline_selection_not_record_bound"]
    page["source_kind"] = "detail"
    assert selected_record_headline(selection("b1", ()), page, ["https://news.example.org/other"])[1] == ["headline_selection_not_record_bound"]
