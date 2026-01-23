from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from canoncomparator.types import LibraryItem


class LidarrError(RuntimeError):
    pass


def _lidarr_get(session: requests.Session, base_url: str, path: str, params: Optional[dict] = None):
    url = f"{base_url.rstrip('/')}{path}"
    r = session.get(url, params=params, timeout=60)
    if r.status_code >= 400:
        # Lidarr often returns JSON with message/content; include it in the exception
        try:
            payload = r.json()
        except Exception:
            payload = r.text
        raise LidarrError(f"GET {url} failed: {r.status_code} {payload}")
    return r.json()


def fetch_library_items(
    lidarr_url: str,
    api_key: str,
    limit_albums: Optional[int] = None,
    include_unmapped: bool = False,
) -> List[LibraryItem]:
    """
    Returns LibraryItem list aggregated by MusicBrainz Release Group MBID (RGID).

    owned_track_count = number of Lidarr trackfiles mapped to that RGID.

    Note:
    - Your Lidarr requires trackfile filters, so we fetch trackfiles per albumId.
    - RGID source is AlbumResource.foreignAlbumId (what you validated in PS).
    - Unmapped trackfiles can't be assigned an RGID, so they are ignored unless you later
      want a separate report (include_unmapped here is kept for future expansion).
    """
    session = requests.Session()
    session.headers.update({"X-Api-Key": api_key})

    # 1) Fetch all albums once
    albums = _lidarr_get(session, lidarr_url, "/api/v1/album")
    if not isinstance(albums, list):
        raise LidarrError(f"Unexpected /album response type: {type(albums)}")

    # Build albumId -> (rgid, artistName, title)
    album_map: Dict[int, Tuple[Optional[str], Optional[str], Optional[str]]] = {}
    albums_with_files: List[dict] = []
    for a in albums:
        album_id = a.get("id")
        rgid = a.get("foreignAlbumId")  # DB RGID (what you want)
        title = a.get("title")
        artist = a.get("artist", {}).get("artistName") if isinstance(a.get("artist"), dict) else None
        album_map[album_id] = (rgid, artist, title)

        stats = a.get("statistics") or {}
        tcount = stats.get("trackFileCount") or 0
        if isinstance(tcount, int) and tcount > 0:
            albums_with_files.append(a)

    if limit_albums is not None:
        albums_with_files = albums_with_files[:limit_albums]

    # 2) For each album with files, fetch trackfiles (filtered by albumId)
    # Then count trackfiles by RGID
    rgid_to_count: Dict[str, int] = {}
    rgid_to_display: Dict[str, Tuple[Optional[str], Optional[str]]] = {}  # (artist, title)

    for a in albums_with_files:
        album_id = a["id"]
        tfs = _lidarr_get(session, lidarr_url, "/api/v1/trackfile", params={"albumId": album_id})
        if not isinstance(tfs, list):
            raise LidarrError(f"Unexpected /trackfile response type for albumId={album_id}: {type(tfs)}")

        rgid, artist, title = album_map.get(album_id, (None, None, None))
        if not rgid:
            # If Lidarr album doesn't have RGID, we can't use it for CanComp
            continue

        # Count trackfiles for this RGID
        rgid_to_count[rgid] = rgid_to_count.get(rgid, 0) + len(tfs)

        # Save something nice to display (first seen wins)
        if rgid not in rgid_to_display:
            rgid_to_display[rgid] = (artist, title)

    # 3) (Optional) Unmapped trackfiles — cannot be assigned RGID, so not added to LibraryItems
    if include_unmapped:
        _ = _lidarr_get(session, lidarr_url, "/api/v1/trackfile", params={"unmapped": "true"})
        # keeping this hook for a future separate report

    # 4) Build LibraryItem list
    items: List[LibraryItem] = []
    for rgid, count in rgid_to_count.items():
        artist, title = rgid_to_display.get(rgid, (None, None))
        items.append(LibraryItem(rgid=rgid, owned_track_count=count, artist=artist, title=title))

    items.sort(key=lambda x: (x.artist or "", x.title or "", x.rgid))
    return items

    # Stable-ish
