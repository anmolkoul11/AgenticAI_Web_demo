"""Local presentation/completeness fixtures; no network or model calls."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from agentic_web_demo.output_contract import select_output_contract
from agentic_web_demo.result_presentation import annotate_source_coverage, group_output_fields, presentation_contract


def columns(*names):
    return [{"name": name, "kind": "text", "description": name, "unit": ""} for name in names]


def fixture(*details, name="Eurostars The Chemists' Club"):
    page = {
        "url": "https://example.org/results",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": name, "group_id": "g1", "association": "record"},
            *[{"id": f"b{index + 2}", "kind": "text", "text": text, "group_id": "g1", "association": "record"}
              for index, text in enumerate(details)],
        ],
    }
    row = {"listing_id": "record-1", "name": name, "source_url": page["url"], "evidence": {"name": name}}
    return row, page


@pytest.mark.parametrize("field,source", [
    ("free_cancellation", "Free cancellation"),
    ("pay_at_property", "You can pay at the property"),
    ("breakfast_included", "Breakfast included"),
    ("recommended_for_group", "Recommended for your group"),
    ("refundable_booking", "Refundable booking until 28 October"),
    ("wheelchair_accessible", "Wheelchair accessible"),
])
def test_supported_missing_feature_is_retained_as_literal_context_not_invented_fact(field, source):
    row, page = fixture(source)
    row[field] = None
    before = deepcopy(row)
    result = annotate_source_coverage([row], [page], columns("name", field))[0]
    assert row == before
    assert result[field] is None
    coverage = result["source_coverage"]
    item = coverage["related_fields"][field][0]
    assert item == {"text": source, "source_url": page["url"], "block_ids": ["b2"]}
    assert coverage["additional_details"] == [item]
    assert coverage["mapped_fields"] == 1
    assert coverage["missing_fields"] == [field]
    assert "not confirmed answers" in coverage["note"]


def test_negation_is_never_converted_to_positive_feature_or_boolean():
    row, page = fixture("No free cancellation; changes incur a fee")
    row["free_cancellation"] = None
    result = annotate_source_coverage([row], [page], columns("name", "free_cancellation"))[0]
    assert result["free_cancellation"] is None
    assert result["source_coverage"]["related_fields"]["free_cancellation"][0]["text"].startswith("No free cancellation")


def test_unmodeled_featured_badge_is_preserved_as_literal_source_detail():
    row, page = fixture("Featured")
    result = annotate_source_coverage([row], [page], columns("name"))[0]["source_coverage"]
    assert result["additional_details"] == [
        {"text": "Featured", "source_url": page["url"], "block_ids": ["b2"]}
    ]


def test_additional_source_quotes_are_grouped_without_filling_output_fields():
    row, page = fixture(
        "Breakfast included", "2 nights, 4 adults", "Location 9.3",
        "Recommended for your group", "Scored 8.1 8.1Very Good 7,067 reviews",
        "Quiet courtyard", "Per night $259", "Free WiFi",
    )
    row["amenities"] = None
    before = deepcopy(row)
    result = annotate_source_coverage([row], [page], columns("name", "amenities"))[0]
    assert row == before
    assert result["amenities"] is None
    coverage = result["source_coverage"]
    sections = {section["id"]: section for section in coverage["detail_sections"]}
    assert sections["terms"]["details"][0]["text"] == "Breakfast included"
    assert sections["configuration"]["details"][0]["text"] == "2 nights, 4 adults"
    assert [item["text"] for item in sections["feedback"]["details"]] == [
        "Location 9.3", "Scored 8.1 8.1Very Good 7,067 reviews",
    ]
    assert sections["promotions"]["label"] == "Offers & recommendations"
    assert sections["promotions"]["details"][0]["text"] == "Recommended for your group"
    assert sections["pricing"]["details"][0]["text"] == "Per night $259"
    assert sections["features"]["details"][0]["text"] == "Free WiFi"
    assert sections["details"]["details"][0]["text"] == "Quiet courtyard"
    # Supplemental metadata preserves the original flat item shape/provenance.
    flattened = [item for section in coverage["detail_sections"] for item in section["details"]]
    assert sorted(flattened, key=lambda item: item["text"]) == sorted(coverage["additional_details"], key=lambda item: item["text"])
    assert all(set(item) == {"text", "source_url", "block_ids"} for item in flattened)
    assert all(item["source_url"] == page["url"] and item["block_ids"] for item in flattened)
    assert "not confirmed answers" in coverage["note"]


@pytest.mark.parametrize("wording,group", [
    ("Location 9.3", "feedback"),
    ("Location: 9.3/10", "feedback"),
    ("Location 9.3 miles from the airport", "location"),
    ("Scored 8.1", "feedback"),
    ("No breakfast included", "terms"),
    ("Two-year warranty", "terms"),
    ("Published date: October 17", "timing"),
    ("Unfamiliar captured wording", "details"),
])
def test_source_detail_categories_preserve_qualifiers_and_do_not_guess_values(wording, group):
    row, page = fixture(wording)
    result = annotate_source_coverage([row], [page], columns("name"))[0]
    sections = result["source_coverage"]["detail_sections"]
    assert len(sections) == 1
    assert sections[0]["id"] == group
    assert sections[0]["details"] == [{"text": wording, "source_url": page["url"], "block_ids": ["b2"]}]
    assert set(result) == set(row) | {"source_coverage"}


def test_mapped_identity_with_navigation_suffix_is_not_repeated_as_additional_detail():
    row, page = fixture(
        "Element Times Square Opens in new window",
        "Element Times Square West Opens in new window",
        name="Element Times Square",
    )
    result = annotate_source_coverage([row], [page], columns("name"))[0]["source_coverage"]
    assert [item["text"] for item in result["additional_details"]] == [
        "Element Times Square West Opens in new window",
    ]
    assert page["blocks"][1]["text"] == "Element Times Square Opens in new window"


def test_navigation_suffix_does_not_relax_source_record_identity_binding():
    row, page = fixture("Breakfast included", name="North Light")
    page["blocks"][0]["text"] = "North Light Opens in new window"
    result = annotate_source_coverage([row], [page], columns("name"))[0]["source_coverage"]
    assert result["additional_details"] == []
    assert result["detail_sections"] == []
    assert "No unique" in result["note"]


@pytest.mark.parametrize("name,detail", [("Barclay", "Bar"), ("Poolside", "Pool"), ("Carpet", "Car")])
def test_partial_words_in_identity_evidence_cannot_hide_distinct_source_details(name, detail):
    row, page = fixture(detail, name=name)
    result = annotate_source_coverage([row], [page], columns("name"))[0]["source_coverage"]
    assert [item["text"] for item in result["additional_details"]] == [detail]


def test_additional_details_cannot_borrow_neighbors_currency_navigation_or_ambiguous_blocks():
    row, page = fixture("Quiet courtyard")
    page["blocks"] += [
        {"id": "b3", "kind": "text", "text": "Free cancellation", "group_id": "g2"},
        {"id": "b4", "kind": "text", "text": "Prices in USD", "group_id": "g1", "association": "page"},
        {"id": "b5", "kind": "text", "text": "Breakfast included", "group_id": "g1", "association": "ambiguous"},
        {"id": "b6", "kind": "link", "text": "See availability", "group_id": "g1"},
        {"id": "b7", "kind": "link", "text": "Show on map", "group_id": "g1"},
        {"id": "b8", "kind": "text", "text": "2×", "group_id": "g1"},
    ]
    result = annotate_source_coverage([row], [page], columns("name"))[0]
    assert [item["text"] for item in result["source_coverage"]["additional_details"]] == ["Quiet courtyard"]


@pytest.mark.parametrize("ambiguity", ["duplicate_identity", "duplicate_page", "unbound", "no_provenance"])
def test_missing_or_ambiguous_record_binding_never_falls_back_to_whole_page(ambiguity):
    row, page = fixture("Free cancellation")
    pages = [page]
    if ambiguity == "duplicate_identity":
        page["blocks"].append({"id": "b3", "kind": "heading", "text": row["name"], "group_id": "g2"})
    elif ambiguity == "duplicate_page":
        pages.append(deepcopy(page))
    elif ambiguity == "unbound":
        page["blocks"][0]["group_id"] = None
    else:
        row["evidence"] = {}
    result = annotate_source_coverage([row], pages, columns("name"))[0]["source_coverage"]
    assert result["additional_details"] == []
    assert "No unique" in result["note"]


def test_one_short_excerpt_does_not_hide_the_rest_of_its_source_block():
    row, page = fixture("Free cancellation until October 27; pay at the property")
    row.update({"cancellation": "Free cancellation", "evidence": {"name": row["name"], "cancellation": "Free cancellation"}})
    result = annotate_source_coverage([row], [page], columns("name", "cancellation"))[0]
    assert result["source_coverage"]["additional_details"][0]["text"] == page["blocks"][1]["text"]


def test_fully_mapped_literal_features_are_not_repeated_as_missing_details():
    row, page = fixture("Free WiFi", "Pool")
    row.update({"amenities": "Free WiFi; Pool", "evidence": {"name": row["name"], "amenities": "Free WiFi Pool"}})
    result = annotate_source_coverage([row], [page], columns("name", "amenities"))[0]
    assert result["source_coverage"]["additional_details"] == []
    assert result["source_coverage"]["missing_fields"] == []


def test_linked_evidence_uses_page_local_block_ids_without_borrowing_uncited_pages():
    row, index = fixture("Index-only summary", name="North Light")
    detail = {
        "url": "https://example.org/item/1", "parent_url": index["url"],
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "North Light", "group_id": "g1"},
            {"id": "b2", "kind": "text", "text": "Solid brass", "group_id": "g1"},
            {"id": "b3", "kind": "text", "text": "Two-year warranty", "group_id": "g1"},
        ],
    }
    uncited = {"url": "https://example.org/item/other", "blocks": deepcopy(detail["blocks"])}
    row.update({"material": "Solid brass", "evidence_sources": {"material": {"source_url": detail["url"], "block_ids": ["b2"]}}})
    row["evidence"]["material"] = "Solid brass"
    result = annotate_source_coverage([row], [index, detail, uncited], columns("name", "material"))[0]["source_coverage"]
    assert {item["source_url"] for item in result["additional_details"]} == {index["url"], detail["url"]}
    warranty = next(item for item in result["additional_details"] if "warranty" in item["text"])
    assert warranty["block_ids"] == ["b3"]


def test_overflow_and_long_source_text_are_disclosed_without_unbounded_body_copying():
    row, page = fixture(*[f"Feature item {index}" for index in range(15)], "Long body " * 60)
    result = annotate_source_coverage([row], [page], columns("name"))[0]["source_coverage"]
    assert len(result["additional_details"]) == 10
    assert result["omitted_details"] == 6
    assert all(len(item["text"]) <= 320 for item in result["additional_details"])


@pytest.mark.parametrize("names", [
    ("hotel_name", "nightly_price", "original_price", "location", "room_type", "amenities", "cancellation", "rating", "listing_url", "unfamiliar_fact"),
    ("headline", "snippet", "published_time", "author", "article_url", "topic", "unfamiliar_fact"),
    ("product_name", "price", "currency", "material", "warranty", "description", "product_url", "unfamiliar_fact"),
])
def test_semantic_groups_cover_each_dynamic_field_once_without_site_templates(names):
    sections = group_output_fields(columns(*names))
    flattened = [field for section in sections for field in section["fields"]]
    assert sorted(flattened) == sorted(names)
    assert len(flattened) == len(set(flattened))
    assert "unfamiliar_fact" in next(section for section in sections if section["id"] == "details")["fields"]


def test_price_context_is_not_selected_as_record_description_and_all_fields_are_grouped():
    names = ("hotel_name", "price_context", "room_description", "unknown_value")
    candidate = SimpleNamespace(
        _explicit_output_fields=set(names), requested_fields=list(names), filters=[], query_rules=[], content_type="records",
        columns=[SimpleNamespace(**column) for column in columns(*names)],
    )
    _, contract = select_output_contract(candidate, [], [{name: "Value" for name in names}])
    assert contract["description_field"] is None  # room details belong to configuration, not the card's summary.
    assert next(section for section in contract["presentation"]["sections"] if section["id"] == "pricing")["fields"] == ["price_context"]
    assert sorted(field for section in contract["presentation"]["sections"] for field in section["fields"]) == sorted(names)


def test_unknown_schema_field_can_use_description_for_display_grouping_only():
    sections = group_output_fields([{"name": "metric", "description": "Guest rating out of ten"}])
    assert sections == [{"id": "feedback", "label": "Ratings & feedback", "fields": ["metric"]}]


def test_presentation_preserves_only_declared_units_and_field_explanations():
    source_columns = [
        {"name": "weight", "kind": "number", "unit": "kg", "description": "Source-displayed shipping weight"},
        {"name": "rating", "kind": "number", "unit": "out of 10", "description": "Displayed guest review score"},
        {"name": "cost", "kind": "number", "unit": "", "description": "Visible amount; currency unconfirmed"},
    ]
    before = deepcopy(source_columns)
    contract = presentation_contract(source_columns)
    assert source_columns == before
    assert contract["field_metadata"] == {
        column["name"]: {key: column[key] for key in ("unit", "description", "kind")}
        for column in source_columns
    }
    assert contract["field_metadata"]["cost"]["unit"] == ""
