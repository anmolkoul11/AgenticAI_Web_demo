# Demo Dashboard MVP

The current navy/teal interface separates **Website Studio**, **Hotel demo**, **Run history**,
**API connection**, and **Administration** (admins only). The search page contains
configure, review/run and results panels. Hotel exports offer all/filtered records;
custom exports download the approved snapshot. See [CUSTOM_WEBSITE_GUIDE.md](CUSTOM_WEBSITE_GUIDE.md).
Follow [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)
for the current three-part acceptance sequence. UI changes are implemented but
still need user-run visual and functional verification.

## Website Studio: simple and detailed views

The main path is: choose a source card, describe the information to collect, give
the required consent, then start. The seven-checkpoint workflow map updates as the
job progresses. Open a checkpoint to see what happened or why it stopped; the
bar counts completed or unneeded checkpoints, not elapsed time. Browser page
health, captured-page coverage and review issues remain visible near the actions
they affect. A failed or partial run must be reviewed before saving; the UI does
not silently turn rejected records into exports.
Saving and optional NATS event publication have separate checkpoints: if event
delivery fails after a successful save, the saved result remains visibly saved.

Open **Advanced settings** for framework selection, record limits, optional
website sign-in, trusted resource origins, manual rules and event delivery.
Use **Detailed stage log** and **Technical evidence** for diagnostics. The
separate **Hotel demo** remains a clearly named guided example; Website Studio
uses neutral wording for websites, records and linked detail pages. Search and
link discovery are separate, explicitly approved model calls.

Local UI with separate user accounts for the LangGraph and CrewAI hotel workflows.
Start with [LOCAL_ACCOUNTS.md](LOCAL_ACCOUNTS.md) for account registration, private
workspaces and session-only or opt-in OS-stored OpenAI keys. See [ACCOUNTS_SECURITY.md](ACCOUNTS_SECURITY.md) for admin setup and storage limitations. This supersedes the original shared login.
Development is ready for user verification; no tests, browser runs or paid API
calls were executed during implementation. This is not a production deployment.

## First-time setup

A developer installs Git, uv and Docker Desktop and clones the repo. Internet
access is needed to download Python dependencies, Chromium and the NATS image.
From the repository root, run:

```powershell
.\scripts\Setup-Demo.ps1
```

The script installs locked dependencies and Chromium, not tests. If company
PowerShell policy blocks scripts, ask IT for the approved way to run them; do not
disable organization policy. Manual equivalent:

```powershell
uv sync --locked
uv run --locked playwright install chromium
```

## Sales/demo operator workflow

1. Start Docker Desktop and wait for its engine.
2. Right-click `scripts/Start-Demo.ps1` and select **Run with PowerShell**, or run
   `.\scripts\Start-Demo.ps1` in the project terminal.
3. Choose a synthetic hotel portal password of at least 12 characters for automation.
   Dashboard registration only requires a new username and password; no invitation code.
4. Create a local account in the browser, then sign in. Guided forms need no key.
   Add your own API key/model inside the dashboard; optionally remember it in the OS credential store.
5. The launcher starts the portal at `http://127.0.0.1:8110` and the dashboard at
   `http://127.0.0.1:8120`, then opens your browser. Use your individual account.
6. Choose LangGraph or CrewAI and the guided form or natural-language mode. Only
   **demo-hotels** is supported in this Hotel demo tab. For general page extraction,
   select **Website Studio** and follow [CUSTOM_WEBSITE_GUIDE.md](CUSTOM_WEBSITE_GUIDE.md).
7. Create a proposal. Planning does not log into the portal or publish events.
8. Review the original request, website target, every criterion, expiry and site configuration.
   Select the review checkbox only when correct, then **Approve & execute**.
9. Follow backend stage updates, inspect results and rule decisions, and download
   Excel/CSV/JSON/JSON Lines (see [export instructions](EXPORTS_GUIDE.md)). New York with maximum 200 USD and minimum 4/5 should give ten records,
   five matches and five verified receipts with the current seed/policy.
10. Inspect earlier dashboard jobs using history. Refreshing the page does not
    resubmit work. Only the latest 100 dashboard jobs are listed; CLI-only runs
    remain available through CLI artifacts, not this history screen.

