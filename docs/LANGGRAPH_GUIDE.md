# Checkpoint 5: LangGraph developer guide

## Scope and completion status

The implementation supports simulated planning, local Ollama, and opt-in OpenAI.
All use the same browser, SQLite/JSON storage, Python rules, and NATS tools.
**Actual inference is not yet verified. Checkpoint 5 remains pending real-model
acceptance. A passing local model is sufficient; paid API use is not required.**

For the local route, start with [OLLAMA_GUIDE.md](OLLAMA_GUIDE.md). Sections 2-3
and the paid test instructions below describe the OpenAI route specifically.
Ollama uses --mode live without --allow-model-api and needs no OpenAI key.

This is a controlled, model-assisted workflow, not an autonomous browser agent.
The model interprets the request; LangGraph routes through code-approved tools.
It cannot choose arbitrary websites, paths, shell commands, credentials, or brokers.
The portal contains fictional listings. Expedia/Tripadvisor integration, a UI,
durable graph resumption, multi-turn conversation storage, and fine-tuning are out
of scope. CrewAI is the next framework, not implemented by this checkpoint.

## 1. Install and run the offline demo

From the repository root in PowerShell:

```powershell
uv sync --locked
uv run --locked playwright install chromium
docker compose up -d --wait nats
```

Start the website in terminal 1 using [PORTAL_GUIDE.md](PORTAL_GUIDE.md).
In terminal 2, use the same dedicated demo account:

```powershell
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Running portal's demo password" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
uv run --locked agentic-demo langgraph --mode simulated --scenario new-york --headed
```

Expected: 4 New York listings saved, 2 qualifying events, 2 run-specific receipts.
`--headed` shows Chromium; omit it for headless operation. `--base-url` is the
loopback-only portal URL, NOT the model endpoint. NATS_URL also stays loopback-only.
Use `& $uvExecutable` instead of `uv` if your terminal requires it.

```powershell
uv run --locked agentic-demo langgraph --mode simulated --list-scenarios
uv run --locked agentic-demo langgraph --mode simulated --scenario missing-city
uv run --locked agentic-demo langgraph --mode simulated --scenario new-york --plan-only
```

The last two commands require no running services or demo credentials. Missing
city returns exit 2 / `needs_input`. Preview returns exit 0 / `planned`; it does
not log in, create data, or publish anything.

| Scenario | Expected records / qualifying events |
| --- | --- |
| new-york | 4 / 2 |
| boston | 2 / 1 |
| all-cities | 6 / 3 |
| no-matches | 4 / 0 (maximum USD 50) |
| empty-results | 0 / 0 (Unknown City) |
| missing-city | Stops before tools |

Simulated mode performs exact fixture lookup, not natural-language interpretation.
Dates are today + 7 through today + 9. It does not call a model even if an API key
is present. It rejects `--request` and `--allow-model-api`.

## 2. Configure a live provider only after approval

Do not use a personal account for organization work without authorization.
Use synthetic requests only; never put credentials or organization/customer data
in request text. CLI arguments can appear in shell history and process listings.
The model receives the request, fixed instructions, reference date, and output
schema. It does not receive website credentials, cookies, listings, database
contents, or NATS records.

No model ID is chosen silently. Set a model available to your approved API project
that supports the Responses API and structured outputs. This is API access, not
reuse of ChatGPT/Codex login credentials.

```powershell
$env:AGENTIC_MODEL_PROVIDER = "openai"
$env:AGENTIC_MODEL_NAME = Read-Host "Approved model ID"
$modelKey = Read-Host "OpenAI API key (input hidden)" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $modelKey).Password
Remove-Variable modelKey
```

Environment variables are process-local and inherited by child processes, not a
production secret vault. Never echo the key or paste it into chat, Git, screenshots
or logs. `.env.example` is sanitized documentation; `.env` is **not automatically
loaded**. Prefer an approved secret manager in shared deployments.

| Setting | Default / allowed values |
| --- | --- |
| AGENTIC_MODEL_PROVIDER | openai or ollama; default openai |
| AGENTIC_MODEL_NAME | Required, no default |
| OPENAI_API_KEY | Required locally; excluded from settings repr/report |
| AGENTIC_MODEL_TIMEOUT_SECONDS | 30; range 1-60, per network operation |
| AGENTIC_MODEL_MAX_RETRIES | 1; range 0-2 (at most 2 attempts by default) |
| AGENTIC_MODEL_MAX_OUTPUT_TOKENS | 1200; range 256-4096 |

There is one logical planning call per invocation, no agent retry loop and no
automatic retry of side-effecting tools. SDK retries may add usage and wait time;
the timeout is not a total workflow deadline. Input is capped at 2000 characters.
Token limits are not a monetary budget: review provider usage/billing separately.

