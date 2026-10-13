# Browser agent — LangGraph first

This is the new dynamic browser path, not the deterministic **Complete hotel
search** driver or the one-step **Suggest search actions** planner. The agent uses
the original request and current page to choose one action, execute it, inspect
the outcome and continue automatically. There are no website-specific form
recipes in this agent. Normal/restricted networking remains your separate choice.

## Start a run

1. Restart the dashboard after updating the code, then hard-refresh (Ctrl+F5).
   Browser-agent UI version: `2026-10-10.1`. No new dependency installation is needed.
2. Configure your own account's model/API key. Choose **Custom Website**, the
   **LangGraph** framework and **Browser** source. Enter the website and full task.
3. Select your browser/networking mode and any sign-in option. Open the website.
   If sign-in/MFA is required, finish the existing sign-in handoff first.
4. In **Let the browser agent do the task**, read and check the paid-call consent,
   then click **Run browser agent · paid API**. This authorizes the retrieval task
   once; routine browser actions do not require individual approvals.
5. Watch the original Chromium/Chrome/Edge window and dashboard activity. Expand
   **Browser-agent action evidence** to see actions, observed values and errors.
   Expand **Search readiness** for requested versus observed form values. Opening
   a date/occupancy widget does not mark those fields verified. An attempted early
   finish is rejected and fed back to the agent; repeated premature finishes pause
   instead of sending the wrong page into paid extraction.
6. When source collection is ready, the existing extraction/validation pipeline
   runs automatically. Review the preview, criteria, missing fields and evidence.
   Approve the snapshot to save it, then download CSV/Excel/JSON/JSON Lines.
   Configured business rules and optional events still run through shared services.

## What the agent observes and can do

- Visible DOM text and interactive controls, including option subtitles, calendar
  buttons, native fields, dropdown options, selected state and nearby counter text.
  Foreground dialogs/options are prioritized over background navigation.
- Paired counter buttons expose the nearby row label, current count and direction
  when accessible labels or simple rendered plus/minus SVG artwork identify them.
  This includes deeply nested icon-only occupancy steppers without a dialog role.
  After a counter click, action evidence shows the expected one-step count and
  observed count. An unchanged/missing count is unconfirmed, not success. Unknown
  artwork is not interpreted by assuming that the right button increases a value.
- Fresh control references on every iteration. The model chooses actions; browser
  tools enforce the reference identity and report read-back or unknown outcomes.
- Literal hotel destination/resolved dates/adults/rooms are retained in a sticky task
  checklist. The model can declare additional request-quoted form or extraction
  requirements; it cannot silently drop known fields. Search requires form
  read-back; completion also requires an observed Search page transition. That
  transition is NOT independent proof that every result satisfies the request.
  Slow searches remain pending and can confirm on a later observation without a
  second submit. Small ad/text changes alone do not confirm a results transition.
- Native and decorated Search actions, including Search-with-AI choices, are
  recognized independently of the model's declared action purpose. Required dates
  and occupancy must be read back before submission. Search-form widgets are
  prioritized over background links in the DOM inventory. Unexpected navigation
  while form values remain unconfirmed pauses instead of treating a city catalog
  as a completed stay search. The browser is not automatically sent back/restarted.
- Repeated no-progress checks use control/checklist state rather than changing
  page ads. Repeated premature Search attempts pause without clicking. Action
  diagnostics include control type, submission semantics and pending form fields.
- In the browser-agent and Complete hotel search paths, English dates without a year use the computer's current
  year only if both endpoints form a valid stay starting today or later. The resolved
  dates/year are disclosed in the dashboard and checklist. Past, invalid or
  year-crossing ranges require explicit years; there is no next-year rollover.
  This default applies to user instructions, never to captured source dates.
- Recognized occupancy rows expose their current quantity and increase/decrease
  controls separately from age-description numbers. `set_counter` takes the exact
  requested target and checks every step (at most ten steps per action, six seconds).
  It stops if a click has no effect or the control changes. After changing counts,
  the agent must confirm/close the widget and verify the committed form summary.
- Initial browser handoff waits for useful DOM for at most 1.5 seconds after
  DOMContentLoaded rather than waiting up to eight seconds for ads/media to finish.
  Launch/navigation/readiness timings appear in page-loading details. This does not
  guarantee faster network/browser launch; capture still has its own stability checks.
- Navigation observations are compacted to a bounded context, with omitted
  controls/text disclosed. Full references remain internal for tool checks; final
  source captures are not shortened by this navigation optimization.
- A result capture can carry a separate, page-bound `browser_task_context` for
  verified pre-submit form values and the observed Search transition. Extraction
  can describe that search scope without inventing record-level availability,
  dates, prices or quotes. Source blocks remain the evidence for listing fields.
- Click, literal fill, native select, checked counter setting, limited keys, scrolling, brief waiting and
  source capture. Same-origin links can be followed in the existing session/tab.
- Up to one retained index and five detail captures, or bounded standalone/result
  captures. Repeated identical URLs are not captured again. Different search states
  sharing the same URL are not separately archived in this first version.

This checkpoint is **DOM/text-based**, not visual computer use: no screenshots are
sent. Closed shadow DOM, opaque cross-origin frames, custom canvas controls and
popup-tab workflows may require user assistance or a later vision/tool extension.
The browser tools are generic, but that is not a guarantee every website works.

## Pauses, limits and costs

- At most **30 navigation decision calls** and **300 active seconds**, followed by
  the separately disclosed extraction call. Each decision can incur API usage.
  Retries are disabled for navigation inference. The provider may charge an
  attempted call even if it fails. Token totals are reported when supplied.
