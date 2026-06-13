# Installs an already verified and extracted Clarith release for the current user.
param([switch]$SkipProtocolRegistration)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
foreach ($required in @("uv.lock", "backend\data\release_manifest.json", "backend\data\release_manifest.sig")) {
    $path = Join-Path $ProjectRoot $required
    if (-not (Test-Path -LiteralPath $path)) { throw "Release file is missing: $required" }
}

$uv = Get-Command "uv.exe" -ErrorAction SilentlyContinue
if (-not $uv) { $uv = Get-Command "uv" -ErrorAction SilentlyContinue }
if (-not $uv) {
    python -m pip install uv==0.11.21
    if ($LASTEXITCODE -ne 0) { throw "Failed to install uv 0.11.21." }
    $uv = Get-Command "uv.exe" -ErrorAction Stop
}
& $uv.Source sync --locked --no-dev
if ($LASTEXITCODE -ne 0) { throw "Locked Python dependency installation failed." }

& (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -c "from backend.app.integrity import verify_release_manifest; r=verify_release_manifest(); print(r); raise SystemExit(0 if r.ok else 1)"
if ($LASTEXITCODE -ne 0) { throw "Signed database verification failed." }

& (Join-Path $PSScriptRoot "install_windows_launcher.ps1") -SkipProtocolRegistration:$SkipProtocolRegistration
if ($LASTEXITCODE -ne 0) { throw "Launcher installation failed." }
Write-Host "Clarith release installation completed. Reload the extension in Chrome."
