from __future__ import annotations

from typing import Dict, List

from canoncomparator.types import LibraryItem
from canoncomparator.mb_client import MbRgStats


def build_override_suggestion(rgid: str, owned: int, mb_mode: int | None, label: str) -> str:
    vals = [owned]
    if mb_mode is not None:
        vals.append(mb_mode)
    # unique + preserve order-ish (owned first, then mode if different)
    uniq: List[int] = []
    for v in vals:
        if v not in uniq:
            uniq.append(v)
    vals_txt = ", ".join(str(v) for v in uniq)
    return f"\"{rgid}\" = [{vals_txt}] #{label}"


def build_rows(
    items: List[LibraryItem],
    mb_stats: Dict[str, MbRgStats],
    overrides: Dict[str, List[int]],
) -> List[dict]:
    rows: List[dict] = []
    for it in items:
        st = mb_stats.get(it.rgid)

        mode_tc = st.mode_track_count if st else None
        hist = st.histogram if st else {}

        # counts from histogram
        mode_release_count = hist.get(mode_tc, 0) if (mode_tc is not None) else 0
        owned_release_count = hist.get(it.owned_track_count, 0)

        label = f"{it.artist or ''} - {it.title or ''}".strip(" -")

        # canon logic
        if it.rgid in overrides and overrides[it.rgid]:
            canon_counts = overrides[it.rgid]
            canon_source = "override"
        else:
            canon_counts = [mode_tc] if mode_tc is not None else []
            canon_source = "mb_mode"

        owned_matches_canon = True if not canon_counts else (it.owned_track_count in canon_counts)

        override_suggestion = build_override_suggestion(
            rgid=it.rgid,
            owned=it.owned_track_count,
            mb_mode=mode_tc,
            label=label,
        )

        diff = (it.owned_track_count - mode_tc) if (mode_tc is not None) else ""

        min_owned_minus_canon = 0 if not canon_counts else min(
            it.owned_track_count - c for c in canon_counts
        )

        rows.append({
            "rgid": it.rgid,
            "artist": it.artist or "",
            "title": it.title or "",
            "min_owned_minus_canon": min_owned_minus_canon,
            "owned_track_count": it.owned_track_count,

            "mb_mode_track_count": mode_tc if mode_tc is not None else "",
            "mode_release_count": mode_release_count if mode_tc is not None else "",
            "owned_trackcount_release_count": owned_release_count if st else "",

            "canon_track_counts": ", ".join(str(x) for x in canon_counts),
            "canon_source": canon_source,
            "owned_matches_canon": str(owned_matches_canon),

            "diff_owned_minus_mode": diff,
            "mb_release_count": st.release_count if st else "",

            "mb_histogram_tracks_releases_json": hist,
            "override_suggestion": override_suggestion,
        })

    return rows
