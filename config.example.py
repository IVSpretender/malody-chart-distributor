from pathlib import Path
import os


def _child_dirs(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return [Path(entry.path) for entry in os.scandir(base) if entry.is_dir()]

# main.py
WELCOME_MESSAGE = "Welcome to my private server!"
PAGE_SIZE = 10
BASE_URL = "http://localhost:8000"

# 目录源：charts / promote 作为歌曲来源，events 作为活动来源。
SONG_SOURCE_ROOTS = [Path("charts"), Path("promote")]
EVENT_SOURCE_ROOT = Path("events")
EVENT_SOURCE_ROOTS = [EVENT_SOURCE_ROOT]

# 下载路径解析会使用的根列表：包含歌曲源和 events 的一级子目录。
DOWNLOAD_ROOTS = SONG_SOURCE_ROOTS + _child_dirs(EVENT_SOURCE_ROOT)

SCAN_ROOTS = DOWNLOAD_ROOTS
EVENT_SCAN_ROOTS = EVENT_SOURCE_ROOTS

# parser.py
SONG_ID_HEAD = 600000
CHART_ID_HEAD = 600000
EVENT_ID_HEAD = 600000
EVENT_PAGE_SIZE = 10
EVENT_DEFAULT_SPONSOR = "Admin"