"""Coherent source-record snapshots; browser fixtures are local and opt-in."""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from test_source_inventory import inventory_browser as shared_browser

from agentic_web_demo.capture import Capture, clean_url, query_identity_omitted

COLLECTOR = (
    Path(__file__).resolve().parents[1] / "src/agentic_web_demo/dashboard/static/capture_dom.js"
).read_text(encoding="utf-8")


@pytest.fixture
def record_page(request):
    yield from shared_browser.__wrapped__(request)


def snapshot(page):
    return Capture.model_validate(page.evaluate("(" + COLLECTOR + ")"))


def payload(href):
    return {
        "version": 1,
        "url": "https://news.example.org/",
        "captured_at": datetime.now(UTC).isoformat(),
        "truncated": False,
        "blocks": [
            {
                "id": "b1",
                "kind": "heading",
                "text": (
                    "A sufficiently descriptive literal source headline for this local record "
                    "and its evidence"
                ),
                "href": href,
                "group_id": "g1",
                "association": "record",
            }
        ],
    }


def test_evidence_urls_drop_tracking_but_retain_query_record_identity():
    first = "https://news.example.org/detail?id=one&label=" + "attribution" * 120
    second = "https://news.example.org/detail?id=two&sid=fixture-only#heading"
    assert clean_url(first) == "https://news.example.org/detail?id=one"
    assert clean_url(second) == "https://news.example.org/detail?id=two"
    assert clean_url(
        "https://news.example.org/story/one?token=fixture&email=fixture@example.org"
    ) == ("https://news.example.org/story/one")
    assert clean_url("https://news.example.org/detail?id=literal+word~value") == (
        "https://news.example.org/detail?id=literal+word~value"
    )


def test_unknown_query_identity_is_not_repaired_as_a_unique_detail_url():
    assert query_identity_omitted("https://news.example.org/view?document=one")
    assert query_identity_omitted("https://news.example.org/view?id=one&document=extra")
    assert not query_identity_omitted("https://news.example.org/story/one?label=attribution")
    capture = Capture.model_validate(payload("https://news.example.org/view?document=one"))
    assert capture.blocks[0].href is None
    assert capture.blocks[0].association == "ambiguous"
    assert capture.truncated


def test_query_identity_is_bounded_and_does_not_keep_account_values():
    for value in ("fixture@example.org", "https://account.example.org/login", "x" * 129):
        assert clean_url("https://news.example.org/view?id=" + value) == (
            "https://news.example.org/view"
        )
    assert clean_url("https://news.example.org/?q=fixture-secret&search=fixture") == (
        "https://news.example.org/"
    )


@pytest.mark.parametrize("path", ["/detail", "/hotel/property-one"])
def test_dropped_identity_is_ambiguous_even_with_retained_variant(path):
    for identifier in ("x" * 129, "\u7814" * 60):
        url = "https://news.example.org" + path + "?id=" + quote(identifier) + "&variant=standard"
        assert query_identity_omitted(url)
        capture = Capture.model_validate(payload(url))
        assert capture.blocks[0].href is None
        assert capture.blocks[0].association == "ambiguous"
    assert query_identity_omitted("https://news.example.org/view?code=one")
    assert query_identity_omitted("https://news.example.org/view?id=one&document=other")


def test_unicode_path_and_query_are_encoded_without_changing_identity():
    assert clean_url("https://news.example.org/\u7814\u7a76?id=\u7814\u7a76") == (
        "https://news.example.org/%E7%A0%94%E7%A9%B6?id=%E7%A0%94%E7%A9%B6"
    )


