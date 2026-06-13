# Removes only the current user's clarith:// protocol registration.
$ProtocolKey = "HKCU:\Software\Classes\clarith"
if (Test-Path -LiteralPath $ProtocolKey) {
    Remove-Item -LiteralPath $ProtocolKey -Recurse -Force
}
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AuthFile = Join-Path $ProjectRoot ".runtime\auth.json"
if (Test-Path -LiteralPath $AuthFile) {
    Remove-Item -LiteralPath $AuthFile -Force
}
Write-Host "Removed the clarith:// launcher registration."
Write-Host "Removed the per-user API credential."
