# Progress

## Connection recovery and categorized source details - 2026-10-17, verification pending

OpenAI authentication/access failures now explain checking an active, complete
key, re-pasting it under API connection, replacing an expired/revoked/invalid key,
and starting a fresh browser workflow after saving. A 401 does not establish
expiry specifically; active-key account/project/IP restrictions remain possible.
Connection-save guidance explains that paused agents retain the old connection.
No key inspection, automatic connectivity check or retry was added.

The latest user1 Element record's six supplemental quotes were correctly bound
to the hotel; combined amenities evidence had failed source validation, while
expanded title/review representations remained visible as additional text.
Additional source details now have generic categories, preserve literal wording
and qualifiers, and keep URLs/block references under View source. Exact mapped
titles with a new-window suffix are suppressed in this drawer only. Location
subscores and richer review descriptors remain separate from the overall rating.
Missing output fields and saved historical exports are not silently filled or
rewritten; unknown wording has a fallback category. UI/backend `2026-10-17.1`;
agent prompt, extraction/price rules and paid budgets unchanged. Regression
fixtures authored, not run; no tests, validators, imports/startup, browser or API
calls. See [SOURCE_DETAILS_AND_CONNECTION_RECOVERY.md](SOURCE_DETAILS_AND_CONNECTION_RECOVERY.md).

## Captured returned-stay handoff - verification pending

User1 run `2bdc45cf` successfully searched/extracted, but kept destination unknown
despite a captured New York results H1. That stale scope blocked every combined
nightly comparison. Capture now refreshes independent returned-page fields once,
then reconciles strict same-document page-level result headings with literal
block evidence. Mismatches/contradictions and missing values remain blocking;
original prices are never selected. Agent/report scope stays consistent with the
captured source, and diagnostic wording no longer equates unknown room scope with
ambiguous price labels. UI/backend `2026-10-16.4`, agent v20.4; pricing contract
v2 and model budgets unchanged. Fixtures authored, not run; no tests, validators,
imports/startup, live browser or API calls. See
[CAPTURED_STAY_HANDOFF_FIX.md](CAPTURED_STAY_HANDOFF_FIX.md).

## Committed destination read-back loop - 2026-10-16, verification pending

The supplied user1 trace repeatedly selected New York, then rejected the site's
qualified location label and overwrote it with the short requested city. Search
was never attempted despite valid decisions. Observation now preserves complete
visible primary suggestion wording; committed option/read-back evidence survives
unrelated form-index changes. Redundant fills cannot erase verified selection,
and compact context respects explicit selection guidance. Exact ownership,
read-back, ambiguity and submission checks remain. UI/backend `2026-10-16.3`,
agent v20.3; no new paid calls or retry budgets. Fixtures authored, not run; no
tests, validators, imports/startup, browser or API calls. See
[DESTINATION_COMMITMENT_FIX.md](DESTINATION_COMMITMENT_FIX.md).

## Grouped source-aware result presentation - 2026-10-16, verification pending

Cards/full preview now group source-appropriate fields and distinguish current,
nightly, total and original prices. Equivalent price observations merge only in
the display; raw facts and selected comparisons stay unchanged. Missing fields
are expandable, with separately labelled record-bound captured wording where
available. The generic layout retains unfamiliar fields rather than assuming a
hotel/news schema. Historical runs receive a read-only view from retained source
blocks; original exports/proposals are not rewritten. UI/backend `2026-10-16.2`;
no new model calls or pricing-rule changes. Fixtures authored, not run; no tests,
validators, imports/startup, browser or API calls. See
[GROUPED_RESULT_PRESENTATION.md](GROUPED_RESULT_PRESENTATION.md).

## Multiple displayed-price relationships - 2026-10-16, verification pending

The next user1 capture retained nightly/current/original amounts, but flattened
labels and omitted strike status blocked every nightly comparison. Collector v6
retains bounded literal amount relationships, extractor v15 requests distinct price
roles, and pricing v2 selects an independently supported current nightly amount
without discarding other observed quotes or inventing a fee explanation. Preview
and flat exports retain all price observations; workflow guidance names actual
blockers. Save rechecks the same evidence. UI/backend `2026-10-16.1`; browser agent
remains v20.2. Tests were authored, not run; no app/browser/model calls were made.
See [MULTI_PRICE_EVIDENCE.md](MULTI_PRICE_EVIDENCE.md).

## Capture and numeric evidence integrity - 2026-10-15, verification pending

The latest user1 run reached results, but a text-typed price schema caused 17
comma-formatted amounts to be cleared; eight other amounts were absent from the
retained capture, including West Side YMCA whose price the user confirmed live.
This checkpoint reconciles
numeric dependencies, retains literal number evidence, captures rendered record
values more completely, and separates known currency/returned scope from amount
verification. Fresh results headings can verify the returned city without using
pre-submit proof. No fixed hotel schema or extra model calls were added. UI/backend
`2026-10-15.3`, agent v20.2, extractor v14 and collector v5. Regression fixtures were
authored, not run; no application/browser startup or API calls were performed.
See [CAPTURE_INTEGRITY_FIX.md](CAPTURE_INTEGRITY_FIX.md) for limitations and manual checks.

## Keep source browser open for verification - 2026-10-15, verification pending

All successful managed-browser capture paths now hand one copied snapshot to the
extraction worker while the original browser remains on its owning thread for
manual verification. A separate Close browser action does not cancel extraction
or saving. The compact verification panel survives Results/Save/job selection;
manual browsing never updates captured data. Logout, session expiry, native window
closure and server shutdown clean up retained browser resources. Original network
mode and collection/model limits remain unchanged. Frontend/backend versions are
`2026-10-15.2`; browser-agent version remains `browser-agent-v20.1`. Regression
fixtures were authored but not run. No tests, static validators, imports, app or
browser startup, or model calls ran. See [BROWSER_VERIFICATION.md](BROWSER_VERIFICATION.md).

