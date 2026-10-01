# Query-first external extraction

Implemented for user verification; no assistant-run tests or paid model calls.

## Normal workflow

1. Start the launcher, sign in, configure your account API key/model.
2. In Custom Website provide a URL, a browser-extension capture, or authorized pasted text.
3. In **What should we extract or flag?**, describe the information, selection criteria and
   any flags you want. Leave blank for the main available content with no inferred rules.
4. Confirm access authorization and paid-API consent, then **Extract & show results**.
5. Review the table, interpreted filters, rules, source quotes and coverage warnings.
6. Select review approval (and partial-result approval if needed), **Save reviewed results**,
   and download Excel, CSV, JSON or JSONL. Saving/downloading does not make another model call.

The optional manual conditions are advanced event-eligibility checks; normal users do not
need to fill them in. Events remain opt-in and cannot be enabled by the model or page text.

## Examples

- Articles: "Get the article headlines, links, authors and publication dates where available."
- Topics: "Get the articles or headlines related to new technology or research."
- Rule flag: "Get the article headlines and links. Flag headlines containing climate as climate_news."
- Listings: "Get hotels priced between 150 and 250 USD. Flag hotels below 180 USD as preferred."
- No query: extract the main available records/fields, without model-invented filters or rules.

Only supplied/captured content is available. Listing-page headlines are not full articles.
The tool does not automatically follow article links or paginate. No default hotel price
policy applies to Custom Website. The separate synthetic Hotel demo remains unchanged.

## What the implementation does

- A single structured model response identifies source fields, records, selection filters
  and optional named rule flags. Structured captures are sent as blocks without repeating
  the same content as flat text. Prompt version: `website-extractor-v5`.
- Topic requests produce a reviewed semantic selection. Each included record has a
  `topic_relevance` label, explanation and source quote. The label is an AI judgment,
  not proof of article meaning. Unrelated rows are excluded; uncertain rows are held
  for review. A topic request without a topic plan does not silently return all records.
- Evidence may contain one pair of display quotation marks. The inner quote is accepted
  only if it is literally present in the captured source and supports the value.
  Paraphrases and absent quotes remain rejected. This addresses the reported homepage
  failure without weakening the source check.
- Reserved field names (e.g. source_url) are deterministically renamed to content_source_url
  or an available suffixed variant. The mapping applies to cells, filters and rules and is
  disclosed. Harmless identical duplicate fields/cells are merged; reordered cells are
  aligned by name. Omitted cells become explicit nulls with empty evidence, never guessed
  values. Rows with undeclared or conflicting cells are quarantined with field-level reasons;
  conflicting column definitions still stop the proposal rather than choosing one meaning.
- Filters select rows. Rules annotate surviving rows with computed rule_<name> columns:
  matched, not_matched, or unknown. Missing source values are not treated as known negatives.
- Supported rules compare text with eq/contains or numbers with gt/gte/lt/lte, combining
  conditions with all/any. Rules require a supporting quote from the user query. No query
  causes model-proposed filters/rules to be discarded with a warning; requested manual
  conditions, if any, remain explicit user input.
- Arbitrary calculations, nested logic, inferred semantic categories, date arithmetic,
  sorting, scripts and external actions are not an executable rule language. The model is
  instructed to request clarification for unsupported requirements, not silently omit them.
  Interpretation can still be wrong: review before approval.
- Source evidence validation remains in place. Good rows can proceed with partial-result
  approval; quarantined rows do not enter results, rule inputs or published record IDs.
- Rule definitions and computed outcomes are preserved in saved snapshots and downloads.
  Computed flag values are application outputs, not source quotes.
- If event delivery is enabled, any matched query flag qualifies a record AND all additional
  manual conditions must pass. With no rules, all accepted records qualify. Unknown flags
  alone never qualify. This policy is shown in the UI; events require separate approval.

This is the shared pipeline for LangGraph and CrewAI, not two different extraction engines.
The browser extension is unchanged; only restart the dashboard and Ctrl+F5 for this update.

## User-run verification

```powershell
uv run --locked pytest tests/test_query_workflow.py tests/test_custom_website.py tests/test_capture_handoff.py tests/test_dashboard_ui_structure.py -v
```

For a controlled manual check, use Paste authorized page text, source URL
`https://example.org/hotels`, and:

```text
Boston hotel North costs 150 USD per night and has a guest rating of 4.2 out of 5.
Boston hotel South costs 250 USD per night and has a guest rating of 4.8 out of 5.
Boston hotel East costs 300 USD per night and has a guest rating of 4.5 out of 5.
```

Query: "Get hotels priced between 150 and 250 USD per night. Include the name and price.
Flag hotels below 180 USD as preferred."

Expected: North and South remain; North's rule_preferred is matched, South's is not_matched.
With an empty query all three should be eligible and no inferred flags/filters should appear.
Repeat with both frameworks, save/download, then retry an authorized article capture.
These are acceptance expectations, not claimed passing test results.

The [official structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
informs the typed response contract; schema conformance is not proof of source accuracy.
