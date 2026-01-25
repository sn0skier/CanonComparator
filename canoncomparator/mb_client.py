from __future__ import annotations

import json
import sqlite3
import time
import random
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


MB_BASE = "https://musicbrainz.org/ws/2"
_MB_MIN_INTERVAL = 1.0
_last_mb_request = 0.0


@dataclass(frozen=True)
class MbRgStats:
    rgid: str
    release_count: int
    mode_track_count: Optional[int]
    histogram: Dict[int, int]          # track_count -> frequency
    fetched_at: float


def build_user_agent(cfg: dict) -> str:
    mb = cfg.get("musicbrainz", {})
    app = mb.get("app_name", "CanComp")
    version = mb.get("version", "0.0.0")
    contact = mb.get("contact", "unknown")
    return f"{app}/{version} ( {contact} )"


def create_mb_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": build_user_agent(cfg),
        "Accept": "application/json",
    })
    return s


def _mb_get(session: requests.Session, path: str, params: dict) -> dict:
    """
    MusicBrainz GET with:
      - global 1 req/sec throttling (via _MB_MIN_INTERVAL / _last_mb_request)
      - retries on transient network errors and 429/5xx responses
      - exponential backoff with small jitter
    """
    global _last_mb_request

    max_retries = 5
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            # --- polite throttling (keep your original behavior) ---
            now = time.time()
            dt = now - _last_mb_request
            if dt < _MB_MIN_INTERVAL:
                time.sleep(_MB_MIN_INTERVAL - dt)

            url = f"{MB_BASE}{path}"
            r = session.get(url, params=params, timeout=60)

            # Update last request time after we actually attempted a request
            _last_mb_request = time.time()

            # Retry on "too many requests" or transient server errors
            if r.status_code in (429, 500, 502, 503, 504):
                # Respect Retry-After if present
                ra = r.headers.get("Retry-After")
                if ra is not None:
                    try:
                        sleep_s = float(ra)
                    except ValueError:
                        sleep_s = 1.0
                else:
                    # Exponential backoff with a little jitter, capped
                    sleep_s = min(30.0, (2 ** attempt)) + random.uniform(0.0, 0.5)

                if attempt < max_retries:
                    print(f"MB retry {attempt+1}/{max_retries} (HTTP {r.status_code}); sleeping {sleep_s:.1f}s")
                    time.sleep(sleep_s)
                    continue

            r.raise_for_status()
            return r.json()

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.SSLError,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            last_exc = e
            if attempt < max_retries:
                sleep_s = min(30.0, (2 ** attempt)) + random.uniform(0.0, 0.5)
                print(f"MB retry {attempt+1}/{max_retries} (network); sleeping {sleep_s:.1f}s")
                time.sleep(sleep_s)
                continue
            raise

    # Defensive: should never reach, but keeps type checkers happy
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("MB request failed unexpectedly without an exception")


def _release_total_tracks(release_obj: dict) -> Optional[int]:
    """
    Total tracks across all media. Uses media[].track-count when present.
    """
    media = release_obj.get("media")
    if not isinstance(media, list) or not media:
        return None

    total = 0
    for m in media:
        tc = m.get("track-count")
        if isinstance(tc, int):
            total += tc
        else:
            # fallback if track-count missing but tracks present
            tracks = m.get("tracks")
            if isinstance(tracks, list):
                total += len(tracks)
            else:
                return None
    return total


