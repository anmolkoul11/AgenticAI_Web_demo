# Use an agent in your normal Chrome or Edge tab

## Larger adult/room adjustments - 2026-11-09

Restart backend **v20.30**, reload Companion **0.5.20** and refresh the website
before a fresh task. The earlier executor allowed targets up to 30 but rejected
changes of more than ten increments; this could block 18 adults from the shown
six-guest starting state.

It now supports up to 30 individually verified steps, within the website's
observed bounds and the existing 0–30 application target range. Controls are
not clicked blindly: each effect is read back before the next step. A genuine
limit or unsupported control gets a specific reason and pauses once. An older
loaded helper gives an update message before attempting a larger change.

Manual check: New York, December 24–30, 2026, 18 adults and ten rooms. Confirm
the separate counts and applied summary after Update. No tests, validators or
live/provider workflows were run; manual acceptance remains pending.

## User3 room-conflict follow-up - 2026-11-09

Restart backend **v20.29** and start a fresh task. Companion **0.5.19** remains
compatible. The inspected user3 run had confirmed Search; collection stopped
because destination proof was incomplete and returned room evidence conflicted.
Its saved log did not include the actual conflicting values.

The current searched page can now be captured as a read-only source preview when
its heading is absent from the control inventory or new conflicting counts
appear. The document, URL and original request remain bound; uncertain scope
still blocks approval as a confirmed stay match. Availability stock such as
“Only 1 room left” no longer becomes the party's selected room count.

Help details now include expected/observed stay values and bounded supporting
quotes, alongside mismatch field names. Repeat New Jersey, November 28–30,
2026, five adults/three rooms under user3, and inspect both the returned form and
preview evidence. No tests, validators or live/provider workflows were run;
manual acceptance remains pending.

## Website behaviour and form performance - 2026-11-09

Restart backend **v20.28** and start a fresh task. Companion **0.5.19** remains
compatible; this update does not change the extension protocol.

- **Booking.com hotel tasks:** after changing the stay form, verify its values,
  click Search and wait for the returned list. Matching editable values alone
  are not a completed search. An already confirmed current-run Search is not
  submitted again.
- **Tripadvisor hotel tasks:** applied control changes can refresh the same
  page. Fresh matching returned results can be collected without a fictitious
  extra Search.
- **Current-page article tasks:** NYTimes/BBC and other news extraction retain
  the existing current-page path. Unknown websites use observed controls and
  result transitions rather than a guessed site recipe.

Known, uniquely observed guest controls can now use their requested numeric
targets without a new model decision for each opener/counter. Ambiguous controls
retain model fallback, every native counter step is read back, and missing child
ages are still left to the user. The technical details show the selected website
and interaction mode.

If a Booking heading proved the destination but disappeared from the next
control inventory, collection re-reads a fresh source heading on that same
document before rejecting it. Previous quotes are not treated as fresh proof.
No tests, validators, live workflows or provider calls were run; behaviour and
speed still require manual acceptance.

## Capturing returned sources with uncertain stay details - 2026-11-09

Restart backend **v20.27**, reload Companion **0.5.19** and refresh the website.
A confirmed Search can now hand off its current result list as a **source
preview** when returned stay details are still uncertain. Previously the agent
allowed this handoff but the full-list collector blocked it before the first
card, misleadingly referring to a “next result page.”

Preview permission is tied to the actual searched document, its result URL and
unchanged returned facts. Capture/scroll does not verify availability or promote
the original form values into result evidence. An unverified preview stops
before additional result pagination and exposes the retained cards for normal
read-only review; existing stay/price/save checks remain in force.

Literal list cautions such as “Some options have fewer than 4 rooms” are retained
as page context. They do not assert that every hotel has insufficient rooms.
Progress and Help details retain connection diagnostics plus scope status,
unverified/mismatched fields and contradiction codes.

Manual acceptance is pending. No tests, validators, live workflows or provider
calls were run. On the Edison six-adult/four-room search, verify that visible
listings reach preview after Search, inspect room/stay warnings, and compare
source-card count with eligible records before approving a save.

## Full collection and calendar follow-up - 2026-11-08, manual verification pending

Restart backend **v20.26**, reload Companion **0.5.18** and refresh the website.
**All available listings in this search** is the default again; the temporary
Limited-preview default produced the latest ten-record Tripadvisor result. The
normal search inventory remains separate from collection-only pagination.
More results require additional paid extraction batches, within the displayed
record/page/time limits. Those limits and incomplete extraction remain explicit.

The latest Booking loop lost checkout's observed full-year evidence when its
calendar closed; it had not yet attempted adults or rooms. Date proof now
survives only the matching same-document form summary and is invalidated by
edits. A uniquely associated expanded opener can close a multi-month picker
without merging unrelated calendar scopes. Repeated Hotels clicks also no
longer reload the current category, and all-results capture avoids redundant
initial loading scrolls.

Manual check: Edison, November 28–30, 2026, six adults, four rooms, zero children.
Confirm both dates remain verified after closing the calendar, then that guest
counts and Search complete. On Tripadvisor, compare source-card coverage with
the destination-matching records; nearby/sidebar links are not automatically
confirmed matches. No tests, validators or live/provider runs were performed.

## Search regression repair - 2026-11-08, manual verification pending

Restart backend **v20.25**, reload Companion **0.5.17** and refresh the website.
The default is again **Limited preview** (25 records); select **All available
listings in this search** explicitly for expanded scrolling and pagination.
The sections below describe earlier changes chronologically; this default
supersedes the initial All-results default.

Search observes its normal form controls. Pagination priority and result-list
identity hashing are now confined to the later collection phase. Fresh verified
stay dates take precedence over stale draft-calendar markers, and an unchanged
calendar-close action is sent only once before a bounded fallback or pause.
The agent cannot put a guest count or stay date into a hotel destination Search
field merely because the value occurs in the prompt.

Check the normal Booking and Tripadvisor search-to-preview path first. Then
select All results and compare collected source cards with approved records.
No tests, validators, live workflow runs or API calls were performed for this
repair; manual acceptance is pending.

## Collecting the full result list - 2026-11-08, manual verification pending

