# Source quality and results preview

Implementation date: 2026-10-05. User-run automated tests and live acceptance are pending.
UI version: `2026-10-05.2`; extraction prompt: `website-extractor-v8`;
Page Capture extension: `0.3.0`. The model, API credentials and network modes are unchanged.

## Why the two extraction paths behaved differently

The saved sports proposal from the reported run contained body quotations in its
title fields and blank excerpts. Inspection of the saved source blocks showed:

- Current-page extraction had the homepage's cards, kickers and teasers, not the
  linked pages' article bodies. Both paths use the **same capture collector**.
- The collector excluded every `<header>`, including article headers, not just
  global navigation. Several captured detail pages had **zero heading blocks**.
  This is consistent with missing headline regions; the original DOM was not
  retained, so it does not prove the exact layout of each live page.
- The collector assigned inline anchor text to a separate block before assigning
  paragraph text. Captured paragraphs lost linked names; for example, an NFL
  sentence named neither official even though their names appeared in other blocks.
- Quote validation established that text occurred on the page, not that it was
  the headline. Consequently, a genuine body quotation passed as a title.
- Evidence could lose display-only quote wrappers while its value kept them.
  Otherwise verbatim excerpts then failed `value_missing_from_quote`.
- The two rejected relevant candidates in that run failed source/title validation.
  They were not classified as unrelated. One other approved page failed navigation
  or capture separately. These are different failure categories.

Opening details provided additional paragraphs; it did **not** establish that the
resulting titles were correct. Current-page and enriched records should have consistent
identities where the source supports them, but their available context and counts
are not expected to be identical.

## Changes

### Capture

- Preserve content headers in article/main content while excluding global navigation.
- Capture primary headline nodes before spending the bounded body-text budget.
- Keep headings as heading blocks with optional `heading_level` and `content_role`.
- Preserve inline names and text in their original paragraph; retain href evidence
  separately. Keep article headers/body in one source group, while separate hotel
  cards and nested records remain separate.
- Use the identical collector in built-in Chromium and the Page Capture extension.
  Existing limits, consent, network modes and credential handling remain unchanged.

### Interpretation and validation

- Instruct the model to distinguish the full headline, a promotional kicker, a
  body excerpt, and a URL. Homepage H2/H3 headlines do not require a detail-page H1.
- Validate headline/excerpt roles when structured capture provides them. Plain text
  cannot provide DOM-role assurance and retains its existing quote-based path.
- Correct a wrong main title only when a **single candidate**, a **unique captured
  primary headline** and its **declared detail URL** identify the same captured page.
  Multiple competing headings, missing URL bindings and sidebar candidates are not guessed.
- On an index, a unique captured heading bound to the declared record URL can
  replace a kicker. No title is generated from an approved link label or URL slug.
- Strip one extra display-only quote wrapper only when the resulting value is
  literally supported by its already-verified quote. Real source quotation marks
  remain intact. Paraphrases and unsupported numbers are not repaired.
- Retain old/corrected values and source evidence in `field_repairs`. These previews
  require the existing explicit partial-result approval. Saved snapshots retain the report.
- Display field-level rejection reasons against each affected captured link.
  Missing model rows remain coverage gaps, not invented records.

The same shared validation runs for LangGraph and CrewAI. Hotel/product names are not
forced into an article-headline schema; price/rating and query-rule protections remain.
Structured output enforces shape, not factual or semantic correctness, so the updated
prompt is paired with source checks and human review.
[OpenAI structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs).

### Preview and progress

- Cards provide a readable overview; Table retains the full grid.
- **Preview record & evidence** opens a focused, keyboard-accessible dialog with
  all supplied fields, source links, quotes, provenance and conflicts.
- **Previous / Next**, **Back to results**, **Back to review** and **Back to source
  setup** do not re-extract, call the model, discard the run, or cancel a browser.
  Escape closes the dialog and returns focus. Back to setup is navigation, not reset.
- A spinner and highlighted checkpoint represent actual queued/running stages.
  Waiting for login/verification, search approval, link selection or final review is
  labelled as waiting, not active automation. Completed/failed stages stop animating.
- The progress bar counts completed/not-needed stages, not estimated time. Network
  loss stops the indicator and states that backend status is unknown; it does not
  falsely claim the backend run was cancelled. Reduced-motion preferences are respected.
- Previews are not saved exports. Downloads become available after explicit approval.

## Refresh before verifying

1. Stop and restart the dashboard using your existing launcher or manual command.
2. Hard-refresh the dashboard (`Ctrl+F5`). Check that the session UI version is current.
3. If using Page Capture, reload the unpacked extension at `chrome://extensions`
   or `edge://extensions` and verify version `0.3.0`.
4. Make a **new capture/run**. Previous captures and saved snapshots are not rewritten;
   rerendering an old saved run will not recover its missing headlines or paragraphs.

## Commands for you to run

From the repository root, first run the offline regressions:

```powershell
uv run --locked pytest tests/test_source_quality.py tests/test_topic_review.py tests/test_topic_evidence.py tests/test_custom_website.py tests/test_detail_enrichment.py tests/test_source_inventory.py tests/test_dashboard_ui_structure.py -v
```

Then run isolated local browser fixtures (no external sites or model calls):

```powershell
uv run --locked pytest tests/test_source_quality.py tests/test_source_inventory.py --run-browser -v
```

Finally run the broader offline suite if you want a regression check:

```powershell
uv run --locked pytest
```

Previously deferred rule/event fixture failures are not addressed by this checkpoint.
No automated tests, live browsers or paid model calls were run by the assistant.
Only formatting, lint and static syntax checks were performed.

## Manual acceptance scenarios

1. **Current page only.** Open an accessible news index with visible sports cards.
   Request: `Extract sports headlines visible on this page, with their exact titles
   and links. Do not infer article bodies.` Verify titles against the actual cards,
   source URLs against the index, and the warning that details were not opened.
   The path cannot return a body that is only present on an unopened page.
2. **Follow and enrich.** Use the same starting page. Request: `Find sports stories,
   open the approved relevant links, and include exact headlines, links and a
   verbatim passage of article context.` Approve up to five relevant links. Compare
   each title to the opened page's headline, and each excerpt to an actual body
   paragraph. Inline names should remain present. Inspect any corrections or gaps.
3. **Topic and failure distinctions.** Try a narrower Soccer topic. Inspect the
   counts for unrelated, uncertain and invalid records separately. A captured link
   rejected for source checks must show its field reasons, rather than appear to
   have failed navigation. A page without a recoverable headline must not use a
   quotation or slug as a fabricated title.
4. **General records.** Repeat a hotel or product extraction with visible names,
   URLs and values. Verify record groups and user-requested filters; there is no
   new article-only requirement or fixed USD 200 ceiling.
5. **Preview and back.** Switch Cards/Table, open a record, use Previous/Next and
   Escape/Back. Return to review and setup. Verify the chosen job, selection, request
   and results remain. These actions should not create another model request.
6. **Running versus waiting.** Observe capture/model/save activity, then stop at
   login or link approval. Animation must stop while waiting for you. Check a
   failure and completed run. Turn on reduced motion; activity text must remain
   useful without animation. A status-connection failure must not claim cancellation.
7. **Exports.** Approve the preview and partial warnings when acceptable, then
   compare CSV/Excel/JSON with the preview's titles, excerpts and source evidence.
   Reopen the saved job in history and inspect its retained correction report.

These changes improve the local prototype. They do not guarantee every website,
full-site completeness, bypass of site restrictions, or production acceptance.

