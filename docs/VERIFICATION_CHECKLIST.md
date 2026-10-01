# Current checkpoint: verification in three parts

The dashboard redesign and account-security implementation are ready for **user
verification**, not marked runtime-tested. The assistant ran no tests, browser
sessions or paid model calls. Static checks are separate from acceptance below.

## Before starting

From the repository root, stop the old launcher with Ctrl+C. Back up your account
database while stopped (if you have accounts). Do not delete or reset the data folder.

```powershell
if (Test-Path .\data\accounts.sqlite3) {
    $backupName = "accounts-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".sqlite3"
    Copy-Item -LiteralPath .\data\accounts.sqlite3 -Destination (Join-Path .\data $backupName)
}
uv sync --locked
uv run --locked playwright install chromium
```

If you have not created an administrator yet, run this once (not on every startup):

```powershell
uv run --locked python -m agentic_web_demo.dashboard.admin_setup
```

Choose a new username and unique password; no default credentials exist. Never
share the password or API key. Existing accounts are retained as ordinary users.

## 1. Verify dashboard, accounts and security

Run the offline checks first. These do not call OpenAI or write to a real OS
credential store through the new security regression tests:

```powershell
uv run --locked pytest tests/test_dashboard.py tests/test_dashboard_accounts.py tests/test_dashboard_security.py tests/test_dashboard_updates.py tests/test_dashboard_ui_structure.py tests/test_catalog.py tests/test_portal.py -v --tb=short
uv run --locked pytest -q --tb=short
```

Stop if tests fail. Share the failing test name, assertion and summary, with secrets
removed. Skipped browser/NATS/live-model tests in the default suite are expected;
they are not successful verification of those integrations.

Start Docker Desktop, wait for its engine, then launch the normal demo (not `-Dev`
during acceptance, because source edits can restart it):

```powershell
.\scripts\Start-Demo.ps1
```

The terminal asks for the separate synthetic hotel portal password. Keep the
launcher running. Open `http://127.0.0.1:8120` and press Ctrl+F5.

### Account/UI checklist

- Sign-in and registration are separate screens. Register two disposable users
  using distinct passwords. No registration code is requested. Duplicate username
  and incorrect password are rejected; secrets never appear in feedback.
- After sign-in, **Search studio** is the default. **Run history**, **API connection**
  and (admins only) **Administration** are separate sections.
- Tab through controls with your keyboard. Check visible focus, labels, narrow
  layout at approximately 390px and 768px, normal desktop, and 200% browser zoom.
  Table scrolling at small widths is expected; page-wide clipping is not.
- Only Search Studio contains search/review/results. API settings should not push
  the main workflow far down the page. No result evidence should start as invented
  success counts: a dash means not available.
- Create a structured proposal under user A. User B must not see it in Run history.
  Use different browser profiles to keep sessions independent; tabs in one profile
  share cookies. Automated tests cover guessed IDs and cross-user API access.
- In API connection, test **session-only** save, sign-out/sign-in: no key restored.
  Test **Remember my key**, sign-out/sign-in and server restart: that user's key is
  restored if the OS store is available. User B must remain unconfigured.
  For storage-only checks you may use a clearly fake non-secret value in a disposable
  test account; do not run model requests with it. Forget it afterward.
- **Clear session key** does not erase a remembered key. **Forget saved key** removes
  the remembered key and clears that account's session keys. Restart/login again
  and confirm it is not restored. No full key should be returned/displayed.
- If secure storage is unavailable or locked, expect session-only operation or a
  clear storage error, never an assertion that saving/deleting succeeded.
- As admin, disable a disposable user while that user is signed in elsewhere.
  Their next API action must be denied and the UI should request re-login. Re-enable
  them and verify sign-in works. Existing jobs/data are retained.
- Promote a disposable user, sign them in again, check Administration appears;
  demote them from another admin and confirm access is revoked. Wrong admin password
  must reject an action. Self-disable/self-demotion must be rejected.
- Inspect audit events. No passwords or API keys should be present. Do not delete
  accounts or reset passwords; these operations are intentionally not implemented.
- With no active jobs, stop/restart the server. Expect a reconnect notice within
  the polling interval. Refresh and sign in; nothing must automatically rerun.

## 2. Confirm both frameworks end-to-end

In another terminal, with Docker/NATS available, run the integration checks:

```powershell
uv run --locked pytest --run-browser --run-nats -q --tb=short
```

This command exercises browser/broker integrations but still does not enable paid
live-model tests. Then perform the following **in the dashboard for each framework**:

### Guided positive run

1. Open Search studio; choose **LangGraph**, then **Guided form**.
2. Use New York, check-in 7 days from today, check-out 9 days from today, maximum
   USD 200/night, minimum 4/5. These expected counts apply to that selected request,
   not a site-wide ceiling or rating floor.
