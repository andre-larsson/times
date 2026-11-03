"""data/seen.json: URLs already used or rejected, so they aren't triaged or written again.

Rules (PLAN.md): items dropped by triage are marked seen right away; items written up are marked seen
once written; link-only items stay unseen, so a later full edition can still use them.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .text import canonical_url

KEEP_DAYS = 14


def load(data_dir: Path) -> dict[str, str]:
    path = data_dir / "seen.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save(data_dir: Path, seen: dict[str, str], now: dt.datetime) -> None:
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).date().isoformat()
    seen = {k: v for k, v in sorted(seen.items()) if v >= cutoff}
    path = data_dir / "seen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, indent=0) + "\n", encoding="utf-8")


def mark(seen: dict[str, str], urls: list[str], now: dt.datetime) -> None:
    day = now.date().isoformat()
    for u in urls:
        if u:
            seen.setdefault(canonical_url(u), day)


def is_seen(seen: dict[str, str], url: str) -> bool:
    return canonical_url(url) in seen
