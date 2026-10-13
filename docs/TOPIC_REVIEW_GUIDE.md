# Topic review correction

Implemented for user-run verification. No live Fox integration, browser session,
paid model call or test execution was performed for this change.

## What changes

- A model candidate marked unrelated to the requested topic is excluded, not rejected
  merely because its unused optional metadata lacks a source quote.
- Uncertain relevance remains excluded from saved results, but is shown separately
  from invalid source records. Missing relevance and conflicting schema still fail.
- Unsupported optional fields on otherwise verified relevant records become null,
  with explicit field warnings and partial-result approval. No source value is invented.
- Title/name aliases identify a record before type/classification columns. Both source
  validation and detail reconciliation use the same choice. Identity and fields used
  by filters/rules still require source evidence; a missing identity rejects the row.
- Ready, unrelated, uncertain, invalid, filtered-out and duplicate candidate counts are
  visible without opening technical JSON. Counts are about model candidates, not the
  full website. Linked index/detail candidates may merge into fewer preview records.
- Zero accepted records create no empty proposal/export. If uncertainty or invalid
  records remain, the app says review needs attention. Otherwise it says no matches
  were found in captured content, not that the entire website has none.
- The new link-discovery setup button copies source and request into the browser form.
  It does not open a browser, retry a model call, log in or follow links automatically.
  Review settings/credentials, renew consent, submit and choose Find relevant links.
- This does not change browser networking, login/MFA handling, provider credentials,
  model or pricing, add a website-wide crawler or guarantee the AI topic assessment.

## Commands (you run)

Run from `D:\Projects\AgenticAI_Web_demo`:

```powershell
uv run --locked pytest tests/test_topic_review.py tests/test_topic_evidence.py tests/test_custom_website.py tests/test_detail_enrichment.py tests/test_source_inventory.py tests/test_dashboard_ui_structure.py -v
```

Browser fixtures in the source-inventory suite remain opt-in and are skipped by this
command. Do not add live-model flags merely to verify the offline correction.

## Manual scenarios

Restart the dashboard and Ctrl+F5 first. Repeat relevant preview/save checks with both
LangGraph and CrewAI. Paid API consent remains required for real extraction calls.

1. Fox homepage, `find articles related to Soccer`, current-page-only capture:
   unrelated records should count as Unrelated, not invalid solely for article_type.
   If there are no safely supported matches, no file is saved. The message must be
   limited to captured content; uncertain/invalid cases must not be declared no-match.
2. A visible Soccer story in an authorized source: a source-verified title/URL should
   survive an unsupported optional type label as a blank, with a visible warning.
   A missing/unsupported title, required filter value or topic evidence still fails.
3. No matches: click Set up a new session to find relevant links. Source and request
   should be retained, paid consent unchecked and no browser/API call started. Submit
   after review, discover links, approve relevant detail URLs and check body coverage.
4. Uncertain snippets: see a separate uncertain category; do not export them as matches.
5. General listing extraction: user-requested hotel price ranges still work, including
   prices above USD 200. This correction introduces no article-only schema or ceiling.
6. Save a valid partial preview deliberately, then download. Blank optional fields,
   verified evidence and accepted records should persist; unrelated/uncertain/invalid
   candidates must not appear as accepted rows or produce events.

The source can lack matching content, the capture can be incomplete, or the model can
misclassify relevance. These are distinct from invalid source fields. Review evidence
and coverage before approving; a no-match page is not a full-site search.
