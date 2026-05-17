from pathlib import Path
import io
import random
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
from config import WELCOME_MESSAGE, PAGE_SIZE, DAILY_RECOMMEND_NUM, BASE_URL, DOWNLOAD_ROOTS, EVENT_PAGE_SIZE

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
                "background": c.get("background") or "",
                "song_folder_name": c.get("source_name") or "",
                "tag": c.get("tag") or "",
                "length": int(c.get("length") or 0),
                "bpm": float(c.get("bpm") or 0),
                "time": int(c.get("song_time") or c.get("chart_time") or 0),
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


def _song_mode_mask(song: dict) -> int:
    mode_mask = 0
    for chart in song.get("charts", []):
        mode = int(chart.get("mode") or -1)
        if 0 <= mode <= 30:
            mode_mask |= 1 << mode
    return mode_mask


def _song_response(song: dict) -> dict:
    return {
        "sid": int(song.get("sid") or 0),
        "cover": song.get("cover") or "",
        "length": int(song.get("length") or 0),
        "bpm": float(song.get("bpm") or 0),
        "title": song.get("title") or "",
        "artist": song.get("artist") or "",
        "mode": _song_mode_mask(song),
        "time": int(song.get("time") or 0),
    }


def _chart_response(chart: dict) -> dict:
    return {
        "cid": int(chart.get("cid") or 0),
        "uid": int(chart.get("uid") or 0),
        "creator": chart.get("creator") or "",
        "version": chart.get("version") or "",
        "level": int(chart.get("level") or 0),
        "length": int(chart.get("length") or 0),
        "type": int(chart.get("type") or 0),
        "size": int(chart.get("size") or 0),
        "mode": int(chart.get("mode") or -1),
    }


def _event_chart_response(chart: dict, org: int) -> dict:
    return {
        "sid": int(chart.get("sid") or 0),
        "cid": int(chart.get("cid") or 0),
        "uid": int(chart.get("uid") or 0),
        "creator": chart.get("creator") or "",
        "title": chart.get("title") or "",
        "artist": chart.get("artist") or "",
        "version": chart.get("version") or "",
        "level": int(chart.get("level") or 0),
        "length": int(chart.get("length") or 0),
        "type": int(chart.get("type") or 0),
        "cover": chart.get("cover") or "",
        "time": int(chart.get("time") or 0),
        "mode": int(chart.get("mode") or -1),
    }


def _assets_url_for_relpath(rel_path: str) -> str:
    if not rel_path:
        return ""
    return f"{BASE_URL}/assets/file?path={urllib.parse.quote(rel_path)}"


def _find_cover_url_for_song(song: dict) -> str:
    for rel_path in (song.get("cover") or "", song.get("background") or ""):
        url = _assets_url_for_relpath(rel_path)
        if url:
            return url
    return ""


def _find_cover_url_for_event(event: dict) -> str:
    cover_name = event.get("cover") or ""
    if not cover_name:
        return ""

    source_root = event.get("source_root") or ""
    event_folder_name = event.get("event_folder_name") or ""
    if not source_root or not event_folder_name:
        return ""

    return _assets_url_for_relpath(str(Path(source_root) / event_folder_name / cover_name))


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
    simple_words = [t.lower() for t in raw_word.split() if not t.startswith("#")]

    def song_matches(s: dict) -> bool:
        # all simple words must match in title/artist/titleorg/artistorg
        for simple_word in simple_words:
            if simple_word not in (s.get("title") or "").lower() and simple_word not in (s.get("titleorg") or "").lower() \
            and simple_word not in (s.get("artist") or "").lower() and simple_word not in (s.get("artistorg") or "").lower():
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
    page, has_more, next_val = _paginate(items, from_)
    _apply_org_titles(page, org)
    _apply_cover_urls(page)
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": [_song_response(item) for item in page]}


