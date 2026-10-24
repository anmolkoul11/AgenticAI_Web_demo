# Use an agent in your normal Chrome or Edge tab

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

Start/Resume explicitly activates the connected website tab/window. This is not a
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
   The extension is named **Agentic Studio Browser Companion**, version 0.4.4.
3. Open the target public HTTPS website in an ordinary tab. Complete login,
   MFA and any site verification yourself before starting. Do not enter passwords,
   API keys or codes in the task prompt.
4. On that website tab, click the extension's toolbar icon and choose **Use this
   tab with agent**. The side panel opens and connects that tab to the signed-in
   dashboard. Confirm the displayed website and dashboard account.
5. Enter your task, optionally set fields/record limit/rules, check the paid
   workflow approval and choose **Start workflow**. Pairing itself makes no model
   call. Existing budgets apply: 30 decisions, five active minutes, up to six
   captured pages, and 1–50 preview records (default 25). These are upper bounds,
   not a promise of full-site coverage.
6. Follow progress and recent actions in the panel. **Pause** stops between
   actions; an in-flight operation can finish. Complete any required manual
   interaction in the connected tab. Renew approval before **Resume agent**.
   **Review collected pages** ends navigation and extracts already-retained
   sources; it does not capture new pages or save automatically.
7. Choose **Open review / results in dashboard**. Review fields, missing values,
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

The worker claims one backend command at a time, runs packaged code in the
selected tab's isolated extension world and acknowledges it. Commands are DOM
observations, a grounded action or a bounded source capture. Unknown/lost action
delivery is not automatically replayed. Temporary run/acknowledgement state lives
in `chrome.storage.session` so a sleeping MV3 worker does not blindly repeat a
click; browser restart clears it. Do not treat this storage as a secrets vault.

Navigation observations use the existing compact task-focused representation.
Extraction uses the existing separate source collector with literal price,
group and quote context, not the compact navigation text. API keys remain in the
local backend; authorized visible source text still goes to your configured
model. DOM reference attributes are added to elements but no visual labels or
overlays are inserted by this adapter.

## First-version boundaries

- LangGraph only for the new tab-agent path; existing CrewAI/manual paths remain.
- DOM/text only, no screenshots, coordinate clicking or arbitrary model-provided
  scripts/selectors. Custom widgets requiring trusted hardware-like input may
  need manual interaction. Native fields and generic clickable counters are
  supported; keyboard automation is limited to native-form Enter and Escape.
- Only the connected top-level tab/origin is automated. Popups, other tabs and
  cross-origin frames are not controlled. Cross-origin navigation pauses rather
  than silently granting control of another website.
- Temporary `activeTab` access is granted by clicking the extension on the
  website. Same-origin navigation can continue; if access is lost, invoke the
  toolbar extension on that site again. No blanket site-access grant is needed.
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
3. **Pause/manual/resume:** pause, inspect/change the connected form, renew
   approval and resume. Fresh observed state must be used, not old control IDs.
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
[MV3 worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).