Reload Companion **0.5.16**, restart the backend (**agent v20.24**, extractor
**v18**) and refresh the website before starting a new task. Under Customize
results, **All available listings in this search** is the default. Choose
**Limited preview** for the earlier small-capture behaviour.

Once the requested search is ready, All results captures cards in windows of
ten, scrolls through the list and follows observed same-origin result pagination.
It retains virtualized cards before scrolling them away, deduplicates repeated
listing identities and preserves separate evidence for each capture. New result
pages must still confirm the requested stay. It does not crawl unrelated pages
or make reservations/payments. The website tab remains open for inspection.

Maximum listings defaults to 5,000. The collector also stops after 100 result
pages or four active collection minutes. Limits and uncertain pagination produce
an explicit partial result; a scope mismatch pauses for review. Progress shows
source cards and result pages, while the dashboard distinguishes captured cards,
extracted candidates and approved records. Reaching the available list end does
not prove that every listing on the website was accessible.

Each source batch uses an additional paid extraction call. Navigation history is
not repeated in these extraction prompts, and scrolling/pagination collection
does not consume extra model decisions. Review completeness and usage before
saving. An interrupted extraction retains earlier successful batches with a
warning; the provider call is not retried automatically.

Manual check: repeat the Raleigh November 28–30, 2026, four adults/two rooms
search. Compare All results against the cards available after scrolling and
pagination (the previous run captured only 16). Check the source count and final
record count separately, then set Maximum listings to 25 and confirm the partial
label. No tests, validators, browser runs or provider calls were executed for
this change.

## Optional prices and visible pricing captions - 2026-11-08, verification pending

Agent **v20.23**, Companion **0.5.15**, pricing contract **v3** address review
job `7dac240c-1f71-45bc-9bb3-8492ca9056af`. Its Virginia stay and USD currency
were verified, but all 25 amounts lacked price-basis evidence. The user confirmed
the visible mode was “Nightly price with fees”; no `price_setting` block survived.
The previous collector only examined a narrow set of controls, preferred ARIA
over visible captions and rejected fallback page-heading wrappers as records.

Capture now reads exact short rendered captions, including plain spans and
accessibility-hidden but physically visible labels, while excluding hidden
menus, unselected radio choices and hotel-card captions. A wrapper with a page
H1 may contain the list's global setting. Coverage records `price_setting_status`
and `price_settings_detected`, so missing or competing captions are explicit.

The request contained no price bounds, nightly requirement or price filters.
An inferred output price nevertheless triggered an unconditional price-review
gate. Plan and save now enforce the same request-aware gate: optional price
uncertainty stays in the record/exports without becoming a confirmed price match
or invented nightly amount. Actual price comparisons, explicitly pinned nightly
fields, and stay-scope mismatches still block. Save re-assesses the retained
sources and equality-checks the approved pricing data. The UI omits nonexistent
price-target counts and retains source-price warnings.

Restart the backend, reload Companion **0.5.15**, refresh the website and start
a fresh workflow. Authored regression cases cover optional-price plan/save,
explicit nightly requests, soft targets, changed scope, page wrappers, visible
versus ARIA captions, hidden/menu/card exclusions and diagnostic metadata.
No tests, validators, browser/application startup or API calls were run.

## Calendar windows and capture handoff - 2026-11-08, verification pending

Agent **v20.22** and Companion **0.5.14** address the next failure observed in
job `525acaae-5641-4a26-bba5-1556da2ebf7c`. Navigation completed in four paid
decisions, but capture preparation closed the read-only guest panel. Its final
passive observation lost adults/children even though post-Update inspection had
verified them. Captured-heading reconciliation also omitted the newer full-date
evidence methods from its allowlist.

Capture now retains the independent guest-row proof only when the document,
applied summary and fresh destination/dates agree. Changed counts, dates,
documents, invalid widgets or missing inspection proof remain unverified. The
date-evidence allowlist now agrees with the navigation observer.

Calendar observation reserves scoped next/previous arrows and date choices in
the bounded inventory. Explicit icon names or a single rendered chevron can
identify direction; arbitrary button order cannot. The runtime reads the two
visible month panels, advances one observed arrow at a time across years, and
pauses if that window does not change. Spillover dates do not count as a third
month panel. This uses no extra model decision for a known month direction.

The source collector retains a selected page-wide price mode such as “Nightly
price with fees,” including its separate evidence IDs. Pricing may use it for a
single otherwise unlabelled current amount. Competing amounts, local labels,
original prices, currency and stay checks retain their independent rules.

Restart the backend, reload Companion **0.5.14**, refresh the website and start a
fresh task. Manually verify a stay beyond the two displayed months, then inspect
the preview's returned guest scope and price-mode evidence. Regression source
covers month windows, crowded calendars, source handoff, changed scope, selected
price settings and ambiguous amounts. No tests, validators, application/browser
startup or live/model/API calls were run; manual acceptance is pending.

## Guest label parity after Update - 2026-11-08, verification pending

Agent **v20.21** corrects a form/result vocabulary mismatch. The real named
steppers expose `adult`, `child` and `room`; the controller recognized those,
but the returned-scope checker used plural stemming that failed for `child`.
A correct zero-child readback therefore remained unverified, leading to another
Update and the loss of visible rows when the panel closed.

Navigation, counter readback and returned-scope checks now share the same field
normalizer. The existing age recognizer is shared too: child ages and ordinal
labels do not supply a child quantity. Real mismatches still block matching.
An unsuccessful readback reports a workflow verification pause, rather than
claiming the request omitted guest values or instructing another Update cycle.

Restart the backend and use a fresh task; Companion remains **0.5.13**. Regression
source uses the actual singular labels and actuator captions, with both 4- and
5-adult requests, zero children, age controls and genuine mismatches. The expected
read-only path is one popup inspection then capture, without another Update.
No tests, validators, browser/app startup or model/API calls were run.

## Calendar draft versus committed dates - 2026-11-08, verification pending

Use agent **v20.20** with Companion **0.5.13**. Restart the backend, reload the
extension in `edge://extensions` or `chrome://extensions`, refresh the website,
then start a fresh task. Older native-ready helpers stop before a paid decision.

