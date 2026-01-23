from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from datetime import datetime

from canoncomparator.config import load_config
from canoncomparator.providers.lidarr import fetch_library_items
from canoncomparator.mb_client import create_mb_session, fetch_rg_stats
from canoncomparator.compare import build_rows
from canoncomparator.overrides import load_overrides, write_overrides_sorted


def main() -> int:
    ap = argparse.ArgumentParser(
        description="CanComp: compare your library’s RG track counts to MusicBrainz release-group mode track counts."
    )
    ap.add_argument("--config", default=None, help="Path to config file (default: ~/.config/cancomp/config.toml)")

    # Lidarr
    ap.add_argument("--provider", default="lidarr", choices=["lidarr"], help="Library provider (currently only lidarr)")
    ap.add_argument("--overrides", default=None, help="Overrides TOML (default: ~/.config/cancomp/overrides.toml)")
    ap.add_argument(
        "--sort-overrides",
        action="store_true",
        help="Rewrite overrides.toml alphabetized by Artist - Release Group (overwrites file)",
    )
    ap.add_argument("--lidarr-url", default=None, help="Lidarr base URL (overrides config)")
    ap.add_argument("--api-key", default=None, help="Lidarr API key (overrides config)")
    ap.add_argument("--limit-albums", type=int, default=None, help="Limit Lidarr albums for testing")

    # MusicBrainz / cache
    ap.add_argument("--limit-rgids", type=int, default=None, help="Limit RGIDs sent to MusicBrainz (fast testing)")
    ap.add_argument("--max-age-days", type=float, default=None, help="MB cache max age in days (-1 = never refetch, 0 = always refetch)")

    # Output
    ap.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: cancomp_<timestamp>.csv)",
    )


    args = ap.parse_args()

    cfg = load_config(Path(args.config) if args.config else None)
    overrides_path = args.overrides or str(Path("~/.config/cancomp/overrides.toml").expanduser())
    overrides = load_overrides(overrides_path)

    # MB settings
    mb_cfg = cfg.get("musicbrainz", {})
    cfg_max_age = mb_cfg.get("cache_max_age_days", 365.0)
    max_age_days = args.max_age_days if args.max_age_days is not None else float(cfg_max_age)

    # Lidarr settings
    lidarr_cfg = cfg.get("lidarr", {})
    lidarr_url = args.lidarr_url or lidarr_cfg.get("url", "http://localhost:8686")
    api_key = args.api_key or lidarr_cfg.get("api_key")
    if not api_key:
        raise SystemExit("Lidarr API key not provided (via config or --api-key)")

    # Cache path
    paths_cfg = cfg.get("paths", {})
    cache_path = paths_cfg.get("cache", str(Path("~/.cache/cancomp/mb_cache.sqlite").expanduser()))

    # Fetch library items (RGID + owned track count)
    items = fetch_library_items(
        lidarr_url=lidarr_url,
        api_key=api_key,
        limit_albums=args.limit_albums,
        include_unmapped=False,
    )

    if args.limit_rgids is not None:
        items = items[: args.limit_rgids]

    # RGID to label map
    rgid_to_label = {}
    for it in items:
        label = f"{it.artist or ''} - {it.title or ''}".strip(" -")
        if it.rgid not in rgid_to_label:
            rgid_to_label[it.rgid] = label

    # Fetch MB stats (cached)
    if max_age_days < 0:
        policy = "never refetch"
    elif max_age_days == 0:
        policy = "always refetch"
    else:
        policy = f"max age = {int(max_age_days)} days"

    print(f"MB cache policy: {policy}")

    mb_session = create_mb_session(cfg)

    mb_stats = {}
    total = len(items)
    for i, it in enumerate(items, start=1):
        stats, status = fetch_rg_stats(
            session=mb_session,
            cache_path=cache_path,
            rgid=it.rgid,
            max_age_days=max_age_days,
        )
        print(f"[{i}/{total}] MB {status}: {it.rgid}")
        mb_stats[it.rgid] = stats

    # Merge + write CSV (Excel-friendly UTF-8 with BOM)
    rows = build_rows(items, mb_stats, overrides)

    if args.out:
        out_path = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = Path(f"cancomp_{ts}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "rgid",
        "artist",
        "title",
        "owned_track_count",
        "canon_track_counts",
        "min_owned_minus_canon",
        "owned_matches_canon",
        "canon_source",
        "mb_mode_track_count",
        "diff_owned_minus_mode",
        "mode_release_count",
        "owned_trackcount_release_count",
        "mb_release_count",
        "mb_histogram_tracks_releases_json",
        "override_suggestion",
    ]

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # ensure histogram is a JSON string for CSV friendliness
            r = dict(r)
            hist = r.get("mb_histogram_tracks_releases_json", {})
            r["mb_histogram_tracks_releases_json"] = json.dumps(hist, ensure_ascii=False, sort_keys=True)
            w.writerow(r)
            
    print(f"Wrote {len(rows)} rows to {out_path}")
    
    # Sort the overrides list
    if args.sort_overrides:
        write_overrides_sorted(overrides_path, overrides, rgid_to_label)
        print(f"Sorted overrides written to {overrides_path}")
        
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
