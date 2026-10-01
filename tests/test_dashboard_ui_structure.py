"""Static markup contract checks; no browser or paid model calls."""

import re
from collections import Counter
from html.parser import HTMLParser

from agentic_web_demo.dashboard.app import ASSETS, UI_VERSION


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.views = set()
        self.pages = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-view" in attrs:
            self.views.add(attrs["data-view"])
        if "data-page" in attrs:
            self.pages.add(attrs["data-page"])


def test_dashboard_markup_and_script_contract():
    page = Markup()
    page.feed((ASSETS / "index.html").read_text(encoding="utf-8"))
    assert all(count == 1 for count in Counter(page.ids).values())
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    script += (ASSETS / "custom.js").read_text(encoding="utf-8")
    references = set(re.findall(r'\$\("([^"\n]+)"\)', script))
    assert references <= set(page.ids), references - set(page.ids)
    assert page.views == page.pages == {"custom", "studio", "history", "connection", "admin"}
    assert f'const UI_VERSION = "{UI_VERSION}";' in script
    assert "localStorage" not in script and "sessionStorage" not in script
    assert "innerHTML" not in script
    assert "Find relevant links (paid API)" in script
    assert "Extract current page only (paid API)" in script
    assert "workflow-map" in script
    assert "flowMeter.max = 7" in script
    assert "flowNodes.set(item.id" in script
    assert '{id: "event", title: "Publish event"' in script
    assert "web-advanced" in script
    assert "source-choice" in script
    assert "web-open-normal-browser" in page.ids
    assert "web-open-url" in page.ids
    assert {
        "web-browser-mode-options",
        "web-browser-mode",
        "web-browser-channel",
        "web-browser-mode-help",
        "web-normal-confirm-label",
        "web-normal-confirm",
    } <= set(page.ids)
    assert 'value="restricted" selected' in (ASSETS / "index.html").read_text(encoding="utf-8")
    assert "values.normal_browser_confirmed" in script
    assert 'noLoginOption.value = "none"' in script
    assert 'loginChoice.id = "web-login-choice"' in script
    assert "article discovery" not in script


def test_dashboard_assets_are_local_and_reduced_motion_is_supported():
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    custom_css = (ASSETS / "custom.css").read_text(encoding="utf-8")
    assert 'href="/static/style.css"' in html
    assert 'src="/static/app.js"' in html
    assert "@import" not in css
    assert "prefers-reduced-motion" in css
    assert "skip-link" in html and 'scope="col"' in html
    assert "Website Studio" in html
    assert "article" not in html.split('<section data-page="studio"', maxsplit=1)[0]
    assert "@media(max-width:650px)" in custom_css
