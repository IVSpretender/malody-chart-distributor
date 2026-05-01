from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


DB_PATH = Path("data") / "malody.db"
SCHEMA_VERSION = 1


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS songs (
            sid INTEGER PRIMARY KEY,
            song_folder_name TEXT NOT NULL,
            path TEXT NOT NULL,
            exist INTEGER NOT NULL,
            promote INTEGER NOT NULL,
            time INTEGER NOT NULL,
            title TEXT,
            artist TEXT,
            title_org TEXT,
            artist_org TEXT,
            bpm REAL,
            length INTEGER,
            cover TEXT,
            background TEXT,
            mode_mask INTEGER,
            UNIQUE(path, song_folder_name)
        );

        CREATE TABLE IF NOT EXISTS charts (
            cid INTEGER PRIMARY KEY,
            sid INTEGER NOT NULL,
            hash TEXT NOT NULL,
            path TEXT NOT NULL,
            exist INTEGER NOT NULL,
            time INTEGER NOT NULL,
            mc_name TEXT NOT NULL,
            version TEXT,
            level INTEGER,
            mode INTEGER,
            uid INTEGER,
            creator TEXT,
            size INTEGER,
            type INTEGER,
            UNIQUE(hash)
        );

        CREATE TABLE IF NOT EXISTS events (
            eid INTEGER PRIMARY KEY,
            event_folder_name TEXT NOT NULL,
            source_root TEXT NOT NULL,
            exist INTEGER NOT NULL,
            song_ids TEXT NOT NULL,
            cover TEXT,
            sponsor TEXT,
            start_date TEXT,
            end_date TEXT,
            active INTEGER,
            UNIQUE(source_root, event_folder_name)
        );

        CREATE TABLE IF NOT EXISTS stats (
            cid INTEGER PRIMARY KEY,
            download_count INTEGER NOT NULL,
            last_download_time INTEGER
        );
        """
    )


def _get_state_map(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT key, value FROM state").fetchall()
    return {str(row["key"]): int(row["value"]) for row in rows}


def _set_state(conn: sqlite3.Connection, key: str, value: int, now: int) -> None:
    conn.execute(
        """
        INSERT INTO state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, int(value), now),
    )


def _ensure_state(conn: sqlite3.Connection, id_heads: dict[str, int], now: int) -> dict[str, int]:
    state = _get_state_map(conn)

    if "schema_version" not in state:
        _set_state(conn, "schema_version", SCHEMA_VERSION, now)
        state["schema_version"] = SCHEMA_VERSION

    if "next_sid" not in state:
        _set_state(conn, "next_sid", int(id_heads.get("sid", 0)) + 1, now)
    if "next_cid" not in state:
        _set_state(conn, "next_cid", int(id_heads.get("cid", 0)) + 1, now)
    if "next_eid" not in state:
        _set_state(conn, "next_eid", int(id_heads.get("eid", 0)) + 1, now)

    return _get_state_map(conn)


def _load_existing_songs(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, int]]:
    rows = conn.execute("SELECT sid, song_folder_name, path, time FROM songs").fetchall()
    existing: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (str(row["path"]), str(row["song_folder_name"]))
        existing[key] = {"sid": int(row["sid"]), "time": int(row["time"])}
    return existing


def _load_existing_charts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    rows = conn.execute("SELECT cid, hash, time FROM charts").fetchall()
    existing: dict[str, dict[str, int]] = {}
    for row in rows:
        existing[str(row["hash"])] = {"cid": int(row["cid"]), "time": int(row["time"])}
    return existing


def _load_existing_events(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    rows = conn.execute("SELECT eid, event_folder_name, source_root FROM events").fetchall()
    existing: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["source_root"]), str(row["event_folder_name"]))
        existing[key] = int(row["eid"])
    return existing