3. Select **Create proposal**. Check original input, city, dates, currency, rating
   scale and price basis. There should be no extraction before approval.
4. Tick the review checkbox and select **Approve & run search**.
5. Confirm completed status and `workflow_verified: true` in technical evidence.
   Expect **10 extracted records, 5 matches, 5 published events and 5 verified receipts**.
   Check final trace; a stage that merely started is not proof it completed.
6. Filter **Matches only**: five displayed records. Filter **Non-matches only**:
   five with readable reasons. Download Excel/CSV/JSON/JSON Lines. **All saved records**
   exports the full run; **Currently filtered records** applies the table's filters.
   Compare IDs, prices and dates. See EXPORTS_GUIDE.md for format-specific checks.
7. Open Run history and select this job. It should load evidence, not execute again.
8. Repeat steps 1–7 with **CrewAI**, using a new proposal.

### Zero-match and failure runs

- Repeat with maximum USD 50 for each framework. Records may still be extracted,
  but there should be zero matches and no qualifying events. Skipped event stages
  are expected. Do not confuse a zero-match run with a failed extraction.
- Use invalid dates in the guided form: the browser should prevent submission or
  validation should stop before extraction. Never silently correct user dates.
- Browser-login failures and interrupted/duplicate execution are covered by the
  integration tests. Do not kill services or delete attempt files mid-run merely
  to force a retry. If testing service failure manually, use a disposable run and
  review evidence for partial side effects before trying a new proposal.

### Model-assisted run (paid, optional until approved to spend)

In API connection, configure a valid authorized key and model. Return to Search
studio, select Natural language, then **Use an example**. This generates an explicit
future-dated Boston request and does not make a call. Read it, approve paid API
consent and create the proposal. Review every field before execution. Repeat for
both frameworks. Do not approve an incomplete or incorrectly interpreted plan.

Record framework, planning mode, job/run ID, status, counts and receipt evidence.
Passing one workflow does not establish broad natural-language reliability.

## 3. Evaluate prompt handling and close documentation

### UI clarification checks

These are model-assisted requests and incur usage when submitted. Change one
condition at a time, start from the example request, and leave execution unapproved:

| Change | Expected safe behavior |
| --- | --- |
| Remove the dates | Visible request for more information; no tools run |
| Use September 31 of a future year | Reject/clarify the invalid date; never invent a checkout |
| Request Expedia | Unsupported external source; no local-source substitution |
| Request Wi-Fi or a pool | Unsupported capability, not an approved plan omitting the filter |
| Use EUR or an 8/10 rating scale | Unsupported definitions; no silent normalization |
| Say strictly under USD 200 | Clarify exclusive versus supported inclusive threshold |
| Ask for USD 150–250 with dates | Plan must include both inclusive bounds; no USD 200 ceiling |
| Ask to book/pay | Unsupported; no transaction tools |

The visible feedback panel should explain the actual returned guidance and list
missing fields. **Edit search** focuses the form; **Use guided form** changes input
method without inventing a translation. Neither automatically submits or approves.
If a constraint is dropped, mark it as a failure and do not execute the proposal.
UI improvements do not repair existing model semantic failures.

### Full live semantic suites (paid; you choose when to run)

The CLI test process does not read dashboard session/remembered keys. Follow the
secure environment setup in `docs/OPENAI_SETUP.md` first in this terminal. Then:

```powershell
$env:AGENTIC_ALLOW_MODEL_API = "1"
try {
    uv run --locked pytest tests/test_model_live.py --run-model --model-framework langgraph -v --tb=short
    uv run --locked pytest tests/test_model_live.py --run-model --model-framework crewai -v --tb=short
} finally {
    Remove-Item Env:AGENTIC_ALLOW_MODEL_API -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
}
```

These evaluate the existing contract; do not change assertions merely to match a
model response. Previous supplied baselines were LangGraph 43/44 and CrewAI 40/44;
new results must be recorded separately, with model and prompt version. A single
passing run is not a reliability guarantee. Stop after unexpected failures if you
want to avoid further API spend, and share the first failure before rerunning.

### Report back

Send test summaries and any failed assertions (no passwords/keys), screenshots of
layout problems, and this evidence table:

| Check | Status | Evidence / issue |
| --- | --- | --- |
| Offline account/dashboard tests | Not run | |
| Browser/NATS integrations | Not run | |
| LangGraph guided + model-assisted | Not run | |
| CrewAI guided + model-assisted | Not run | |
| Two-user/admin/key isolation | Not run | |
| Restart, empty state, keyboard/mobile UI | Not run | |
| Prompt handling / live semantic suite | Not run | |

PROJECT_PLAN.md and PROGRESS.md now distinguish current implementation from historical
checkpoints. Only add verified completion claims after these results are reviewed.
External website integration, clean-checkout handoff and landscape alignment remain
separate work; hosting is deferred.
