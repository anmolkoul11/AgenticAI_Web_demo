# Collection metadata must not block browser actions

Implementation checkpoint: 2026-10-15. Manual verification pending. No tests,
static validators, application imports/startup, browsers or model calls were run.

## What the reported runs establish

- The supplied Booking trace has 23 entries, including 12 metadata rejections.
  Destination selection, dates, adults and rooms did work. Search transitioned at
  step 20; capture steps 21–23 were rejected before the capture tool ran.
- Its temporary post-submit DOM-readiness failure recovered with passive reads.
  That recovery was not the final capture blocker.
- The NYTimes trace has nine capture/finish rejections and no retained source.
  Extraction was never reached. These traces do not establish an independent
  extraction or website-blocking defect.
- The exact rejected information-need fields were not retained in those logs.
  The shared rejection path is verified in source, but their specific names
  cannot be reconstructed from action explanations.

The application treated every optional model-proposed `information_needs` entry
as a mandatory browser requirement. Inferred basic output columns need not occur
verbatim in a generic request; rejecting them also blocked otherwise valid
destination selection, widget Done, capture and finish. A rejected optional field
prevented accepting the valid collection goal, disabling the existing automatic
post-search capture handoff.

## Correction

1. Validate the core collection goal and real form requirements independently.
2. Ignore unsupported optional information hints with a bounded diagnostic note.
   They do not authorize new navigation, change values, or prove source evidence.
3. Accept the valid core goal and continue the otherwise valid browser action.
4. Commit collection-goal changes atomically. An invalid core goal cannot leave
   partially updated needs or expanded navigation scope behind.
5. Feed back at most three compact ignored-field notes to an existing decision;
   retain at most eight distinct notes in the task snapshot. No extra model call.
6. Preserve requested fields and source validation during extraction. Ignoring a
   browser-navigation hint does not discard a source column or waive an output
   requirement.

True form-value changes, invalid core request quotes, unsupported scope changes,
MFA/access handoffs and capture errors still stop as before. No budgets, networking
defaults, model/SDK configuration, pricing checks or review-before-save changed.

OpenAI Docs informed the distinction between schema-valid responses and semantic
correctness, and the prompt now explicitly permits an empty optional needs list:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Restart before verification

Stop/restart the usual dashboard launcher, hard-refresh with **Ctrl+Shift+R**,
and start new browser sessions. Existing agents keep their loaded Python code;
Resume is not a code reload. Old histories are not rewritten.

- Frontend/backend: `2026-10-15.1`
- Browser agent: `browser-agent-v20.1`
- Extractor and collector unchanged: `website-extractor-v13`, `source-inventory-v4`

## Manual scenarios

1. **NYTimes homepage:** `Get me articles related to world politics.` The valid
   current-page capture should run rather than repeatedly fail on optional field
   declarations. Check the preview and evidence. This prompt does not request
   opening every story or acquiring full article bodies.
2. **NYTimes requested depth:** `Find articles related to world politics. Include
   headline, URL, author, publication date and a short excerpt from the actual
   article body. Open relevant same-site links if those details are missing.`
   Expect the starting source retained, bounded detail collection, and explicit
   missing/partial coverage where necessary.
3. **Booking:** `Find hotels in New York with check-in October 28, 2026 and check-out
   October 30, 2026 for 4 adults and 2 rooms. Try to find prices around 250–350 USD
   nightly. Include hotel name, listing URL, displayed price, currency, price basis
   and guest rating.` Check committed destination, dates, occupancy, actual Search
   and automatic source capture. Unsupported optional field suggestions must not
   block Done or capture. Price/stay uncertainty may still produce a read-only
   source preview; verify returned scope and price basis separately.
4. **Page-only/negation:** `Get headlines from this page only. Do not include
   authors or open links.` An unsupported author hint must be ignored, not create
   detail navigation or reject capture.
5. **Invalid real form values:** A changed requested occupancy or invented field
   value must still be rejected. Optional-metadata tolerance is not action approval.

Inspect `information_need_notes` on action evidence and
`task_checklist.information_need_feedback` in technical evidence. Hard rejections
now include `declaration_stage` and bounded field names, not credential/page values.
Repeated rejections in older histories may span separate resumes; the three-error
streak is per run, while the paid-call budget and action history persist.

## Optional commands for the user

```powershell
uv run --locked pytest tests/test_collection_metadata.py tests/test_information_needs.py tests/test_browser_context.py tests/test_search_handoff.py tests/test_submission_scope.py tests/test_collection_goal.py -v -ra
```

These fixtures have been authored but not executed. Actual live site behavior,
content accuracy, timings and token usage remain for manual verification.