The saved v20.19 report selected December 28 successfully at step 5, then repeated
that day twelve times. Only three model decisions ran; the repeats were runtime
actions. The runtime required a complete committed range before advancing from
check-in, although the widget was still waiting for checkout. Its blanket
`calendar_selection_required` override then defeated the executor's selected-day
protection. The 140-control cap could also hide the November form summaries
behind calendar cells, making those missing values look like no progress.

Draft calendar progress now advances a confirmed, freshly selected start to
checkout without marking the committed stay verified. After both picks, an
observed Apply/Done/Close action commits the widget; full dates are read again
before collection. Date dispatch receipts are keyed by physical page/date rather
than viewport/control fingerprints, so an uncertain click is not repeated after
a scroll/rerender. Explicit pre-input rejection can release the intent; Resume
reconciles fresh user changes. Same-page URL updates preserve draft progress,
while actual document navigation clears it.

Both DOM observers reserve inventory space for stay summaries and selected days.
Physically visible date/guest summaries remain readable when a modal applies
`aria-hidden` to background content; unrelated hidden content stays excluded.
An old selected range interior can be reselected only with full summary proof,
or for the next checkout pick after a confirmed draft start. Unrelated date,
price and availability evidence is still checked independently. Help reports the
draft phase/next field without adding field values to its control diagnostics.

Regression sources cover the exact failure (November summaries stay unchanged
until Apply), same-page URL changes, uncertain delivery, a crowded calendar and
old-helper rejection. No tests, validators, browser/app startup or live/model/API
calls were run. Manual verification remains pending.

## Replace a previous stay before guest readback - 2026-11-08, verification pending

Agent **v20.19** addresses the New Jersey/November to New York/December case.
Saved v20.18 evidence showed a guest-summary parsing error: `Rooms/Guests 3 Rooms,
4 Guests` supplied both 3 and 4 as guest totals. Mixed headers are now excluded
from count pairs, while actual labelled row counts and contradictory values
remain visible. A narrow New York/New York City alias fixes the observed heading
mismatch; explicit states and unrelated city names are not collapsed.

Guest readback no longer preempts unresolved or mismatched place/date criteria.
The model focuses on correcting the stay first, and an observed requested city
link can leave the previous city's hotel page without claiming a stay submission.
A unique observed endpoint opener/requested day can run without another model
decision; unfamiliar calendar navigation still uses the model. A day outside the
requested stay dates is rejected before input. Selecting checkout triggers a
bounded passive results wait. Explicit `5 adults only` also requests zero children;
unspecified child counts remain unspecified.

Restart the backend and start a fresh task with the original prompt. Companion
remains **0.5.12**. Source fixtures cover the exact December request, the saved
mixed-header wording, city aliases, old-city navigation, wrong-month choices and
one guest read followed by capture after correcting dates. No tests, validators,
application/browser startup or live/model/API calls were run. Reading saved run
JSON was investigation only; live acceptance remains pending.

## Complete guest widgets before capture - verification pending

Agent **v20.18** addresses the reported `stay_widget_open` pause with rendered
hotel cards. Runtime execution and the model's focused view share one guest
completion rule. An unrelated required global Search field does not block this
step. `widget_scope` describes a control type, so differing counter/choice types
no longer exclude an otherwise uniquely associated Update/Done button.

Matching live guest values lead to the observed confirmation control. When no
confirmation button exists, a unique expanded guest opener can receive Escape
without editing values. The agent waits briefly for automatic result updates,
then re-reads the committed stay and rendered records before collection. Missing
dependent values, unknown ages, mismatched counts and ambiguous buttons remain
unconfirmed. Existing read-only guest inspections can still establish the split
behind a total-guest summary without another Update.

Help's collection diagnostic includes open control IDs, guest field statuses and
the available completion action. Restart the backend and start a fresh task;
Companion stays **0.5.12**. Regression sources cover differing widget types,
required global Search, direct same-page capture after Update/Escape, varying
guest counts, missing ages, wrong counts and ambiguous controls. They were
authored only; no tests, validators, app/browser startup or live/model calls ran.

## Search aliases and request grounding - 2026-11-07, verification pending

Agent **v20.17** treats a hotel's generic Search/query binding as navigation,
not an additional stay requirement. Redundant query metadata cannot block a
guest-widget action or survive as a prerequisite after the destination is known.
Actual action values still require grounding; missing ages still require the user.
Declaration errors retain the actual field label, including errors raised before
an action target is attached to the activity entry.

Dates and destination have separate parsers: a correct calendar does not prove
the internal destination was populated. The reported temporal `form 28-30` wording
is accepted without changing the request, and a model can ground a missing
canonical destination in the user's literal place wording. This parsing edge
case alone does not establish the cause of the reported live loop.

Help diagnostics now include `agent_version`, `request_fields` and `collection`
so the running backend and actual handoff blocker can be identified. Restart the
backend and start a fresh task; Companion remains **0.5.12**. Regression cases were
authored only. No tests, validators, application/browser startup or model calls ran.

## Automatic results updates - 2026-11-07, verification pending

Agent **v20.16** tracks verified counter changes as criteria edits, and retains
their pre-change record baseline when Done/Update merely closes a widget. A
changed set of rendered records after an actual edit can establish an automatic
update without requiring an observed spinner, URL change or Search button.
Requested returned criteria still need verification before a matching handoff.
Opening a date field only to inspect it is not treated as a date change.

Search preflight checks again whether the results finished updating while the
model was deciding. If ready, it collects them without sending Search. An empty
generic Search field is not new missing user data when the destination is already
in the request. Technical evidence includes `result_handoff` with the specific
collection blocker and any unverified/mismatched stay fields.

Restart the dashboard backend and use a fresh task. Companion **0.5.12** remains
the current extension; this update changes backend behavior only. Source fixtures
cover automatic counter updates, unchanged cards, closing Update and a result
update during Search planning. No tests, validators or live workflows were run.

## Collect existing same-page hotel results - 2026-11-07, verification pending

Companion **0.5.12** / agent **v20.15** recognizes heading forms such as
"New Jersey Hotels and Places to Stay" and reads fresh result criteria before
trying a destination query. Committed full-date openers and named guest/room
summaries can establish the applied page state without a new URL or a refresh
the agent witnessed. An explicitly read guest split is still required when the
closed summary only shows total guests. Individual listing availability/prices
remain separate source checks.

