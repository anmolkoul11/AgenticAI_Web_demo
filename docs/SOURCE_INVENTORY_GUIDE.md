# Checkpoint 1: shared source inventory and capture coverage

Implementation is ready for **user-run validation**. No tests, public-site browser
runs, sign-ins or model calls were performed by the assistant for this checkpoint.

## What changed

- Chromium capture, link discovery and the Chrome/Edge capture extension use the
  same DOM collector. Capture and discovery scan both the main content and the
  remaining loaded page, including accessible open shadow roots.
- Repeated links to the same URL are merged before selecting a title. A full
  linked heading takes priority over a short editorial label such as
  “LOST IN TRANSLATION”. Labels are retained separately; they are source text,
  not an application failure message.
- Record groups distinguish neighbouring linked records. Hotel/property cards
  with one identifiable primary heading link keep their price/rating association
  even when a separate review link is present. Ambiguous optional metadata is
  blanked with a field issue; identity and filter/rule fields still reject the
  record if they cannot be associated with the correct source record.
- Browser capture and link discovery perform bounded content-stability sampling
  and up to the chosen number of loading scrolls (default 3, range 0–8), then
  restore the operator's scroll position. No pagination or clicks are added.
- Captured-page coverage is visible in the review panel: captured/omitted text,
  link counts, record groups, collection limits, loading steps, observed page end
  and excluded iframe count. New extension captures include these metrics;
  older version-1 captures remain accepted without claiming coverage metrics.

Both restricted and normal networking remain available and unchanged. This
checkpoint does not add model calls or remove existing execution review steps.

## Run the checks yourself

From the project directory:

```powershell
uv run --locked pytest tests/test_source_inventory.py tests/test_capture_handoff.py tests/test_browser_links.py tests/test_topic_evidence.py tests/test_custom_website.py tests/test_dashboard_ui_structure.py -v
```

The four real DOM cases in `test_source_inventory.py` skip without `--run-browser`.
To run those cases as well:

```powershell
uv run --locked pytest tests/test_source_inventory.py --run-browser -v
```

These new browser cases route all requests to local fixture HTML. They do not
contact public websites or a model, but require installed Playwright Chromium.
For the wider offline regression suite:

```powershell
uv run --locked pytest
```

Do not add `--run-model` unless you intend to run paid model evaluations. NATS is
not needed for these focused checks.

## Manual dashboard checks

1. Stop and restart the dashboard with your existing launcher. Hard-refresh the
   dashboard tab. Reload the unpacked **page-capture extension** in Chrome/Edge
   (`chrome://extensions` / `edge://extensions`); its version is now 0.2.0.
2. Start a Custom Website browser session on an authorized news/blog index.
   Choose either existing network mode and set Loading scroll steps to 3.
   Inspect the rendered page before continuing.
3. Use **Find relevant links** with your topic request. Check that proposals show
   the actual linked headlines rather than a shared editorial kicker. Only up to
   five reviewed links are opened, as before; this checkpoint does not promise
   an exhaustive topic search or detail enrichment for unselected records.
4. On a separate session, use **Extract current page only**. Review the captured
   page's coverage and any blanked-field issues. Verify headlines and available
   URLs against that exact source page. Discovery and capture have a common
   collector, but separate actions can see a changed live page and different
   limits; do not expect identical output schemas or records from the model.
5. Repeat with an authorized hotel/product result page that has distinct cards.
   Ensure each record's name, price and rating belong to the same card; a review
   link must not move neighbouring card metadata into that record.
6. Repeat once with 0 loading scrolls. Confirm the coverage honestly reports the
   smaller bounded snapshot rather than claiming all lazy-loaded results.
7. Capture the same type of page using the extension. Preview its coverage in
   the dashboard, approve only verified records, then download CSV/Excel/JSON.

Public-site extraction actions incur the existing paid calls after consent.
Loading sampling and scrolling themselves do not call a model. Share failures,
coverage and redacted field issues; never send API keys, passwords or cookies.

## Remaining boundaries

This is a **loaded-DOM inventory**, not the entire website. Text capture remains
limited to 600 blocks, 24,000 total text/link characters and 6,000 text characters
per block. Discovery returns at most 100 candidate links from its bounded scan.
Omissions and limits are disclosed instead of silently claimed as complete.

Cross-origin frames, closed shadow roots, virtualized rows removed during scroll,
infinite feeds, nested scroll containers, pagination and pages that deny access
can remain incomplete. Stability sampling is a heuristic, not proof that the
website application has finished rendering. The extension is a manual snapshot;
it does not perform browser-side preparation. Link discovery can additionally
inspect up to eight same-origin frames; text capture does not include iframe
bodies. Source/export URLs retain the existing query/fragment stripping, so
query-only record identity remains a limitation.

Checkpoint 2 will preserve index records and enrich approved detail pages.
Checkpoint 3 will improve multi-step search controls and verify action outcomes.
Checkpoint 4 will cover diagnostics, acceptance evidence and clean-checkout
handoff. No universal-site or production-readiness claim is made here.
