#!/usr/bin/env pwsh
# Start Uvicorn with source directory reload.

Write-Host "Starting Malody Chart Distributor..." -ForegroundColor Green
Write-Host ""

Write-Host "Starting Uvicorn server..." -ForegroundColor Cyan
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 --reload-dir charts --reload-dir promote --reload-dir events --reload-include '*.mc' --reload-include 'event.json'
