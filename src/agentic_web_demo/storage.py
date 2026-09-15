"""Append-only run snapshots in SQLite, with repeatable JSON export."""

import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from agentic_web_demo.listings import Snapshot


def save_snapshot(snapshot: Snapshot, data_dir: Path) -> str:
    # Revalidate at the persistence boundary before creating any output.
    snapshot = Snapshot.model_validate_json(snapshot.model_dump_json())
    run_id = str(uuid4())
    data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(data_dir / "listings.sqlite3")
    try:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("Unsupported database schema version")
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, extracted_at TEXT NOT NULL,
                city TEXT NOT NULL, check_in TEXT NOT NULL, check_out TEXT NOT NULL,
                record_count INTEGER NOT NULL, snapshot_json TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS listings (
                run_id TEXT NOT NULL REFERENCES runs(run_id), listing_id TEXT NOT NULL,
                record_json TEXT NOT NULL, PRIMARY KEY (run_id, listing_id))""")
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    snapshot.extracted_at.isoformat(),
                    snapshot.stay.city,
                    snapshot.stay.check_in.isoformat(),
                    snapshot.stay.check_out.isoformat(),
                    len(snapshot.listings),
                    snapshot.model_dump_json(),
                ),
            )
            connection.executemany(
                "INSERT INTO listings VALUES (?, ?, ?)",
                [(run_id, row.listing_id, row.model_dump_json()) for row in snapshot.listings],
            )
    finally:
        connection.close()
    return run_id


def export_snapshot(run_id: str, data_dir: Path) -> Path:
    run_id = str(UUID(run_id))  # Also prevents path traversal in output filenames.
    database = data_dir / "listings.sqlite3"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT snapshot_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError("Unknown run ID")
    snapshot = Snapshot.model_validate_json(row[0])
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "record_count": len(snapshot.listings),
        **snapshot.model_dump(mode="json"),
    }
    export_dir = data_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{run_id}.json"
    temporary = export_dir / f".{run_id}.{uuid4()}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, ensure_ascii=False)
            output.write("\n")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