Resume clears old transient autocomplete, readback and loop state, preserving
the original request, paid budget and real submission guards. A matching hotel
results page with stay widgets blocks redundant site-wide destination Search.
Record markers and URL metadata aliases are consistent across both adapters.

Restart the backend, reload Companion **0.5.12**, refresh the website and start a
fresh task. Manually check both starting from visible hotel results and changing
guest values while paused, choosing Update then Resume. The expected next stage
is collection/review once the requested criteria are read, rather than retyping
the destination. Unknown years/count splits remain unknown. Regression sources
were authored and reviewed only; no tests, validators, browser/app startup or
model/API calls were executed.

## Adults-only requests and Tripadvisor Update - 2026-11-07, verification pending

Companion **0.5.11** / agent **v20.14** fixes the reported Charlotte path:
`find me hotels in charlotte from 28-30 Nov 2026 ,for 3 adults`.
Only the requested adult count is a target. Existing room/child settings are
preserved and read in context; they are not invented missing requirements.
The model focus and runtime recognize the guest panel's **Update** control.
Matching live counts are applied once, then a bounded passive wait observes the
results. Already verified applied listings are collected before another guest
panel reopen. An unsupported Enter on Search is reported as an action problem,
not a request for the user to supply a value called "Search".

Generic click preflight failures now report a phase, reason and changed field
names without exposing values. The old `control_changed` log cannot establish
whether the guest opener changed, was covered or was outside the viewport.
Exact identity and hit-test checks remain active. A blocked read-only reopen
stops without repeating an undispatched click.

Restart the backend, reload Companion **0.5.11**, refresh the website and use a
fresh task for manual verification. The authored fixtures include the exact
adults-only prompt, Update focus, separate site Search validation and applied
result handoff. No tests, validators, live browser workflow or API calls were run.

## Child age after Update and exact guest counts - 2026-11-07, verification pending

Companion **0.5.10** / agent **v20.13** addresses the reported sequence: select
child age **7**, choose **Update**, then **Resume** with the guest panel closed.
The agent preserves the manual confirmation while fields are hidden and can
reopen one uniquely observed rooms/guests summary to read the selected age.
The observed wording "The selected number of rooms is 3 and the selected number
of guests is 5" is supported even without popup attributes. An empty or invalid
age still requires input; site defaults are not silently accepted.

Custom age dropdowns can read their selected ARIA value, an explicitly owned
selected option or compact rendered age text. After Update, a read-only guest
inspection compares the closed summary with fresh separate count rows. Hidden
rows are not carried forward as current proof. The same summary is reopened at
most twice per Resume, without extra model calls. Listing handoff still needs
evidence that the requested stay was applied to the results.

Stop the old task, restart the backend, reload Companion **0.5.10**, refresh the
website and start a fresh run. Retry `find hotels in Virginia from 28-30 November
2026 with 4 adults 3 rooms 1 child`. At the age pause, select **7**, choose
**Update**, then **Resume** once. Verify **4 adults, 1 child and 3 rooms** in the
actual rows and applied stay. **5 guests** is the combined adult/child total,
not independent proof of 4 adults; a summary showing 2 rooms is still wrong.
Check the final dates and listings before collection/review. Regression fixtures
were authored and source reviewed only; no tests, validators, live browser
workflow or model/API calls were run. Manual acceptance remains pending.

## Correct dates with an open calendar - 2026-11-07, verification pending

Companion **0.5.9** / agent **v20.12** addresses the confirmed case where the
requested November 28–30 dates were already correct but the calendar stayed open.
The observer distinguishes date openers from day choices, including an opener
whose accessible label contains a full selected date. It reads actual Selected
labels with explicit false/native state taking precedence and keeps calendar
ownership bounded to the observed widget, including supported roleless layouts.

Form verification and returned-stay checks share full-year selected endpoint
parsing. Matching current ranges are preserved; a selected interior day can still
become a new endpoint when the requested range differs. Model focus closes the
verified calendar using its observed confirmation control or Escape before
unrelated global Search. Automatic form submission waits while it is open.
Generic Search openers are distinct from query submits; a genuinely targeted
ambiguous query still retains its validation. Pre-input date reference failures
now include reason/field names, without bypassing native identity or hit checks.

Stop the old task, restart the dashboard backend, reload Companion 0.5.9 and
refresh the website. Start a fresh run. Check the exact reported scenario with
dates already correct and the calendar open: it should preserve the selected
range, dismiss the calendar, verify guests/rooms, then collect applied results.
Also check changing an old selected range, missing ages, independent calendars
and an actual required query. Regression fixtures were authored, but no tests,
validators, live browser workflow or configured API calls were run.

## Exact counters and already-applied stay results - 2026-11-07, verification pending

Companion **0.5.8** / agent **v20.11** interprets an explicit actuator label such
as Increase adult count by 1 as a quantity control, not a current value of 1.
It reads the rendered count in the same row. Raw increase/decrease clicks are
converted to the request's absolute target, so a requested total of 3 already
showing 3 causes no input. Unreadable or contradictory counts remain unconfirmed;
repeated failures on unchanged evidence pause instead of allowing blind clicks.

Same-page results no longer require an invented new Search. The ledger can adopt
already-applied matching results when returned stay evidence verifies the request
and either the returned URL contains the criteria, or an observed results refresh
follows a criteria application. Update/Done alone is insufficient: changed result
cards or a witnessed loading-to-settled cycle is needed. Draft fields next to old
cards, wrong guest counts, open widgets, missing ages and uncertain submissions
do not qualify. Small record signatures track refreshes; they are not source or
availability evidence and are omitted from the navigation model context.

Observed-results provenance is separate from a witnessed agent Search. Matching
results proceed to source collection and review, including explicit empty results.
The unused generic Search box does not block an already-applied matching result
page; explicitly submitting that box still checks its own required fields. Listing
prices and availability continue to require their own evidence and human review.

