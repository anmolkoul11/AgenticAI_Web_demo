# Project plan

## New checkpoint: bounded Custom Website extraction

Implemented, awaiting user verification: dynamic public-page/pasted-text extraction,
optional instructions/filters, preview approval, per-account storage, exports and
optional business-rule summary events through both orchestration frameworks.
See [CUSTOM_WEBSITE_GUIDE.md](CUSTOM_WEBSITE_GUIDE.md).

Remaining: runtime acceptance, semantic evaluations, external authenticated browser
adapters, JS/pagination support, custom-event consumer receipt verification, and
enterprise deployment/identity/secrets hardening. Do not claim universal website support.
The older checkpoint notes below describe the separate synthetic Hotel demo.

## Current checkpoint: local dashboard and account-system acceptance

LangGraph and CrewAI are implemented as independent runners with shared browser,
storage, rule and event services. Both support structured or OpenAI-assisted
proposals followed by explicit review and approval. The dashboard, 100-hotel
catalogue, local accounts, administrator controls and optional OS-stored keys are
implemented. The latest UI/security changes await user-run acceptance; no tests
or paid model calls were run by the assistant for them.

Follow [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) for offline tests,
both frameworks' end-to-end demos and paid opt-in semantic checks. Previous
supplied language baselines: LangGraph 43/44, CrewAI 40/44. Do not treat these as
verification of new changes or unrestricted language reliability.

Remaining priorities: verify this checkpoint, fix semantic failures, integrate
an approved external website, reproduce a clean-checkout starter kit, and align
the landscape/handoff documentation. Hosting is deferred. Cross-platform OS
credential storage is implemented but must be verified on each supported OS.

The reference adapter is still local demo hotels, not an arbitrary-site scraper.
Admin roles and a desktop keyring do not constitute enterprise production readiness.
See ACCOUNTS_SECURITY.md for limitations and migration requirements.

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

The LLM interprets the request into a structured plan. LangGraph coordinates
approved tools; code reports evidence-backed results and handles credentials,
validation, exact rule evaluation, storage, and events. Autonomous tool selection
is not required for this bounded demo. OpenAI is the implemented live provider
for both frameworks. Structured proposals need no paid model. The Ollama adapter
has been retired; earlier checkpoint entries describe historical implementation.
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

### Historical checkpoint 5 interim split (superseded by current status above)

Model access is pending organizational approval. Checkpoint 5a builds and tests
the real LangGraph tool workflow with explicitly simulated planning. This does
not satisfy the real-model agent requirement. Checkpoint 5b must integrate an
approved model and evaluate request interpretation, tool coordination and errors
before checkpoint 5 is complete. The 5b adapter, request CLI, policy gate and offline
tests are now implemented; real model quality/end-to-end verification is pending.
Personal API use was not approved at implementation time: offline tests only.
Local Ollama is now an alternative for real-model acceptance; successful local
semantic and end-to-end evaluations can close the model-verification requirement.
Installing an adapter alone does not demonstrate model quality.
The proposed minimal dashboard is a separate scope confirmation, not required to
close checkpoint 5. CrewAI follows after LangGraph acceptance and user review.

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
