"""Captured item links survive an inferred schema without a URL; local fixtures only."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from test_custom_website import source
from test_dashboard import finished

from agentic_web_demo import custom_service
from agentic_web_demo.capture import Capture
from agentic_web_demo.custom_extract import Extraction, validate_extraction
from agentic_web_demo.dashboard.service import DashboardService


INDEX = "https://www.booking.com/searchresults.html"
FIRST = "https://www.booking.com/hotel/us/north.html"
SECOND = "https://www.booking.com/hotel/us/south.html"


def captured():
    return {
        "url": INDEX, "source_kind": "page", "truncated": False,
        "text": f"North Hotel {FIRST}\nSouth Hotel {SECOND}",
        "blocks": [
            {"id": "b1", "kind": "heading", "text": "North Hotel", "href": FIRST,
             "group_id": "g1", "association": "record"},
            {"id": "b2", "kind": "heading", "text": "South Hotel", "href": SECOND,
             "group_id": "g2", "association": "record"},
        ],
    }


def candidate():
    return Extraction.model_validate({
        "outcome": "ready", "guidance": "Review hotels", "content_type": "hotels",
        "interpretation": "Hotel names visible in the list", "warnings": [],
        "more_records_available": False, "filters": [],
        "columns": [{"name": "hotel_name", "kind": "text", "unit": "",
                     "description": "Captured hotel name"}],
        "rows": [{"page_index": 0, "cells": [
            {"field": "hotel_name", "value": name, "evidence": name}
        ]} for name in ("North Hotel", "South Hotel")],
    })


def validated(page):
    values = source(urls=[INDEX], instructions="Get hotel names", page_text=page["text"])
    rows, excluded = validate_extraction(candidate(), values, [page])
    assert len(rows) == 2 and excluded == 0
    return rows


def test_individual_links_are_kept_without_a_model_url_column():
    page = captured()
    # An unrelated action in the card must not replace its exact name link.
    page["blocks"].append({"id": "b3", "kind": "link", "text": "Sign in",
                           "href": "https://account.booking.com/auth/oauth2",
                           "group_id": "g1", "association": "record"})
    rows = validated(page)
    assert [row["record_url"] for row in rows] == [FIRST, SECOND]
    assert all(row["source_url"] == INDEX for row in rows)
    assert rows[0]["evidence"] == {"hotel_name": "North Hotel"}
    assert not any("hotel_url" in row for row in rows)


def test_unique_link_in_the_identity_group_is_kept():
    page = captured()
    page["blocks"][0]["href"] = None
    page["blocks"].append({"id": "b3", "kind": "link", "text": "View hotel",
                           "href": FIRST, "group_id": "g1", "association": "record"})
    assert validated(page)[0]["record_url"] == FIRST


def test_conflicting_identity_links_are_not_guessed():
    page = captured()
    other = deepcopy(page["blocks"][0])
    other.update(id="b3", href="https://www.booking.com/hotel/us/other.html")
    page["blocks"].append(other)
    rows = validated(page)
    assert "record_url" not in rows[0]
    assert rows[1]["record_url"] == SECOND


def test_ambiguous_source_association_still_rejects_the_record():
    page = captured()
    page["blocks"][0]["association"] = "ambiguous"
    values = source(urls=[INDEX], instructions="Get hotel names", page_text=page["text"])
    rejected = []
    rows, _ = validate_extraction(candidate(), values, [page], rejected=rejected)
    assert [row["hotel_name"] for row in rows] == ["South Hotel"]
    assert rows[0]["record_url"] == SECOND
    assert any(issue["reason"] == "ambiguous_record_association"
               for item in rejected for issue in item["issues"])


def test_page_wide_link_is_not_promoted_to_an_individual_hotel_link():
    page = captured()
    page["blocks"][0]["href"] = None
    page["blocks"].append({"id": "b3", "kind": "link", "text": "Hotels",
                           "href": FIRST, "association": "page"})
    assert "record_url" not in validated(page)[0]


def test_unusable_url_is_not_retained_as_record_metadata():
    page = captured()
    page["blocks"][0]["href"] = "javascript:alert(1)"
    assert "record_url" not in validated(page)[0]


def test_approved_snapshot_and_export_keep_individual_links_without_enrichment(tmp_path, monkeypatch):
    page = captured()
    capture = Capture(version=1, url=INDEX, captured_at=datetime.now(UTC), truncated=False,
                      blocks=page["blocks"])
    values = source(source="capture", urls=[INDEX], page_text="", capture=capture,
                    instructions="Get hotel names")
    monkeypatch.setattr(custom_service, "interpret", lambda *_: (candidate(), {"model": "fixture"}))
    service = DashboardService(tmp_path, Path("config/rules.yaml"), "http://127.0.0.1:8000")
    try:
        planned = finished(service, custom_service.plan(service, values, object()))
        assert planned["status"] == "awaiting_review", planned
        result = planned["result"]
        proposal = result["proposal"]
        assert not proposal.get("enrichment")
        assert [row["record_url"] for row in proposal["records"]] == [FIRST, SECOND]
        saved = finished(service, custom_service.execute(
            service, proposal["plan_id"], result["revision"]
        ))
        assert saved["status"] == "completed", saved
        snapshot = service.records(saved["job_id"])
        assert "record_url" in snapshot["columns"]
        assert [row["record_url"] for row in snapshot["records"]] == [FIRST, SECOND]
        assert all(row["source_url"] == INDEX for row in snapshot["records"])
    finally:
        service.close()
