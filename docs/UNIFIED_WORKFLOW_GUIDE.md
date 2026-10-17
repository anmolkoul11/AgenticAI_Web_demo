# Run a website workflow (v1.2)

The main Website Studio path is **Run workflow**. It reuses the existing
LangGraph browser agent and extraction pipeline, rather than running all the
manual collection tools in sequence or adding a separate paid routing call.

## Main path

1. Choose **Open a website**, enter one HTTPS URL and describe the information
   you need. Include search values and business filters in the same request.
2. Choose whether sign-in is needed. Automatic sign-in uses the credentials you
   supply; email codes, MFA, CAPTCHA and account verification remain manual.
   A requested manual sign-in waits for your confirmation before automation.
3. Review browser networking and paid API consent. Screenshots are optional and
   have their own consent. Click **Run workflow** once.
4. The browser observes the live page, prepares and verifies necessary fields,
   submits a search when ready, and collects current results or relevant linked
   detail pages according to your request. Extraction, evidence checks and query
   filters follow in the same job. No second collection button is needed.
5. Inspect the preview, missing fields, source evidence and any partial coverage.
   Then approve and save the snapshot using the existing review controls. Final
   saving is deliberately not automatic. Excel, CSV, JSON and JSON Lines downloads
   use saved records and do not call the model again.

The managed website browser now stays open after capture and extraction for direct
comparison. **Verify in your browser** provides a separate **Close browser** action,
including after saving or selecting another run. Closing it does not cancel
processing or change the captured snapshot. Sign-out, session expiry and shutdown
close retained windows. See [BROWSER_VERIFICATION.md](BROWSER_VERIFICATION.md).

Optional business rules and event publishing keep their existing explicit
settings. A preview is not a saved run, and a broker acknowledgement is not
proof that a consumer processed an event.

## When the run pauses

The run does not automatically resume a human handoff or silently refresh its
budget. Inspect the browser, complete the requested step, then explicitly resume
or continue manually. A pause during a model call takes effect when that call
returns, before the next browser action; that attempted call may incur usage.
Cancel closes the workflow instead of saving an incomplete snapshot.

Budgets remain 30 paid browser decisions, five active minutes and six captured
pages (a starting page plus at most five details). Navigation uses compact live
control context; final extraction uses the separate full captured sources, not
the trimmed navigation payload. Captures and evidence checks do not prove that
every website record, stay availability or price basis is complete.

## Advanced and manual alternatives

Select manual collection under Settings when you want to choose each step. The
separate tools are under **Advanced tools**, not extra required workflow stages:

| Tool | What it does |
| --- | --- |
| Run browser agent | Observes, acts and checks repeatedly until source collection is ready or a handoff is needed. |
| Suggest search actions | Proposes a small, reviewed action plan for the current visible controls; it is not a complete autonomous run. |
| Find relevant links | Proposes links for your review, then captures the selected pages plus the starting page. |
| Extract current page only | Captures the current page without opening linked details. |
| Prepare complete hotel search | A separate no-model form recipe for supported hotel controls, not the generic browser agent. |

Current-page and linked-page outputs can differ because their captured sources
are different. The main agent chooses the collection depth within the same
run; it should not invoke these paid alternatives redundantly.

Autonomous browsing currently uses **LangGraph**. CrewAI remains available for
the manual extraction/save orchestration, and browser-extension capture, public
HTML and pasted text remain existing non-autonomous source paths. The app does
not silently change a selected framework. Unknown layouts, access restrictions,
ambiguous controls or missing source values can still require your attention.

## Verification you run

Restart the launcher and refresh the dashboard. Both frontend and backend should
report UI version `2026-10-15.2`; new agent sessions report `browser-agent-v20.1`.
Cancel old sessions before comparing runs. The implementation author has not run
tests, opened browsers or made paid API calls for this checkpoint.

See [SEARCH_HANDOFF_FIX.md](SEARCH_HANDOFF_FIX.md) for the latest correction to
attempted Search tracking and passive recovery during navigation. Recovery does
not repeat Search or make another model call.

See [PRICING_SCOPE_FIX.md](PRICING_SCOPE_FIX.md) for independent returned-stay
checks, combined-nightly/average/per-room price labels and approximate preferences.
New extraction/capture versions are v13/v4 respectively. A prepared form alone
does not make a catalogue price a requested-stay quote.

The latest [dynamic-field workflow](DYNAMIC_FIELDS_GUIDE.md) infers usable columns
from the request and captured content, omits empty inferred fields, preserves
explicit missing fields and follows detail links only when needed and permitted.

The shared submission/capture corrections and focused verification scenarios are
in [SOURCE_WORKFLOW_FIXES.md](SOURCE_WORKFLOW_FIXES.md). Ordinary relevant-headline
requests start on the supplied page; request searching or linked detail context
explicitly when needed. Unverified nightly pricing is a read-only source preview,
not a matched result.

```powershell
uv run --locked pytest tests/test_unified_workflow.py tests/test_collection_goal.py tests/test_unified_workflow_ui.py tests/test_browser_agent.py tests/test_browser_task.py tests/test_browser_context.py tests/test_browser_optimization.py tests/test_dynamic_browser_agent.py tests/test_browser_agent_ui.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Then check these live scenarios on sources you can access:

- Hotel results: `Find hotels in New York with check-in October 29, 2026 and
  check-out October 31, 2026 for 3 adults and 2 rooms. Include hotel name, listing
  URL, displayed price, currency, price basis and guest rating. Keep hotels
  priced between 250 and 350 USD nightly.` Check committed destination, dates,
  occupancy, actual Search results and a preview without another collection click.
- Linked content: `Find relevant sports content. Open relevant headline links
  and include the headline, source URL and a short source-backed excerpt.` Check
  that actual detail pages are captured, not just index snippets.
- Current content: `Extract the names, links and displayed prices visible on
  this page only. Do not open linked pages.` Check that no detail navigation runs.
- Human handoff: request sign-in, finish MFA yourself and explicitly continue.
  Check no paid browsing begins during sign-in, and Pause/Resume does not reset
  calls or repeat an uncertain Search submission.
- Manual mode: enable it and verify the separate actions remain usable. Check
  CrewAI and browser-extension/public/pasted sources do not start the LangGraph
  browser loop automatically.

Compare navigation usage, model-decision count and measured phase timings in
technical evidence. There is no promised live step count, speedup, accuracy or
token saving until these runs are verified.

This design follows the single-agent-first, stable outer-workflow approach in
[OpenAI orchestration guidance](https://developers.openai.com/api/docs/guides/agents/orchestration).
