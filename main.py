from pathlib import Path
import io
import zipfile
import hashlib
import tomllib
import urllib.parse
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse

import db
from parser import reload_database
from config import WELCOME_MESSAGE, PAGE_SIZE, BASE_URL, DOWNLOAD_ROOTS, EVENT_PAGE_SIZE

# repository root (used for producing repo-relative asset paths)
REPO_ROOT = Path(__file__).parent.resolve()


def get_version() -> str:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def refresh_database_on_startup() -> None:
    """Refresh DB on startup so uvicorn --reload can rebuild data after file changes."""
    start = time.time()
    print("[startup] refreshing database via parser.reload_database() ...")
    reload_database()
    print(f"[startup] database refreshed in {time.time() - start:.2f}s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    refresh_database_on_startup()
    yield


app = FastAPI(title="Malody Chart Distributor", version=get_version(), lifespan=lifespan)


def _empty_page(next_value: int = 0) -> dict:
    return {"code": 0, "hasMore": False, "next": next_value, "data": []}


def _paginate(items: list, from_: int = 0, is_event: bool = False) -> tuple[list, bool, int]:
    """通用分页逻辑：返回 (页面数据, 是否有更多, 下一页起点)"""
    start = int(from_ or 0)
    end = start + PAGE_SIZE if not is_event else start + EVENT_PAGE_SIZE
    page = items[start:end]
    has_more = end < len(items)
    return page, has_more, end if has_more else 0


def _apply_cover_urls(items: list[dict]) -> None:
    """为歌曲/事件项应用封面URL（原地修改）"""
    for item in items:
        cover_url = _find_cover_url_for_song(item)
        if cover_url:
            item["cover"] = cover_url
        else:
            item["cover"] = item.get("cover") or ""


def _build_songs_from_charts(charts: list[dict], include_fields: list[str] | None = None) -> dict[int, dict]:
    """从chart列表构建songs字典
    
    Args:
        charts: chart列表
        include_fields: 要包含的额外字段列表，如 ['promote', 'rep_cid']
    """
    songs: dict[int, dict] = {}
    for c in charts:
        sid = int(c["sid"])
        if sid not in songs:
            title = c.get("title") or ""
            artist = c.get("artist") or ""
            titleorg = c.get("titleorg") or title
            artistorg = c.get("artistorg") or artist
            song = {
                "sid": sid,
                "title": title,
                "titleorg": titleorg,
                "artist": artist,
                "artistorg": artistorg,
                "cover": c.get("cover") or "",
                "tag": c.get("tag") or "",
                "charts": [],
                "song_path": c.get("song_path") or None,
            }
            # 添加可选字段
            if include_fields:
                for field in include_fields:
                    if field == "promote":
                        song["promote"] = int(c.get("promote") or 0)
                    elif field == "rep_cid":
                        song["rep_cid"] = c.get("cid")
            songs[sid] = song
        songs[sid]["charts"].append({
            "cid": c["cid"],
            "mc_name": c.get("mc_name"),
            "version": c.get("version"),
            "level": int(c.get("level") or 0),
            "type": c.get("type"),
            "size": c.get("size"),
            "mode": int(c.get("mode") or -1),
            "chart_path": c.get("chart_path") or None,
            "background": c.get("background") or None,
        })
    return songs


def _localized_text(primary: str, alternate: str, use_alternate: bool) -> str:
    if use_alternate and alternate:
        return alternate
    if primary:
        return primary
    return alternate or ""


def _apply_org_titles(items: list[dict], org: int) -> None:
    use_alternate = int(org) == 1
    for item in items:
        item["title"] = _localized_text(item.get("title") or "", item.get("titleorg") or "", use_alternate)
        item["artist"] = _localized_text(item.get("artist") or "", item.get("artistorg") or "", use_alternate)


def _assets_url_for_path(p: Path) -> str | None:
    try:
        rp = p.resolve()
    except Exception:
        return None
    # ensure under allowed roots
    allowed = [r.resolve() for r in DOWNLOAD_ROOTS]
    ok = False
    for root in allowed:
        try:
            if root in rp.parents or rp == root:
                ok = True
                break
        except Exception:
            continue
    if not ok or not rp.exists() or not rp.is_file():
        return None
    # require asset path be under repository root so we return repo-relative paths
    try:
        rel = rp.relative_to(REPO_ROOT)
    except Exception:
        return None
    # use posix style relative path in URL
    rel_posix = rel.as_posix()
    return f"{BASE_URL}/assets/file?path={urllib.parse.quote(rel_posix)}"


def _find_cover_url_for_song(song: dict) -> str:
    # collect candidate names: cover then backgrounds from charts
    candidates: list[str] = []
    cover_name = song.get("cover") or ""
    if cover_name:
        candidates.append(cover_name)
    for ch in song.get("charts", []):
        bg = ch.get("background")
        if bg:
            candidates.append(bg)

    # search in chart folders first then song_path
    for cand in candidates:
        for ch in song.get("charts", []):
            cp = ch.get("chart_path")
            if not cp:
                continue
            p = Path(cp) / cand
            url = _assets_url_for_path(p)
            if url:
                return url
        sp = song.get("song_path")
        if sp:
            p2 = Path(sp) / cand
            url2 = _assets_url_for_path(p2)
            if url2:
                return url2
    return ""


def _find_cover_url_for_event(event: dict) -> str:
    cover_name = event.get("cover") or ""
    if not cover_name:
        return ""

    source_root = event.get("source_root") or ""
    event_folder_name = event.get("event_folder_name") or ""
    if not source_root or not event_folder_name:
        return ""

    return _assets_url_for_path(Path(source_root) / event_folder_name / cover_name) or ""


@app.get("/")
def root() -> dict:
    return {"code": 0, "message": "malody-chart-distributor is running"}


@app.get("/api/store/info")
def store_info() -> dict:
    return {
        "code": 0,
        "api": 202310,
        "min": 202103,
        "welcome": WELCOME_MESSAGE,
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
    charts = db.query_all_charts()
    songs = _build_songs_from_charts(charts, include_fields=["promote", "rep_cid"])

    # parse tag tokens from word: tokens starting with '#'
    raw_word = (word or "").strip()
    tags = [t[1:].lower() for t in raw_word.split() if t.startswith("#")]
    simple_word = " ".join([t for t in raw_word.split() if not t.startswith("#")]).lower()

    def song_matches(s: dict) -> bool:
        # word search in title/artist or their original variants depending on org flag
        if simple_word:
            if int(org) == 1:
                if simple_word not in (s.get("titleorg") or "").lower() and simple_word not in (s.get("artistorg") or "").lower():
                    return False
            else:
                if simple_word not in (s.get("title") or "").lower() and simple_word not in (s.get("artist") or "").lower():
                    return False
        # tag matching: check tag or title contains tag
        for tag in tags:
            if tag.lower() not in (s.get('tag') or "").lower().split():
                return False
        # mode filter: any chart matches mode
        if int(mode) >= 0:
            if not any(int(ch.get("mode", -1)) == int(mode) for ch in s["charts"]):
                return False
        # level range filter
        if lvge or lvle:
            ok = False
            for ch in s["charts"]:
                lvl = int(ch.get("level", 0) or 0)
                if lvl >= int(lvge) and (int(lvle) == 0 or lvl <= int(lvle)):
                    ok = True
                    break
            if not ok:
                return False
        return True

    items = [v for v in songs.values() if song_matches(v)]
    # 最新内容优先
    items.reverse()
    page, has_more, next_val = _paginate(items, from_)
    _apply_org_titles(page, org)
    _apply_cover_urls(page)
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": page}


@app.get("/api/store/promote")
def store_promote(
    org: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    _ = org  # 暂未使用
    charts = db.query_all_charts()
    songs = _build_songs_from_charts(charts, include_fields=["promote"])

    # 仅过滤已推荐的歌曲
    items = [s for s in songs.values() if int(s.get("promote", 0)) == 1]
    if int(mode) >= 0:
        items = [s for s in items if any(int(ch.get("mode", -1)) == int(mode) for ch in s["charts"])]
    # 最新内容优先
    items.reverse()

    page, has_more, next_val = _paginate(items, from_)
    _apply_org_titles(page, org)
    _apply_cover_urls(page)
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": page}


@app.get("/assets/file")
def assets_file(path: str = Query(...)):
    # `path` is expected to be a repo-relative posix path (URL-quoted)
    try:
        rel = urllib.parse.unquote(path)
    except Exception:
        raise HTTPException(status_code=404, detail="invalid path")
    p = (REPO_ROOT / Path(rel)).resolve()
    # ensure file under allowed DOWNLOAD_ROOTS
    allowed = [r.resolve() for r in DOWNLOAD_ROOTS]
    ok = False
    for root in allowed:
        try:
            if root in p.parents or p == root:
                ok = True
                break
        except Exception:
            continue
    if not ok or not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path=p, media_type="image/png")


@app.get("/api/store/friend")
def store_friend(
    org: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    _ = org
    return _empty_page(next_value=from_)


@app.get("/api/store/charts")
def store_charts(
    sid: int,
    beta: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
    promote: int = Query(default=0),
) -> dict:
    charts = db.query_charts_by_sid(sid)
    # optional mode filter
    if mode is not None and int(mode) >= 0:
        charts = [c for c in charts if int(c.get("mode", -1)) == int(mode)]
    return {"code": 0, "hasMore": False, "next": 0, "data": charts}


@app.get("/api/store/query")
def store_query(
    sid: int | None = Query(default=None),
    cid: int | None = Query(default=None),
    org: int = Query(default=0),
) -> dict:
    if cid is not None:
        chart = db.query_chart_by_cid(cid)
        if not chart:
            raise HTTPException(status_code=404, detail="cid not found")
        return {"code": 0, "data": chart}
    if sid is not None:
        charts = db.query_charts_by_sid(sid)
        return {"code": 0, "data": charts}
    return {"code": 0, "data": []}


@app.get("/api/store/download")
def store_download(cid: int) -> dict:
    chart = db.query_chart_by_cid(cid)
    if not chart:
        return {"code": -2, "items": [], "sid": 0, "cid": cid}
    chart_path = Path(chart.get("chart_path") or chart.get("chart_path"))
    if not chart_path.exists():
        # try relative to repo
        chart_path = Path.cwd() / chart.get("chart_path")
    if not chart_path.exists():
        return {"code": 0, "items": [], "sid": chart.get("sid"), "cid": cid, "uid": 0}

    items = []
    for entry in sorted(chart_path.iterdir()):
        if entry.is_file():
            size = entry.stat().st_size
            md5 = _file_md5(entry)
            url = f"{BASE_URL}/download/cid/{cid}/file?name={urllib.parse.quote(entry.name)}"
            items.append({"name": entry.name, "size": size, "hash": md5, "url": url, "file": url})
    return {"code": 0, "items": items, "sid": chart.get("sid"), "cid": cid, "uid": 0}


def _file_md5(path: Path) -> str:
    m = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            m.update(chunk)
    return m.hexdigest()


@app.get("/download/cid/{cid}")
def download_by_cid(cid: int):
    chart = db.query_chart_by_cid(cid)
    if not chart:
        raise HTTPException(status_code=404, detail="cid not found")
    chart_path = Path(chart.get("chart_path") or chart.get("chart_path"))
    if not chart_path.exists():
        chart_path = Path.cwd() / chart.get("chart_path")
    if not chart_path.exists():
        raise HTTPException(status_code=404, detail="chart folder not found")

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(chart_path.rglob("*")):
            arcname = p.relative_to(chart_path)
            if p.is_file():
                z.write(p, arcname.as_posix())
    bio.seek(0)
    db.increment_download(cid)
    return StreamingResponse(bio, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=chart_{cid}.zip"})


@app.get("/download/cid/{cid}/file")
def download_entry_by_name(cid: int, name: str = Query(...)):
    chart = db.query_chart_by_cid(cid)
    if not chart:
        raise HTTPException(status_code=404, detail="cid not found")
    chart_path = Path(chart.get("chart_path") or chart.get("chart_path"))
    if not chart_path.exists():
        chart_path = Path.cwd() / chart.get("chart_path")
    target = chart_path / name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    db.increment_download(cid)
    return FileResponse(path=target, filename=target.name, media_type="application/octet-stream")


@app.get("/api/store/events")
def store_events(
    active: int = Query(default=1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    events = db.query_events()
    if int(active) == 1:
        events = [e for e in events if int(e.get("active", 0)) == 1]
    # 最新活动优先
    events.reverse()
    page, has_more, next_val = _paginate(events, from_)

    data: list[dict] = []
    for ev in page:
        data.append({
            "eid": int(ev.get("eid") or 0),
            "name": ev.get("event_folder_name") or "",
            "sponsor": ev.get("sponsor") or "",
            "start": ev.get("start_date") or ev.get("start") or "",
            "end": ev.get("end_date") or ev.get("end") or "",
            "active": int(ev.get("active") or 0) == 1,
            "cover": _find_cover_url_for_event(ev),
        })

    return {"code": 0, "hasMore": has_more, "next": next_val, "data": data}


@app.get("/api/store/event")
def store_event(
    eid: int,
    org: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    event = db.query_event_by_eid(eid)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")

    song_ids = event.get("song_ids") or []
    data: list[dict] = []
    
    for sid in song_ids:
        charts = db.query_charts_by_sid(sid)
        # 从第一条chart获取歌曲级别的字段
        title = charts[0].get("title") if charts else ""
        titleorg = (charts[0].get("titleorg") or title) if charts else title
        artist = charts[0].get("artist") if charts else ""
        artistorg = (charts[0].get("artistorg") or artist) if charts else artist
        cover = charts[0].get("cover") if charts else ""
        
        for c in charts:
            item = {
                "sid": int(c.get("sid") or sid),
                "cid": int(c.get("cid") or 0),
                "uid": int(c.get("uid") or 0),
                "creator": c.get("creator") or "",
                "title": titleorg if int(org) == 1 else title,
                "artist": artistorg if int(org) == 1 else artist,
                "titleorg": titleorg,
                "artistorg": artistorg,
                "version": c.get("version") or "",
                "level": int(c.get("level") or 0),
                "length": int(c.get("length") or 0),
                "type": int(c.get("type") or 0),
                "cover": cover,  # 初始值用于查找
                "time": int(c.get("chart_time") or c.get("song_time") or 0),
                "mode": int(c.get("mode") or -1),
                "song_path": c.get("song_path"),
                "charts": [{
                    "chart_path": c.get("chart_path"),
                    "background": c.get("background"),
                }],
            }
            data.append(item)
    
    # 最新内容优先
    data.reverse()

    # 分页处理
    page, has_more, next_val = _paginate(data, from_, is_event=True)
    _apply_org_titles(page, org)
    # 应用覆盖URL
    _apply_cover_urls(page)
    # 清理临时字段
    for item in page:
        item.pop("song_path", None)
        item.pop("charts", None)
    
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": page}


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
    return {"code": 0, "data": {"name": "", "url": "", "id": sid}}


