# Multiple displayed amounts — 2026-10-16

Implemented, awaiting manual verification. No tests, app imports/startup, browser
sessions or model/API calls were run for this checkpoint.

## Changes

- Collector v6 preserves each amount separately, along with an exact local source
  quote, its amount-specific label, and actual rendered crossed-out styling.
  It does not infer a price's role from its magnitude. The same capture contract
  works for product and other listing records, not just hotels.
- Ordinary form values, credentials and CSS-hidden content remain excluded.
  Bounded metadata is charged against the existing 24,000-character capture limit;
  it does not add another model call or increase that ceiling.
- Extractor v15 asks for distinct useful monetary roles rather than flattening all
  amounts into one price. A canonical primary `price` slot can coexist with other
  dynamically inferred price columns. Literal context quotes retain block provenance.
- Pricing v2 preserves structured observations for every captured monetary amount.
  A uniquely supported current nightly quote takes priority over an average derived
  from a full-stay total. Crossed-out prices are never eligible budget comparisons.
  Unclassified additional amounts stay visible; competing current nightly amounts
  still require attention. The original model fields are not rewritten.
- Cards and full preview show the observed amounts and their evidence. CSV/Excel
  receive a readable `pricing_observed_amounts` column; JSON also retains structured
  observations. Source prices and computed comparison values remain distinct.
- Workflow guidance lists only the actual per-record blockers. It no longer claims
  that currency or returned stay scope is missing when those facts are verified.
- Save approval rechecks the same captured evidence and comparison. Existing v1
  pending pricing proposals must be recreated; historical saved exports are not
  rewritten.

The existing typed SDK output contract remains in place. Instruction clarity was
informed by [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs),
which distinguishes valid structure from possible content mistakes. Deterministic
source validation remains necessary; no model, credential or endpoint was changed.

## Manual verification

1. Restart the dashboard, hard-refresh, and start a new run. Reload the page-capture
   extension if used. UI/backend version: `2026-10-16.1`; extractor:
   `website-extractor-v15`; collector: `source-inventory-v6`; pricing:
   `stay-pricing-v2`. Browser-agent decisions remain `browser-agent-v20.2`.
2. Repeat the New York request with full dates, four adults and two rooms. When
   West Side YMCA shows the same source values, verify separate observations for
   `$259` labelled per night, `$559` with the two-night context, and crossed-out
   `$665`. Exact prices may change; compare the retained evidence with the still-open
   source browser at capture time.
3. The supported nightly amount should drive the nightly budget check. Do not
   reconcile `259 × 2` with `559` by inventing a fee, tax or discount explanation.
   Tax/fee coverage remains unknown unless the source explicitly establishes it.
4. Preview the complete record, save it after review, and download CSV/Excel/JSON.
   All supported amounts and original-price status should survive the handoff.
5. Check competing current nightly quotes, an original-only quote, missing labels,
   currencyless prices with an explicit selected currency, and separate neighboring
   records. Unsupported comparisons must stay unverified, with exact reasons.
6. Try product listings with current/original prices. Capture and model fields
   remain dynamic; hotel stay conversion must not run on non-hotel records.

Suggested commands for the user (not executed here):

```powershell
uv run --locked pytest tests/test_pricing_observations.py tests/test_multi_price_contract.py tests/test_numeric_contract_integrity.py tests/test_pricing_workflow.py -v
uv run --locked pytest tests/test_pricing_capture.py tests/test_pricing_ui.py tests/test_capture_handoff.py --run-browser -v
```

Captures remain bounded and can be incomplete. The change does not establish
universal website compatibility, taxes, availability or a valid checkout quote.
