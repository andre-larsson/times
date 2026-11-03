"""Monthly budget: the spend tally in data/usage.json and the pacing decision.

Only API spend counts. Calls made through the claude-code backend (local development on the Claude
subscription) are logged with their API-equivalent cost but don't touch the monthly total.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
from pathlib import Path
from typing import Any

from .llm import Tally


def usage_path(data_dir: Path) -> Path:
    return data_dir / "usage.json"


def load_usage(data_dir: Path) -> dict[str, Any]:
    path = usage_path(data_dir)
    if not path.is_file():
        return {"months": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def month_key(now: dt.datetime) -> str:
    return f"{now:%Y-%m}"


def spent_this_month(usage: dict[str, Any], now: dt.datetime) -> float:
    return float((usage.get("months") or {}).get(month_key(now), {}).get("usd", 0.0))


def pace_decision(cfg: dict[str, Any], usage: dict[str, Any], now: dt.datetime) -> tuple[str, str]:
    """('full' | 'reduced' | 'over', reason), from spend so far against the month's pace."""
    b = cfg.get("budget") or {}
    monthly = float(b.get("monthly_usd", 20))
    allowance = float(b.get("pace_allowance_usd", 2))
    spent = spent_this_month(usage, now)
    days = calendar.monthrange(now.year, now.month)[1]
    pace = monthly * now.day / days + allowance
    if spent >= monthly:
        return "over", f"monthly budget used: ${spent:.2f} of ${monthly:.2f}"
    if spent > pace:
        return "reduced", f"ahead of pace: ${spent:.2f} spent, pace allows ${pace:.2f} by day {now.day}"
    return "full", f"on pace: ${spent:.2f} of ${pace:.2f} allowed by day {now.day}"


def record_run(data_dir: Path, now: dt.datetime, edition_id: str, mode: str, backend: str, tally: Tally) -> None:
    """Add this run to usage.json (API spend counts toward the month; subscription runs don't)."""
    if not tally.calls:
        return
    usage = load_usage(data_dir)
    month = usage.setdefault("months", {}).setdefault(month_key(now), {"usd": 0.0, "runs": []})
    s = tally.summary()
    if backend == "api":
        month["usd"] = round(month["usd"] + s["usd"], 6)
    month["runs"].append({
        "at": now.isoformat(), "edition_id": edition_id, "mode": mode, "backend": backend,
        "usd": s["usd"] if backend == "api" else 0.0, "equivalent_usd": s["equivalent_usd"],
        "calls": s["calls"], "by_task": s["by_task"], "stopped": s["stopped"],
        "tokens": {
            "input": sum(c.input_tokens for c in tally.calls),
            "output": sum(c.output_tokens for c in tally.calls),
            "cache_read": sum(c.cache_read for c in tally.calls),
            "cache_write": sum(c.cache_write for c in tally.calls),
        },
    })
    path = usage_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, indent=1) + "\n", encoding="utf-8")
