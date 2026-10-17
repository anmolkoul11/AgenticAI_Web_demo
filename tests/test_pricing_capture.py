"""Visible currency source context; opt-in local fixtures, no external websites."""

import pytest
from pydantic import ValidationError
from test_record_capture import payload as capture_payload
from test_record_capture import record_page as shared_page
from test_record_capture import snapshot

from agentic_web_demo.capture import Capture


@pytest.fixture
def pricing_page(request):
    yield from shared_page.__wrapped__(request)


CONTENT = """<main><article><h2><a href='/hotel/source-one'>Source hotel one</a></h2>
<p>US$600 total for 2 nights, 4 adults and 2 rooms, including taxes and fees.</p>
</article></main>"""


def test_capture_retains_one_visible_selected_currency_label(pricing_page):
    pricing_page.set_content(
        '<header><button aria-label="Prices in U.S. Dollar USD">USD</button></header>'
        + CONTENT
    )
    capture = snapshot(pricing_page)
    settings = [block for block in capture.blocks if block.content_role == "currency_setting"]
    assert len(settings) == 1
    assert settings[0].text == "Prices in U.S. Dollar USD"
    assert settings[0].association == "page"
    assert settings[0].group_id is None
    assert capture.coverage.collector_version == "source-inventory-v6"


@pytest.mark.parametrize(
    "controls",
    [
        '<p>News about the USD currency and a dollar $ symbol.</p>',
        '<div style="opacity:0"><button aria-label="Prices in U.S. Dollar USD">USD</button></div>',
        '<button aria-label="Currency: USD">USD</button><button aria-label="Currency: EUR">EUR</button>',
    ],
)
def test_plain_hidden_or_conflicting_currencies_do_not_become_selected_setting(
    pricing_page, controls
):
    pricing_page.set_content(controls + CONTENT)
    capture = snapshot(pricing_page)
    assert not any(block.content_role == "currency_setting" for block in capture.blocks)


def test_rendered_aria_hidden_amount_survives_accessibility_only_basis_label(pricing_page):
    pricing_page.set_content("""<main><article>
      <h2><a href='/hotel/source-one'>Source hotel with a rendered nightly price</a></h2>
      <div aria-hidden='true'><span>US$</span><span>1,234</span><span>.50</span></div>
      <div>Per night</div><div>2 nights, 4 adults, 2 rooms</div>
      <p>The separately accessible label contains no monetary amount.</p>
      <span aria-hidden='true'>PRIVATE DECORATIVE WORDS</span>
      </article></main>""")
    capture = snapshot(pricing_page)
    identity = next(block for block in capture.blocks if block.kind == "heading")
    amount = next(block for block in capture.blocks if block.text == "US$1,234.50")
    assert amount.association == "record" and amount.group_id == identity.group_id
    assert "Per night" in capture.page()["text"]
    assert "PRIVATE DECORATIVE WORDS" not in capture.page()["text"]


def test_scalar_exception_does_not_read_hidden_records_forms_or_attributes(pricing_page):
    pricing_page.set_content(CONTENT + """
      <article><h2>Visible product record with safe public source text</h2>
        <span aria-hidden='true' style='display:none'>USD 919</span>
        <span aria-hidden='true' style='visibility:hidden'>USD 929</span>
        <span aria-hidden='true' style='opacity:0'>USD 939</span>
        <span hidden>USD 949</span><span data-price='USD 959'>Amount pending</span>
        <form><span aria-hidden='true'>USD 969</span><input value='USD 979'></form>
        <button aria-hidden='true'>USD 989</button>
      </article>
      <article aria-hidden='true'><h2>Excluded whole record</h2><span>USD 999</span></article>
      <span aria-hidden='true'>USD 1009</span>""")
    capture = snapshot(pricing_page)
    text = capture.page()["text"]
    for value in (919, 929, 939, 949, 959, 969, 979, 989, 999, 1009):
        assert f"USD {value}" not in text
    assert "Excluded whole record" not in text
    assert "US$600 total" in text


def test_generic_scalar_groups_keep_currencyless_prices_before_long_descriptions(pricing_page):
    cards = "".join(
        f"""<article><h2><a href='/product/{index}'>Public product {index}</a></h2>
          <p>{'Detailed source description with secondary product information. ' * 40}</p>
          <div aria-hidden='true'><span>{1234 + index:,}</span><span>.50</span></div>
          <div>Per item</div><div>12 units available</div></article>"""
        for index in range(35)
    )
    pricing_page.set_content("<main>" + cards + "</main>")
    capture = snapshot(pricing_page)
    for index in range(35):
        identity = next(
            block for block in capture.blocks
            if block.kind == "heading" and block.text == f"Public product {index}"
        )
        amount = next(block for block in capture.blocks if block.text == f"{1234 + index:,}.50")
        assert amount.group_id == identity.group_id and amount.association == "record"
    assert capture.truncated
    assert len(capture.blocks) <= 600
    assert sum(len(block.text) + len(block.href or "") for block in capture.blocks) <= 24000


