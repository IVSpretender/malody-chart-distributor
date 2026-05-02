#!/bin/bash
# Start Uvicorn with source directory reload.

echo -e "\033[32mStarting Malody Chart Distributor...\033[0m"
echo ""

# Check if config.py exists, if not copy from config.example.py
if [ ! -f "config.py" ]; then
    echo -e "\033[33m[Setup] config.py not found. Copying from config.example.py...\033[0m"
    cp config.example.py config.py
    echo -e "\033[32m[Setup] config.py created successfully.\033[0m"
    echo -e "\033[36m[Setup] Please review config.py and adjust settings as needed.\033[0m"
    echo -e "\033[36m[Setup] Key settings: BASE_URL, SONG_SOURCE_ROOTS, DOWNLOAD_ROOTS\033[0m"
fi

# Create required directories
for dir in data charts charts_tagged promote events; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo -e "\033[32m[Setup] Created directory: $dir\033[0m"
    fi
done



echo -e "\033[36mStarting Uvicorn server...\033[0m"
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000 --reload-dir charts --reload-dir charts_tagged --reload-dir promote --reload-dir events --reload-include '*.mc' --reload-include 'event.json'
