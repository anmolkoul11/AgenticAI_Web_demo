# Run from PowerShell, or right-click and choose Run with PowerShell.
param([switch]$Dev)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first. See docs/DASHBOARD_GUIDE.md.' }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop first.' }
    docker compose up -d --wait nats
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and try again.' }
    $env:DEMO_USERNAME = 'demo'
    $demoSecret = Read-Host 'Choose a synthetic hotel portal password (12+ characters; separate from dashboard accounts)' -AsSecureString
    $env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new('', $demoSecret).Password
    Remove-Variable demoSecret
    if ($env:DEMO_PASSWORD.Length -lt 12) { throw 'Demo password must be at least 12 characters.' }
    Write-Host 'Create your local dashboard account using your own username and password. No invitation code is needed.'
    Write-Host 'Each user adds their own API key after signing in; secure remembering is optional.'
    if ($Dev) {
        Write-Warning 'Development reload clears sessions and session keys. Do not edit code during active jobs. Hotel portal changes still need a launcher restart.'
        uv run --locked python -m agentic_web_demo.dashboard.launcher --dev
    } else {
        uv run --locked python -m agentic_web_demo.dashboard.launcher
    }
    if ($LASTEXITCODE -ne 0) { throw 'Demo stopped with an error. Review the message above.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Remove-Item Env:DEMO_PASSWORD -ErrorAction SilentlyContinue
    Read-Host 'Demo stopped. Press Enter to close'
}