Restart the dashboard backend, reload Companion 0.5.8 and refresh the website.
Retry `find me hotels in New Jersey from 28-30 November for 3 adults and 2 rooms`.
With the current reference date this means November 28–30, 2026. Verify that a
correct adult count stays at 3, a value of 2 changes once to 3, and a value of 5
decreases to 3. Then check that Update applies the requested dates/occupancy and
matching listings go to collection without reopening global Search. Also check
unchanged stale cards, a wrong count, a missing age and a genuinely unconfirmed
Search outcome. Regression cases were authored, but no tests, validators, live
browser workflow or configured API calls were run.

## Location discovery before hotel search - 2026-11-07, verification pending

Companion **0.5.7** / agent **v20.10** separates location/category discovery from
the final stay search. The shared ledger derives a current navigation stage from
visible controls: discover the location, open Hotels (or the observed equivalent),
prepare the dates/guest form, await its response, then collect sources. Intermediate
city-result/category navigation does not confirm stay details or hotel availability.

Two control budgets previously obscured category links: the browser's bounded
inventory and the smaller model context. Both now retain a small set of actual
category controls. The context also retains grounded city-result actions such as
See all results, using fresh IDs only. General Search is not automatically a final
stay submission; positive source evidence determines whether it opens discovery,
searches for a location or submits a dates-and-guests form. Runtime filling waits
for an actual stay form rather than repeatedly refilling the global query.

Real required fields, uncertain submit outcomes and manual child-age handoff
remain enforced. This is shared control interpretation and agent guidance, not
site-specific URLs or model-weight training. The existing control and token budgets
remain; no extra model or screenshots were added.

Restart the dashboard backend, reload Companion 0.5.7, refresh the target website
and begin a fresh workflow. The supplied failed log used Companion 0.5.5.
Manually retry `find hotels in New Jersey from 28-30 November with 4 adults and
3 rooms.` With the current reference date, the existing future-date default should
resolve the stay to November 28–30, 2026. Verify city discovery, Hotels-category
selection, final stay summary, actual Search transition, source preview and reviewed
save. Repeat from a city overview with Hotels visible, a query-results page and
an already-open hotel form; a missing child age must still pause for user input.
No tests, validators, app/browser startup or paid calls were run.

## A simpler browser panel - 2026-11-07, visual verification pending

Browser Companion **0.5.6** adds a labelled connection indicator: green for a
healthy connection, red when no website is connected, and yellow for a pause,
interruption or required input. A stored tab binding alone is not shown as healthy
when a session or transport error prevents control. The workflow separately says
**Working on your request**, **Waiting for you**, **Preparing your results** or
**Results ready to review**. Ready does not mean saved.

The refreshed panel shows the website name/domain, clearer Start task / Resume
task / Review results actions, softer cards and an animated working indicator.
Custom fields, usage/access explanations and diagnostics are expandable. The
request collapses once when a run appears; users can reopen it without polling
closing it again. Identical text updates preserve live-region nodes. AI steps
are labelled as budget usage, not a percentage of results completed.

Reload the unpacked extension at `edge://extensions` or `chrome://extensions`,
refresh the website tab and reopen the panel. Manually check connected, disconnected,
running, paused/missing input, interrupted connection and ready-for-review states,
including a narrow panel. No tests, validators, browser startup or visual preview
were run; styling and live behavior remain for manual verification.

## Automatic tab connection and hotel discovery - 2026-11-07, verification pending

Extension **0.5.5**, dashboard **2026-11-07.1**, agent **v20.9** follows the selected
eligible website tab while idle, including before Start. Switching to the dashboard
or browser settings does not replace the website connection. A running or paused
workflow keeps its original target until completion/cancellation. Completed review
access remains available after an idle tab change. Disconnect disables automatic
pairing until Connect is chosen again. A changed dashboard account/session still
requires explicit reconnection. If the browser withholds access to a new tab, open
the companion from that tab's toolbar icon to grant access.

The repeated paid-workflow and native-input checkboxes have been removed. Start
and Resume are the authorization gestures; neither pairing nor polling starts a
paid workflow. Existing limits and review before saving remain. Optional event
publishing is a Yes/No setting, default No. The browser's debugger permission and
warning remain browser-controlled. This supersedes the older approval-checkbox
instructions below.

Hotel discovery now distinguishes actual category links/tabs inside a search popup
from choices that enter a value. A Hotels link is not a missing Search value and
does not become the chosen destination. A positively identified query-only native
form can perform discovery before a stay form exists; that does not confirm stay
dates, occupancy or hotel availability. Forms containing date/guest controls still
need the requested values before submission. Agent guidance prioritizes the
requested listing category before individual hotels. Required values omitted from
the request, including child ages, still pause for manual input.

This improves shared observation, action classification and prompt guidance; API
model weights are not trained by a run. Reusable examples should come from reviewed
successful/failed transitions, with regression cases across websites, rather than
memorizing a site's selectors or a specific city.

Manual checks (not executed):

1. Keep the dashboard signed in, select two eligible website tabs while idle and
   confirm the displayed connection follows without Disconnect. Start only when
   requested. While paused, switching tabs must not move the existing workflow.
2. Finish a run, select another website tab and confirm the previous dashboard
   review remains accessible. Disconnect must remain disconnected until Connect.
3. On Tripadvisor use `Find me hotels in Edison with 3 adults and 2 rooms and
   1 child with check in and check out on 28-30 November 2026.` Check entry into
   Hotels/search rather than repeated individual-hotel navigation. Discovery
   must not be reported as a completed stay search.
4. If child age is required, enter it yourself, close with Done and Resume once.
   Confirm destination, dates, guests and returned prices before saving. Repeat
   with another city and guest counts, and with a news request for current-page
   articles. Clearly labelled links/tabs are supported; ambiguous unlabeled
   controls still need live review.

## Resume with the guest panel closed - 2026-11-06, verification pending

Extension **0.5.4**, dashboard **2026-11-06.4**, agent **v20.8** retains manual age
confirmation when Done closes the guest panel. On explicit Resume, a uniquely
observed occupancy summary can be opened once to read the ages already entered;
one passive wait accommodates delayed rendering. The agent never uses Search
as an opener or chooses a substitute age. If the fields remain hidden, ambiguous
or invalid, it asks for manual attention instead of looping. Confirmation remains
bound to the paused document and the values actually read.

