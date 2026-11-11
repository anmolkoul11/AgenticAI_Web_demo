"""Opt-in local DOM regressions, authored without running a browser."""

from datetime import date, timedelta

import pytest

from test_extension_executor_contract import executor_page


def test_icon_month_arrows_and_two_months_survive_crowded_popup(executor_page):
    days = [date(2026, 11, 1) + timedelta(days=n) for n in range(61)]
    choices = "".join(f'<button data-date="{day}">{day}</button>' for day in days)
    background = "".join(f'<button>Other choice {n}</button>' for n in range(180))
    executor_page.set_content(f'''<main><div role="dialog" aria-label="Calendar">
      {background}<button><svg width="16" height="16" viewBox="0 0 16 16">
      <path d="M 10 2 L 4 8 L 10 14" fill="none" stroke="black"/></svg></button>
      {choices}<button><svg width="16" height="16" viewBox="0 0 16 16">
      <path d="M 4 2 L 10 8 L 4 14" fill="none" stroke="black"/></svg></button>
      </div></main>''')
    result = executor_page.evaluate("() => __agenticTabExecutor.dispatch('observe', {focus:'form'})")
    fields = result["frame"]["controls"]
    arrows = [item for item in fields if item.get("date_navigation")]
    assert {item["date_navigation"] for item in arrows} == {"previous", "next"}
    assert len({item["date_widget_id"] for item in arrows}) == 1
    assert {item["date"] for item in fields if item.get("date_kind") == "day_choice"} == {str(day) for day in days}


def test_collector_retains_only_selected_page_price_mode(executor_page):
    executor_page.set_content('''<header><button>Nightly price with fees</button>
      <div role="menu" hidden><button>Total price</button></div></header>
      <main><article><h2>Example Hotel</h2><p>$106</p></article></main>''')
    captured = executor_page.evaluate("() => captureDocument()")
    settings = [block for block in captured["blocks"] if block.get("content_role") == "price_setting"]
    assert len(settings) == 1 and settings[0]["text"] == "Nightly price with fees"
    assert settings[0]["association"] == "page" and settings[0]["group_id"] is None


@pytest.mark.parametrize("caption", [
    '<button aria-label="Choose price display">Nightly price with fees</button>',
    '<span>Nightly price with fees</span>',
    '<span aria-hidden="true">Nightly price with fees</span>',
    '<a role="button" aria-expanded="true">Nightly price with fees</a>',
])
def test_price_mode_inside_page_heading_wrapper_is_not_a_hotel_feature(executor_page, caption):
    executor_page.set_content(f'''<main><div><h1>Virginia Hotels</h1><div>{caption}</div>
      <div role="menu"><button>Total price</button></div>
      <article><h2><a href="/hotel/first">First Hotel</a></h2><p>$140</p></article>
      <article><h2><a href="/hotel/second">Second Hotel</a></h2><p>$170</p></article>
      </div></main>''')
    captured = executor_page.evaluate("() => captureDocument()")
    settings = [block for block in captured["blocks"] if block.get("content_role") == "price_setting"]
    assert [block["text"] for block in settings] == ["Nightly price with fees"]
    assert captured["coverage"]["price_setting_status"] == "captured"
    assert captured["coverage"]["price_settings_detected"] == 1


def test_card_basis_and_hidden_captions_do_not_become_global_price_mode(executor_page):
    executor_page.set_content('''<main><h1>Virginia Hotels</h1>
      <span hidden>Nightly price with fees</span>
      <article><h2><a href="/hotel/one">Example Hotel</a></h2>
      <p>$140</p><span>Nightly price with fees</span></article></main>''')
    captured = executor_page.evaluate("() => captureDocument()")
    assert not any(block.get("content_role") == "price_setting" for block in captured["blocks"])
    assert captured["coverage"]["price_setting_status"] == "not_found"


def test_sixty_listing_cards_survive_disjoint_capture_windows(executor_page):
    cards = "".join(f'''<article><h2><a href="/hotel/{index}">Hotel {index}</a></h2>
      <p>USD {100 + index} per night</p><p>{'Useful source description. ' * 22}</p>
      </article>''' for index in range(60))
    executor_page.set_content('<main><h1>Hotel results</h1><button>Nightly price with fees</button>' + cards + '</main>')
    found = set()
    for offset in range(0, 60, 10):
        capture = executor_page.evaluate("offset => captureDocument({record_window:true,record_offset:offset,record_count:10})", offset)
        assert capture["coverage"]["record_window"] and capture["coverage"]["records_selected"] == 10
        assert capture["coverage"]["records_detected"] == 60
        names = {block["text"] for block in capture["blocks"] if block["kind"] == "heading" and block.get("association") == "record"}
        assert names == {f"Hotel {index}" for index in range(offset, offset + 10)}
        assert not names & found
        found |= names
    assert len(found) == 60


def test_observed_next_page_survives_background_control_limit(executor_page):
    links = ''.join(f'<a href="/hotel/{index}">Hotel {index}</a>' for index in range(250))
    executor_page.set_content('<main>' + links + '<nav aria-label="Pagination"><a rel="next" href="/results?page=2">Next page</a></nav></main>')
    observation = executor_page.evaluate("() => __agenticTabExecutor.dispatch('observe', {focus:'collection'})")
    assert any(item.get("pagination") == "next" and item["label"] == "Next page" for item in observation["frame"]["controls"])


def test_result_pagination_cannot_displace_destination_options_during_search(executor_page):
    links = ''.join(f'<a rel="next" href="/results?page={index}">Next page</a>' for index in range(160))
    executor_page.set_content('<main>' + links + '''<div role="listbox">
      <div role="option">New York, United States</div></div></main>''')
    observation = executor_page.evaluate("() => __agenticTabExecutor.dispatch('observe', {focus:'form'})")
    assert any(item["label"] == "New York, United States" for item in observation["frame"]["controls"])


def test_record_windows_keep_literal_list_availability_warning_as_page_context(executor_page):
    executor_page.set_content('''<main><h1>Edison: 16 properties found</h1>
      <div>Some options have fewer than 4 rooms.
      <a href="/results?rooms=4">Only show results with 4 rooms or more.</a></div>
      <article><h2><a href="/hotel/one">Example Hotel</a></h2>
      <p>2 nights, 6 adults</p><p>USD 593 per night</p></article></main>''')
    captured = executor_page.evaluate("() => captureDocument({record_window:true,record_count:10})")
    notices = [block for block in captured["blocks"] if block["text"].startswith("Some options have fewer")]
    assert len(notices) == 1
    assert notices[0]["association"] == "page" and notices[0]["group_id"] is None
    assert "Only show results with 4 rooms or more." in notices[0]["text"]

