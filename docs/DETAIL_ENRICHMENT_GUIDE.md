# Checkpoint 2: retain starting-page records and enrich reviewed detail links

Implementation is ready for **user-run validation**. The assistant did not run
tests, browsers, live sign-ins or model calls for this checkpoint.

## What changed

Previously, **Find relevant links** returned only the selected detail-page
captures. Starting-page evidence was discarded when the browser followed links.
It could therefore lose records that **Extract current page only** had found.

The new flow is:

1. Discover relevant links and review up to five, as before.
2. Capture and retain the starting page before navigating away.
3. Open only the approved detail links. Show each attempt as opening, captured
   or failed. Failed pages do not delete starting-page or successful-page data.
4. Send the starting page plus successful detail captures to **one extraction
   call**. The model emits separate, page-specific records under a shared schema.
5. Validate each row against its own page. Reconcile counterparts by verified
   URL and source-container association, not fuzzy title or topic similarity.
6. Fill missing starting-page fields with verified detail-page values, keeping
   each field's quote, source URL and page-local block IDs. Preserve unmatched
   starting-page records and safely unmerged detail records separately.
7. Apply the user's filters to reconciled records, then enforce Maximum records.
   Query/business rules operate on the resulting reviewed values. No accepted
   records are silently cut to meet the limit.
8. Review and approve the exact preview, then save and download as before.

This applies to news/blog items, property/product listings and other content
with identifiable detail links. Both orchestration frameworks use the same
reconciliation service. **Current page only**, public HTML and extension capture
remain single-capture paths; they do not automatically open detail pages.

## Coverage and conflicting values

The dashboard now shows **Starting page & linked-page coverage** during
collection and in the completed review. Captured pages are labelled starting or
detail pages. Result rows include `record_url` and `detail_status`:

| Status | Meaning |
| --- | --- |
| `enriched` | A verified counterpart was joined; missing fields were filled where available. |
| `not_opened` | No detail page was approved/opened for this index record. |
| `failed` | Its approved detail page could not be captured. |
| `not_extracted` | A capture exists, but no verified counterpart was returned/matched. |
| `detail_only` | A verified detail record could not be safely joined to an index record. |
| `conflict` | Index and detail contain different populated values; review required. |

The starting-page `source_url` is retained for a merged row. **View quotes,
sources & conflicts** identifies each field's actual source. JSON and tabular
exports retain `evidence_sources`, conflicts and row status; nested metadata
appears as JSON text inside CSV/Excel cells. Full JSON also retains the coverage
report. A matching URL verifies association, not the meaning of a model judgement.

Existing populated values are not silently replaced. Alternative detail values
and their quotes are shown as conflicts. If a conflicting field is used by a
filter or rule (for example two quoted prices), both source variants remain
available for evaluation before filtering. Conflicts, failed pages and missing
counterparts or truncated linked captures require explicit partial-result review. This does not
resolve differences in tax basis, stay dates or availability between pages.

## Run these checks yourself

In the repository's PowerShell terminal:

```powershell
uv run --locked pytest tests/test_detail_enrichment.py tests/test_custom_website.py tests/test_capture_handoff.py tests/test_source_inventory.py tests/test_browser_links.py tests/test_topic_evidence.py tests/test_dashboard_ui_structure.py -v
```

These focused tests mock collection and model transport; no paid calls or public
sites are used. The previous checkpoint's real DOM fixtures skip unless you add
`--run-browser`. To include them and other existing browser checks:

```powershell
uv run --locked pytest tests/test_detail_enrichment.py tests/test_source_inventory.py tests/test_browser_login.py tests/test_dashboard_ui_structure.py --run-browser -v
```

For the wider offline regression suite:

```powershell
uv run --locked pytest
```

Do not add `--run-model` unless you intentionally want paid evaluations. No NATS
service is required for these focused, non-publishing tests.

## Manual news/blog acceptance

1. Restart the dashboard with your existing launcher, hard-refresh its tab, and
   sign into your local account. Keep the configured model/credentials unchanged.
2. Open an authorized external index in Custom Website's browser mode. Use the
   network mode you already validated; visually inspect that content has loaded.
3. Request: **Find relevant sports stories. Include headline, exact detail URL,
   available author and a short source excerpt from each opened detail page.**
4. Click **Find relevant links**, review the proposed URLs, and approve a subset.
5. Check the live coverage list: starting page retained; each approved link has
   an attempt/result. Only approved detail pages should be opened.
6. At review, confirm unselected matching index records can remain as
   `not_opened`, with unavailable body fields blank. Confirm opened-page excerpts
   and authors point to the actual detail URL, not the homepage.
7. Compare a separate **current page only** run. The model may still select
   different records between calls, but following details must no longer discard
   the starting-page capture. Review gaps explicitly; do not assume completeness.
8. Approve only verified records (and partial coverage if appropriate), save,
   and download CSV, Excel and JSON. Check sources and row status in downloads.

## Manual hotel/product acceptance

Use an authorized result page and request its names, exact listing URLs,
available prices/ratings and detail descriptions. Approve only a small subset of
property/product links. Confirm unopened listings remain separately identifiable,
descriptions cite their detail pages, and unrelated sidebar records are not
merged. If a detail page changes a quoted price/rating used by your query, inspect
both variants and conflict evidence; do not treat different stay/offer conditions
as interchangeable. Automated search-form improvements are **Checkpoint 3**.

## Remaining limitations and cost

No additional automatic model calls were introduced. The combined extraction
contains more source text, so token usage and cost can increase. Discovery is
still a separately consented call. Each page keeps the existing collection limits;
at most six source pages (one index and five approved details) reach extraction.

The model can omit or reject records. Retaining the capture does not guarantee
it emits every relevant index record. Missing verified counterparts are reported;
they are not manufactured from discovery titles. Only unique URL associations
are merged; ambiguous/missing URLs remain separate. Query-only URL identity,
virtualized/infinite content, pagination and denied access remain limitations.
Cancellation aborts collection and prevents the subsequent extraction call.
If the starting page cannot be captured, no detail navigation is attempted.

The updated prompt retains structured output and application evidence validation,
consistent with [OpenAI's structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs):
schema compliance alone does not establish factual correctness. Model and API
endpoint selection were not changed.
