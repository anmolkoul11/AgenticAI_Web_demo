import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from agentic_web_demo.browser import Credentials, ExtractionError, portal_origin
from agentic_web_demo.cli import main
from agentic_web_demo.listings import Listing, Snapshot, Stay
from agentic_web_demo.storage import export_snapshot, save_snapshot


@pytest.fixture
def snapshot():
    start = date.today() + timedelta(days=2)
    stay = Stay(city="New York", check_in=start, check_out=start + timedelta(days=1))
    now = datetime.now(UTC)
    listing = Listing(
        listing_id="NYC-001",
        title="Harbor House",
        city=stay.city,
        check_in=stay.check_in,
        check_out=stay.check_out,
        price="180.00",
        currency="USD",
        price_basis="per_night_taxes_included",
        rating="4.6",
        rating_scale=5,
        source_url="http://127.0.0.1:8000/listings#NYC-001",
        extracted_at=now,
    )
    return Snapshot(stay=stay, extracted_at=now, listings=(listing,))


@pytest.mark.parametrize(
    "field,value",
    [
        ("price", "-1"),
        ("price", "NaN"),
        ("price", "1.123"),
        ("currency", "EUR"),
        ("rating", "5.1"),
        ("rating_scale", 10),
        ("title", "  "),
        ("extracted_at", "2026-01-01T12:00:00"),
        ("price_basis", "unknown"),
    ],
)
def test_invalid_records_rejected(snapshot, field, value):
    payload = snapshot.listings[0].model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        Listing.model_validate(payload)


def test_duplicates_rejected(snapshot):
    with pytest.raises(ValidationError):
        Snapshot(
            stay=snapshot.stay, extracted_at=snapshot.extracted_at, listings=snapshot.listings * 2
        )


def test_mismatched_city_rejected(snapshot):
    with pytest.raises(ValidationError):
        Snapshot(
            stay=snapshot.stay.model_copy(update={"city": "Boston"}),
            extracted_at=snapshot.extracted_at,
            listings=snapshot.listings,
        )


def test_save_export_repeat_and_history(snapshot, tmp_path):
    first = save_snapshot(snapshot, tmp_path)
    second = save_snapshot(snapshot, tmp_path)
    assert first != second
    with sqlite3.connect(tmp_path / "listings.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 2
    target = export_snapshot(first, tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    assert payload["listings"][0]["price"] == "180.00"
    assert payload["run_id"] == first
    original = target.read_bytes()
    assert export_snapshot(first, tmp_path).read_bytes() == original


def test_empty_run_is_saved(snapshot, tmp_path):
    empty = Snapshot(stay=snapshot.stay, extracted_at=snapshot.extracted_at, listings=())
    run_id = save_snapshot(empty, tmp_path)
    assert json.loads(export_snapshot(run_id, tmp_path).read_text())["listings"] == []


def test_missing_export_does_not_create_database(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        export_snapshot("00000000-0000-0000-0000-000000000000", tmp_path)
    assert not (tmp_path / "listings.sqlite3").exists()


def test_invalid_export_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        export_snapshot("../../secrets", tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://expedia.com",
        "http://evil.example",
        "http://127.0.0.1:8000@evil.example",
        "http://demo:password@localhost:8000",
        "http://localhost:8000/login",
        "http://localhost:8000?secret=x",
    ],
)
def test_external_or_credential_urls_rejected(url):
    with pytest.raises(ExtractionError):
        portal_origin(url)


def test_credentials_repr_is_redacted():
    assert "sensitive" not in repr(Credentials("sensitive-user", "sensitive-password"))


def test_missing_credentials_fail_without_storage(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "new"))
    assert main(["extract"]) == 1
    assert "DEMO_PASSWORD" in capsys.readouterr().err
    assert not (tmp_path / "new").exists()


def test_invalid_dates_fail_without_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path / "new"))
    assert main(["extract", "--check-in", "wrong"]) == 1
    assert not (tmp_path / "new").exists()


def test_persistence_revalidates_before_writing(snapshot, tmp_path):
    invalid = snapshot.model_copy(update={"listings": snapshot.listings * 2})
    output = tmp_path / "never-created"
    with pytest.raises(ValidationError):
        save_snapshot(invalid, output)
    assert not output.exists()


def test_export_failure_preserves_run_and_can_recover(snapshot, monkeypatch, tmp_path, capsys):
    import agentic_web_demo.cli as cli

    monkeypatch.setenv("DEMO_PASSWORD", "test-only-password")
    monkeypatch.setenv("AGENTIC_DEMO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "extract_listings", lambda *args, **kwargs: snapshot)

    def failed_export(*args):
        raise OSError("Synthetic write failure")

    monkeypatch.setattr(cli, "export_snapshot", failed_export)
    assert main(["extract"]) == 1
    assert "saved in SQLite" in capsys.readouterr().err
    with sqlite3.connect(tmp_path / "listings.sqlite3") as db:
        run_id = db.execute("SELECT run_id FROM runs").fetchone()[0]
        assert db.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
    assert export_snapshot(run_id, tmp_path).exists()
