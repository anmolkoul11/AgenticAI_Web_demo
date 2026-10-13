# Dynamic browser-agent checkpoint

## Current checkpoint: useful decisions instead of retry loops (v14)

The supplied v13 run used all 30 paid decisions with no Search submission or
captured page. Thirteen decisions were rejected for request-quote validation;
four `select` attempts targeted custom controls, not native selects. Optional
bindings also targeted destination options/calendar cells instead of the fields
whose values must be checked, discarding valid selection/date evidence.

Revision v14 changes these contracts without increasing budgets or changing models:

- Already-grounded, unchanged requirements do not need a model-generated quote
  again. Canonical dates can differ from original human wording. Known optional
  bindings can use an empty quote; normal actions should use `requirements=[]`.
- New requirements still need a real request quote/interpretation. Changed known
  values/applications are rejected. A declaration batch commits atomically, so an
  invalid later declaration cannot partially install fields or bindings.
- A known destination/date value cannot be rebound to a suggestion, calendar
  choice or widget opener. Redundant invalid binding metadata is ignored; the
  actual action still needs a fresh, valid target and real source read-back.
- Current controls include `supported_actions`/`action_hint`: native `SELECT`
  uses `select`, custom options use `click`, text boxes use `fill`, and counters
  take absolute requested values. No wrong action is blindly converted to a click.
- `interaction_focus` suggests completing visible pending values in the current
  widget before switching. Its IDs must exist in the projected current inventory.
  It cannot invent a Done control or prove a value was set.
- After an autocomplete fill, a bounded read-only observation interval (up to
  1.1 seconds plus observation overhead) can wait for stable changed suggestions,
  without spending a model decision, choosing a city or repeating the fill.
  Unsettled suggestions are marked pending. Cancellation/MFA still stop the loop.
- Three consecutive ungrounded/invalid declarations pause rather than burning
  the rest of the paid budget on metadata errors. Other model/call/time limits,
  context caps, source capture and human approval remain unchanged.

