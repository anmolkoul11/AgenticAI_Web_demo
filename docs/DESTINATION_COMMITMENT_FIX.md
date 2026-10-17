# Destination selection and qualified read-back

Checkpoint: UI/backend `2026-10-16.3`; browser agent `browser-agent-v20.3`.
Manual verification pending. No model/provider or paid-budget changes.

## Observed failure

The supplied run made eleven valid model decisions without attempting Search.
The action evidence shows the correct city suggestion being clicked and the site
returning `New York, New York, United States of America`. The tracker nevertheless
reported destination mismatch and replaced that committed value with `new york`.
This discarded the site's selection and repeated the same cycle. Dates remained
verified, while occupancy was never reached.

## Targeted changes

- Prefer the suggestion's first complete rendered text line over an aggregate
  accessible label containing primary and secondary text. When no distinct line
  exists, preserve its explicit accessible label or full visible text; arbitrary
  inline spans and bold highlights do not become guessed subtitle boundaries.
  No Booking-specific selector or city alias is added.
- Continue to require an actually clicked, associated suggestion followed by its
  exact source-backed canonical read-back. Mere typed text, popup dismissal,
  broad prefix similarity or an unrelated option does not prove selection.
- Keep selection evidence stable for a uniquely named input if unrelated forms
  change the inventory's form index. Ambiguous controls and new documents still
  require fresh verification.
- Skip redundant model fills on a verified destination or identical current
  input value before they can invalidate selection. Skips remain visible in action
  evidence and subject to existing repeat limits; no new retry loop is introduced.
- Do not let raw canonical-versus-request string differences override the
  tracker's explicit wait/open/select guidance in compact navigation context.

These changes do not alter extraction, price assessment, source-aware cards,
networking, sign-in, MFA, submission verification or model-call limits.

## Manual verification

Restart the dashboard and hard-refresh, then start a **new** browser session;
resuming an existing session does not replace its in-memory tracker.

Use the original request with consistent dates, for example:

> Find hotels in new york with check-in 2026-10-28 and check-out 2026-10-30
> for 4 adults and 2 rooms. Include name, listing URL, displayed prices,
> price basis, currency and guest rating. Prefer 250-350 USD nightly.

Check that one destination choice changes the input to the site's qualified
label, destination stays verified while dates/occupancy are entered, and Search
is attempted only after all required form values are verified. Then check result
capture/review and the returned stay scope separately. Repeat with another city;
an airport, same-name hotel or ambiguous destination must not be silently accepted.

Regression fixtures were authored but **not run**, as requested. No tests,
validators, application imports/startup, browsers or model/API calls ran.
