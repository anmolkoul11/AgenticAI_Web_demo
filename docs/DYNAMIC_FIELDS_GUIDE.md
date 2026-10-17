# Dynamic fields and needs-driven collection

For the subsequent non-blocking optional-metadata fix and current restart versions,
see [COLLECTION_METADATA_FIX.md](COLLECTION_METADATA_FIX.md). That patch is
`2026-10-15.1` / `browser-agent-v20.1`; the table below records this original
dynamic-fields checkpoint, not the latest application patch.

Implementation checkpoint: 2026-10-14. User verification is pending. No tests,
static validation commands, application imports/startup, browsers or model calls
were run while implementing this checkpoint.

## The workflow

1. Interpret the request and use the relevant starting page or completed search.
2. Collect coherent source records: identity, links and their actual details stay
   together. Capture remains bounded; it is not an exhaustive website crawl.
3. Within the existing extraction call, infer useful fields from the request and
   supplied content. There is no fixed article, hotel or product output template.
4. Verify source values and source ownership, then select one consistent set of
   columns for the result. The preview and saved/downloadable dataset use that set.
5. Keep explicitly requested fields even when unavailable, with per-record reasons.
   Keep partially populated inferred fields; omit inferred fields empty everywhere.
6. Review before saving. Calculated prices, rule results and AI relevance decisions
   are distinct from literal source facts.

Field selection uses the existing structured extraction response and local
projection code, not a new paid planning call. The configured model and account
remain unchanged. OpenAI Docs informed the prompt and schema design; structured
output compliance does not establish factual correctness. See
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Collection depth

- A general request for relevant headlines/records starts on the supplied page;
  it does not start an unrelated website search or automatically open every link.
- A hotel request with stay/search criteria completes the form and Search first.
- Explicitly requested body/context, authors, dates or other missing detail
  information can lead to same-site record links, when not already captured.
- Explicit `current page only` wins. Unavailable fields remain missing; the agent
  must not navigate beyond that instruction to fill the table.
- Unknown ordinary field values do not automatically authorize detail browsing.
  The extraction stage checks their actual per-record availability.
- The existing limits remain: 30 model decisions, five active minutes and six
  captured pages, normally the index plus up to five detail pages. No new paid
  router, budget increase, silent retries or model upgrade were introduced.
- When limits or source access prevent completion, retained sources may produce
  a clearly marked partial preview. Collection evidence for one field on one page
  is not proof that every selected record has that field.

## Corrections from the inspected user1 runs

- Rendered text-node boundaries prevent source labels and numbers being fused.
  Bounded legacy numeric checks support `Location9.4` and `score14,058 reviews`
  without treating `Hotel31`, `4.8` or `40` as a requested numeric value of `4`.
- Nested bed/room lists inherit their enclosing coherent listing owner. Genuine
  nested records and separately presented live updates retain distinct groups,
  even if their URLs are identical.
- Hotel descriptions no longer receive article-only teaser/body validation.
  News body fields still need actual body evidence, not headlines or snippets.
- Exact amenity items may share a field only with evidence from the same record;
  any repaired quote is copied from a real contiguous captured source span.
- No empty standard author/date/excerpt/section columns are appended to every
  news run. Requested fields are preserved; inferred empty fields are disclosed
  as omitted, not silently treated as unavailable on the website itself.
- Cards use available snippets/descriptions, including `article_snippet`, and
  dynamically selected names/URLs. Pricing metadata does not inflate source-field
  completeness. Expand **Fields chosen for this request** for missing-field and
  capture coverage information.
- Topic instructions preserve qualifiers: world politics is not automatically
  equivalent to all domestic political reporting. Relevance remains AI-assessed
  and needs human review; this is not model fine-tuning or guaranteed classification.

The pending [returned-stay pricing correction](PRICING_SCOPE_FIX.md) is included:
nightly defaults to all requested rooms combined; raw totals remain unchanged;
verified stay totals may yield labelled average nightly costs divided by nights,
never rooms. Per-room pricing and taxes/fees are labelled separately. Wrong-stay,
starting or unverified prices are not approved as requested-stay budget matches.

## Restart and versions

