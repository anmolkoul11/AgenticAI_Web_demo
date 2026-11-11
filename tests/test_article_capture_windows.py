"""Local article layouts and hotel isolation; browser cases are opt-in."""

from test_extension_executor_contract import executor_page

from agentic_web_demo.capture import Capture


def window(page, offset=0, **options):
    return Capture.model_validate(page.evaluate(
        "options => captureDocument(options)",
        {"record_window": True, "record_offset": offset, "record_count": 10, **options},
    ))


def record_titles(captured):
    return {block.text for block in captured.blocks
            if block.association == "record" and block.kind == "heading"}


def test_linked_headlines_without_card_wrappers_survive_multiple_windows(executor_page):
    articles = "".join(
        f'<div><a href="/news/item-{index}"><h2>Team {index} wins its championship</h2>'
        f'<p>Players describe the final and their next match for team {index}.</p></a></div>'
        for index in range(24)
    )
    executor_page.set_content(
        '<nav><a href="/sports">Sports navigation</a></nav><main><h1>Latest headlines</h1>'
        + articles + '</main>'
    )
    found = set()
    for offset in (0, 10, 20):
        captured = window(executor_page, offset, article_records=True)
        names = record_titles(captured)
        assert captured.coverage.records_detected == 24
        assert captured.coverage.records_selected == min(10, 24 - offset)
        assert names == {f"Team {index} wins its championship"
                         for index in range(offset, min(offset + 10, 24))}
        assert not names & found
        assert not any(block.href and block.href.endswith("/sports") for block in captured.blocks)
        found |= names
    assert len(found) == 24


def test_topic_section_cards_precede_general_stories_without_dropping_the_others(executor_page):
    general = "".join(
        f'<article><a href="/news/{index}"><h2>General news headline {index}</h2></a></article>'
        for index in range(55)
    )
    sports = "".join(
        f'<article><a href="/sport/{index}"><h2>Team {index} reaches the final</h2></a></article>'
        for index in range(3)
    )
    executor_page.set_content('<main><h1>Latest news</h1><section><h2>World</h2>' + general
                              + '</section><section><h2>Sport</h2>' + sports + '</section></main>')
    captured = window(executor_page, article_records=True, record_priority_terms=["sports"])
    assert captured.coverage.records_detected == 58
    assert {f"Team {index} reaches the final" for index in range(3)} <= record_titles(captured)
    assert len(record_titles(captured)) == 10
    ordinary = window(executor_page)
    assert record_titles(ordinary) == {f"General news headline {index}" for index in range(10)}


def test_heading_and_paragraph_cards_follow_source_order(executor_page):
    executor_page.set_content('''<main><h1>Latest news</h1>
      <article><a href="/first"><p>First visible headline on the page</p></a></article>
      <article><a href="/second"><h2>Second visible headline on the page</h2></a></article>
      </main>''')
    captured = Capture.model_validate(executor_page.evaluate(
        "() => captureDocument({record_window:true,record_count:1,article_records:true})"
    ))
    assert captured.coverage.records_detected == 2
    assert any(block.text == "First visible headline on the page" and block.association == "record"
               for block in captured.blocks)
    assert not any("Second visible" in block.text for block in captured.blocks)


def test_known_hotel_cards_do_not_gain_unowned_links_as_extra_records(executor_page):
    executor_page.set_content('''<main><h1>Edison hotel results</h1>
      <a href="/help">How to understand the displayed hotel prices</a>
      <article><h2><a href="/hotel/one">First Hotel</a></h2><p>USD 140 per night</p></article>
      <article><h2><a href="/hotel/two">Second Hotel</a></h2><p>USD 170 per night</p></article>
      </main>''')
    captured = window(executor_page)
    assert captured.coverage.records_detected == 2
    assert record_titles(captured) == {"First Hotel", "Second Hotel"}
    assert {"USD 140 per night", "USD 170 per night"} <= {block.text for block in captured.blocks}
    assert not any(block.href and block.href.endswith("/help") for block in captured.blocks)


def test_extension_capture_dispatch_keeps_article_topic_options(executor_page):
    general = "".join(
        f'<article><a href="/news/{index}"><h2>General headline {index}</h2></a></article>'
        for index in range(12)
    )
    executor_page.set_content('<main><h1>Latest news</h1>' + general
        + '<section><h2>Sport</h2><a href="/final"><h2>Team reaches the final</h2></a></section></main>')
    reply = executor_page.evaluate('''async () => {
      const observation = await __agenticTabExecutor.dispatch('observe', {});
      return __agenticTabExecutor.dispatch('capture', {
        document_token:observation.document_token, record_window:true, record_offset:0,
        article_records:true, record_priority_terms:['sports']
      });
    }''')
    captured = Capture.model_validate(reply["capture"])
    assert "Team reaches the final" in record_titles(captured)
    assert captured.coverage.records_detected == 13
