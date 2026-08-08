# Start NexusRAG API (FastAPI + uvicorn)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
  Write-Error "Missing .venv — create it with: python -m venv .venv"
}

.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
Write-Host "API → http://127.0.0.1:8000  docs → /docs"
uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