def test_long_query_hotel_cards_keep_prices_ratings_and_source_bound_urls(record_page):
    tracking = "x" * 1400
    cards = "".join(
        f"""<li class='result'>
          <a href='/hotel/property-{i}?aid=123&amp;label={tracking}&amp;sid=fixture-only'>
            <h2>Hotel property {i} beside the city park</h2></a>
          <p>{"Enjoy your stay near the park and read the guest reviews. " * 30}</p>
          <div><span>USD {250 + i}</span><span> per night including taxes</span></div>
          <div><span>Guest rating</span><span>8.{i % 10}</span><span>out of 10</span></div>
          <a href='/hotel/property-{i}/reviews'>Read guest reviews</a>
        </li>"""
        for i in range(25)
    )
    headings = "".join(f"<h2>Secondary section heading {i}</h2>" for i in range(108))
    record_page.set_content("<main><ul>" + cards + "</ul>" + headings + "</main>")
    capture = snapshot(record_page)
    assert capture.coverage.collector_version == "source-inventory-v6"
    for index in range(25):
        identity = next(
            block
            for block in capture.blocks
            if block.text == (f"Hotel property {index} beside the city park")
            and block.kind == "heading"
        )
        group = [block for block in capture.blocks if block.group_id == identity.group_id]
        text = " ".join(block.text for block in group)
        assert f"USD {250 + index}" in text
        assert "per night including taxes" in text
        assert f"8.{index % 10}" in text
        assert identity.href == f"https://news.example.org/hotel/property-{index}"
        assert all("label=" not in (block.href or "") for block in group)
    assert capture.truncated and capture.coverage.omitted_text_chars > 0
    assert sum(len(block.text) + len(block.href or "") for block in capture.blocks) <= 24000
    assert len(capture.blocks) <= 600


def test_detail_article_headline_and_body_survive_record_prioritization(record_page):
    record_page.set_content("""<article>
      <header><h1>Soccer researchers publish a new training study</h1></header>
      <main><div class='article-body'>
        <p>The researchers examined training sessions across several soccer clubs.</p>
        <p>The source article explains the actual study methods and limitations.</p>
        <p>Additional visible research context belongs to the same opened article.</p>
      </div></main></article>""")
    capture = snapshot(record_page)
    headline = next(block for block in capture.blocks if block.content_role == "headline")
    paragraphs = [block for block in capture.blocks if block.content_role == "body"]
    assert headline.text == "Soccer researchers publish a new training study"
    assert len(paragraphs) == 3
    assert all(block.group_id == headline.group_id for block in paragraphs)
    assert not capture.truncated


def test_article_body_precedes_large_recommendation_card_inventory(record_page):
    body_text = "The actual soccer study reports its methods, results and limitations. " * 60
    recommendations = "".join(
        f"<li><a href='/related/{index}'><h2>Related recommendation {index}</h2></a>"
        f"<p>{'Other visible recommendation information. ' * 80}</p></li>"
        for index in range(45)
    )
    record_page.set_content(
        "<article><h1>Soccer researchers publish a new training study</h1>"
        "<div class='article-body'><p>" + body_text + "</p></div></article>"
        "<aside><ul>" + recommendations + "</ul></aside>"
    )
    capture = snapshot(record_page)
    paragraph = next(block for block in capture.blocks if block.content_role == "body")
    assert paragraph.text == body_text.strip()
    headline = next(block for block in capture.blocks if block.content_role == "headline")
    assert paragraph.group_id == headline.group_id
    assert capture.truncated


def test_query_distinct_cards_keep_separate_identity_and_navigation_urls(record_page):
    record_page.set_content("""<main><ul>
      <li><a href='/detail?id=one&amp;utm_source=fixture'><h2>Source record one</h2></a>
        <p>USD 251 per night, guest rating 8.1 out of 10.</p></li>
      <li><a href='/detail?id=two&amp;utm_source=fixture'><h2>Source record two</h2></a>
        <p>USD 302 per night, guest rating 9.2 out of 10.</p></li>
      </ul></main>""")
    capture = snapshot(record_page)
    first = next(block for block in capture.blocks if block.text == "Source record one")
    second = next(block for block in capture.blocks if block.text == "Source record two")
    assert first.group_id != second.group_id
    assert first.href == "https://news.example.org/detail?id=one"
    assert second.href == "https://news.example.org/detail?id=two"
    # The collector's link-discovery mode still carries the actual navigation URL.
    links = record_page.evaluate("(" + COLLECTOR + ")", {"mode": "links"})
    assert all("utm_source=fixture" in item["url"] for item in links)