- Resuming keeps the same original request, action history, captured pages and
  used budget. These are in-memory continuations, not durable graph checkpoints.
  Waiting for user input is excluded from the active agent budget; the enclosing
  browser session still expires after ten minutes. An in-flight browser operation
  or network timeout can delay cancellation and the time-limit check.
- MFA/password/code fields and access challenges pause before another agent call.
  Finish them yourself, then renew consent and **Resume agent**. No inbox access,
  CAPTCHA bypass, payment, reservation or website account changes are implemented.
- If needed, **Continue manually** restores existing collection/search choices.
  **Extract retained captures** can produce a clearly marked partial preview; it
  does not claim the original task was completed. No final records are saved until
  you approve the preview. Cancel closes the session without launching extraction.
- The model receives bounded visible content/control metadata. Known supplied
  login credentials and sensitive form fields are excluded/redacted. Review the
  browser first; this is not a general-purpose confidential-data classifier.

## Manual acceptance scenarios

### Hotel search

Website: `https://www.booking.com/`

> Find hotels in New York with check-in 2026-10-28 and check-out 2026-10-30 for
> 3 adults and 2 rooms. Extract name, listing URL, price, currency, price basis
> and guest rating. Keep listings priced 250–350 USD per night when that basis
> and currency can be verified; explain unavailable or incompatible prices.

Verify it selects **New York, United States of America**, not **Search with AI**;
opens/operates the date and occupancy widgets; submits Search; and captures
actual result content. Compare form summaries and exported prices against the
website. If the website shows total-stay prices or a different currency/rating
scale, it must not silently treat them as the requested units.

### News/details

Website: `https://www.bbc.com/news`

> Find soccer-related stories. Open up to 5 relevant story links and extract the
> actual headline, source URL, author and publication date if available, plus a
> source-backed excerpt. Retain the useful index page for comparison.

Verify URLs are really visited and captured, not merely copied from index cards.
Unavailable author/date fields should stay blank. The source-backed extraction
path currently favors quoted excerpts rather than unrestricted generated summaries.

### Negative and recovery cases

- Omit the hotel year for a future current-year stay: verify the disclosed resolved
  dates in the checklist and browser. Use a past or year-crossing range: the agent
  should ask for explicit years before a paid decision. Correcting
  the original task requires a new session; manually setting a value can help only
  if you subsequently review what the agent observes and intends to do.
- Open a visible MFA/password page: no navigation model call before user handoff.
- Cancel during inference: the returned decision must not cause a browser action.
- Fail a control action: the next decision should inspect the fresh observation,
  not blindly replay the action or submit a duplicate search.
- Reach the call limit: resuming must not reset the paid-call count.
- Retain sources then pause: extract only those sources and require partial approval.
- Choose CrewAI: this first browser-agent option is unavailable; existing CrewAI
  flows remain unchanged. Port the agent loop only after LangGraph acceptance.

## Tests for you to run

### Counter and calendar regression (browser-agent-v4)

When the occupancy popup opens but no counts change, an opening click is not
evidence of a populated form. The agent now records the selected control, target,
requested counts and detected counter rows for `set_counter`, including failures.
A unit-labelled absolute target such as `3 adults` is accepted only when it
matches the original requested Adults count. A clearly labelled row or the
opposite stepper button can resolve to a unique, fresh, same-frame counter in the
required direction. Mixed summaries, duplicate rows, unrecognized artwork and
conflicting targets are not guessed. Each click still requires count read-back.

Pending full-year calendar dates are supplied as exact control choices. Month
navigation is not performed when a requested pending date is already visible.
The agent receives the date and control ID instead, then observes again.

Restart the launcher after code updates; refresh alone does not reload Python.
Cancel the old session and use a new session. The report should show
`prompt_version: browser-agent-v4`. This fixes demonstrated validation/feedback
paths; live Booking.com acceptance remains a manual test, not a claimed result.

Offline/mocked decisions (no paid calls, no live websites):

```powershell
uv run --locked pytest tests/test_browser_agent.py tests/test_browser_task.py tests/test_browser_startup.py tests/test_dashboard_ui_structure.py -v
```

Opt-in isolated local browser/UI fixtures (still no live websites or paid calls):

```powershell
uv run --locked pytest tests/test_browser_agent.py tests/test_browser_task.py tests/test_browser_agent_ui.py tests/test_complete_hotel_search.py tests/test_hotel_autocomplete.py tests/test_navigation_dashboard.py tests/test_dashboard_ui_structure.py --run-browser -v
```

Then run the manual acceptance cases above. Static checks are not evidence that
live Booking.com or BBC navigation succeeds. No live run was performed at implementation.

## Next checkpoints

The dynamic observation/binding and consented visual-assistance checkpoint is
implemented in [Dynamic browser agent](DYNAMIC_BROWSER_AGENT_GUIDE.md). Use that
guide for `browser-agent-v5`, cross-domain fixtures and manual acceptance. Earlier
counter/calendar fixes remain supporting tools, not a universal navigation recipe.

1. User acceptance of the LangGraph loop: hotel widgets, source capture, MFA and costs.
2. Fix demonstrated live shortcomings; evaluate screenshot/vision tools where DOM
   evidence is insufficient and compare an existing browser-agent library if needed.
3. Implement equivalent CrewAI browser-agent orchestration with the shared tools;
   publish a comparable acceptance report. Do not call a CrewAI Flow alone a team
   of autonomous agents.

The OpenAI Docs skill informed the structured decision adapter: the model returns
a typed action, but schema conformance does not establish its semantic accuracy.
References: [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [LangGraph workflow/agent distinction](https://docs.langchain.com/oss/python/langgraph/workflows-agents).
