# Capture and numeric evidence integrity — 2026-10-15

Implementation is pending manual verification. No tests, application/browser
startup or model calls were run for this checkpoint.

## What changed

- The bounded DOM collector retains short CSS-rendered numeric/value text inside
  records even when it is marked `aria-hidden`. Actual hidden content, form values
  and credential controls remain excluded. Numeric span clusters and record-local
  value priority reduce loss of displayed amounts within the existing budget.
- Numeric request dependencies correct an existing text-typed amount/count field
  instead of adding a competing empty alias. Qualification fields such as price
  basis, currency, range and IDs do not become amount candidates. Explicit numeric
  comparisons work for other domains too; there is no fixed hotel output schema.
- Number formatting differences such as `3140` versus the literal quote
  `Price $3,140` no longer erase a supported amount. Whole-token and record-group
  checks still apply. Original evidence and numeric-format repairs are retained.
- Pricing retains known currency and returned-stay facts independently of amount
  verification. Raw same-record monetary candidates remain diagnostic evidence,
  not a guessed replacement price or a confirmed nightly budget match.
- Fresh top-level result-count headings can establish the returned destination.
  Conflicting headings/controls fail verification; card titles, form echoes,
  arbitrary prose, old form values and iframe headings cannot supply it.

Versions: UI/backend `2026-10-15.3`, browser agent `browser-agent-v20.2`,
extractor `website-extractor-v14`, collector `source-inventory-v5`.
Existing captures remain readable. Model/account settings, call limits, networking
modes and capture-size limits have not been increased; no extra model call is added.

## Manual verification

1. Restart the dashboard and hard-refresh it. Reload the page-capture extension
   if installed. Start a new run; old jobs/captures are not silently rewritten.
2. Repeat the Booking.com request with explicit full dates, four adults and two
   rooms. For each returned hotel, compare the captured price and quote with the
   still-open source browser. In particular inspect West Side YMCA when present.
   A visible amount must appear in its own record group, not a neighboring card.
3. Inspect prices with commas and cents. The numeric value may be canonicalized,
   but the evidence must preserve the source wording. Currency and returned-city
   checks should retain their evidence even when a particular amount is missing.
4. Compare nightly versus full-stay totals, room scope, taxes and fees. Do not
   accept a budget match solely because an amount was captured. Ambiguous labels
   and conflicting stay details must remain unverified, with the raw price visible.
5. Try products or another listing site with numeric prices/counts and unrelated
   string IDs. Fields should follow the request and available source; formatting
   equivalence must not change identifiers, choose between multiple prices or
   borrow another record's quote.

Suggested focused commands for the user to run (not executed here):

```powershell
uv run --locked pytest tests/test_numeric_contract_integrity.py tests/test_pricing_basis.py tests/test_result_stay_scope.py -v
uv run --locked pytest tests/test_record_capture.py tests/test_dynamic_capture.py tests/test_pricing_capture.py tests/test_browser_agent.py --run-browser -v
```

If a visible value is still missing, compare the exact saved group and capture
coverage against the live card. A truncated capture is not evidence that the live
site lacks a value. This checkpoint improves collection/validation, not universal
site support or proof of availability.
