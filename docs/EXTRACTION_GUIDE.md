# Checkpoint 3: browser extraction and local storage

## What this implements

Playwright opens Chromium, fills and submits the actual login form, searches the
rendered listings page, extracts its DOM fields, validates all records with
Pydantic, and logs out. The CLI saves a snapshot in SQLite and exports that run
to JSON. It does not import the seed data or call a listings API.

No model, agent framework, business rule, or event publishing is involved yet.
Only the local demo portal is allowed by this adapter; external-site support
requires a separate authorized adapter. Browser requests are restricted to the
configured local origin. Cookies, passwords and browser profiles are not saved.

## Setup

From the repository in your VS Code PowerShell terminal:

```powershell
uv sync --locked
uv run --locked playwright install chromium
```

Installing the Python package alone does not install Chromium. If uv is available
only via `$uvExecutable`, use `& $uvExecutable` instead of `uv` in these commands.

## Start the website (terminal 1)

Follow `PORTAL_GUIDE.md` to set DEMO_USERNAME, DEMO_PASSWORD and
DEMO_SESSION_SECRET, and leave Uvicorn running at `http://127.0.0.1:8000`.
If the site is already running, leave it running.

## Run extraction (terminal 2)

A new terminal does not inherit the password set in terminal 1. Configure the
same dedicated test account in this terminal. The scraper does not need the
website's signing secret.

```powershell
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Enter the same demo password used by the website" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
uv run --locked agentic-demo extract --city "New York" --headed
```

`--headed` lets you watch Chromium log in, search, and sign out. Omit it for
headless execution. By default, dates are tomorrow and the day after tomorrow.
To set a stay explicitly (choose future dates):

```powershell
$checkIn = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
$checkOut = (Get-Date).AddDays(9).ToString('yyyy-MM-dd')
uv run --locked agentic-demo extract --city "Boston" --check-in $checkIn --check-out $checkOut
```

Change ports with `--base-url http://127.0.0.1:8001`. Use only the local demo site.

## Expected output

The CLI prints a unique `run_id`, a `record_count`, and absolute database/export
paths. New York returns 4 records; Boston returns 2. No city returns all 6.

- Database: `data/listings.sqlite3`.
- JSON: `data/exports/<run_id>.json`.
- `runs` table: one row per successful extraction, including empty results.
- `listings` table: one row per listing per run, with its validated JSON payload.

Each record contains ID, title, city, dates, price, currency, price basis, rating,
rating scale, source URL, and a timezone-aware extraction timestamp. Prices and
ratings serialize as decimal strings to avoid floating-point rounding. USD and
5-point ratings are explicit adapter constraints, not automatic currency conversion.
JSON has `schema_version`, `run_id`, `record_count`, stay metadata, and `listings`.

Repeated extractions append new runs; they never overwrite earlier snapshots.
Duplicate listing IDs within a single run are rejected. This is snapshot history,
not cross-run deduplication. SQLite and exports are excluded from Git under `data/`.
If you override `AGENTIC_DEMO_DATA_DIR`, keep the destination outside Git or add
an explicit ignore rule, particularly for JSON exports.

SQLite commits all records for a run in one transaction. JSON is written from
the committed snapshot via a temporary file and rename. The two outputs are NOT
one distributed transaction: if JSON writing fails, the CLI reports the stored
run ID and returns failure. Recover without rerunning the browser:

```powershell
uv run --locked agentic-demo export --run-id "PASTE-THE-RUN-ID-HERE"
```

Re-export replaces only that run's derived JSON file; SQLite remains the source.

## Review checklist

1. New York extraction reports 4, and JSON contains the four NYC IDs.
2. Boston reports 2; blank city reports 6.
3. `--city "No Such City"` succeeds with 0 and a saved empty snapshot.
4. A wrong password fails without creating a run or writing records.
5. Invalid/reversed/past dates fail without launching Chromium or saving data.
6. Repeat an extraction: the new run ID differs and both exports remain.
7. Stop the portal: extraction fails with a safe error, not a traceback containing credentials.

## Tests

```powershell
uv run --locked pytest
uv run --locked pytest --run-browser
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The default run skips browser tests. `--run-browser` starts a separate temporary
portal on a free loopback port, uses generated test credentials, runs real
Chromium, and stops the server. It does not require your existing server or
credentials and stores test outputs in pytest's temporary directories.

If the portal markup changes or Chromium is missing, errors are intentionally
sanitized: browser call logs can contain sensitive form values. No screenshots,
traces, cookies, or persistent profiles are captured by default.

References: [Playwright Python library](https://playwright.dev/python/docs/library)
and [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).
