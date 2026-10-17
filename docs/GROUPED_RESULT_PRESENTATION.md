# Grouped, source-aware results

Checkpoint: UI/backend `2026-10-16.2`. Manual verification pending.

Cards and the full preview organize source fields into readable sections rather
than displaying the first few arbitrary fields. Sections adapt to returned field
names/descriptions: overview, pricing, location, options, features, terms, ratings,
dates, links and a catch-all Details section. This is a shared presentation layer,
not a Booking/news template or a copy of a source website's styling.
Declared source units and field explanations remain available; missing units are
not inferred from the layout.

Current nightly pricing stays prominent. Other displayed amounts, original prices
and evidence remain available under Price details. Equivalent observations merge
only for display when amount, currency, basis and role agree. Different price
roles remain separate; the selected comparison and raw saved observations do not
change. Missing fields move into an expandable disclosure, not an invented value.

## Captured details versus extracted fields

Some literal source details may be captured but omitted by the model. The preview
now lists bounded additional wording from the uniquely identified record's own
container, with source URL/block references. Related wording may also accompany
a missing field. It is **not** a verified answer to that field: qualifiers and
negations remain literal, and canonical null values remain null. Neighboring
records, ambiguous groups and page-level text do not supply missing facts.

At most ten short snippets per record are shown; the omitted count and capture
coverage explain limits. This cannot recover information absent from the capture,
guarantee whole-site completeness or infer hotel availability/tax treatment.

New previews include this metadata before approval. Saved historical runs can use
a read-only presentation projection if their original proposal/source blocks are
still retained. Original exports, proposal revisions and saved values are not
rewritten. Downloads continue using the raw saved snapshot. JSON from new saves
retains additional wording as separate `source_coverage` metadata, not source
columns, rule inputs or approved values for blank cells.

No extra model calls, browser actions, paid budgets or pricing-rule changes.

## Manual checks

1. Restart the dashboard and hard-refresh; frontend/backend should both show
   `2026-10-16.2`.
2. Open the previous Booking run. Check readable sections, current nightly quote,
   total/original prices and collapsed evidence. Repeated equivalent totals should
   display once, but same-number nightly/total/original prices must stay distinct.
3. Inspect Eurostars, Romer, La Quinta or Hyatt Place. If supported source wording
   is present but a feature was null, it should appear as additional captured
   wording or beside the missing field—not silently become a confirmed amenity.
4. Open the BBC run: headline/context/links should remain readable without empty
   hotel sections. Check a product/company extraction too; unfamiliar populated
   fields must remain visible in Details.
5. Open full preview, change records, return to cards and toggle the table. Confirm
   no automatic scrolling, lost back action or hidden populated fields. Check a
   narrow viewport and keyboard navigation.
6. Download a historical JSON before/after viewing. Saved facts and observations
   must be unchanged. A new save should retain the approved grouped output and
   separate source-coverage metadata.

Regression fixtures were authored but **not executed**, as requested. No tests,
validators, application imports/startup, live browsers or API calls ran.
