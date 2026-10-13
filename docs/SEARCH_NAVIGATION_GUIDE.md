# Checkpoint 3: reviewed dynamic search navigation

Implementation is ready for user-run verification, not certified for every website.
Both LangGraph and CrewAI use the same navigation and capture code. Restricted
and explicitly confirmed normal networking remain unchanged. No tests, browsers,
sign-ins or paid calls were run by the assistant for this checkpoint.

## Purpose-aware search correction (October 8)

See [Hotel search verification](HOTEL_SEARCH_VERIFICATION.md) for the shortest manual
check. Normal networking remains the dashboard default; this correction changes
form understanding and action validation, not browser networking or data storage.

- The former exact-request fallback ignored calendar opener controls. It could paste
  a structured hotel request into a generic-looking destination field, then stop
  before Search because other requirements were unconfirmed. This fallback is no
  longer permitted for structured hotel requests or forms with widget controls.
- Search planning now receives bounded independent field metadata, purpose and
  current date values, not just one display label. It does not receive credentials,
  raw form text or private frame URLs. A generic label can be recognized as a
  destination using its placeholder or local dated-form context.
- Values are checked against their field purpose and explicit request. Missing
  years remain unresolved, not guessed. Supported full English/ISO dates and
  explicit ranges are grounded independently of the model response. Destination
  preparation and widget opening remain separately approved intermediate steps.
- Submission-capable plans have a feasibility check **before any fields change**,
  followed by live value checks immediately before Search. A partial step may
  change a field but never claims that search was submitted. Both kinds preserve
  evidence and pending criteria in the dashboard.
- Read-back supports separately labelled full dates and two explicit, ordered full
  dates on a combined widget. Abbreviated full-date calendar options are supported;
  visible calendar controls take priority over unrelated background controls.
- The review shows field purpose, exact values/options, missing information and
  remaining site criteria. Correcting missing request values requires a new browser
  session; merely replanning retains the original request.

The planning prompt is `site-search-navigation-v5`. It still uses one explicitly
consented call per proposal and at most five reviewed actions; there is no extra
automatic paid call, retry or autonomous navigation loop. Both agent frameworks use
the same code. Schema-valid output is not proof of correct field interpretation,
as explained in the [official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Capture regression correction

Playwright's omitted evaluate argument becomes JavaScript null. The shared DOM
collector now accepts null, and browser capture explicitly passes an empty options
object. The dashboard and extension copies remain identical. Capture errors no
longer imply the browser failed to launch: sanitized stage/code diagnostics are
retained. A recoverable capture failure leaves the original tab open so the user
can inspect it and explicitly retry. Raw driver exceptions are not displayed,
because they may contain URLs, DOM content or credentials. No engine fallback or
automatic retry was added. Browser cleanup cannot replace a captured result with
a misleading shutdown error.

## Workflow

1. Restart the dashboard; hard-refresh the page (Ctrl+F5 on Windows). If using the
   extension, reload it so the collector update is active.
2. Open Custom Website, supply the URL and complete request, choose the browser
   and networking mode, confirm authorization and paid API consent, then start.
3. Inspect the original browser tab. Complete login/consent/verification manually
   where needed. Wait until the intended form is visible.
4. Choose **Suggest search actions**. Review every proposed control, value and
   coverage description before **Run these search actions**.
5. Read **Search action evidence**. Fill/select operations report the actual value
   read back. A mismatch stops all later actions. A click reports an action, not
   proof of successful search or matching records.
6. If the step opened a search box, date picker, autocomplete suggestion or calendar
   month, inspect the new UI and request another plan. Each proposal is a separate
   paid call and each action sequence needs a fresh approval; no autonomous loop.
7. Requested site requirements declared by the planner must be confirmed in visible
   search fields before submission. Unconfirmed fields stop the submission. Price
   or rating requirements can be explicitly deferred to extraction when the site
   has no corresponding controls; they are not reported as applied website filters.
8. After submission, inspect destination, dates, guest count, currency, rating scale
   and result records in the original tab. The report records page/content changes
   and visible record elements, but does not prove that the server honored filters.
9. Capture the results page, or approve relevant detail links for enrichment. Review
   source evidence and extracted filters, save the preview and download exports.

## What is supported

- Supported text/search/date/number inputs and select controls, including accessible
  names supplied through aria-labelledby.
- Read-only date inputs and clearly labelled search/calendar opening buttons.
- Explicitly labelled next/previous-month controls inside a calendar/dialog.
- Exact autocomplete options and fully dated calendar options (ISO date attributes
  or full English dates including year). Calendar choices must match a declared
  requested check-in/out date. Undated day numbers are not guessed.
- Same-origin embedded search forms and open shadow roots; a changed frame/control
  identity invalidates the old proposal. Old inventory handles are removed when
  the next inventory is created.
- At most five actions per proposal, forty controls and eight same-origin frames.
- Twenty most recent action reports in browser diagnostics, persisted with the
  proposal/snapshot. The dashboard shows the latest report and prior steps.

Credentials/payment fields are excluded from navigation planning. Only values
from supported visible search fields are included in the paid planning request.
Do not put confidential information in these fields or in the request unless your
organization approves sending it to the configured provider.

## Verification commands (you run these)

First, offline regressions; the local browser fixtures will be skipped:

```powershell
uv run --locked pytest tests/test_navigation_verification.py tests/test_browser_navigation.py tests/test_source_inventory.py tests/test_dashboard_ui_structure.py -v
```

Then opt-in, isolated browser fixtures with Chromium installed. These fixtures
fulfil their own local pages: no external websites or paid model calls:

```powershell
uv run --locked pytest tests/test_navigation_verification.py tests/test_source_inventory.py --run-browser -v
```

Manual smoke checks:

- Fox/BBC or another authorized source: current-page capture proceeds past content
  preparation, with no null-options error. Open a search overlay, replan for the
  revealed field and verify the entered query. Submit and inspect results before
  extraction. Headlines alone are not detail-page context.
- Hotel site: request Boston, explicit future dates, USD 150-250 nightly and your
  rating scale. Approve destination, suggestion and date steps separately when
  needed. Confirm that site fields and results actually match; an unsupported
  datepicker remains a manual step, not a fabricated success.
- Deliberately change a reviewed control or edit a requested date before submission:
  it should stop, show the unmet field/action and require a new plan.
- Keep the browser tab open through capture. For cancellation/closed-tab cases,
  confirm diagnostics distinguish session/capture failure from installation failure.
- Repeat a search and extraction using each framework; compare source evidence,
  coverage, saved records and downloaded files.

The unrelated historical rule/event tests still use outdated catalogue counts;
they were left unchanged at the user's request. This is not a full-suite pass claim.

## Limits / acceptance still required

Structured output is not semantic proof: the planner can omit/misclassify a user
requirement. Human review of the complete request, proposed requirements and results
is still necessary. Form read-back checks the visible values, not the server's
interpretation. Price units, tax basis, rating scales and date associations must be
verified from captured source data. Requirements that a dynamic widget exposes only
as a combined/localized label may remain unconfirmed and need manual entry or a
dedicated connector. No universal datepicker, pagination, CAPTCHA/MFA automation,
access-control bypass, screenshot-based navigation or production-readiness claim.

Official OpenAI documentation informed the separation between a schema-valid
proposal and independently checked browser evidence:
[Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
