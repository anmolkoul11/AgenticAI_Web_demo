"""Opt-in local DOM regressions. These fixtures make no external website calls."""

from pathlib import Path

import pytest
from test_source_inventory import inventory_browser as shared_browser

from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import Cell, Column, value_supported

COLLECTOR = (
    Path(__file__).resolve().parents[1] / "src/agentic_web_demo/dashboard/static/capture_dom.js"
).read_text(encoding="utf-8")


@pytest.fixture
def dynamic_page(request):
    yield from shared_browser.__wrapped__(request)


def snapshot(page, html):
    page.set_content(html)
    return Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))


def containing(capture, text):
    return next(block for block in capture.blocks if text in block.text)


def test_nested_bed_lists_and_room_tables_share_the_actual_listing_owner(dynamic_page):
    capture = snapshot(dynamic_page, """<main>
      <div data-testid='property-card'>
        <div class='card-header'><a href='/hotel/one'><h3>Harbour Hotel</h3></a></div>
        <div>USD 300</div><div>Per night</div><div>2 nights, 4 adults</div>
        <ul><li>2 bunk beds</li><li>Breakfast included</li></ul>
        <table><tr><td>Room configuration</td><td>2 king beds</td></tr></table>
        <p>Literal listing description and source details for this hotel.</p>
      </div>
      <div data-testid='property-card'>
        <a href='/hotel/two'><h3>Riverside Hotel</h3></a>
        <div>USD 420 per night</div><ul><li>1 queen bed</li></ul>
      </div></main>""")
    first = containing(capture, "Harbour Hotel")
    second = containing(capture, "Riverside Hotel")
    assert first.group_id != second.group_id
    for text in ("USD 300", "Per night", "2 nights, 4 adults", "2 bunk beds", "2 king beds"):
        assert containing(capture, text).group_id == first.group_id
    assert containing(capture, "1 queen bed").group_id == second.group_id
    assert capture.coverage.collector_version == "source-inventory-v6"


def test_generic_product_card_metadata_is_not_split_by_nested_list_markup(dynamic_page):
    capture = snapshot(dynamic_page, """<main><section class='listing'>
      <header class='card-header'><a href='/product/one'><h2>Research notebook</h2></a></header>
      <div>USD 32</div><ul><li>240 pages</li><li>Recycled paper cover</li></ul>
      <p>Original product description with information useful to its purchaser.</p>
      </section></main>""")
    identity = containing(capture, "Research notebook")
    assert containing(capture, "240 pages").group_id == identity.group_id
    assert containing(capture, "Recycled paper cover").group_id == identity.group_id


def test_unlinked_room_subheading_at_same_level_does_not_split_listing_metadata(dynamic_page):
    capture = snapshot(dynamic_page, """<main><div data-testid='property-card'>
      <h3><a href='/hotel/one'>Hotel with room details</a></h3>
      <div>USD 300 per night, 2 nights, 4 adults, 2 rooms</div>
      <h3>Rooms</h3><ul><li>2 king beds</li><li>Breakfast included</li></ul>
      <p>The visible source description belongs to this single hotel listing.</p>
      </div></main>""")
    identity = containing(capture, "Hotel with room details")
    assert containing(capture, "2 king beds").group_id == identity.group_id
    assert containing(capture, "Breakfast included").group_id == identity.group_id


def test_independently_headed_nested_record_keeps_its_own_group(dynamic_page):
    capture = snapshot(dynamic_page, """<main><article>
      <h2><a href='/hotel/main'>Main hotel record</a></h2>
      <ul><li>2 king beds in the main hotel</li></ul>
      <article><h3><a href='/hotel/other'>Separate recommended hotel</a></h3>
        <p>USD 480 per night for the separate recommendation.</p></article>
      <p>USD 300 per night for the main listing.</p>
      </article></main>""")
    main = containing(capture, "Main hotel record")
    other = containing(capture, "Separate recommended hotel")
    assert main.group_id != other.group_id
    assert containing(capture, "2 king beds").group_id == main.group_id
    assert containing(capture, "USD 480").group_id == other.group_id
    assert containing(capture, "USD 300").group_id == main.group_id


def test_parent_wrapper_with_multiple_unheaded_links_does_not_claim_price_owner(dynamic_page):
    capture = snapshot(dynamic_page, """<main><div class='card'>
      <a href='/hotel/one'>First hotel destination</a>
      <a href='/hotel/two'>Second hotel destination</a>
      <p>USD 300 per night; the DOM does not identify which record owns this amount.</p>
      </div></main>""")
    price = containing(capture, "USD 300")
    assert price.association == "ambiguous"
    assert price.group_id is None


