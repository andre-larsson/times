"""The opinion column: when it's due, the rotation that keeps it varied, and writing it.

Two calls. The opinion editor (`opinion_pick`, Opus) reads the headlines of the last
`opinion.lookback_days` of editions and picks a topic, a thesis and the stories to use. The columnist
(`opinion`, Fable) then writes the column from those stories' full text.

Variety is enforced in code, through the pick call's schema: the format can't repeat either of the
last two columns' formats, and the focus (AI, Tech, Gaming or cross-section) can't repeat the last
column's. Every earlier column's topic and thesis go to the editor so topics don't come back.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from . import desk
from .llm import LLM, LLMError
from .text import slugify

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MIN_STORIES = 2                   # fewer known stories than this from the editor: no column
MAX_STORIES = 8


@dataclass
class Outcome:
    column: dict[str, Any] | None = None
    note: str = ""                # why no column was written, when one was due


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("opinion") or {}


def edition_date(edition: dict[str, Any]) -> dt.date:
    return dt.date.fromisoformat(edition["edition_id"][:10])


def is_due(cfg: dict[str, Any], day: dt.date, last: dt.date | None) -> bool:
    """On one of opinion.days, once at least `every_weeks` weeks have passed since the last column."""
    o = settings(cfg)
    if not o.get("enabled", True):
        return False
    days = {WEEKDAYS.index(str(d)[:3].lower()) for d in o.get("days", ["sun"])}
    if day.weekday() not in days:
        return False
    weeks = max(1, int(o.get("every_weeks", 2)))
    return last is None or (day - last).days > 7 * (weeks - 1)


def history(editions: list[dict[str, Any]], exclude: str = "") -> list[dict[str, Any]]:
    """Earlier columns, newest first."""
    out = []
    for ed in sorted(editions, key=lambda e: e["edition_id"], reverse=True):
        col = ed.get("opinion")
        if col and ed["edition_id"] != exclude:
            out.append({"date": ed["edition_id"][:10],
                        **{k: col.get(k, "") for k in ("headline", "topic", "thesis", "focus", "format")}})
    return out


def rotation(hist: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(allowed formats, allowed focus) for the next column."""
    recent_formats = {c.get("format") for c in hist[:2]}
    formats = [f for f in desk.COLUMN_FORMATS if f not in recent_formats] or list(desk.COLUMN_FORMATS)
    last_focus = hist[0].get("focus") if hist else None
    focus = [f for f in desk.COLUMN_FOCUS if f != last_focus]
    return formats, focus


