"""Reading and writing edition files under data/editions/YYYY/MM/DD[-HHMM].json."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def edition_path(data_dir: Path, edition_id: str) -> Path:
    year, month, rest = edition_id.split("-", 2)
    return data_dir / "editions" / year / month / f"{rest}.json"


def latest_edition(data_dir: Path) -> dict[str, Any] | None:
    files = sorted((data_dir / "editions").rglob("*.json"))
    if not files:
        return None
    editions = [json.loads(p.read_text(encoding="utf-8")) for p in files[-3:]]
    return max(editions, key=lambda e: e["edition_id"])


def last_generated_at(data_dir: Path) -> dt.datetime | None:
    ed = latest_edition(data_dir)
    if not ed or not ed.get("generated_at"):
        return None
    return dt.datetime.fromisoformat(ed["generated_at"].replace("Z", "+00:00"))


def save_edition(data_dir: Path, edition: dict[str, Any]) -> Path:
    path = edition_path(data_dir, edition["edition_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(edition, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
