# Local accounts, administrators and remembered credentials

This implements local-demo administration, **not a production identity system**.
Keep the server on loopback, one process/worker, without a proxy or tunnel.

## Setup

1. Stop the dashboard and install the updated locked dependencies: `uv sync --locked`.
2. Back up `data/accounts.sqlite3` while stopped. Existing accounts migrate to enabled
   ordinary users; passwords, UUIDs and workspaces are retained. Nobody is automatically
   promoted. Account schema additions happen at startup.
3. Run `uv run --locked python -m agentic_web_demo.dashboard.admin_setup` once.
   Choose a **new** username and strong unique password interactively. No default
   admin password, command-line password, or browser-based first-user takeover exists.
   The setup refuses if an admin already exists, including a disabled admin.
4. Start `./scripts/Start-Demo.ps1` and refresh the browser. Sign in as the admin.
   Existing ordinary accounts continue working. Registration remains open locally.

## User-owned API connections

The user signs in, pastes their own key, selects a model, and confirms authorization
to use the associated billing account. Session-only remains the default. Optional
**Remember my key on this computer** uses Windows Credential Manager, macOS Keychain,
or Linux Secret Service. The server explicitly selects those backends; it does not
use arbitrary keyring plugins, plaintext fallbacks or environment-selected backends.
Unsupported/headless systems retain session-only operation. A locked store reports
an error; saving is never falsely reported successful. OS unlock prompts may appear.

Keys are stored under an application-installation namespace and an authenticated
account UUID. Client-supplied owner IDs are forbidden. API keys never enter SQLite,
audit events, browser storage, returned JSON or model job state. Keys are available
to the server process in memory while used. This is credential access, **not proof
of OpenAI account ownership**. No verification API calls run when saving/loading.

On login, a saved key is restored only for that account. If loading fails, login
still succeeds with guided mode and an actionable storage notice. Other users'
keys and environment keys are never used as fallback.

- **Clear session key** clears only this session; remembered credentials persist.
- **Forget saved key** removes the OS entry and clears keys from all that user's
  sessions. If the OS store cannot be accessed, deletion fails visibly rather than
  claiming success. Unlock it and retry.
- Saving a session-only key leaves an existing remembered key unchanged.
- Replacing a saved key clears other sessions' cached keys; those users can sign
  in again to load the replacement. Already-started jobs retain captured keys.
- Forgetting locally does not revoke a key at OpenAI; revoke compromised keys at
  the provider as well. Logout clears memory sessions, not remembered OS entries.

Moving the data directory changes its credential namespace; re-enter keys after
moving. Backing up SQLite does not back up OS credentials. Do not delete account
records to reset passwords; this can orphan data and OS credential entries.

## Administration boundaries

Admins list users, enable/disable accounts, grant/remove admin roles, revoke
sessions, and inspect the last 100 audit events. Every mutation requires the
admin's current password, CSRF and same-origin checks, and rate limiting. Roles
are checked server-side on each request. Role/status changes revoke target sessions.
Self-disable/self-demotion and removal of the last active admin are rejected.

Admins cannot read/set/use someone else's API key, inspect private jobs through an
admin endpoint, impersonate a user, or reset passwords. Password reset is deliberately
not implemented: allowing an admin to take over a login would also unlock saved
credentials. A future recovery design must invalidate/delete saved credentials,
verify user identity and force re-enrollment. Keep a second trusted administrator
for access management; lost-password recovery currently needs a separately designed
operator procedure. There is no built-in hard-delete or reset tool.

Disabling/revoking sessions does not cancel accepted jobs or revoke provider keys.
Audit rows contain actor/target UUIDs, timestamps and action names, not passwords
or keys. Local audit storage is not tamper-proof or externally retained. Successful
registration, bootstrap, admin actions, remembered-key save and forget are recorded;
this is not comprehensive enterprise security telemetry.

## Trust boundary and enterprise migration

Anyone controlling the shared OS account, application code or local filesystem can
bypass application-level protections. Desktop keyrings do not separate dashboard
users at the OS level. This is for trusted local demo participants only.

Before shared enterprise hosting:

| Local component | Required enterprise replacement / acceptance work |
| --- | --- |
| Local passwords and open signup | Organization OIDC/SSO, MFA, approved membership, recovery and offboarding policies |
| Desktop keyring | Managed vault using workload identity, per-user/tenant authorization and audited secret access |
| SQLite and process sessions | Transactional shared database, migrations/backups, centralized revocable session store |
| Single in-process worker | Durable queue, job ownership, idempotency, cancellation semantics and graceful release draining |
| Local admin audit | Central append-only security logs, retention, alerting, failed-access events and security review |
| Loopback HTTP | TLS, secure cookies, deployment-specific trusted origins/hosts and ingress protection |
| Account-level isolation | Enforced tenant boundaries across records, proposals, brokers, downloads and credentials |
| Personal API billing | Approved provider/project provisioning, rotation, quotas and spend policy |

Do not enable network access merely by changing the bind address. Document threat
model, operational recovery, deletion/retention and test cross-tenant authorization
before claiming enterprise readiness. Desktop setup/launcher scripts are currently
PowerShell; the Python storage layer is cross-platform, not a complete cross-platform
one-click installer.

## Verification (user-run; no tests or paid calls run by the assistant)

`uv run --locked pytest tests/test_dashboard_security.py tests/test_dashboard_accounts.py tests/test_dashboard.py tests/test_dashboard_updates.py -v --tb=short`

Manually verify admin bootstrap, ordinary-user admin denial, disable/sign-out,
role changes, lockout protection, separate users' saved keys across restart,
session-only behavior, forget, and unavailable/locked-keyring errors. Use disposable
credentials and never paste keys into logs. Automated tests use an in-memory fake
credential store, not the real OS keyring. Test real backend behavior separately on
each supported OS; its presence is not proof that the OS store is unlocked.

References: [Python keyring documentation](https://keyring.readthedocs.io/en/stable/)
and [OpenAI API authentication](https://developers.openai.com/api/reference/overview).