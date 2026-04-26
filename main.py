from typing import Any
from urllib.parse import quote
from io import BytesIO
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from parser import scan_chart_sources

app = FastAPI(title="Malody Chart Distributor", version="0.1.0")
PAGE_SIZE = 20
TEST_BASE_URL = "http://localhost:8000"
SCAN_ROOTS = (Path("charts"), Path(".local/example_chart"))


def _empty_page(next_value: int = 0) -> dict:
    return {"code": 0, "hasMore": False, "next": next_value, "data": []}


def _paginate(items: list[dict[str, Any]], start: int) -> dict[str, Any]:
    safe_start = max(start, 0)
    page_items = items[safe_start : safe_start + PAGE_SIZE]
    next_value = safe_start + len(page_items)
    has_more = next_value < len(items)
    return {
        "code": 0,
        "hasMore": has_more,
        "next": next_value if has_more else 0,
        "data": page_items,
    }


def _load_chart_catalog() -> list[dict[str, Any]]:
    try:
        charts = scan_chart_sources(SCAN_ROOTS[0])
    except FileNotFoundError:
        charts = []

    if charts:
        return charts

    try:
        return scan_chart_sources(SCAN_ROOTS[1])
    except FileNotFoundError:
        return []


def _find_chart_by_cid(cid: int) -> dict[str, Any] | None:
    return next((c for c in _load_chart_catalog() if int(c.get("cid", 0)) == cid), None)


def _resolve_source_path(chart: dict[str, Any]) -> Path | None:
    source_name = str(chart.get("source_name") or "")
    source_type = str(chart.get("source_type") or "")
    if not source_name:
        return None

    for root in SCAN_ROOTS:
        candidate = root / source_name
        if source_type == "mcz" and candidate.is_file():
            return candidate
        if source_type == "folder" and candidate.is_dir():
            return candidate
    return None


def _chart_subdir(chart: dict[str, Any]) -> str:
    subdir = str(chart.get("chart_subdir") or "").replace("\\", "/").strip("/")
    return subdir


def _resolve_chart_folder_root(chart: dict[str, Any], source_path: Path) -> Path:
    subdir = _chart_subdir(chart)
    if not subdir:
        return source_path
    return source_path / Path(subdir)


def _build_download_filename(chart: dict[str, Any]) -> str:
    source_name = str(chart.get("source_name") or "")
    source_type = str(chart.get("source_type") or "")
    if source_type == "mcz":
        return source_name
    if source_type == "folder":
        return f"{source_name}.mcz"
    return source_name or "chart.mcz"


def _file_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def _bytes_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _build_store_download_items(cid: int, chart: dict[str, Any]) -> list[dict[str, str]]:
    source_path = _resolve_source_path(chart)
    if source_path is None:
        return []

    source_type = str(chart.get("source_type") or "")
    items: list[dict[str, str]] = []

    if source_type == "mcz":
        with ZipFile(source_path, "r") as zf:
            for info in sorted(zf.infolist(), key=lambda x: x.filename.lower()):
                if info.is_dir():
                    continue
                name = info.filename
                content = zf.read(name)
                item_hash = _bytes_md5(content)
                file_url = f"{TEST_BASE_URL}/download/cid/{cid}/file?name={quote(name)}"
                items.append({"name": name, "hash": item_hash, "file": file_url})
        return items

    if source_type == "folder":
        root = _resolve_chart_folder_root(chart, source_path).resolve()
        if not root.is_dir():
            return []
        for file_path in sorted(p for p in root.rglob("*") if p.is_file()):
            name = file_path.relative_to(root).as_posix()
            item_hash = _file_md5(file_path)
            file_url = f"{TEST_BASE_URL}/download/cid/{cid}/file?name={quote(name)}"
            items.append({"name": name, "hash": item_hash, "file": file_url})
        return items

    return items


def _zip_folder_bytes(folder_path: Path) -> bytes:
    mem = BytesIO()
    with ZipFile(mem, mode="w", compression=ZIP_DEFLATED) as zf:
        for file_path in sorted(p for p in folder_path.rglob("*") if p.is_file()):
            arcname = file_path.relative_to(folder_path).as_posix()
            zf.write(file_path, arcname)
    mem.seek(0)
    return mem.read()


