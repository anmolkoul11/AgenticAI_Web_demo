# Custom Website extraction — implementation awaiting validation

## Browser modes and optional sign-in

The automated browser now has two networking modes. **Restricted** remains the
default. **Normal networking** is an explicit per-session option for supervised
local compatibility testing; it removes application network filters, not the
browser's native security or the extraction/review workflow.

See [Browser modes and manual verification](BROWSER_MODES.md) for the exact
differences, setup steps and checks. Normal mode does not use the resource,
verification or identity-origin allowlists described below. Those restrictions
continue to apply in restricted mode. Both modes use a fresh browser context,
not your everyday Chrome/Edge profile or saved sessions.

For the new normal-browser extension, structured capture, and partial-result approval,
start with [Browser capture guide](BROWSER_CAPTURE_GUIDE.md). Both frameworks share the
same extraction validation. Rejected records are quarantined, not silently accepted.
When a record's title and required rule/filter evidence are sound but an optional field
uses an unsupported composite quote, that field is set to null and shown separately
for review. Such previews require explicit partial-result approval; no source value is
invented or silently repaired.

In **Website Studio**, the default source card is **Open a website**. It opens a visible,
dedicated browser on the computer running the dashboard. It does not attach to a
personal Chrome profile or reuse saved browser credentials/cookies.

1. Enter one public HTTPS website URL. Configure your model under API connection.
2. Under **Website access**, choose **No login needed** (default) for a public page,
   **Yes — I will sign in in Chromium** for manual sign-in, or **Yes — sign in with
   website credentials** for one automatic attempt. Only the automatic choice asks for
   credentials. No-login mode starts at the requested page and makes no sign-in attempt.
3. For automatic sign-in, open **Advanced settings** and enter the website
   username/password. The HTTPS login URL
   is optional: when blank, the browser looks for one visible **Log in** or **Sign in**
   entry on the target page. If that entry is ambiguous, provide the login URL.
   These are not your dashboard password or OpenAI key. If sign-in uses a different
   identity-provider domain, review and add its exact HTTPS origin under **Trusted
   identity origins** before starting a new session. Optional CSS selectors can
   identify the username input, password input and continue/sign-in button. Set
   an optional signed-in indicator selector (such as a unique account menu) for
   an explicit success check; without one, review the browser yourself.
4. Confirm site access/data-processing authorization and model consent, then inspect.
5. Chromium opens. Automatic login supports an unambiguous HTTPS POST form, a
   JavaScript button that cannot natively submit a GET form, or an email-first
   screen followed by a password screen. It submits credentials once; a click
   is not proof of login. A configured signed-in indicator must appear before
   the dashboard reports confirmation.
   Unknown identity redirects, email links and MFA pause for manual completion.
   Finish any supported manual steps in the original tab. Optionally select **Suggest search
   actions** for a separate paid model call. It inspects labels of visible search inputs,
   standard select options and search buttons, not input values or the whole page.
   Review the proposed fill/select/autocomplete-suggestion/click/Enter sequence
   before **Run these search actions**. The inspector also sees open-shadow and
   same-origin-frame controls. A **text-search discovery** proposal uses a generic
   search box to find candidate pages; it does not apply date, price, rating or other
   structured website filters. If the model cannot propose safe steps but this is the
   only supported control, the dashboard may offer your exact request (up to 200
   characters) as a reviewed text search. It still makes no claim that the site
   understands those criteria. Review coverage and extraction filters carefully.
   Dynamic destination suggestions may require a separate **partial form** plan:
   approve the initial fill, wait for suggestions, then request and approve another
   plan. A partial form plan is not a submitted search. If the form uses unsupported custom calendars or
   controls, navigate manually or use an authorized API connector. The plan can fail if the
   site changes its DOM; it never retries or books automatically.
6. For a page with relevant detail links, optionally select **Find relevant links (paid API)**. A separate
   model call proposes up to five visible same-origin links based on their titles/snippets.
   Obvious navigation/category links are excluded from a detail-page proposal
   before review, with the exclusion disclosed. A section-only proposal opens
   one approved section without extracting it; request discovery again there.
   Candidate discovery also inspects open shadow roots and up to eight same-origin frames;
   the captured article text itself remains top-frame only.
   If relevant articles are not visible yet, it may instead propose one related section.
   Approve the section, inspect the new page, then request discovery again; at most two
   reviewed section hops are allowed. A section hop does not extract or save articles.
   Inspect exact URLs and uncheck unwanted links, then select **Open selected pages and
   extract**. The original Chromium session visits only approved links, checks robots.txt
   for each path, and captures each article. If some pages fail, the preview is partial
   and requires explicit partial-result approval. No automatic pagination or general crawl.
