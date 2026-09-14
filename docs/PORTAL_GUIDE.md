# Checkpoint 2: local demo website

## Start in your VS Code PowerShell terminal

From the repository folder, synchronize the changed lockfile:

```powershell
uv sync --locked
```

Configure a dedicated demo account. The password prompt avoids putting your
password in shell history. Do not reuse a personal or enterprise password.

```powershell
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Choose a demo password (at least 12 characters)" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
$env:DEMO_SESSION_SECRET = uv run --locked python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run --locked uvicorn agentic_web_demo.portal.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Sign in with username `demo` and the password you
chose. Keep the terminal running; Ctrl+C stops the server. A new terminal needs
the environment variables set again. `.env` is not loaded automatically.

If uv works only through `$uvExecutable` in your terminal, substitute
`& $uvExecutable` for `uv`, including inside the secret-generation command.

## Manual review

1. Open `/listings` in a private browser window: it redirects to login.
2. Enter an incorrect password: an error appears and no listings are disclosed.
3. Sign in correctly: six fictional listings appear.
4. Search for **New York** with a valid future stay: four listings appear.
5. Search for **Boston**: two listings appear.
6. Search for an unknown city: an empty state appears, not an application error.
7. Choose a check-out before check-in: validation appears.
8. Sign out, then visit `/listings`: login is required again.

All rates are fixed USD per night, including fictional taxes and fees. Ratings
are out of five. Dates describe the requested stay; there is no live availability
engine. The New York fixtures include pass, fail and boundary cases for the
future `price <= 200 and rating >= 4` rule. The website itself does not apply that
business rule yet. `data-field` and `data-testid` attributes provide stable browser
extraction targets; no public JSON endpoint bypasses the protected listings page.

## Automated checks

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Tests cover valid/invalid login, protected routes, filtering, invalid dates,
empty results, CSRF, cookie tampering, expiry, logout revocation, trusted hosts,
HTML escaping, configuration, and static assets. They are HTTP integration tests;
Playwright browser automation belongs to checkpoint 3.

## Security scope

- Loopback-only, single-worker development server. Do not expose it to a LAN or
  the internet. No account registration, SSO, MFA, rate limiter or password store.
- The dedicated demo password lives in the server process environment. The
  browser session never contains the password or session-signing secret.
- Signed HttpOnly/SameSite=Strict cookies; one-hour authentication lifetime,
  CSRF tokens on login/logout, and server-side logout revocation.
- Sessions are in memory. Restarting the process invalidates authentication;
  multiple workers are not supported. Do not use `--workers` for this demo.
- Secure cookies are disabled solely for loopback HTTP. An enterprise deployment
  needs HTTPS, proper identity integration, secure cookies, shared session state,
  abuse controls, and a separate security review.

## Windows setup troubleshooting

If WinGet reports a Microsoft Store certificate problem, use the explicit
`--source winget` installation command in the main README; do not weaken TLS checks.
If uv is installed but unrecognized, restart VS Code. To refresh PATH in the
current PowerShell session:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
uv --version
```

If a virtual environment reports `No Python at ...`, verify/install Python from
your own developer terminal with `uv python install 3.11`, then run
`uv sync --locked --python 3.11`. Do not copy `.venv` between machines or users.

Framework references: [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/)
and [Starlette session middleware](https://starlette.dev/middleware/#sessionmiddleware).
