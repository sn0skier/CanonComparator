from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class LibraryItem:
    rgid: str                      # MusicBrainz Release Group MBID
    owned_track_count: int         # how many tracks you have for that release group
    artist: Optional[str] = None
    title: Optional[str] = None
    source_id: Optional[str] = None  # e.g., Lidarr albumId (debugging)
