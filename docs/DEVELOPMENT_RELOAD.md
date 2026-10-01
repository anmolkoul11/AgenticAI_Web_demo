# Dashboard development and reconnect handling

Normal demos: `./scripts/Start-Demo.ps1` (no automatic reload).

Development: `./scripts/Start-Demo.ps1 -Dev`.

Development mode watches dashboard Python code only. Editing it reloads the dashboard,
invalidating sessions and session-only keys. Do not edit during active jobs. Portal,
shared workflow and launcher changes still require a full launcher restart. Static
HTML/JS/CSS changes require a browser refresh. This is not zero-downtime deployment.

The page checks its server session/version every ten seconds. On restart, expiry,
connection loss or version mismatch, it displays a reconnect/refresh notice and
blocks API actions. It never retries a paid call, registration or execution.
Refreshing loses unsaved fields. Check saved history before repeating a request
whose response was lost. Restart does not guarantee an interrupted job completed.

Keep `UI_VERSION` in dashboard/app.py and static/app.js identical; bump both when
changing the UI/API contract. Deploy them together. Versioned browser mutations
with a mismatched version receive HTTP 409. Unversioned clients remain compatible;
this is a UX guard, not authentication or a rolling-deployment mechanism.

## Manual verification (not run by the assistant)

1. Restart once to install this behavior; hard-refresh the page.
2. Register/sign in, then check invalid account fields show account-specific guidance.
3. Start with `-Dev`, make a harmless dashboard Python edit while idle, and verify
   reload and the restart notice. Refresh, sign in and re-enter a session key only
   if model planning is needed. Do not make a paid call just to test reconnect.
4. Stop the server: within ten seconds the page should show connection loss.
   Restart it: refresh to reconnect. Verify no work is resubmitted.
5. Check normal launcher mode does not reload on code edits.
6. Check a version mismatch displays the refresh notice, and expired sessions
   require sign-in. Existing accounts and saved history should remain available.

For live/shared hosting, use a controlled release with admission draining, durable
job ownership and managed sessions/secrets. The current local in-memory design
does not support uninterrupted multi-instance upgrades.