The adapter pins `https://api.openai.com/v1`, ignores OPENAI_BASE_URL, disables
redirect following, and does not disable TLS verification. Normal HTTP proxy/
certificate environment configuration may apply. Organization/project environment
settings recognized by the SDK may also apply; use the intended API project.
Other gateways require an explicitly reviewed adapter, not an untrusted URL swap.

Responses use `store=False`; this is **not a guarantee of zero provider retention**.
Check approved account data controls. LangSmith tracing is disabled around graph
execution. SDK/HTTP debug logging is suppressed to avoid printing model payloads.

## 3. Preview, then execute a synthetic natural-language request

Only run these commands once API usage is approved; even plan-only makes a paid
model call. No services or portal credentials are required for the preview.

```powershell
$checkIn = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
$checkOut = (Get-Date).AddDays(9).ToString('yyyy-MM-dd')
$demoRequest = "Find hotels in New York from $checkIn to $checkOut, at most USD 200 per night including taxes, rated at least 4 out of 5."
uv run --locked agentic-demo langgraph --mode live --allow-model-api --request $demoRequest --plan-only
```

Inspect city, dates, price, rating and `effective_rules`. With portal and NATS
running and demo credentials configured, execute:

```powershell
uv run --locked agentic-demo langgraph --mode live --allow-model-api --request $demoRequest --headed
```

This is a **new model call**, not execution of the exact saved preview. There is
no durable approval/resume mechanism. Inspect the returned executed plan too.
For this request, acceptance is 4 records, 2 rule matches, 2 published events,
and 2 verified receipts. A valid no-match request succeeds with zero events.

Missing/ambiguous information returns `needs_input` and field names. Resubmit the
**whole request** with explicit values; the process has no previous conversation.
Use ISO dates and inclusive wording (`at most`, `at least`). Ambiguous dates such
as "next weekend" and strict comparisons such as "under" require clarification;
the existing rule engine uses inclusive comparisons and must not silently change
their meaning. Unsupported amenities, currencies, booking/payment and external
website requests are rejected by the planner. Semantic interpretation is still
model-dependent; the live evaluations measure it, rather than guaranteeing it.

## 4. Preferences versus policy

Live mode loads `config/rules.yaml` as its trusted policy by default. A missing or
invalid file stops before model access; use `--policy PATH` for another reviewed
local policy. A request can tighten but cannot loosen its maximum price or minimum
rating. Conflict returns `policy_rejected` before tools; no silent clamping.

For the current policy (maximum USD 200, minimum rating 4): a request for USD 180
and rating 4.5 is valid; USD 300 or rating 3 is rejected. Policy identity/version
are preserved in the effective rules. Events use the effective-rule fingerprint.
The model never edits policy files. This local file is developer-controlled, not
a centrally enforced enterprise authorization system.

Simulated mode retains its original fixture thresholds without loading YAML,
unless `--policy PATH` is explicitly supplied. Standalone `process --rules`
behavior is unchanged. API callers using a live planner get default Rules if they
do not provide a policy; CLI always loads the configured file.

## 5. Understand the implementation and results

`plan_request -> validate_plan -> extract -> save -> export -> evaluate -> publish -> receive -> verify`

Validation stops missing, unsupported, invalid, or policy-conflicting plans.
Preview stops after validation. Zero matches skips publish/receive. Tool errors
stop subsequent stages; verification checks this run's persisted event IDs and
receipts, not a global consumer count or just a broker acknowledgment.

| File | Responsibility |
| --- | --- |
| agents/planning.py | Plan/Candidate contracts, planner protocol, validation, fixtures |
| agents/model_contract.py | Shared versioned instructions and wire schema |
| agents/openai_planner.py | Hosted OpenAI SDK adapter and safe errors |
| agents/ollama_planner.py | Local-only Ollama HTTP adapter and safe errors |
| agents/langgraph_workflow.py | StateGraph, deterministic tool routing, result projection |
| agents/tools.py | Existing shared browser/storage/rule/NATS wrappers |
| agents/cli.py | Explicit modes, request input, policy and permission gates |

Progress is stderr; the JSON report is stdout. It includes `mode`, `model_used`,
`model_api_attempted`, safe provider/model metadata and token usage when available,
validated plan/effective rules, run ID, counts, export path, delivery evidence and
stage trace. Raw request, raw model response and secrets are not included.
`model_used` means a parsed API response was returned, not that the model's answer
was correct; failures during SDK parsing may have incurred usage even when false.
Mocked SDK tests simulate that response and are not real-model evidence.

