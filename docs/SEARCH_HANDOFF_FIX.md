# Search-to-results handoff

Implementation checkpoint: 2026-10-14. Live verification remains with the user.
No tests, static validation commands, browser runs or API calls were run for this
checkpoint.

## The failure

The latest user1 Booking.com job (`d29f7c77-9f95-4b49-8b3d-5a182595b392`)
verified New York's destination suggestion, both dates, three adults and two rooms.
The runtime selected the actual Search submit button. A browser error occurred
around the post-submit observation and the agent paused without capturing sources.

Submission tracking was created only after the resulting page was read. A browser
read failure could therefore erase evidence that Search had been attempted. The
ten-minute expiry was a later consequence of the pause, not its initial cause.
The old trace did not retain the precise browser exception; a navigation-context
race was plausible, not proven.

## The correction

- Record Search dispatch intent after fresh form/control checks, before the risky
  interaction. An attempt is **not** proof the click ran or results arrived.
- Retain an attempted-but-unconfirmed response across browser read failures and
  resume. Recovery must not click Search again or restart the model-call budget.
  A known pre-dispatch rejection is labelled separately and cannot be confirmed
  by later unrelated navigation. Review that control or start a fresh session.
- Passively reread the page for bounded, recognized transient navigation errors.
  Other browser errors pause with an actionable category. Cancellation, sign-in,
  access restrictions, origin checks and active-time budgets still apply.
- Confirm the observed Search transition, then wait for rendered records or a
  confirmed empty response. Only then can the existing capture/extraction flow
  finish. A changed URL alone does not prove listing availability or pricing.
- Show and persist the error category, operation and recovery outcome. Raw browser
  exceptions, URLs, page text, credentials and screenshots are not diagnostic fields.

The agent reports `browser-agent-v18.1`. Frontend and backend UI versions both
advance to `2026-10-14.1`. The configured model, price/source validation, normal
networking and final review-before-save are unchanged.

## Your manual walkthrough

1. Cancel the old session. Stop/restart the launcher, then hard-refresh the
   dashboard with Ctrl+Shift+R. Confirm the UI version above and start a fresh job.
2. Open Booking.com in Website Studio with LangGraph, Normal networking and
   automatic collection. Choose your usual sign-in preference and consent.
3. Use a consistent request:

   > Find hotels in New York with check-in October 29, 2026 and check-out October
   > 31, 2026 for 3 adults and 2 rooms. Include hotel name, listing URL, displayed
   > price, currency, price basis and guest rating.

4. Observe destination selection, dates and occupancy. Search should run once,
   without your manual click. The agent must not refill fields or submit again
   while awaiting its response.
5. After the page loads, expect collection followed by extraction and review in
   the same job. Check source URLs, prices and evidence before saving. A transient
   recovery should appear in diagnostics without an additional paid decision.
6. If the agent pauses, inspect the displayed browser category and operation. A
   pending Search must remain visible. Once the existing results are loaded,
   explicitly resume; it should inspect that response rather than repeat Search.
   Do not resume a changed form, different website, access warning or closed tab
   as if it were the same result page.
7. Repeat with `Keep hotels priced between 250 and 350 USD nightly, inclusive.`
   Requested bounds must remain present. Ambiguous totals/basis remain read-only
   source previews, not verified nightly matches. This handoff change does not
   infer missing prices or divide totals by nights/rooms.
8. Approve a verified preview, save, then download Excel or CSV. No records should
   be saved or published merely because Search was attempted or recovery failed.

Use future dates if following this guide later. Keep the launcher open while the
job runs. Old jobs are not rewritten by deploying this correction.

## Optional regression commands you run

The new fixtures use synthetic tools and do not call a model or external website:

```powershell
uv run --locked pytest tests/test_search_handoff.py tests/test_submission_scope.py tests/test_collection_goal.py tests/test_browser_agent.py -v -ra
```

Existing local fixture-browser checks can be enabled separately:

```powershell
uv run --locked pytest tests/test_navigation_verification.py tests/test_unified_workflow.py tests/test_unified_workflow_ui.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Neither command was executed during implementation. Share the new job's action
evidence and browser diagnostics if a live run still stops after Search.