def _mode_from_hist(hist: Dict[int, int]) -> Optional[int]:
    if not hist:
        return None
    # Highest frequency; tie-breaker: smallest track count
    return sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _ensure_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rg_cache (
            rgid TEXT PRIMARY KEY,
            fetched_at REAL NOT NULL,
            release_count INTEGER NOT NULL,
            mode_track_count INTEGER,
            histogram_json TEXT NOT NULL
        )
    """)
    conn.commit()


def _read_cache(conn: sqlite3.Connection, rgid: str, max_age_days: float) -> Optional[MbRgStats]:
    row = conn.execute(
        "SELECT rgid, fetched_at, release_count, mode_track_count, histogram_json FROM rg_cache WHERE rgid=?",
        (rgid,)
    ).fetchone()
    if not row:
        return None
    rgid, fetched_at, release_count, mode_track_count, histogram_json = row
    if max_age_days < 0:
        pass
    elif max_age_days == 0:
        return None
    elif (time.time() - fetched_at) > max_age_days * 86400:
        return None
    hist = {int(k): int(v) for k, v in json.loads(histogram_json).items()}
    return MbRgStats(rgid=rgid, fetched_at=fetched_at, release_count=release_count,
                     mode_track_count=mode_track_count, histogram=hist)


def _write_cache(conn: sqlite3.Connection, stats: MbRgStats) -> None:
    conn.execute("""
        INSERT INTO rg_cache (rgid, fetched_at, release_count, mode_track_count, histogram_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(rgid) DO UPDATE SET
            fetched_at=excluded.fetched_at,
            release_count=excluded.release_count,
            mode_track_count=excluded.mode_track_count,
            histogram_json=excluded.histogram_json
    """, (
        stats.rgid,
        stats.fetched_at,
        stats.release_count,
        stats.mode_track_count,
        json.dumps({str(k): v for k, v in stats.histogram.items()}, ensure_ascii=False),
    ))
    conn.commit()


def fetch_rg_stats(
    session: requests.Session,
    cache_path: str | Path,
    rgid: str,
    max_age_days: float = 30.0,
) -> Tuple[Optional[MbRgStats], str]:
    cache_path = Path(cache_path).expanduser()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(cache_path))
    try:
        _ensure_cache(conn)

        row = conn.execute(
            "SELECT rgid, fetched_at, release_count, mode_track_count, histogram_json "
            "FROM rg_cache WHERE rgid=?",
            (rgid,),
        ).fetchone()

        if row:
            _rgid, fetched_at, release_count, mode_track_count, histogram_json = row
            hist = {int(k): int(v) for k, v in json.loads(histogram_json).items()}
            cached_stats = MbRgStats(
                rgid=rgid,
                fetched_at=float(fetched_at),
                release_count=int(release_count),
                mode_track_count=mode_track_count,
                histogram=hist,
            )

            if max_age_days < 0:
                return cached_stats, "cached"
            if max_age_days == 0:
                fetch_reason = "fetched (forced)"
            elif (time.time() - float(fetched_at)) <= max_age_days * 86400:
                return cached_stats, "cached"
            else:
                fetch_reason = "fetched (cache expired)"
        else:
            fetch_reason = "fetched (not in cache)"

        # --- MB fetch (may fail); do NOT crash the whole run ---
        try:
            limit = 100
            offset = 0
            hist: Dict[int, int] = {}
            release_count = 0

            while True:
                data = _mb_get(session, "/release", params={
                    "release-group": rgid,
                    "inc": "media",
                    "fmt": "json",
                    "limit": str(limit),
                    "offset": str(offset),
                })

                releases = data.get("releases", [])
                if not isinstance(releases, list):
                    releases = []

                for rel in releases:
                    release_count += 1
                    tc = _release_total_tracks(rel)
                    if tc is None:
                        continue
                    hist[tc] = hist.get(tc, 0) + 1

                total = data.get("release-count")
                if not isinstance(total, int):
                    break
                offset += limit
                if offset >= total:
                    break

            mode_tc = _mode_from_hist(hist)
            stats = MbRgStats(
                rgid=rgid,
                release_count=release_count,
                mode_track_count=mode_tc,
                histogram=hist,
                fetched_at=time.time(),
            )
            _write_cache(conn, stats)
            return stats, fetch_reason

        except Exception as e:
            # Keep going; CSV row will just have blank MB fields
            return None, f"failed ({type(e).__name__})"

    finally:
        conn.close()
