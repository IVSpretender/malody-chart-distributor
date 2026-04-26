from pathlib import Path


# main.py
PAGE_SIZE = 20
BASE_URL = "http://localhost:2465"
SCAN_ROOTS = (Path("charts"), Path(".local/example_chart"))

# parser.py
SONG_ID_HEAD = 600000
CHART_ID_HEAD = 600000