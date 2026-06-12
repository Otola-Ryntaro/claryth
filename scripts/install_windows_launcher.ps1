# Registers the per-user clarith:// launcher. Administrator rights are not required.
$ErrorActionPreference = "Stop"
$Launcher = Join-Path $PSScriptRoot "clarith_launcher.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$ProtocolKey = "HKCU:\Software\Classes\clarith"
$LauncherName = (-join [char[]](12367, 12425, 12426, 12377)) + " Local Launcher"
New-Item -Path $ProtocolKey -Force | Out-Null
Set-ItemProperty -Path $ProtocolKey -Name "(Default)" -Value "URL:$LauncherName"
Set-ItemProperty -Path $ProtocolKey -Name "URL Protocol" -Value ""

$CommandKey = Join-Path $ProtocolKey "shell\open\command"
New-Item -Path $CommandKey -Force | Out-Null
$Command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" "%1"' -f $Launcher
Set-ItemProperty -Path $CommandKey -Name "(Default)" -Value $Command

Write-Host "Registered the clarith:// launcher for the current user."
Write-Host "Allow Chrome to open $LauncherName when prompted."
