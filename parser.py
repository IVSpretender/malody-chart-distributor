from __future__ import annotations

import hashlib
import json
import os
from threading import Lock
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import SONG_ID_HEAD, CHART_ID_HEAD


_SID_STATE_FILENAME = ".sid_state.json"
_SID_STATE_LOCK = Lock()
_SID_STATE_VERSION = 2


@dataclass
class ParsedChart:
    sid: int
    cid: int
    source_name: str
    source_type: str
    source_hash: str
    mc_name: str
    chart_subdir: str
    background: str
    cover: str
    title: str
    titleorg: str
    artist: str
    artistorg: str
    version: str
    mode: int
    creator: str
    free: int
    bpm: float


def compute_directory_md5(directory_path: str | Path) -> str:
    md5 = hashlib.md5()
    base = Path(directory_path)
    for file_path in sorted(p for p in base.rglob("*") if p.is_file()):
        relative = file_path.relative_to(base).as_posix().encode("utf-8")
        md5.update(relative)
        md5.update(b"\x00")
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                md5.update(chunk)
        md5.update(b"\x00")
    return md5.hexdigest()


def _parse_mc_content(mc_content: bytes) -> dict[str, Any]:
    data = json.loads(mc_content.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(".mc 文件根结构不是 JSON 对象")
    return data


def _chart_from_mc_data(
    *,
    data: dict[str, Any],
    sid: int,
    cid: int,
    source_name: str,
    source_type: str,
    source_hash: str,
    mc_name: str,
    chart_subdir: str,
) -> ParsedChart:
    meta_raw = data.get("meta")
    meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    song_raw = meta.get("song")
    song: dict[str, Any] = song_raw if isinstance(song_raw, dict) else {}

    title = str(song.get("title") or meta.get("title") or "")
    titleorg = str(song.get("titleorg") or meta.get("titleorg") or "")
    artist = str(song.get("artist") or meta.get("artist") or "")
    artistorg = str(song.get("artistorg") or meta.get("artistorg") or "")
    background = str(meta.get("background") or "")
    cover = str(meta.get("cover") or "")
    version = str(meta.get("version") or "")
    mode = int(meta.get("mode", -1))
    creator = str(meta.get("creator") or "")
    free_raw = meta.get("free", 0)
    free = 1 if bool(free_raw) else 0
    bpm_value = song.get("bpm", 0)

    try:
        bpm = float(bpm_value)
    except (TypeError, ValueError):
        bpm = 0.0

    return ParsedChart(
        sid=sid,
        cid=cid,
        source_name=source_name,
        source_type=source_type,
        source_hash=source_hash,
        mc_name=mc_name,
        chart_subdir=chart_subdir,
        background=background,
        cover=cover,
        title=title,
        titleorg=titleorg,
        artist=artist,
        artistorg=artistorg,
        version=version,
        mode=mode,
        creator=creator,
        free=free,
        bpm=bpm,
    )


def parse_extracted_chart_dir(directory_path: str | Path, sid: int, cid_start: int) -> list[ParsedChart]:
    base = Path(directory_path)
    source_hash = compute_directory_md5(base)
    mc_files = sorted(base.rglob("*.mc"))
    charts: list[ParsedChart] = []
    cid = cid_start

    for mc_file in mc_files:
        mc_rel = mc_file.relative_to(base)
        mc_data = _parse_mc_content(mc_file.read_bytes())
        charts.append(
            _chart_from_mc_data(
                data=mc_data,
                sid=sid,
                cid=cid,
                source_name=base.name,
                source_type="folder",
                source_hash=source_hash,
                mc_name=mc_rel.as_posix(),
                chart_subdir=mc_rel.parent.as_posix() if mc_rel.parent.as_posix() != "." else "",
            )
        )
        cid += 1

    return charts


def _normalize_song_key(root: Path, entry: Path) -> str:
    rel = entry.relative_to(root).as_posix().strip("/")
    rel = "/".join(part for part in rel.split("/") if part)
    if os.name == "nt":
        return rel.lower()
    return rel


def _sid_state_path(root: Path) -> Path:
    return root / _SID_STATE_FILENAME


def _load_sid_state(root: Path) -> dict[str, Any]:
    path = _sid_state_path(root)
    if not path.is_file():
        return {"version": _SID_STATE_VERSION, "next_sid": 1, "songs": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": _SID_STATE_VERSION, "next_sid": 1, "songs": {}}

    songs_raw = data.get("songs") if isinstance(data, dict) else None
    songs_dict = songs_raw if isinstance(songs_raw, dict) else {}

    local_songs = {
        str(k): int(v)
        for k, v in songs_dict.items()
        if isinstance(v, int) and int(v) >= 1
    }
    max_known_local_sid = max(local_songs.values(), default=0)
    next_sid_raw = data.get("next_sid") if isinstance(data, dict) else 1
    next_sid = int(next_sid_raw) if isinstance(next_sid_raw, int) else 1
    next_sid = max(next_sid, max_known_local_sid + 1, 1)
    return {"version": _SID_STATE_VERSION, "next_sid": next_sid, "songs": local_songs}


def _save_sid_state(root: Path, state: dict[str, Any]) -> None:
    path = _sid_state_path(root)
    payload = {
        "version": _SID_STATE_VERSION,
        "next_sid": max(int(state.get("next_sid", 1)), 1),
        "songs": {
            k: int(v)
            for k, v in dict(state.get("songs", {})).items()
            if isinstance(v, int) and int(v) >= 1
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _allocate_sid_map(root: Path, entries: list[Path]) -> dict[str, int]:
    with _SID_STATE_LOCK:
        state = _load_sid_state(root)
        songs = dict(state.get("songs", {}))
        next_sid = int(state.get("next_sid", 1))
        changed = False
        result: dict[str, int] = {}

        for entry in entries:
            song_key = _normalize_song_key(root, entry)
            sid = songs.get(song_key)
            if sid is None:
                sid = next_sid
                songs[song_key] = sid
                next_sid += 1
                changed = True
            result[song_key] = sid

        if changed:
            _save_sid_state(root, {"version": _SID_STATE_VERSION, "next_sid": next_sid, "songs": songs})

    return result


def scan_chart_sources(root_path: str | Path) -> list[dict[str, Any]]:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"路径不存在: {root}")

    parsed: list[ParsedChart] = []
    cid = CHART_ID_HEAD + 1

    song_entries = [
        entry
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower())
        if entry.is_dir() and any(entry.rglob("*.mc"))
    ]
    sid_map = _allocate_sid_map(root, song_entries)

    for entry in song_entries:
        song_key = _normalize_song_key(root, entry)
        sid = SONG_ID_HEAD + sid_map[song_key]
        charts = parse_extracted_chart_dir(entry, sid=sid, cid_start=cid)
        if charts:
            parsed.extend(charts)
            cid += len(charts)

    return [asdict(item) for item in parsed]