7. Otherwise select **Extract current page only (paid API)**. Unless you requested
   optional search or article guidance, no model request is sent before capture. Capture
   checks robots.txt, rejects visible password forms
   and common access-challenge text, and extracts bounded rendered text excluding forms,
   editable controls, scripts and obvious hidden elements. This is not a guarantee that
   every sensitive value on a page can be detected—review the page before capture.
   Important: capturing the current page never opens its headline URLs. If you
   need linked-page context, use the separate **Find relevant links**
   action, approve the proposed URLs, then open and extract those article pages.
   An index-only preview may have headlines and URLs, but its `source_url` remains
   the index page and body context from the linked articles is unverified.
8. Chromium closes, then the normal model preview, approval, rules and export workflow runs.

**Preview limit:** The maximum-records setting applies to source-verified records
remaining after deduplication and filters, not to raw model candidates. If the
accepted count exceeds the limit, the dashboard reports both counts and saves
nothing; it never silently cuts records to fit. Broad or truncated pages may
still produce incomplete results. Narrow the links or request before paying for
another extraction call.
When a page has a substantial `<main>` region, capture now uses that region
without continuing through the surrounding menus and footer. This reduces
irrelevant text but does not guarantee complete coverage of long pages.

Cancel closes the session without an extraction call when requested before capture.
Optional search/article proposal calls may already have incurred usage. Closing the
browser, logging out, account/session revocation, server shutdown
or a ten-minute browser timeout stops the session. Shutdown can wait for an in-flight
network timeout. A model request already started cannot be undone by closing the dashboard.

Website credentials are excluded from serialized inputs, proposals and job records.
The dashboard clears the credential fields after submission. Form text is excluded and
known automatically supplied credentials are redacted from captured text. Browser cookies
and credentials are not intentionally saved for later runs; no storage-state, screenshots,
videos or HAR files are recorded. Playwright debug environment flags are disabled before
driver startup to avoid logging credential fills. Memory/OS temporary files are not securely
erased, and this is not an enterprise secret vault. Prefer dedicated demo website accounts.

Browser networking uses a local authenticated safety proxy: it validates DNS results and
connects to public IPs, with end-to-end TLS certificate validation. This is not a rotating,
anonymizing or anti-bot proxy. Loopback/private destinations and non-HTTPS browser requests
are blocked. Service workers, downloads, WebSockets, popups and unknown cross-origin
main-tab navigation are disabled. Exact user-approved identity origins may receive
sign-in redirects and POSTs; they are not automatically trusted. Same-origin frames
are permitted. Up to eight additional HTTPS
resource origins can be explicitly trusted for scripts/images/styles, but that list does
not permit cross-origin frames or POST. The dashboard now shows blocked resources by origin
and type as well as network failures; an operator can select trusted script/style/font/image
origins for the **next** browser session. Nothing is automatically allowlisted. Failed
requests can also be caused by the site, not this proxy. Review ownership and data exposure
before approving a domain.

The dashboard shows document load state, main HTTP status, visible-text length and
frame count without exposing page text in those diagnostics. A `complete` load state
does not prove that a JavaScript app has finished rendering. Chromium waits briefly
for the load event, but you may still need to wait for the actual form. If sign-in
redirects to an unknown origin, the blocked origin is shown; verify ownership before
adding it under **Trusted identity origins** for a new session. This is not an access bypass.

The search, article-link and extraction planners are separate optional paid calls. All use the account's
configured provider key; navigation does not store the key or run until the user clicks the
planning button. Navigation is deliberately bounded: visible text/search/date/number fields
and standard selects (including open-shadow and same-origin-frame controls), plus
visible autocomplete options in a separately reviewed partial-form step,
at most five actions, and at most one final search-button click or Enter submission
on the approved origin.
No arbitrary model-authored selector, login, account action, checkout or payment is executed.
The page's labels are untrusted data; human approval is still required. A model plan can be
wrong even when schema-valid. The user inspects the result page before extraction.
Article-link candidates and page text are untrusted data. The model only proposes candidate
IDs, never arbitrary URLs. The operator approves a subset; sensitive-looking URL query keys
are excluded. Browser capture strips query strings from recorded source URLs. Link-following
is currently Chromium-only; static Public HTML mode still requires explicit page URLs.

### Manual verification compatibility (awaiting your validation)

With manual sign-in selected, **Optional manual website verification** accepts up to four
trusted HTTPS origins. This separate opt-in permits their scripts, embedded frames and POST
requests for the session. Those services can receive browser/website data; adding them is
a trust decision, not an automatic recommendation or a guarantee of access. No origin is
preapproved. Automatic credential filling cannot be combined with this setting.

1. Cancel the blocked session. Select manual sign-in.
2. Inspect the blocked origin and confirm it is a required service you trust before adding
   it to **Verification HTTPS origins** (not the resource-only list). For the reported
   Tripadvisor session the blocked origin was `https://ct.captcha-delivery.com`; this is
   an observed dependency, not confirmation that Tripadvisor will work or permits extraction.
