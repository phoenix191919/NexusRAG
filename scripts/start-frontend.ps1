# Start NexusRAG UI (Vite)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "frontend")

if (-not (Test-Path .\node_modules)) {
  Write-Host "Installing frontend deps..."
  npm install
}

Write-Host "UI → http://127.0.0.1:5173"
npm run dev
