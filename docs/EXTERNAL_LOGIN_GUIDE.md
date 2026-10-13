# Checkpoint 4A: email verification handoff (Fox News acceptance target)

Implemented for user-run verification; not yet a verified Fox News integration.
No external sign-in, email submission, browser run or model call was performed by
the assistant. Both frameworks share this authentication lifecycle.

## Scope agreed

Automate the initial email entry/continue step, let the account holder complete
the emailed code or login link in the original browser, then resume navigation and
scraping. Password-plus-MFA can use the existing password method with the same
human confirmation. Email-only authentication is not necessarily MFA: it may be
a passwordless single-factor login. Do not describe the Fox demonstration as a
verified multi-factor flow without observing an additional independent factor.

Fox's official help describes an email login-link flow and acknowledges passwordless
accounts. Its current live page may show a code instead, depending on the entry
point/account. These are references, not proof that our connector works today:

- [Email login help](https://help.foxnews.com/hc/en-us/articles/23074352680475-Are-you-encountering-any-technical-challenges-while-trying-to-log-into-Fox-News-to-access-special-content)
- [Passwordless account help](https://help.foxnews.com/hc/en-us/articles/18031807879195-I-don-t-have-a-password-How-do-I-log-in)

## Manual acceptance

1. Restart the dashboard and hard-refresh (Ctrl+F5). In Custom Website enter
   `https://www.foxnews.com/`, Chromium/Chrome/Edge, your selected networking mode,
   and a complete extraction request such as:

   > Find world-politics headlines and open relevant detail pages. Include the
   > headline, source URL, author where available and a source-backed context excerpt.

2. Select automatic sign-in, then under website credentials choose
   **Email code or login link — no password**. Enter your Fox account email locally.
   No password is required or sent for this method.
3. Leave the login URL blank to start from the requested website and discover one
   visible sign-in entry. If detection is ambiguous, supply the sign-in URL you
   inspected. This is the news website account flow, not TV-provider streaming login.
4. If using restricted networking, explicitly review identity/resource origins
   needed by the actual login flow. In normal networking no application origin
   allowlist is installed. Selecting normal mode still requires its confirmation.
5. For independent login verification, configure an exact CSS selector for a unique
   visible signed-in indicator you inspected (account identity or Log out control).
   No Fox-specific selector has been guessed. Without one, continuation is explicitly
   operator-confirmed, not independently verified by the application.
6. Submit the session. The app attempts one email-field fill and one continue click.
   It never retries/resends automatically. If a sign-in entry/form/POST is unsupported,
   use the original browser to finish it manually; the message identifies the issue.
7. Check your inbox yourself. Enter the code into the website, or open its emailed
   login link **in the original controlled browser context**. A link opened in your
   regular separate browser may not authenticate the automation session. Do not
   paste codes/login links into the dashboard, terminal, chat or extraction prompt.
8. Return to the selected news website in that original tab. Inspect the account
   indicator, then click **I completed sign-in — continue** in the dashboard.
   A visible code/password form, authentication callback page, unexpected origin,
   access restriction or missing configured indicator prevents continuation.
9. Read Page loading status. `authenticated` means the configured visible indicator
   was verified; `operator confirmed` means you attested to login, not that the app
   independently proved it. Returning to the homepage alone is not login evidence.
10. Use reviewed search/link discovery or current-page capture. Approve/save the
    verified preview, download results and, if enabled, inspect event delivery.
    Repeat with LangGraph and CrewAI. Public headlines alone do not prove login.

## Behaviour and limitations

- Search planning, link discovery and capture are unavailable during authentication
  handoff; the application does not send verification screens to the extraction model.
- Detected reauthentication clears pending actions, invalidates the verified claim
  and returns to the human handoff. No automatic resend or action replay.
- Session cancellation, dashboard logout/expiry and the existing ten-minute browser
  timeout stop the run. If the email arrives too late, start a fresh session deliberately.
- Email/password credentials are excluded from proposals and job exports and cleared
  from the input object after the one automatic attempt. The email is redacted from
  capture. OTP values are never read/submitted by the application. Login callback
  queries/fragments are stripped from exported source URLs as before.
- Cookie/session persistence across runs is NOT added. Authentication remains in the
  current isolated browser context. A future persistence feature would require
  per-account protected storage, expiry/revocation and explicit user choice.
- Capture rejects visible verification-code/password inputs. Detection is bounded
  and heuristic, not universal proof of authentication or absence of personal data.
- Dynamic forms/iframes, popup-only login, SSO, passkeys, email links that require a
  different context, unsupported field/button selectors and site anti-bot decisions
  may require manual interaction or a tested site connector. No CAPTCHA/MFA bypass.

## Commands (you run these)

Offline authentication/schema/state checks, without browser/model calls:

```powershell
uv run --locked pytest tests/test_email_authentication.py tests/test_browser_login.py tests/test_browser_modes.py tests/test_dashboard_ui_structure.py -v
```

Opt-in locally fulfilled browser fixtures, not a live Fox account:

```powershell
uv run --locked pytest tests/test_email_authentication.py tests/test_browser_login.py --run-browser -v
```

Save redacted acceptance evidence: framework, selected browser/mode, account indicator,
sign-in verification method, requested topic, approved links, saved records, downloaded
files and event receipts. Never share verification codes, email links, cookies or secrets.

Checkpoint 4B remains the real-site connector/acceptance work; 4C covers parity and handoff.
