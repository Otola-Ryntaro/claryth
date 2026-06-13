# Registers the per-user clarith:// launcher and local API credential.
param(
    [switch]$RotateToken,
    [switch]$SkipProtocolRegistration
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "clarith_launcher.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$AuthFile = Join-Path $RuntimeDir "auth.json"
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

if ($RotateToken -or -not (Test-Path -LiteralPath $AuthFile)) {
    $bytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    @{ apiToken = $token } | ConvertTo-Json | Set-Content -LiteralPath $AuthFile -Encoding utf8
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
& icacls.exe $AuthFile /inheritance:r /grant:r "*$($identity.Value)`:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to restrict the API credential ACL." }

$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if (-not $npm) { $npm = Get-Command "npm" -ErrorAction SilentlyContinue }
if (-not $npm) { throw "npm was not found. Install Node.js and npm first." }
& $npm.Source ci --prefix (Join-Path $ProjectRoot "extension")
if ($LASTEXITCODE -ne 0) { throw "Extension dependency installation failed." }
& $npm.Source run build --prefix (Join-Path $ProjectRoot "extension")
if ($LASTEXITCODE -ne 0) { throw "Extension build failed." }

$LauncherName = (-join [char[]](12367, 12425, 12426, 12377)) + " Local Launcher"
if (-not $SkipProtocolRegistration) {
    $ProtocolKey = "HKCU:\Software\Classes\clarith"
    New-Item -Path $ProtocolKey -Force | Out-Null
    Set-ItemProperty -Path $ProtocolKey -Name "(Default)" -Value "URL:$LauncherName"
    Set-ItemProperty -Path $ProtocolKey -Name "URL Protocol" -Value ""

    $CommandKey = Join-Path $ProtocolKey "shell\open\command"
    New-Item -Path $CommandKey -Force | Out-Null
    $Command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" "%1"' -f $Launcher
    Set-ItemProperty -Path $CommandKey -Name "(Default)" -Value $Command
    Write-Host "Registered the clarith:// launcher for the current user."
}
Write-Host "Created the per-user API credential and rebuilt extension/dist."
Write-Host "Reload the Clarith extension in chrome://extensions after token rotation."
if (-not $SkipProtocolRegistration) {
    Write-Host "Allow Chrome to open $LauncherName when prompted."
}
