import asyncio
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import yaml
from pydantic import ValidationError

from agentic_web_demo.events import (
    delivery_status,
    evaluate_run,
    pending_events,
    record_receipt,
)
from agentic_web_demo.listings import Listing, Snapshot, Stay
from agentic_web_demo.messaging import Broker, publish_pending
from agentic_web_demo.rules import Rules, load_rules
from agentic_web_demo.storage import save_snapshot


def seeded_run(data_dir, city="New York"):
    from agentic_web_demo.portal.seed import LISTINGS

    tomorrow = date.today() + timedelta(days=1)
    stay = Stay(city=city, check_in=tomorrow, check_out=tomorrow + timedelta(days=1))
    now = datetime.now(UTC)
    records = tuple(
        Listing(
            listing_id=item.id,
            title=item.title,
            city=item.city,
            price=item.price,
            rating=item.rating,
            rating_scale=5,
            currency="USD",
            price_basis="per_night_taxes_included",
            check_in=stay.check_in,
            check_out=stay.check_out,
            extracted_at=now,
            source_url=f"http://127.0.0.1:8000/listings#{item.id}",
        )
        for item in LISTINGS
        if item.city == city
    )
    return save_snapshot(Snapshot(stay=stay, extracted_at=now, listings=records), data_dir)


def test_defaults_and_boundary_match(tmp_path):
    run = seeded_run(tmp_path)
    report = evaluate_run(run, Rules(), tmp_path)
    assert report["evaluated"] == 4
    assert report["matched"] == 2
    assert {item["listing_id"] for item in report["decisions"] if item["matched"]} == {
        "NYC-001",
        "NYC-004",
    }
    assert len(pending_events(run, tmp_path)) == 2
    assert report["decisions"][1]["reasons"] == ["price_above_maximum"]
    assert report["decisions"][2]["reasons"] == ["rating_below_minimum"]


def test_repeated_evaluation_is_idempotent(tmp_path):
    run = seeded_run(tmp_path)
    evaluate_run(run, Rules(), tmp_path)
    original = [item.model_dump_json() for item in pending_events(run, tmp_path)]
    evaluate_run(run, Rules(max_price=Decimal("200.00")), tmp_path)
    assert original == [item.model_dump_json() for item in pending_events(run, tmp_path)]
    assert len(delivery_status(run, tmp_path)["evaluations"]) == 1


def test_changed_rules_produce_new_evaluation(tmp_path):
    run = seeded_run(tmp_path)
    evaluate_run(run, Rules(), tmp_path)
    assert evaluate_run(run, Rules(max_price=Decimal("190")), tmp_path)["matched"] == 1
    assert len(delivery_status(run, tmp_path)["evaluations"]) == 2
    assert len(pending_events(run, tmp_path)) == 3


@pytest.mark.parametrize("city,max_price", [("Unknown", "200"), ("Boston", "0")])
def test_zero_matches_succeeds_without_broker(tmp_path, city, max_price):
    run = seeded_run(tmp_path, city)
    assert evaluate_run(run, Rules(max_price=Decimal(max_price)), tmp_path)["matched"] == 0
    assert asyncio.run(publish_pending(run, tmp_path))["broker_contacted"] is False


def test_receipts_are_idempotent(tmp_path):
    run = seeded_run(tmp_path)
    evaluate_run(run, Rules(), tmp_path)
    item = pending_events(run, tmp_path)[0]
    assert record_receipt(item, "test-consumer", tmp_path) is True
    assert record_receipt(item, "test-consumer", tmp_path) is False
    assert len(delivery_status(run, tmp_path)["receipts"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"max_price": "-1"},
        {"min_rating": "6"},
        {"max_price": "NaN"},
        {"currency": "EUR"},
        {"unexpected": 1},
        {"version": True},
    ],
)
def test_bad_rules_rejected(change):
    with pytest.raises(ValidationError):
        Rules.model_validate(change)


def test_yaml_roundtrip_and_safe_loader(tmp_path):
    config = tmp_path / "rules.yaml"
    config.write_text('max_price: "180"\nmin_rating: "4.5"\n', encoding="utf-8")
    assert load_rules(config).max_price == Decimal("180")
    config.write_text('!!python/object/apply:os.system ["never-execute"]', encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_rules(config)


def test_unknown_run_does_not_create_event_database(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        evaluate_run("00000000-0000-0000-0000-000000000000", Rules(), tmp_path)
    assert not (tmp_path / "events.sqlite3").exists()


@pytest.mark.parametrize(
    "url",
    ["nats://external.example:4222", "nats://user:secret@localhost:4222", "http://127.0.0.1:4222"],
)
def test_broker_boundary(url):
    with pytest.raises(ValueError):
        Broker(url=url)
