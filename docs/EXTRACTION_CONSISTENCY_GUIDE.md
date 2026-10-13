# Capture, output fields and active progress

Checkpoint implementation: 2026-10-06. UI 2026-10-06.3; extraction prompt
website-extractor-v9; extension 0.3.1. Supersedes earlier motion behavior.

## Evidence from user1's October 6 Fox News runs

The same sports request produced 8 Normal-mode candidates and 9 Restricted-mode
candidates. Neither run rejected a whole record. Restricted cleared six optional
snippets whose source groups did not match the record. Both captures stopped at
200 blocks, omitted roughly 12,000 characters, and never opened detail pages.
The model chose different column sets. Multiple captured H3 headlines lacked hrefs.

## Changes

- Progress uses real ring elements and persistent Web Animations instead of relying
  on a pseudo-element inside a collapsed disclosure. Unchanged polling does not
  restart the ring. Extraction stages outrank an old browser waiting snapshot.
- Progress animation defaults to On, as requested. Choose Off for static indicators
  or Use device motion setting to respect reduced motion. This is an in-page choice,
  not a stored preference. Waiting/review/finished steps do not pretend to be working.
- Both synchronized collectors preserve a unique anchor inside or around a heading.
  Multiple different heading URLs are not guessed. Listing/product containers are
  recognized alongside news cards. Headings and their record containers are collected
  before secondary page labels. The block cap is 600; the combined text/link cap stays
  24,000 characters. Capture remains bounded and can be partial; no pagination added.
  More metadata can increase model input tokens even with an unchanged text cap.
- Explicit Output fields pins the same snake_case field names across runs. Filter/rule
  dependencies are retained with a warning. Other unrequested inferred fields are
  excluded from the pinned view. Requested slots omitted by the model remain null,
  not invented. Prompt-inferred requested fields are also retained, but interpreting
  free-form instructions still requires human review.
- With inferred news schemas containing article_title, missing standard detail fields
  are retained as blank slots. This does not imply that the homepage contains them.
- Missing record URLs can be repaired from a unique captured headline-href binding.
  Main detail-page excerpts can be filled from their first captured body paragraph.
  Every repair keeps literal source evidence. No URL slug/title guesses, summaries,
  network requests, hidden article access or extra model calls are used for repairs.
- Index snippets must be supported by paragraph text, not a kicker/category link.
- Cards explain null fields as model-not-returned, failed validation or not-extracted;
  none proves the original website lacks the data. Status metadata survives saving.
- Proposals/snapshots include a fingerprint of the captured input. Different fingerprints
  mean different captured inputs, not different mode-specific validation policies.
  Equal inputs still do not guarantee identical outputs from separate model calls.

Structured-output schema compliance does not prove correct source interpretation.
The contract and source validation complement the existing Responses parsing workflow:
[official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
No model/provider/credential changes were made.

## Start and verify

### Checkpoint status follow-up

Before the first request, Set up source shows Idle; later steps show Pending.
Running is reserved for work actually being processed; user interaction continues
to show Waiting for you or Your review.

Publish event distinguishes Published (a broker acknowledgement, not a consumer
receipt), Skipped — disabled, and Skipped — no matches. Both skipped outcomes
finish the optional checkpoint and count toward the progress meter. Before saving,
the checkpoint instead shows Optional — disabled or Pending approval & save.
Failures remain Needs attention; missing delivery evidence is not assumed to be
success. Successful summary acknowledgements are recognized even when the returned
delivery object does not include an enabled flag.

To publish a custom-website summary event, enable the checkbox under Advanced:
manual rule override & event delivery **before creating a new preview**, ensure
NATS is running, then review and approve saving. Changing that checkbox does not
modify an existing approved proposal or replay an earlier event. Downloads do not
require event delivery. No saved runs, event settings or network policies were changed.

Manual checks: a fresh dashboard has no Running checkpoint; a saved run with events
off ends at 7/7 with Skipped — disabled; an enabled run with matching records shows
Published after acknowledgement; an enabled run with zero matches shows Skipped —
no matches; broker failure shows Needs attention without losing saved results.

Restart the dashboard and hard-refresh with Ctrl+F5. Reload the unpacked extension
if you use extension captures; an older extension still sends its older collector.
Old saved runs are not reprocessed or modified.

Assistant performed static syntax/lint checks only. User-run offline regressions:

```powershell
uv run --locked pytest tests/test_extraction_consistency.py tests/test_source_inventory.py tests/test_source_quality.py tests/test_custom_website.py tests/test_query_workflow.py tests/test_dashboard_ui_structure.py tests/test_dashboard_live_updates.py -v
```

Opt-in browser fixtures fulfill all network requests locally; they do not make model
calls or visit external websites. They measure actual transform/time advancement:

```powershell
uv run --locked pytest tests/test_extraction_consistency.py tests/test_dashboard_live_updates.py tests/test_source_inventory.py --run-browser -v
```

Manual acceptance:

1. During model extraction, keep the dashboard visible: the current ring revolves,
   the number stays still, and polling does not reset it. Off stops it; On restarts it.
2. Repeat the same URL, prompt, output fields and extraction option in both modes.
   Compare captured-page coverage, source_fingerprint, preview fields and field issues.
   Different live content, scripts and model candidates may still produce different rows.
3. News: request title, URL and context. Use current-page capture for index records;
   use Find relevant links and approve pages for body context. URL fields should retain
   actual captured heading links. Null author/date/excerpt fields have explanations.
4. Listings: pin name, city, price, currency, rating. Apply the user's price/rating
   criteria; verify labels remain attached to their own listing, not a neighbor.
5. Preview, save and compare CSV/Excel headers and values. Blank preserved fields must
   not disappear or be filled with guesses. Full field-status metadata is in the saved
   snapshot; existing flat downloads may not include that metadata as separate columns.

This improves the identified defects; it does not guarantee complete extraction from
any website. Browser rendering, access decisions and uncaptured content remain separate
constraints. No automatic retries or extra paid calls have been added.
