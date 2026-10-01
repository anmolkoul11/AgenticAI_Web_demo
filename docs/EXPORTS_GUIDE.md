# Downloading results

Open a completed run in the dashboard (or from History), then use **Explore your results**:

1. Choose **Excel**, **CSV**, **JSON**, or **JSON Lines**.
2. Choose **All saved records** (default), or **Currently filtered records** to apply the table's search and rule-outcome filters.
3. Select **Download results**. Check the browser's Downloads folder or save prompt.

Downloads read your account's saved snapshot. They do not rerun scraping, change rules, publish events, or call a model. An older run retains its original data and rule decisions. Other users cannot download your runs.

## Formats

| Format | Use | Details |
| --- | --- | --- |
| Excel (.xlsx) | Excel, LibreOffice, business review | Records sheet with frozen headers and filters; Export info sheet with run ID, export time and selected scope; Rule decisions sheet when decisions exist for exported records. Hotel prices/ratings are numeric, stay dates are date cells, timestamp cells are UTC. |
| CSV (.csv) | Spreadsheet imports, databases and processing tools | UTF-8 with BOM for Excel; comma-separated with quoted commas/newlines. All discovered fields, including source URL and extraction time, are included. |
| JSON (.json) | Exact source types and snapshot context | Saved snapshot with the selected records; retains other snapshot metadata. |
| JSON Lines (.jsonl) | Line-oriented processing | One JSON record per line, without snapshot metadata. An empty result produces an empty file. |

CSV and Excel represent nested objects/arrays as JSON text in cells. Missing/null tabular values are blank; JSON formats preserve nulls. CSV/JSON do not include a separate rule-decision sheet; use Excel for that evidence.

Excel writes text explicitly as text, with automatic formulas and hyperlinks disabled. CSV prefixes formula-like text with an apostrophe; this changes the CSV representation intentionally. CSV applications may still auto-convert IDs or dates—import identifier columns as Text, or use Excel/JSON to retain leading zeros. Re-saving CSV in another application can change these protections.

## Bounds and limitations

- Up to 10,000 records, 128 columns, and 200,000 record cells per export; the existing saved-snapshot size limit also applies.
- Excel cells cannot contain more than 32,767 characters. The download fails visibly instead of silently truncating; use CSV or JSON for long articles.
- Large numbers are kept as text where practical; JSON is the preferred exact-source format. Generic string fields are never guessed to be dates or numbers.
- Zero matching records is valid. Tabular exports retain known headers.
- The export layer accepts varying record fields for future adapters. **This checkpoint does not implement Custom Website extraction or change the current hotel-only planning/UI contract.**

## Developer verification (run manually)

Stop project Python processes before installing the new dependency:

```powershell
uv sync --locked
uv run --locked pytest tests/test_exports.py tests/test_dashboard.py tests/test_dashboard_accounts.py tests/test_dashboard_ui_structure.py -v
```

These focused tests use local fixtures, not paid model calls. Then restart the launcher, refresh the browser, and open a saved successful run:

1. Download all four formats; open Excel/CSV in your spreadsheet program and JSON/JSONL in VS Code.
2. Compare the all-records count against the saved run; inspect source fields and Excel's rule decisions.
3. Select Matches only, choose Currently filtered records, and verify the downloaded count against the table.
4. Try a search with no matches. Verify headers/empty results, not an error.
5. Switch to a second account. The first account's run must not appear or be downloadable.

Tests and interactive verification are left to you; they were not run during implementation.
