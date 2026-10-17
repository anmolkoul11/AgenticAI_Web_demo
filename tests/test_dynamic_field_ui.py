"""Local opt-in presentation fixtures for inferred fields and missing information."""

import pytest
from test_source_workflow_ui import source_ui as shared_ui


@pytest.fixture
def fields_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_snippets_are_used_in_card_summaries(fields_ui):
    text = fields_ui.evaluate("""() => {
      previewQuality={};
      webTable([{listing_id:'record-1',article_title:'World politics headline',
        article_snippet:'A literal source teaser.',article_url:'https://example.org/story'}],
        ['listing_id','article_title','article_snippet','article_url']);
      return $('web-record-cards').textContent;
    }""")
    assert "A literal source teaser." in text
    assert "No descriptive text" not in text


def test_dynamic_identity_description_and_url_have_no_site_dependency(fields_ui):
    result = fields_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'company_name',description_field:'profile_overview',
        url_field:'url',selected_fields:['company_name','profile_overview','url']}};
      webTable([{listing_id:'record-1',company_name:'Example Company',profile_overview:'A literal profile.',
        url:'https://example.org/company'}],['listing_id','company_name','profile_overview','url']);
      return {title:$('web-record-cards').querySelector('h3').textContent,
        text:$('web-record-cards').textContent,
        source:$('web-record-cards').querySelector('.record-card-source a').href};
    }""")
    assert result["title"] == "Example Company"
    assert "A literal profile." in result["text"]
    assert result["source"] == "https://example.org/company"


def test_contract_panel_explains_empty_inferred_columns_and_bounded_coverage(fields_ui):
    state = fields_ui.evaluate("""() => {
      showOutputContract({output_contract:{selected_fields:['headline','url','author'],
        omitted_inferred_fields:['published_time'],missing_requested_fields:['author'],
        field_coverage:[{field:'author',requested:true,populated:0,missing:3}]},
        collection_coverage:{captured_pages:1,detail_pages:0,truncated_pages:1}});
      return {hidden:outputContractPanel.hidden,text:outputContractPanel.textContent};
    }""")
    assert not state["hidden"]
    assert "3 extracted fields" in state["text"]
    assert "author: 0 populated; 3 missing" in state["text"]
    assert "Empty optional fields omitted: published time" in state["text"]
    assert "not verified whole-website coverage" in state["text"]


def test_computed_pricing_does_not_inflate_source_field_completeness(fields_ui):
    state = fields_ui.evaluate("""() => {
      previewQuality={output_contract:{selected_fields:['hotel_name','price']}};
      previewFields=['listing_id','hotel_name','price','pricing_basis','pricing_combined_nightly'];
      return recordCoverage({hotel_name:'Example Hotel',price:null,pricing_basis:'unknown'});
    }""")
    assert state["names"] == ["hotel_name", "price"]
    assert state["filled"] == 1
    assert state["missing"] == ["price"]
