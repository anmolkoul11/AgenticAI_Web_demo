# Stable updates and readable checkpoints

2026-10-06; dashboard version `2026-10-06.1` (supersedes `2026-10-05.3`).
Implementation is ready for user validation. No tests, live browser sessions or model
calls were run by the assistant. Static lint/syntax checks only.

## Findings and changes

### Jumping content during a running task

The custom polling loop rendered a job without browser state, then rendered it again
after fetching browser state. Source coverage/navigation evidence could first disappear
and then reappear. Several panels destroyed/rebuilt their children every second, even
when unchanged. This could close disclosures, disturb focus and restart activity state.
Checkpoint details also opened automatically as the inferred active step changed.

The loop now obtains job/browser data before a **single coherent render**. Changed-only
regions retain unchanged DOM nodes and open details. The stage log, navigation plan,
source coverage, rejection details and results grid no longer rebuild for identical data.
Checkpoints do not expand themselves. Stale responses from a previous selection are
ignored using a selection generation counter. Hotel-demo stage lists also skip identical
updates, preserve opened step details, and avoid automatic scroll when showing feedback.

Actual changes (a new stage, error, preview or a user opening details) can legitimately
change the layout. The goal is to eliminate the repeated hide/show bounce, not freeze
the interface or conceal new content. The live symptom still needs manual verification.

### Activity circles and checkpoint information

Each Website Studio checkpoint has a circular status ring. Only the step actually
processing rotates its decorative ring; the number/glyph and text remain stationary.
Completed steps show a checkmark, waiting/review steps a pause marker, and failures an
attention marker. The top activity indicator has explicit sizing/display styling.

Click a checkpoint to see a brief task-specific explanation, such as loading the
website, proposing search actions, collecting approved pages, extracting records or
checking source quotes. Open/closed choices survive ordinary polling. Hotel-demo
recorded stages also have activity rings and clickable short explanations.

Waiting for sign-in, verification, search approval or link approval is **not running
automation**. Its rings deliberately stop. Reduced-motion users get static rings and
textual Running/Waiting status. No invented time-based percentage was added.

### Cards and missing information

The card overview previously displayed three facts and a four-line excerpt; the full
preview/table/export could contain more. Cards now provide **All output fields**, a
filled/missing field count and available source-check reasons. The focused preview
also identifies fields not extracted. Null no longer claims that the website itself
lacks the information.

These UI changes do not acquire extra data or change exports. There are distinct cases:

1. A value exists in preview/export but not the compact summary: a display omission.
2. A value was cleared by evidence/field validation: inspect its source-check reason.
3. A value is absent from the capture or was not returned by the model: an acquisition
   or interpretation gap requiring fresh source/job evidence.
4. A requested field was not part of the inferred output schema: no field-count badge
   can detect that omission by itself; compare the full request with the proposed fields.

A fully filled card does not establish all-site completeness. Never fill missing source
facts with guesses simply to make a card appear complete.

### UI direction to agree next

The proposed non-developer layout is **Request → Browser & progress → Results**, with
navy/teal styling, a clear current task, and technical settings/evidence folded away.
This patch makes a small start: page loading/sign-in details and collected/link coverage
are disclosures, while actions, approval, status and cards remain available. It does
not replace the entire workspace before the user confirms the layout preference.

## User-run checks

Restart the dashboard and hard-refresh (`Ctrl+F5`) to load matching `2026-10-06.1` assets.
No extension reload is needed for this UI-only patch.

Offline contracts and source-quality regressions:

```powershell
uv run --locked pytest tests/test_dashboard_ui_structure.py tests/test_dashboard_live_updates.py tests/test_source_quality.py -v
```

Actual DOM/animation tests use isolated Chromium and **locally fulfilled requests**;
they stub dashboard API calls and do not access an external website or model:

```powershell
uv run --locked pytest tests/test_dashboard_live_updates.py --run-browser -v
```

Manual scenarios:

- Open Website Studio: **Normal networking** is preselected. The session confirmation
  remains required. **Restricted networking** remains an explicit alternative, with
  its origin controls shown when selected. Changing modes requires a new session;
  existing browser sessions do not switch. Direct API requests that omit a mode still
  use the existing restricted fallback; the dashboard explicitly submits its selection.
- During a running job, scroll to the browser actions and open a checkpoint. Wait
  through several updates: no repeated up/down bounce and no auto-open/close.
- Run a model extraction and inspect the active checkpoint: one rotating stage ring
  in Website Studio, a brief explanation on click, and stationary numbers/text.
- Pause at login or link selection: amber/static waiting state, not a fake spinner.
  Select links and wait through polling: your checkboxes should remain selected.
- Open page/source details while polling; unchanged content stays open. Changing jobs
  must not allow a delayed earlier response to overwrite the new selection.
- Compare card summary, **All output fields**, full preview and export. Longer context
  remains available in full fields even when the compact overview is shortened.
- Inspect a missing optional field: show its known source-check reason when available.
  An unknown acquisition gap must not be labelled as proven website absence.
- Enable reduced motion: circles stop rotating but the Running/Waiting text remains.

For an acquisition mismatch, share the fresh job JSON, starting/detail URL, prompt,
mode (current page or linked enrichment), and one expected field visible on the site.
Redact credentials, cookies, codes and personal data. This lets the next fix target
capture, schema inference, evidence validation or merging rather than guessing.

