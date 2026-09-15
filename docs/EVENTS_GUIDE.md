# Checkpoint 4: rules and event delivery

## What changes

Use an existing extraction run from checkpoint 3. Evaluate every stored listing
against a deterministic rule, persist the decisions, queue an event for each
match, publish through NATS JetStream, then confirm the sample consumer saved it.
No browser or model is needed to process an existing run.

The website and extraction guides remain valid. Agent orchestration and the
proposed dashboard are later checkpoints, not part of this terminal-based tool layer.

## 1. Install and start NATS

Start Docker Desktop and wait for its Linux engine to be running. From the repo:

```powershell
uv sync --locked
docker compose up -d --wait nats
docker compose ps
```

The service should be healthy. Compose downloads the pinned `nats:2.11.8-alpine`
image on first use and enables JetStream. This is a reproducible demo version,
not a claim that it is the newest release or approved for production deployment.
Client port 4222 and monitoring port 8222 are bound only to 127.0.0.1.
Messages live in the Docker named volume, not Git. No external broker account.
No authentication/TLS is configured: local demo only, never expose these ports.

Default client URL: `nats://127.0.0.1:4222`. A process-level `NATS_URL` override
can point to another loopback port. `.env` files are not automatically loaded by
the Python commands. No secrets belong in `config/rules.yaml` or `compose.yaml`.

## 2. Pick a run and inspect the rule

Use the `run_id` printed by extraction or visible in an exported JSON file:

```powershell
$runId = "PASTE-YOUR-EXTRACTION-RUN-ID-HERE"
```

The run must exist in your `data/listings.sqlite3` (or configured data directory).
The default YAML rule in `config/rules.yaml` requires all of:

- Price **at most USD 200 per night**, including taxes and fees.
- Rating **at least 4 out of 5**.

Boundaries are inclusive: a listing at exactly 200 and 4 qualifies.

Expected results from the current fixtures:

| Search | Evaluated | Qualifying events |
| --- | --- | --- |
| New York | 4 | 2: NYC-001 and NYC-004 |
| Boston | 2 | 1: BOS-001 |
| All cities | 6 | 3 |
| Unknown city | 0 | 0 |

Nonmatching listings remain in the extraction snapshot; they are not deleted.

## 3. Evaluate and publish

```powershell
uv run --locked agentic-demo process --run-id $runId --rules config/rules.yaml
```

Output contains decisions for every listing (including rejection reasons) and
the number of events acknowledged by JetStream. A broker acknowledgment means
NATS accepted the event, **not** that the consumer processed it.

For a zero-match run, processing succeeds with zero events and does not need to
contact NATS. To evaluate offline and queue events without publishing:

```powershell
uv run --locked agentic-demo evaluate --run-id $runId --rules config/rules.yaml
uv run --locked agentic-demo publish --run-id $runId
```

Omitting `--rules` uses built-in defaults equivalent to the provided YAML. An
explicit YAML file lets you change thresholds without editing Python. Unknown
keys, unsupported currencies/scales, and invalid values are rejected.

## 4. Receive the events

```powershell
uv run --locked agentic-demo consume
```

This can run **after** publishing: JetStream stores the events. The consumer
stops after 3 seconds with no next message, or after 100 deliveries. Adjust with
`--idle-timeout` (up to 60 seconds) and `--limit` if needed.

Output shows newly received events, detected duplicates, rejected invalid
events, and their IDs. A named durable consumer resumes its broker position on
the next invocation. By default it receives all pending demo events, not just
the selected run. Correlate them by inspecting that run next.

## 5. Confirm end-to-end delivery

```powershell
uv run --locked agentic-demo events-status --run-id $runId
```

For a fresh New York run after successful consumption, expect:

- One evaluation with `matched: 2`.
- `pending: 0` and `published: 2`.
- Two receipts with consumer name, event ID and received timestamp.

Receipt persistence is the sample consumer's business side effect. There is no
email, booking, purchase, or other external action. It commits the receipt
before acknowledging the broker. Invalid payloads do not become receipts;
their delivery is terminated and counted as invalid (no separate dead-letter queue yet).

## Persistence and retries

`data/events.sqlite3` holds three tables, separate from extraction storage:

- `evaluations`: rule configuration, decisions, and counts per run/rule fingerprint.
- `outbox`: one event per qualifying listing, with publish acknowledgment state.
- `receipts`: one receipt per consumer identity/event ID.

Decisions and pending events commit together locally before a publish attempt.
If NATS is down, fix it and rerun `publish --run-id $runId`; no new scraping is
required. If a process stops after broker acceptance but before recording that
acceptance locally, retry may resend. Stable event IDs and a 2-minute broker
deduplication window reduce duplicates; consumer receipt deduplication handles
duplicates beyond that window while its local database is retained.

This is **at-least-once delivery with an idempotent sample side effect**, not
an exactly-once guarantee. Do not delete either database to resolve retries.
Publishing twice after acknowledgment does not intentionally resend an event.
Changing the rule configuration creates a new rule fingerprint and a new
evaluation/event identity; a fresh extraction run also creates new identities.
`publish --run-id` sends all still-pending events for that run across its evaluations.

The stream is `AGENTIC_DEMO`, subject `agentic_demo.listings.qualified.v1`.
It retains messages up to 24 hours, 10,000 messages, or 50 MB, whichever limit
is reached first. Consume before retention limits remove messages. A published
status alone cannot prove a late consumer received an expired message.

One local publisher/consumer workflow is the demo target. Multiple consumers
with the same durable name share delivery; different `--consumer` names get
independent broker positions and receipt identities. Keep the same broker and
data directory across retries; this is not a broker-migration mechanism.

## Tests and review

```powershell
uv run --locked pytest
uv run --locked pytest --run-browser --run-nats
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Real NATS tests use a unique TEST stream and delete only that stream afterward.
They do not purge your demo stream. The default suite skips browser/live-broker
tests; the full suite requires installed Chromium and running NATS.

Review: New York gives 2 events and receipts; a repeated process call queues no
duplicates for the same rules; unknown-city runs give 0; a stopped broker leaves
events pending. Use a **fresh run** for the outage test because already-published
events will not be sent again.

Stop the service when finished:

```powershell
docker compose stop nats
```

Start again with `docker compose up -d --wait nats`. Do not use `down -v` unless
you intend to destroy the saved broker messages and consumer positions.

References: [NATS JetStream](https://docs.nats.io/learn/jetstream/) and
[NATS Python client](https://nats-io.github.io/nats.py/modules.html).
