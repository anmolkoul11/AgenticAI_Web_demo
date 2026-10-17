# Returned-stay and price accuracy checkpoint

Included in [Dynamic fields and needs-driven collection](DYNAMIC_FIELDS_GUIDE.md),
which supplies the latest versions and complete manual acceptance scenarios.

Implemented on 2026-10-14. Runtime verification is pending with the user. No tests,
static validation commands, browsers, application startup/imports or model calls
were run for this checkpoint. No model, endpoint, account or paid-call limit changed.

## Why the earlier result was misleading

The inspected user1 Booking run completed the search form and saved 12 records.
Its captured page was a city catalogue: multiple price blocks said **Price from**
and **1 night, 2 adults**, whereas the request was October 28-30, 2026, four adults,
two rooms. These are not equivalent stay quotes. Some price blocks also had no
record-level association, and the approximate budget was not recognized.

Form read-back proves what was entered, not what the results used. Stored display
URLs omit search parameters; their absence alone does not prove that navigation
lost those parameters. New diagnostics project only named date/occupancy values,
not arbitrary URL queries or credentials.

## Price meanings

| Source/request | Presentation and comparison |
| --- | --- |
| Unqualified `nightly` budget | Combined nightly cost for all requested rooms; never silently per room. |
| Verified USD 600 full-stay total for two nights, all requested rooms | Keep displayed total 600; calculate **average per night: USD 300, all requested rooms**. Divide by nights, not rooms. |
| Explicit `per room, per night` source | Keep that label. Do not multiply by room count without evidence that this rate applies to every room. An explicitly per-room request may compare on that basis. |
| `Price from`, default occupancy, missing scope/basis/currency or ambiguous record ownership | Source-only preview; not a verified requested-stay or budget match. |
| `around`, `try`, `prefer` a price range | Preference. Verified outside-target records may remain as labelled alternatives, not budget matches. |
| `keep/only/between` an explicit hard range | Hard selection, inclusive unless explicitly exclusive. Compare on the verified requested price basis, not a raw full-stay total. |

Taxes and fees are separately labelled included, excluded or unknown from captured
wording: `taxes included` alone does not establish included fees. No
tax estimate, currency conversion or assumption that a bare `$` means USD is made.
If the request requires taxes included, excluded/unknown amounts are not inclusive
budget matches. A visibly selected currency setting is retained as separate evidence.

## What changed

- Returned destination, full dates and named occupancy are checked independently
  from fresh result-page controls and normalized URL facts. Old calendar selections
  and pre-submit field bindings cannot supply missing result values.
- A different, clearly identified catalogue with its own native form may receive
  one fresh, verified Search. An uncertain previous dispatch is never repeated.
- Pricing requires a uniquely identity-bound record group, a matching numeric
  quote, source currency/basis and independent stay scope. Unowned prices are not
  assigned to a hotel merely because they occur elsewhere on the page.
- Raw amounts and quotes remain intact. Application-computed fields are marked
  computed, not source quotes, and saved with their basis/calculation metadata.
- Approval re-assesses stored source evidence and returned context. Old pending
  previews cannot bypass the new pricing checks; already-saved exports are unchanged.
- Cards and full previews show displayed price, combined/average nightly amount,
  taxes, budget status and stay discrepancies. Unknown/mismatched prices have no
  Save/Download action as matched records. Generic news/product extraction is unchanged.

OpenAI Docs informed the source-grounded extraction instructions; valid structured
output still needs application-level correctness checks. See
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Restart

1. Cancel existing sessions and stop/restart the usual launcher.
2. Hard-refresh the dashboard (Ctrl+Shift+R). Frontend/backend: `2026-10-14.3`.
3. A new browser-agent run reports `browser-agent-v20`; extraction reports
   `website-extractor-v13`; capture reports `source-inventory-v4`.
4. If using the capture extension, reload it in Chrome/Edge's extensions page and
   refresh the source tab. Older capture payloads remain readable, but may lack
   the evidence needed to approve stay-specific prices.

## Manual acceptance scenarios

Start a new Booking.com run with:

> Find hotels in New York with check-in October 28, 2026 and check-out October 30,
> 2026 for 4 adults and 2 rooms. Try to find prices around 250-350 USD nightly.
> Include hotel name, listing URL, displayed price, currency, price basis, taxes
> and fees wording, and guest rating.

Check the website's post-search dates/occupancy **and each price card**, then compare
the preview with that same rendered page:

- Correct two-night total: raw total unchanged; average labelled; no division by rooms.
- Wrong `1 night, 2 adults`/starting price: clearly unverified, not saved as a match.
- Per-room source: clearly per-room; combined amount stays unavailable without proof.
- Approximate range: within-target vs outside-target alternatives are distinguished.
- Repeat with `Keep only hotels priced between 250 and 350 USD nightly, inclusive`:
  verified out-of-range prices are excluded; unknown prices are not called out-of-range.
- Taxes unknown/excluded: labelled accurately. Requiring inclusion must not pass them.
- Missing source association/currency: readable raw price, no invented hotel binding/USD.
- News/product request: no new hotel dates/occupancy or price calculations imposed.
- Approved exports: raw price, computed nightly value, currency, basis, taxes, fees and budget status
  agree with the preview; source evidence remains available.

These checks do not guarantee every website supports automation, all listings were
captured, or a displayed offer remains available. A read-only price warning is an
accuracy stop, not successful stay-price retrieval. If the site still returns a
catalogue, share the new returned-scope evidence and price-card text for follow-up.

Optional commands for **you** to run:

```powershell
uv run --locked pytest tests/test_result_stay_scope.py tests/test_pricing_basis.py tests/test_pricing_workflow.py -v -ra
uv run --locked pytest tests/test_pricing_capture.py tests/test_pricing_ui.py tests/test_record_capture.py tests/test_capture_handoff.py tests/test_search_handoff.py tests/test_navigation_verification.py tests/test_dashboard_ui_structure.py --run-browser -v -ra
```

Some older fixtures assumed plain text/column units alone verified stay pricing.
If they fail, inspect the fixture's source ownership and stay evidence; do not
weaken the new checks or manufacture quotes to preserve a permissive expectation.