def _mode_bitmask(modes: list[int]) -> int:
    bitmask = 0
    for mode in modes:
        if 0 <= mode <= 30:
            bitmask |= 1 << mode
    return bitmask


def _asset_url(chart: dict[str, Any], asset_name: str) -> str:
    if not asset_name:
        return ""
    source_name = str(chart.get("source_name", ""))
    if not source_name:
        return ""
    source_type = str(chart.get("source_type") or "")

    if source_type == "folder":
        path_parts = [quote(source_name)]
        subdir = _chart_subdir(chart)
        if subdir:
            path_parts.extend(quote(part) for part in subdir.split("/") if part)
        path_parts.extend(quote(part) for part in asset_name.replace("\\", "/").split("/") if part)
        return f"{TEST_BASE_URL}/download/{'/'.join(path_parts)}"

    if source_type == "mcz":
        return f"{TEST_BASE_URL}/download/{quote(source_name)}?asset={quote(asset_name)}"

    return f"{TEST_BASE_URL}/download/{quote(source_name)}/{quote(asset_name)}"


def _resolve_cover_url(chart: dict[str, Any]) -> str:
    if str(chart.get("source_type") or "") == "mcz":
        return ""

    cover_name = str(chart.get("cover") or "")
    background_name = str(chart.get("background") or "")

    cover_url = _asset_url(chart, cover_name)
    if cover_url:
        return cover_url

    background_url = _asset_url(chart, background_name)
    if background_url:
        return background_url

    return ""


def _build_song_list(charts: list[dict[str, Any]], org: int) -> list[dict[str, Any]]:
    songs: dict[int, dict[str, Any]] = {}
    song_modes: dict[int, list[int]] = {}

    for chart in charts:
        sid = int(chart.get("sid", 0))
        if sid not in songs:
            title = chart.get("titleorg") if org else chart.get("title")
            artist = chart.get("artistorg") if org else chart.get("artist")
            songs[sid] = {
                "sid": sid,
                "cover": _resolve_cover_url(chart),
                "length": 0,
                "bpm": float(chart.get("bpm", 0) or 0),
                "title": title or chart.get("title", ""),
                "artist": artist or chart.get("artist", ""),
                "mode": 0,
                "time": 0,
                "titleorg": chart.get("titleorg", ""),
                "artistorg": chart.get("artistorg", ""),
                "background": chart.get("background", ""),
            }
            song_modes[sid] = []
        song_modes[sid].append(int(chart.get("mode", -1)))

    for sid, song in songs.items():
        song["mode"] = _mode_bitmask(song_modes.get(sid, []))

    return [songs[sid] for sid in sorted(songs)]


def _parse_level(version: str) -> int:
    digits = "".join(ch for ch in version if ch.isdigit())
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


@app.get("/")
def root() -> dict:
    return {"code": 0, "message": "malody-chart-distributor is running"}


@app.get("/api/store/info")
def store_info() -> dict:
    return {
        "code": 0,
        "api": 202310,
        "min": 202103,
        "welcome": "Welcome to my personal Store!",
    }


