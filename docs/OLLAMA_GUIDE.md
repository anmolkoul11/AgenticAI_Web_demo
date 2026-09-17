# Local Ollama setup for the LangGraph demo

Ollama runs the model; LangGraph coordinates the tools. This path needs no OpenAI
key or hosted API credits. It uses real local inference, not simulated scenarios.
The adapter is implemented and tested with mock responses; actual inference and
GPU usage must still be verified on your machine. Checkpoint 5 remains pending.

## 1. Install Ollama on Windows

Download and run the official installer: https://ollama.com/download/windows.
It normally runs in the background after installation. Reopen VS Code completely
so its terminal receives the updated PATH, then check:

```powershell
ollama --version
```

Use a current NVIDIA driver. The suggested starting model is qwen3:8b (Q4_K_M,
about 5.2 GB download). Runtime memory exceeds model-file size; the reported
12 GB VRAM should be a reasonable starting point with our 4096-token context,
but GPU placement and performance must be measured. Allow extra disk space for
Ollama itself. No CUDA development toolkit or Docker-based Ollama is required
for this native Windows setup. Docker is still used separately for NATS.

## 2. Keep the model service local

Quit Ollama using its system tray icon. In Windows **Edit environment variables
for your account**, add these user variables:

- `OLLAMA_NO_CLOUD` = `1`
- `OLLAMA_HOST` = `127.0.0.1:11434`

Optional: set `OLLAMA_MODELS` to a separate models folder, such as
`D:\AIModels\Ollama`, before downloading. Do not store model weights in Git.
Restart Ollama from the Start menu after applying the variables. Ollama's server
log should contain `Ollama cloud disabled: true`. Keep this setting: a localhost
client URL alone does not guarantee that a server cannot use a cloud model.

The client pins http://127.0.0.1:11434/api/chat, ignores proxy variables, rejects
redirects, sends no credentials, and permits only qwen3:8b/qwen3:4b names. It does
not download models or fall back to OpenAI. Use official model pulls rather than
replacing these tags with custom/cloud aliases. Model pulls and app updates need
internet; local inference after download does not need a hosted model API.

## 3. Download the model

This command downloads about 5.2 GB and stores it outside the project:

```powershell
ollama pull qwen3:8b
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
```

Do not start a second `ollama serve` if the tray application is already serving
port 11434. If the service is unreachable, open Ollama from the Start menu first.
For a smaller fallback, explicitly pull qwen3:4b (about 2.5 GB) and change the
model setting below; there is no automatic substitution.

## 4. Run one plan-only request

In the project's VS Code PowerShell terminal:

```powershell
Set-Location 'D:\Projects\AgenticAI_Web_demo'
uv sync --locked
$env:AGENTIC_MODEL_PROVIDER = "ollama"
$env:AGENTIC_MODEL_NAME = "qwen3:8b"
$env:AGENTIC_OLLAMA_TIMEOUT_SECONDS = "120"

$checkIn = (Get-Date).AddDays(7).ToString('yyyy-MM-dd')
$checkOut = (Get-Date).AddDays(9).ToString('yyyy-MM-dd')
$demoRequest = "Find New York hotels from $checkIn to $checkOut, at most USD 200 per night including taxes, rated at least 4 out of 5."
uv run --locked agentic-demo langgraph --mode live --request $demoRequest --plan-only
ollama ps
```

No portal, NATS, website credentials, OpenAI key or --allow-model-api is required
for this preview. The local config/rules.yaml policy must still exist. Expect
`status: planned`, `model_used: true`, model.provider `ollama`, and correct plan
fields. A first call can be slower while weights load. `ollama ps` shows GPU/CPU
placement; aim for 100% GPU. Run it promptly: the adapter keeps the model loaded
for five minutes. Hardware memory is released with `ollama stop qwen3:8b`.

The adapter uses structured JSON, disables thinking, limits context to 4096 and
output to 1200 tokens, and makes one HTTP request with no automatic retries.
The local timeout defaults to 120 seconds (allowed 1-300), per network operation,
not a hard whole-workflow deadline. OPENAI-specific retry/token settings do not
apply. HTTP errors, missing model, malformed/incomplete output, or policy issues
stop before tools. Only synthetic demo requests should be used.

## 5. Run the actual browser-to-events workflow

Follow PORTAL_GUIDE.md to start the portal in another terminal, and start NATS:

```powershell
docker compose up -d --wait nats
$env:DEMO_USERNAME = "demo"
$demoPassword = Read-Host "Running portal's demo password" -AsSecureString
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $demoPassword).Password
Remove-Variable demoPassword
uv run --locked agentic-demo langgraph --mode live --request $demoRequest --headed
```

Use the same demo username/password as the running portal. Expected: 4 listings,
2 matches and 2 verified receipts. This command replans, rather than resuming the
preview. All existing validation, policy limits, storage and recovery behavior
in LANGGRAPH_GUIDE.md still applies. The model never sees portal credentials.

## 6. Test and record evidence

Regular tests remain offline (HTTP responses mocked), even if Ollama is running:

```powershell
uv run --locked pytest
uv run --locked pytest --run-browser --run-nats
```

With the same explicit Ollama provider/model variables set, real-model evaluation:

```powershell
uv run --locked pytest tests/test_model_live.py --run-model -q
uv run --locked pytest tests/test_browser_integration.py -k live_model --run-model --run-browser --run-nats -q
```

These are 12 semantic calls and 1 end-to-end call, using local compute, no hosted
API billing. Do not omit the provider configuration: the default provider remains
OpenAI, whose live tests are independently gated by AGENTIC_ALLOW_MODEL_API=1.
Failures are evidence to improve prompts or model choice, not tests to discard.
Save model tag/digest (`ollama list`), Ollama version, GPU placement, test results
and timing when recording acceptance. Passing local real-model tests can complete
LangGraph acceptance; OpenAI-specific paid evaluations are not mandatory too.

## Troubleshooting and switching providers

- Command not found: fully restart VS Code after installing Ollama.
- local_connection: check the tray app and port 11434; do not expose it on the LAN.
- local_model_missing: run `ollama pull` for the exact configured allowed tag.
- local_service_error: check server logs/version and available GPU memory.
- timeout: close GPU-heavy applications and retry once; increase the local timeout
  if needed within its bound. A failed client request may not immediately stop
  server computation. Do not rapidly launch repeated requests.
- invalid_response/incomplete: inspect the safe report; check model/version.
- policy_rejected: keep price <= 200 and rating >= 4 for the default policy.
- needs_input: resubmit the complete request with explicit dates and inclusive
  thresholds; no conversation state is retained.

The shared schema and versioned instructions live in agents/model_contract.py.
Switching back to OpenAI requires setting AGENTIC_MODEL_PROVIDER=openai, a valid
AGENTIC_MODEL_NAME, local OPENAI_API_KEY, and explicit --allow-model-api. No
provider switch or paid call is performed automatically.

Official references: [Windows setup](https://docs.ollama.com/windows),
[local-only mode and GPU checks](https://docs.ollama.com/faq),
[structured output](https://docs.ollama.com/capabilities/structured-outputs),
[Qwen3 8B](https://ollama.com/library/qwen3:8b).
