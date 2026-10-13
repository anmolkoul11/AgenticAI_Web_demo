# Compact workspace

October 8, 2026. UI version 2026-10-08.1. Restart the dashboard and hard-refresh
with Ctrl+F5. Backend extraction, approvals, credentials, networking and event
delivery behavior are unchanged; this checkpoint changes presentation/navigation.

Website Studio now has three task surfaces:

1. Source: collection method, address, request, sign-in choice and required permissions.
   Framework, output fields, browser engine/networking, limits and rules are in Settings.
2. Workflow: live browser actions, progress, review and approval. Preview results opens
   the Results surface. Scope/field/filter details, warnings, rejected-record details
   and technical diagnostics are collapsed but remain available.
3. Results: cards/table, individual record preview and downloads after saving.
   Back to review and Back to source setup keep the selected run and form entries.

Only one surface is visible, with the compact progress strip shared above it. On desktop
the checkpoints use one row; smaller screens wrap them. Arrow keys/Home/End navigate
the task tabs. Polling never switches the surface, opens a disclosure or scrolls the
page. Starting/selecting a run explicitly opens Workflow; results do not steal focus.

Workspace tabs (Hotel demo, Run history, API connection, etc.) start at the top instead
of scrolling down to their heading. Background message updates no longer scroll.
Optional controls are not deleted or automatically approved. Required normal-browser
permission and paid API consent remain visible. Invalid fields open their settings
disclosure so they can be corrected.

Running rings are always animated; the motion selector and its handlers are removed.
Idle, waiting/review, failed and completed stages still stop spinning. This supersedes
the earlier On/Off/device-setting instructions in the extraction consistency guide.
Reduced-motion CSS still disables nonessential transitions, but no longer disables
the running status ring. Textual status remains alongside every indicator.

## User-run verification

The assistant ran syntax/lint checks only, not tests, browsers or model calls.

```powershell
uv run --locked pytest tests/test_dashboard_ui_structure.py tests/test_dashboard_live_updates.py tests/test_dashboard_compact.py -v
uv run --locked pytest tests/test_dashboard_live_updates.py tests/test_dashboard_compact.py --run-browser -v
```

Browser tests use local fixtures and do not visit websites or call models.

Manual checks:

- Sign in: Source is visible, Settings is closed, no animation preference is offered.
- Switch workspace tabs after scrolling: each starts at the top, with navigation visible.
- Configure an authorized demo: browser settings and output fields still work; permission
  checkboxes remain required. No defaults or permissions are silently changed.
- Start a run: Workflow appears; only the actual running checkpoint rotates. Change
  task tabs while work runs: updates do not pull you back or move your viewport.
- Review preview records, return to Workflow and approve; inspect saved downloads.
- Open Settings, scope, warnings, source evidence and record issues when needed.
- Try a narrow window: tabs/controls remain usable, and checkpoints wrap rather than
  forcing the whole page sideways. Expanded optional panels can still require scrolling.
