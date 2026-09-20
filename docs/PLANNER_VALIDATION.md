# Planner validation history

Current instructions: [OPENAI_SETUP.md](OPENAI_SETUP.md). Prompt v3 supersedes
v2 after three strict-comparison cases regressed to unsupported. The original
44 live expectations remain unchanged; v3 testing is pending. The following
describes the earlier v2 change and its motivation.

The reported OpenAI baseline was 36 passed / 2 failed on the original 38 live
cases. The failures were external-site requests accepted as local plans and a
ten-point rating reported as failed rather than unsupported. This is historical
evidence, not a result for the changes below.

Changes:

- Shared `hotel-planner-v2` instructions explicitly bind interpretation to
  `demo-hotels`, reject external sources and prohibit rating-scale conversion.
- Unsupported decisions discard unused search fields before executable-plan
  validation. Ready/needs-input decisions retain existing validation. This fixes
  a demonstrated code path, not a confirmed diagnosis of the historical model
  response, which was not captured in full.
- Eleven offline regression cases cover both framework runners, no-tool behavior,
  strict control fields and unchanged input dictionaries.
- Original live expectations remain unchanged; six added cases cover external
  sources, alternate scales and supported/negated-source controls (44 total).
- Live failure diagnostics include sanitized model metadata, error code and trace.

No tests or paid model calls were run while preparing this change. In the project
terminal, first run offline tests (no portal, Docker or API key required):

```powershell
uv run --locked pytest tests/test_planning_rejections.py -q
uv run --locked pytest -q
```

In the terminal already configured with your OpenAI API key, use the same model
as the baseline. The following commands make billable API requests, not browser
or broker calls. Start with the two original failures:

```powershell
$env:AGENTIC_MODEL_PROVIDER = "openai"
$env:AGENTIC_MODEL_NAME = "gpt-5.4-mini"
$env:AGENTIC_MODEL_MAX_RETRIES = "0"
$env:AGENTIC_ALLOW_MODEL_API = "1"
try {
    uv run --locked pytest tests/test_model_live.py --run-model --model-framework langgraph -k "external-site or ten-point-rating" -v --tb=short
} finally {
    Remove-Item Env:AGENTIC_ALLOW_MODEL_API -ErrorAction SilentlyContinue
}
```

The filter also includes the new external-site cases. Once these pass, repeat with
the `-k` filter removed to run all 44 cases. Share failures and the summary, never
API credentials. Repeat successful live evaluations to assess variability.

Prompt improvements are not a deterministic semantic guarantee. Human review of
source and criteria remains required before execution. External-site integration
is still unimplemented. CrewAI now uses OpenAI; see the current setup guide.

The official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
notes that schema-compliant outputs can still contain mistakes; semantic tests
are needed in addition to output validation.
