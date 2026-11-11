# Developer/publisher build only. End users run the resulting installer.
[CmdletBinding()]
param(
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?$')]
    [string]$Version = '1.0.0',
    [switch]$PortableOnly,
    [string]$InnoCompiler = ''
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Build this Windows x64 release on 64-bit Windows.'
}
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$workRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'build\windows-release'))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist\windows\$Version"))
foreach ($taskPath in @($workRoot, $releaseRoot)) {
    if (-not $taskPath.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release output must remain inside this project.'
    }
}
if (Test-Path -LiteralPath $releaseRoot) {
    throw "Release output already exists: $releaseRoot. Choose a new version or move the old release yourself."
}
$null = Get-Command uv -ErrorAction Stop
if (-not $PortableOnly) {
    if (-not $InnoCompiler) {
        $taskCompiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($taskCompiler) { $InnoCompiler = $taskCompiler.Source }
        else {
            foreach ($taskCandidate in @(
                (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 7\ISCC.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 7\ISCC.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
            )) {
                if (Test-Path -LiteralPath $taskCandidate -PathType Leaf) {
                    $InnoCompiler = $taskCandidate
                    break
                }
            }
        }
    }
    if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
        throw 'Install Inno Setup 7 (or a current Inno Setup 6) or pass -InnoCompiler with its ISCC.exe path. Use -PortableOnly for a folder build.'
    }
}

$taskEnvironmentNames = @('UV_PROJECT_ENVIRONMENT', 'PLAYWRIGHT_BROWSERS_PATH',
    'AGENTIC_RELEASE_ROOT', 'AGENTIC_RELEASE_VERSION', 'AGENTIC_RELEASE_FILE_VERSION',
    'AGENTIC_RELEASE_STAGING', 'CREWAI_DISABLE_TELEMETRY', 'CREWAI_DISABLE_TRACKING',
    'CREWAI_TRACING_ENABLED', 'OTEL_SDK_DISABLED', 'LANGSMITH_TRACING')
$previousEnvironment = @{}
foreach ($name in $taskEnvironmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $projectRoot
    $null = New-Item -ItemType Directory -Path $workRoot -Force
    $null = New-Item -ItemType Directory -Path $releaseRoot
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $workRoot 'venv'
    $env:PLAYWRIGHT_BROWSERS_PATH = '0'
    $env:AGENTIC_RELEASE_ROOT = $releaseRoot
    $env:AGENTIC_RELEASE_VERSION = $Version
    $env:AGENTIC_RELEASE_FILE_VERSION = ($Version -replace '^([0-9]+\.[0-9]+\.[0-9]+).*$', '$1') + '.0'
    $env:AGENTIC_RELEASE_STAGING = Join-Path $workRoot 'staging'
    $env:CREWAI_DISABLE_TELEMETRY = 'true'
    $env:CREWAI_DISABLE_TRACKING = 'true'
    $env:CREWAI_TRACING_ENABLED = 'false'
    $env:OTEL_SDK_DISABLED = 'true'
    $env:LANGSMITH_TRACING = 'false'

    Write-Host 'Preparing the locked release environment...'
    uv sync --locked --no-dev --group release --python 3.11
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the locked release dependencies.' }
    Write-Host 'Downloading Chromium for inclusion in the installer...'
    uv run --no-sync python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the bundled Chromium browser.' }
    uv run --no-sync python packaging/windows/prepare_release.py prepare --root $projectRoot --staging $env:AGENTIC_RELEASE_STAGING
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare release resources.' }
    Write-Host 'Bundling Agentic Studio (no application or workflow is started)...'
    uv run --no-sync python -m PyInstaller --noconfirm --clean --distpath $releaseRoot --workpath (Join-Path $workRoot 'pyinstaller') packaging/windows/AgenticStudio.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed. Inspect its build output before distributing anything.' }
    $applicationPath = Join-Path $releaseRoot 'AgenticStudio'
    uv run --no-sync python packaging/windows/prepare_release.py finish --root $projectRoot --application $applicationPath --version $Version
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare Companion files and package notices.' }
    if (-not $PortableOnly) {
        Write-Host 'Creating the per-user Windows installer...'
        & $InnoCompiler (Join-Path $projectRoot 'packaging\windows\AgenticStudio.iss')
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed. No installer was completed.' }
    }
    Write-Host "Release candidate: $releaseRoot"
    Write-Host 'Nothing was launched or installed. Manual acceptance, publisher terms, signing and extension-store publication remain separate release steps.'
} finally {
    Set-Location -LiteralPath $previousLocation
    foreach ($name in $taskEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
