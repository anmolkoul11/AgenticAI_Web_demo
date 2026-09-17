# Progress

## Integration re-verification after Docker startup

The local NATS container was healthy. `pytest --run-browser --run-nats` passed:
204 passed, 39 skipped, one existing Starlette/AnyIO deprecation warning.
The skips are 38 live semantic evaluations and one live-model integration case;
no model requests were made. The previously failing broker-dependent tests now
pass, including saved-plan real-browser/storage/rules/NATS execution and zero
matches. Manual review of the new plan/review/execute UX remains for the user.
This does not change the documented 20/38 model interpretation baseline.

## Reviewed-plan handoff (current)

User evidence: local Qwen3 8B ran on GPU and completed the portal-to-NATS workflow
with four records, two matches and two verified receipts. Expanded semantic
evaluation: 20 passed, 18 failed. Preserve that baseline; broad language parsing
is not accepted. Earlier "no live inference" statements are historical.

Added structured and model-assisted proposal creation, review, revision-bound
approval, fixed saved-target execution, policy/date/expiry checks and single-attempt
claims. Execution starts at graph validation and never replans. Results are kept
beside proposals under the ignored data directory. Legacy direct runs remain
explicitly documented as bypassing this local review interface.
See PLAN_EXECUTION_GUIDE.md for commands, extension boundaries and recovery limits.
No prompt/model changes or semantic test expectation changes are part of this work.
CrewAI and final clean-checkout starter-kit acceptance remain separate work.

Verification so far: 21 new saved-plan unit/CLI cases pass. Full local suite
attempt: 198 passed, 39 skipped, 6 broker-dependent failures because Docker's
Linux engine/NATS were unavailable. These are not accepted as passing; rerun
after Docker/NATS start. Lint, format and whitespace checks passed.
No new live-model calls, model downloads, commits or pushes were performed.

## Completed checkpoints

- Checkpoints 1-2: foundation and portal merged into main.
- Checkpoints 3-4: extraction/storage and rules/NATS merged in commit bfbdc08;
  previous full suite: 79 passed. User owns all commits and pushes.

## Checkpoint 5a: LangGraph scaffold

Branch `langgraph-agent`, clean at initial inspection.
Implemented explicit simulated planning and a real LangGraph state graph calling
the existing browser, persistence, rules and messaging tools. Missing/invalid
plans stop before tools; failures stop later actions; verified receipts are
correlated by extraction run and event IDs.

No live model integration, arbitrary-language interpretation, agentic tool-choice
loop, durable graph resumption or dashboard is claimed. Checkpoint 5 remains
incomplete until approved model access and real-model evaluation are available.

Verification on Python 3.11.16:

- Full suite `pytest --run-browser --run-nats`: 101 passed, no skipped tests.
- Default suite: 94 passed, 7 skipped (opt-in browser/broker cases).
- New real-tool integration exercised the LangGraph graph with scripted planning:
  4 NYC records, 2 matches, 2 acknowledged events, and 2 verified receipts.
  Also tested the no-match path skipping broker operations.
- 21 graph/planner/CLI unit cases cover success, missing fields, invalid plans,
  every tool-stage failure, error redaction, relative dates and receipt verification.
- Ruff lint passed. One upstream Starlette/AnyIO deprecation warning remains.
- External tracing disabled for graph execution. No model inference or paid API
  calls made. Temporary test portal stopped and TEST stream removed afterward.
- Packaging and final formatting/whitespace checks recorded at handoff.

No commit or push performed. Checkpoint 5a is ready for review; checkpoint 5 is
still pending approved model integration and real-model evaluation.

## Checkpoint 5b implementation: live adapter, offline verification

Implemented on the existing `langgraph-agent` branch, preserving uncommitted 5a
work. User explicitly confirmed approval is pending and requested offline-only
implementation/testing. No personal API key was read and no live model request
was made. No Git commit, push or branch change was performed.

Added:

- OpenAI Responses structured-output adapter using the actual SDK, replaceable
  behind the provider-neutral Planner/Candidate contract. No model ID is assumed.
- Explicit live CLI mode and API-use permission flag, natural-language requests,
  plan-only preview, missing-information/unsupported outcomes, and safe errors.
- Code-enforced policy limits loaded from config/rules.yaml in live mode; request
  preferences may tighten but cannot loosen them. Effective rules are reported.
- Bounded request length, output tokens, retries and timeouts; no automatic retry
  of browser/storage/messaging stages and no fallback to simulated planning.
- Safe metadata/token reporting, disabled graph tracing, suppressed SDK payload
  logging, pinned OpenAI endpoint and store=False (not a zero-retention claim).
- SDK MockTransport tests plus the mocked-model -> real Chromium -> SQLite/JSON
  -> rules -> NATS path. Live semantic/end-to-end tests are separate and opt-in.
- Updated step-by-step guide, safe configuration example and provider replacement
  instructions. Model interpretation remains unverified until live tests pass.

Verification in staging, then the actual repository on Python 3.11.16:

- Default suite: 144 passed, 21 skipped (browser/NATS/live-model opt-ins).
- Full local suite `pytest --run-browser --run-nats`: 152 passed, 13 skipped.
  The 13 skips are exactly 12 live semantic cases plus 1 live end-to-end case.
- Both simulated and mocked-SDK integration paths extracted 4 NYC listings,
  matched 2 and verified 2 receipts; both also passed zero-match routing.
- One upstream Starlette/AnyIO deprecation warning remains.
- All 50 SDK/configuration/permission regression cases passed without network
  model calls. Ruff lint, formatting (36 files), Git whitespace checks and both
  source/wheel package builds passed. Locked dependency sync succeeded.
- CLI smoke checks verified status, simulated plan-only, and missing-city exit 2.
- Git ignores .env/.env.local, data exports and local evaluation artifacts;
  only the sanitized .env.example is tracked among environment files.
- Temporary portal/test data and uniquely owned TEST streams are isolated from
  user demo records; the already-running NATS service was not replaced.

## Remaining acceptance and user review

Review the changed guide and run the offline commands from the repository.
Checkpoint 5 is NOT marked complete: a configured local Ollama model or approved
hosted model and successful live semantic plus end-to-end evaluations remain
required. Commands and expected evidence are in LANGGRAPH_GUIDE.md and
OLLAMA_GUIDE.md. Credentials stay local, never in chat or Git.
The status command reports this pending milestone, not runtime service health.
Dashboard, durable graph resumption and autonomous website navigation are not
required for this checkpoint and are not implemented. CrewAI remains checkpoint 6.

## Ollama local-model option

Added a local Ollama planner using the shared structured plan contract, fixed
localhost endpoint, bounded context/output and no cloud-provider fallback.
The supported starting models are qwen3:8b and qwen3:4b. The setup guide includes
disabling Ollama cloud features, GPU checks and explicit model downloads.
Local inference requires neither an OpenAI key nor the paid-API permission flag.
Offline adapter tests and a mocked-Ollama real-tool integration are included;
the existing opt-in semantic and full-workflow evaluations support either provider.
No model has been downloaded or real Ollama inference verified at implementation
time. Checkpoint 5 remains pending those evaluations and user review.

Repository verification: `pytest --run-browser --run-nats` completed with
182 passed and 13 skipped (the opt-in real-model evaluations). The mocked local
adapter exercised the actual browser/storage/NATS workflow. Ruff lint and
format checks and Git whitespace validation passed. One existing upstream
Starlette/AnyIO deprecation warning remains. No inference, commit or push occurred.
