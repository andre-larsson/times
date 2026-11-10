"""Reading and writing edition files under data/editions/YYYY/MM/DD[-HHMM].json."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def edition_path(data_dir: Path, edition_id: str) -> Path:
    year, month, rest = edition_id.split("-", 2)
    return data_dir / "editions" / year / month / f"{rest}.json"


def load_edition(data_dir: Path, edition_id: str) -> dict[str, Any] | None:
    path = edition_path(data_dir, edition_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def all_editions(data_dir: Path) -> list[dict[str, Any]]:
    """Every saved edition, oldest first."""
    root = data_dir / "editions"
    if not root.exists():
        return []
    editions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.rglob("*.json"))]
    return sorted(editions, key=lambda e: e["edition_id"])


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


def recent_headlines(data_dir: Path, exclude: str = "", count: int = 2) -> list[dict[str, Any]]:
    """Headlines of the last few editions, so the editor can avoid repeating yesterday's stories."""
    files = sorted((data_dir / "editions").rglob("*.json"))[-(count + 2):] if (data_dir / "editions").exists() else []
    out = []
    for p in reversed(files):
        ed = json.loads(p.read_text(encoding="utf-8"))
        if ed.get("edition_id") == exclude:
            continue
        heads = [s["headline"] for s in ed.get("stories", [])] or [l["title"] for l in ed.get("links", [])]
        out.append({"edition_id": ed["edition_id"], "headlines": heads[:30]})
        if len(out) >= count:
            break
    return out


def previous_edition(data_dir: Path, before: str, key: str, limit: int = 14) -> dict[str, Any] | None:
    """The newest of the last `limit` saved editions whose id sorts before `before` and that has `key` (the deals
    carried over: re-running today's edition skips today's own file)."""
    root = data_dir / "editions"
    if not root.exists():
        return None
    editions = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.rglob("*.json"))[-limit:]]
    for ed in sorted(editions, key=lambda e: e["edition_id"], reverse=True):
        if ed["edition_id"] < before and ed.get(key):
            return ed
    return None