def reload_database(snapshot: dict[str, Any], id_heads: dict[str, int], now: int | None = None) -> None:
    now = int(time.time()) if now is None else int(now)
    songs = [asdict(song) for song in snapshot.get("songs", [])]
    charts = [asdict(chart) for chart in snapshot.get("charts", [])]
    events = [asdict(event) for event in snapshot.get("events", [])]

    with _connect() as conn:
        _init_schema(conn)
        state = _ensure_state(conn, id_heads, now)

        next_sid = int(state.get("next_sid", 1))
        next_cid = int(state.get("next_cid", 1))
        next_eid = int(state.get("next_eid", 1))

        existing_songs = _load_existing_songs(conn)
        existing_charts = _load_existing_charts(conn)
        existing_events = _load_existing_events(conn)

        song_key_to_sid: dict[str, int] = {}
        scanned_song_keys: set[tuple[str, str]] = set()
        scanned_chart_hashes: set[str] = set()
        scanned_event_keys: set[tuple[str, str]] = set()

        for song in songs:
            key = (str(song.get("path", "")), str(song.get("song_folder_name", "")))
            scanned_song_keys.add(key)
            existing = existing_songs.get(key)
            if existing is None:
                sid = next_sid
                next_sid += 1
                time_value = now
            else:
                sid = int(existing["sid"])
                time_value = int(existing["time"])

            song_key_to_sid[str(song.get("song_key", ""))] = sid
            song["sid"] = sid
            song["time"] = time_value
            song["exist"] = 1

        for chart in charts:
            chart_hash = str(chart.get("hash", ""))
            scanned_chart_hashes.add(chart_hash)
            existing = existing_charts.get(chart_hash)
            if existing is None:
                cid = next_cid
                next_cid += 1
                time_value = now
            else:
                cid = int(existing["cid"])
                time_value = int(existing["time"])

            chart["cid"] = cid
            chart["sid"] = int(song_key_to_sid.get(str(chart.get("song_key", "")), 0))
            chart["time"] = time_value
            chart["exist"] = 1

        for event in events:
            key = (str(event.get("source_root", "")), str(event.get("event_folder_name", "")))
            scanned_event_keys.add(key)
            existing = existing_events.get(key)
            if existing is None:
                eid = next_eid
                next_eid += 1
            else:
                eid = int(existing)

            song_ids = [song_key_to_sid.get(song_key, 0) for song_key in event.get("song_keys", [])]
            song_ids = [sid for sid in song_ids if sid > 0]

            event["eid"] = eid
            event["song_ids"] = json.dumps(song_ids, ensure_ascii=False)
            event["exist"] = 1

        for song in songs:
            conn.execute(
                    """
                    INSERT INTO songs (
                        sid, song_folder_name, path, exist, promote, time,
                        title, artist, title_org, artist_org, bpm, length,
                        cover, background, mode_mask
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path, song_folder_name) DO UPDATE SET
                        sid=excluded.sid,
                        exist=excluded.exist,
                        promote=excluded.promote,
                        time=excluded.time,
                        title=excluded.title,
                        artist=excluded.artist,
                        title_org=excluded.title_org,
                        artist_org=excluded.artist_org,
                        bpm=excluded.bpm,
                        length=excluded.length,
                        cover=excluded.cover,
                        background=excluded.background,
                        mode_mask=excluded.mode_mask
                    """,
                (
                        song.get("sid"),
                        song.get("song_folder_name"),
                        song.get("path"),
                        song.get("exist"),
                        song.get("promote"),
                        song.get("time"),
                        song.get("title"),
                        song.get("artist"),
                        song.get("title_org"),
                        song.get("artist_org"),
                        song.get("bpm"),
                        song.get("length"),
                        song.get("cover"),
                        song.get("background"),
                        song.get("mode_mask"),
                    ),
            )

        for chart in charts:
            conn.execute(
                    """
                    INSERT INTO charts (
                        cid, sid, hash, path, exist, time, mc_name,
                        version, level, mode, uid, creator, size, type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hash) DO UPDATE SET
                        cid=excluded.cid,
                        sid=excluded.sid,
                        path=excluded.path,
                        exist=excluded.exist,
                        time=excluded.time,
                        mc_name=excluded.mc_name,
                        version=excluded.version,
                        level=excluded.level,
                        mode=excluded.mode,
                        uid=excluded.uid,
                        creator=excluded.creator,
                        size=excluded.size,
                        type=excluded.type
                    """,
                (
                        chart.get("cid"),
                        chart.get("sid"),
                        chart.get("hash"),
                        chart.get("path"),
                        chart.get("exist"),
                        chart.get("time"),
                        chart.get("mc_name"),
                        chart.get("version"),
                        chart.get("level"),
                        chart.get("mode"),
                        chart.get("uid"),
                        chart.get("creator"),
                        chart.get("size"),
                        chart.get("type"),
                    ),
            )

        for event in events:
            conn.execute(
                    """
                    INSERT INTO events (
                        eid, event_folder_name, source_root, exist, song_ids,
                        cover, sponsor, start_date, end_date, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_root, event_folder_name) DO UPDATE SET
                        eid=excluded.eid,
                        exist=excluded.exist,
                        song_ids=excluded.song_ids,
                        cover=excluded.cover,
                        sponsor=excluded.sponsor,
                        start_date=excluded.start_date,
                        end_date=excluded.end_date,
                        active=excluded.active
                    """,
                (
                        event.get("eid"),
                        event.get("event_folder_name"),
                        event.get("source_root"),
                        event.get("exist"),
                        event.get("song_ids"),
                        event.get("cover"),
                        event.get("sponsor"),
                        event.get("start_date"),
                        event.get("end_date"),
                        1 if event.get("active") else 0,
                    ),
            )

        if existing_songs:
            missing_song_keys = set(existing_songs.keys()) - scanned_song_keys
            for path, folder in missing_song_keys:
                conn.execute(
                    "UPDATE songs SET exist=0 WHERE path=? AND song_folder_name=?",
                    (path, folder),
                )

        if existing_charts:
            missing_chart_hashes = set(existing_charts.keys()) - scanned_chart_hashes
            for chart_hash in missing_chart_hashes:
                conn.execute("UPDATE charts SET exist=0 WHERE hash=?", (chart_hash,))

        if existing_events:
            missing_event_keys = set(existing_events.keys()) - scanned_event_keys
            for source_root, folder in missing_event_keys:
                conn.execute(
                    "UPDATE events SET exist=0 WHERE source_root=? AND event_folder_name=?",
                    (source_root, folder),
                )

        for chart in charts:
            conn.execute(
                """
                INSERT INTO stats (cid, download_count, last_download_time)
                VALUES (?, 0, NULL)
                ON CONFLICT(cid) DO NOTHING
                """,
                (chart.get("cid"),),
            )

        _set_state(conn, "next_sid", next_sid, now)
        _set_state(conn, "next_cid", next_cid, now)
        _set_state(conn, "next_eid", next_eid, now)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def query_all_charts() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.cid, c.sid, c.hash, c.path AS chart_path, c.mc_name, c.version, c.level, c.mode,
                     c.uid, c.creator, c.size, c.type,
                     s.song_folder_name AS source_name, s.path AS song_path, s.promote AS promote,
                   s.title AS title, s.title_org AS titleorg, s.artist AS artist, s.artist_org AS artistorg,
                   s.bpm AS bpm, s.cover AS cover, s.background AS background, s.length AS length, c.time AS chart_time, s.time AS song_time
            FROM charts c
            JOIN songs s ON c.sid = s.sid
            WHERE c.exist = 1
            ORDER BY c.cid ASC
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def query_charts_by_sid(sid: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.cid, c.sid, c.hash, c.path AS chart_path, c.mc_name, c.version, c.level, c.mode,
                     c.uid, c.creator, c.size, c.type,
                     s.song_folder_name AS source_name, s.path AS song_path, s.promote AS promote,
                   s.title AS title, s.title_org AS titleorg, s.artist AS artist, s.artist_org AS artistorg,
                   s.bpm AS bpm, s.cover AS cover, s.background AS background, s.length AS length, c.time AS chart_time, s.time AS song_time
            FROM charts c
            JOIN songs s ON c.sid = s.sid
            WHERE c.exist = 1 AND c.sid = ?
            ORDER BY c.cid ASC
            """,
            (int(sid),),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def query_chart_by_cid(cid: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT c.cid, c.sid, c.hash, c.path AS chart_path, c.mc_name, c.version, c.level, c.mode,
                     c.uid, c.creator, c.size, c.type,
                     s.song_folder_name AS source_name, s.path AS song_path, s.promote AS promote,
                   s.title AS title, s.title_org AS titleorg, s.artist AS artist, s.artist_org AS artistorg,
                   s.bpm AS bpm, s.cover AS cover, s.background AS background, s.length AS length, c.time AS chart_time, s.time AS song_time
            FROM charts c
            JOIN songs s ON c.sid = s.sid
            WHERE c.exist = 1 AND c.cid = ?
            LIMIT 1
            """,
            (int(cid),),
        ).fetchone()
        return _row_to_dict(row) if row else None


