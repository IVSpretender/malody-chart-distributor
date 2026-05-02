from __future__ import annotations

import hashlib
import json
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import (
    CHART_ID_HEAD,
    EVENT_DEFAULT_SPONSOR,
    EVENT_ID_HEAD,
    EVENT_SOURCE_ROOT,
    SONG_ID_HEAD,
    SONG_SOURCE_ROOTS,
    SONG_TAGGED_ROOT,
)


_EVENT_JSON_NAME = "event.json"
_DEFAULT_EVENT_START_DATE = "2026-04-28"
_DEFAULT_EVENT_END_DATE = "2099-12-31"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@dataclass
class ScanSong:
    song_key: str
    song_folder_name: str
    path: str
    promote: int
    tag: str
    title: str
    title_org: str
    artist: str
    artist_org: str
    bpm: float
    length: int
    cover: str
    background: str
    mode_mask: int


@dataclass
class ScanChart:
    song_key: str
    hash: str
    path: str
    mc_name: str
    version: str
    level: int
    mode: int
    uid: int
    creator: str
    size: int
    type: int


@dataclass
class ScanEvent:
    event_key: str
    event_folder_name: str
    source_root: str
    cover: str
    sponsor: str
    start_date: str
    end_date: str
    active: bool
    song_keys: list[str]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_level(version: str) -> int:
    # 在字符串中寻找 "Lv"（不区分大小写），后面可能有小数点或直接数字。
    # 匹配示例："Lv.22", "LV11-12", "LV.10.1" "4K Easy" -> 返回 22、11、10、0
    if not version:
        return 0
    s = str(version)
    m = re.search(r"lv\.?\s*([0-9]+)", s, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    return 0



def _normalize_json_bytes(data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return payload.encode("utf-8")


def _hash_mc_content(data: dict[str, Any]) -> str:
    normalized = _normalize_json_bytes(data)
    return hashlib.sha1(normalized).hexdigest()


def _load_mc_data(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _discover_song_directories(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        entry
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower())
        if entry.is_dir() and any(entry.rglob("*.mc"))
    ]


def _discover_event_directories(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [entry for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()) if entry.is_dir()]


def _discover_image_name(directory: Path) -> str:
    for file_path in sorted(p for p in directory.iterdir() if p.is_file()):
        if file_path.suffix.lower() in _IMAGE_SUFFIXES:
            return file_path.name
    return ""


def _default_event_meta() -> dict[str, Any]:
    return {
        "sponsor": EVENT_DEFAULT_SPONSOR,
        "start_date": _DEFAULT_EVENT_START_DATE,
        "end_date": _DEFAULT_EVENT_END_DATE,
        "active": True,
    }


def _normalize_event_meta(raw: Any) -> tuple[dict[str, Any], bool]:
    meta = _default_event_meta()
    changed = False
    if isinstance(raw, dict):
        sponsor = raw.get("sponsor")
        if isinstance(sponsor, str) and sponsor:
            meta["sponsor"] = sponsor
        else:
            changed = True

        start_date = raw.get("start_date")
        if isinstance(start_date, str) and start_date:
            meta["start_date"] = start_date
        else:
            changed = True

        end_date = raw.get("end_date")
        if isinstance(end_date, str) and end_date:
            meta["end_date"] = end_date
        else:
            changed = True

        active = raw.get("active")
        if isinstance(active, bool):
            meta["active"] = active
        elif isinstance(active, int):
            meta["active"] = bool(active)
            changed = True
        else:
            changed = True
    else:
        changed = True

    return meta, changed


def _load_event_meta(event_dir: Path) -> dict[str, Any]:
    meta_path = event_dir / _EVENT_JSON_NAME
    raw_data: Any = None

    if meta_path.is_file():
        try:
            raw_data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            raw_data = None

    meta, changed = _normalize_event_meta(raw_data)
    if changed or not meta_path.is_file():
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta


def _song_key(path: str, folder_name: str) -> str:
    clean_path = path.strip("/")
    clean_folder = folder_name.strip("/")
    if not clean_path:
        return clean_folder
    return f"{clean_path}/{clean_folder}"


def _scan_song_directory(
    song_dir: Path,
    path_root: str,
    promote: int,
    tag: str,
) -> tuple[ScanSong | None, list[ScanChart]]:
    mc_files = sorted(song_dir.rglob("*.mc"))
    charts: list[ScanChart] = []

    title = ""
    title_org = ""
    artist = ""
    artist_org = ""
    cover = ""
    background = ""
    bpm = 0.0
    length = 0
    mode_mask = 0

    song_key = _song_key(path_root, song_dir.name)
    base_root = Path(path_root) / song_dir.name

    for mc_file in mc_files:
        mc_data = _load_mc_data(mc_file)
        if mc_data is None:
            continue

        meta_raw = mc_data.get("meta")
        meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        song_raw = meta.get("song")
        song_meta: dict[str, Any] = song_raw if isinstance(song_raw, dict) else {}

        chart_title = str(song_meta.get("title") or meta.get("title") or "")
        chart_title_org = str(song_meta.get("titleorg") or meta.get("titleorg") or "")
        chart_artist = str(song_meta.get("artist") or meta.get("artist") or "")
        chart_artist_org = str(song_meta.get("artistorg") or meta.get("artistorg") or "")
        chart_cover = str(meta.get("cover") or "")
        chart_background = str(meta.get("background") or "")
        chart_version = str(meta.get("version") or "")
        chart_mode = _safe_int(meta.get("mode", -1), default=-1)
        chart_uid = _safe_int(meta.get("uid", 0), default=0)
        chart_creator = str(meta.get("creator") or "")
        chart_type = _safe_int(meta.get("type", 2), default=2)
        chart_length = _safe_int(meta.get("length", 0), default=0)
        chart_bpm = _safe_float(song_meta.get("bpm", 0))

        if not title:
            title = chart_title
        if not title_org:
            title_org = chart_title_org
        if not artist:
            artist = chart_artist
        if not artist_org:
            artist_org = chart_artist_org
        if not cover:
            cover = chart_cover
        if not background:
            background = chart_background
        if bpm == 0.0 and chart_bpm:
            bpm = chart_bpm

        length = max(length, chart_length)
        if 0 <= chart_mode <= 30:
            mode_mask |= 1 << chart_mode

        mc_rel = mc_file.relative_to(song_dir)
        chart_dir = mc_rel.parent if mc_rel.parent.as_posix() != "." else Path(".")
        chart_root = base_root / chart_dir
        chart_path = chart_root.as_posix().strip("/")

        charts.append(
            ScanChart(
                song_key=song_key,
                hash=_hash_mc_content(mc_data),
                path=chart_path,
                mc_name=mc_rel.as_posix(),
                version=chart_version,
                level=_parse_level(chart_version),
                mode=chart_mode,
                uid=chart_uid,
                creator=chart_creator,
                size=mc_file.stat().st_size,
                type=chart_type,
            )
        )

    if not charts:
        return None, []

    song = ScanSong(
        song_key=song_key,
        song_folder_name=song_dir.name,
        path=path_root,
        promote=promote,
        tag=tag,
        title=title,
        title_org=title_org,
        artist=artist,
        artist_org=artist_org,
        bpm=bpm,
        length=length,
        cover=cover,
        background=background,
        mode_mask=mode_mask,
    )
    return song, charts


def scan_song_root(root: Path, promote: int) -> tuple[list[ScanSong], list[ScanChart]]:
    songs: list[ScanSong] = []
    charts: list[ScanChart] = []
    path_root = root.as_posix().strip("/")

    for song_dir in _discover_song_directories(root):
        song, song_charts = _scan_song_directory(song_dir, path_root, promote, tag="")
        if song is None:
            continue
        songs.append(song)
        charts.extend(song_charts)

    return songs, charts


def scan_event_root(root: Path) -> tuple[list[ScanEvent], list[ScanSong], list[ScanChart]]:
    events: list[ScanEvent] = []
    songs: list[ScanSong] = []
    charts: list[ScanChart] = []

    for event_dir in _discover_event_directories(root):
        event_root = root.name
        path_root = f"{event_root}/{event_dir.name}".strip("/")
        cover = _discover_image_name(event_dir)
        meta = _load_event_meta(event_dir)

        event_songs: list[ScanSong] = []
        event_charts: list[ScanChart] = []

        for song_dir in _discover_song_directories(event_dir):
            song, song_charts = _scan_song_directory(song_dir, path_root, promote=0, tag="")
            if song is None:
                continue
            event_songs.append(song)
            event_charts.extend(song_charts)

        event = ScanEvent(
            event_key=event_dir.name,
            event_folder_name=event_dir.name,
            source_root=event_root,
            cover=cover,
            sponsor=str(meta.get("sponsor", "")),
            start_date=str(meta.get("start_date", "")),
            end_date=str(meta.get("end_date", "")),
            active=bool(meta.get("active", True)),
            song_keys=[song.song_key for song in event_songs],
        )
        events.append(event)
        songs.extend(event_songs)
        charts.extend(event_charts)

    return events, songs, charts


def scan_tagged_root(root: Path) -> tuple[list[ScanSong], list[ScanChart]]:
    songs: list[ScanSong] = []
    charts: list[ScanChart] = []

    if not root.is_dir():
        return songs, charts

    root_name = root.as_posix().strip("/")
    for tag_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not tag_dir.is_dir():
            continue
        tag = tag_dir.name
        path_root = f"{root_name}/{tag}".strip("/")
        for song_dir in _discover_song_directories(tag_dir):
            song, song_charts = _scan_song_directory(song_dir, path_root, promote=0, tag=tag)
            if song is None:
                continue
            songs.append(song)
            charts.extend(song_charts)

    return songs, charts


def scan_all_sources(
    song_roots: list[Path] | None = None,
    event_root: Path | None = None,
) -> dict[str, Any]:
    songs: list[ScanSong] = []
    charts: list[ScanChart] = []
    events: list[ScanEvent] = []

    song_roots = song_roots or SONG_SOURCE_ROOTS
    event_root = event_root or EVENT_SOURCE_ROOT

    for root in song_roots:
        promote = 1 if root.name == "promote" else 0
        root_songs, root_charts = scan_song_root(root, promote)
        songs.extend(root_songs)
        charts.extend(root_charts)

    tagged_songs, tagged_charts = scan_tagged_root(SONG_TAGGED_ROOT)
    songs.extend(tagged_songs)
    charts.extend(tagged_charts)

    event_list, event_songs, event_charts = scan_event_root(event_root)
    events.extend(event_list)
    songs.extend(event_songs)
    charts.extend(event_charts)

    return {
        "songs": songs,
        "charts": charts,
        "events": events,
    }


def reload_database() -> None:
    try:
        import db as db_module
    except ImportError:
        return

    snapshot = scan_all_sources()
    db_module.reload_database(
        snapshot,
        id_heads={
            "sid": SONG_ID_HEAD,
            "cid": CHART_ID_HEAD,
            "eid": EVENT_ID_HEAD,
        },
        now=int(time.time()),
    )


def main() -> None:
    reload_database()
    print("[OK] database reload finished")
    import db as db_module
    db_module.print_stats()


if __name__ == "__main__":
    main()
