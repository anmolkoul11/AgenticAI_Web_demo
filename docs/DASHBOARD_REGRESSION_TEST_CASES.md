# Dashboard and Companion regression test cases

These cases cover the simplified dashboard actions and shared logo. They were
written without running tests, starting the app/browser, or making model calls.

## Automated checks to run

Run these commands from `D:\Projects\AgenticAI_Web_demo` in PowerShell.

### Branding and structure

```powershell
uv run --locked pytest tests/test_shared_branding.py tests/test_dashboard_ui_structure.py tests/test_dashboard_compact.py tests/test_extension_panel_contract.py -v
```

This checks shared SVG assets, logo/favicon references, PNG dimensions,
extension permissions, manifest/helper version compatibility and dashboard
markup. Any opt-in browser cases are skipped in this first command.

### Local browser interactions

```powershell
uv run --locked pytest tests/test_dashboard_action_confirmations.py tests/test_dashboard_api_setup.py tests/test_unified_workflow_ui.py tests/test_complete_hotel_dashboard.py tests/test_browser_agent_ui.py tests/test_workflow_review_ui.py tests/test_extension_panel_lifecycle.py --run-browser -v
```

These use isolated local fixtures with mocked API responses. They do not visit
Booking.com, Tripadvisor or news sites, use your key, or make paid model calls.
They require the project's Playwright Chromium installation. If it is missing:

```powershell
uv run --locked playwright install chromium
```

Do not add `--run-model` or `--run-nats` for these checks.

## What the cases cover

| Area | Expected behavior |
| --- | --- |
| Shared branding | Dashboard, side panel and popup reference the same logo; favicons match; toolbar icons have the declared dimensions. |
| Extension access | Logo changes do not expand permissions or site access; packaged helper and manifest versions agree. |
| Start | The explicit button sends one request with the selected mode, screenshot setting and publishing choice. |
| Idle/settings | Opening the dashboard, changing settings or invoking an unrelated submit action sends no workflow request. |
| API setup | Missing keys direct the user to setup; saving a key requires the actual Save action and does not start a task. |
| Duplicate clicks | A pending Start, Save or API-connection request is not submitted again. The original request/revision stays bound. |
| Resume | No repeated permission checkbox is needed; screenshot sharing follows the selected option and does not start on a poll. |
| Reviewed hotel actions | Run sends the displayed hotel plan's exact revision; Search and Search & extract remain separate choices. |
| Complete save | Save enables when a valid preview and revision arrive; no extra checkbox is required. |
| Partial save | Save available results explicitly accepts only that preview's partial status. Nothing saves on rendering alone. |
| Review handoff | Reopening a saved review follows the original execution, including after browser-channel expiry, without renewing browser input. |
| Companion state | Record limit defaults to 50; zero cannot start; saving/saved states stay coherent and stale updates are ignored. |

## Manual checks on the dashboard

Restart the backend, refresh the dashboard, reload Companion **0.5.22**, refresh
the website tab and reconnect. Use the same signed-in dashboard account.

| Case | Steps | Expected result |
| --- | --- | --- |
| M1 Logo consistency | Compare the login page, dashboard header, Companion side panel, popup and toolbar. | The navy a. mark with mint dot appears consistently and is readable at each size. |
| M2 Simple setup | Open Website Studio and inspect the default setup. Open Settings. | No repetitive authorization checkboxes. Optional screenshots/rules stay in Settings; concise paid-AI and browser-access information remains visible. |
| M3 Missing API key | With no key configured, describe a request and choose Start. Add a valid key through API connection. | Setup is shown clearly; no workflow starts until Start is chosen again. |
| M4 New browser workflow | Ask for New York hotels for December 28–30, 2026, 3 adults and 2 rooms. Choose Start AI workflow. | One task starts. The existing search-to-preview behavior is preserved. |
| M5 Companion workflow | Run the same request in your current Booking.com or Tripadvisor tab. | Booking submits Search after edits; Tripadvisor can collect applied same-page results. Both reach the dashboard preview as before. |
| M6 Missing child age | Request hotels for 3 adults, 1 child and 2 rooms, omitting the age. When asked, enter the actual age on the website, apply it and choose Resume. | The agent waits for input, preserves the user's age and continues without another authorization checkbox. |
| M7 Save | Open a fresh complete preview and choose Save results once. Reopen it from Companion/history. | One save attempt and the same saved run/downloads are shown; results do not need saving again. |
| M8 Partial results | Open a fresh partial preview and inspect its coverage note before choosing Save available results. | Partial status is visible. Only available eligible records are saved after the explicit click. |
| M9 News workflow | Ask for sports articles on BBC or NYTimes. | Relevant article records reach preview; games and navigation/section links are not presented as valid article records. |
| M10 Preferences | Change screenshots and event publishing between No and Yes, without starting. | No task starts from changing a setting. The next explicit action uses the chosen values. |

Known intermittent no-progress/false-loop pauses remain tracked in
`PROGRESS.md`. If one occurs, record the action, current website values and
whether Resume recovered it. A successful resume does not close that open bug.

For a failure, share the failed test name and traceback. For manual failures,
include the exact prompt, website, recent activity and visible UI version;
exclude API keys, passwords, cookies and other account secrets.
