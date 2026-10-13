# Browser decision failure fix

## v13 navigation-cost diagnostics

The current browser-agent version is `browser-agent-v13`. `input_chars` measures
the actual compact JSON navigation text; `system_chars` and `schema_chars` are
reported separately. Character counts are not token estimates. Consented images
are adaptive, so `visual_calls_attempted` may be lower than total calls.

`usage.cached_input_tokens` is the API-reported cached subset of `input_tokens`,
not extra input and not assumed free. It follows the provider's returned metadata:
[Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

`performance.phase_seconds` and `phase_calls` distinguish observation, context
projection, screenshot generation, model requests, actions and source capture.
These are measured wall-time intervals, not a benchmark or billing estimate.
`performance.navigation_context` retains per-call text/section character counts
and screenshot-sent flags. Bounded numeric metrics survive job persistence without
retaining prompts, page text, labels, image data or credentials in that diagnostic
field. Full reviewed source/action evidence remains in its existing locations.

Shorter decision responses and up to three requirement declarations per turn
address verbosity; the configured output budget is not increased and an incomplete
response still cannot execute an action. Correct canonical city labels no longer
falsely block Search; a truly incomplete form still must be resolved. Restart and
begin a fresh session before comparing this revision with a v12 trace.

The earlier generic pause did not establish the original cause. An account's
remaining balance does not identify an individual request timeout, rate limit,
incomplete response or invalid action JSON. This change distinguishes them so the
next run provides actionable evidence rather than guessing.

## Implemented changes

- The decision timeout now uses the configured account timeout (60 seconds in
  the dashboard), bounded by the agent's remaining active time. It is no longer
  silently capped at 30 seconds. Injected offline deciders still default to 30.
- Responses are requested with the same strict action schema. The agent checks
  completion/refusal status before parsing action JSON. Incomplete JSON never
  becomes an executable action. This follows the [OpenAI structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
- Failed responses retain reported token usage, including reasoning-token usage
  when available. Failed calls still consume the existing attempted-call budget.
- The dashboard shows the failure code/stage, decision number, effective timeout,
  output-token budget, reported output usage and HTTP status when available.
- Decision-only diagnostics are saved while the browser is still open, under
  `browser_agent_diagnostics` in the job's technical evidence/history. Subsequent
  progress/final writes and restarts retain the latest diagnostics. Restarting
  does not resume a browser agent or reset a running job to queued.
- Diagnostic fields exclude raw response text, refusal/error bodies, credentials,
  prompts, page contents and images. Existing separately reviewed source/action
  evidence is unchanged.

No model, output-token budget, networking mode, provider retry, paid fallback,
sign-in/MFA behavior or browser tool has been changed. This is not evidence that
Booking.com or every website now completes successfully; a fresh run is required.

## Completed response rejected at the first decision

The inspected v6 run had two completed responses in about 5–8 seconds, with
959 and 939 output tokens and zero reported reasoning tokens. Both failed local
validation. It was not an incomplete output-limit response or a request timeout.
The exact field is not recoverable from the old diagnostics, which omitted it.

Revision v7 fixes a separate, concrete parsing defect: the SDK's `output_text`
convenience property concatenates all assistant text, including intermediate
commentary. The adapter now reads output items and selects the explicit
`final_answer` message, or one unphased message for models without phases. It
never executes commentary as an action or concatenates final outputs. Revision
v8 refines multiple-message handling as described below.
This follows the [official message-phase guidance](https://developers.openai.com/api/docs/guides/reasoning#phase-parameter).
The old logs do not establish whether commentary caused that particular run.

Schema failures now retain up to eight schema-owned field paths and validator
codes, such as `requirements.0.expected (string_type)`. Unknown property names
are replaced with `unexpected_field`. Raw values, validator messages, context,
response contents and screenshots are not retained. These details appear directly
in the browser-agent status and survive in its existing decision diagnostics.
Regression fixtures now represent real output messages instead of just a synthetic
aggregate `output_text` string.

## Observation incorrectly treated as a human handoff (v8)

The latest inspected v7 job had two separate problems. Decision 1 contained two
final messages and was rejected as `ambiguous_output` without a browser action.
After an explicit user resume, decision 2 was valid JSON but chose `pause` merely
to request a fresh view of a date picker. No timeout or output-limit failure was
reported. Raw output was not retained, so whether the first messages were
identical, conflicting or progress prose plus JSON cannot be reconstructed.

- Final messages are now independently validated. A unique schema-valid decision
  can be selected alongside non-JSON progress prose. Identical validated decisions
  are deduplicated and acted on once. Different decisions, unfinished/refused final
  messages and invalid JSON-like alternatives still stop without guessing an action.
  Blocks within one message are not joined into JSON. Counts, not message bodies,
  appear in diagnostics.
- The decision contract has an explicit `pause_reason`. `observation` becomes a
  read-only `inspect` followed by a fresh observation and another budgeted decision.
  It does not invent a click or submission. Two consecutive refreshes with no
  meaningful control/widget change are allowed; a third stops with clear guidance.
  MFA, authentication, access restrictions, missing input and ambiguity still hand
  off to the user. Older injected decisions with no reason retain human-pause behavior.
- Each decision is told that its observation is fresh. After explicit resume from
  a failed decision, safe failure metadata is supplied so the model can correct the
  rejected output instead of receiving the same unexplained state. A successful
  decision clears this failure feedback from the next model payload.
- Transport/provider/schema failures still have no automatic retry. Ordinary agent
  continuation after read-only inspection is not a provider retry and consumes the
  same 30-call/300-active-second budget; screenshot calls keep the existing consent.

The OpenAI Docs skill informed the distinction between normal loop continuation
and an actual stop/handoff: [Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents).
This is still the local LangGraph loop, not a migration to the OpenAI Agents SDK.

## Tests for you to run

From `D:\Projects\AgenticAI_Web_demo`:

```powershell
uv run --locked pytest tests/test_browser_decision_diagnostics.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_task.py tests/test_dashboard_ui_structure.py -v -ra
```

These fixtures use mocked HTTP responses and no paid API calls. Local browser
cases are intentionally skipped without `--run-browser`. To include them and the
dashboard diagnostic display checks:

```powershell
uv run --locked pytest tests/test_browser_decision_diagnostics.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_task.py tests/test_browser_agent_ui.py tests/test_navigation_dashboard.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

The implementation author did not execute either test command or a live run.

## Repeat the manual scenario

1. Cancel the old browser session. Stop and restart the demo launcher; refreshing
   the dashboard alone does not reload Python. Dashboard version: `2026-10-12.1`.
2. Open Custom Website with your selected networking/browser mode and
   `https://www.booking.com/`. Finish any sign-in or MFA yourself.
3. Use this complete request:

   > Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 for
   > 3 adults and 2 rooms. Include hotel name, listing URL, displayed price,
   > currency, price basis and guest rating.

4. Authorize the browser agent. Its status must show `browser-agent-v12`.
   Screenshot consent remains optional; use the same setting as the failing run
   for the first comparison. Starting/resuming makes paid requests.
5. If it pauses, share the failure code, the new `Validation:` line and
   `browser_agent_diagnostics` from the
   technical evidence. Do not share keys, cookies, credentials or screenshots
   containing account information. Inspect the original browser before Resume.
6. If it reaches results, check dates and occupancy in the site's rendered form
   and review listing evidence before saving/downloading. Model completion alone
   is not proof of exact availability, price basis or source accuracy.
7. An observation-only refresh should continue without pressing Resume. A real
   MFA or missing-information handoff must remain paused. Check that call counts
   rise within the existing budget and that no premature Search or save occurs.

## Interpreting a pause

| Code | What it identifies | Next action |
| --- | --- | --- |
| `timeout` | Request exceeded its effective timeout | Check the displayed timeout; no account-balance diagnosis is implied. |
| `output_limit` | Provider reported the per-response output-token limit | Share the budget and output/reasoning usage; review a budget change before another paid attempt. |
| `rate_limit` | Provider returned a rate limit | Wait and inspect usage/rate limits; this is not evidence of depleted credits. |
| `quota` | Provider explicitly returned `insufficient_quota` | Check API billing/account access. |
| `authentication` | Provider rejected credentials/access | Check this local user's configured connection without exposing its key. |
| `request_invalid` | Provider rejected request/model/schema/image compatibility | Share code and HTTP status; consider a separately consented DOM-only comparison if image-related. |
| `invalid_decision` | Completed text was not valid action-schema JSON | No returned action was executed; share the safe diagnostic metadata. |
| `ambiguous_output` | Conflicting final decisions or multiple text blocks | No arbitrary action was selected; share the safe message/decision counts. |
| `refusal`, `content_filter`, `incomplete` | Provider declined or stopped generation | Do not treat partial output as an action or retry automatically. |
| `browser_timeout`, `browser_error` | Browser observation/action failed | Inspect the tab; a click may have occurred even if later verification failed. |
| `internal_error` | Unexpected local processing error | Share stage/diagnostics; do not assume this was a provider quota issue. |

Existing task/user-input pauses remain distinct from model failures. Resuming
retains the action history, previous failure diagnostics and used call/time budget.

The v10 run with 28 valid model responses stopped after Search because `finish`
contradicted its separate completion flag, not because of quota or output limits.
In v11 that redundant flag is removed: `finish` requests source capture and the
existing extraction handoff. Real unmet form/submission checks still reject it.
See [DYNAMIC_BROWSER_AGENT_GUIDE.md](DYNAMIC_BROWSER_AGENT_GUIDE.md#search-results-to-extraction-v11)
for focused regressions and the manual results-to-preview check. Earlier rejected
finishes do not carry across actual form/search progress or explicit Resume.

For occupancy/control failures, v10 also retains a bounded `counter_diagnostics`
object: standard tag/role/type, recognition and ARIA-value-presence flags, and
child-button counts. It does not save actual field values, labels or raw DOM in
that field. See [DYNAMIC_BROWSER_AGENT_GUIDE.md](DYNAMIC_BROWSER_AGENT_GUIDE.md)
for the revised quantity fixtures and manual checks. Older v9 failures lacked
this structure evidence; do not claim their exact widget markup is known.

In v12 `input_chars` adds a bounded numeric measure of decision text payload size,
without retaining the text. The browser session owns/reuses its HTTP client and
schema; explicit session exit closes the client, but a pause does not. Request
timeouts still honor the remaining active budget and errors never retry themselves.
Model feedback history is compacted separately from full dashboard action evidence.
See the v12 section of [DYNAMIC_BROWSER_AGENT_GUIDE.md](DYNAMIC_BROWSER_AGENT_GUIDE.md)
for destination dropdown acceptance and performance comparison checks.
