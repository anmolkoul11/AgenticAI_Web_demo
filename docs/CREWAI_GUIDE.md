# CrewAI: reviewed website-extraction demo

CrewAI independently orchestrates the same hotel workflow as LangGraph. One
Agent/Task/Crew creates model-assisted proposals; a CrewAI Flow executes approved
plans using shared browser, SQLite/JSON, rules and NATS services. It does not call
LangGraph. Structured planning calls no model. No agent books rooms or pays money.

## Setup

Run from `D:\Projects\AgenticAI_Web_demo`. Stop project Python processes before
syncing on Windows (loaded dependency files can otherwise block installation):

```powershell
uv sync --locked
uv run --locked playwright install chromium
```

Follow PORTAL_GUIDE.md to start the portal in a separate terminal. Use its actual
port (examples here use 8000); if Windows reserves it, choose an available port
and use the same URL when creating plans. Start Docker Desktop, then:

```powershell
docker compose up -d --wait nats
```

In the execution terminal, configure the same account as the running portal:

```powershell
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Running portal's demo password" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
Remove-Variable demoPassword
$portalUrl = "http://127.0.0.1:8000"
$checkIn = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
$checkOut = (Get-Date).AddDays(9).ToString('yyyy-MM-dd')
```

## Path A: explicit inputs, no model

```powershell
$proposalJson = uv run --locked agentic-demo crewai plan --city "New York" --check-in $checkIn --check-out $checkOut --max-price 200 --min-rating 4 --base-url $portalUrl
if ($LASTEXITCODE -ne 0) { $proposalJson; throw "Planning failed; stop here." }
$proposal = ($proposalJson -join "`n") | ConvertFrom-Json
$planId = $proposal.proposal.plan_id
$revision = $proposal.revision
uv run --locked agentic-demo crewai review --plan-id $planId
```

Review the plan before running the next command. Expected: framework `crewai`,
source `structured`, correct target and dates, inclusive USD nightly price <=200
including taxes and rating >=4/5. Use `--all-cities` instead of `--city` only when
you explicitly want all cities.

```powershell
uv run --locked agentic-demo crewai execute --plan-id $planId --approve $revision --headed
```

Expected: framework `crewai`, status `completed`, four records, two matches and
two verified receipts. Execution calls no model. Do not execute the same plan twice.

## Path B: local model-assisted proposal

Install/configure Ollama using OLLAMA_GUIDE.md, including disabling cloud features.
This CrewAI adapter currently supports only local Ollama qwen3:8b or qwen3:4b.
It does not silently select a hosted provider. LangGraph's OpenAI adapter remains
available separately; CrewAI hosted-provider integration is future work.

```powershell
$env:AGENTIC_MODEL_PROVIDER = "ollama"
$env:AGENTIC_MODEL_NAME = "qwen3:8b"
$demoRequest = "Find New York hotels from $checkIn to $checkOut, at most USD 200 per night including taxes, rated at least 4 out of 5."
$proposalJson = uv run --locked agentic-demo crewai plan --request $demoRequest --base-url $portalUrl
if ($LASTEXITCODE -ne 0) { $proposalJson; throw "Planning failed; stop here." }
$proposal = ($proposalJson -join "`n") | ConvertFrom-Json
$planId = $proposal.proposal.plan_id
$revision = $proposal.revision
uv run --locked agentic-demo crewai review --plan-id $planId
```

Stop and compare every interpreted field with your original request. If anything
was guessed, omitted or changed, do not approve. Create a corrected proposal.
When satisfied, run the same `crewai execute` command as Path A. Expect
`planning_source: model-assisted` and `planning_model.orchestrator: crewai`.
`model_used: false` during execution is correct: the exact saved plan is executed
without another inference call. To cancel a proposal, do not execute it.

## Implementation and customization

- `agents/crewai_planner.py`: defines the agent role, goal, task and sequential crew.
  The BaseLLM bridge sends actual task messages to local Ollama and validates JSON.
  It wraps validated JSON in CrewAI's final-answer format without a second inference.
- `agents/model_contract.py`: shared instructions and schema. "Train" here means
  configure instructions/examples and evaluate, not fine-tune weights.
- `agents/crewai_workflow.py`: Flow listeners coordinate validation, extraction,
  save, export, evaluation, publishing, receiving and verification. Failures stop
  subsequent tool calls; zero matches skips publish/receive. Synchronous tools run
  in worker threads because CrewAI Flows use an async event loop.
- `agents/runners.py`: explicit framework dispatch. No fallback to LangGraph.
- `agents/saved_plans.py`: shared review artifacts, hashes, expiry and attempt claims.
  New version-2 proposals bind the framework into the approved revision. Old
  version-1 LangGraph proposals retain their original hash calculation.
- `browser.py`, `listings.py`, `rules.py`: approved website adapter, hotel schema
  and deterministic rules. Add site-specific authentication, field mapping and
  tests to support another website; changing only the URL is insufficient.

No delegation, execution tools, memory, embedding service or additional planning
agent is enabled in the planning Crew. The adapter permits one local HTTP call
per planning attempt, no model repair loop, 1200 output tokens and an 8192-token
context for Crew task overhead (LangGraph's direct adapter remains at 4096).
CrewAI tracing/tracking and OpenTelemetry are disabled before runtime import.
These process-level settings suit a local CLI; shared hosting needs its own
isolation, identity, authorization and telemetry policy.

## Recovery and limitations

Proposals expire after 24 hours and revalidate current dates/policy before tools.
Approval binds framework, target and fields. Each plan ID allows one execution
attempt; failed/crashed attempts are not automatically replayed. Inspect
`data/plans/<id>.result.json` and use run-specific recovery commands described in
PLAN_EXECUTION_GUIDE.md. Never delete an attempt claim merely to repeat side effects.
Default `data/` is ignored by Git. Credentials stay in local environment variables,
not proposals or model prompts. Use synthetic requests: proposal text is stored.

CrewAI's observed Qwen3 baseline: **21 passed, 17 failed** in 38 semantic tests.
Thirteen failed cases accepted incorrect plans (including wrong relative dates);
three stopped with the wrong classification and one returned a generic failure.
Human review is required but does not guarantee semantic correctness. Do not
claim CrewAI resolves LangGraph's interpretation limitations or production readiness.
Different framework prompts/context limits mean this is not an isolated model benchmark.

## Checks for the developer

The user reported staging results: 222 passed, 39 skipped in the full local suite.
The skips are 38 live semantic cases and one live-model integration case. Recheck
in the actual repository after syncing; staging results are not a fresh-checkout
or actual-repository acceptance claim. No tests were rerun during final handoff.

```powershell
uv run --locked pytest --run-browser --run-nats -q --tb=short
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
```

Optional real-model checks (expect documented semantic failures until improved):

```powershell
uv run --locked pytest tests/test_model_live.py --run-model --model-framework crewai -v --tb=short
uv run --locked pytest tests/test_browser_integration.py -k live_model --run-model --model-framework crewai --run-browser --run-nats -v --tb=short
```

The shared semantic expectations are unchanged. Upstream CrewAI deprecation
warnings are reported separately from assertion failures. Before pushing, manually
verify both reviewed paths above in the actual repository. No auto-commit/push.

Official references: [Flows](https://docs.crewai.com/en/concepts/flows),
[custom LLM bridge](https://docs.crewai.com/en/learn/custom-llm),
[telemetry](https://docs.crewai.com/en/telemetry).
