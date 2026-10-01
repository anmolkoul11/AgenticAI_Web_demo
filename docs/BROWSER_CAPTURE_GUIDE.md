# Capture from your normal Chrome or Edge

Implementation checkpoint: browser/runtime and test-suite validation still pending.
No assistant-run tests, live sites, browser launches or paid calls were performed.

## Install once

1. Start the local dashboard with `./scripts/Start-Demo.ps1` and sign in at
   `http://127.0.0.1:8120` (or `http://localhost:8120`). Refresh with Ctrl+F5 after updating.
2. In Chrome open `chrome://extensions`; in Edge open `edge://extensions`.
3. Enable Developer mode, choose **Load unpacked**, and select
   `D:\Projects\AgenticAI_Web_demo\extensions\page-capture`.
4. Pin **Agentic Studio Page Capture** to the toolbar. Install only this reviewed local
   extension; no web-store publication is included in this checkpoint.

## Use it

1. Open **Website Studio -> Use my browser** in the same Chrome or Edge where you installed
   the extension. Enter the HTTPS address and select **Open website in this browser**.
   This opens a normal tab in that browser; the dashboard does not proxy its traffic,
   automate sign-in, or receive website credentials. You can also open the URL yourself.
2. In that same browser, open content you are authorized to process. Sign in yourself if
   required. Open the actual article/listings, not an access-denied page. The extension
   does not solve verification, bypass paywalls, or follow links automatically.
3. Click the extension, then **Capture visible content**. Review the complete JSON preview
   (text, link destinations and source URL). Forms, input values, hidden content and iframes
   are excluded, but visible personal information can remain. Do not transfer secrets.
4. Check the authorization checkbox and choose **Keep this capture for transfer**.
5. Switch to your signed-in dashboard tab and open the extension again. Check the displayed
   destination account and source preview. Confirm, then **Send to displayed dashboard account**.
6. In **Custom Website**, the source switches to **Capture from my Chrome / Edge** and shows
   the received snapshot. No model call has happened. You can discard it without API cost.
7. Choose LangGraph or CrewAI, enter optional instructions, and confirm both permissions.
   Select **Inspect & preview extraction**. This makes the normal paid model request.
8. Review source evidence, filters, warnings and rejected fields. Partial results require
   an additional checkbox before **Approve & save snapshot**. Downloads and optional events
   include only accepted records. If none survive, no approvable proposal is created.
9. After transfer, use **Discard capture** in the extension to remove its temporary copy.
   It is retained briefly to allow retrying a failed handoff, not silently resent.

Example instruction: "Extract the visible article headlines and their link URLs. Include
authors and publication dates only when present; otherwise leave them empty. Do not summarize."
Blank instructions infer main content without default hotel filters.

## What is captured

- Top-frame rendered DOM text, grouped as headings, paragraphs, table rows, links or text.
- Up to 200 source blocks, 6,000 characters per block and 24,000 total text/link characters.
  Limits set a truncation flag. Loaded off-screen text may be included; not only the viewport.
- Source block IDs are retained with proposals and mapped to matching evidence quotes where
  possible. Cross-block quotes can have no single block match. Literal support is not proof
  that records were associated correctly or that all requested constraints were captured.
- Query strings and fragments are removed from page/link URLs. This reduces token leakage
  but may make query-based links incomplete. Sensitive values in URL paths are not detected.
- No screenshots, canvas/OCR, shadow DOM, iframe extraction, crawling or pagination.
  Content is an explicitly supplied snapshot, not proof of a current, complete live site.

The Playwright path uses the same block extractor after its existing network/robots checks.
Static HTML and pasted text still use text evidence without DOM block structure. Imported
captures do not perform a second network fetch or robots check; the user must ensure access,
reuse and model-processing permission. Successful viewing alone is not authorization.

## Security and retention

The extension requests only activeTab, scripting and storage; no all-sites host permissions,
cookies, history, background capture, remote code or API-key access. Capture contents can
still be sensitive: review before keeping and sending. Captures are held in extension
session storage, not sync/local disk storage. Ten-minute expiry is checked on use; discard
or browser restart clears them. This is not a secure-memory-erasure guarantee.

Transfer occurs from the explicitly selected loopback dashboard tab using its same-origin
session and CSRF protection. The account and session must match what the popup displayed.
There is no public cross-origin receiver, wildcard CORS permission or persistent pairing token.
The inbox has 20 slots globally, a ten-minute lifetime, session-bound one-time claims and
periodic cleanup. Logout/revocation makes old claims inaccessible. A refreshed dashboard
loses unsent preview data; resend the still-valid extension capture if necessary.

After submitting extraction, proposals and rejected-field diagnostics persist in the account's
local job/proposal files, as with existing workflows. Rejected values are never promoted into
normal result exports/events. Dashboard logout/connection loss clears the in-memory preview.
No paid extraction or save happens merely by receiving a capture.

For this checkpoint the extension recognizes only localhost/127.0.0.1 port 8120. Remote/shared
deployment needs a separate identity, trusted-origin and extension-distribution design.
This is a user-assisted path; do not claim it demonstrates automated external-site login.

## Checks for you to run

```powershell
uv run --locked pytest tests/test_capture_handoff.py tests/test_custom_website.py tests/test_browser_login.py tests/test_dashboard_ui_structure.py -v
```

Then manually check:

1. Capture an authorized external page; preview matches the page and reports truncation.
2. Discard and recapture; verify the extension never transfers without explicit confirmation.
3. Sign out or switch accounts after opening the extension: sending must require reopening
   and checking the current account. Old capture IDs cannot be claimed in another session.
4. Send to a signed-in dashboard without an API key: preview should still work, extraction
   should require configuring a key. Try both frameworks on the same captured fixture.
5. Review an all-valid result, partial result and all-rejected result (offline fixtures cover
   the latter two without relying on unpredictable live-model mistakes).
6. Confirm partial approval is mandatory and rejected records are absent from saved exports
   and rule/event inputs. Download CSV, XLSX and JSON from a completed accepted run.
7. Restart/refresh checks; verify expired captures and invalid source URLs fail safely.

## Design references

- [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
  and [session storage](https://developer.chrome.com/docs/extensions/reference/api/storage).
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs):
  schema conformance does not remove the need to validate source support.
