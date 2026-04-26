from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile


@dataclass
class ParsedChart:
    sid: int
    cid: int
    source_name: str
    source_type: str
    source_hash: str
    mc_name: str
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


def compute_file_md5(file_path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    path = Path(file_path)
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


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


def parse_mcz_file(mcz_path: str | Path, sid: int, cid_start: int) -> list[ParsedChart]:
    path = Path(mcz_path)
    source_hash = compute_file_md5(path)
    charts: list[ParsedChart] = []
    cid = cid_start

    with ZipFile(path, "r") as zip_file:
        mc_names = sorted(name for name in zip_file.namelist() if name.lower().endswith(".mc"))
        for mc_name in mc_names:
            mc_bytes = zip_file.read(mc_name)
            mc_data = _parse_mc_content(mc_bytes)
            charts.append(
                _chart_from_mc_data(
                    data=mc_data,
                    sid=sid,
                    cid=cid,
                    source_name=path.name,
                    source_type="mcz",
                    source_hash=source_hash,
                    mc_name=mc_name,
                )
            )
            cid += 1

    return charts


def parse_extracted_chart_dir(directory_path: str | Path, sid: int, cid_start: int) -> list[ParsedChart]:
    base = Path(directory_path)
    source_hash = compute_directory_md5(base)
    mc_files = sorted(base.rglob("*.mc"))
    charts: list[ParsedChart] = []
    cid = cid_start

    for mc_file in mc_files:
        mc_data = _parse_mc_content(mc_file.read_bytes())
        charts.append(
            _chart_from_mc_data(
                data=mc_data,
                sid=sid,
                cid=cid,
                source_name=base.name,
                source_type="folder",
                source_hash=source_hash,
                mc_name=mc_file.relative_to(base).as_posix(),
            )
        )
        cid += 1

    return charts


def scan_chart_sources(root_path: str | Path) -> list[dict[str, Any]]:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"路径不存在: {root}")

    parsed: list[ParsedChart] = []
    sid = 600000
    cid = 600000

    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and entry.suffix.lower() == ".mcz":
            charts = parse_mcz_file(entry, sid=sid, cid_start=cid)
            if charts:
                parsed.extend(charts)
                sid += 1
                cid += len(charts)
            continue

        if entry.is_dir() and any(entry.rglob("*.mc")):
            charts = parse_extracted_chart_dir(entry, sid=sid, cid_start=cid)
            if charts:
                parsed.extend(charts)
                sid += 1
                cid += len(charts)

    return [asdict(item) for item in parsed]