def increment_download(cid: int) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE stats SET download_count = download_count + 1, last_download_time = ? WHERE cid = ?",
            (now, int(cid)),
        )


def query_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM events WHERE exist=1 ORDER BY eid DESC").fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            d = _row_to_dict(r)
            try:
                d["song_ids"] = json.loads(d.get("song_ids") or "[]")
            except Exception:
                d["song_ids"] = []
            result.append(d)
        return result


def query_event_by_eid(eid: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM events WHERE eid = ? AND exist=1", (int(eid),)).fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        try:
            d["song_ids"] = json.loads(d.get("song_ids") or "[]")
        except Exception:
            d["song_ids"] = []
        return d


def print_stats() -> None:
    conn = _connect()
    try:
        songs_count = conn.execute("SELECT COUNT(*) FROM songs WHERE exist=1").fetchone()[0]
        charts_count = conn.execute("SELECT COUNT(*) FROM charts WHERE exist=1").fetchone()[0]
        events_count = conn.execute("SELECT COUNT(*) FROM events WHERE exist=1").fetchone()[0]
        stats_count = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]

        state = _get_state_map(conn)
        next_sid = state.get("next_sid", 0)
        next_cid = state.get("next_cid", 0)
        next_eid = state.get("next_eid", 0)

        print("\n[DB] Database Statistics:")
        print(f"  Songs:    {songs_count:5d} rows (next_sid: {next_sid})")
        print(f"  Charts:   {charts_count:5d} rows (next_cid: {next_cid})")
        print(f"  Events:   {events_count:5d} rows (next_eid: {next_eid})")
        print(f"  Stats:    {stats_count:5d} rows")
        print()
    finally:
        conn.close()
