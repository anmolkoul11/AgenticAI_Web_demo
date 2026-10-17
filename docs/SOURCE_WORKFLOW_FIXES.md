# Search and source-capture checkpoint

Implementation: 2026-10-13. Live acceptance remains pending. This is a shared
browser/extraction correction, not a Booking.com or Fox-specific connector and
not model fine-tuning. The configured model and account settings are unchanged.

The subsequent [Search handoff correction](SEARCH_HANDOFF_FIX.md) adds attempted
submission tracking and bounded passive observation recovery after Search. Use
its recovery walkthrough. [Returned-stay pricing](PRICING_SCOPE_FIX.md) is the
latest checkpoint for current versions and price-verification scenarios. The
original 2026-10-13 capture behavior below remains historical context.

[Dynamic fields and needs-driven collection](DYNAMIC_FIELDS_GUIDE.md) supersedes
fixed-column behavior and includes the subsequent pricing correction.

## What changed

- **Real Search:** closing a calendar or occupancy widget is not a search,
  regardless of the model's action label. A ready form proceeds to its actual
  submit control. Search evidence records the action and observed response;
  typing a query alone does not establish submission.
- **Collection depth:** an ordinary request for relevant headlines or visible
  records starts with the supplied page. Explicit search values allow form
  automation; explicit requests to open links or get detail context allow linked
  pages. These instructions use the existing agent call, not another paid router.
- **Richer capture:** coherent record bundles retain names, links and numeric
  price/rating details before less useful descriptions. Long tracking queries
  no longer consume most of the capture allowance. Bounded record identifiers
  remain in evidence URLs; omitted identifiers are disclosed, not guessed.
  Opened article bodies take priority over recommendation cards. Browser
  navigation still uses the actual live links.
- **Source checks:** a URL quoted incorrectly by the model can be corrected only
  when the captured record uniquely binds that exact URL to its identity.
  Ambiguous or uncaptured links are not manufactured.
- **Requested criteria:** explicit price/rating comparisons have a separate
  coverage check. The model cannot silently omit a recognized requested bound.
  Currency, nightly basis and rating scale must have source support. Unsupported
  criteria are counted separately from unrelated or out-of-range records.
- **Useful failure states:** unresolved criteria can show a read-only,
  source-verified preview with raw displayed prices and links. It is not a matched
  result and cannot be saved, downloaded or published. Capture failures show a
  specific diagnostic and pause rather than repeating model decisions. A real,
  confirmed empty search avoids a paid extraction call.

The collector still has bounded text, record and page coverage. Normal networking
remains the default; sign-in/MFA, consent, review-before-save and paid-call budgets
are unchanged. No bypass, extra framework or model upgrade was added.

## Restart and check versions

1. Cancel old browser sessions and stop/restart your usual launcher.
2. Hard-refresh the dashboard (Ctrl+Shift+R). Frontend and backend must both show
   UI version `2026-10-14.3`; a new agent session reports `browser-agent-v20`.
3. New extraction calls report `website-extractor-v13`. New captures report
   `source-inventory-v4`; older payloads remain supported.
4. If using the page-capture extension, reload it in Chrome/Edge's extensions
   page, then refresh the source tab. Its collector matches the browser collector.

Old jobs and saved exports are not rewritten by restarting. Compare new runs.

## Tests you run

No tests, browsers or paid API calls were run by the implementation author for
this checkpoint. Static syntax, formatting and source-contract checks are separate
from runtime verification.

Focused regression checks:

```powershell
uv run --locked pytest tests/test_submission_scope.py tests/test_record_capture.py tests/test_extraction_contract.py tests/test_capture_diagnostics.py tests/test_source_workflow_ui.py --run-browser -v -ra
```

Then the existing workflow checks:

```powershell
uv run --locked pytest tests/test_unified_workflow.py tests/test_collection_goal.py tests/test_browser_agent.py tests/test_browser_task.py tests/test_browser_context.py tests/test_browser_optimization.py tests/test_dynamic_browser_agent.py tests/test_navigation_verification.py tests/test_detail_enrichment.py tests/test_topic_evidence.py tests/test_custom_website.py tests/test_dashboard_ui_structure.py tests/test_dashboard_live_updates.py tests/test_unified_workflow_ui.py --run-browser -v -ra
```

`--run-browser` enables local fixture-browser cases; it does not authorize a real
website or paid model run. Check the skip summary before assuming complete coverage.

## Live checks

### Hotel search first, then price selection

Use Booking.com, normal networking and **Run workflow**, with this unfiltered
request first:

> Find hotels in New York with check-in October 29, 2026 and check-out October 31,
> 2026 for 3 adults and 2 rooms. Include hotel name, listing URL, displayed price,
> currency, price basis and guest rating.

Verify the destination suggestion is committed, both dates and occupancy match,
Done closes the widget, and **Search actually runs without your click**. Verify
that results are captured and a preview follows without another collection button.
Check at least three names, prices and URLs against the visible results, including
whether prices are stay totals, per-room or per-night and include taxes.

Start another run with the same request plus:

> Keep hotels priced between 250 and 350 USD nightly, inclusive.

Both bounds must remain visible in criteria diagnostics. Records qualify only
when source evidence supports the amount, currency and nightly basis. If the site
only exposes multi-night totals or an unclear basis, expect a labelled read-only
source preview, **not** a successful nightly match. This checkpoint does not divide
totals by nights/rooms or guess taxes. Unknown criteria must not be called
out-of-range, saved or published. A verified subset needs partial-result review.

Use dates still in the future if running this guide later. Explicit check-in/out
dates take precedence over an inconsistent stated number of nights.

### Starting-page headlines

At `https://www.foxnews.com/`, use:

> Find articles related to sports. Include the exact headline and its URL from
> the current page.

Expect collection from the supplied page, no section/search wandering. Compare
exact titles and URLs with the page. Some source-supported records may still be
unrelated to the request; missing relevant content is a coverage issue, not proof
that the entire website has no matches. Repeat with soccer and check the relevant,
unrelated, uncertain and invalid counts separately.

### Linked details explicitly requested

At Fox or BBC, use:

> Find relevant sports headlines on this page. Open up to five relevant headline
> links and include each exact headline, URL and a short source-backed excerpt.

Check actual opened detail URLs and body evidence, preservation of starting-page
records, failures/partial coverage and no unsupported URL repair. Current-page and
linked-detail outputs can differ because their source coverage differs.

### Failure and recovery

- Confirmed empty search: a real submit plus a non-loading empty response gives
  a clear no-matches outcome; no extraction charge or saved run.
- Capture failure: a specific capture code appears in action evidence; the agent
  stops once instead of repeatedly calling capture/finish.
- Unresolved pricing: source preview is readable, but Save and Download remain
  unavailable. Returning to the source/workflow view does not approve the preview.
- Successful verified preview: approve/save, download CSV/Excel, compare fields
  with the preview, and confirm download makes no model call.

Record navigation input/output tokens, decisions and active time for each new run.
Compare like-for-like prompts, screenshot consent and pages with the previous
checkpoint; no token-saving percentage or live speed improvement is claimed yet.

Trace-derived regression cases and concise corrected action examples follow
[OpenAI's agent-evaluation guidance](https://developers.openai.com/api/docs/guides/agent-evals).
