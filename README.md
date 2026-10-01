# AgenticAI_Web_demo

## Custom Website workspace

New bounded path for public HTML pages or authorized pasted page text: optional
instructions, dynamic fields and range filters (no hotel policy ceiling), readable
evidence-backed previews, approval, private storage, Excel/CSV/JSON/JSONL downloads,
and optional rule-based NATS summary events. Both LangGraph and CrewAI Flow are
available. See [CUSTOM_WEBSITE_GUIDE.md](docs/CUSTOM_WEBSITE_GUIDE.md) for setup,
user-run validation and limitations, and [EXTERNAL_SITE_ACCEPTANCE.md](docs/EXTERNAL_SITE_ACCEPTANCE.md)
for the BBC News and Booking.com acceptance scenarios. Chromium rendering, optional single-form HTTPS
sign-in and human-approved same-site article discovery are implemented, with isolated sessions. Cross-origin SSO,
complex login adapters, pagination and custom-event consumer receipts remain unimplemented. Runtime validation
is pending; the assistant did not run tests or paid model calls.

## Local dashboard (new MVP)

Now includes [individual local accounts](docs/LOCAL_ACCOUNTS.md), private workspaces,
session-only or opt-in OS-stored API keys, administrator roles, and 100 fictional hotels across 10 cities. See [account security and admin setup](docs/ACCOUNTS_SECURITY.md). Restart the
dashboard and create an account with your own username/password. No registration
code is required. The launcher password is only for synthetic hotel automation.

See [DASHBOARD_GUIDE.md](docs/DASHBOARD_GUIDE.md) for setup, sales/demo instructions
and [VERIFICATION_CHECKLIST.md](docs/VERIFICATION_CHECKLIST.md) for current acceptance
steps. Start with `scripts/Setup-Demo.ps1`, then
`scripts/Start-Demo.ps1`. The dashboard adds guided/model-assisted planning,
explicit review and approval, background stage progress, results and exports,
and recent job history for both frameworks. These hotel-demo instructions describe
the local hotel adapter; use Custom Website for the new general path above.
This MVP awaits user tests and visual verification; earlier test
results below do not validate the new UI.

**OpenAI-only migration ready for user testing:** see [OPENAI_SETUP.md](docs/OPENAI_SETUP.md).
Prompt v4 adds optional minimum price and removes fixed hotel price/rating thresholds;
both frameworks now share
the OpenAI transport. Live semantic acceptance is still pending. Historical
staging/provider results below are not verification of this migration.

**Historical CrewAI checkpoint results (not current acceptance):** see
[CREWAI_GUIDE.md](docs/CREWAI_GUIDE.md) for structured/model-assisted planning and
approved execution using an independent CrewAI Flow. User-run staging tests:
222 passed / 39 skipped; CrewAI live interpretation: 21 passed / 17 failed.
Actual-repository checks and manual CrewAI acceptance remain pending. The
LangGraph implementation and its known language limitations are preserved.

A reusable developer starter kit for two website-agent demos: **LangGraph** and
**CrewAI**, sharing browser automation, data validation, local storage, business
rules, and event publishing.

**Current scope: bounded LangGraph and CrewAI demos; broad language reliability remains pending.**
LangGraph coordinates the real browser, validation, SQLite/JSON, rules and NATS
tools. Planning supports offline scripted scenarios and an opt-in OpenAI adapter
with structured output, deterministic criteria checks, and plan-only preview. Both frameworks
also support structured proposals without a model. Historical local-model
results are retained in PROGRESS.md, not current acceptance evidence.
Use [reviewed plan execution](docs/PLAN_EXECUTION_GUIDE.md) for the new bounded path.
This is a demo starter kit,
not a production-certified platform.

## Development setup (PowerShell)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed:

```powershell
winget install --id astral-sh.uv --exact --source winget
```

Reopen your terminal after installing, then from the repository directory:

