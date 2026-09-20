# OpenAI setup (LangGraph and CrewAI)

OpenAI is now the only implemented live provider. The retired Ollama adapter and
its provider-specific tests/setup guide have been removed. This does not uninstall
Ollama or delete downloaded models. Structured plans and approved execution still
need no model, API key or paid calls. Existing saved plans retain provenance.

In the terminal where you will create model-assisted proposals:

```powershell
$env:AGENTIC_MODEL_PROVIDER = "openai"
$env:AGENTIC_MODEL_NAME = "gpt-5.4-mini"
$env:AGENTIC_MODEL_MAX_RETRIES = "0"
$env:AGENTIC_MODEL_TIMEOUT_SECONDS = "60"
$env:AGENTIC_MODEL_MAX_OUTPUT_TOKENS = "1200"
$apiSecret = Read-Host "Enter your OpenAI project API key" -AsSecureString
$env:OPENAI_API_KEY = ([System.Net.NetworkCredential]::new("", $apiSecret).Password).Trim()
Remove-Variable apiSecret
```

Enter the API key at the secure prompt, not your portal password. Never paste it
into chat, a commit, or diagnostics. These variables apply to this process and its
children; `.env` is not loaded automatically. API usage is billed separately from
ChatGPT subscriptions. Configure billing and monitor usage in your API account.

Both `langgraph plan --request ...` and `crewai plan --request ...` require
`--allow-model-api`. Use synthetic data only. Review saved proposals before
execution. Neither framework's approved-plan execution makes a model call.

To change to an organization-owned OpenAI account later, re-enter its approved key
and select a model available to that project. A different enterprise endpoint or
security-token scheme requires a separate adapter change; no arbitrary endpoint
override or automatic fallback is implemented.

## Validation handoff

No tests or paid calls were run while making this migration. Run:

```powershell
uv run --locked pytest -q
uv run --locked pytest --run-browser --run-nats -q --tb=short
```

The second command requires Chromium and local NATS. These checks mock model calls.
For paid semantic tests, first target the three strict-comparison regressions:

```powershell
$env:AGENTIC_ALLOW_MODEL_API = "1"
try {
    uv run --locked pytest tests/test_model_live.py --run-model --model-framework langgraph -k "strict" -v --tb=short
} finally {
    Remove-Item Env:AGENTIC_ALLOW_MODEL_API -ErrorAction SilentlyContinue
}
```

After those pass, remove BOTH `-k` and `"strict"` to run all 44 cases. Repeat with
`--model-framework crewai` to validate the independent CrewAI path. A passing
single run is not a guarantee of interpretation accuracy; retain human review.

Prompt v3 explicitly distinguishes unsupported tasks from strict comparisons that
need clarification. Original expectations remain unchanged. The official
[Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
explains that schema compliance alone does not eliminate semantic errors.