Keep the launcher open during a demo. Ctrl+C stops its dashboard and owned portal;
NATS stays running so messages persist. To stop NATS later: `docker compose stop nats`.
The launcher refuses occupied/reserved ports instead of killing unrelated processes.
Do not close the window in the middle of a run if avoidable.

## Manual startup with an existing portal

Set `DEMO_USERNAME`, `DEMO_PASSWORD` and `DEMO_SESSION_SECRET` as in PORTAL_GUIDE.md
in this terminal too. Use matching portal credentials. For model planning configure
your API key in the dashboard after signing in (environment keys are not used). Then:

```powershell
$env:AGENTIC_DASHBOARD_PORTAL_URL = "http://127.0.0.1:8000"
uv run --locked uvicorn agentic_web_demo.dashboard.app:create_app --factory --host 127.0.0.1 --port 8120 --workers 1 --no-access-log
```

Open `http://127.0.0.1:8120`. Serve exactly one dashboard worker/process against
the data directory. Do not expose it through a public bind, proxy or tunnel.
`AGENTIC_DEMO_DATA_DIR` selects storage, default `data/`. Policy remains
`config/rules.yaml`; restart after server configuration changes.

## Verification — run these yourself

No paid calls are made by these tests:

```powershell
uv run --locked pytest tests/test_dashboard.py -v --tb=short
uv run --locked pytest -q
uv run --locked pytest --run-browser --run-nats -q --tb=short
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
```

The integration command requires Chromium and running NATS. Manually verify:

- Wrong password fails; sign-out protects job APIs and downloads.
- Structured proposals work with no API key and show the approved user thresholds.
- Dates, missing fields and unsupported input stop without tools.
- Both frameworks complete a reviewed structured New York run.
- Background progress is visible; page refresh/history can re-open an active job.
- A second submission during a job is rejected, not queued or silently billed.
- Re-executing an attempted plan cannot repeat side effects.
- Zero matches completes without publish/receive; those stages are marked skipped.
- Downloads default to all saved records; choose Currently filtered records to export the table's current subset. Excel includes available rule decisions. Rule reasons and receipts agree.
- Stop the portal, execute a new approved plan, inspect the sanitized error.
- Restarting after interrupted work marks the job interrupted, never auto-replays.
- With explicit paid consent, try a model proposal in each framework, review it,
  and execute. These manual model actions incur API charges.
- Verify keyboard navigation, mobile layout and error messages in your browser.

Known semantic issues remain: LangGraph's latest supplied live result was 43/44;
CrewAI's 40/44. Wi-Fi, sorting, trip budgets and reversed-date classification have
known failures. The dashboard does not fix them. Never approve a plan that omits
a requirement. A successful API call is not proof of accurate interpretation.

## Recovery and implementation boundaries

`data/users/<account-uuid>/dashboard-jobs/<uuid>.json` stores sanitized stage starts and final workflow
evidence. Each user's `plans/` remains the authoritative approval/attempt/result
store. A restart marks unfinished dashboard jobs interrupted. Check the matching
plan result and run-specific event status before deciding how to recover; never
delete attempt claims to force a replay. The UI has no cancel/resume/retry button
because safely interrupting side effects requires a separate design.

Progress is stage-based, not a fabricated percentage. A stage shown as started
is not proof of success; final trace and receipt evidence determine completion.
Readiness checks only TCP reachability; they do not verify API credentials,
Chromium, portal login or NATS JetStream. Pending delivery is not shown as success.

API keys stay server-side, in session memory or opt-in OS credential storage; passwords are stored as salted hashes. Browser sessions are
HTTP-only signed cookies, with server-side expiry/logout revocation. POST requests
require CSRF tokens and the same Origin; hostnames are restricted to loopback.
No permissive CORS, arbitrary URL entry or filesystem path input is provided.
Exports neutralize spreadsheet formulas. Synthetic request text is persisted:
do not type confidential data or secrets. The local account can still read its
files/process environment; this is not multi-user enterprise authorization.

Developers extend `dashboard/service.py` orchestration, `dashboard/app.py` HTTP
boundaries and `dashboard/static/` presentation. Shared agent services remain the
source of validation/execution behavior. No Node.js build or new dependency is
required. External adapters, enterprise identity, durable distributed workers,
secret vault integration and production deployment remain future work.
