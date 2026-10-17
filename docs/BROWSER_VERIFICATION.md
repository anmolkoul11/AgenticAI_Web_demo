# Keep the source browser open for verification

Implementation checkpoint: 2026-10-15. Manual verification pending. No tests,
static validators, application imports/startup, browsers or model calls were run.

## New default

After successful capture, the original managed Chromium/Chrome/Edge window stays
open. Extraction, preview, review, saving and downloads continue independently.
The window is for manual inspection at this point; the agent no longer runs there.

Use **Verify in your browser → Close browser**, or close the original window
yourself. This closes only that verification browser, not extraction or saving.
The control remains available when you switch Source/Workflow/Results, select
another job or save results into a separate execution job.

Before capture, **Cancel & close browser** keeps its original cancellation meaning.
After handoff, a legacy Cancel request closes the verification browser without
cancelling processing. New agent/search/capture commands are rejected in the
verification phase; a new extraction requires a new run and its normal consent.

## What remains unchanged

- Captured source text, timestamps, fields and evidence form a frozen snapshot.
  Manual browsing, changing site filters or later live price changes do not update
  the preview or exports. Start a new run to obtain fresh data.
- No extra model calls, screenshot capture or automatic collection occur while
  waiting for verification.
- The chosen normal/restricted networking mode stays in effect. Existing browser
  or restricted-proxy connection/budget failures can still close a session.
- The ten-minute collection deadline and paid-agent limits are unchanged. The
  verification phase is not limited to whatever remains of collection time.
- Verification ends on explicit close, original-tab/window closure, dashboard
  sign-out/session expiry or revocation, or server shutdown/restart. No additional
  short review timeout was added; the existing fixed one-hour account session
  remains the outer lifetime.
- Cookies remain in this session's temporary browser context until cleanup; they
  are not exported or saved as a reusable login profile.
- Public HTML, pasted text and extension captures do not open a managed browser,
  so this lifecycle change does not create windows for those source methods.

Source collection runs on a tracked browser-owner thread. That thread owns all
Playwright calls, network/proxy resources and cleanup. One deep-copied snapshot
is delivered to the job worker, which is free to finish and accept Save/new jobs.
Threading does not move live Playwright objects into the extraction/API threads.
Owner cleanup removes the browser control; closing after handoff never replaces
already handed-off data with a late browser error.

## Restart

Restart the usual launcher, hard-refresh the dashboard with **Ctrl+Shift+R**, and
start a new browser workflow. Both frontend/backend report `2026-10-15.2`.
Browser agent remains `browser-agent-v20.1`; extractor/collector are unchanged.
Already running sessions keep the code they loaded and cannot be converted by
resuming them. Existing saved results are not rewritten.

## Manual verification scenarios

1. Run a hotel/news extraction. When preview appears, confirm the original source
   window is still open and compare at least one name, URL, price or quote with it.
2. Switch to Results, open a record preview and save the reviewed records. The
   website must stay open, and the verification Close button must still address
   its original browser job, not the new Save job.
3. Change a website filter manually. Existing preview/download values must not
   change; they remain the captured snapshot, not a live data feed.
4. Close the verification window during extraction if you want to check the
   distinction: processing should continue on captured data. An already-started
   model call is not cancelled or automatically retried.
5. Start another job while an earlier verification window is open. The earlier
   window must not hold the extraction job gate or prevent Save.
6. Close the original browser window yourself. Its verification panel should
   disappear on the next light status refresh without failing the captured job.
7. Sign out or stop the launcher. Retained managed browsers should close and the
   next login should not regain an old browser context. Before-capture Cancel
   should still stop collection normally.
8. Repeat current-page, approved-link and agent collection paths, including a
   partial/no-matches preview. Post-capture model/validation errors should not
   immediately remove the page you need to inspect.

## Optional commands for you to run

```powershell
uv run --locked pytest tests/test_browser_review_lifecycle.py tests/test_browser_review_dashboard.py tests/test_browser_login.py tests/test_unified_workflow.py -v -ra
uv run --locked pytest tests/test_browser_review_dashboard.py tests/test_dashboard_live_updates.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Fixtures were authored, not executed. Live websites, cleanup timings, account
handoffs and extraction accuracy remain for your manual verification.
