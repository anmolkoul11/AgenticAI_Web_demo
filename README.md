# AgenticAI_Web_demo

A reusable developer starter kit for two website-agent demos: **LangGraph** and
**CrewAI**, sharing browser automation, data validation, local storage, business
rules, and event publishing.

**Current scope: checkpoint 4, rules and event delivery.** The website, browser
extraction, validation, SQLite/JSON, deterministic rules and NATS JetStream
publisher/consumer are implemented. AI agent orchestration is not implemented yet.
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

The status command now reports `4-rules-events`. `workflow_implemented` remains
false until the complete agent workflow has been built and verified.

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
