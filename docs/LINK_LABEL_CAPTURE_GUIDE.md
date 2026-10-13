# Current-page link label evidence

Implemented October 7, 2026. Extension version 0.3.2. No model/provider,
network policy, approval, login or event-delivery settings changed.

## Identified mismatch

The NYTimes current-page run yielded nine title-role rejections. Literal text
validation succeeded, but capture represented the titles as paragraphs rather
than headings/link blocks. Link discovery separately read anchor labels, so it
could propose relevant links without producing validated current-page records.
The saved failure contains summary counts, not raw DOM evidence; its exact page
markup was not retained. Local regression fixtures reproduce the code mismatch.

## Changes

- Preserve literal visible anchor labels as separate link blocks with their
  captured URLs and source groups, regardless of paragraph/span/list nesting.
- Keep native headings first, then reserve link evidence before general page text
  uses the block/text budget. Deduplicate by label AND URL, not URL alone.
- Do not spend the href budget again on a paragraph/text block when its separate
  link label already carries that URL. Paragraph content remains available.
- Link labels use the same visibility/exclusion checks as capture: no hidden,
  navigation or form text. Full labels are preserved rather than using the
  link-discovery UI's 180-character display label as source evidence.
- A missing record URL can be filled only from an exact identity match with one
  distinct captured heading/link URL. Multiple URLs remain unresolved. Repairs
  keep source evidence and are reported in field_repairs.
- Browser and extension collectors remain identical. No extra API calls occur.

This does not reclassify every paragraph as a headline. Generic promotional labels
still require human review. An existing real heading outranks a kicker for its URL;
detail-page validation still requires the main headline, not an inline link.
Topic relevance, filters, source grouping and unsupported-value checks still apply.

Capture remains capped at 600 blocks and 24,000 combined text/href characters.
Link evidence can leave less room for body text; coverage diagnostics disclose
limits. A current-page capture cannot supply uncaptured detail-page context.
Link discovery is a proposal, not proof of extraction accuracy. Separate live
captures/model calls need not return identical records.

## User-run checks

No pytest/browser/model calls were run by the assistant; static checks only.

```powershell
uv run --locked pytest tests/test_link_label_capture.py tests/test_source_quality.py tests/test_extraction_consistency.py tests/test_source_inventory.py -v
uv run --locked pytest tests/test_link_label_capture.py tests/test_source_quality.py tests/test_extraction_consistency.py tests/test_source_inventory.py --run-browser -v
```

The browser fixtures fulfill every request locally. They cover anchor-wrapped
paragraphs, paragraphs containing anchors, spans, nested formatting, repeated labels,
long headlines, capture pressure, hidden/form/navigation exclusions, hotel names,
ambiguous URLs, kicker rejection and detail-page headline requirements.

## Manual check

1. Restart the dashboard so it loads the changed collector; hard-refresh the UI.
   Reload the unpacked Page Capture extension if using extension captures.
2. Start a fresh browser session with the same URL and request. Wait until the
   relevant content is visibly rendered, then use Extract current page only.
3. Compare preview titles/URLs with the actual page. A paragraph-rendered linked
   title should no longer fail solely because it lacks an H1/H2/H3 element.
4. Start a separate run for Find relevant links. Compare the proposed labels and
   URLs. After approval, detail pages should add only their own captured context.
5. Inspect coverage, field issues, repairs and topic decisions when a result is
   missing. Uncertain topic classification and capture limits are separate issues.

Earlier saved runs/captures are not changed or reprocessed. Success with these
fixtures is not a guarantee of complete extraction from every website.