@pytest.mark.parametrize("prefix", ["USD ", ""])
def test_neighbouring_distinct_scalars_are_not_fused_into_one_price(pricing_page, prefix):
    pricing_page.set_content("""<main><article>
      <h2><a href='/product/source-one'>Source product with separate displayed amounts</a></h2>
      <div><span>AMOUNT100.00</span><span>AMOUNT120.00</span></div>
      <p>Separate public monetary values retain their literal spelling and record owner.</p>
      </article></main>""".replace("AMOUNT", prefix))
    capture = snapshot(pricing_page)
    amounts = [
        block.text for block in capture.blocks
        if block.text in (f"{prefix}100.00", f"{prefix}120.00")
    ]
    assert amounts == [f"{prefix}100.00", f"{prefix}120.00"]


def test_nightly_current_and_struck_amounts_keep_distinct_literal_relationships(pricing_page):
    pricing_page.set_content("""<main><article>
      <h2><a href='/hotel/one'>Example hotel with several displayed quotes</a></h2>
      <div class='prices'><div>Per night <span>$259</span></div>
        <div><s>$665</s> <strong>$559</strong></div>
        <div>2 nights, 4 adults</div></div>
      <p>The quoted room configuration is separately available in the visible listing.</p>
      </article></main>""")
    capture = snapshot(pricing_page)
    amounts = {block.text: block for block in capture.blocks if block.text in ("$259", "$559", "$665")}
    assert set(amounts) == {"$259", "$559", "$665"}
    nightly, current, original = (amounts[value] for value in ("$259", "$559", "$665"))
    assert nightly.value_context.label == "Per night"
    assert current.value_context.label == "2 nights, 4 adults"
    assert "$259" not in current.value_context.quote
    assert original.value_context.struck_through
    assert not nightly.value_context.struck_through and not current.value_context.struck_through
    assert current.value_context.label != nightly.value_context.label
    assert len({block.group_id for block in amounts.values()}) == 1
    for block in amounts.values():
        assert block.text in block.value_context.quote
        assert block.value_context.quote in capture.page()["text"]


def test_rendered_aria_hidden_multi_price_wrapper_keeps_each_scalar_not_private_prose(pricing_page):
    pricing_page.set_content("""<main><article>
      <h2><a href='/hotel/one'>Visible hotel with an accessibility-hidden price cluster</a></h2>
      <div><div>Per night <span>$259</span></div>
        <div aria-hidden='true'><s>$665</s> <strong><span>$</span><span>559</span></strong>
          <span>PRIVATE DECORATIVE WORDS</span></div>
        <div>2 nights, 4 adults</div></div>
      <p>Visible listing details with sufficient public source content for a snapshot.</p>
      <h3 aria-hidden='true'>123456</h3>
      <form aria-hidden='true'><span>$777</span><input value='$778'></form>
      </article><article aria-hidden='true'><h2>Hidden whole record</h2>
        <div><s>$888</s><strong>$889</strong></div></article></main>""")
    capture = snapshot(pricing_page)
    amounts = {block.text: block for block in capture.blocks if block.text in ("$259", "$559", "$665")}
    assert set(amounts) == {"$259", "$559", "$665"}
    assert amounts["$665"].value_context.struck_through
    assert amounts["$559"].value_context.label == "2 nights, 4 adults"
    text = capture.page()["text"]
    for omitted in ("PRIVATE", "123456", "$777", "$778", "$888", "$889", "Hidden whole record"):
        assert omitted not in text


@pytest.mark.parametrize("container", ["paragraph", "table_row"])
@pytest.mark.parametrize("currency", ["$", ""])
def test_multi_price_paragraphs_and_rows_keep_individual_strike_status(
    pricing_page, container, currency
):
    values = f"<s>{currency}665</s> <strong>{currency}559</strong><span>2 nights, 4 adults</span>"
    price = f"<p>{values}</p>" if container == "paragraph" else (
        f"<table><tbody><tr><td>{values}</td></tr></tbody></table>"
    )
    pricing_page.set_content("""<main><article>
      <h2><a href='/hotel/one'>Hotel with multiple amounts inside one semantic block</a></h2>
      PRICE
      <p>Public room configuration and original source details remain in the same record.</p>
      </article></main>""".replace("PRICE", price))
    capture = snapshot(pricing_page)
    original = next(block for block in capture.blocks if block.text == f"{currency}665")
    current = next(block for block in capture.blocks if block.text == f"{currency}559")
    assert original.value_context.struck_through
    assert not current.value_context.struck_through
    assert current.value_context.label == "2 nights, 4 adults"
    assert original.group_id == current.group_id


