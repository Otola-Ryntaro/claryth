# Starts Clarith's localhost API or optional Ollama from the registered protocol.
param(
    [string]$Uri = "clarith://start-api"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
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
    if (Test-LocalPort 8765) { return }
    $python = Find-Python
    Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "backend.app" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RuntimeDir "api.out.log") `
        -RedirectStandardError (Join-Path $RuntimeDir "api.err.log")
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