| Status | Exit code | Meaning |
| --- | --- | --- |
| completed | 0 | Tool workflow and expected receipts verified |
| planned | 0 | Validated preview only; no tools ran |
| needs_input | 2 | Missing/ambiguous fields; resubmit full request |
| unsupported | 2 | Request outside supported demo scope |
| policy_rejected | 2 | Request conflicts with trusted policy |
| failed | 1 | Safe stage/error code; later tools did not execute |
| delivery_unconfirmed | 1 | Incomplete run-specific delivery evidence |

`workflow_verified` describes this run, not project-wide completion. The obsolete
`checkpoint_complete` report field was removed: one successful run cannot certify
a checkpoint. `agentic-demo status` reports implementation availability and the
pending live-verification milestone; it does not contact services or discover
whether you have run acceptance tests locally.

## 6. Recovery

SQLite snapshots, event outbox and receipts persist, but LangGraph state does not.
Re-running a request creates a NEW extraction run. After a failure, retain run_id
and use the relevant recovery command rather than repeating extraction:

```powershell
uv run --locked agentic-demo export --run-id "RUN-ID"
uv run --locked agentic-demo events-status --run-id "RUN-ID"
uv run --locked agentic-demo publish --run-id "RUN-ID"
uv run --locked agentic-demo consume
```

If evaluation failed, recover with `process --run-id` and a YAML containing the
reported `effective_rules`; do not substitute different thresholds. The shared
receiver can consume other pending runs and is bounded to 100 messages per call.
Backlog can produce `delivery_unconfirmed`; consume and inspect the existing run.
See [EVENTS_GUIDE.md](EVENTS_GUIDE.md) for retention, retries, and deduplication.

## 7. Evaluate and close checkpoint 5

Offline checks (no OpenAI calls, even with a key present):

```powershell
uv run --locked pytest
uv run --locked pytest --run-browser --run-nats
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The SDK tests use HTTPX MockTransport, not a fake parser: they exercise actual
request serialization and response parsing. Browser tests also drive mocked
model output through real Chromium, SQLite and NATS using isolated TEST streams
and temporary data. These tests do not establish natural-language model quality.

After approval and local model configuration, run these **paid** evaluations:

```powershell
$env:AGENTIC_ALLOW_MODEL_API = "1"
uv run --locked pytest tests/test_model_live.py --run-model -q
uv run --locked pytest tests/test_browser_integration.py -k live_model --run-model --run-browser --run-nats -q
Remove-Item Env:AGENTIC_ALLOW_MODEL_API
```

There are 12 semantic cases plus 1 live end-to-end case: 13 logical model calls
(up to 26 attempts with default retry settings). Tests skip unless --run-model
is supplied; enabling it without AGENTIC_ALLOW_MODEL_API=1 fails before API use.
They use synthetic requests and temporary local data. Do not publish raw pytest
failure output without review. Optional local evidence: `--junitxml=artifacts/model-evals.xml`.

Acceptance requires correct structured fields, clarification for missing/ambiguous
input, unsupported requests rejected, policy conflicts stopped, and a real-model
run producing the expected saved listings/events/receipts. Infrastructure/model
errors and tool failures are tested offline. Record model ID, prompt version,
date and results in PROGRESS.md; approval plus passing real tests closes checkpoint
5. Do not mark it complete just because the adapter or mocked tests pass.

## 8. Adapt the template and replace the provider

"Training" here means editing versioned instructions, schema and evaluation
examples, then measuring behavior; it is not changing model weights. Extend
instructions in model_contract.py only with matching schema/tool/tests changes.
Keep credentials inside tools and results derived from persisted evidence.

For another provider, implement `Planner.plan(request, today) -> dict` producing
Candidate-compatible fields; use `mode="live"`, safe metadata, and PlanningError
codes. Add an explicit CLI factory branch and provider configuration. Reuse the
graph and tool contracts, then rerun the same evaluations. Authentication,
structured outputs and semantics may differ: migration is not promised to be a
single environment-variable change. Never silently fall back to another provider.

For another authorized website, replace the browser adapter and listing mapping,
retain the validation/storage/event contracts where applicable, and add dedicated
login/extraction tests. Do not bypass MFA, CAPTCHA or access controls.

References: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[OpenAI production guidance](https://developers.openai.com/api/docs/guides/production-best-practices),
[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
# Recommended reviewed execution

See [PLAN_EXECUTION_GUIDE.md](PLAN_EXECUTION_GUIDE.md) for structured or model-assisted
planning followed by revision-bound execution. The commands below describe the
legacy direct-run/evaluation interface: they do not enforce saved-plan approval.
The real local end-to-end demo succeeded, but the expanded semantic baseline was
20 passed / 18 failed. Broad natural-language acceptance is not complete.