def test_price_context_is_generic_and_retains_computed_ancestor_strike(pricing_page):
    pricing_page.set_content("""<style>.previous{ text-decoration:line-through; }</style><main>
      <article><h2><a href='/product/one'>Reusable source product</a></h2>
        <div>Per item <span>USD 32.50</span></div>
        <div class='previous'><span>USD 40</span></div>
        <p>Public product description with the source details provided by its seller.</p>
      </article></main>""")
    capture = snapshot(pricing_page)
    current = next(block for block in capture.blocks if block.text == "USD 32.50")
    previous = next(block for block in capture.blocks if block.text == "USD 40")
    assert current.value_context.label == "Per item"
    assert previous.value_context.struck_through
    assert previous.value_context.label == ""


def test_unlabelled_current_amounts_do_not_inherit_record_wide_basis(pricing_page):
    pricing_page.set_content("""<main><article>
      <h2><a href='/product/one'>Product with ambiguous current price choices</a></h2>
      <div><div>Per item</div><span>USD 100</span> <span>USD 120</span></div>
      <p>The record does not identify which of these two current amounts the label describes.</p>
      </article><article>
      <h2><a href='/product/two'>Separate source product</a></h2>
      <div>Per month <span>USD 25</span></div></article></main>""")
    capture = snapshot(pricing_page)
    for value in ("USD 100", "USD 120"):
        block = next(block for block in capture.blocks if block.text == value)
        assert block.value_context is None or not block.value_context.label
    other = next(block for block in capture.blocks if block.text == "USD 25")
    assert other.value_context.label == "Per month"


def test_value_relationships_exclude_hidden_forms_and_share_existing_budget(pricing_page):
    pricing_page.set_content("""<main><article>
      <h2><a href='/product/one'>Public product with visible price</a></h2>
      <div>Per item <span>USD 32</span>
        <form><input value='PRIVATE FORM VALUE'><span>PRIVATE FORM TEXT</span></form>
        <span hidden>PRIVATE HIDDEN VALUE</span></div>
      <p>Public description and information about the item available from the source website.</p>
      </article></main>""")
    capture = snapshot(pricing_page)
    amount = next(block for block in capture.blocks if block.text == "USD 32")
    assert amount.value_context.label == "Per item"
    assert "PRIVATE" not in amount.value_context.quote
    size = sum(
        len(block.text) + len(block.href or "")
        + (len(block.value_context.quote) + len(block.value_context.label) if block.value_context else 0)
        for block in capture.blocks
    )
    assert size <= 24000
    assert capture.coverage.captured_text_chars == sum(len(block.text) for block in capture.blocks)


def test_literal_relationship_contract_is_optional_and_source_quotes_are_not_repeated():
    data = capture_payload("https://news.example.org/product/one")
    assert Capture.model_validate(data).blocks[0].value_context is None
    context = {"quote": "Per item USD 32.50", "label": "Per item",
               "relation": "local_container", "struck_through": False}
    data["blocks"] += [
        {"id": "b2", "kind": "text", "text": "USD 32.50", "group_id": "g1",
         "association": "record", "value_context": context},
        {"id": "b3", "kind": "text", "text": "USD 32.50", "group_id": "g1",
         "association": "record", "value_context": context},
    ]
    assert Capture.model_validate(data).page()["text"].count(context["quote"]) == 1
    data["blocks"][1]["value_context"] = {**context, "label": "Per month"}
    with pytest.raises(ValidationError, match="literal record-local"):
        Capture.model_validate(data)


@pytest.mark.parametrize("budget", ["metadata", "combined"])
def test_relationship_metadata_cannot_expand_existing_capture_budget(budget):
    data = capture_payload("https://news.example.org/product/one")
    context = {"quote": "Per item USD 32.50 " + "x" * 470, "label": "Per item",
               "relation": "local_container", "struck_through": False}
    amount = {"kind": "text", "text": "USD 32.50", "group_id": "g1",
              "association": "record", "value_context": context}
    if budget == "metadata":
        data["blocks"] += [{**amount, "id": f"b{index}"} for index in range(2, 16)]
    else:
        data["blocks"] += [
            {"id": f"b{index}", "kind": "paragraph", "text": "x" * 5900}
            for index in range(2, 6)
        ] + [{**amount, "id": "b6"}]
    with pytest.raises(ValidationError, match="6,000|24,000"):
        Capture.model_validate(data)
