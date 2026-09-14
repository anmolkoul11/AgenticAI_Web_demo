# Progress

## Completed checkpoint 1

- User verified package startup and all 7 foundation tests in VS Code.
- User approved local commit and checkpoint 2.
- Foundation commit: `7625e46` (no push).
- Windows setup required uv installation from the explicit WinGet source and
  refreshing terminal PATH. The user then installed/synchronized Python locally.

## Current checkpoint 2

Implemented a local FastAPI/Jinja2 portal with dedicated login, six seeded hotel
listings, city/date search, empty/error states, CSRF, session expiry, logout
revocation, and responsive CSS. Configuration requires explicit secrets.

Automated verification passed. Browser visual review remains a user checkpoint.
The detailed startup and review instructions are in `PORTAL_GUIDE.md`.

### Verification evidence

- Python 3.11.16: 29 tests passed (7 foundation, 22 portal cases).
- Ruff lint and formatting checks passed; `git diff --check` passed.
- Source distribution and wheel built; all three templates and the CSS asset
  were verified inside the wheel.
- Started a real loopback Uvicorn process with temporary credentials: health,
  denied anonymous listing access, login, four New York results, and CSS delivery
  passed. Stopped the temporary process afterward; no server is left running.
- Two upstream deprecation warnings remain: Starlette's httpx test-client
  integration and its AnyIO BlockingPortal alias. Neither failed the tests;
  revisit test-client compatibility during dependency maintenance.
- No automated browser/visual test is claimed at this checkpoint. User browser
  review follows the manual checklist; Playwright comes in checkpoint 3.

## Boundaries

No external websites accessed, no scraping/storage/rules/events/agent workflow
implemented, no model provider chosen. Checkpoint 2 is not committed or pushed.

## Next step

Complete automated checks, have the user review the website in their browser,
then request approval to commit checkpoint 2 and begin checkpoint 3.
