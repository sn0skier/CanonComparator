from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tomllib


HEADER = """# Override the mode(TrackCounts) definition of canon with manual values or leave blank to allow any value
# Make sure to save before running script. You can optionally alphabetize this list when running CanonComparator 
# If the script overwrites this file you will lose any #commented notes that you have entered here
# Format "{MBReleaseGroupID}" = [{TrackCount(optional)}, ...] #{ReleaseGroupName}
[canon]
"""


def load_overrides(path: str | Path) -> Dict[str, List[int]]:
    """
    Returns dict: rgid -> list[int] (canon track counts)
    """
    p = Path(path).expanduser()
    if not p.exists():
        return {}

    with p.open("rb") as f:
        cfg = tomllib.load(f)

    canon = cfg.get("canon", {})
    out: Dict[str, List[int]] = {}
    if isinstance(canon, dict):
        for rgid, counts in canon.items():
            if isinstance(rgid, str) and isinstance(counts, list):
                cleaned = [int(x) for x in counts if isinstance(x, int) or (isinstance(x, str) and x.isdigit())]
                # unique + stable sort
                cleaned = sorted(set(cleaned))
                out[rgid] = cleaned
    return out


def write_overrides_sorted(
    path: str | Path,
    overrides: Dict[str, List[int]],
    rgid_to_label: Dict[str, str],
) -> None:
    """
    Writes overrides back out in a stable, alphabetized order, with comments:
      "RGID" = [a, b] #Artist - Release Group

    Sort key is the comment label (Artist - Release Group), then RGID.
    """
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)

    def sort_key(item: Tuple[str, List[int]]):
        rgid, _counts = item
        label = rgid_to_label.get(rgid, "")
        return (label.casefold(), rgid)

    lines = [HEADER.rstrip("\n")]
    for rgid, counts in sorted(overrides.items(), key=sort_key):
        label = rgid_to_label.get(rgid, "").strip()
        comment = f" # {label}" if label else ""
        counts_txt = ", ".join(str(x) for x in sorted(set(counts)))
        lines.append(f"\"{rgid}\" = [{counts_txt}]{comment}")

    text = "\n".join(lines) + "\n"
    p.write_text(text, encoding="utf-8")
