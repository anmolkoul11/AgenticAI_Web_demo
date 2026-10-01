# Automated browser modes — awaiting manual verification

This applies to Website Studio's **Open a website** path, for both LangGraph and
CrewAI. The extension-based **Use my browser** path remains separate.

## Start a normal-network session

1. Restart the dashboard using your existing launcher. Refresh the dashboard
   (Ctrl+Shift+R if it was already open). The new UI version is `2026-10-01.2`.
2. Sign into your dashboard account and configure your model connection.
3. Choose **Website Studio → Open a website**. Enter one public HTTPS starting URL
   and your request. The URL, prompt and extraction limits work as before.
4. In **How should the automated browser open?**, choose:
   - **Restricted networking (default)** for the existing filtered path; or
   - **Normal networking — no app network restrictions** for the new direct path.
5. Choose **Bundled Chromium**, **Installed Google Chrome** or **Installed
   Microsoft Edge**. Chrome/Edge must already be installed; there is no silent
   fallback. Bundled Chromium requires `uv run --locked playwright install chromium`.
6. For normal mode, confirm its separate supervised-session checkbox. This is
   separate from paid-model consent and permission to process website data.
7. Choose no login, manual login or automatic website credentials. In normal
   mode, an external HTTPS identity origin need not be allowlisted. Review the
   website and use a dedicated test account. An optional explicit login URL can
   help where a unique visible sign-in link is not detected. Credentials still
   require HTTPS and a supported POST/JavaScript or email-first flow. MFA,
   CAPTCHAs, passwordless flows and popup-only sign-in may need manual handling.
8. Confirm the existing authorization and model-consent checkboxes. Click
   **Open website and start**. Keep the original browser tab open and inspect it.
9. Check **Page loading status**. It must report the mode and engine actually
   used. Normal mode should not report app-blocked resources. Network failures
   can still come from the site, browser, connection or other installed software.
10. Use the existing reviewed search actions, relevant-link discovery or current
    page extraction. Review the preview, approve saving, and download the results.
    Downloads from our saved results do not make another model call.
11. Cancel and close the session before switching modes. Changing the dropdown
    does not alter a running context. Each new normal session requires confirmation.

## What differs

| Capability | Restricted (default) | Normal networking (opt-in) |
| --- | --- | --- |
| Application network proxy / DNS destination filter | Applied | Not installed |
| Application request-origin / method allowlist | Applied | Not installed |
| Third-party assets, frames, redirects and POSTs | Filtered | Browser defaults |
| WebSocket interception | Connections closed | No interception |
| Popup handler | Extra pages closed | No automatic closing |
| Service workers | Blocked | Allowed |
| Browser downloads | Disabled | Enabled for the temporary context |
| QUIC / non-proxied WebRTC flags | Applied | Not added |
| Automatic login identity allowlist | Required for external identity origins | Not applied |
| Capture origin lock | Starting origin only | Current public page can be captured after redirects |
| Browser sandbox and TLS certificate validation | Enabled | Enabled |
| Profile | Fresh temporary context | Fresh temporary context |

Normal mode does not register `context.route`, `route_web_socket` or our popup
closing handler, and does not start `GuardedProxy`. Browser requests are governed
by the browser/OS/network rather than our app allowlist. This can expose browser
data to third-party services and allow requests to local/private network services.
Use it only on your supervised local prototype; do not deploy it to a shared
enterprise service without a separate review. Native download files are temporary
and discarded when the context closes; saved result CSV/XLSX/JSON exports are separate.

## What is deliberately unchanged

- This is still a Playwright-launched dedicated browser, not your everyday profile.
  Choosing Chrome does not import its cookies, extensions or passwords and does
  not hide automation. There is no stealth, CAPTCHA solving or access bypass.
- The initial input/captured artifacts remain public HTTP(S) URLs under the
  existing capture contract; the browser's network traffic is not subject to
  that artifact-validation rule in normal mode.
- Credentials are not sent to the model or intentionally persisted. HTTPS,
  unambiguous controls and no native credential-bearing GET submissions remain
  requirements for automatic credential filling.
- The ten-minute lifecycle, logout/cancel handling, access-challenge/password-form
  checks, robots.txt capture checks, source-text caps, evidence validation,
  reviewed action plans, save approval and optional event approval remain.
  These are workflow/data checks, not browser resource blocking.
- Search planners still support bounded visible controls. Link discovery still
  proposes up to five same-site links relative to the current page. Opening
  pages fully does not guarantee the planner can operate every site's controls.
- Extra tabs are allowed, but automation/capture continues to target the original
  tab. If sign-in finishes in a popup, return to/reload the original tab yourself.

## Checks for you to run

No tests or live website sessions were run by the coding agent for this change.

```powershell
uv run --locked pytest tests/test_browser_modes.py tests/test_dashboard_ui_structure.py tests/test_browser_login.py tests/test_browser_navigation.py -q
```

Browser-enabled login/navigation fixtures, if desired (no paid model tests):

```powershell
uv run --locked pytest tests/test_browser_modes.py tests/test_browser_login.py tests/test_browser_navigation.py --run-browser -q
```

Then manually compare the same site in a new restricted session and a new normal
session. Check page styling, visible controls, sign-in redirects, search results,
preview provenance, exports, cancel and logout. In normal mode inspect the live
Chromium/Chrome/Edge tab, not just its HTTP status. If the site still returns a bot
warning or access denial, record that separately from app-blocked resources.

Normal mode is not a guarantee of compatibility with NYTimes, Booking or any other
site. It is an explicit way to separate our network-filtering effects from
website restrictions, browser automation compatibility and extraction issues.
