# Windows release build and engineering notes

For user setup, see [the short Windows guide](WINDOWS_DISTRIBUTION.md).

## Where the backend runs

Each user installs their own copy of Agentic Studio. Opening its desktop shortcut
starts one backend process on that computer at `http://127.0.0.1:8120` and opens
the dashboard in a normal browser. The status window must stay running; it can
be minimized. There is no dependency on the developer's PC or an always-on
shared server. Closing a dashboard tab does not stop the backend. Closing the
desktop controller stops its own backend; it does not stop unrelated processes.

| Component | Runs or is stored where |
| --- | --- |
| Dashboard, account sessions and workflow orchestration | User's computer |
| Browser Companion and the selected website tab | User's Chrome or Edge |
| New-browser collection | Included Playwright Chromium on the user's computer |
| Model inference | Configured AI provider over the internet |
| Accounts, previews, approved results and exports | `%LOCALAPPDATA%\AgenticStudio\data` |
| Opt-in remembered API keys | Existing Windows credential-store integration |
| Desktop lifecycle log | `%LOCALAPPDATA%\AgenticStudio\logs` |

Prompts and captured page content are sent to the configured AI provider for the
requested task. Local storage does not mean offline AI. Each user supplies their
own API connection in this release; shared company billing is not implemented.
Website login, MFA, CAPTCHA and values absent from the prompt remain with the
user. Final Save still approves the reviewed snapshot.

The dashboard stays in a normal browser tab because Companion uses that tab for
its authenticated local connection. A separate embedded WebView is not part of
this package. Remote hosting would require a separate connection/authentication
design; changing the extension URL alone would not provide it.

## What the product launch changes

The new `agentic-studio` entry point starts Website Studio without the synthetic
hotel portal, its demo password prompt, or Docker. The existing
`scripts/Start-Demo.ps1` continues to launch the developer demonstration.
Hotel demo navigation is hidden only in desktop mode. Rule fields remain;
optional event publishing is hidden by default because no broker is installed.
An administrator can configure a broker separately and explicitly enable its
desktop UI with `AGENTIC_DESKTOP_ENABLE_EVENTS=1`.

The installed app includes Python, its locked dependencies, dashboard assets,
default rules and the Playwright Chromium version matching its runtime. Its
BrowserCompanion folder uses the existing extension. Current website navigation,
stay checks, pricing, article selection and save approval are reused.

The backend binds only to loopback; no LAN listener, firewall opening, Windows
service, start-at-login task or automatic updater is installed. Port 8120 remains
fixed to preserve the extension connection. If a development dashboard already
uses that port, close it before starting the desktop app. Reopening a running
desktop app opens its dashboard rather than starting a second backend.

## Build on the publisher's Windows computer

Build requirements are for engineers/publishers, not end users:

- Windows x64 and uv.
- Internet access for locked dependencies and the matching Chromium download.
- Inno Setup 7 or a current Inno Setup 6 for the installer; the folder/ZIP build
  can be made without it.

From the repository root:

```powershell
.\scripts\Build-WindowsRelease.ps1 -Version 1.0.0
```

For a portable pilot package only:

```powershell
.\scripts\Build-WindowsRelease.ps1 -Version 1.0.0 -PortableOnly
```

If ISCC is not on PATH, pass `-InnoCompiler` with its full executable path.
PowerShell must permit the reviewed build script; honor organizational policy.
The script creates its own locked environment under `build/windows-release/venv`
and preserves the developer `.venv`. Existing release output is refused rather
than overwritten. Use a new version or explicitly archive the prior output.

Output under `dist/windows/1.0.0/`:

- `AgenticStudio/`: complete portable application, including `_internal`.
- `AgenticStudio-1.0.0-win-x64.zip`: complete folder for a supervised pilot.
- `BrowserCompanion-1.0.0.zip`: extension package for a separate store submission.
- `AgenticStudio-Setup-1.0.0-win-x64.exe`: per-user installer when ISCC is available.

Only application resources, locked runtime packages and explicitly named
extension assets are staged. Project `data`, `.env`, browser profiles, private
reinstall backups and local API credentials are not distribution inputs.
Third-party notices and dependency versions are included. Publisher identity,
application terms, signing and store publication are separate release actions.

Building does not launch the installed application, run tests/workflows or call
the AI provider. A successful build is not end-to-end acceptance.

## First user setup

1. Install Agentic Studio, or extract the entire portable ZIP to a stable folder
   and open `AgenticStudio.exe`. Do not run it directly from inside the ZIP.
2. Keep the status window running. Use the dashboard it opens in Chrome or Edge.
3. Create a local account, open API connection and add the user's own key/model.
   Remembering a key is optional and uses the existing OS store.
4. Install Browser Companion using the publisher's store link. For a supervised
   pilot before store publication: choose **Extension setup** in the desktop
   controller, open `edge://extensions` or `chrome://extensions`, enable Developer
   mode and use **Load unpacked** to select that BrowserCompanion folder.
   Store publication is required to remove this developer-mode setup from the
   general-user experience. The installer cannot silently install an extension.
   If the developer copy of Companion is already installed, disable that copy
   before loading the packaged one so there is only one active Companion.
5. Keep the signed-in dashboard in the same browser as the website. Open the
   Companion on the website, enter a task and start. Alternatively choose
   **Open a new browser** in the dashboard; its Chromium is included.
6. Complete any requested website sign-in or missing values, then review, save
   and download approved results.

Browser-level control can display the browser's own debugging warning. The app
does not hide that permission prompt. The extension operates on its connected
website tab; the dashboard continues to handle review and saving.

## Data, updates and release acceptance

User data lives outside the installation directory and is retained by normal
installer upgrades and uninstallation. A desktop package does not copy the
developer's existing accounts/results to another user's computer. Existing
developer data stays at its original location. A deliberate
`AGENTIC_DEMO_DATA_DIR` override remains available for managed setups.

Back up the data folder separately after closing the app. Windows-stored API
keys are not included in that folder backup; users may need to add them again
after moving computers. Updates are manual installers in this first release.
Do not replace an installed app while a workflow is running.

Before sharing externally, manually verify a clean Windows machine:

1. First launch, account creation, API setup and a second launch.
2. Companion connection in Chrome and Edge, including pause/resume and review.
3. Booking explicit Search followed by hotel extraction, individual URLs/prices.
4. Tripadvisor live results without requiring a separate Search submission.
5. BBC and NYTimes articles, including actual headlines on editorial audio items.
6. New-browser mode with included Chromium and no separate browser installation.
7. Save/export, close/reopen persistence, uninstall/reinstall with data retained.
8. A port conflict leaves the unrelated application untouched.

Authored local regressions (not executed during packaging implementation):

```powershell
uv run --locked pytest tests/test_desktop_configuration.py tests/test_desktop_dashboard.py -v
```

The unsigned candidate needs publisher terms/privacy copy, code signing and
browser-store submission before a general-user release. No store publication,
signing, background service or remote deployment is performed by the build.

Implementation references: [PyInstaller bundle resources](https://pyinstaller.org/en/stable/runtime-information.html),
[Playwright browser bundling](https://playwright.dev/python/docs/library#pyinstaller),
and [Inno per-user installation](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
