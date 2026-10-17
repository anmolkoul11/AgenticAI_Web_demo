# Returned stay evidence at capture handoff

Checkpoint: UI/backend `2026-10-16.4`; browser agent `browser-agent-v20.4`.
Manual verification pending. Pricing contract remains `stay-pricing-v2`.

## Why this run stopped

Run `2bdc45cf-c7ee-4c42-877f-d04258f51a64` submitted Search, captured results
and extracted twenty source-verified candidates. Dates, four adults and two rooms
had independent returned-page evidence. Destination alone was unverified.

The capture nevertheless retained page-level H1 block `b1`:
`New York: 372 properties found`. The browser attached its earlier scope snapshot
before content preparation had exposed that heading. The pricing checks therefore
withheld the combined-room nightly comparison. This was a stale handoff, not a
failure to capture the price or a model quota/schema failure.

For West Side YMCA the source retained:

- `$282`, with its own `Per night $282` label;
- `$605`, with `2 nights, 4 adults`;
- `$720`, explicitly struck through.

No arithmetic relationship between these displayed amounts is invented. Current,
nightly and original amounts remain separate; taxes/fees remain unknown if absent.

## Changes

After bounded capture preparation, one fresh local observation rechecks the
returned dates/occupancy. The same-document captured H1/H2 result-count heading
can then supply destination evidence. Only ungrouped, page-associated result
headings qualify—not a hotel name, neighborhood, arbitrary paragraph or the old
pre-submit form. Source quotes/block IDs remain attached to the field ledger.

The live URL identity and captured source must match. Conflicting headings,
changed occupancy, missing years, existing mismatches or contradictions still
prevent verification. A failed final DOM read keeps content read-only rather than
promoting old control values. No automatic retry or additional model call is added.

The final agent report adopts the reconciled captured scope, removing a stale
`stay_scope_unverified` outcome only when scope really verifies. General searches
with no stay request are not mislabeled as hotel source previews. Diagnostics now
say the price basis/room scope could not be confirmed rather than claiming every
unknown basis means ambiguous price labels.

Extraction prompts, prices, business rules, networking and model budgets are
unchanged. Existing failed jobs are not rewritten, saved or approved automatically.
Optional unsupported fields still remain blank with their source issues disclosed.

## Manual checks

1. Restart the backend and hard-refresh. Start a new session; check agent v20.4
   and matching UI/backend `2026-10-16.4`.
2. Repeat the original New York request with October 28–30, 2026, four adults,
   two rooms and the soft nightly preference of USD 250–350.
3. Verify the website's returned stay details. If a captured top-level result
   heading confirms New York and the returned dates/counts agree, destination
   should no longer remain unknown merely because the first observation missed it.
4. Check nightly, total and original prices against the same browser session.
   Original prices must never become budget matches. Different displayed amounts
   must not be forced into an unexplained nightly/total equation.
5. Review any remaining missing optional fields separately, approve the preview
   if appropriate, then verify saved records/downloads. A genuine stay mismatch
   or missing price basis must still stop matching/saving.

Regression fixtures were authored but **not run**, as requested. No tests,
validators, application imports/startup, live browser or model/API calls ran.
