# Cleanup A: housekeeping and current documentation

Implemented 11 October 2026; user-run verification pending. No tests, live browsers
or paid model calls were run during this checkpoint.

## What changed

- Removed an unreferenced destination regex and redundant dev dependency declaration.
- Reused `source_fields.normalized` for extraction and enrichment. NFC/whitespace
  normalization remains case-sensitive; browser task/form normalization is unchanged.
- Reused `browser_runtime.controls` for task observation flattening.
- Replaced historical CLI status/checkpoint scores with an implementation inventory
  that does not claim service health or discover test results.
- Corrected import ordering and current documentation while retaining historical evidence.
- Designated the packaged dashboard DOM collector as canonical. The extension keeps
  its own generated deployment copy, checked by `scripts/sync_capture.py` and a regression.

No navigation paths, prompts, model budgets, networking modes, validation rules,
credential handling, storage formats, event schemas or framework implementations
were removed or changed. Policy default reconciliation is a separate behavioral
decision: the configured YAML is unlimited, while `Rules()` retains old demo defaults.

## Run these checks yourself

From the repository root in PowerShell:

```powershell
uv lock --check
uv run --locked ruff check src tests scripts/sync_capture.py
uv run --locked python scripts/sync_capture.py
uv run --locked agentic-demo status
uv run --locked pytest tests/test_cleanup_contracts.py tests/test_foundation.py tests/test_source_quality.py tests/test_source_inventory.py tests/test_detail_enrichment.py tests/test_browser_task.py tests/test_dynamic_browser_agent.py -v
```

The collector check is read-only unless `--write` is supplied. The status command
must omit old checkpoint/language scores and report `health_checks_performed: false`.
The listed tests use local/mocked fixtures; no `--run-model`, `--run-browser` or
`--run-nats` flags are needed. Inspect any skips in the report rather than treating
them as passed checks. You can then run the full ordinary suite:

```powershell
uv run --locked pytest
git diff --check
git diff --stat
```

Live model/browser/site acceptance is separate and still yours to initiate.

## Editing the collector later

1. Edit `src/agentic_web_demo/dashboard/static/capture_dom.js`.
2. Run `uv run --locked python scripts/sync_capture.py --write`.
3. Review both collector files and reload the unpacked browser extension.
4. Run capture regressions before merging. Do not delete either deployment copy.

## Remaining work

Return to the browser-agent decision failure with safe error-category diagnostics.
Then undertake shared browser primitives, session/frontend separation and model/
extraction boundaries in separate checkpoints. Cleanup A does not resolve the
Booking.com form failures or establish universal website compatibility.