def test_unicode_capture_matches_python_counts_and_query_normalization(record_page):
    identifier = "x" * 100 + "\U0001f600" * 20
    raw_url = "https://news.example.org/\u7814\u7a76?id=" + quote(identifier)
    record_page.set_content(
        "<main><li><a href='" + raw_url + "'><h2>Soccer \U0001f600 research headline</h2></a>"
        "<p>Literal source context \U0001f600 and research evidence shown in the opened page. "
        "No field is inferred by this local capture fixture.</p></li></main>"
    )
    capture = snapshot(record_page)
    headline = next(block for block in capture.blocks if block.kind == "heading")
    assert headline.href == clean_url(raw_url)
    assert capture.coverage.captured_text_chars == sum(len(block.text) for block in capture.blocks)
    assert "\U0001f600" in capture.page()["text"]


def test_text_budget_clipping_does_not_split_unicode_surrogate_pairs(record_page):
    record_page.set_content("<main><p>" + "x" * 5999 + "\U0001f600 Source tail.</p></main>")
    capture = snapshot(record_page)
    assert all(
        not any(0xD800 <= ord(character) <= 0xDFFF for character in block.text)
        for block in capture.blocks
    )
    assert capture.truncated and "cell_text_limit" in capture.coverage.limit_reasons


def test_unknown_query_cards_disclose_missing_identity_without_wrong_link(record_page):
    record_page.set_content("""<main><ul>
      <li><a href='/view?document=one'><h2>First query-addressed source record</h2></a>
        <p>Literal source description with the first record's details.</p></li>
      <li><a href='/view?document=two'><h2>Second query-addressed source record</h2></a>
        <p>Literal source description with the second record's details.</p></li>
      </ul></main>""")
    capture = snapshot(record_page)
    headlines = [block for block in capture.blocks if block.kind == "heading"]
    assert len(headlines) == 2
    assert all(block.href is None and block.association == "ambiguous" for block in headlines)
    assert "url_identity_omitted" in capture.coverage.limit_reasons
    assert capture.truncated


def test_current_query_addressed_page_discloses_lost_identity(record_page):
    record_page.goto("https://news.example.org/view?document=source-one")
    record_page.set_content("""<article><h1>Source article about a soccer research study</h1>
      <p>Literal article content includes the study context and evidence actually
      shown on this query-addressed page, rather than invented information.</p></article>""")
    capture = snapshot(record_page)
    assert capture.url == "https://news.example.org/view"
    assert capture.coverage.page_url_identity_omitted is True
    assert "url_identity_omitted" in capture.coverage.limit_reasons
    assert capture.truncated
    assert any(block.content_role == "body" for block in capture.blocks)


def test_current_path_addressed_page_ignores_only_tracking_query(record_page):
    record_page.goto("https://news.example.org/story/source-one?label=attribution")
    record_page.set_content("""<article><h1>Source article about a soccer research study</h1>
      <p>Literal source article context is available from this ordinary content path.
      The discarded attribution query does not identify a different article.</p></article>""")
    capture = snapshot(record_page)
    assert capture.url == "https://news.example.org/story/source-one"
    assert capture.coverage.page_url_identity_omitted is False
    assert not capture.truncated


def test_insufficient_content_raises_distinct_capture_marker(record_page):
    record_page.set_content("<main><p>No results.</p></main>")
    with pytest.raises(Exception, match="CAPTURE_INSUFFICIENT_CONTENT"):
        record_page.evaluate("(" + COLLECTOR + ")")
