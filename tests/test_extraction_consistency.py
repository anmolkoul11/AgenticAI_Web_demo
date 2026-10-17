"""Output contracts and DOM provenance. No real model requests; browsers are opt-in."""

import pytest
from pydantic import ValidationError
from test_source_inventory import COLLECTOR
from test_source_inventory import inventory_browser as shared_browser

from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import (
    Extraction,
    WebsiteInput,
    prepare_extraction,
    validate_extraction,
)
from agentic_web_demo.custom_service import output_field_statuses


def inputs(**changes):
    return WebsiteInput(
        source="paste",
        urls=["https://example.org/"],
        page_text="Sports news headline and visible content for source verification. " * 2,
        authorized=True,
        allow_model_api=True,
        **changes,
    )


def candidate():
    return Extraction.model_validate(
        dict(
            outcome="ready",
            guidance="Review",
            content_type="articles",
            interpretation="Sports headlines",
            columns=[
                dict(
                    name="article_title",
                    kind="text",
                    unit="",
                    description="Actual title",
                )
            ],
            filters=[],
            rows=[
                dict(
                    page_index=0,
                    cells=[
                        dict(
                            field="article_title",
                            value="Sports news headline",
                            evidence="Sports news headline",
                        )
                    ],
                )
            ],
            warnings=[],
            more_records_available=False,
        )
    )