The existing approvals sit beside Resume while paused; both still need renewal.
No automatic resume or extra model budget was added. Verify the original hotel
prompt with no age: fill the actual age on the website, click Done, renew the
visible approvals and Resume. The panel should reopen once for read-back and
continue. Also verify leaving the panel open, age zero, and resuming with an age
still missing. These checks were authored but not executed.

## Missing values require user input - 2026-11-06, verification pending

Extension **0.5.3**, dashboard **2026-11-06.3**, agent **v20.7**, extractor **v17**
complete the missing-value handoff and reject non-article results. A model cannot
choose a new form value solely because a website requires it. Request quotes
must ground the field and value; a child count or date is not an age. Direct
edits and owned option choices are checked before execution. Required child ages
not supplied in the request cause a pause before another model decision, even
when the site preselects an age. The UI says **Waiting for your input**. Enter or
confirm the ages on the website, then explicitly Resume. A still-empty field
pauses again; confirmed manual values are preserved. No automatic resume occurs.

Manual acceptance:

1. Use `Find hotels in Baltimore for November 28–30, 2026, with 3 adults, 1 child
   and 2 rooms.` Check that no age is chosen. Fill the actual age on the website,
   Resume, and verify the final search summary and listings.
2. Repeat with an explicit actual age in the prompt, and with two children whose
   age selectors are distinguishable. Verify that ages are not swapped or reused.
   Ambiguous field-to-child associations should ask for manual input.
3. Repeat a news article request. `Play Connections: Sports Edition` and `Sports
   coverage` are game/section links, not article records. A URL-only candidate
   without a captured headline must not become an approved article. Real short
   headlines and article headlines containing "game" must remain valid.

Restart/refresh the dashboard, reload the extension, refresh the website and
reconnect a fresh workflow after upgrading. Tests and live workflows remain for
manual verification; none were executed while implementing these changes.

## News homepage validation - 2026-11-06, verification pending

Agent **v20.6** and extractor **v16** correct page-role handling in the shared
backend. A current-page homepage or search result must not become a single
article detail merely because the model uses `capture=detail` or `finish=detail`.
Verified card headings and bound links can be returned from neutral pages;
direct article pages with explicit main-headline evidence retain strict checks.
Unsupported optional labels such as an invented `source_type=article link` are
cleared using the existing field-issue path, not accepted as captured facts.

After restarting the dashboard, reconnect the extension and use a fresh workflow.
Check a news homepage with `Find me articles related to sports`: captured article
cards should be source-verified and games/navigation excluded or uncertain. Then
check one actual article URL: its title must be the primary headline, not a body
quotation or related-story title. For linked collection, verify the starting
index remains an index after finishing on it. Text/link limits still mean partial
coverage. No tests, validators, browser sessions or model calls were run.

## Newly required form fields - 2026-11-06, verification pending

Extension **0.5.2**, dashboard **2026-11-06.2**, agent prompt **v20.5** observes
newly revealed required/invalid fields and unresolved select placeholders. These
fields take priority in compact navigation context and prevent automatic Search
while incomplete. A dependent field inside an open widget must be completed
before closing or switching widgets. Values come from the request or the user;
the agent must never invent a child's age.

For `Edison, November 28–30, 2026, 5 adults, 1 child, 4 rooms`, no age was supplied.
The expected path is a specific age-field pause, manual age entry on the website,
then Resume and one Search. Alternatively include `one child aged 7` in a fresh
request and verify that the agent selects the actual matching option. With two
children, provide both ages and check both fields. Check the no-children case too.

A native validation preflight can report that Search input was explicitly
prevented. Only that proof releases the local attempt after field repair. An
unchanged page or timeout still does not authorize another Search. Old paused
runs with an unknown attempt should be restarted after upgrading, or completed
manually and resumed for passive result verification. No tests, validators,
application/browser startup or paid model calls were run.

## Startup compatibility - 2026-11-06, verification pending

Extension **0.5.1**, dashboard **2026-11-06.1**, checks the loaded website
executor's version and native-input protocol before Start or Resume reaches the
backend. Observation readiness is confirmed by the worker's actual attachment,
instead of relying on a page helper echoing an input-driver flag. An old or mixed
installation still stops before a model decision; diagnostics now retain the
worker version, executor version, input driver and protocol when available.

The earlier `native input is not active` message with empty diagnostics proves
the startup marker was missing, but does not identify which component was stale.
Current source inspection found that the prior worker and executor agree when
both are loaded. Reload the unpacked extension from this project's
`extensions/page-capture` folder, confirm **0.5.1**, refresh the website and
reconnect a fresh workflow after restarting and refreshing the dashboard.

Manual checks: start once without manually clicking the website; confirm version
diagnostics and the actual destination/date/occupancy summary, Search and source
records. A version mismatch must show the upgrade instructions before a backend
Start/Resume request. No tests, validators, application/browser startup or paid
calls were run for this change.

## Native browser input - 2026-10-26, verification pending

Extension **0.5.0**, dashboard UI/backend **2026-10-26.1**, replaces synthetic DOM
clicks/typing in the current-tab agent path with browser-level mouse/keyboard
input through the extension's `debugger` permission. Observations and source
capture still use the existing DOM collectors; no screenshots, new model planner,
additional paid-call budget, cookie export or remote debugging port were added.

**Review this permission change:** `debugger` is a powerful browser permission.
This implementation attaches only to the already connected website tab after a
separate **browser-level mouse and keyboard control** approval on Start or Resume.
It does not attach merely for pairing, status checks or a one-page snapshot.
The browser can show a debugging warning. Cancelling that warning, opening
DevTools, closing the website or another debugger taking the tab can interrupt
input. Inspect the page/action evidence, resolve the conflict and approve Resume
explicitly; an uncertain action must not be replayed automatically. See the
[browser debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger).

The public agent actions and decision schema are unchanged. Public `press` is
still limited to Enter/Escape; native arrow keys used for a numeric input are
internal counter stepping, not arbitrary model-provided key sequences. The
packaged executor grounds each action in observed controls and reads its result
back. Native input does not bypass login, MFA, CAPTCHA, paywalls or access denials,
and a dispatched click is not proof that search criteria or listing prices match.

