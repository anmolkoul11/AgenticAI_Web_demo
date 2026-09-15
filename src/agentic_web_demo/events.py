"""Durable local decisions, publish outbox, and consumer receipts."""

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from agentic_web_demo.listings import Listing, Snapshot
from agentic_web_demo.rules import Rules


def event_id(run_id: str, rules: Rules, listing_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, json.dumps([str(UUID(run_id)), rules.fingerprint(), listing_id]))


class QualifiedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    event_type: Literal["listing.qualified"] = "listing.qualified"
    event_id: UUID
    run_id: UUID
    occurred_at: AwareDatetime
    rules: Rules
    listing: Listing

    @model_validator(mode="after")
    def check_identity_and_rule(self) -> Self:
        if self.event_id != event_id(str(self.run_id), self.rules, self.listing.listing_id):
            raise ValueError("Event identity does not match its contents")
        if self.rules.reasons(self.listing):
            raise ValueError("Event listing does not qualify")
        return self


@contextmanager
def event_db(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data_dir / "events.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS evaluations (
          run_id TEXT NOT NULL, fingerprint TEXT NOT NULL, report TEXT NOT NULL,
          PRIMARY KEY(run_id, fingerprint));
        CREATE TABLE IF NOT EXISTS outbox (
          event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL,
          published_at TEXT, stream_sequence INTEGER);
        CREATE TABLE IF NOT EXISTS receipts (
          consumer TEXT NOT NULL, event_id TEXT NOT NULL, run_id TEXT NOT NULL,
          received_at TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(consumer, event_id));
        """)
        yield db
    finally:
        db.close()


def evaluate_run(run_id: str, rules: Rules, data_dir: Path) -> dict:
    run_id = str(UUID(run_id))
    database = (data_dir / "listings.sqlite3").resolve()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT snapshot_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown extraction run")
    snapshot = Snapshot.model_validate_json(row[0])
    fingerprint = rules.fingerprint()
    decisions = [
        {
            "listing_id": item.listing_id,
            "matched": not rules.reasons(item),
            "reasons": rules.reasons(item),
        }
        for item in snapshot.listings
    ]
    report = {
        "run_id": run_id,
        "rule_fingerprint": fingerprint,
        "rules": rules.model_dump(mode="json"),
        "evaluated": len(decisions),
        "matched": sum(item["matched"] for item in decisions),
        "decisions": decisions,
    }
    now = datetime.now(UTC)
    events = [
        QualifiedEvent(
            event_id=event_id(run_id, rules, item.listing_id),
            run_id=UUID(run_id),
            occurred_at=now,
            rules=rules,
            listing=item,
        )
        for item in snapshot.listings
        if not rules.reasons(item)
    ]
    with event_db(data_dir) as db, db:
        db.execute(
            "INSERT OR IGNORE INTO evaluations VALUES (?, ?, ?)",
            (run_id, fingerprint, json.dumps(report)),
        )
        db.executemany(
            "INSERT OR IGNORE INTO outbox(event_id,run_id,payload) VALUES (?, ?, ?)",
            [(str(item.event_id), run_id, item.model_dump_json()) for item in events],
        )
    return report


def pending_events(run_id: str, data_dir: Path) -> list[QualifiedEvent]:
    with event_db(data_dir) as db:
        if (
            db.execute("SELECT 1 FROM evaluations WHERE run_id=?", (str(UUID(run_id)),)).fetchone()
            is None
        ):
            raise ValueError("Evaluate this run before publishing")
        rows = db.execute(
            "SELECT payload FROM outbox WHERE run_id=? AND published_at IS NULL ORDER BY event_id",
            (str(UUID(run_id)),),
        ).fetchall()
    return [QualifiedEvent.model_validate_json(row["payload"]) for row in rows]


def mark_published(item: QualifiedEvent, sequence: int, data_dir: Path):
    with event_db(data_dir) as db, db:
        db.execute(
            "UPDATE outbox SET published_at=?,stream_sequence=? WHERE event_id=?",
            (datetime.now(UTC).isoformat(), sequence, str(item.event_id)),
        )


def record_receipt(item: QualifiedEvent, consumer: str, data_dir: Path) -> bool:
    # Persist before broker ACK. Redelivery after a crash cannot repeat this local side effect.
    with event_db(data_dir) as db, db:
        cursor = db.execute(
            "INSERT OR IGNORE INTO receipts VALUES (?, ?, ?, ?, ?)",
            (
                consumer,
                str(item.event_id),
                str(item.run_id),
                datetime.now(UTC).isoformat(),
                item.model_dump_json(),
            ),
        )
        return cursor.rowcount == 1


def delivery_status(run_id: str, data_dir: Path) -> dict:
    run_id = str(UUID(run_id))
    with event_db(data_dir) as db:
        evaluations = [
            json.loads(row[0])
            for row in db.execute("SELECT report FROM evaluations WHERE run_id=?", (run_id,))
        ]
        outbox = [
            dict(row)
            for row in db.execute(
                "SELECT event_id,published_at,stream_sequence FROM outbox WHERE run_id=?", (run_id,)
            )
        ]
        receipts = [
            dict(row)
            for row in db.execute(
                "SELECT consumer,event_id,received_at FROM receipts WHERE run_id=?", (run_id,)
            )
        ]
    return {
        "run_id": run_id,
        "evaluations": evaluations,
        "events": outbox,
        "receipts": receipts,
        "pending": sum(row["published_at"] is None for row in outbox),
        "published": sum(row["published_at"] is not None for row in outbox),
    }
