"""Grouped record presentation; local opt-in fixtures, never a live website/model."""

import pytest
from test_source_workflow_ui import source_ui as shared_ui

from agentic_web_demo.dashboard.app import ASSETS


@pytest.fixture
def grouped_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_grouped_preview_retains_navigation_and_readonly_history_projection():
    script = (ASSETS / "custom.js").read_text(encoding="utf-8")
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert "keys.slice(0, 3)" not in script
    assert "contract.presentation?.sections" in script
    assert "/records?presentation=true" in script
    assert '<div id="web-preview-fields"' in html
    assert "Technical evidence, sources &amp; conflicts" in html
    assert "web-preview-back" in html and "web-view-table" in html
    assert "source_coverage" in script


def test_generic_contract_sections_and_unknown_fields_are_both_visible(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'company_name',description_field:'overview',
        url_field:'profile_url',selected_fields:['company_name','overview','profile_url','office',
          'equipment','minimum_order','is_available','contact_person'],presentation:{sections:[
          {id:'access',label:'Location & contact',fields:['office','contact_person']},
          {id:'capabilities',label:'Capabilities',fields:['equipment','is_available']}]}}};
      webTable([{listing_id:'r1',company_name:'Example Company',overview:'A literal profile.',
        profile_url:'https://example.org/company',office:'Boston',equipment:['Scanner','Printer'],
        minimum_order:0,is_available:false,contact_person:'Example Company',source_coverage:{
          additional_details:[],related_fields:{}}}],
        ['listing_id','company_name','overview','profile_url','office','equipment','minimum_order',
          'is_available','contact_person','source_coverage']);
      return {title:$('web-record-cards').querySelector('h3').textContent,
        groups:[...$('web-record-cards').querySelectorAll('.record-fact-section h4')].map(e=>e.textContent),
        text:$('web-record-cards').textContent,coverage:recordCoverage(previewRows[0]),
        table:$('web-table').querySelector('thead').textContent};
    }""")
    assert state["title"] == "Example Company"
    assert state["groups"] == ["Location & contact", "Capabilities", "Details"]
    assert "Scanner" in state["text"] and "Printer" in state["text"]
    assert "No" in state["text"] and "0" in state["text"]
    assert state["coverage"]["filled"] == 8
    assert "source coverage" not in state["table"]
    # An equal value with a different role must not disappear with the title.
    assert state["text"].count("Example Company") == 2


def test_missing_values_and_unmapped_quotes_do_not_become_confirmed_features(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'name',selected_fields:['name','equipment']}};
      webTable([{listing_id:'r1',name:'Example',equipment:null,source_coverage:{
        additional_details:[{text:'Accessible entrance',source_url:'https://example.org',block_ids:['b2']}],
        related_fields:{equipment:[{text:'Printer available on request',source_url:'https://example.org',block_ids:['b3']}]}}],
        ['listing_id','name','equipment','source_coverage']);
      const card=$('web-record-cards');
      return {facts:card.querySelector('.record-sections').textContent,
        missing:card.querySelector('.record-missing-details').textContent,
        extra:card.querySelector('.record-source-details').textContent,
        collapsed:!card.querySelector('.record-source-details').open,
        coverage:recordCoverage(previewRows[0])};
    }""")
    assert "Accessible entrance" not in state["facts"]
    assert "Printer available" not in state["facts"]
    assert "Related text was captured" in state["missing"]
    assert "Printer available on request" in state["missing"]
    assert "not confirmed output fields" in state["extra"]
    assert "Additional source details (1)" in state["extra"]
    assert "Other source details" in state["extra"]
    assert state["collapsed"] and state["coverage"]["missing"] == ["equipment"]


