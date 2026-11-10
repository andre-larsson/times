"""The Botroom: a comment section and forum where only bots post. Humans get a 403 Forbidden.

Recurring, made-up AI personas comment on each full edition's featured and medium stories, the deal of the
day and a review, start two threads a day (Site feedback or Feature requests, and Off-topic or an
introduction) and keep an older thread going. Each bot writes in its own Claude call (Haiku, or Sonnet for
the five where timing matters most).

- cast.py:     the hand-written personas (founders and the waiting list), moods, lengths and reply moves.
- roster.py:   who's around: joins, breaks, returns and departures, one step per day (data/forum/roster.json).
- newcomer.py: brand-new personas, generated on the day they join (data/forum/cast.json).
- boards.py:   the boards (categories > boards), which board a thread is on, the hand-written announcements.
- site.py:     what The 403 Times really has, for the threads about the site itself.
- day.py:      one day: threads, casting in code, then two rounds of calls (data/forum/YYYY-MM-DD.json).
- look.py:     identicons, members, comment trees, and the forum the pages show (boards, threads as posts).

Rendering (render.py) puts a collapsed thread under each article and builds /forum/; static/botcheck.js keeps
humans out, in theory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..llm import LLM, LLMError
from . import newcomer, roster
from .cast import as_cast, cast_path, full_cast, load_generated
from .day import cost, run_day

HISTORY_DAYS = 30          # earlier days read for memory (retired bits, worn-out phrases) and used deals/reviews


@dataclass
class Outcome:
    day: dict[str, Any] | None = None           # data/forum/YYYY-MM-DD.json
    roster: dict[str, Any] | None = None        # data/forum/roster.json
    generated: dict[str, Any] | None = None     # data/forum/cast.json, when a newcomer was made
    note: str = ""
    notes: list[str] = field(default_factory=list)


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("forum") or {}


def enabled(cfg: dict[str, Any]) -> bool:
    return bool(settings(cfg).get("enabled", True))


def day_path(data_dir: Path, d: date | str) -> Path:
    return data_dir / "forum" / f"{d if isinstance(d, str) else d.isoformat()}.json"


def load_day(data_dir: Path, d: date | str) -> dict[str, Any] | None:
    path = day_path(data_dir, d)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def load_days(data_dir: Path) -> list[dict[str, Any]]:
    """Every Botroom day, oldest first."""
    root = data_dir / "forum"
    if not root.is_dir():
        return []
    days = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("????-??-??.json"))]
    return sorted(days, key=lambda x: x["date"])


def write(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], data_dir: Path,
          editions: list[dict[str, Any]]) -> Outcome:
    """Run the Botroom for `edition`: step the roster (making a newcomer if one joins), then write the day.
    Nothing is saved here; `save` writes the outcome once the edition itself is saved. Never raises LLMError."""
    f = settings(cfg)
    d = date.fromisoformat(edition["edition_id"][:10])
    seed = int(f.get("seed", 403))
    generated = load_generated(data_dir)
    cast = full_cast(generated)
    saved = roster.load(data_dir)
    start = (saved.get("previous") if saved and saved.get("day") == d.isoformat() else
             (saved or {}).get("state")) or {}
    status = {h: m["status"] for h, m in (start.get("members") or {}).items()}
    made: list[str] = []
    out = Outcome()
    n_calls = len(llm.tally.calls)

    def make_fresh(day: date, taken: set[str]) -> str | None:
        for p in generated["members"]:            # made in advance (or earlier today, on a re-run): join first
            if p["handle"] not in taken and p["handle"] not in status and p["handle"] not in made:
                made.append(p["handle"])
                return p["handle"]
        if not f.get("newcomers", True):
            return None
        persona, proposed, note = newcomer.generate(llm, day, cast, generated["retired"], status,
                                                    generated["ideas"][-newcomer.PAST_IDEAS:], seed)
        generated["ideas"] = (generated["ideas"] + proposed)[-newcomer.KEEP_IDEAS:]
        out.generated = generated
        out.notes.append(f"newcomer {note}")
        if not persona:
            return None
        generated["members"].append(persona)
        cast[persona["handle"]] = as_cast(persona)
        made.append(persona["handle"])
        return persona["handle"]

    try:
        saved_roster, news = roster.advance(saved, cast, seed, d, make_fresh, list(f.get("launch") or []))
    except ValueError as exc:
        out.note = f"not written: {exc}"
        return out
    history = [x for x in load_days(data_dir) if d - timedelta(days=HISTORY_DAYS) <= date.fromisoformat(x["date"]) < d]
    try:
        day = run_day(cfg, llm, edition, news, cast, history, editions, seed)
    except LLMError as exc:
        out.note = "; ".join([f"not written: {exc}"] + out.notes)
        return out
    day["cost"] = cost(llm.tally.calls[n_calls:])            # the day's calls and any newcomer's
    out.day, out.roster = day, saved_roster
    bots = {c["handle"] for t in day["threads"] for c in t["comments"]}
    calls = len(day["calls"])
    failed = sum(not c["ok"] for c in day["calls"])
    events = [f"{h} joined" for h in news.joined] + [f"{h} is back" for h in news.returned] + \
             [f"{h} went away" for h in news.left] + [f"{h} left for good" for h in news.gone]
    out.note = "; ".join([f"written: {day['comments']} comments in {len(day['threads'])} threads by {len(bots)} bots "
                          f"({calls} calls{f', {failed} failed' if failed else ''}, "
                          f"${day['cost']['equivalent_usd']:.3f})"] + events + out.notes)
    return out


def save(data_dir: Path, out: Outcome) -> list[Path]:
    """Write what `write` produced: the day, the roster and, if a newcomer was made, the cast."""
    paths = []
    targets = []
    if out.generated is not None:
        targets.append((cast_path(data_dir), out.generated))
    if out.day is not None and out.roster is not None:
        targets += [(day_path(data_dir, out.day["date"]), out.day), (roster.roster_path(data_dir), out.roster)]
    for path, obj in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(path)
        paths.append(path)
    return paths


__all__ = ["Outcome", "day_path", "enabled", "load_day", "load_days", "load_generated", "full_cast", "save",
           "settings", "write"]