@app.get("/api/store/list")
def store_list(
    word: str = Query(default=""),
    org: int = Query(default=0),
    mode: int = Query(default=-1),
    lvge: int = Query(default=0),
    lvle: int = Query(default=0),
    beta: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    _ = beta
    charts = _load_chart_catalog()
    songs = _build_song_list(charts, org=org)

    if word:
        keyword = word.lower()
        songs = [
            s
            for s in songs
            if keyword in str(s.get("title", "")).lower()
            or keyword in str(s.get("artist", "")).lower()
            or keyword in str(s.get("titleorg", "")).lower()
            or keyword in str(s.get("artistorg", "")).lower()
        ]

    if mode >= 0:
        songs = [s for s in songs if int(s.get("mode", 0)) & (1 << mode)]

    if lvge > 0 or lvle > 0:
        sid_to_levels: dict[int, list[int]] = {}
        for chart in charts:
            sid = int(chart.get("sid", 0))
            sid_to_levels.setdefault(sid, []).append(_parse_level(str(chart.get("version", ""))))

        filtered_songs: list[dict[str, Any]] = []
        for song in songs:
            levels = sid_to_levels.get(int(song["sid"]), [0])
            level = max(levels)
            if lvge > 0 and level < lvge:
                continue
            if lvle > 0 and level > lvle:
                continue
            filtered_songs.append(song)
        songs = filtered_songs

    return _paginate(songs, from_)


@app.get("/api/store/promote")
def store_promote(
    org: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    charts = _load_chart_catalog()
    songs = _build_song_list(charts, org=org)
    if mode >= 0:
        songs = [s for s in songs if int(s.get("mode", 0)) & (1 << mode)]
    return _paginate(songs, from_)


@app.get("/api/store/friend")
def store_friend(
    org: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    charts = _load_chart_catalog()
    songs = _build_song_list(charts, org=org)
    return _paginate(songs, from_)


@app.get("/api/store/charts")
def store_charts(
    sid: int,
    beta: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
    promote: int = Query(default=0),
) -> dict:
    _ = (beta, promote)
    charts = [c for c in _load_chart_catalog() if int(c.get("sid", 0)) == sid]
    if mode >= 0:
        charts = [c for c in charts if int(c.get("mode", -1)) == mode]

    payload = [
        {
            "cid": int(c.get("cid", 0)),
            "uid": 0,
            "creator": c.get("creator", ""),
            "version": c.get("version", ""),
            "level": _parse_level(str(c.get("version", ""))),
            "length": 0,
            "type": 2,
            "size": 0,
            "mode": int(c.get("mode", -1)),
            "title": c.get("title", ""),
            "titleorg": c.get("titleorg", ""),
            "artist": c.get("artist", ""),
            "artistorg": c.get("artistorg", ""),
            "free": int(c.get("free", 0)),
            "cover": _resolve_cover_url(c),
            "background": c.get("background", ""),
        }
        for c in charts
    ]
    payload.sort(key=lambda item: item["cid"])
    return _paginate(payload, from_)


@app.get("/api/store/query")
def store_query(
    sid: int | None = Query(default=None),
    cid: int | None = Query(default=None),
    org: int = Query(default=0),
) -> dict:
    charts = _load_chart_catalog()

    target_sid = sid
    if target_sid is None and cid is not None:
        chart = next((c for c in charts if int(c.get("cid", 0)) == cid), None)
        if chart is None:
            return _empty_page(next_value=0)
        target_sid = int(chart.get("sid", 0))

    if target_sid is None:
        return {"code": -1, "hasMore": False, "next": 0, "data": []}

    songs = [s for s in _build_song_list(charts, org=org) if int(s.get("sid", 0)) == target_sid]
    return {"code": 0, "hasMore": False, "next": 0, "data": songs}


@app.get("/api/store/download")
def store_download(cid: int) -> dict:
    chart = _find_chart_by_cid(cid)
    if chart is None:
        return {"code": -2, "items": [], "sid": 0, "cid": cid}

    items = _build_store_download_items(cid, chart)
    return {
        "code": 0,
        "items": items,
        "sid": int(chart.get("sid", 0)),
        "cid": int(chart.get("cid", cid)),
        "uid": 0,
    }


def _download_by_cid_response(cid: int):
    chart = _find_chart_by_cid(cid)
    if chart is None:
        raise HTTPException(status_code=404, detail="chart not found")

    source_path = _resolve_source_path(chart)
    if source_path is None:
        raise HTTPException(status_code=404, detail="chart source file not found")

    filename = _build_download_filename(chart)
    source_type = str(chart.get("source_type") or "")

    if source_type == "mcz":
        return FileResponse(
            path=source_path,
            media_type="application/octet-stream",
            filename=filename,
        )

    if source_type == "folder":
        zip_bytes = _zip_folder_bytes(source_path)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(iter([zip_bytes]), media_type="application/octet-stream", headers=headers)

    raise HTTPException(status_code=400, detail="unsupported chart source type")


@app.get("/download/cid/{cid}")
def download_by_cid(cid: int):
    return _download_by_cid_response(cid)


@app.get("/download/cid/{cid}/file")
def download_entry_by_name(cid: int, name: str = Query(...)):
    chart = _find_chart_by_cid(cid)
    if chart is None:
        raise HTTPException(status_code=404, detail="chart not found")

    source_path = _resolve_source_path(chart)
    if source_path is None:
        raise HTTPException(status_code=404, detail="chart source file not found")

    source_type = str(chart.get("source_type") or "")
    download_name = Path(name).name or "file.bin"

    if source_type == "mcz":
        with ZipFile(source_path, "r") as zf:
            try:
                info = zf.getinfo(name)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="entry not found") from exc
            if info.is_dir():
                raise HTTPException(status_code=404, detail="entry is a directory")
            content = zf.read(name)

        headers = {"Content-Disposition": f'attachment; filename="{download_name}"'}
        return StreamingResponse(iter([content]), media_type="application/octet-stream", headers=headers)

    if source_type == "folder":
        root = _resolve_chart_folder_root(chart, source_path).resolve()
        if not root.is_dir():
            raise HTTPException(status_code=404, detail="chart folder not found")
        target = (root / name).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid file name") from exc

        if not target.is_file():
            raise HTTPException(status_code=404, detail="entry not found")

        return FileResponse(
            path=target,
            media_type="application/octet-stream",
            filename=download_name,
        )

    raise HTTPException(status_code=400, detail="unsupported chart source type")


@app.get("/api/store/events")
def store_events(
    active: int = Query(default=1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    _ = active
    return _empty_page(next_value=from_)


@app.get("/api/store/event")
def store_event(
    eid: int,
    org: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    _ = (eid, org)
    return _empty_page(next_value=from_)


@app.post("/api/store/upload/sign")
def store_upload_sign(
    sid: int,
    cid: int,
    name: str = Query(default=""),
    hash: str = Query(default=""),
) -> dict:
    _ = (sid, cid, name, hash)
    return {"code": 0, "errorIndex": -1, "errorMsg": "", "host": "", "meta": []}


@app.post("/api/store/upload/finish")
def store_upload_finish(
    sid: int,
    cid: int,
    name: str = Query(default=""),
    hash: str = Query(default=""),
    size: int = Query(default=0),
    main: str = Query(default=""),
    title: str = Query(default=""),
    artit: str = Query(default=""),
    orgt: str = Query(default=""),
    orga: str = Query(default=""),
    version: str = Query(default=""),
    mode: int = Query(default=0),
    length: int = Query(default=0),
    bpm: float = Query(default=0),
) -> dict:
    _ = (
        sid,
        cid,
        name,
        hash,
        size,
        main,
        title,
        artit,
        orgt,
        orga,
        version,
        mode,
        length,
        bpm,
    )
    return {"code": 0}


@app.get("/api/Skin/list")
def skin_list(
    plat: int = Query(default=0),
    mode: int = Query(default=-1),
    word: str = Query(default=""),
    from_: int = Query(default=0, alias="from"),
    v: int = Query(default=0),
) -> dict:
    _ = (plat, mode, word, v)
    return _empty_page(next_value=from_)


@app.post("/api/skin/buy")
def skin_buy(uid: int = Query(default=0), sid: int = Query(default=0)) -> dict:
    _ = uid
    return {
        "code": 0,
        "data": {
            "name": "",
            "url": "",
            "id": sid,
        },
    }


@app.get("/dev/parser/scan")
def dev_parser_scan(path: str = Query(default=".local/example_chart")) -> dict:
    try:
        charts = scan_chart_sources(path)
    except FileNotFoundError as exc:
        return {"code": -1, "error": str(exc), "data": []}
    except Exception as exc:  # pragma: no cover
        return {"code": -2, "error": str(exc), "data": []}

    return {"code": 0, "count": len(charts), "data": charts}


app.mount("/download", StaticFiles(directory="charts", check_dir=False), name="download")