## Optional collection-metadata rejection fix - 2026-10-15, verification pending

The new Booking trace submitted Search but rejected capture, and NYTimes rejected
all capture/finish actions before retaining any page. Optional inferred information
fields were incorrectly treated as hard browser prerequisites. Agent v20.1 ignores
unsupported optional hints with bounded diagnostics, preserves the valid core goal,
and commits declaration changes atomically. Real form values, request scope, source
checks and budgets remain enforced. Existing post-search capture can now proceed
without corrective model calls for optional metadata. Frontend/backend versions
are `2026-10-15.1`. No tests, static validators, application startup, browsers or
model calls ran. See [COLLECTION_METADATA_FIX.md](COLLECTION_METADATA_FIX.md).

## Dynamic fields and needs-driven collection - 2026-10-14, verification pending

The user1 audit found missing values at several stages: homepage-only news
collection, forced empty news columns, fused numeric labels, nested bed-list
ownership and article-only checks applied to hotel descriptions. Extractor v13
infers source-appropriate fields inside the existing call; explicit fields and
rule dependencies remain, while entirely empty inferred columns are omitted by
local projection. Preview/save/export share the resulting contract. Collector v4
retains coherent records, rendered text boundaries and separate live-update groups.
Agent v20 carries requested information needs in its existing decisions and follows
record links only when needed and permitted. Existing budgets remain unchanged.

This checkpoint incorporates the previously staged pricing correction below.
Both UI versions are `2026-10-14.3`. New tests were authored, not executed; no tests,
static validation, application imports/startup, browser or model calls ran. See
[DYNAMIC_FIELDS_GUIDE.md](DYNAMIC_FIELDS_GUIDE.md) for manual scenarios and commands.

## Returned stay and combined-nightly pricing - 2026-10-14, verification pending

The inspected user1 run filled and submitted the hotel search but saved city
catalogue prices for one night/two adults rather than the requested stay. Revision
v19 separates returned stay scope from pre-submit proof. Extractor v12 preserves
displayed prices and approximate preferences; shared application checks compare
only source-bound pricing, label combined/per-room/average bases and disclose taxes.
Unknown or mismatched pricing remains a read-only preview. Save rechecks source
inputs; historical exports are not rewritten. Collector v3 retains a selected
currency label as explicit evidence. Both UI versions are `2026-10-14.2`.

Regression fixtures were authored but not executed. No tests, static validation,
application imports/startup, browsers or API calls ran. Model/account configuration
and paid-call budgets are unchanged. See [PRICING_SCOPE_FIX.md](PRICING_SCOPE_FIX.md)
for user-run verification and pricing semantics.

## Search observation recovery - 2026-10-14, verification pending

The latest user1 Booking trace verified all five form fields and attempted the real
Search button, then paused on a browser observation error. No source capture or
extraction ran. Search bookkeeping was recorded after the first post-click read,
so that error left the checklist incorrectly reporting no attempt. The precise
browser exception was not retained; the subsequent ten-minute expiry was secondary.

Revision v18.1 retains attempted-but-unconfirmed submission before risky dispatch,
uses bounded passive recovery for recognized transient navigation observations,
and reports safe operation/error/recovery diagnostics. It never repeats Search or
a model decision during recovery and keeps existing consent, budgets, sign-in,
source validation and review-before-save. Frontend/backend UI versions are both
`2026-10-14.1`. No tests, static validation commands, browsers or API calls ran for
this checkpoint. See [SEARCH_HANDOFF_FIX.md](SEARCH_HANDOFF_FIX.md) for user-run
scenarios and optional regression commands.

## Search submission and source integrity - 2026-10-13, verification pending

The latest two user1 website jobs confirmed three shared faults: widget Done was
misclassified as Search; long evidence links and heading-first capture exhausted
the source budget before prices; ordinary headline requests wandered into site
search. Revision v18 uses actual submission semantics and starting-page-first
collection scope. Collector v2 balances coherent record bundles, preserves bounded
record identifiers, and prioritizes opened detail bodies. Source validation repairs
only uniquely bound URLs. Extractor v11 independently checks explicit price/rating
bounds and units/basis; unresolved criteria remain read-only source previews, not
matched/saved records. Capture failures pause with specific diagnostics, and a
confirmed empty search skips extraction. No new paid routing call or model change.

Frontend/backend versions are both `2026-10-13.2`. Static checks only; tests, token
comparisons and live hotel/news acceptance remain with the user. See
[SOURCE_WORKFLOW_FIXES.md](SOURCE_WORKFLOW_FIXES.md) for commands and scenarios.

## Single-run Website Studio workflow - 2026-10-13, verification pending

The user confirmed the v1.1 fixes worked and created `backend_update_v1.2`.
This checkpoint connects the existing browser-agent-to-extraction chain to one
initial Run workflow action. Manual search/link/current-page tools are retained
under Advanced, rather than invoked in sequence. Requested sign-in/MFA waits for
the user; agent pauses keep the same budgets. Final preview approval is retained
before saving. Generic collection intent is carried by the existing model decision
instead of an additional paid router. The configured model, compact navigation
context and full-source extraction separation remain unchanged.

Frontend and backend UI versions advance together to `2026-10-13.1` and the
agent prompt reports v17. Static verification only; tests and live comparisons
remain with the user. See [UNIFIED_WORKFLOW_GUIDE.md](UNIFIED_WORKFLOW_GUIDE.md).

## Native submit visibility regression - 2026-10-13, rerun pending

