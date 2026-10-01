"""Offline export coverage; no browser, broker or model calls."""

import csv
import io
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from agentic_web_demo.exports import ExportError, build_export


def export(payload, format, **kwargs):
    return build_export(payload, format, run_id="fixture", framework="langgraph", **kwargs)[0]


@pytest.mark.parametrize("value", ["=SUM(1,2)", "+cmd", "-123", "@name", " \t=BAD()", "\ntext"])
def test_csv_formula_text(value):
    content = export({"records": [{"=header": value}]}, "csv")
    assert content.startswith(b"\xef\xbb\xbf")
    assert list(csv.reader(io.StringIO(content.decode("utf-8-sig")))) == [
        ["'=header"],
        ["'" + value],
    ]


def test_dynamic_columns_unicode_and_nested_values():
    records = [
        {"headline": "Café, news\nToday", "tags": ["news"], "empty": None},
        {"author": "Ana"},
    ]
    content = export({"records": records}, "csv").decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(content)))
    assert list(rows[0]) == ["headline", "tags", "empty", "author"]
    assert rows[0]["headline"] == records[0]["headline"]
    assert rows[0]["tags"] == '["news"]'
    assert rows[0]["empty"] == ""
    assert [
        json.loads(line) for line in export({"records": records}, "jsonl").splitlines()
    ] == records
    assert (
        json.loads(export({"records": records, "source": "fixture"}, "json"))["source"] == "fixture"
    )


def test_filtered_export_and_default_full_export():
    payload = {
        "listings": [
            {"listing_id": "1", "title": "North", "city": "Boston"},
            {"listing_id": "2", "title": "South", "city": "Boston"},
        ]
    }
    decisions = [{"listing_id": "1", "matched": True}, {"listing_id": "2", "matched": False}]
    assert len(json.loads(export(payload, "json", search="missing"))["listings"]) == 2
    result = export(
        payload, "json", scope="filtered", search="north", outcome="matched", decisions=decisions
    )
    assert json.loads(result)["listings"] == payload["listings"][:1]
    assert export(payload, "jsonl", scope="filtered", search="missing") == b""


def test_excel_explicit_text_dates_numbers_and_evidence():
    payload = {
        "listings": [
            {
                "listing_id": "001",
                "title": "=BAD()",
                "price": "150.25",
                "check_in": "2026-09-29",
                "source_url": "https://example.org",
            }
        ]
    }
    content = export(
        payload, "xlsx", decisions=[{"listing_id": "001", "matched": True, "reasons": []}]
    )
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        assert [s.attrib["name"] for s in workbook.findall("s:sheets/s:sheet", ns)] == [
            "Records",
            "Export info",
            "Rule decisions",
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        assert not sheet.findall(".//s:f", ns)
        assert not sheet.findall(".//s:hyperlink", ns)
        cells = {c.attrib["r"]: c for c in sheet.findall(".//s:c", ns)}
        assert cells["A2"].attrib["t"] == "s"
        assert cells["B2"].attrib["t"] == "s"
        assert cells["F2"].find("s:v", ns).text == "150.25"
        assert cells["D2"].find("s:v", ns) is not None
        strings = archive.read("xl/sharedStrings.xml").decode()
        assert "001" in strings and "=BAD()" in strings


def test_excel_rejects_truncation_and_limits():
    with pytest.raises(ExportError, match="text limit"):
        export({"records": [{"body": "x" * 32768}]}, "xlsx")
    with pytest.raises(ExportError, match="10,000"):
        export({"records": [{}] * 10001}, "csv")
    with pytest.raises(ExportError, match="128-column"):
        export({"records": [{str(i): i for i in range(129)}]}, "csv")
    with pytest.raises(ExportError, match="scope"):
        export({"records": []}, "json", scope="invalid")


def test_empty_exports_keep_headers():
    assert (
        export({"records": [], "columns": ["headline", "url"]}, "csv").decode("utf-8-sig").strip()
        == "headline,url"
    )
    assert export({"listings": []}, "csv").decode("utf-8-sig").startswith("listing_id,title,")
