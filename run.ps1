#!/usr/bin/env pwsh
# Start Uvicorn with source directory reload.

Write-Host "Starting Malody Chart Distributor..." -ForegroundColor Green
Write-Host ""

# Check if config.py exists, if not copy from config.example.py
if (-not (Test-Path "config.py")) {
    Write-Host "[Setup] config.py not found. Copying from config.example.py..." -ForegroundColor Yellow
    Copy-Item "config.example.py" "config.py"
    Write-Host "[Setup] config.py created successfully." -ForegroundColor Green
    Write-Host "[Setup] Please review config.py and adjust settings as needed." -ForegroundColor Cyan
    Write-Host "[Setup] Key settings: BASE_URL, SONG_SOURCE_ROOTS, DOWNLOAD_ROOTS" -ForegroundColor Cyan
}

# Create required directories
$dirs = @("data", "charts", "charts_tagged", "promote", "events")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "[Setup] Created directory: $dir" -ForegroundColor Green
    }
}



Write-Host "Starting Uvicorn server..." -ForegroundColor Cyan
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 --reload-dir charts --reload-dir charts_tagged --reload-dir promote --reload-dir events --reload-include '*.mc' --reload-include 'event.json'