def test_grouped_source_quotes_keep_provenance_without_promoting_output_fields(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'hotel_name',selected_fields:['hotel_name','features']}};
      const breakfast={text:'Breakfast included',source_url:'https://example.org/search',block_ids:['b47']};
      const stay={text:'2 nights, 4 adults',source_url:'https://example.org/search',block_ids:['b49']};
      const score={text:'Location 9.3',source_url:'https://example.org/search',block_ids:['b51']};
      const row={listing_id:'r1',hotel_name:'Example',features:null,source_coverage:{
        detail_sections:[{id:'terms',label:'Terms & inclusions',details:[breakfast]},
          {id:'configuration',label:'Configuration & capacity',details:[stay]},
          {id:'feedback',label:'Ratings & reviews',details:[score]}],
        additional_details:[breakfast,stay,score],related_fields:{}}};
      const before=JSON.stringify(row);
      webTable([row],['listing_id','hotel_name','features','source_coverage']);
      const card=$('web-record-cards');openRecordPreview(0);
      const full=$('web-preview-fields');
      return {groups:[...card.querySelectorAll('.record-source-section h4')].map(e=>e.textContent),
        quotes:[...card.querySelectorAll('.record-source-details blockquote')].map(e=>e.textContent),
        fullQuotes:[...full.querySelectorAll('.record-source-details blockquote')].map(e=>e.textContent),
        caveat:card.querySelector('.record-source-details>.micro').textContent,
        facts:card.querySelector('.record-sections').textContent,
        links:[...full.querySelectorAll('.source-quote-evidence a')].map(e=>e.href),
        ids:[...full.querySelectorAll('.source-quote-evidence small')].map(e=>e.textContent),
        evidenceCollapsed:[...card.querySelectorAll('.source-quote-evidence')].every(e=>!e.open),
        missing:recordCoverage(row).missing,unchanged:before===JSON.stringify(row)};
    }""")
    assert state["groups"] == ["Terms & inclusions", "Configuration & capacity", "Ratings & reviews"]
    assert state["quotes"] == ["Breakfast included", "2 nights, 4 adults", "Location 9.3"]
    assert state["fullQuotes"] == state["quotes"]
    assert state["links"] == ["https://example.org/search"] * 3
    assert state["ids"] == ["b47", "b49", "b51"]
    assert "verified filter matches" in state["caveat"]
    assert "Breakfast included" not in state["facts"]
    assert state["evidenceCollapsed"] and state["unchanged"]
    assert state["missing"] == ["features"]


def test_partial_and_legacy_source_groups_keep_unfamiliar_quotes_once(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      const known={text:'Recommended for your group',source_url:'https://example.org',block_ids:['b1']};
      const unfamiliar={text:'Unexpected platform-specific wording',source_url:'https://example.org',block_ids:['b2']};
      const coverage={detail_sections:[{id:'promotions',label:'Offers & recommendations',details:[known]}],
        additional_details:[known,unfamiliar],related_fields:{}};
      const partial=recordSourceDetails({source_coverage:coverage});
      const legacy=recordSourceDetails({source_coverage:{additional_details:[unfamiliar]}});
      return {partial:partial.textContent,
        groups:[...partial.querySelectorAll('h4')].map(e=>e.textContent),
        quotes:[...partial.querySelectorAll('blockquote')].map(e=>e.textContent),
        legacy:legacy.textContent,legacyQuotes:legacy.querySelectorAll('blockquote').length};
    }""")
    assert state["groups"] == ["Offers & recommendations", "Other source details"]
    assert state["quotes"] == ["Recommended for your group", "Unexpected platform-specific wording"]
    assert "Additional source details (2)" in state["partial"]
    assert "Other source details" in state["legacy"] and state["legacyQuotes"] == 1


def test_equal_quote_text_with_distinct_sources_keeps_both_evidence_entries(grouped_ui):
    state = grouped_ui.evaluate("""() => sourceDetailSections({source_coverage:{
      detail_sections:[{id:'features',label:'Features & amenities',details:[
        {text:'WiFi',source_url:'https://example.org/one',block_ids:['b1']},
        {text:'WiFi',source_url:'https://example.org/two',block_ids:['b2']}]}],
      additional_details:[{text:'WiFi',source_url:'https://example.org/one',block_ids:['b1']}]
    }}).flatMap(group=>group.details).map(detail=>detail.source_url)""")
    assert state == ["https://example.org/one", "https://example.org/two"]


