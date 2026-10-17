param([switch]$Offline, [int]$Port=8000)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $taskRoot
if ($Offline) { $env:CB_OFFLINE='true'; $env:CB_PROVIDER='ollama'; $env:CB_RUNNER='docker' }
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Create a Python 3.12 .venv and install the package first. See README.md.' }
if (!(Test-Path -LiteralPath 'dist\index.html')) { throw 'Build the frontend first: npm ci --legacy-peer-deps; npm run build' }
& '.\.venv\Scripts\python.exe' -m uvicorn claimbreaker.app:app --host 127.0.0.1 --port $Port
