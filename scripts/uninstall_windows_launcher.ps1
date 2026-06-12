# Removes only the current user's clarith:// protocol registration.
$ProtocolKey = "HKCU:\Software\Classes\clarith"
if (Test-Path -LiteralPath $ProtocolKey) {
    Remove-Item -LiteralPath $ProtocolKey -Recurse -Force
}
Write-Host "Removed the clarith:// launcher registration."