def test_inferred_news_fields_do_not_gain_empty_template_columns():
    fixed, values, notes = prepare_extraction(candidate(), inputs())
    names = [column.name for column in fixed.columns]
    assert names == ["article_title"]
    assert [cell.field for cell in fixed.rows[0].cells] == names
    assert all(cell.value is None for cell in fixed.rows[0].cells[1:])
    rows, _ = validate_extraction(
        fixed, values, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert "article_excerpt" not in rows[0]
    assert not notes


def test_explicit_generic_fields_are_preserved_even_when_model_omits_schema_slot():
    values = inputs(output_fields=["article_title", "author", "publication"])
    fixed, _, _ = prepare_extraction(candidate(), values)
    assert {column.name for column in fixed.columns} == {
        "article_title",
        "author",
        "publication",
    }
    reports = output_field_statuses(
        [
            {
                "listing_id": "r1",
                "article_title": "Sports news headline",
                "author": None,
                "publication": None,
            }
        ],
        fixed.columns,
        {"article_title"},
        [],
    )
    assert reports[0]["fields"]["author"]["status"] == "model_not_returned"


def test_pinned_fields_exclude_unrequested_columns_but_keep_filter_dependencies():
    raw = candidate()
    raw.columns.append(raw.columns[0].model_copy(update={"name": "extra_label"}))
    raw.rows[0].cells.append(raw.rows[0].cells[0].model_copy(update={"field": "extra_label"}))
    fixed, _, notes = prepare_extraction(raw, inputs(output_fields=["article_title"]))
    assert [column.name for column in fixed.columns] == ["article_title"]
    assert [cell.field for cell in fixed.rows[0].cells] == ["article_title"] and notes


def test_added_optional_identity_does_not_erase_valid_listing_values():
    from test_custom_website import candidate as hotel_candidate
    from test_custom_website import source

    raw, values = hotel_candidate(), source(output_fields=["price", "name"])
    fixed, effective, _ = prepare_extraction(raw, values)
    rows, _ = validate_extraction(
        fixed, effective, [{"url": values.urls[0], "text": values.page_text}]
    )
    assert len(rows) == 2 and all(row["name"] is None for row in rows)


def test_filter_dependency_is_not_silently_projected_out():
    from agentic_web_demo.custom_extract import Condition

    raw = candidate()
    raw.filters = [Condition(field="article_title", operator="contains", value="Sports")]
    fixed, effective, notes = prepare_extraction(
        raw, inputs(output_fields=["author"], instructions="Filter titles containing Sports")
    )
    assert {column.name for column in fixed.columns} == {"author", "article_title"}
    rows, _ = validate_extraction(
        fixed, effective, [{"url": effective.urls[0], "text": effective.page_text}]
    )
    assert len(rows) == 1 and any("dependency" in note for note in notes)


def test_single_detail_body_can_fill_empty_excerpt_from_literal_capture():
    raw = candidate()
    values = inputs(output_fields=["article_title", "article_url", "article_excerpt"])
    fixed, effective, _ = prepare_extraction(raw, values)
    body = "The team won the match after scoring twice in extra time, with fans celebrating."
    page = {
        "url": "https://example.org/sport/story",
        "source_kind": "detail",
        "text": "Sports news headline\n" + body,
        "blocks": [
            {
                "id": "b1",
                "kind": "heading",
                "text": "Sports news headline",
                "heading_level": 1,
                "content_role": "headline",
                "group_id": "g1",
            },
            {
                "id": "b2",
                "kind": "paragraph",
                "text": body,
                "content_role": "body",
                "group_id": "g1",
            },
        ],
    }
    rows, _ = validate_extraction(
        fixed, effective, [page], field_issues=[], rejected=[], field_repairs=[]
    )
    assert rows[0]["article_excerpt"] == body
    assert rows[0]["article_url"] == page["url"]
    page["source_kind"] = "index"
    rows, _ = validate_extraction(
        fixed, effective, [page], field_issues=[], rejected=[], field_repairs=[]
    )
    assert rows[0]["article_excerpt"] is None


@pytest.mark.parametrize(
    "names",
    [["author", "author"], ["Author"], ["source_url"], ["rule_result"], ["a b"]],
)
def test_invalid_output_contracts_fail_before_model_calls(names):
    with pytest.raises(ValidationError, match="Output fields"):
        inputs(output_fields=names)


@pytest.mark.parametrize("mode", ["normal", "restricted"])
def test_same_captured_snapshot_uses_same_validation_in_both_modes(mode):
    values = WebsiteInput(
        source="browser",
        browser_mode=mode,
        normal_browser_confirmed=mode == "normal",
        urls=["https://example.org/"],
        authorized=True,
        allow_model_api=True,
    )
    fixed, effective, _ = prepare_extraction(candidate(), values)
    rows, excluded = validate_extraction(
        fixed,
        effective,
        [
            {
                "url": values.urls[0],
                "text": "Sports news headline and enough visible source content.",
            }
        ],
    )
    assert len(rows) == 1 and excluded == 0
    assert rows[0]["article_title"] == "Sports news headline"


def test_captured_unique_headline_href_repairs_missing_url_without_guessing():
    values = inputs(output_fields=["article_title", "article_url"])
    fixed, effective, _ = prepare_extraction(candidate(), values)
    url = "https://example.org/sport/story"
    page = {
        "url": values.urls[0],
        "text": "Sports news headline\n" + url,
        "blocks": [
            {
                "id": "b1",
                "kind": "heading",
                "text": "Sports news headline",
                "href": url,
                "group_id": "g1",
                "association": "record",
                "heading_level": 3,
            }
        ],
    }
    repairs = []
    rows, _ = validate_extraction(
        fixed, effective, [page], field_repairs=repairs, field_issues=[], rejected=[]
    )
    assert rows[0]["article_url"] == url and repairs
    # Two literal URLs for the same headline are ambiguous, not a first-link guess.
    page["blocks"].append({**page["blocks"][0], "id": "b2", "href": "https://example.org/other"})
    page["text"] += "\nhttps://example.org/other"
    rows, _ = validate_extraction(fixed, effective, [page], field_issues=[], rejected=[])
    assert rows[0]["article_url"] is None


@pytest.fixture
def local_page(request):
    yield from shared_browser.__wrapped__(request)


@pytest.mark.parametrize(
    "content",
    [
        '<article><h3><a href="/sport/story">A real sports headline</a></h3>'
        "<p>Actual teaser about the match.</p></article>",
        '<div class="listing"><h3><a href="/hotel/one">Boston Hotel North</a></h3>'
        "<p>Nightly price 250 USD; guest rating 4.2 out of 5.</p></div>",
    ],
)
def test_nested_heading_links_and_companion_fields_remain_associated(local_page, content):
    local_page.set_content(
        "<main>" + content + "<p>Additional visible page source text.</p></main>"
    )
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    heading = next(block for block in capture.blocks if block.kind == "heading")
    paragraph = next(
        block
        for block in capture.blocks
        if block.kind == "paragraph" and block.group_id == heading.group_id
    )
    assert heading.href and heading.href.startswith("https://")
    assert paragraph.group_id == heading.group_id


def test_late_record_headline_survives_early_label_block_pressure(local_page):
    labels = "".join("<div>Secondary label " + str(i) + "</div>" for i in range(650))
    local_page.set_content(
        "<main>" + labels + '<article><h3><a href="/late/story">Late sports headline</a></h3>'
        "<p>Actual teaser for this late story.</p></article></main>"
    )
    capture = Capture.model_validate(local_page.evaluate("(" + COLLECTOR + ")"))
    heading = next(block for block in capture.blocks if block.text == "Late sports headline")
    assert heading.href.endswith("/late/story")
    assert "Actual teaser for this late story." in capture.page()["text"]
    assert capture.truncated and len(capture.blocks) <= 600
