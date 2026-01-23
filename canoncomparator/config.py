from __future__ import annotations

import os
from pathlib import Path
import tomllib

DEFAULT_CONFIG_PATH = Path("~/.config/cancomp/config.toml").expanduser()


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        # Allow running without config (still possible via CLI args)
        return {}

    with cfg_path.open("rb") as f:
        cfg = tomllib.load(f)

    # Expand ~ in any string paths under [paths]
    paths = cfg.get("paths", {})
    for k, v in list(paths.items()):
        if isinstance(v, str):
            paths[k] = os.path.expanduser(v)

    return cfg