```powershell
uv python install 3.11
uv sync --locked
uv run --locked agentic-demo status
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

`uv sync` creates the local `.venv`; select `.venv\Scripts\python.exe` as the
interpreter in VS Code. The project targets Python 3.11; Python 3.12 is also
permitted by the foundation metadata, but does not replace 3.11 validation.
Track `uv.lock`; update it deliberately when adding dependencies.
See [uv's project guide](https://docs.astral.sh/uv/guides/projects/).

The status command only checks package startup and configuration. It does not
check Docker, NATS, browser access, or model connectivity.

## Run the demo website

Follow [the portal startup and review guide](docs/PORTAL_GUIDE.md) to configure
your demo account and start the login-protected website at `http://127.0.0.1:8000`.
It includes Windows setup troubleshooting from checkpoint 1.

Follow [the extraction guide](docs/EXTRACTION_GUIDE.md) to install Chromium and run
the browser-to-SQLite/JSON workflow. Browser tests are opt-in: `uv run --locked pytest --run-browser`.

Follow [the rules and events guide](docs/EVENTS_GUIDE.md) to start NATS, process an
existing extraction run, and verify consumer receipt. `config/rules.yaml` is
non-secret business configuration. Pending events and receipts stay under ignored `data/`.

Follow [the LangGraph guide](docs/LANGGRAPH_GUIDE.md) for the single-command
offline demo, approved live-model setup, graph structure, policy and acceptance tests.

The status command reports `5b-langgraph-live-verification-pending`,
`workflow_implemented: true` and `live_model_verified: false`. These describe the
implementation milestone, not service health or automatic discovery of test results.
Ordinary tests never call a live model. Live tests require `--run-model` and
explicit provider configuration. OpenAI tests additionally require the paid-use
permission variable. See the guides before enabling them.

## Configuration

The application reads process environment variables. `.env.example` documents the
non-secret defaults; merely copying it to `.env` does **not** load it yet.

```powershell
$env:AGENTIC_DEMO_DATA_DIR = "./data"
$env:AGENTIC_DEMO_LOG_LEVEL = "INFO"
uv run --locked agentic-demo status
```

Relative paths resolve from your current working directory. No directories or
records are created by the status command. Credentials, API keys, authenticated
browser state, scraped data, and traces must not be committed. Git exclusions
are a safeguard, not a substitute for reviewing staged changes.

## Planned workflow

Interpret a request -> log in to the demo portal -> extract listings -> validate
and save locally -> apply business rules -> publish matching events -> confirm
receipt with a sample consumer.

Both agent frameworks will independently execute this workflow using shared
tools. We first test those tools without an agent, then add agent orchestration.

## Repository layout

- `src/agentic_web_demo/`: package, configuration, and foundation CLI.
- `tests/`: automated tests.
- `docs/PROJECT_PLAN.md`: scope, stack, checkpoints, and acceptance criteria.
- `docs/PROGRESS.md`: verification evidence, pending decisions, and next step.

Docker Desktop will be required for the NATS checkpoint; it is not required for
the foundation tests. Agent framework dependencies and the model provider will
be added at their checkpoints, not preinstalled as unused placeholders.

## Review workflow

Work in small checkpoints. Inspect changes in VS Code, run tests, then approve a
Git commit. No automatic commits, remote pushes, or external-site automation.
The landscape document is the separate research deliverable; this repository
will contain the implementations and the two step-by-step developer guides.
# Reviewed LangGraph demo

For external pages in your normal Chrome/Edge session, see
[Browser capture setup and partial-result review](docs/BROWSER_CAPTURE_GUIDE.md).
This user-assisted path complements automated Chromium; runtime verification is pending.

Start with [the plan/review/execute guide](docs/PLAN_EXECUTION_GUIDE.md) for the
recommended two-path interface: explicit inputs or model-assisted proposals,
then execution of the exact reviewed revision without replanning. The local hotel
adapter is the reference implementation, not a universal website scraper.
Natural-language interpretation remains experimental (baseline 20/38 passing).
