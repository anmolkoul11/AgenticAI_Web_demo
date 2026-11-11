# Dashboard usability verification

For the latest direct-button actions and shared logo, use
[the regression test cases](DASHBOARD_REGRESSION_TEST_CASES.md). That guide
contains the targeted pytest commands and current manual acceptance scenarios.

No tests or live API calls were run for this UI change.

Restart the dashboard, then hard-refresh the browser (Ctrl+F5).

1. Open `http://127.0.0.1:8120/#login`. Only sign-in should appear.
2. Select **Create an account**. The separate `#register` screen asks only for a username and password. Browser Back returns to sign-in. Registration success returns to sign-in without automatically logging in.
3. Sign in. Create a guided proposal. Review the human-readable fields; technical JSON remains available in an expandable section. Approval is still required before execution.
4. With your session API key configured, choose **Create AI preview** for an incomplete natural-language request. A prominent information panel should show the returned guidance and missing field labels without opening JSON.
5. Select **Edit search**, complete the request and choose **Create AI preview** again. Editing alone must not retry a paid call or execute tools.
6. Try **Use guided form**. Review every field: this switches modes without copying uncertain model interpretations into the form.
7. Inspect an unsupported or failed job. Its guidance should be visible; execution failures should warn that earlier stages may already have produced side effects.
8. While a job is running, creating another proposal is disabled. Verify keyboard focus, narrow-window layout, logout and your existing account/key isolation checks.

No registration code is required. Anyone who can access the local dashboard can register. Keep it bound to loopback; do not expose it through a network proxy or tunnel. The launcher still asks for the separate synthetic hotel portal password (`DEMO_PASSWORD`). Existing accounts and session-only API-key handling are unchanged.

Planner semantics are unchanged: the UI displays actual returned guidance and does not invent an explanation for invalid dates or add minimum-price support.

## API connection setup notice

Restart the dashboard and hard-refresh after updating to `2026-10-25.1`.

1. Sign in without a session key. Confirm **API connection required** appears
   above every workspace section, with **Set up API connection** and a **Setup
   required** navigation badge. This is not hidden in Follow and review.
2. Enter a website/task, then select **Set up API connection**. The connection
   form opens with keyboard focus on the key field; returning to Website Studio
   retains the task and source. No browser or paid run should start.
3. Save a connection. The notice disappears, the workflow action returns to its
   normal label, and no workflow starts until explicitly approved. A configured
   key is labelled unverified, not promised to be valid or funded.
4. Clear the session key, or forget the saved key. The notice returns. If another
   dashboard tab clears the same session's key, the existing heartbeat updates
   the notice without navigation or automatic retries.
5. With no key, the guided hotel demo remains available, as do saved results and
   downloads. AI-assisted proposal creation opens API setup before making a call.
6. Snapshot transfer remains free. Without a received capture, its extraction
   button still explains that it is waiting; the workspace setup button remains
   available. Logout/session-loss notices must not be mislabelled as a missing key.

## Website Studio visual pass

After restarting and hard-refreshing, check the new Website Studio separately:

1. Choose each of the four source cards. The short guidance should change, while
   the underlying source method remains synchronized in Advanced settings.
2. Keep Advanced settings closed for a basic public-page run. Open it to confirm
   framework, record limit, sign-in, trusted origins, rules and NATS controls are
   still available. Automatic sign-in should open it for credential entry.
3. During a browser run, watch the seven checkpoints advance. Expand one while
   updates are arriving: it should stay open and remain keyboard-usable. Page
   health, blocked-resource diagnostics and captured-page coverage should be
   accessible without opening raw job JSON.
4. Inspect a `needs_input` or failed run. The affected checkpoint should show
   **Needs attention** with useful guidance. Review and approval must still be
   explicit; a failed run must not appear as saved.
5. Save a reviewed run and download CSV or Excel. If optional event publication
   fails after saving, **Save results** must remain done while **Publish
   event** shows the delivery failure. Broker acknowledgement is not a consumer
   receipt.
6. Repeat at a narrow browser width and with keyboard-only navigation. The
   page is a local demo; this UI update does not make blocked third-party sites
   accessible or turn model outputs into verified facts.