User verification reported 382 passes and one failure: the smaller form context
removed a native submit labelled Continue before the model could choose it. The
injected test model raised while finding the missing control, leaving no recorded
action. Revision v16.1 retains native submit/image controls irrespective of label;
it does not treat Continue as a ready Search candidate or relax date/guest checks.
Added focused projection regressions. Static checks only; user rerun remains pending.

## Autocomplete state and navigation input size - 2026-10-13, verification pending

The latest live trace confirms v15 was deployed, but no destination fill/option
selection ran. Dates/occupancy verified; repeated destination opener clicks consumed
14 decisions and 56,081 navigation input tokens without a Search or retained source.
The UI-only trace does not establish the raw input value or why suggestions were
missing. Inspection found a genuine misleading state: uncommitted autocomplete
always said select_option, including empty fields; compaction hid empty values.

Revision v16 distinguishes fill, open, wait and fresh-option selection; explicit
empty values remain visible, unknown values remain unknown. A known literal value
in a fresh editable native form can be filled locally with read-back; ambiguous
suggestion choices remain agent/model-led. Foreground widgets, stale values,
readonly/disabled/unknown fields, MFA and cancellation do not authorize that fill.
The existing verified Search/result handoff remains; no hardcoded city/website recipe.

Recognizable form phases target 6,500 JSON text characters with a 3,500-character
observation. Required values, fresh controls, associated ambiguity choices and
calendar/counter confirmation evidence must fit; otherwise retain the original
14,000/8,000 ceilings or stop explicitly. General browsing keeps its rich context.
Shorter instructions/control hints, geometry only when an image is actually sent,
and local-only packing diagnostics further reduce navigation input. Character
budgets are not token counts. Actual input/cached-input/output usage stays reported;
no live token-saving percentage or acceptance is claimed. Full extraction sources,
original requests, model, strict schema, consent and budgets are unchanged.

Static checks only; regression tests and live verification are left to the user.
OpenAI Docs informed context filtering and fewer redundant calls:
[Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization).

## Prepared-search handoff - 2026-10-13, user verification pending

The v14 trace completed the requested form in eight actions. Action nine opened
the "New York hotels" catalogue link instead of submitting the form. The new
document reset the fields: 25 model decisions used 99,050 input tokens and retained
no agent pages. A later manual capture was the city catalogue, not stay-specific
results; extraction correctly reported unavailable price/availability evidence.

Revision v15 identifies the actual native Search button through DOM form ownership
and fresh read-back of every requested form value. For literal hotel-listing searches,
the ready-form submit and rendered-results handoff are local runtime actions, not
extra model calls. Unfamiliar widgets remain agent-driven; explicit linked-detail
requests keep their model-led collection path. A bounded passive loading wait never
resubmits Search. Busy, ambiguous, changed, interrupted or unconfirmed results stop
for attention. Structural result hints do not prove availability, price or completeness.

Search candidates and collection phases take priority in the existing compact model
context. Full source capture, original instructions, source validation, review-before-
save, model and paid-call limits remain unchanged. No frontend-version bump needed.
Added scoped-form, eight-paid-step handoff, interruption and negative regressions;
only static checks performed. Tests and live acceptance remain with the user.