def material(editions: list[dict[str, Any]], today: dict[str, Any],
             lookback_days: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Compact rows for the editor (oldest first), and an index from row id to the full item."""
    day = edition_date(today)
    start = day - dt.timedelta(days=max(1, lookback_days) - 1)
    eds = [e for e in sorted(editions, key=lambda e: e["edition_id"])
           if start <= edition_date(e) <= day and e["edition_id"] != today["edition_id"]] + [today]
    rows: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for ed in eds:
        eid, date = ed["edition_id"], ed["edition_id"][:10]
        for s in ed.get("stories", []):
            sid = f"{eid}/{s['slug']}"
            row = {"id": sid, "date": date, "section": s["section"], "tier": s["tier"], "headline": s["headline"]}
            if s["tier"] != "brief" and s.get("dek"):
                row["dek"] = s["dek"]
            if s["tier"] == "featured" and s.get("key_points"):
                row["key_points"] = s["key_points"]
            rows.append(row)
            index[sid] = {"kind": "story", "edition_id": eid, "item": s}
        g = ed.get("gaming") or {}
        for i, n in enumerate((g.get("console_spotlight") or []) + (g.get("news") or []), 1):
            if not n.get("headline"):
                continue
            sid = f"{eid}/gaming-{i}"
            rows.append({"id": sid, "date": date, "section": "gaming", "tier": "gaming_news",
                         "headline": n["headline"], "summary": n.get("summary", "")})
            index[sid] = {"kind": "gaming", "edition_id": eid, "item": n}
    return rows, index


def _sources(entry: dict[str, Any]) -> list[dict[str, str]]:
    it = entry["item"]
    srcs = it.get("sources") or ([{"name": it.get("source", ""), "url": it.get("url", "")}] if it.get("url") else [])
    return [{"name": s.get("name", ""), "url": s.get("url", ""), **({"title": s["title"]} if s.get("title") else {})}
            for s in srcs if s.get("url")][:3]


def _reporting(entry: dict[str, Any]) -> dict[str, Any]:
    """What the columnist gets for one story: its full text and the outlets behind it."""
    it = entry["item"]
    keys = ("headline", "dek", "body", "key_points", "why_it_matters") if entry["kind"] == "story" \
        else ("headline", "summary")
    out = {"date": entry["edition_id"][:10], **{k: it[k] for k in keys if it.get(k)}}
    out["sources"] = [s["name"] for s in _sources(entry)]
    return out


def _reading(entry: dict[str, Any]) -> dict[str, Any]:
    """A 'reporting behind this column' link: the article page if it has one, else the source."""
    it = entry["item"]
    row = {"headline": it["headline"], "edition_id": entry["edition_id"], "sources": _sources(entry)}
    if entry["kind"] == "story":
        row.update(section=it["section"], tier=it["tier"], slug=it["slug"])
    else:
        row.update(section="gaming", tier="gaming_news")
    return row


def unique_slug(headline: str, taken: set[str]) -> str:
    base = slugify(headline) or "column"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def write(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], editions: list[dict[str, Any]],
          force: bool = False) -> Outcome:
    """Write the column for `edition` if one is due (or forced). Never raises LLMError."""
    o = settings(cfg)
    hist = history(editions, exclude=edition["edition_id"])
    day = edition_date(edition)
    last = dt.date.fromisoformat(hist[0]["date"]) if hist else None
    if not force and not is_due(cfg, day, last):
        return Outcome()
    rows, index = material(editions, edition, int(o.get("lookback_days", 14)))
    if len(rows) < 5:
        return Outcome(note="too little recent material")
    formats, focus = rotation(hist)
    try:
        pick = desk.pick_opinion(llm, cfg, {
            "today": day.isoformat(),
            "allowed_formats": formats, "format_guide": {f: desk.COLUMN_FORMATS[f] for f in formats},
            "allowed_focus": focus, "focus_guide": {f: desk.COLUMN_FOCUS[f] for f in focus},
            "earlier_columns": hist[:26],
            "stories": rows,
        })
        ids = list(dict.fromkeys(i for i in pick.get("story_ids", []) if i in index))[:MAX_STORIES]
        if len(ids) < MIN_STORIES:
            return Outcome(note="the opinion editor picked too few known stories")
        fmt = pick.get("format") if pick.get("format") in formats else formats[0]
        foc = pick.get("focus") if pick.get("focus") in focus else focus[0]
        out = desk.write_opinion(llm, cfg, {
            "today": day.isoformat(), "topic": pick.get("topic", ""), "thesis": pick.get("thesis", ""),
            "format": fmt, "format_guide": desk.COLUMN_FORMATS[fmt], "focus": foc,
            "earlier_headlines": [c["headline"] for c in hist[:6]],
            "stories": [_reporting(index[i]) for i in ids],
        })
    except LLMError as exc:
        return Outcome(note=str(exc))
    if not out.get("headline") or not out.get("body"):
        return Outcome(note="the columnist returned an empty column")
    body = out["body"].strip()
    quote = (out.get("pull_quote") or "").strip()
    if quote and " ".join(quote.split()) not in " ".join(body.split()):
        quote = ""                                   # only quote what the column actually says
    column = {
        "slug": unique_slug(out["headline"], {s["slug"] for s in edition.get("stories", [])}),
        "section": "opinion", "kicker": "Opinion",
        "headline": out["headline"].strip(), "dek": (out.get("dek") or "").strip(), "body": body,
        "pull_quote": quote, "topic": pick.get("topic", ""), "thesis": pick.get("thesis", ""),
        "focus": foc, "format": fmt, "model": llm.model_for("opinion"),
        "reading": [_reading(index[i]) for i in ids],
    }
    return Outcome(column)
