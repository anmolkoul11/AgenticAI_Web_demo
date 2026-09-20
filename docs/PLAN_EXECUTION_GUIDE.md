# Reviewed LangGraph execution

This is the recommended bounded demo interface. It has two planning paths and
one execution path. Only `demo-hotels` / `hotel-search-v1` is supported today:
the local login-protected portal, USD per night including taxes, ratings out of
five, inclusive thresholds. This is not arbitrary-URL scraping or model training.

## 1. Structured proposal (no model)

Run from the repository root in PowerShell:

```powershell
$checkIn = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
$checkOut = (Get-Date).AddDays(9).ToString('yyyy-MM-dd')
uv run --locked agentic-demo langgraph plan --city "New York" --check-in $checkIn --check-out $checkOut --max-price 200 --min-rating 4 --base-url "http://127.0.0.1:8100"
```

Use `--all-cities` instead of `--city` for an intentional unrestricted city search.
Missing fields do not acquire defaults. Inputs may tighten policy, not loosen it.
No portal, credentials, broker or model is required for proposal creation.

## 2. Model-assisted proposal (experimental interpretation)

Follow OPENAI_SETUP.md to configure your API key in this terminal first:

```powershell
$env:AGENTIC_MODEL_PROVIDER = "openai"
$env:AGENTIC_MODEL_NAME = "gpt-5.4-mini"
$demoRequest = "Find New York hotels from $checkIn to $checkOut, at most USD 200 per night including taxes, rated at least 4 out of 5."
uv run --locked agentic-demo langgraph plan --request $demoRequest --base-url "http://127.0.0.1:8100" --allow-model-api
```

Never combine `--request` with explicit search fields. The model proposes; it
does not execute tools. Unsupported/missing/invalid outcomes do not create plans.
Incorrect plans can pass validation. Compare every field and omitted requirement with the original
request. Approval does not prove semantic correctness. Use synthetic requests only.
OpenAI is required only for the model-assisted path, not the structured path.

## 3. Review, then approve an exact revision

Copy the plan ID printed by either planning path:

```powershell
$planId = "PASTE-PLAN-ID"
uv run --locked agentic-demo langgraph review --plan-id $planId
```

Read the request (if present), city, dates, price basis, rating scale, thresholds,
policy and website target. Copy the full revision hash only after review.
To cancel, do nothing: proposals do not execute automatically and expire after
24 hours. To edit, create a new proposal with corrected inputs; do not edit JSON.

Start the portal as described in PORTAL_GUIDE.md, using port 8100 if Windows has
reserved port 8000. Start Docker Desktop and NATS, then set credentials in the
execution terminal to match the running portal:

```powershell
docker compose up -d --wait nats
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Running portal's demo password" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
Remove-Variable demoPassword
$revision = "PASTE-REVIEWED-REVISION-HASH"
uv run --locked agentic-demo langgraph execute --plan-id $planId --approve $revision --headed
```

Execution uses the saved target and exact plan; it never calls the model. Any
explicit `--base-url` must equal the saved target. Policy is reloaded from
config/rules.yaml (`--policy` may select another file); a changed policy requires
a new proposal. Dates and expiry are rechecked before tools run.
Expected seeded New York result: four records, two matches and two verified receipts.
Execution reports `model_used: false` because no inference occurred during execution;
`planning_source` and `planning_model` retain proposal provenance.

## Local artifacts and recovery

`data/plans/<id>.json` stores the proposal, `.attempt.json` records its execution
claim, and `.result.json` records the sanitized result. The default data directory
is already Git-ignored. Custom data directories need their own exclusions.
Credentials are not stored in proposals. Requests are stored, so use synthetic data.

Each plan ID permits one execution attempt. A crash or failure keeps the claim:
do not delete it to retry blindly. Inspect the result and use existing export,
events-status, publish and consume recovery commands by extraction run ID.
If a crash leaves no result, inspect local records before deciding to create a
new run. This is not durable resumption, distributed locking or exactly-once execution.
The digest binds approval to reviewed content; it is not authentication or a
signature against a malicious local user. Shared deployment needs real identity,
authorization, a protected store and durable jobs.

## Developer boundaries

- `agents/saved_plans.py`: framework-neutral proposal storage and revision checks;
  execution currently invokes LangGraph and will need a separate CrewAI runner.
- `agents/plan_commands.py`: CLI entry points; future UI should call services,
  not shell out to these commands.
- `agents/langgraph_workflow.py`: graph coordination; saved plans start at validation.
- `browser.py`: reference website adapter (login, DOM extraction, normalization).
- `listings.py` and `rules.py`: hotel schema and deterministic hotel policy.
- `storage.py` and `messaging.py`: persistence and NATS delivery services.

Adding a website requires approved automation scope, authentication, field
mapping and tests. Adding another domain requires its schema and rules; merely
changing a URL is insufficient. Unknown currency/price definitions must not be
guessed. The current hotel adapter rejects incompatible/invalid extraction data;
a generic record-level "cannot evaluate" state is not implemented.
No generic adapter registry or UI is claimed in this checkpoint.

## Verification and limitations

```powershell
uv run --locked pytest
uv run --locked pytest --run-browser --run-nats
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
```

Saved-plan tests cover both proposal paths (model mocked), exact execution with
no planner call, mismatched approval, changed content/policy/target, expiry, past
dates, missing approval, unsupported adapters, stage failures and replay rejection.
The browser/NATS suite exercises saved-plan execution with real tools and isolated
test data, including zero matches. Live semantic tests remain unchanged and opt-in:

```powershell
uv run --locked pytest tests/test_model_live.py --run-model -v --tb=short
```

The old `langgraph --mode ...` commands remain for compatibility and evaluation.
They bypass this approval flow, and `--plan-only` there does not save a proposal.
Use `plan/review/execute` for reviewed demonstrations. This is a local UX boundary,
not an authorization barrier against a user who controls the CLI and repository.
CrewAI, clean-checkout handoff and enterprise deployment are separate milestones.