def test_live_updates_linking_same_page_keep_container_distinct_groups(dynamic_page):
    capture = snapshot(dynamic_page, """<main><article>
      <h1>Live world politics coverage</h1>
      <article><h2><a href='/live/politics#first'>Diplomatic talks resume</a></h2>
        <p>The first update describes the meeting and its participants.</p></article>
      <article><h2><a href='/live/politics#second'>New statement issued</a></h2>
        <p>The second update describes a newly published official statement.</p></article>
      </article></main>""")
    first = containing(capture, "Diplomatic talks resume")
    second = containing(capture, "New statement issued")
    assert first.href == second.href == "https://news.example.org/live/politics"
    assert first.group_id != second.group_id
    assert containing(capture, "first update").group_id == first.group_id
    assert containing(capture, "second update").group_id == second.group_id


def test_identical_url_and_heading_in_sibling_cards_do_not_merge_wrappers(dynamic_page):
    capture = snapshot(dynamic_page, """<main><div class='card-grid'>
      <article><h2><a href='/live/politics'>Shared live headline</a></h2>
        <p>First independently presented update and source context.</p></article>
      <article><h2><a href='/live/politics'>Shared live headline</a></h2>
        <p>Second independently presented update and source context.</p></article>
      </div></main>""")
    headings = [
        block for block in capture.blocks
        if block.kind == "heading" and block.text == "Shared live headline"
    ]
    assert len(headings) == 2
    assert headings[0].group_id != headings[1].group_id


def test_rendered_label_number_boundaries_preserve_numeric_evidence(dynamic_page):
    capture = snapshot(dynamic_page, """<style>.metric span{display:block}</style><main>
      <article><h2><a href='/hotel/one'>Boundary example hotel</a></h2>
        <p class='metric'><span>Location</span><span>9.4</span></p>
        <p class='metric'><span>Review score</span><span>14,058 reviews</span></p>
        <p>Literal source description containing useful details about the property.</p>
      </article></main>""")
    location = containing(capture, "Location")
    reviews = containing(capture, "Review score")
    assert location.text == "Location 9.4"
    assert reviews.text == "Review score 14,058 reviews"
    number = Column(name="value", kind="number", unit="", description="Source number")
    assert value_supported(Cell(field="value", value="9.4", evidence=location.text), number)
    assert value_supported(Cell(field="value", value="14058", evidence=reviews.text), number)


def test_inline_words_decimal_fragments_and_superscripts_are_not_rewritten(dynamic_page):
    capture = snapshot(dynamic_page, """<main><article>
      <h2><a href='/research/one'>Inline source formatting example</a></h2>
      <p>Inter<strong>national</strong> researchers measured 23m<sup>2</sup> and paid
        <span>US$202</span><span>.05</span> for the study materials.</p>
      <p><span>Formula</span><span>1</span> retains its original contiguous spelling.</p>
      </article></main>""")
    paragraph = containing(capture, "International researchers")
    assert "23m2" in paragraph.text
    assert "US$202.05" in paragraph.text
    assert "Formula1" in containing(capture, "retains its original").text


def test_balanced_listing_metadata_stays_within_existing_capture_limits(dynamic_page):
    cards = "".join(
        f"""<article><h2><a href='/hotel/{index}'>City hotel {index}</a></h2>
          <p>{'Long descriptive source text about the surrounding area. ' * 50}</p>
          <div>USD {250 + index} per night</div><div>2 nights, 4 adults, 2 rooms</div>
          <ul><li>2 king beds</li><li>Breakfast included</li></ul></article>"""
        for index in range(30)
    )
    capture = snapshot(dynamic_page, "<main>" + cards + "</main>")
    for index in range(30):
        identity = next(
            block for block in capture.blocks
            if block.kind == "heading" and block.text == f"City hotel {index}"
        )
        text = " ".join(block.text for block in capture.blocks if block.group_id == identity.group_id)
        assert f"USD {250 + index} per night" in text
        assert "2 nights, 4 adults, 2 rooms" in text
        assert "2 king beds" in text
    assert len(capture.blocks) <= 600
    assert sum(len(block.text) + len(block.href or "") for block in capture.blocks) <= 24000
    assert capture.truncated
