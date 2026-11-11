# Agentic Studio

Agentic Studio helps you collect information from websites without copying it
into a spreadsheet by hand. Describe what you need, let the browser agent work
through the page, and review the results before saving them.

You can use it to find hotels for a particular stay, collect articles on a topic,
or turn information from a website into an organized set of results. The fields
adapt to your request and the information available on the page.

## How it works

1. **Choose your browser.** Open a new browser from the dashboard, or connect
   your existing Chrome or Edge tab with Browser Companion.
2. **Describe your task.** Include the details that matter, such as a topic,
   dates, guest counts or a price range.
3. **Let the agent collect the information.** It can navigate, fill search forms
   and read results. Complete website sign-in, CAPTCHA or missing details when
   prompted, then resume the task.
4. **Review and save.** Check the results, links and source evidence, save the
   reviewed results, and download Excel, CSV or JSON.

The results remain a preview until you approve saving them. If information is
missing or uncertain, the dashboard shows it for review.

## Start using the Windows app

The current Windows package is **`AgenticStudio-1.0.0-win-x64.zip`**, a portable
app rather than a Setup.exe installer. Extract the whole ZIP and open
`AgenticStudio.exe`. Python, the required libraries and Chromium are included;
you do not need to install developer tools or Docker.

Create a local account and add your own OpenAI API key in **API connection**.
Browser Companion is included, but must be added to Chrome or Edge separately
if you want to use an existing tab.

Follow the [Windows quick start](docs/WINDOWS_DISTRIBUTION.md) for the short,
step-by-step instructions.

## Where your information goes

The app and its backend run on **your computer**. The app starts the backend
for you and opens the dashboard in your browser; the developer's PC does not
need to be online.

Your prompt and captured page content are sent to OpenAI for processing, so
internet access is required and API usage is billed to your configured account.
Accounts and results stay on your computer. The Windows package stores them in
`%LOCALAPPDATA%\AgenticStudio\data`. Remembering an API key is optional and
uses the operating system's credential store.

Keep the app and dashboard tab open while a task is running. Use **Stop and
close** in the app's status window when finished.

## For developers

The project uses Python, FastAPI and Playwright. LangGraph runs the autonomous
browser agent; CrewAI is also available for extraction and save workflows.
Both use the shared source checks, storage, rules and export tools.

For the desktop workflow from source, install [uv](https://docs.astral.sh/uv/)
and Python 3.11, then run these commands from the repository root in PowerShell:

```powershell
uv sync --locked
uv run --locked playwright install chromium
$env:AGENTIC_DEMO_DATA_DIR = "$PWD\data"
uv run --locked agentic-studio
```

Close any other running dashboard before starting another copy. The data setting
above keeps development records in the repository's ignored `data` folder.
`.env.example` describes the configuration; `.env` files are not loaded automatically.

For the separate synthetic hotel demo, use the
[developer dashboard guide](docs/DASHBOARD_GUIDE.md). That full demo launcher
requires Docker; the desktop app does not.

## Current status

This is an active pilot project. Manual runs have been reported working with
Booking.com, Tripadvisor, BBC and The New York Times. Website layouts and access
rules can change, so check important details before relying on the results.

The Windows download is an unsigned pilot ZIP. It still needs manual testing
before wider distribution. A standard Windows installer and browser-store
release are the next steps.

## Useful guides

- [Windows quick start](docs/WINDOWS_DISTRIBUTION.md): open the app and set up Companion.
- [Website workflow](docs/UNIFIED_WORKFLOW_GUIDE.md): understand collection and review.
- [Account administration](docs/LOCAL_ACCOUNTS.md): technical details about accounts and saved credentials.
- [Build a Windows release](docs/WINDOWS_RELEASE_BUILD.md): packaging and publisher instructions.
- [Verification checklist](docs/VERIFICATION_CHECKLIST.md): manual checks and test guidance.
- [Progress notes](docs/PROGRESS.md): changes, known issues and verification history.

Source code is in `src/agentic_web_demo`, the browser extension is in
`extensions/page-capture`, packaging files are in `packaging/windows`, and tests
are in `tests`.