Cancel old sessions, stop/restart the usual launcher and hard-refresh the dashboard
(Ctrl+Shift+R). If using the capture extension, reload it and refresh the source tab.

| Component | New version |
| --- | --- |
| Frontend/backend | `2026-10-14.3` |
| Browser agent | `browser-agent-v20` |
| Extractor | `website-extractor-v13` |
| Shared browser/extension collector | `source-inventory-v4` |
| Output-field projection | `dynamic-fields-v1` |

Old jobs and saved exports are not rewritten. Start fresh runs when comparing.

## Live scenarios for you to verify

### A. Homepage news, no search

Website: `https://www.nytimes.com/`

> Get me articles related to world politics from the current page.

Expect source-supported headlines, URLs and available teasers, without a site
search or arbitrary empty author/body columns. Check that teasers appear on cards,
and that domestic election coverage is not included merely because it is political.
The reported capture limits still apply; this is not every article on the website.

### B. Requested detail information

> Find articles related to world politics. Include each headline, URL, author,
> publication date and a short excerpt from the actual article body. Open relevant
> same-site links when that information is not on this page.

Expect the index retained, relevant record links opened within the existing page
budget, and actual detail-source evidence. Not every requested field will exist
on every page. Missing fields stay visible with reasons. If the selected records
exceed the detail budget, the preview must say it is partial rather than claim
all article bodies were collected.

### C. Page-only instruction wins

> From the current page only, get world-politics headlines, URLs and authors.
> Do not open linked pages or search the website.

Expect no linked navigation. Authors may remain blank with reasons. No invented
bylines and no claim that the source website has no authors.

### D. Hotel search and price meaning

Website: `https://www.booking.com/`

> Find hotels in New York with check-in October 28, 2026 and check-out October 30,
> 2026 for 4 adults and 2 rooms. Try to find prices around 250-350 USD nightly.
> Include useful listing details, displayed price, currency, price basis and URL.

Verify committed destination, both dates, adults and rooms, then actual Search.
Compare the returned header and each price card against the preview. No article
description rules should erase room details or review counts. A canonical city
label may include its region, but must not match a different place containing
the city name. Approximate budgets are preferences; outside-target alternatives
must be labelled, not silently rejected or called matches. A city catalogue for
one night/two adults must not pass as this stay's quote.

Repeat with `Keep only prices between 250 and 350 USD nightly, inclusive` to check
hard filtering on the verified combined nightly basis. Inspect taxes/fees and
per-room labels; do not assume a bare dollar symbol proves USD.

### E. Another content type

On an accessible product, research or directory page:

> Extract the main records and useful details available on this page. Include
> their names and source links. Do not search or open other pages.

Expect fields appropriate to that content, not article-only or hotel-only columns.
Check at least one source value against its own card, not a neighbouring record.

### F. Explicit and inferred missing fields

In Advanced, pin a small set such as `name, url, warranty` on a suitable product
page where warranty is not visible. Expect warranty retained with missing-value
reasons. In a separate unpinned run, an inferred field empty for every record
should be omitted and disclosed; a field available on some records should remain.

### G. Save/download parity

Approve an appropriate preview and compare CSV/Excel/JSON against it. Same source
columns, same raw prices and blanks, with computed price/basis/tax/fee fields
clearly labelled. Downloading must not invoke the model. Read-only unverified
pricing previews must not gain a Save/Download-as-matches action.

## Optional regression commands for you to run

```powershell
uv run --locked pytest tests/test_dynamic_output_contract.py tests/test_dynamic_field_service.py tests/test_dynamic_record_integrity.py tests/test_information_needs.py tests/test_pricing_basis.py tests/test_pricing_workflow.py tests/test_result_stay_scope.py tests/test_extraction_consistency.py tests/test_extraction_contract.py -v -ra
uv run --locked pytest tests/test_dynamic_capture.py tests/test_dynamic_field_ui.py tests/test_pricing_capture.py tests/test_pricing_ui.py tests/test_record_capture.py tests/test_capture_handoff.py tests/test_collection_goal.py tests/test_search_handoff.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

These authored fixtures have not been executed by the implementation author.
Actual website layouts, source availability, access decisions, model relevance,
coverage, timings and token usage still require your manual verification.
