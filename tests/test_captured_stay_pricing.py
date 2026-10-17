"""Captured returned-heading pricing regressions; authored without execution."""

from copy import deepcopy
from types import SimpleNamespace

from agentic_web_demo.pricing import assess_pricing
from agentic_web_demo.stay_scope import reconcile_captured_result_scope


URL = "https://example.org/searchresults.html"
DOCUMENT_ID = "returned-results-document"
PROMPT = (
    "Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 "
    "for 4 adults and 2 rooms, around 250-350 USD nightly."
)
REQUESTED = {
    "destination": "New York",
    "check_in": "2026-10-28",
    "check_out": "2026-10-30",
    "nights": 2,
    "adults": 4,
    "rooms": 2,
}


def _returned_scope():
    """Independent returned facts, not pre-submit form read-back."""
    observed = {
        "destination": None,
        "check_in": "2026-10-28",
        "check_out": "2026-10-30",
        "adults": "4",
        "rooms": "2",
    }
    fields = [{
        "field": "destination", "expected": "New York", "observed": None,
        "status": "unverified", "method": "none",
        "evidence": "No fresh returned-page value.",
    }]
    for field in ("check_in", "check_out", "adults", "rooms"):
        fields.append({
            "field": field, "expected": REQUESTED[field],
            "observed": observed[field], "status": "verified",
            "method": "returned_url", "evidence": f"{field}={observed[field]}",
        })
    return {
        "status": "unverified", "requested": deepcopy(REQUESTED),
        "observed": observed, "fields": fields, "contradictions": [],
        "document_id": DOCUMENT_ID, "source": "returned_page",
        "availability_verified": False,
    }


def _price_block(identifier, text, quote, label="", *, original=False):
    return {
        "id": identifier, "kind": "text", "text": text,
        "group_id": "g2", "association": "record",
        "value_context": {
            "quote": quote, "label": label, "relation": "local_container",
            "struck_through": original,
        },
    }


def _fixture(heading="New York: 372 properties found"):
    row = {
        "listing_id": "record-0001", "hotel_name": "West Side YMCA",
        "price_per_night": "282", "source_url": URL,
        "evidence": {
            "hotel_name": "West Side YMCA", "price_per_night": "Per night $282",
        },
    }
    page = {
        "url": URL,
        "blocks": [
            {
                "id": "b1", "kind": "heading", "text": heading,
                "heading_level": 1, "association": "page", "group_id": None,
            },
            {
                "id": "b21", "kind": "heading", "text": "West Side YMCA",
                "heading_level": 3, "association": "record", "group_id": "g2",
            },
            _price_block("b26", "$282", "Per night $282", "Per night"),
            _price_block("b27", "$720", "$720", original=True),
            _price_block("b28", "$605", "$605 2 nights, 4 adults", "2 nights, 4 adults"),
            {
                "id": "b31", "kind": "text", "text": "2 nights, 4 adults",
                "group_id": "g2", "association": "record",
            },
            {
                "id": "b505", "kind": "text", "text": "Prices in U.S. Dollar USD",
                "association": "page", "content_role": "currency_setting",
            },
        ],
        "browser_task_context": {"result_scope": _returned_scope()},
    }
    columns = [
        SimpleNamespace(name="hotel_name", kind="text"),
        SimpleNamespace(name="price_per_night", kind="number"),
    ]
    return row, page, columns


def _pricing(row, page, columns):
    return assess_pricing([row], [page], PROMPT, columns)["records"][0]["pricing"]


def test_partial_returned_scope_does_not_label_captured_prices_as_matches():
    row, page, columns = _fixture()
    pricing = _pricing(row, page, columns)
    assert pricing["status"] == "unverified"
    assert pricing["scope_status"] == "unverified"
    assert pricing["comparison_amount"] is None
    assert "requested_stay_scope_unverified" in pricing["issues"]
    assert {item["amount"] for item in pricing["observations"]} == {"282", "605", "720"}
    assert not any(item["selected"] for item in pricing["observations"])


def test_same_document_captured_heading_completes_scope_and_preserves_all_price_roles():
    row, page, columns = _fixture()
    original_row = deepcopy(row)
    original_scope = deepcopy(page["browser_task_context"]["result_scope"])
    reconciled = reconcile_captured_result_scope(
        original_scope, page["blocks"], document_id=DOCUMENT_ID,
    )
    assert original_scope["observed"]["destination"] is None
    assert reconciled["status"] == "verified"
    assert reconciled["observed"]["destination"] == "New York"
    assert reconciled["availability_verified"] is False
    for before in original_scope["fields"]:
        if before["field"] != "destination":
            after = next(item for item in reconciled["fields"]
                         if item["field"] == before["field"])
            assert after["observed"] == before["observed"]
            assert after["evidence"] == before["evidence"]
            assert after["method"] == before["method"]
    page["browser_task_context"]["result_scope"] = reconciled

    pricing = _pricing(row, page, columns)
    assert row == original_row
    assert pricing["status"] == "verified"
    assert pricing["scope_status"] == "verified"
    assert pricing["currency"] == "USD"
    assert pricing["comparison_amount"] == "282"
    assert pricing["combined_nightly"] == "282"
    assert pricing["budget_status"] == "within_target"
    assert pricing["calculation"] is None
    assert pricing["taxes"] == "unknown"
    assert pricing["fees_status"] == "unknown"
    observations = {item["amount"]: item for item in pricing["observations"]}
    assert observations["282"]["kind"] == "all_rooms_per_night"
    assert observations["282"]["selected"] is True
    assert observations["282"]["quote"] == "Per night $282"
    assert observations["605"]["kind"] == "stay_total_all_rooms"
    assert observations["605"]["selected"] is False
    assert observations["605"]["quote"] == "$605 2 nights, 4 adults"
    assert observations["720"]["role"] == "original"
    assert observations["720"]["selected"] is False
    # The source's nightly quote and stay total are separate observations. Do
    # not replace either with an invented reconciliation or tax explanation.
    assert pricing["displayed_amount"] == "282"
    assert set(observations) == {"282", "605", "720"}


def test_conflicting_captured_destination_does_not_make_prices_verified():
    row, page, columns = _fixture("Boston: 372 properties found")
    page["browser_task_context"]["result_scope"] = reconcile_captured_result_scope(
        page["browser_task_context"]["result_scope"], page["blocks"],
        document_id=DOCUMENT_ID,
    )
    assert page["browser_task_context"]["result_scope"]["status"] != "verified"
    pricing = _pricing(row, page, columns)
    assert pricing["status"] == "unverified"
    assert pricing["scope_status"] != "verified"
    assert pricing["comparison_amount"] is None
    assert not any(item["selected"] for item in pricing["observations"])
    assert any(item["amount"] == "720" and item["role"] == "original"
               for item in pricing["observations"])
