# Project plan

## Current checkpoint: CrewAI developer review

CrewAI plan/review/execute is implemented with its own Flow and local planning
Agent/Task/Crew. See CREWAI_GUIDE.md. It shares adapters/contracts/services, not
LangGraph orchestration. Both LangGraph reviewed paths were manually verified;
CrewAI actual-repository checks and manual approval-path acceptance are pending.
Language baselines remain explicit: LangGraph 20/38 and CrewAI 21/38; neither
is accepted for unrestricted natural-language execution. Checkpoint 7 follows
review/merge and covers clean-checkout reproducibility and developer handoff.

## Current bounded handoff scope

The reference use case is local hotel extraction, not an arbitrary-site scraper.
LangGraph now supports explicit structured inputs or experimental model-assisted
proposals, followed by review and exact saved-plan execution. See
PLAN_EXECUTION_GUIDE.md. CrewAI should reuse schemas, tools and proposal contracts
through its own runner, not wrap the LangGraph graph. Website/domain onboarding
requires explicit adapters, definitions and tests. A dashboard and generic adapter
registry are deferred. Historical checkpoint notes below remain as context.

Acceptance is split: reproducible bounded workflow versus general language
interpretation. The user demonstrated local Ollama plus the complete real-tool
workflow; the language baseline is 20/38 passing and remains an open limitation.
Human review is a mitigation, not proof that interpretation is correct. Do not
claim all original semantic evaluations pass or enterprise production readiness.

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
is not required for this bounded demo. OpenAI and local Ollama adapters are
implemented. Ollama enables synthetic local evaluation without a paid API;
enterprise provider selection and hosted usage remain separate approval decisions.
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

### Checkpoint 5 interim split

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