3. Start a new session and complete any offered verification yourself in Chromium.
4. When a detected challenge clears, review the content, then capture explicitly.
5. If access is still denied, cancel. Do not repeatedly resubmit credentials. Use a
   permitted supported site or authorized access method instead.

The dashboard pauses capture for common challenge text and main-document 403/429 responses.
Detection is heuristic, not proof of authorization; it can miss challenges or misclassify
text. An HTTP-denied document remains blocked until a successful main-document navigation
(reload after verification if needed). No CAPTCHA solving, stealth/fingerprint changes,
cookie imports, auto-trusting domains or model calls during verification are implemented.
Only main-page text is extracted, not iframe content. SSO requiring popups or
other blocked capabilities still needs a dedicated adapter. robots.txt checks
remain in effect and may independently prevent capture after successful verification.

This is not universal login automation: passwordless login, SSO, passkeys and unusual forms
may fall back to manual handling or remain unsupported. No MFA/CAPTCHA bypass, payment,
booking, automatic pagination or unreviewed model-controlled browser clicking is implemented. Site
permissions and reuse restrictions still apply even when the page opens successfully.

Manual verification commands (assistant has not run these):

```powershell
uv sync --locked
uv run --locked playwright install chromium
uv run --locked pytest tests/test_browser_navigation.py tests/test_browser_login.py tests/test_custom_website.py tests/test_dashboard_ui_structure.py -v
.\scripts\Start-Demo.ps1
```

The new automated tests use mocks or loopback-only proxy rejection checks—not Chromium,
real website credentials or paid models. For joint browser validation, first open an approved
public HTTPS page with manual sign-in mode, capture, and inspect the preview. Then use a
dedicated test account on an authorized HTTPS login site. Check correct login, incorrect
password (no retry), manual fallback, cancel, timeout and a second account's inability to
control the first account's browser. Verify previews/exports contain no login credentials.

This workspace is separate from **Hotel demo**. Both paths now use the user's requested extraction criteria rather than a built-in USD 200 ceiling or 4/5 rating floor. The hotel path still requires dates and a maximum nightly price and minimum rating; Custom Website can leave criteria unspecified.

## What works in this checkpoint

- Rendered Chromium pages with optional bounded login, as described above; static HTML/plain-text pages remain an alternative.
- Human-reviewed same-origin article discovery in Chromium: up to five approved links,
  one capture per reachable page, and explicit partial approval when a page fails.
- Pasted page text for content you can access but the reader cannot (for example, after a manual login or JavaScript rendering). Provide the original URL for provenance. Pasted content is user-supplied, not independently fetched or verified.
- Optional natural-language instructions. Empty instructions mean infer the main content and useful fields, with no implicit search filters—not recursively download an entire website.
- Up to three explicitly supplied, same-origin public pages, or up to five approved Chromium
  article pages. At most 24,000 text characters per page, 16 fields and 50 candidate records;
  default 25 records. The extraction call has a 12,000-output-token ceiling and no automatic retry.
- Dynamic schemas for hotel listings, articles, blogs and other text records; explicit search filters, including inclusive price ranges. Missing values stay null. Unrepresentable requirements should trigger clarification.
- Verbatim evidence checks for every non-null value, deterministic filtering, and a readable human review screen.
- Both LangGraph and CrewAI Flow orchestration, using shared extraction and security services.
- Account-owned approved JSON snapshots and SQLite storage; Excel, CSV, JSON and JSON Lines downloads.
- Optional business rules evaluated **after** search filtering. Rules mark records without removing them. Optional NATS summary events contain run ID, record IDs and counts, not page bodies.

## How to use it

1. Restart the dashboard after updating and refresh with Ctrl+F5. Sign in to your local account.
2. Configure your key/model in **API connection**. The model remains configurable; this feature does not install or select a different model.
3. Open **Custom Website** and choose LangGraph or CrewAI.
4. Choose Public HTML pages and provide 1–3 URLs, or choose Paste authorized page text and provide one source URL plus copied text. Do not paste passwords, keys, cookies, confidential material or URLs containing access tokens.
5. Add instructions if desired. A price range can be `price at least 150 and at most 250 USD`; no hotel policy ceiling is applied here. Include units, tax/price basis and rating scale where relevant.
6. Optionally configure a business rule using a field name expected in the schema. Turn on event publication only if desired and NATS is running. With no rule, all saved records qualify; zero qualifying records produce no event.
7. Confirm access/data-sharing authorization and paid-model consent, then select **Inspect & preview extraction**. This step fetches the listed pages and sends their bounded text plus your instructions to OpenAI. It incurs model usage even if you subsequently reject the preview.
8. Review the interpretation, exact filters, units, warnings, available rows and **View quotes**. Check omitted requirements; matching quotes are not proof of semantic correctness.
9. Approve only when correct. **Approve & save snapshot** saves exactly the preview, evaluates optional rules and publishes an opted-in summary event. It does not re-fetch pages or call the model again. Proposals expire after one hour and allow one execution attempt.
10. Download the saved results. History can reopen custom proposals and runs without repeating work.

