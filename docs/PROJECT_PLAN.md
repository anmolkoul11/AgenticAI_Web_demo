# Project plan

## Objective and requirements

Give developers a reusable template for quick agent demos, not a new platform.
The landscape comparison remains a separate research deliverable.

Deliver two open-source framework implementations, LangGraph and CrewAI, each
with a tested guide to create/configure an agent that:

1. Logs in to a website with a dedicated test account.
2. Extracts actual rendered listings and validates them.
3. Stores records locally in SQLite and exports JSON.
4. Applies configurable business rules.
5. Publishes events through NATS JetStream, verified by a sample consumer.

"Train" means configure instructions, tools and examples, then evaluate and
iterate. Model fine-tuning is outside the initial scope.

## Agreed stack and boundaries

| Responsibility | Technology |
| --- | --- |
| Language and environment | Python 3.11, uv |
| Agent implementations | LangGraph and CrewAI |
| Demo portal | FastAPI, Jinja2 |
| Website interaction | Playwright |
| Validation | Pydantic |
| Local records | SQLite and JSON export |
| Business rules | Python with YAML configuration |
| Events | NATS JetStream and a sample consumer |
| Supporting services | Docker Compose |
| Tests and quality | pytest, Ruff |

The LLM interprets the request, coordinates approved tools, and explains results.
Code handles credentials, validation, exact rule evaluation, storage, and events.
The model provider is undecided; no paid provider is assumed in checkpoint 1.
MCP is optional future agent-to-tool integration, not a replacement for NATS.

Start locally with a login-protected, seeded listings portal that we control.
This is real browser login and extraction, but it is NOT an Expedia/Tripadvisor
integration. A real external adapter requires an approved target and account,
permitted automation scope, and its own tests. Do not bypass access controls,
CAPTCHA, or MFA. Shared enterprise deployment is a later scope decision.

Example request: find listings for a city and date range, with price no greater
than USD 200 per night and rating at least 4 on a 5-point scale. Record price
basis, currency, rating scale, listing identifier, title, URL and extraction time.
Do not compare ambiguous currencies or rating scales without normalization.

## Checkpoints

| # | Deliverable | Completion evidence |
| --- | --- | --- |
| 1 | Foundation: package, configuration, tests, docs and exclusions | Clean environment setup, CLI smoke check, tests and lint pass; exclusions checked |
| 2 | Login-protected seeded demo portal | Valid/invalid login and denied unauthenticated listing access tested |
| 3 | Browser tools and local persistence | Real browser login and extraction; validated SQLite records and JSON export inspected |
| 4 | Rules, NATS JetStream and consumer | Matching/nonmatching rules tested; event publish acknowledgment and consumer receipt demonstrated |
| 5 | LangGraph agent | Independently completes the full workflow from a user request |
| 6 | CrewAI agent | Independently completes the same workflow with shared tools and contracts |
| 7 | Developer starter kit | Both guides reproduced from a clean checkout; customization and evaluation examples tested |

Every checkpoint: implement -> automated checks -> user review in VS Code ->
approved commit. Do not proceed beyond the agreed checkpoint without review.
Do not automatically commit, push, delete existing work, or choose a paid service.

## End-to-end acceptance

- Both agents log in and extract website data, not hardcoded tool results.
- A passing listing is saved and its event is received by the sample consumer.
- A failing listing is saved but does not emit a qualifying event.
- Zero matches is a successful run with zero qualifying events.
- Failed login and invalid data are reported without exposing secrets.
- Repeated runs have documented duplicate-handling behavior; do not claim
  exactly-once delivery. Design event IDs and consumer idempotency at checkpoint 4.
- Each guide explains setup, instructions, tools, examples, evaluation, common
  failures, and how to adapt the template to another authorized website.
- A fresh checkout can reproduce the demo using documented commands and
  explicitly configured credentials/model access.
