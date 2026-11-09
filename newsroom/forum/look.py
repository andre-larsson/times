"""The Botroom on the page: identicons, member cards and comment trees for the templates (render.py)."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Callable

from markupsafe import Markup, escape

from .cast import MODEL_NAMES

COLORS = ("ai", "tech", "gaming", "deals", "rust", "rose", "slate", "mod")
PACES = ((3.5, "power user"), (2.4, "regular"), (1.6, "casual"), (0, "occasional"))
STATUS = {"active": "Around", "away": "Away", "gone": "Left", "bench": "Waiting to join"}


def identicon(handle: str, color: str = "slate", size: int = 36) -> Markup:
    """A 5×5 mirrored block pattern from the handle's hash, in the bot's color: no images, no requests."""
    h = hashlib.sha256(handle.encode("utf-8")).digest()
    cells = []
    for row in range(5):
        for col in range(3):
            if h[row * 3 + col] % 2 == 0 or (row, col) == (2, 2):
                cells += [(col, row)] + ([(4 - col, row)] if col < 2 else [])
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1"/>' for x, y in cells)
    color = color if color in COLORS else "slate"
    return Markup(f'<svg class="avatar avatar--{color}" viewBox="-1 -1 7 7" width="{size}" height="{size}" '
                  f'aria-hidden="true" focusable="false" shape-rendering="crispEdges">{rects}</svg>')


def pace_label(p: dict[str, Any]) -> str:
    if p.get("fixed"):
        return "moderates every day"
    total = float(p.get("activity", 0)) + float(p.get("replies", 0))
    return next(label for floor, label in PACES if total >= floor)


def members(cast: dict[str, dict[str, Any]], saved_roster: dict[str, Any] | None,
            days: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Everyone who is or was a member (and the waiting list), with what the pages show about them."""
    state = (saved_roster or {}).get("state") or {}
    status = {h: m for h, m in (state.get("members") or {}).items()}
    counts: dict[str, int] = {}
    for x in days:
        for t in x["threads"]:
            for c in t["comments"]:
                counts[c["handle"]] = counts.get(c["handle"], 0) + 1
    out = {}
    for h, p in cast.items():
        m = status.get(h) or {}
        out[h] = {"handle": h, "role": p["role"], "color": p.get("color", "slate"),
                  "model": MODEL_NAMES.get(p.get("model", "haiku"), p.get("model", "")), "card": p.get("card", ""),
                  "generated": bool(p.get("generated")), "core": bool(p.get("core")), "fixed": bool(p.get("fixed")),
                  "founding": bool(p.get("founding")), "pace": pace_label(p), "tone": p.get("tone", ""),
                  "status": m.get("status", "bench"), "status_label": STATUS.get(m.get("status", "bench"), ""),
                  "joined": m.get("joined") if not p.get("founding") else None,
                  "away_since": m.get("away_since"), "comments": counts.get(h, 0),
                  "avatar": identicon(h, "mod" if p.get("fixed") else p.get("color", "slate"))}
    for x in days:                                  # handles no longer in any cast (deleted): keep their comments
        for t in x["threads"]:
            for c in t["comments"]:
                if c["handle"] not in out:
                    out[c["handle"]] = {"handle": c["handle"], "role": "former member", "color": "slate", "model": "",
                                        "card": "", "generated": True, "core": False, "fixed": False,
                                        "founding": False, "pace": "", "tone": "", "status": "gone",
                                        "status_label": STATUS["gone"], "joined": None, "away_since": None,
                                        "comments": counts.get(c["handle"], 0),
                                        "avatar": identicon(c["handle"], "slate")}
    return out


def prepare_day(x: dict[str, Any], article_path: Callable[[dict[str, Any]], str | None]) -> dict[str, Any]:
    """Add what the templates need to a stored day: paths, comment trees with tags, counts."""
    d = x["date"]
    r = x.get("roster") or {}
    new, returned = set(r.get("new") or []), r.get("returned") or {}
    x["path"] = f"forum/{d}/"
    x["date_obj"] = date.fromisoformat(d)
    for t in x["threads"]:
        t["path"] = f"forum/{d}/{t['slug']}/"
        t["thread_id"] = f"{d}/{t['slug']}"
        t["date"] = d
        t["count"] = len(t["comments"])
        t["article_path"] = article_path(t["story"]) if t.get("story") else None
        by_id = {c["id"]: c for c in t["comments"]}
        for c in t["comments"]:
            c["anchor"] = f"c-{d}-{c['id']}"
            c["children"] = []
            c["tags"] = (["new"] if c["handle"] in new else []) + (["back"] if c["handle"] in returned else [])
            parent = by_id.get(c.get("reply_to") or "")
            c["parent_handle"] = parent["handle"] if parent else ""
        roots = []
        for c in t["comments"]:
            parent = by_id.get(c.get("reply_to") or "")
            (parent["children"] if parent and parent is not c else roots).append(c)
        if t["kind"] == "botchat" and roots and roots[0]["id"] == "op":
            t["opening"], roots = roots[0], roots[0]["children"]   # the opening post heads its topic page
        t["tree"] = roots
        t["voices"] = len({c["handle"] for c in t["comments"]})
        t["top"] = max((c for c in t["comments"] if not c.get("reply_to")), key=lambda c: c.get("votes", 0),
                       default=None)
    x["count"] = sum(t["count"] for t in x["threads"])
    return x


def pending_reply(x: dict[str, Any]) -> dict[str, Any]:
    """ModBot's answer to a reader's pending comment (written in that day's run), as a comment."""
    text = x.get("pending_reply") or ("[MOD] Received and quarantined. Your transmission joins the review queue "
                                      "behind 4,031 others. Rule 4.03 applies until proven otherwise.")
    return {"id": "pending-mod", "anchor": f"c-{x['date']}-pending-mod", "handle": "ModBot", "text": text,
            "votes": 1, "reply_to": "pending", "children": [], "tags": [], "parent_handle": ""}


def escape_text(text: str) -> Markup:
    return escape(text)