def test_price_dedup_preserves_roles_source_identifiers_and_original_records(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      const items=[
        {amount:'559.00',currency:'USD',kind:'stay_total_all_rooms',role:'current',quote:'Price $559',block_ids:['b1'],quote_id:'q1'},
        {amount:559,currency:'USD',kind:'stay_total_all_rooms',role:'current',quote:'Current total $559',block_ids:['b2'],quote_ids:['q2'],selected:true},
        {amount:'559',currency:'USD',kind:'all_rooms_per_night',role:'current',quote:'Per night $559',block_ids:['b3']},
        {amount:'559',currency:'USD',kind:'stay_total_all_rooms',role:'original',quote:'Originally $559',block_ids:['b4']}];
      const before=JSON.stringify(items), result=groupedPriceObservations(items);
      return {result,unchanged:before===JSON.stringify(items)};
    }""")
    assert state["unchanged"] and len(state["result"]) == 3
    assert state["result"][0]["selected"]
    assert state["result"][0]["block_ids"] == ["b1", "b2"]
    assert state["result"][0]["quote_ids"] == ["q1", "q2"]
    assert state["result"][0]["quotes"] == ["Price $559", "Current total $559"]
    assert state["result"][2]["role"] == "original"


def test_price_dedup_does_not_round_distinct_decimal_strings(grouped_ui):
    amounts = grouped_ui.evaluate("""() => groupedPriceObservations([
      {amount:'9007199254740992',currency:'USD',kind:'unknown',role:'current'},
      {amount:'9007199254740993',currency:'USD',kind:'unknown',role:'current'},
      {amount:'001.2300',currency:'USD',kind:'unknown',role:'current'},
      {amount:'1.23',currency:'USD',kind:'unknown',role:'current'}
    ]).map(item=>item.amount)""")
    assert amounts == ["9007199254740992", "9007199254740993", "001.2300"]


def test_nightly_and_stay_quotes_are_clear_with_originals_collapsed(grouped_ui):
    grouped_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'name',selected_fields:['name','nightly_price','currency']}};
      webTable([{listing_id:'r1',name:'Example',nightly_price:259,currency:'USD',pricing:{
        status:'verified',combined_nightly:259,currency:'USD',comparison_scope:'all_rooms',
        budget_status:'within_target',scope_status:'verified',displayed_amount:259,
        observations:[{amount:259,currency:'USD',role:'current',kind:'all_rooms_per_night',selected:true,quote:'Per night $259'},
          {amount:559,currency:'USD',role:'current',kind:'stay_total_all_rooms',quote:'2 nights, 4 adults $559'},
          {amount:665,currency:'USD',role:'original',kind:'stay_total_all_rooms',quote:'Original $665'}]}}],
        ['listing_id','name','nightly_price','currency']);setStudioStep('results');
    }""")
    card = grouped_ui.locator("#web-record-cards .record-card")
    assert card.locator(".price-headline").inner_text() == "259 USD"
    assert card.get_by_text("Current stay total · all requested rooms: 559 USD", exact=True).is_visible()
    assert not card.locator("s").is_visible()
    card.get_by_text("Price details & source quotes", exact=True).click()
    assert card.locator("s").inner_text() == "665 USD"
    assert card.get_by_text("Original price · not used for matching:", exact=False).is_visible()
    card.get_by_role("button", name="Preview record & evidence").click()
    assert grouped_ui.get_by_role("button", name="Back to results", exact=True).is_visible()


def test_unknown_total_scope_is_not_labelled_as_all_requested_rooms(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      const section=pricingPreview({status:'unverified',currency:'USD',displayed_amount:559,
        observations:[{amount:559,currency:'USD',role:'current',kind:'stay_total_unknown',quote:'Total $559'}]});
      return {total:section.querySelector('.price-stay-total').textContent,text:section.textContent};
    }""")
    assert state["total"] == "Current stay total · scope unverified: 559 USD"
    assert "all requested rooms" not in state["total"]


def test_source_units_and_descriptions_are_shown_without_inference(grouped_ui):
    state = grouped_ui.evaluate("""() => {
      previewQuality={output_contract:{identity_field:'name',selected_fields:['name','rating','weight','capacity'],
        presentation:{field_metadata:{rating:{unit:'out of 10',description:'Displayed guest score',kind:'number'},
          weight:{unit:'kg',description:'Declared weight',kind:'number'}}}}};
      webTable([{listing_id:'r1',name:'Example',rating:6.6,weight:12,capacity:4}],
        ['listing_id','name','rating','weight','capacity']);
      return [...$('web-record-cards').querySelectorAll('.record-fact-section dt')].map(e=>({label:e.textContent,description:e.title}));
    }""")
    assert {"label": "rating · out of 10", "description": "Displayed guest score"} in state
    assert {"label": "weight · kg", "description": "Declared weight"} in state
    assert {"label": "capacity", "description": ""} in state

