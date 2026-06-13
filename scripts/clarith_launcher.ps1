# Starts Clarith's localhost API or optional Ollama from the registered protocol.
param(
    [string]$Uri = "clarith://start-api"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$AuthFile = Join-Path $RuntimeDir "auth.json"
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

function Test-LocalPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(500) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Get-ClarithToken {
    if (-not (Test-Path -LiteralPath $AuthFile)) {
        throw "Clarith API credential was not found. Run install_windows_launcher.ps1."
    }
    $config = Get-Content -Raw -LiteralPath $AuthFile | ConvertFrom-Json
    if (-not $config.apiToken) { throw "Clarith API credential is invalid." }
    return [string]$config.apiToken
}

function Test-ClarithApi {
    param([string]$Token)
    try {
        $health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8765/health" `
            -Headers @{ "X-Clarith-Token" = $Token } `
            -TimeoutSec 2
        return (
            $health.app_id -eq "jp.clarith.local-api" -and
            $health.protocol_version -eq 1 -and
            $health.authenticated -eq $true -and
            -not [string]::IsNullOrWhiteSpace([string]$health.startup_nonce)
        )
    }
    catch {
        return $false
    }
}

function Find-Python {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    foreach ($name in @("python.exe", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw "Python was not found. Install Python 3.11 or later."
}

function Find-Ollama {
    $command = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $fallback = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    throw "Ollama was not found. Install Ollama first."
}

function Start-ClarithApi {
    $token = Get-ClarithToken
    if (Test-ClarithApi $token) { return }
    if (Test-LocalPort 8765) {
        throw "Port 8765 is occupied by a service that failed Clarith authentication."
    }
    $python = Find-Python
    Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "backend.app" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeDir "api.out.log") `
        -RedirectStandardError (Join-Path $RuntimeDir "api.err.log")
    foreach ($attempt in 1..20) {
        Start-Sleep -Milliseconds 250
        if (Test-ClarithApi $token) { return }
    }
    throw "Clarith API did not pass authenticated health check after startup."
}

function Start-ClarithOllama {
    if (Test-LocalPort 11434) { return }
    $ollama = Find-Ollama
    Start-Process `
        -FilePath $ollama `
        -ArgumentList "serve" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeDir "ollama.out.log") `
        -RedirectStandardError (Join-Path $RuntimeDir "ollama.err.log")
}

$action = ([Uri]$Uri).Host.ToLowerInvariant()
switch ($action) {
    "start-api" { Start-ClarithApi }
    "start-ollama" { Start-ClarithOllama }
    "start-all" {
        Start-ClarithOllama
        Start-ClarithApi
    }
    default { throw "Unsupported launcher action: $action" }
}
