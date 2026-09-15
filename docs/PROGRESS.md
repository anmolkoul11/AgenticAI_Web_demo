# Progress

## Completed implementation

- Checkpoints 1 and 2: foundation and portal, reviewed by the user and merged.
- Checkpoint 3: browser extraction, validation, SQLite/JSON; 59 tests passed
  including real Chromium. User reports the workflow works.
- User owns all commits and pushes.

## Current checkpoint 4

Working on `browser_extraction_storage`. Checkpoint 3 remains uncommitted in the
working tree; those changes were preserved rather than reset or stashed.

Added typed YAML rules, persisted decisions, deterministic event IDs, local
SQLite outbox, JetStream publisher, durable pull consumer and local receipts.
Compose provides a loopback-only NATS service. No dashboard or LLM calls yet.

Verification on Python 3.11.16:

- `pytest --run-browser --run-nats`: 79 passed, no skips; two existing upstream
  test-client deprecation warnings remain (httpx and AnyIO BlockingPortal).
- Full pipeline test: actual Chromium login/extraction -> 4 NYC records -> 2
  rule matches -> 2 JetStream publish acknowledgments -> 2 persisted receipts.
- Verified repeat evaluation/publish, explicit threshold boundary, empty/no-match
  runs, refused broker connection retaining pending events, consumer duplicate
  handling, invalid payload rejection, and rule-file validation.
- Initial outage testing revealed zero retry count meant unlimited retries in
  the client. Replaced it with a bounded retry count; outage test now terminates.
- Ruff lint/format and Git whitespace checks passed; sdist and wheel built.
- Docker Compose service is healthy on loopback ports 4222 and 8222. It remains
  running for user review; `docker compose stop nats` stops it without deleting data.
- Integration tests used unique TEST streams and removed those streams afterward.
  User extraction records and exports were not changed or published by these tests.

See EVENTS_GUIDE.md for the developer walkthrough.
No commits or pushes made by the assistant.

## Next

Finish automated and live-broker verification, then user review of checkpoint 4.
Next implementation is LangGraph (checkpoint 5), including a model-provider
choice and the separately discussed minimal demo dashboard scope.
