"""Local opt-in dashboard receipt fixtures. No live sites or model providers."""

import pytest
from test_dashboard_live_updates import live_ui as shared_ui


@pytest.fixture
def receipt_ui(request):
    yield from shared_ui.__wrapped__(request)


def transfer(page):
    page.evaluate("""() => {
      window.fixtureReceipts = [];
      window.addEventListener('message', event => {
        if (event.data?.type === 'agentic-capture-received-v1') window.fixtureReceipts.push(event.data);
      });
      window.postMessage({type:'agentic-capture-ready-v1',
        transfer_id:'11111111-1111-4111-8111-111111111111',
        capture_id:'22222222-2222-4222-8222-222222222222'}, location.origin);
    }""")
    page.wait_for_function("window.fixtureReceipts.length === 1")
    return page.evaluate("window.fixtureReceipts[0]")


def test_receipt_is_confirmed_only_after_snapshot_claim_and_visible_source_review(receipt_ui):
    receipt_ui.evaluate("""() => {
      window.fixtureApi = async () => ({url:'https://news.example.org/sports',
        version:1,truncated:false,blocks:[{id:'b1',kind:'text',text:'Source snapshot'}]});
      setStudioStep('results');
    }""")
    receipt = transfer(receipt_ui)
    assert receipt["ok"] is True
    assert receipt["capture_id"] == "22222222-2222-4222-8222-222222222222"
    assert receipt["transfer_id"] == "11111111-1111-4111-8111-111111111111"
    assert receipt_ui.evaluate("studioStep") == "source"
    assert receipt_ui.evaluate("webCapture.url") == "https://news.example.org/sports"
    assert receipt_ui.locator("#web-capture-preview").is_visible()
    assert receipt_ui.evaluate("window.fixtureCalls") == [
        "/api/custom/captures/22222222-2222-4222-8222-222222222222/claim"
    ]


@pytest.mark.parametrize("condition,reason", [
    ("connectionBlocked = true", "dashboard_not_ready"),
    ("signedIn = false", "dashboard_not_ready"),
    ("webSubmitting = true", "dashboard_busy"),
])
def test_blocked_dashboard_returns_negative_receipt_without_claiming(receipt_ui, condition, reason):
    receipt_ui.evaluate(condition)
    receipt = transfer(receipt_ui)
    assert receipt["ok"] is False and receipt["reason"] == reason
    assert receipt_ui.evaluate("window.fixtureCalls") == []


def test_failed_claim_is_not_reported_as_success(receipt_ui):
    receipt_ui.evaluate("window.fixtureApi = async () => { throw new Error('Fixture claim failed'); }")
    receipt = transfer(receipt_ui)
    assert receipt["ok"] is False and receipt["reason"] == "capture_claim_failed"
    assert receipt_ui.evaluate("webCapture") is None