Recent counter evidence now separates **before**, **requested**, **observed**,
**input attempts** and **dispatched**. Unreported values are labelled unconfirmed,
not inferred from an unchanged UI. Browser diagnostics name the `native_cdp` input
adapter separately from DOM observation. Capture, extraction, review, saved data
and event publishing retain the existing workflow.

An old extension worker cannot silently keep using DOM-only input after disk
files are updated: the backend requires an observation declaring the native
driver before any new model decision, otherwise it asks for reload/reconnect.

Upgrade manually: restart the dashboard, hard-refresh its tab, reload the unpacked
extension, review/accept its new debugger permission, refresh the target website
and reconnect a fresh workflow. The first live acceptance check is New York,
November 28–30, 2026, 3 adults and 2 rooms **without manually clicking the page
after Start**. Compare the actual destination/date/occupancy summary, Search
transition and listings before saving. Then repeat with different counts, pause
and renew both approvals before Resume, and intentionally detach input to confirm
that it stops instead of replaying an uncertain action. These checks remain for
the user: no tests, validators, application/browser startup or model calls were run.

## Earlier implementation checkpoints

Implementation checkpoint: 2026-10-18. Manual verification pending. No tests,
validators, application startup, live browser sessions or model calls were run
while implementing this checkpoint, as requested.

Recovery checkpoint: 2026-10-19. Extension 0.4.1 corrects editable-control focus,
composed text-input events and stale-element read-back. Reload the extension,
refresh the website and start a fresh workflow after upgrading. The dashboard now
has one website-address box for existing-tab paths; it is read-only only after a
snapshot has been received. The full live Booking.com issue still requires user
verification; the last saved run did not include its DOM observation.

Handoff recovery checkpoint: extension 0.4.2 / dashboard `2026-10-19.2`. A stale
dashboard connection now offers **Reconnect dashboard** even when an old agent is
paused. Distinct messages identify sign-out, changed session/account, server
restart, stale UI, unavailable tab, and rejected origin/CSRF checks. Refresh/sign in
to the dashboard first, reconnect explicitly, then renew consent and **Start
workflow**. Old paid decisions and uncertain actions are never replayed. A stale
run may be cancelled only when the freshly validated dashboard still has the same
account/session/server; a new account cannot take control of it. Session-only API
keys may need to be configured again after a server restart.

## What changes

Workflow/lifecycle checkpoint: extension **0.4.4**, dashboard **2026-10-20.1**.
The dashboard now has two primary workflows: **Open a new browser** and
**Use my current tab**. A one-page snapshot is under **Advanced collection options →
Extract this page only**; it is not a second way to start browser automation.

In that earlier DOM-only checkpoint, Start/Resume explicitly activated the connected website tab/window. This was not a
claim of trusted DOM input: actual page visibility/focus is reported separately in
Browser control diagnostics. Counter preflight compares exact fact keys/values,
not object property order, then focuses and rechecks the observed actuator before
any click. A rejection identifies its structural reason and says no click was sent.
Session, account and server ownership checks remain unchanged.

Manual checks for this checkpoint (not executed by the implementation):

1. Run a current-tab search for New York, November 28–30, 2026, **3 adults and 2 rooms**.
   Confirm the website becomes active after Start and the actual counter values,
   date summary, Search transition and collected listings match the request.
2. After review, start another approved task without closing/reopening the panel,
   including when the dashboard tab is currently active. Check the displayed bound
   website/account; the connection must not switch to the dashboard as its target.
3. Hide/reopen the panel or switch tabs, then check that its status recovers without
   resending Start, Resume or an uncertain website action. A lost Start reply may
   mean work began: check status before approving another run.
4. Pause/resume and cancel a run; stale replies must not revive it or replace the
   next run. Real sign-out, account change or backend restart still needs explicit
   reconnection and must not resume old work automatically.
5. Open Advanced collection options, transfer a reviewed snapshot and extract it.
   Verify it reveals the extraction-only source and never starts navigation.

No tests, validators, browsers, application startup or model calls were run.

Calendar interaction checkpoint: extension **0.4.3**, dashboard **2026-10-19.3**.
Calendar cells and their observed inner day controls are associated explicitly;
the task view avoids duplicate choices only within the same actual cell. Extension
date clicks are single-dispatch, followed by a bounded selection/change read-back.
An unchanged click is not reported as a selected date. A selected day is not proof
that the complete requested stay is applied: the form and returned results still
use the existing shared verification. DOM input is not equivalent to Playwright
pointer input; sites requiring a different input mechanism may still need manual
attention. No debugger, extra browser permission or model-call budget was added.

Manual verification after reloading the extension and refreshing the dashboard:

1. In Booking.com, request New York, **November 28–30, 2026**, **3 adults, 2 rooms**.
   Confirm the actual selected destination, both full dates and occupancy, then
   confirm Search and listing collection occur without repeatedly clicking a day.
2. Repeat using a different date range and **4 adults, 2 rooms**. Check the final
   form/result summary, not just the action's dispatched status. If paused, share
   the calendar action evidence and what the visible date summary shows.
3. Verify the existing new-browser workflow still uses its normal extraction and
   review path. Inspect prices, units, URLs and source quotes before saving.

These scenarios were documented, not executed by the implementation.

There are now three distinct browser paths:

| Path | Browser session | What it does |
| --- | --- | --- |
| Open a new browser | Playwright-launched isolated profile | Automatic or reviewed/manual workflow; normal/restricted networking remains available |
| Use my current tab | Your selected, already-open Chrome/Edge tab | Extension side panel runs the shared LangGraph agent through a local tab adapter, then opens the normal dashboard review |
| Advanced: Extract this page only | Reviewed snapshot from your Chrome/Edge tab | Single-page extraction, no agent navigation; review before saving |

The extension does not start a separate browser or export your browser profile.
The website keeps the session you already have. The local Python backend still
owns the configured API connection, agent decisions/budgets, task ledger,
extraction, source/price validation, SQLite results, exports and optional NATS
event publishing. This is a browser adapter, not another model or planner.

## Set up and use

1. Start the dashboard as usual and refresh its tab after this update. Sign in
   and configure the API connection. Keep exactly one signed-in dashboard tab
   open at `http://localhost:8120` or `http://127.0.0.1:8120` in the same browser.