OpenAI Docs informed clearer action schemas and reusing values already known by
the application: [Function calling best practices](https://developers.openai.com/api/docs/guides/function-calling).
This remains the existing LangGraph/Playwright runtime, not a hosted-agent migration.

### Verify v14

Restart the launcher, cancel old browsers and begin a fresh session that reports
`browser-agent-v14`. No frontend version bump is needed for these backend changes.
The author ran static checks only, not tests, browsers or paid model calls.

```powershell
uv run --locked pytest tests/test_browser_task.py tests/test_destination_selection.py tests/test_browser_context.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_decision_diagnostics.py tests/test_browser_optimization.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Use this unambiguous request for the next live comparison:

`Find hotels in New York with check-in October 29, 2026 and check-out October 30,
2026, for 3 adults and 2 rooms. Include hotel name, listing URL, displayed price,
currency, price basis and guest rating. Keep hotels priced between 250 and 350 USD
nightly.`

Those dates mean one night. For two nights use October 29–31; the user's earlier
two-night/29–30 wording was inconsistent, separate from the wasted metadata calls.

The new offline fixture specifies a ten-decision fill → committed city → dates →
occupancy → Done → Search → source-capture path, asserting at most fifteen decisions.
It has **not been run by the author** and is not a promise that the live website
always needs that exact number. Popups, delayed rendering and MFA can add work.
Check that the next live run avoids quote-rejected known fields, custom `select`
errors, repeated widget toggles and refilling an already committed destination.
Then verify actual Search results, extraction preview and reviewed save/export.

## Current checkpoint: lean navigation and completed search (v13)

The v12 live trace selected the correct New York option but the website expanded
the input to `New York, New York, United States of America`. The old exact-short-name
check rejected it, so Search never ran. v13 verifies the actual selected option's
full words/order, ignoring presentation punctuation only. It does not accept a
prefix, an unselected city string, an airport/AI option or stale selection proof.
Blocked internal Search decisions now say Search was not clicked.

Navigation and source extraction have different context needs:

- Each navigation decision gets the original request, compact field readiness,
  fresh relevant control IDs/options/dates/counters, and three brief recent results.
  Its JSON text payload is bounded to 14,000 characters, with at most 8,000 for
  observations. These are character limits, **not token counts**; fixed system
  instructions, response schema and any image are additional API input.
- Requested values/instructions are not shortened. Required visible field/date
  controls cannot be silently lost. Other omitted text/controls/options are counted
  explicitly; lexical link priority is navigation assistance, not relevance proof.
- Full source capture, evidence validation, result filtering, preview, approval,
  save and downloads remain separate and unchanged. Navigation trimming must not
  be used as the final extraction source or as proof that omitted content is absent.
- Optional screenshots are generated only for unfamiliar/ambiguous/stalled states,
  not every DOM-sufficient step; identical layouts are not repeatedly sent. The
  same consent, masking and human authentication handoff remain in place.
- Decision descriptions are shorter; at most three new/alias requirement
  declarations per decision, while the ledger can retain sixteen requirements
  across decisions. Known values normally need no redeclaration. The configured
  model, 1,200-output-token setting, call/time budget and no-retry behavior are unchanged.

OpenAI Docs informed the context and output-size choices:
[Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).
Image token behavior varies by model, so this change skips unnecessary images
rather than assuming that `detail=low` always costs less:
[Images and vision](https://developers.openai.com/api/docs/guides/images-vision).
Response streaming alone would not remove input tokens; these requests remain
self-contained rather than relying on hidden conversation memory.

### Verify this checkpoint yourself

Restart the launcher and refresh the dashboard. Cancel old browser sessions;
the new session must show `browser-agent-v13`. The author ran static checks only,
not these tests, browser sessions or paid requests.

```powershell
uv run --locked pytest tests/test_browser_context.py tests/test_browser_optimization.py tests/test_destination_selection.py tests/test_occupancy_commitment.py tests/test_browser_agent.py tests/test_browser_task.py tests/test_dynamic_browser_agent.py tests/test_browser_decision_diagnostics.py tests/test_browser_agent_ui.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Then try: `Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30
for 3 adults and 2 rooms. Include hotel name, listing URL, displayed price,
currency, price basis and guest rating. Apply a nightly price range of 250–350 USD.`

Check the selected city option, full dates and committed occupancy, actual Search
submission/results, source capture, extraction preview and saving/downloading.
Saving still requires your review; automation does not prove site completeness or
exact availability. Test another destination/count and a generic news/product task
to check that context trimming does not impose hotel behavior on other sites.

Compare fresh runs using `usage`, `decision_diagnostics.input_chars`, and
`performance.phase_seconds`/`phase_calls`/`navigation_context` in technical evidence.
The dashboard shows navigation input/output and cached-input counts; extraction
usage is separate. Cached input is included in input, not added to total and not
assumed free. No measured savings or speedup is claimed until your live comparison.

This extends the existing LangGraph browser agent; it does not add site-specific
Booking.com/BBC recipes or guarantee every website. CrewAI's autonomous browser
loop is still a separate parity checkpoint. Existing collection, source review,
approval, storage, rules and downloads remain in use.

## What changed

1. The model discovers form requirements from the request and live controls.
   It can bind a semantic field such as `topic` to a website's `q` input using a
   fresh control ID. Runtime reads the actual field value; the model cannot
   mark a requirement verified just by asserting success.
2. A meaning-preserving interpretation such as soccer → football must include
   the original request quote and an explanation. The dashboard labels it as a
   model interpretation. This is not a deterministic guarantee of semantic accuracy.
   Existing literal stay values remain unchanged; missing criteria are not invented.
3. Each action gets before/after feedback: changed values, expanded widgets,
   new controls, scrolling and document transitions. Advertising/body-text churn
   does not count as form progress. Failed actions return that feedback for replanning.
4. The agent can focus inspection on forms/dialogs, operate checkboxes, editable
   text, native selects and observed quantity steppers, and return to a previously
   observed same-site page. Open shadow-root controls are included in the inventory.
5. An optional screenshot mode supplements DOM observations using the same
   configured model and existing decision-call budget. Fresh control IDs and
   CSS-pixel rectangles accompany an unlabelled screenshot. No text labels are
   injected into the user's webpage. No new model/provider is selected.

## Start and verify

1. Run the local fixture tests below yourself. No hosted model or external site
   is contacted by those fixtures.
2. Cancel the previous browser session, stop the launcher with Ctrl+C, then run
   `scripts/Start-Demo.ps1` again. Refresh the dashboard. Python is not reloaded
   by merely refreshing the page. UI version: `2026-10-12.1`.
3. Choose Custom Website, enter the URL and your request, and open the browser.
   Review the rendered page and finish any required sign-in/MFA.
4. Under “Let the browser agent do the task,” authorize the paid action loop.
   For unfamiliar layouts, optionally authorize viewport screenshots separately.
   Screenshot input can incur extra image-token costs and reveal page/account
   information. Use it only with pages you are authorized to send to your model.
5. Run the agent. The status should show `browser-agent-v12` and its observation
   mode. Open Browser-agent action evidence to see changes and newly discovered
   controls. A successful click is not proof that a field or business rule is met.
6. Review the extracted preview, rules and source evidence before saving. Download
   CSV/Excel/JSON using the existing export controls. Images are not export evidence.

On Resume, screenshot consent can be renewed or left unchecked to return to
DOM/text. Neither Resume nor a mode change resets the run's call/time budget.
If the configured model rejects image input, the run pauses rather than silently
switching models or retrying a paid request; inspect settings or resume in DOM mode.

## Search results to extraction (v11)

The inspected v10 Booking.com run finally read back destination, both dates,
3 adults and 2 rooms. Search produced a later observed page transition, but the
model chose `finish` without its separate completion flag. The runtime rejected
that contradictory combination before retaining a page, so extraction never ran.
An earlier premature finish also counted toward that later pause.

- `finish` is now the single capture-and-handoff action. The redundant
  `completion_status` property is removed from the model action schema.
- Required form values and an observed Search response still gate the handoff.
  An unchanged Search click, unconfirmed occupancy, visible sign-in/MFA, access
  restrictions, cancellation or failed capture cannot become a successful result.
- Finishing captures the rendered source and uses the existing extraction,
  source validation, query filtering and human review stages. The navigation
  agent must not first compile the final filtered hotel list. Source readiness
  does not prove exact availability, nightly price basis or website completeness.
- Rejected finishes count against an unchanged state, not the whole run. Form/
  submission progress, document/widget changes and explicit Resume reset that
  rejection streak; scrolling or unrelated controls alone do not. None of these
  reset the paid-call or active-time budget.
- No model, decision budget, networking mode, browser engine or provider retry
  has changed. Repeated full observations and screenshots remain a separate
  performance checkpoint. No live speed improvement is claimed yet.

The OpenAI Docs skill informed the single stopping/handoff contract, following
[Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents).
This remains the local LangGraph runtime, not an SDK or provider migration.

Run the focused mocked regressions yourself:

```powershell
uv run --locked pytest tests/test_browser_task.py tests/test_browser_agent.py tests/test_browser_decision_diagnostics.py -v -ra
```

Then cancel the old session, restart the launcher and start a new browser session
showing `browser-agent-v11`. Use an unambiguous stay request, for example:

> Find hotels in New York with check-in 2026-10-29 and check-out 2026-10-31 for
> 3 adults and 2 rooms. Include hotel name, listing URL, displayed price, currency,
> price basis and guest rating. Keep only hotels priced from 250 to 350 USD nightly.

Those dates are two nights; October 29-30 is one night. Do not combine conflicting
nights and dates in the request. Verify occupancy/dates before Search, then check
that at least one source page is retained and the workflow reaches extraction and
review. Matching record count can legitimately be zero. Review price basis and
source evidence before saving/exporting; missing values must not be invented.
The implementation author has not run pytest or the live scenario.

## Destination selection and lightweight decisions (v12)

The next user run entered stay dates/occupancy but did not choose a destination
from the site's suggestions. Source inspection found that both bound and unbound
destination read-back accepted matching typed text alone. That is not enough for
an autocomplete form that requires a committed location.

The shared v11 diagnostics identified another blocker: closing the occupancy
popup removed its bound inputs/buttons. The checker then reported adults/rooms
pending instead of reading the committed 3-adult/2-room header. Search was blocked
before execution. The agent spent 42.2 active seconds on 13 decisions, then paused;
the browser later reached its separate ten-minute wall-clock session expiry.

- Editable autocomplete fields now expose field-associated fresh option IDs and
  an explicit accessible name or first rendered text line for each option.
  The destination stays pending after typing;
  the model must choose the matching option, not an airport/park/AI-search variant.
- A successful associated choice must be followed by matching field read-back and
  a closed suggestion widget. Dismissing the widget without a choice is not proof.
  Retyping, including the identical text, invalidates the remembered selection.
  Plain text fields/native selects keep their existing read-back behavior.
- No arbitrary first-match choice or Booking-only location identifier is used.
  Ambiguous/missing relationships or unsupported widgets still need user attention.
- When a bound occupancy control disappears after the popup closes, the same
  document/frame's visible summary can supply fresh read-back. Old counter values
  are not retained as proof; stale/conflicting/absent summaries remain unconfirmed.
- One owned OpenAI/HTTP client is reused for the browser session, including pauses,
  then closed on session exit. Each request still uses its current remaining-time
  timeout and zero retries. Different sessions/users never share that client.
- The strict action schema is built once per decider. The model receives up to
  eight compact action summaries (6,000 characters maximum) instead of twelve
  full audit entries and repeated stale control inventories. Full dashboard action
  history and final source capture are not truncated by that model-only projection.
- `input_chars` in safe decision diagnostics records text payload size, not its
  contents. Compare attempted calls, input tokens and total elapsed time in new
  runs; static checks do not establish a measured live speedup.
- A session expiry now includes the last paused-agent reason. Wall-clock browser
  expiry is distinct from active agent runtime or the provider request timeout.

The OpenAI Docs skill informed bounded context and reduced repeated setup following
[Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).
The configured model, screenshot consent/detail, networking and call/time budgets
are unchanged. Dependent browser actions remain serial and use fresh observations;
no blind batching, provider fallback, reservation or payment is added.

Run the focused offline/local fixtures yourself (no external websites or paid calls):

```powershell
uv run --locked pytest tests/test_destination_selection.py tests/test_occupancy_commitment.py tests/test_browser_task.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_decision_diagnostics.py --run-browser -v -ra
```

Cancel the old browser session, restart the launcher, refresh the dashboard and
start a new session showing `browser-agent-v12`. Repeat the v11 dated hotel prompt.
Check that it types New York, then clicks the correct city suggestion, then prepares
dates and occupancy before Search. Matching text alone must not mark destination
verified. The flow should retain a results page and reach extraction/review, or
report an actual capture/extraction issue rather than claim a final verified list.
Share action evidence and safe diagnostics if it stops; do not repeatedly resume an
unchanged unsupported control. Live accuracy and performance await your verification.

## Privacy and operational boundaries

- Images are viewport-only, kept in memory, and not written into jobs, traces,
  saved records, exports or a screenshot directory. API requests use `store=False`;
  this is not a promise about the provider's separate retention policies.
- Known credential fields/secret text are masked. A visible password or code
  screen stops image capture. Masking is not comprehensive personal-data detection:
  review the browser yourself and do not expose confidential page/account data.
- Screenshots help choose fresh DOM control IDs; arbitrary pixel actions, generated
  scripts, canvas interaction, closed shadow roots and arbitrary cross-site tabs
  are not implemented. Some custom widgets still need another tool/connector.
- The existing human sign-in/MFA and access-restriction handoffs remain. Network
  mode is unchanged. No reservation, payment, website posting or downloads are added.
- Navigation feedback establishes UI changes, not website completeness, exact stay
  availability, price basis, currency conversion or model interpretation correctness.

## Tests for you to run

For decision failures, response-status checks and safe run diagnostics, see
[BROWSER_DECISION_DIAGNOSTICS.md](BROWSER_DECISION_DIAGNOSTICS.md).

An observation-only request now continues through read-only inspection instead
of asking you to Resume. Genuine user-input/MFA handoffs remain paused. Inspect
action evidence for automatic refreshes and bounded no-progress pauses; this does
not guarantee that a site's dates, counters or results can always be operated.

## Counter widgets and visual flicker (v9)

The changes below describe v9. The next user-run attempt revealed false-positive
review-card counters and missing semantic quantity support; see the v10 revision
below. Passing static checks was not live acceptance evidence.

The inspected v8 run verified destination and both dates, but exposed no usable
Adults/Rooms steppers. The requested counts were correctly present in its task
checklist; the failure occurred in observation/resolution before a counter click.
The exact live DOM was not included in the log. Generic detection has been revised
to cover clickable row wrappers containing nested buttons and SVG symbol references:

- Keep the actual leaf buttons, not just an enclosing `role=button` row. Associate
  their rendered count/label without excluding all text inside that wrapper.
- Read same-document SVG reference names/titles alongside existing icon geometry;
  external sprites are not fetched. Direction is never assigned from left/right order.
- A structurally clear quantity row with unfamiliar icons can expose `unknown`
  directions. The model must choose a specific fresh actuator ID; the tool does not
  choose arbitrarily from a row label. Each click must produce exactly the next
  numeric step toward the requested target, otherwise the action stops. Disabled,
  ambiguous, detached and unchanged controls do not establish success.
- Screenshot capture no longer adds temporary ID text to the live document. CSS
  screenshot scale aligns with the accompanying control rectangles. Consent, MFA
  checks, credential masks, byte limits and in-memory-only image handling remain.
  Credential masking can still briefly obscure sensitive fields during capture.

The OpenAI Docs skill informed the observation/action separation, not a model
upgrade or new computer-tool integration: [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use).

Run these local fixtures yourself (no external websites or paid calls):

```powershell
uv run --locked pytest tests/test_counter_widgets.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_task.py tests/test_browser_decision_diagnostics.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

For a new live browser session, repeat the dated New York request with 3 adults and
2 rooms, then vary it to 4 adults/3 rooms and 1 adult/1 room. Verify visible counts,
the committed header and dates before Search. No fixed `3`/`2` targets are coded.
The run should show leaf steppers in counter evidence and no flashing ID text.
Cancel/restart if an old browser session still reports v8. Live success remains
pending your verification; universal website support is not claimed.

## Numeric controls and false-positive counters (v10)

The v9 trace correctly verified destination and dates but labelled hotel cards'
review counts as steppers. These were background carousel controls, not occupancy
fields. The agent repeatedly attempted `set_counter` on unrelated controls. The
actual occupancy element's tag/role was not retained in that older run, so its
precise structure cannot be proven from the text log alone.

- Unknown-direction pairs now require an isolated, compact quantity region; card
  headings, links, images and surrounding review text cannot establish a counter.
- Native number inputs and named ARIA spinbuttons are recognized from their actual
  value/attributes. `set_counter` uses ArrowUp/ArrowDown and checks every numeric
  step, observing minimum/maximum, readonly state and the existing bounds. It never
  assigns values through injected JavaScript. This follows the [W3C spinbutton
  pattern](https://www.w3.org/WAI/ARIA/apg/patterns/spinbutton/).
- Recognized, physically rendered +/- buttons may remain usable when marked
  `aria-hidden` for accessibility. That annotation does not mean CSS-hidden.
  CSS-hidden, inert, credential and unrelated accessibility-hidden controls remain
  excluded. Numeric displays can provide read-back for their sibling buttons.
- Counter evidence now shows selected tag/role/type and visible/accessibility-
  hidden child-button counts. Bounded structure-only diagnostics survive in
  `browser_agent_diagnostics.counter_diagnostics`; labels, actual values, raw DOM,
  page text and screenshots are not added to that persisted field.
- Diagnostic-only probes are omitted from compact model control observations so
  they do not displace calendar/widget controls from the existing context budget.

The OpenAI Docs skill informed the updated action description and the separation
between model decisions and verified tool effects: [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use).
This remains the existing local LangGraph/Playwright runtime and configured model;
it does not switch to a hosted browser, a different model or generated-code execution.

Restart the launcher, refresh the dashboard and start a new session showing
`browser-agent-v10`. Test the original request, including explicit dates and
3 adults/2 rooms, then vary counts and check the committed occupancy header before
Search. If it still stops, share the `Control structure:` line, counter evidence
and the bounded structural diagnostics—not credentials, cookies or raw account DOM.
Do not repeatedly resume an unchanged unsupported widget and spend more calls.

```powershell
uv run --locked pytest tests/test_counter_widgets.py tests/test_browser_agent.py tests/test_dynamic_browser_agent.py tests/test_browser_task.py tests/test_browser_decision_diagnostics.py tests/test_browser_agent_ui.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

These regressions use local fixtures/mocked transport, not live Booking.com or
paid API requests. The implementation author did not run them. The actual site
still needs manual verification; keyboard semantics alone do not guarantee an
application implements them correctly or that the returned listings are available.

Offline/mocked tests:

```powershell
uv run --locked pytest tests/test_dynamic_browser_agent.py tests/test_browser_agent.py tests/test_browser_task.py tests/test_dashboard_ui_structure.py -v
```

Local browser/UI fixtures, still no external websites or paid model calls:

```powershell
uv run --locked pytest tests/test_dynamic_browser_agent.py tests/test_browser_agent.py tests/test_browser_task.py tests/test_browser_agent_ui.py tests/test_navigation_dashboard.py tests/test_dashboard_ui_structure.py --run-browser -v
```

## Prepared form to results handoff (v15)

For a literal hotel-listing request, once every requested form value is verified
in a uniquely associated native form and its widgets are closed, the runtime uses
that form's actual Search button. It rechecks the form immediately before clicking.
This is not a Booking.com selector recipe or a catalogue-link substitution. It then
waits passively for up to five seconds for rendered records or an explicit empty
result. A confirmed result document is captured for the existing extraction and
business-rule review flow without another model decision to choose Search/finish.
The action history labels these terminal operations `decision_origin: runtime`;
`calls` still counts paid model decisions, not local browser actions.

Unsupported/ambiguous forms remain model-led. Requests explicitly asking to open
linked hotel detail pages continue model-led collection rather than finishing at the
listing index. Sign-in/MFA, cancellation, changed values, unconfirmed Search and busy
results stop for attention. Search is not automatically repeated after uncertainty.
An unrecognized result layout falls back to the existing model-led collection path,
within the same paid-call budget; a missing structural hint is not proof of failure.
Read-back, submission and structural result hints are not proof of availability,
nightly price basis, taxes or completeness; those still require captured source evidence.

Restart the launcher, refresh the dashboard and start a new browser session showing
`browser-agent-v15`. Use a consistent one-night request for this verification:

> Find hotels in New York with check-in 2026-10-29 and check-out 2026-10-30
> for 3 adults and 2 rooms. Include hotel name, listing URL, displayed price,
> currency, price basis and guest rating. Keep hotels priced 250-350 USD nightly.

Check the actual Search click, stay-specific result URL/header, retained source page,
preview and download after your approval. A displayed stay total must not be silently
treated as a nightly price. If no matching prices are source-supported, inspect the
review explanation rather than expecting fabricated records. Compare paid calls,
actual token usage and active phase timings with v14; no live savings are claimed.

```powershell
uv run --locked pytest tests/test_browser_task.py tests/test_browser_context.py tests/test_browser_agent.py tests/test_browser_optimization.py tests/test_browser_decision_diagnostics.py --run-browser -v -ra
```

These use local fixtures/mocked transport, not paid model calls or external websites.
The implementation author did not run them. OpenAI Docs informed keeping known
terminal operations in runtime code: [Function calling](https://developers.openai.com/api/docs/guides/function-calling).

## Manual acceptance matrix

### Autocomplete and smaller navigation calls (v16)

Start a new session showing `browser-agent-v16`; existing in-memory sessions retain
their old request/agent. Empty or wrong destination text now requests a fill rather
than claiming it is already typed. Matching uncommitted text distinguishes closed
suggestions, loading/no choices, and fresh owned options. The agent still reviews
city/airport/park/AI choices; there is no fixed New York target or arbitrary first pick.
Known literal fills in actual editable native forms can run locally, with a fresh
preflight/read-back. Unavailable/uneditable/ambiguous controls remain model-led.

Form-navigation requests use a smaller target view (6,500 JSON characters, including
3,500 observation characters) when required evidence fits. Otherwise they fall back
to the existing 14,000/8,000 bounds. Original task/expected values and fresh required
IDs are never silently shortened; full source capture for extraction is unchanged.
Regular browsing retains relevant links/text. Geometry accompanies actual consented
images only, and packing diagnostics stay local instead of being resent to the API.
The same model, strict action schema, consent and call/time budgets remain in use.

Run the local fixtures yourself:

```powershell
uv run --locked pytest tests/test_destination_selection.py tests/test_browser_context.py tests/test_browser_optimization.py tests/test_browser_task.py tests/test_browser_agent.py tests/test_browser_decision_diagnostics.py --run-browser -v -ra
```

Then repeat the consistent one-night New York request above. Check:

- Fill or committed destination read-back, then the intended city suggestion.
- Dates/occupancy read back, actual Search, rendered stay results, preview and export.
- No repeated opener clicks, no retyping a verified canonical destination.
- `performance.navigation_context`: actual `text_chars`, local `packing.tier`,
  and whether geometry/images were sent. Compare total paid navigation calls and
  actual input tokens, not only characters or cached-token counts.

V15's failed example used 14 calls/56,081 navigation input tokens. This is a diagnostic
baseline, not a successful acceptance run. Extraction usage is separate and unchanged
by these navigation reductions. No tests or live calls were run by the author;
measured savings and completion still need your verification. The OpenAI Docs skill
informed this work: [Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).

| Workflow | Request | What to inspect |
| --- | --- | --- |
| Hotel search | Find New York hotels, check-in 2026-10-28, check-out 2026-10-30, 3 adults, 2 rooms. Include listing URLs, shown prices and guest ratings. | All requested fields read back before Search; actual result page captured; price basis/rating scale disclosed. |
| News search | Find soccer stories. Open relevant detail pages and include headline, URL and brief source-supported context. | Widget opens once; search/section choices follow the topic; actual detail URLs opened and captured; headline not replaced with a body quote. |
| Product catalog | Find available laptops priced below USD 1,000. Include name, price, availability and product URL. | Fields inferred from the site rather than hotel schema; no cart/purchase clicks; unknown prices stay blank. |
| Different labels | Search for science using a website whose search field is named q or labelled “Search this site.” | Semantic request field bound to that input; actual value shown; no false claim based only on model prose. |
| Delayed widget | Open a custom filter/popover with dynamic choices. | New controls/expanded state shown; wait/inspect/replan rather than repeated opener clicks. |
| Human handoff | Reach email-code/password verification. | Agent pauses; no screenshot/model decision on the code-entry screen; Resume retains the budget. |

Run applicable cases in DOM and consented screenshot modes on websites you may
access. Compare accuracy, coverage, failures and usage—not just whether the run
shows “completed.” No live acceptance or test execution was performed during
implementation. Universal website support and production readiness are not claimed.

The OpenAI Docs skill informed the image-message integration and action/result
separation: [Images and vision](https://developers.openai.com/api/docs/guides/images-vision)
and [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use).
