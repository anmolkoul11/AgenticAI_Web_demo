"""Shared branding and packaged icon regressions; no browser or provider calls."""

import json
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "agentic_web_demo" / "dashboard" / "static"
EXTENSION = ROOT / "extensions" / "page-capture"
SVG_NS = "{http://www.w3.org/2000/svg}"


class BrandingMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images = []
        self.favicons = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            self.images.append(attrs)
        if tag == "link" and "icon" in attrs.get("rel", "").split():
            self.favicons.append(attrs)


def test_dashboard_and_extension_share_the_exact_vector_logo():
    canonical = (ASSETS / "logo.svg").read_bytes()
    assert (EXTENSION / "icons" / "logo.svg").read_bytes() == canonical
    svg = ET.fromstring(canonical)
    assert svg.tag == SVG_NS + "svg"
    _, _, width, height = map(float, svg.attrib["viewBox"].split())
    assert width == height and width > 0
    assert svg.find(SVG_NS + "path") is not None
    # Branding assets must remain self-contained on the login page and offline
    # extension surfaces, without remote fonts, scripts or linked images.
    assert svg.find(".//" + SVG_NS + "script") is None
    for element in svg.iter():
        for attribute in element.attrib:
            assert attribute.rsplit("}", 1)[-1] != "href"


@pytest.mark.parametrize("page,logo_path", [
    (ASSETS / "index.html", "/static/logo.svg"),
    (EXTENSION / "sidepanel.html", "icons/logo.svg"),
    (EXTENSION / "popup.html", "icons/logo.svg"),
])
def test_each_interface_uses_the_shared_logo_and_favicon(page, logo_path):
    markup = BrandingMarkup(page.read_text(encoding="utf-8"))
    images = [image for image in markup.images if image.get("src") == logo_path]
    assert len(images) == 1
    # The adjacent product name labels a decorative logo without announcing it
    # twice to screen-reader users.
    assert images[0].get("alt") == ""
    assert any(icon.get("href") == logo_path
               and icon.get("type") == "image/svg+xml" for icon in markup.favicons)


def test_extension_icon_declarations_point_to_valid_matching_png_sizes():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    required_sizes = {"16", "32", "48", "128"}
    assert required_sizes <= manifest["icons"].keys()
    assert {"16", "32", "48"} <= manifest["action"]["default_icon"].keys()
    for definitions in (manifest["icons"], manifest["action"]["default_icon"]):
        for size, relative in definitions.items():
            path = (EXTENSION / relative).resolve()
            assert path.is_relative_to(EXTENSION.resolve())
            data = path.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            assert data[12:16] == b"IHDR"
            assert struct.unpack(">II", data[16:24]) == (int(size), int(size))
    for size, path in manifest["action"]["default_icon"].items():
        assert manifest["icons"][size] == path


def test_branding_does_not_expand_extension_access():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["permissions"]) == {
        "activeTab", "scripting", "storage", "sidePanel", "debugger",
    }
    assert set(manifest["host_permissions"]) == {
        "http://localhost:8120/*", "http://127.0.0.1:8120/*",
    }
