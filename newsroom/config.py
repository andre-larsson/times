"""Load and lightly validate config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import ROOT

REQUIRED_SITE_KEYS = ("title", "tagline", "url", "base_path")


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or ROOT / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    site = cfg.get("site") or {}
    missing = [k for k in REQUIRED_SITE_KEYS if not site.get(k)]
    if missing:
        raise ValueError(f"config.yaml: site is missing {', '.join(missing)}")

    base = site["base_path"]
    if not (base.startswith("/") and base.endswith("/")):
        raise ValueError("config.yaml: site.base_path must start and end with '/' (e.g. /times/)")

    cfg.setdefault("schedule", {}).setdefault("timezone", "Europe/Stockholm")
    cfg.setdefault("sections", [])
    return cfg