If clarification is shown, edit the input and explicitly submit again. This creates another paid call; there is no automatic retry or conversational memory. Your form remains available while you review the response.

## Important limits — not universal scraping

The static public reader does not execute JavaScript or sign in; use Chromium mode for rendered pages and supported login. Cross-origin authenticated adapters, automated pagination, general crawling, PDFs and bot-protection bypass are not supported. Pasted text remains an option for authorized content unavailable to these readers.

This path rejects private/loopback network destinations and custom ports. It resolves and validates all DNS addresses, connects to the verified address directly, validates TLS, ignores environment proxies and does not send credentials/cookies. Redirected page URLs must be submitted explicitly. robots.txt is checked for public fetching; access authorization and website terms remain your responsibility. Do not weaken these protections to make a target work.

The HTML reader strips scripts and forms, but it is not a browser and cannot perfectly determine visual visibility. Text may contain navigation/hidden content or unusual encoding. Source truncation is disclosed. No model can guarantee exhaustive extraction or correct interpretation; dates, availability, currencies, rating scales and total-versus-nightly prices need particular review. If the model cannot establish a requested constraint, the safe result is clarification, not invented data.

The snapshot's `captured_at` is source-inspection time, not approval time. IDs are local to a run. Exact duplicate content within one preview is deduplicated; there is no cross-run deduplication. Custom downloads currently export all saved records, including evidence; the Hotel demo retains its existing all/filtered download selector.

## Storage and events

Under each local account's data directory:

- `website-plans/<plan-id>.json`: private proposal and extracted preview; no raw API key.
- `website-plans/<plan-id>.attempt`: one-attempt marker. A restart/failure does not authorize replay.
- `website-records.sqlite3`: approved run snapshots.
- `exports/<run-id>.json`: compatible with the shared download service.
- `website-events/<run-id>.json`: optional pending/acknowledged summary event evidence.

Events use a separate account-specific `_WEB` JetStream stream and `website.records.matched.v1` schema. Publication counts mean **broker acknowledgement only**; a dedicated custom-event consumer/receipt verification is not implemented. The hotel-event consumer is not compatible with this schema. If publication fails, records remain downloadable and the job reports failure; check saved event evidence and the broker before recovery. No automatic replay or exactly-once claim.

All source URLs, extracted values, quotes and prompts in saved proposals are data that other users of the OS/filesystem may access. This remains a local demo, not a hardened multi-tenant enterprise deployment.

## Verification — you run this

No tests, browser sessions, external extraction runs or paid API calls were run by the assistant during implementation. Static lint/syntax checks are not runtime acceptance.

Stop the launcher first, then:

```powershell
uv sync --locked
uv run --locked pytest tests/test_custom_website.py tests/test_dashboard.py tests/test_dashboard_accounts.py tests/test_dashboard_ui_structure.py tests/test_exports.py -v
.\scripts\Start-Demo.ps1
```

The focused tests mock content/model access and do not make paid requests. For the first manual paid preview, choose **Paste authorized page text**, URL `https://example.org/hotels`, and this synthetic fixture:

```text
Boston hotel North: nightly price including taxes 150 USD; guest rating 4.2 out of 5.
Boston hotel South: nightly price including taxes 250 USD; guest rating 4.8 out of 5.
Boston hotel East: nightly price including taxes 200 USD; guest rating 3.9 out of 5.
Boston hotel West: nightly price including taxes 300 USD; guest rating 4.9 out of 5.
```

Instructions: `Extract Boston hotels with nightly prices including taxes from 150 to 250 USD inclusive and guest ratings at least 4.2 out of 5. Include name, city, price, currency and rating.`

Expected review: minimum **150**, maximum **250**, minimum rating **4.2**, North and South. Check that the model does not invent availability dates. Approve, download all formats, then repeat with CrewAI. With blank instructions all four supplied hotels should be eligible and no price/rating filters should appear. These are expectations to verify, not claimed passing results.

Next, try one approved public article/listing URL with event publication off. Check empty results, evidence mismatches, same-origin URL limits, source truncation and clear login/JavaScript fallback messages. Finally opt into one rule and a summary event, verify broker acknowledgement, and verify a second dashboard account cannot open the first account's jobs or proposals.

Structured output is based on the [official OpenAI structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs); a valid schema does not establish factual accuracy.
