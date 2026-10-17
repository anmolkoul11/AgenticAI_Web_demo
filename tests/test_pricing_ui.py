"""Price presentation contracts; local, opt-in browser fixtures only."""

import pytest
from test_source_workflow_ui import source_ui as shared_ui


@pytest.fixture
def pricing_ui(request):
    yield from shared_ui.__wrapped__(request)


def test_price_copy_preserves_total_and_labels_combined_average(pricing_ui):
    text = pricing_ui.evaluate("""() => pricingText({
      status:'verified',scope_status:'verified',displayed_amount:'600',currency:'USD',
      basis_label:'Full-stay total, all requested rooms',combined_nightly:'300',
      calculation:{operation:'stay_total / nights',nights:2,result:'300'},
      taxes_status:'unknown',budget_status:'within_target'
    })""")
    assert "Displayed price: 600 USD" in text
    assert "Average nightly cost, all requested rooms: 300 USD" in text
    assert "divided by nights, not rooms" in text
    assert "Taxes: unknown; fees: unknown" in text


def test_per_room_price_and_unknown_stay_are_not_combined_matches(pricing_ui):
    text = pricing_ui.evaluate("""() => pricingText({
      status:'unverified',scope_status:'mismatch',displayed_amount:'250',currency:'USD',
      basis_label:'Per room, per night',combined_nightly:null,
      taxes_status:'excluded',budget_status:'unverified'
    })""")
    assert "Per room, per night" in text
    assert "Combined nightly cost" not in text
    assert "Displayed stay details differ" in text
    assert "not a verified requested-stay quote" in text


def test_soft_price_target_remains_a_labelled_alternative(pricing_ui):
    state = pricing_ui.evaluate("""() => {
      showPricingSummary({pricing_summary:{applicable:true,verified:3,unverified:1,
        within_target_ready:1,outside_target_ready:2},request_preferences:[{
          request_quote:'around 250-350 USD',currency:'USD',enforcement:'preference',
          conditions:[{operator:'gte',value:'250'},{operator:'lte',value:'350'}]}]});
      return {hidden:pricingPanel.hidden,summary:pricingPanel.textContent,
        alternative:pricingText({status:'verified',scope_status:'verified',
          displayed_amount:'450',currency:'USD',basis_label:'Per night, all requested rooms',
          combined_nightly:'450',budget_status:'outside_target',taxes_status:'included'})};
    }""")
    assert not state["hidden"]
    assert "1 ready records within the price target; 2 outside it" in state["summary"]
    assert "Not a hard exclusion filter" in state["summary"]
    assert "alternative, not a budget match" in state["alternative"]


def test_returned_stay_status_is_separate_from_form_readiness(pricing_ui):
    text = pricing_ui.evaluate("""() => {
      renderBrowserOptions({state:'agent_paused',page_health:{},agent_report:{status:'paused',
        calls:1,max_calls:30,captured_pages:[],actions:[],task_checklist:{
          search_submitted:true,requirements:[{field:'adults',application:'form',
            status:'verified',expected:'4',observed:'4'}],
          result_scope:{status:'mismatch',source:'returned_page'}}}});
      return agentChecklistNote.textContent;
    }""")
    assert "Returned stay: mismatch" in text
    assert "separate from the values entered before Search" in text


def test_multiple_prices_preserve_original_and_do_not_invent_total_basis(pricing_ui):
    state = pricing_ui.evaluate("""() => {
      const panel=pricingPreview({status:'unverified',scope_status:'verified',currency:'USD',
        displayed_amount:'259',issues:['price_basis_unverified'],observations:[
          {amount:'259',currency:'USD',kind:'all_rooms_per_night',role:'current',selected:true,
            quote:'Per night $259',source_url:'https://example.org/results'},
          {amount:'559',currency:'USD',kind:'unknown',role:'current',quote:'$559; 2 nights, 4 adults'},
          {amount:'665',currency:'USD',kind:'unknown',role:'original',quote:'$665'}]});
      return {text:panel.textContent,original:panel.querySelector('s').textContent,
        evidence:[...panel.querySelectorAll('details blockquote')].map(node=>node.textContent)};
    }""")
    assert state["original"] == "665 USD"
    assert "Nightly price · all requested rooms: 259 USD" in state["text"]
    assert "Additional price · basis unverified: 559 USD" in state["text"]
    assert "Full-stay total" not in state["text"]
    assert "not a verified requested-stay quote" in state["text"]
    assert "Per night $259" in state["evidence"]


def test_price_evidence_is_text_and_unknown_currency_is_not_guessed(pricing_ui):
    state = pricing_ui.evaluate("""() => {
      const panel=pricingPreview({status:'unverified',observations:[{
        amount:'259',currency:null,kind:'unknown',role:'unknown',
        quote:'<img src=x onerror=alert(1)> $259',source_url:'javascript:alert(1)'}]});
      return {text:panel.textContent,images:panel.querySelectorAll('img').length,
        links:panel.querySelectorAll('a').length};
    }""")
    assert "259 currency unverified" in state["text"]
    assert "<img src=x onerror=alert(1)> $259" in state["text"]
    assert state["images"] == state["links"] == 0


def test_constraint_panel_reports_only_actual_reason_counts(pricing_ui):
    text = pricing_ui.evaluate("""() => {
      showRequestConstraints({constraint_unverified_records:[{record_id:'record-1',issues:[
        {reason:'price_basis_unverified'},{reason:'price_basis_unverified'}]}]});
      return constraintPanel.textContent;
    }""")
    assert "1 record(s): Price basis is not verified" in text
    assert "unknown values, currency" not in text
    text = pricing_ui.evaluate("""() => {
      showRequestConstraints({criteria_issues_summary:[{reason:'price_observation_ambiguous',
        count:3,label:'Current price selection remains ambiguous'}]});
      return constraintPanel.textContent;
    }""")
    assert "3 record(s): Current price selection remains ambiguous" in text


def test_price_breakdown_survives_full_preview_navigation(pricing_ui):
    state = pricing_ui.evaluate("""() => {
      previewQuality={criteria_unverified_preview:true};
      webTable([{listing_id:'record-1',hotel_name:'Example Hotel',price:'259',pricing:{
        status:'unverified',observations:[{amount:'559',currency:'USD',
          kind:'stay_total_all_rooms',role:'current',quote:'Total $559'}]}},
        {listing_id:'record-2',hotel_name:'Another Hotel',price:null}],
        ['listing_id','hotel_name','price']);
      openRecordPreview(0);
      const text=previewDialog.querySelector('.pricing-preview').textContent;
      openRecordPreview(1);
      return {text,remaining:previewDialog.querySelectorAll('.pricing-preview').length};
    }""")
    assert "Current stay total · all requested rooms: 559 USD" in state["text"]
    assert state["remaining"] == 0
