#!/bin/bash
# Start Uvicorn with source directory reload.

echo -e "\033[32mStarting Malody Chart Distributor...\033[0m"
echo ""

echo -e "\033[36mStarting Uvicorn server...\033[0m"
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 --reload-dir charts --reload-dir promote --reload-dir events --reload-include '*.mc' --reload-include 'event.json'