OpenAI Docs informed moving already-known terminal operations into runtime code:
[Function calling](https://developers.openai.com/api/docs/guides/function-calling).

## Model decision waste and value bindings — 2026-10-13, user verification pending

The v13 trace used 30 calls (122,257 input tokens; 6,070 output tokens), no retained
pages and no Search submission. Thirteen decisions failed redundant request-quote
validation; four tried native `select` on custom options/comboboxes. Canonical
destination/date checks were also poisoned by optional bindings to action targets.
The observed roughly 4,075 input tokens per call reflect the prior context reduction,
not proof that the complete workflow is efficient or successful.

Revision v14 reuses original grounding for unchanged known fields, makes declaration
updates atomic, and ignores invalid optional bindings that would replace actual
value fields. New/changed criteria remain checked. Current control capabilities
and widget-focus hints clarify the next useful action; brief read-only autocomplete
settling avoids paying immediately for stale suggestions. Three consecutive invalid
declarations stop further waste. Model, call/time/output budgets and source capture
remain unchanged. No frontend-version bump; server/frontend IDs stay synchronized.

Added a ten-decision offline hotel workflow fixture and focused grounding/binding/
capability/suggestion regressions, not run by the author. Static checks only;
live completion and fewer than fifteen decisions still need user verification.
The supplied two-night/October 29–30 prompt was internally inconsistent; the next
verification example uses October 29–30 as one night, as allowed by the user.

OpenAI Docs informed the contract simplification:
[Function calling](https://developers.openai.com/api/docs/guides/function-calling).

## Navigation cost and completed-search fixes — 2026-10-12, user verification pending

Revision v13 fixes a proven v12 false rejection: after the correct city suggestion
was clicked, its fuller canonical city/country label did not equal the short user
value. Verification now accepts that actually selected option's exact words/order,
with punctuation differences only. Untyped/unselected, wrong-city, airport/AI,
retyped, reopened and stale-document choices remain unverified. Internally blocked
Search attempts are no longer reported as clicks that happened on the website.

Navigation model requests now use a separate task-focused projection: at most
14,000 JSON text characters, including an 8,000-character observation, three short
recent outcomes and compact field readiness. Original instructions and requested
values are kept exactly; fresh required field/date IDs cannot be silently dropped.
Relevant visible links/options are prioritized, with explicit coverage omissions.
Full live observations, tool references, captured sources and saved evidence are
unchanged. This is a self-contained request, not a delta stream requiring hidden
conversation memory. The previous duplicate history-compaction helper was removed.

Consented screenshots are adaptive, not generated/sent for every DOM-sufficient
step; unchanged layout images are suppressed. Model decision descriptions and
requirement declarations are shorter, without increasing the output budget or
changing the configured model. Timing, payload-character and actual input/output/
cached-input diagnostics support comparing the next run. Cached input is a subset
of the input count, not additional usage or a promise of free tokens.

OpenAI Docs informed context filtering, concise output and selective images:
[Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)
and [Images and vision](https://developers.openai.com/api/docs/guides/images-vision).
No tests, browser sessions or paid calls were run by the implementation author.
Live search → capture → extraction → review still requires user verification;
no measured speedup, savings percentage or universal-site support is claimed.

## Destination commitment and decision overhead — 2026-10-12, user verification pending

The user reported that v11 entered dates/occupancy but typed the destination without
selecting its suggestion. Code inspection confirmed both destination read-back paths
could prematurely verify matching text. Revision v12 observes scoped autocomplete
choices and keeps the destination pending until a matching choice is committed.
Retyping/cross-document changes invalidate selection proof; plain fields/native
selects remain supported. No arbitrary first match or site-only identifier is added.

Shared v11 diagnostics also showed that popup-bound adults/rooms lost verification
after Done, despite a committed 3-adult/2-room header, blocking Search before click.
The revised checker can use fresh same-document/frame summary evidence when those
controls disappear. Conflicting/absent summaries and changed documents are not
accepted. The logged 42.2 active seconds preceded a pause; the later ten-minute
session expiry was not ten minutes of active model execution. Expiry guidance now
retains that last pause reason instead of masking it with only a generic deadline.

Reuses a per-browser-session HTTP client and strict schema, with per-request timeout
bounds, no retries and explicit close on worker exit. Reduces model-only action
history to bounded summaries while preserving full action/source evidence. Numeric
input-size diagnostics support comparing future runs without retaining request text.
Model/network/image/call budgets unchanged. Added mocked/local regressions and guide.

Static checks only; no tests, browsers or paid calls run by the implementation author.
Actual dropdown behavior, successful extraction and live latency improvements still
need user verification. This is not universal website or production acceptance.

## Results-to-extraction handoff — 2026-10-12, user verification pending

The user's v10 trace verified all five requested hotel form fields, including
3 adults and 2 rooms, and observed Search results. It then paused before capture:
the model chose `finish` with a non-complete redundant flag, and an earlier finish
rejection contributed to the pause. All 28 model decisions were valid; API-call
time alone was 87.624 seconds. This did not establish end-to-end extraction.

Revision v11 removes that extra completion flag. `finish` captures source content
after actual form/Search checks, then uses existing extraction/filtering/review.
Rejected-finish streaks reset with real form/submission progress or explicit Resume;
call/time limits remain. Added focused mocked/local regression cases and updated
manual handoff instructions. No model/budget/network change or automatic provider
retry. Broader loop/context/screenshot performance work remains separate.

Static checks only; no tests, browsers or paid calls run by the implementation
author. Live listings, rule correctness and exports still need user verification.

## Semantic numeric controls — 2026-10-12, user verification pending

The v9 user run still had no usable occupancy actuators and incorrectly labelled
hotel-card review counts as steppers. Tightened unknown-icon recognition to isolated
quantity regions and added native number/ARIA spinbutton support with bounded,
read-back-verified keyboard steps. Physically rendered recognized counters can be
operated despite accessibility-only `aria-hidden`; hidden/inert/credential controls
remain excluded. Native numeric displays can supply read-back for sibling actuators.

Added visible tag/role/type and child-button evidence plus persisted structure-only
diagnostics, without raw DOM, labels, actual values or images. Diagnostic probes do
not consume compact control context. Added local/mocked regression cases and updated
the manual guide. Static checks only: no tests, browsers or paid calls run by the
implementation author. The exact live widget structure and successful end-to-end
search remain pending the user's verification, not established by these changes.

## Counter observation and screenshot flicker — 2026-10-11, user verification pending

The v8 run correctly retained destination, dates and requested occupancy, but its
inventory exposed no usable steppers. Revised generic detection to preserve leaf
buttons inside clickable wrappers, read quantity text inside those rows and resolve
same-document SVG reference metadata. Unknown icon direction is explicitly reported;
only a model-selected fresh actuator may be tried, with each numeric step checked.
No arbitrary counter retargeting or fixed adults/rooms value was introduced.

Removed live-page screenshot ID overlays; CSS-scale screenshots retain accompanying
DOM rectangles, consent, masks and in-memory handling. Added nested-widget/generic-
quantity/icon/read-back regressions and manual varied-count scenarios. Static checks
only; no pytest, browsers or paid calls run by the implementation author. The live
widget's exact DOM was not captured, so actual site success still needs verification.

## Observation continuation — 2026-10-11, user verification pending

The inspected v7 run rejected two final messages on its first decision, then
paused on a valid second decision merely to request another observation. Revision
v8 selects a unique independently validated decision across final messages,
deduplicates identical decisions and still rejects conflicts or invalid JSON-like
alternatives. Observation-only pauses become read-only inspection and normal
budgeted continuation, bounded against repeated unchanged refreshes. Actual human
handoffs remain. Explicit resume supplies the last safe decision-failure metadata.

Added offline multi-message/continuation/handoff/budget regressions and updated
the diagnostic guide. Static checks only; no pytest, browsers or paid model calls
run by the implementation author. Live date/occupancy completion is not yet proven.

## Decision message parsing — 2026-10-11, user verification pending

The user-run v6 scenario completed its model responses below the token budget,
but rejected decision JSON. Exact field errors were not retained. Revision v7
now selects an explicit final-answer message instead of parsing concatenated
commentary/final text, and reports bounded schema-field paths/error codes without
raw values or output text. Multiple possible decisions are not guessed between.
Added message-phase/validation and opt-in UI regressions. No tests, browsers or
paid model calls were run by the implementation author. Whether message mixing
caused the inspected run remains unconfirmed until the next user-run attempt.

## Browser-agent decision diagnostics — 2026-10-11, user verification pending

Removed the hidden 30-second inference cap; the configured timeout is bounded
by the remaining active budget. Strict responses are checked for completion and
refusal before action JSON parsing. Failed calls preserve reported usage and get
specific failure codes rather than one generic browser/model message. Safe
per-decision metadata is shown in the dashboard and retained in job history while
the session is live, including through progress/final writes and restarts.

No model, output-token budget or automatic retry was added. The original third-
decision failure cannot be proven from the older generic log; a fresh run is
needed. Added offline transport/graph/persistence and opt-in UI regression cases,
plus [BROWSER_DECISION_DIAGNOSTICS.md](BROWSER_DECISION_DIAGNOSTICS.md). No pytest,
browser or paid model call was run by the implementation author.

## Cleanup A — 2026-10-11, user verification pending

Removed the unused destination regex and duplicate dev-only `httpx` declaration;
runtime `httpx` remains. Extraction/enrichment now share source-text normalization,
and the browser task reuses runtime control flattening without changing behavior.
CLI status lists implemented capabilities instead of historical checkpoint/test
scores. Updated current guides, retaining older evidence as historical context.
The dashboard DOM collector is canonical; the extension keeps a generated copy
with a read-only drift check and explicit `--write` synchronization command.

Added cleanup regressions and [CLEANUP_GUIDE.md](CLEANUP_GUIDE.md). No tests,
live browsers or paid model calls were run for this checkpoint. Existing prompts,
budgets, navigation paths, networking modes and policy behavior were not changed.
The browser-agent decision failure and larger shared-browser/session/frontend
refactors remain pending. Current-year resolution and opt-in screenshots are
implemented in the dynamic browser revision; earlier DOM-only entries below
describe their implementation at that earlier date, not the present feature set.

Historical baselines removed from runtime status: LangGraph 20/38 passing and
CrewAI 21/38 passing. These are dated earlier observations, not current acceptance.

## LangGraph dynamic browser agent — 2026-10-09, user validation pending

Added a native LangGraph observe/decide/act loop with typed model decisions and
generic visible-control tools. The agent can adapt after each browser action,
retain source pages, pause for user input and resume without resetting its used
budget. Dashboard controls expose paid consent, live activity and action/read-back
evidence. Existing extraction/source validation, preview approval, exports and
optional rule/event handling remain downstream. Normal/restricted networking and
existing sign-in flows are unchanged.

Navigation uses the user's configured OpenAI model with no provider retry/fallback.
Limits: 30 attempted decisions, 300 active seconds, at most six retained source
pages. Partial captures collected after a pause require partial-preview approval.
This implementation observes DOM/text, not screenshots; it is not universal site
automation or a production-readiness claim. CrewAI browser-agent parity is pending.

Added offline/mocked and opt-in local browser/UI regressions plus
[BROWSER_AGENT_GUIDE.md](BROWSER_AGENT_GUIDE.md). No tests, external browsers,
paid model calls, commits or pushes were run during implementation. Historical
test totals below do not validate this new checkpoint.

## UI stability and checkpoint activity — 2026-10-05, user validation pending

Replaced the browser-less/intermediate custom poll render with one coherent update.
Unchanged source/navigation/result regions retain their DOM nodes and disclosures;
stale selection responses are ignored. Removed automatic checkpoint expansion.
Added rotating decorative rings for the actual running step, stationary status glyphs,
and short clickable stage explanations. Waiting/review and reduced-motion states are
explicitly static. Hotel-demo stage updates also retain opened details and avoid
feedback-induced scrolling. Cards expose all output fields, filled/missing counts and
known field-check reasons; blanks no longer claim source absence. Source diagnostics
are collapsible. The larger guided-layout design awaits user preference; unresolved
acquisition gaps require a fresh expected-field/job example, not a cosmetic patch.
No tests, browsers or model calls run by the assistant. Added offline contracts and
opt-in isolated UI/browser fixtures. Follow [UI_USABILITY_GUIDE.md](UI_USABILITY_GUIDE.md).

## Source quality and preview — 2026-10-05, user validation pending

Inspected the reported saved sports proposal and its source blocks. Missing detail
headlines, inline-link paragraph splitting, display-quote value mismatches and
substring-only title validation explain the wrong titles and missing excerpts.
Current-page and detail enrichment share the collector but cover different content.
The collector now retains content headers, heading/body roles and intact inline text.
Source-backed corrections require unambiguous captured headings/URL bindings or
literal wrapper removal; corrections and per-link rejection reasons are reviewable.
Both frameworks share these changes. Added generic cards/table previews, a focused
record/evidence dialog with back/previous/next navigation, and server-state-driven
activity indicators that distinguish running from waiting. Existing models, consent,
network modes and credentials are unchanged. Added regression fixtures; no tests,
live browser sessions or paid model calls run by the assistant. Follow
[SOURCE_QUALITY_GUIDE.md](SOURCE_QUALITY_GUIDE.md) for user-run acceptance checks.

## Topic review correction — 2026-10-05, user validation pending

Unrelated topic candidates are excluded before optional cell validation; uncertain
topic candidates are shown separately from invalid source records. Verified relevant
records retain blank optional fields instead of invented classifications. Shared
identity selection supports title/name aliases independently of column order; missing
or unsupported identities and filter/rule values still reject a record. The dashboard
shows review counts and distinguishes no matches in captured content from validation
failures. No-match jobs save no proposal or export; a setup button copies source/query
for a new, explicitly consented browser/link-discovery session without launching it.
Counts are retained in approved snapshots. Both frameworks use the shared correction.
Regression fixtures include the 20-unrelated-record case, partial Soccer previews,
uncertain/missing relevance, protected fields, identity aliases and hotel price ranges.
No tests, live browsers or paid model calls were run by the assistant. Follow
[TOPIC_REVIEW_GUIDE.md](TOPIC_REVIEW_GUIDE.md).

## Checkpoint 4A: human-completed email verification — user validation pending

Added email-code/login-link sign-in without a password. One email entry/continue
attempt hands off to the account holder in the original browser. Navigation and
capture pause until explicit confirmation; visible-indicator verification remains
distinct from operator attestation. Obvious reauthentication clears pending actions.
Fox News is the selected live acceptance target; no Fox-specific DOM selectors or
successful integration are claimed. No inbox access, OTP submission, session-cookie
persistence, tests, live browser runs or paid calls were performed by the assistant.
Follow [EXTERNAL_LOGIN_GUIDE.md](EXTERNAL_LOGIN_GUIDE.md). 4B/4C remain pending.

## Checkpoint 3: reviewed search navigation — user verification pending

Corrected null options in the shared collector and added sanitized, stage-specific
browser/capture diagnostics. Added search/calendar opening actions, fully dated
calendar choices, accessible-name discovery, stale-control rejection, fill/select
read-back, declared site-requirement checks before submission, and navigation
evidence/history in the dashboard and saved diagnostics. Opened controls require
another separately consented and reviewed planning step. Result observations never
claim that the site's filters or returned records satisfy the request. Both browser
network modes and model/credentials are unchanged. No tests, live browser sessions
or paid API calls were run by the assistant. Follow
[SEARCH_NAVIGATION_GUIDE.md](SEARCH_NAVIGATION_GUIDE.md). The three legacy
rule/event fixture failures were intentionally left unchanged at the user's request.

## Checkpoint 2: starting-page retention and detail enrichment — validation pending

Implemented retained index capture plus up to five approved detail captures in
one extraction call. Page-specific evidence is validated before URL-based
reconciliation. Missing fields keep detail-source provenance; starting records,
unmatched details and conflicting filter/rule source variants are preserved.
User filters and the preview limit run after reconciliation. Live per-link
coverage, result status, source/conflict evidence and export metadata were added.
Both frameworks share the implementation. No tests, browser runs or paid calls
were performed by the assistant. Follow
[DETAIL_ENRICHMENT_GUIDE.md](DETAIL_ENRICHMENT_GUIDE.md) for user validation.
Checkpoint 3 is now implemented within the bounded scope described above.

## Checkpoint 1: shared source inventory — manual validation pending

Implemented one collector for browser capture, link discovery and extension
handoff. Removed the short-main-content early exit, merged repeated URL labels
with their linked headings, distinguished neighbouring record groups, and added
bounded loading/scrolling with visible coverage. Optional mis-associated metadata
is blanked with evidence issues; identity/filter failures still reject records.
Both browser network modes are unchanged. Added offline and opt-in local DOM
fixtures; the assistant did not run tests, browsers, sign-ins or paid API calls.
Follow [SOURCE_INVENTORY_GUIDE.md](SOURCE_INVENTORY_GUIDE.md) for verification.
Detail enrichment and verified dynamic search actions remain the next checkpoints.

## Chromium and optional credential-flow sign-in: expanded, unverified

Added a visible, isolated Chromium source with manual sign-in or one optional
credential flow. Automatic mode can discover one visible sign-in entry, handle
POST/JavaScript buttons and email-first screens, and follow only exact
operator-approved identity origins. An optional signed-in indicator can confirm
the result; a submit click alone is never reported as success. Account-scoped
capture/cancel controls,
session-expiry cleanup, credential exclusion/redaction, public-network safety
proxy and explicit resource-origin permissions are implemented. Browser capture
precedes the model call; approvals still save the captured preview. Offline and
browser tests were added but not run by the assistant; static lint/format checks
passed. No external login, credential submission or paid API call was performed.
Read CUSTOM_WEBSITE_GUIDE.md for validation and limitations, including unsupported
passwordless/SSO variants, complex login widgets and automated pagination.

## Custom Website checkpoint: implementation complete within bounded scope; validation pending

Added a separate general extraction workspace: optional instructions, dynamic fields,
explicit range filters without hotel policy limits, evidence-backed previews, approval,
private SQLite/JSON snapshots, shared exports, and optional rules/NATS summary events.
Both LangGraph and CrewAI Flow orchestrate the shared services. Public HTML fetching
has public-IP pinning and robots checks; an authorized pasted-text mode handles content
the static reader cannot retrieve. No tests or paid calls were run by the assistant.
Follow CUSTOM_WEBSITE_GUIDE.md for manual validation and precise limitations.
Automated external login, JS rendering, pagination and custom-event consumer verification
remain unimplemented. The legacy Hotel demo's policy and receipt workflow are unchanged.

## Result exports: implemented, user verification pending

Added Excel, UTF-8 CSV, JSON and JSON Lines downloads, full-run/filtered selection,
run-specific filenames, source fields, and Excel metadata/rule-decision sheets.
Exports read only account-owned saved results and do not call a model. Text is
written explicitly in Excel; CSV formula-like values are escaped. Added bounded,
schema-flexible export utilities and offline regression coverage. Tests were not
run by the assistant. Follow EXPORTS_GUIDE.md to install and verify this checkpoint.
Custom Website extraction is the next checkpoint and is not implemented here.

## Current: dashboard usability and local account controls — acceptance pending

Implemented a light navy/teal dashboard with separate Search studio, Run history,
API connection and admin sections; readable proposal review, stage labels, result
metrics, outcome filtering, policy/clarification feedback, and separate sign-in/
registration screens. Added optional user-owned OS credential storage, explicit
first-admin setup, role/status controls, session revocation and secret-free audit
events. No browser verification, tests or paid calls were run by the assistant.

Use VERIFICATION_CHECKLIST.md for the user-run acceptance sequence. Prior supplied
live semantic baselines were LangGraph 43/44 and CrewAI 40/44; known failures remain.
These are historical model results, not verification of the new UI/account changes.
Current implementation status and remaining work are in PROJECT_PLAN.md. Hosting
is deferred; the external adapter and final starter-kit handoff remain unfinished.

## Historical entries below

The entries below preserve earlier evidence and scope decisions; statements such
as "dashboard deferred", session-only-only keys or earlier model counts are not
the current scope. Do not delete previous failures or infer a new passing result.

## Local accounts and 100-hotel catalogue: user verification pending

Expanded deterministic seed data to 10 major US cities with 10 hotels each,
preserving original records. Added individual local account registration/login,
salted password hashing, UUID-scoped data and NATS streams, session-memory API
keys with no environment fallback, and a global one-job execution limit.
Existing shared artifacts are preserved and are not automatically assigned to
new accounts. See LOCAL_ACCOUNTS.md. Tests and paid calls were not run for this change.

## Dashboard MVP: development handoff, user verification pending

Added a separate loopback FastAPI dashboard over shared proposal, revision,
execution and tool services. Includes structured and paid opt-in model planning,
both frameworks, explicit review/approval, bounded background jobs, stage polling,
results/rule decisions, JSON/CSV exports and the latest 100 dashboard jobs.

Login, session expiry/logout, same-origin CSRF checks, bounded request bodies,
trusted hosts and a server-configured portal target protect the local demo.
Job restart recovery never replays side effects. CSV exports neutralize formulas.
Windows setup/launcher scripts start owned local services without storing keys.

No tests, UI/browser sessions, paid API calls or Git commits were run for this
checkpoint. Python lint/format checks only. User verification and known semantic
limitations are documented in DASHBOARD_GUIDE.md. External website integration,
production identity and durable multi-user execution remain out of scope.

## Current: OpenAI-only migration and prompt v3 (user validation pending)

Both frameworks now use the shared OpenAI Responses adapter for live planning.
CrewAI forwards its actual Agent/Task messages through the bounded bridge.
Ollama code, provider-specific tests and setup guide are removed; installed apps
and downloaded models are untouched. Earlier entries below are historical and
may reference retired providers or superseded approval/status information.

Prompt v2 user results exposed three strict-comparison classification failures.
Prompt v3 clarifies that these require input, rather than unsupported-filter
rejection. Original test expectations are preserved. No tests or paid calls were
run for this migration; follow OPENAI_SETUP.md. Do not infer acceptance from
earlier staging or local-provider results.

## Checkpoint 6: CrewAI implementation, developer review pending

Implemented an independent CrewAI Flow plus one Agent/Task/Crew for local Ollama
planning. Reuses validated hotel inputs and browser/storage/rules/NATS services,
not the LangGraph runner. Shared CLI now offers crewai plan/review/execute.
Version-2 proposals bind framework into approval; legacy v1 LangGraph hashes are
preserved. Added bounded Crew task-message transport and disabled CrewAI tracing.

User-reported staging verification: 222 passed, 39 skipped, 40 warnings in the
full browser/NATS regression run. User live semantic evaluation: 21 passed,
17 failed, 494 repeated upstream CrewAI deprecation warnings. Thirteen semantic
failures accepted incorrect plans; three misclassified unsupported requests;
one failed generically. No general-language reliability acceptance is claimed.
The previous LangGraph baseline remains 20 passed / 18 failed; both LangGraph
reviewed paths were subsequently manually demonstrated successfully by the user.

Final handoff adds the CrewAI guide and checkpoint status; no tests were rerun
at the user's request. Actual-repository tests and manual CrewAI structured and
model-assisted reviewed runs remain pending. No commit, push or branch change.
See CREWAI_GUIDE.md for setup, customization, recovery and acceptance commands.

Remaining: developer review/acceptance of CrewAI, then checkpoint 7 clean-checkout
starter-kit reproduction. Generic website discovery and a dashboard remain deferred.

## Integration re-verification after Docker startup

The local NATS container was healthy. `pytest --run-browser --run-nats` passed:
204 passed, 39 skipped, one existing Starlette/AnyIO deprecation warning.
The skips are 38 live semantic evaluations and one live-model integration case;
no model requests were made. The previously failing broker-dependent tests now
pass, including saved-plan real-browser/storage/rules/NATS execution and zero
matches. Manual review of the new plan/review/execute UX remains for the user.
This does not change the documented 20/38 model interpretation baseline.

## Reviewed-plan handoff (current)

User evidence: local Qwen3 8B ran on GPU and completed the portal-to-NATS workflow
with four records, two matches and two verified receipts. Expanded semantic
evaluation: 20 passed, 18 failed. Preserve that baseline; broad language parsing
is not accepted. Earlier "no live inference" statements are historical.

Added structured and model-assisted proposal creation, review, revision-bound
approval, fixed saved-target execution, policy/date/expiry checks and single-attempt
claims. Execution starts at graph validation and never replans. Results are kept
beside proposals under the ignored data directory. Legacy direct runs remain
explicitly documented as bypassing this local review interface.
See PLAN_EXECUTION_GUIDE.md for commands, extension boundaries and recovery limits.
No prompt/model changes or semantic test expectation changes are part of this work.
CrewAI and final clean-checkout starter-kit acceptance remain separate work.

Verification so far: 21 new saved-plan unit/CLI cases pass. Full local suite
attempt: 198 passed, 39 skipped, 6 broker-dependent failures because Docker's
Linux engine/NATS were unavailable. These are not accepted as passing; rerun
after Docker/NATS start. Lint, format and whitespace checks passed.
No new live-model calls, model downloads, commits or pushes were performed.

## Completed checkpoints

- Checkpoints 1-2: foundation and portal merged into main.
- Checkpoints 3-4: extraction/storage and rules/NATS merged in commit bfbdc08;
  previous full suite: 79 passed. User owns all commits and pushes.

## Checkpoint 5a: LangGraph scaffold

Branch `langgraph-agent`, clean at initial inspection.
Implemented explicit simulated planning and a real LangGraph state graph calling
the existing browser, persistence, rules and messaging tools. Missing/invalid
plans stop before tools; failures stop later actions; verified receipts are
correlated by extraction run and event IDs.

No live model integration, arbitrary-language interpretation, agentic tool-choice
loop, durable graph resumption or dashboard is claimed. Checkpoint 5 remains
incomplete until approved model access and real-model evaluation are available.

Verification on Python 3.11.16:

- Full suite `pytest --run-browser --run-nats`: 101 passed, no skipped tests.
- Default suite: 94 passed, 7 skipped (opt-in browser/broker cases).
- New real-tool integration exercised the LangGraph graph with scripted planning:
  4 NYC records, 2 matches, 2 acknowledged events, and 2 verified receipts.
  Also tested the no-match path skipping broker operations.
- 21 graph/planner/CLI unit cases cover success, missing fields, invalid plans,
  every tool-stage failure, error redaction, relative dates and receipt verification.
- Ruff lint passed. One upstream Starlette/AnyIO deprecation warning remains.
- External tracing disabled for graph execution. No model inference or paid API
  calls made. Temporary test portal stopped and TEST stream removed afterward.
- Packaging and final formatting/whitespace checks recorded at handoff.

No commit or push performed. Checkpoint 5a is ready for review; checkpoint 5 is
still pending approved model integration and real-model evaluation.

## Checkpoint 5b implementation: live adapter, offline verification

Implemented on the existing `langgraph-agent` branch, preserving uncommitted 5a
work. User explicitly confirmed approval is pending and requested offline-only
implementation/testing. No personal API key was read and no live model request
was made. No Git commit, push or branch change was performed.

Added:

- OpenAI Responses structured-output adapter using the actual SDK, replaceable
  behind the provider-neutral Planner/Candidate contract. No model ID is assumed.
- Explicit live CLI mode and API-use permission flag, natural-language requests,
  plan-only preview, missing-information/unsupported outcomes, and safe errors.
- Code-enforced policy limits loaded from config/rules.yaml in live mode; request
  preferences may tighten but cannot loosen them. Effective rules are reported.
- Bounded request length, output tokens, retries and timeouts; no automatic retry
  of browser/storage/messaging stages and no fallback to simulated planning.
- Safe metadata/token reporting, disabled graph tracing, suppressed SDK payload
  logging, pinned OpenAI endpoint and store=False (not a zero-retention claim).
- SDK MockTransport tests plus the mocked-model -> real Chromium -> SQLite/JSON
  -> rules -> NATS path. Live semantic/end-to-end tests are separate and opt-in.
- Updated step-by-step guide, safe configuration example and provider replacement
  instructions. Model interpretation remains unverified until live tests pass.

Verification in staging, then the actual repository on Python 3.11.16:

- Default suite: 144 passed, 21 skipped (browser/NATS/live-model opt-ins).
- Full local suite `pytest --run-browser --run-nats`: 152 passed, 13 skipped.
  The 13 skips are exactly 12 live semantic cases plus 1 live end-to-end case.
- Both simulated and mocked-SDK integration paths extracted 4 NYC listings,
  matched 2 and verified 2 receipts; both also passed zero-match routing.
- One upstream Starlette/AnyIO deprecation warning remains.
- All 50 SDK/configuration/permission regression cases passed without network
  model calls. Ruff lint, formatting (36 files), Git whitespace checks and both
  source/wheel package builds passed. Locked dependency sync succeeded.
- CLI smoke checks verified status, simulated plan-only, and missing-city exit 2.
- Git ignores .env/.env.local, data exports and local evaluation artifacts;
  only the sanitized .env.example is tracked among environment files.
- Temporary portal/test data and uniquely owned TEST streams are isolated from
  user demo records; the already-running NATS service was not replaced.

## Remaining acceptance and user review

Review the changed guide and run the offline commands from the repository.
Checkpoint 5 is NOT marked complete: a configured local Ollama model or approved
hosted model and successful live semantic plus end-to-end evaluations remain
required. Commands and expected evidence are in LANGGRAPH_GUIDE.md and
OLLAMA_GUIDE.md. Credentials stay local, never in chat or Git.
The status command reports this pending milestone, not runtime service health.
Dashboard, durable graph resumption and autonomous website navigation are not
required for this checkpoint and are not implemented. CrewAI remains checkpoint 6.

## Ollama local-model option

Added a local Ollama planner using the shared structured plan contract, fixed
localhost endpoint, bounded context/output and no cloud-provider fallback.
The supported starting models are qwen3:8b and qwen3:4b. The setup guide includes
disabling Ollama cloud features, GPU checks and explicit model downloads.
Local inference requires neither an OpenAI key nor the paid-API permission flag.
Offline adapter tests and a mocked-Ollama real-tool integration are included;
the existing opt-in semantic and full-workflow evaluations support either provider.
No model has been downloaded or real Ollama inference verified at implementation
time. Checkpoint 5 remains pending those evaluations and user review.

Repository verification: `pytest --run-browser --run-nats` completed with
182 passed and 13 skipped (the opt-in real-model evaluations). The mocked local
adapter exercised the actual browser/storage/NATS workflow. Ruff lint and
format checks and Git whitespace validation passed. One existing upstream
Starlette/AnyIO deprecation warning remains. No inference, commit or push occurred.
