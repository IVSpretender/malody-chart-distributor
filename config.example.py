from pathlib import Path
import os

# main.py
WELCOME_MESSAGE = "Welcome to my private server!"
PAGE_SIZE = 10
BASE_URL = "http://localhost:8000"
SCAN_ROOTS = [Path("charts"), Path("promote")]
# "events" 的所有子文件夹也会被扫描
for entry in os.scandir("events"):
    if entry.is_dir():
        SCAN_ROOTS.append(Path(entry.path))

EVENT_SCAN_ROOTS = [Path("events")]

# parser.py
SONG_ID_HEAD = 600000
CHART_ID_HEAD = 600000
EVENT_ID_HEAD = 600000
EVENT_PAGE_SIZE = 10