# AgenticAI_Web_demo

## Custom Website workspace

Collect content through an interactive browser, the Chrome/Edge capture extension,
static public HTML or authorized pasted text. Optional instructions determine fields
and filters; reviewed snapshots support private storage, Excel/CSV/JSON/JSONL exports
and optional rule-based NATS summary events. Both LangGraph and CrewAI Flow are
available for extraction/save orchestration. Autonomous observe/decide/act browser
execution is currently **LangGraph only**; it supports DOM observations and separately
consented viewport screenshots. See [the dynamic agent guide](docs/DYNAMIC_BROWSER_AGENT_GUIDE.md).

Browser sessions support normal networking by default, an optional restricted mode,
optional sign-in and human-completed email verification/MFA. Generic login is not a
universal SSO connector. Search, reviewed link discovery and detail capture are bounded;
site compatibility, extraction completeness and end-to-end acceptance require user
verification. Custom events currently prove broker acknowledgement, not consumer receipt.
See [CUSTOM_WEBSITE_GUIDE.md](docs/CUSTOM_WEBSITE_GUIDE.md) and
[EXTERNAL_SITE_ACCEPTANCE.md](docs/EXTERNAL_SITE_ACCEPTANCE.md).

## Local dashboard

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
The latest changes await user-run verification; historical results in the progress
log do not validate a newer UI or browser-agent revision.

OpenAI is the implemented live provider; users supply their own account credentials.
See [OPENAI_SETUP.md](docs/OPENAI_SETUP.md). The configured hotel policy has no fixed
price ceiling or rating floor; the user's approved criteria become the effective
run rules. Legacy `Rules()` defaults still exist for callers omitting configuration.
Ollama is retired. See [PROGRESS.md](docs/PROGRESS.md) for dated historical evaluations
and [CREWAI_GUIDE.md](docs/CREWAI_GUIDE.md) for the independent CrewAI workflow.

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

The status command lists implemented frameworks/source methods and reports
`health_checks_performed: false`. It does not publish a historical checkpoint or
test score as current status. Dated acceptance evidence belongs in `docs/PROGRESS.md`.
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

Docker Desktop is used by the full demo launcher to start NATS; ordinary unit tests
do not require it. LangGraph, CrewAI and the OpenAI SDK are already runtime dependencies.
See [CLEANUP_GUIDE.md](docs/CLEANUP_GUIDE.md) for the current housekeeping checkpoint
and canonical capture-script maintenance.

## Review workflow

Work in small checkpoints. Inspect changes in VS Code, run tests, then approve a
Git commit. No automatic commits or remote pushes. Live website/model checks are
user-initiated and separate from ordinary offline verification.
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
Natural-language interpretation remains experimental. Historical evaluation totals
are in the progress log, not a current quality guarantee.