@app.get("/api/store/promote")
def store_promote(
    org: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    charts = db.query_all_charts()
    songs = _build_songs_from_charts(charts, include_fields=["promote"])

    # 仅过滤已推荐的歌曲
    items = [s for s in songs.values() if int(s.get("promote", 0)) == 1]
    if int(mode) >= 0:
        items = [s for s in items if any(int(ch.get("mode", -1)) == int(mode) for ch in s["charts"])]

    page, has_more, next_val = _paginate(items, from_)
    _apply_org_titles(page, org)
    _apply_cover_urls(page)
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": [_song_response(item) for item in page]}


@app.get("/api/store/choice")
def store_choice(
    org: int = Query(default=0),
) -> dict:
    charts = db.query_all_charts()
    songs = _build_songs_from_charts(charts, include_fields=["promote", "rep_cid"])

    items = list(songs.values())
    recommend_num = max(0, int(DAILY_RECOMMEND_NUM))
    if recommend_num > 0 and items:
        items = random.sample(items, min(recommend_num, len(items)))
    else:
        items = []

    _apply_org_titles(items, org)
    _apply_cover_urls(items)
    return {"code": 0, "hasMore": False, "next": 0, "data": [_song_response(item) for item in items]}


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
    return FileResponse(path=p)


@app.get("/api/store/friend")
def store_friend(
    org: int = Query(default=0),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    return _empty_page(next_value=from_)


@app.get("/api/store/charts")
def store_charts(
    sid: int,
    beta: int = Query(default=0),
    mode: int = Query(default=-1),
    from_: int = Query(default=0, alias="from"),
    promote: int = Query(default=0), # ignored temporarily, as promote is now a song-level field and this endpoint is chart-level. Can consider adding promote filter in the future if needed.
) -> dict:
    charts = db.query_charts_by_sid(sid)
    # default only returns stable charts, beta=1 includes non-stable charts
    if int(beta) == 0:
        charts = [c for c in charts if int(c.get("type") or 0) == 2]

    # optional mode filter
    if mode is not None and int(mode) >= 0:
        charts = [c for c in charts if int(c.get("mode", -1)) == int(mode)]

    page, has_more, next_val = _paginate(charts, from_)
    data = [_chart_response(c) for c in page]
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": data}


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
        charts = db.query_charts_by_sid(int(chart.get("sid") or 0))
        songs = _build_songs_from_charts(charts)
        song = songs.get(int(chart.get("sid") or 0))
        if not song:
            return {"code": 0, "data": []}
        _apply_org_titles([song], org)
        _apply_cover_urls([song])
        return {"code": 0, "data": [_song_response(song)]}
    if sid is not None:
        charts = db.query_charts_by_sid(sid)
        songs = _build_songs_from_charts(charts)
        items = list(songs.values())
        _apply_org_titles(items, org)
        _apply_cover_urls(items)
        return {"code": 0, "data": [_song_response(item) for item in items]}
    return {"code": 0, "data": []}


@app.get("/api/store/download")
def store_download(cid: int) -> dict:
    chart = db.query_chart_by_cid(cid)
    if not chart:
        return {"code": -2, "items": [], "sid": 0, "cid": cid}
    chart_path = Path(chart.get("chart_path", ''))
    if not chart_path.exists():
        # try relative to repo
        chart_path = Path.cwd() / chart.get("chart_path", '')
    if not chart_path.exists():
        return {"code": 0, "items": [], "sid": chart.get("sid"), "cid": cid, "uid": 0}

    db.increment_download(cid)

    main_mc_name = (chart.get("mc_name") or "").lower()
    items = []
    for entry in sorted(chart_path.rglob("*")):
        if entry.is_file():
            if entry.suffix.lower() in {".mc_"}: # 跳过这些文件
                continue
            rel_name = entry.relative_to(chart_path).as_posix()
            is_mc_file = entry.suffix.lower() == ".mc"
            if is_mc_file and rel_name.lower() != main_mc_name:
                continue

            md5 = _file_md5(entry)
            url = _assets_url_for_relpath((Path(chart.get("chart_path", "")) / Path(rel_name)).as_posix())
            items.append({"name": rel_name, "hash": md5, "file": url})
    return {"code": 0, "items": items, "sid": chart.get("sid"), "cid": cid}


def _file_md5(path: Path) -> str:
    m = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            m.update(chunk)
    return m.hexdigest()


@app.get("/api/store/events")
def store_events(
    active: int = Query(default=1),
    from_: int = Query(default=0, alias="from"),
) -> dict:
    events = db.query_events()
    if int(active) == 1:
        events = [e for e in events if int(e.get("active", 0)) == 1]
    # 最新活动优先，已在数据库查询代码中实现
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

    charts = db.query_charts_by_sids(song_ids)
    charts_by_sid: dict[int, list[dict]] = {}
    for chart in charts:
        charts_by_sid.setdefault(int(chart.get("sid") or 0), []).append(chart)

    for sid in song_ids:
        sid_charts = charts_by_sid.get(int(sid), [])
        if not sid_charts:
            continue

        first_chart = sid_charts[0]
        title = first_chart.get("title") or ""
        titleorg = first_chart.get("titleorg") or title
        artist = first_chart.get("artist") or ""
        artistorg = first_chart.get("artistorg") or artist
        cover = first_chart.get("cover") or first_chart.get("background") or ""

        for c in sid_charts:
            data.append({
                "sid": int(c.get("sid") or sid),
                "cid": int(c.get("cid") or 0),
                "uid": int(c.get("uid") or 0),
                "creator": c.get("creator") or "",
                "title": titleorg if int(org) == 1 else title,
                "artist": artistorg if int(org) == 1 else artist,
                "version": c.get("version") or "",
                "level": int(c.get("level") or 0),
                "length": int(c.get("length") or 0),
                "type": int(c.get("type") or 0),
                "cover": cover,
                "time": int(c.get("chart_time") or c.get("song_time") or 0),
                "mode": int(c.get("mode") or -1),
            })
    

    # 分页处理
    page, has_more, next_val = _paginate(data, from_, is_event=True)
    _apply_org_titles(page, org)
    _apply_cover_urls(page)
    return {"code": 0, "hasMore": has_more, "next": next_val, "data": [_event_chart_response(item, org) for item in page]}


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


