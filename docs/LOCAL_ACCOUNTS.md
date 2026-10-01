# Local accounts and the expanded synthetic catalogue

This is a local demo on one computer, not a shared enterprise web server. Keep
binding to `127.0.0.1`, use one dashboard process/worker, and do not expose it via
a network proxy or tunnel. No tests or paid calls were run for this change.

Admin setup, secure persistence and enterprise migration: [ACCOUNTS_SECURITY.md](ACCOUNTS_SECURITY.md).

## Sign-up and API-key workflow

1. Stop the old dashboard/launcher so it can load the new code.
2. Start Docker Desktop, then run `scripts/Start-Demo.ps1`.
3. The operator chooses a synthetic hotel portal password (12+ characters) for automated extraction. This is separate from dashboard accounts.
4. At `http://127.0.0.1:8120`, select **Create an account** and choose your own username/password. No registration code is needed. Usernames are 3–32
   letters, digits, dots, underscores or hyphens, case-insensitive; passwords are
   12–128 characters. There is no automatic account named `demo`.
5. Sign in. Guided form planning works without an API key.
6. Optionally enter your key/model under **Your API connection** and confirm billing authorization. Session-only is the default. Select **Remember my key on this computer** to use supported secure OS storage. Saving does not verify access or ownership or make a paid call. Each model-planning request still requires explicit paid-API consent.
7. Use **Clear session key** or **Sign out** when finished. Remembered credentials survive logout/restart and reload after login; use **Forget saved key** to remove them. Expiry (one hour) or restarting
   the server also removes session access. Expired keys are pruned on access and
   by a 30-second background sweep. Already-started work may finish using the
   key it captured at submission; sign-out does not cancel side effects.

Keys are never written to account/job files, browser storage or cookies, and are
not returned by endpoints. Dashboard planning never falls back to `OPENAI_API_KEY`
from the environment. CLI configuration is unchanged. No automatic retries are
configured for dashboard model calls. Python memory cannot promise cryptographic
erasure of immutable strings; session-only means no intentional persistent storage.

Each browser profile has one signed-in dashboard account. To compare two users,
use separate browser profiles/private windows or sign out between users.

## Storage, ownership and migration

- `data/accounts.sqlite3`: UUIDs, normalized usernames and independently salted
  PBKDF2-SHA256 password hashes (600,000 iterations). No raw passwords or API keys.
- `data/users/<account-uuid>/`: private plans, job history, listings DB and exports.
- NATS stream `USER_<ACCOUNT_UUID_HEX>`: each user's own event subjects and receipts.
- One active dashboard job globally; additional submissions are rejected, not queued.

Existing shared data under `data/plans`, `data/dashboard-jobs`, etc. is preserved
but is not assigned to new users or exposed through their dashboards. CLI tools
can still inspect it. Existing user accounts survive restart and a changed
portal password. An administrator UI now manages roles and account status. There is still no password-reset or email recovery flow.
Do not delete the accounts DB as a reset: that would orphan user workspaces.

Application-level isolation prevents another logged-in user opening a guessed
job, plan or download ID. It does not protect against someone with access to the
same OS account, filesystem, process memory or unauthenticated local NATS service.
Shared enterprise hosting requires stronger identity, TLS, authorization and
secret-management controls. This version is deliberately local-only.

## Catalogue

Exactly 100 fictional hotels: 10 each in New York, Boston, Chicago, Los Angeles,
San Francisco, Seattle, Miami, Las Vegas, Washington DC and Atlanta. Suggestions
appear in the portal and dashboard city fields. All prices are fixed synthetic
USD/night including taxes; all ratings are out of five. No real availability or
real hotel inventory is implied. The original six IDs/values are preserved.

With the default maximum USD 200 and minimum 4/5, New York now returns **10 records,
5 matches and 5 verified receipts** after successful execution. A maximum USD 50
returns no matches. Historical run snapshots and old test results are unchanged.

## Run verification yourself

```powershell
uv run --locked pytest tests/test_catalog.py tests/test_dashboard.py tests/test_dashboard_accounts.py tests/test_portal.py -v --tb=short
uv run --locked pytest -q
uv run --locked pytest --run-browser --run-nats -q --tb=short
```

The above tests mock models and do not incur API charges. The integration command
needs Chromium and local NATS. Then manually verify registration/login, both
frameworks' structured runs, ten-city filtering, private history across two users,
session key save/clear, logout/restart behavior and JSON/CSV exports. Only try live
model planning when you explicitly choose to incur API costs.

Per-user model configuration follows the server-side credential boundary in the
[OpenAI API reference](https://developers.openai.com/api/reference/overview).
