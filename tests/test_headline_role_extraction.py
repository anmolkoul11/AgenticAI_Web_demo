"""Headline/programme source roles, through extraction validation; no live calls."""

from copy import deepcopy

import pytest

from agentic_web_demo.custom_extract import Extraction, prepare_extraction, validate_extraction
from test_custom_website import candidate as hotel_candidate, source as request_values
from test_record_headline_roles import URL, source as role_source


INDEX = "https://news.example.org/"
TITLE = "The coach discusses the team's championship win"


def page():
    captured = role_source()
    captured.update(url=INDEX, source_kind="page")
    captured["text"] = "\n".join(
        block["text"] + (" " + block["href"] if block.get("href") else "")
        for block in captured["blocks"]
    )
    return captured


def extraction(*, headline_id="b2", labels=("b1", "b3"), title="Morning Briefing",
               programme="Morning Briefing", media="Audio"):
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review captured headlines", "content_type": "articles",
        "interpretation": "Sports headlines, including editorial items with audio",
        "columns": [{"name": name, "kind": "text", "unit": "", "description": name}
                    for name in ("article_title", "article_url", "programme_name", "media_format")],
        "filters": [], "warnings": [], "more_records_available": False,
        "semantic_selection": {"request_quote": "sports", "topic": "sports"},
        "rows": [{"page_index": 0, "headline_block_id": headline_id, "label_block_ids": list(labels),
                  "cells": [
                      {"field": "article_title", "value": title, "evidence": title or ""},
                      {"field": "article_url", "value": URL, "evidence": URL},
                      {"field": "programme_name", "value": programme, "evidence": programme or ""},
                      {"field": "media_format", "value": media, "evidence": media or ""},
                  ], "relevance": "relevant", "relevance_reason": "A championship story",
                  "relevance_evidence": TITLE}],
    })


def validate(result, captured=None):
    captured = captured or page()
    values = request_values(urls=[INDEX], instructions="Find sports articles, including items with audio",
                            page_text=captured["text"])
    candidate, effective, _ = prepare_extraction(result, values)
    rejected, repairs, issues = [], [], []
    records, _ = validate_extraction(candidate, effective, [captured], rejected=rejected,
                                    field_repairs=repairs, field_issues=issues)
    return records, rejected, repairs


def test_programme_cell_is_repaired_to_the_selected_actual_heading_and_audio_is_kept():
    records, rejected, repairs = validate(extraction())
    assert not rejected
    assert records[0]["article_title"] == TITLE
    assert records[0]["programme_name"] == "Morning Briefing"
    assert records[0]["media_format"] == "Audio"
    assert records[0]["article_url"] == URL
    assert records[0]["evidence"]["article_title"] == TITLE
    assert repairs[0]["issues"][0]["reason"] == "headline_from_selected_source_block"


def test_actual_h2_article_headline_is_not_replaced_by_a_longer_h3_subheading():
    captured = page()
    captured["blocks"][0]["text"] = "Team wins final"
    captured["text"] += "\nTeam wins final"
    records, rejected, repairs = validate(
        extraction(headline_id="b1", labels=(), title="Team wins final", programme=None, media=None),
        captured,
    )
    assert not rejected and not repairs
    assert records[0]["article_title"] == "Team wins final"


def test_selected_headline_link_wins_over_a_programme_heading():
    captured = page()
    captured["blocks"][1]["kind"] = "link"
    captured["blocks"][1].pop("heading_level")
    records, rejected, _ = validate(extraction(), captured)
    assert not rejected
    assert records[0]["article_title"] == TITLE


def test_selected_headline_repairs_label_evidence_even_when_title_value_was_correct():
    result = extraction(title=TITLE)
    result.rows[0].cells[0].evidence = "Morning Briefing"
    records, rejected, repairs = validate(result)
    assert not rejected
    assert records[0]["evidence"]["article_title"] == TITLE
    assert repairs[0]["issues"][0]["old_evidence"] == "Morning Briefing"


@pytest.mark.parametrize("headline_id,labels,reason", [
    (None, (), "headline_role_unverified"),
    ("b4", (), "headline_selection_url_mismatch"),
    ("b2", ("b2",), "headline_selection_is_label"),
    ("b999", (), "headline_selection_not_captured"),
])
def test_unresolved_or_cross_episode_role_choices_do_not_save_a_programme_as_headline(
    headline_id, labels, reason,
):
    records, rejected, repairs = validate(extraction(headline_id=headline_id, labels=labels))
    assert not records and not repairs
    assert reason in {issue["reason"] for issue in rejected[0]["issues"]}


def test_same_programme_keeps_two_episode_headlines_with_their_respective_urls():
    captured = page()
    second_url = "https://news.example.org/episode-two"
    second_title = "Another coach reviews the championship final"
    captured["blocks"][3]["text"] = second_title
    captured["blocks"].extend([
        {"id": "b5", "kind": "heading", "heading_level": 2, "text": "Morning Briefing",
         "href": second_url, "group_id": "g2", "association": "record"},
        {"id": "b6", "kind": "text", "text": "Audio", "href": None,
         "group_id": "g2", "association": "record"},
    ])
    captured["text"] += "\n" + second_title + "\nMorning Briefing\nAudio"
    result = extraction()
    second = deepcopy(result.rows[0])
    second.headline_block_id, second.label_block_ids = "b4", ["b5", "b6"]
    second.cells[1].value = second.cells[1].evidence = second_url
    second.relevance_evidence = second_title
    result.rows.append(second)
    records, rejected, _ = validate(result, captured)
    assert not rejected
    assert {(record["article_title"], record["article_url"]) for record in records} == {
        (TITLE, URL), (second_title, second_url),
    }


def test_selected_record_group_prevents_borrowing_details_when_headline_text_is_repeated():
    captured = page()
    captured["blocks"][3]["text"] = TITLE
    captured["blocks"].append({
        "id": "b5", "kind": "heading", "heading_level": 2, "text": "Another Programme",
        "href": "https://news.example.org/episode-two", "group_id": "g2", "association": "record",
    })
    captured["text"] += "\nAnother Programme"
    result = extraction(programme="Another Programme")
    records, rejected, _ = validate(result, captured)
    assert not rejected
    assert records[0]["article_title"] == TITLE and records[0]["article_url"] == URL
    assert records[0]["programme_name"] is None


def test_hotel_rows_keep_the_existing_validation_and_price_filter_path():
    values, result = request_values(), hotel_candidate()
    for row in result.rows:
        row.headline_block_id, row.label_block_ids = "b999", ["b999"]
    records, excluded = validate_extraction(
        result, values, [{"url": values.urls[0], "text": values.page_text}], rejected=[]
    )
    assert [record["price"] for record in records] == ["150", "250"]
    assert excluded == 1