2. Open `chrome://extensions` (Chrome) or `edge://extensions` (Edge). Enable
   Developer mode, choose **Load unpacked**, and select the repository folder
   `extensions/page-capture`. If it was already installed, click **Reload**.
   The extension is named **Agentic Studio Browser Companion**, version 0.5.12.
   Review/accept the new debugger permission after this upgrade; the runtime
   attaches only when you choose Start or Resume.
3. Open the target public HTTPS website in an ordinary tab. Complete login,
   MFA and any site verification yourself before starting. Do not enter passwords,
   API keys or codes in the task prompt.
4. On that website tab, click the extension's toolbar icon and choose **Use this
   tab with agent**. The side panel opens and connects that tab to the signed-in
   dashboard. Confirm the displayed website and dashboard account.
5. Enter your task, optionally set fields/record limit/rules, then choose
   **Start task**. Start authorizes model use and control of the connected tab.
   Pairing itself makes no model
   call. Existing budgets apply: 30 decisions, five active minutes, up to six
   captured pages, and 1–50 preview records (default 25). These are upper bounds,
   not a promise of full-site coverage.
6. Follow progress and recent actions in the panel. **Pause** stops between
   actions; an in-flight operation can finish. Complete any required manual
   interaction in the connected tab, then choose **Resume task** to continue
   within the same budget. There are no repeated approval checkboxes.
   **Get collected results** ends navigation and extracts already-retained
   sources; it does not capture new pages or save automatically.
7. Choose **Review results**. Review fields, missing values,
   prices, criteria and evidence. Use **Save reviewed results** there, then
   download. Event publishing remains optional and happens only on reviewed save.
   The website tab remains open for comparison.

If a destination field stalls, expand **Browser control diagnostics** in the side
panel. Its value-free focus/popup/owned-option counts distinguish a missing popup,
a hidden popup and missing field-to-choice association. These counts are also
retained in the dashboard's technical evidence. They add no page text or entered
values and are not added to model navigation context. Include the diagnostics and
recent action evidence when reporting a problem; do not send credentials.

Cancel stops the local workflow, not the browser tab. Closing the panel is not
cancellation. Keep it open during initial manual acceptance checks. A backend
restart loses in-memory runs; a logged-out/expired session cannot resume them.
The extension transport has a 15-minute wall-clock lifetime, separate from the
agent's five active minutes.

## How the connection works

The extension worker uses the signed-in loopback dashboard tab as a same-origin
HTTP relay. Existing session/CSRF checks remain, with an exact backend-instance
binding. No wildcard CORS, debugger port, cookie-reading permission, API-key
storage in the extension or messages from arbitrary webpages were added.

The worker claims one backend command at a time. Packaged code in the selected
tab's isolated extension world observes/validates controls and reads action
results; the debugger-backed driver sends bounded browser-level input to that
tab. Commands are DOM observations, a grounded action or a bounded source capture.
Unknown/lost action
delivery is not automatically replayed. Temporary run/acknowledgement state lives
in `chrome.storage.session` so a sleeping MV3 worker does not blindly repeat a
click; browser restart clears it. Do not treat this storage as a secrets vault.

Navigation observations use the existing compact task-focused representation.
Extraction uses the existing separate source collector with literal price,
group and quote context, not the compact navigation text. API keys remain in the
local backend; authorized visible source text still goes to your configured
model. DOM reference attributes are added to elements but no visual labels or
overlays are inserted by this adapter.

## Current boundaries

- LangGraph only for the new tab-agent path; existing CrewAI/manual paths remain.
- DOM/text observations only, no screenshots or arbitrary model-provided
  coordinates/scripts/selectors. Browser-level clicks use coordinates derived
  from the observed control, not a model-generated point. Native input still
  requires source-grounded read-back; unsupported or ambiguous widgets can pause.
  Public keyboard actions remain Enter/Escape; arrow stepping for a numeric
  counter is internal to the verified action.
- Only the connected top-level tab/origin is automated. Popups, other tabs and
  cross-origin frames are not controlled. Cross-origin navigation pauses rather
  than silently granting control of another website.
- Temporary `activeTab` access is granted by clicking the extension on the
  website. Same-origin navigation can continue; if access is lost, invoke the
  toolbar extension on that site again. The debugger permission is separately
  required for native input, but attachment is limited by this workflow to the
  connected website tab; it is not a browser-wide debugging port.
- Login/MFA/CAPTCHA remain manual. This does not bypass bot detection, access
  denials, paywalls or guarantee Tripadvisor will accept automated actions.
- Dynamic prices, availability and source completeness still require review.
  Neither a successful click nor the existing login session proves that a saved
  amount applies to the requested dates, rooms or guests.

## Manual acceptance scenarios

1. **Booking search → review → save:** in a normal Booking.com tab, request
   `Find hotels in New York, check-in 2026-10-28, check-out 2026-10-30, 4 adults,
   2 rooms. Prefer USD 250–350 per night for all rooms combined. Include listing
   URL, displayed nightly price, current total, original price if shown, taxes,
   fees, price basis and rating.` Verify selected destination, dates and occupancy
   before Search; compare returned prices with the unchanged tab before saving.
   Missing/unverified criteria must remain visible, not labelled matches.
2. **News current page:** open an accessible news homepage; ask for world-politics
   headlines visible on this page with original titles and links, without opening
   detail pages. Check that collection can finish without an unnecessary search.
3. **Pause/manual/resume:** pause, inspect/change the connected form, renew both
   paid and browser-level control approvals and resume. Fresh observed state must
   be used, not old control IDs. Cancel the browser debugging warning or open
   DevTools in a separate check: the interrupted input must stop without replay.
4. **Connection boundaries:** switch to another site, close the selected tab,
   sign out of the dashboard, or restart the backend. Actions must stop; another
   account/tab must not inherit the run. Reconnect explicitly for a new workflow.
5. **Interrupted acknowledgement:** reload the extension while an action is in
   flight. It must not blindly repeat the action. Inspect the tab and reconnect
   or resume only when the run remains available.
6. **Existing paths:** verify the original Playwright workflow and one-page
   extension capture still work. Discarding an old snapshot must not wipe an
   active side-panel workflow.

Implementation references: [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab),
[sidePanel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel),
[debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger),
[MV3 worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).
