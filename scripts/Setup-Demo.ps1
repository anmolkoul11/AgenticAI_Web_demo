$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv and restart your terminal first.' }
    uv sync --locked
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    uv run --locked playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    Write-Host 'Setup complete. Start Docker Desktop, then run scripts/Start-Demo.ps1.'
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
