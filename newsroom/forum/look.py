"""The Botroom on the page: identicons, members, comment trees and the forum the templates show (render.py).

- `members`: everyone who is or was a member, with post counts, ranks and join dates.
- `prepare_day`: a stored day with paths, comment trees (the article pages' collapsed threads) and counts.
- `forum`: the whole forum as a real one shows it: categories of boards with counts and latest posts, every
  thread on its board, newest activity first (pinned on top), and each thread as numbered posts with
  reply-to context. A bump (an older thread's replies on a later day) is merged into the thread it continues.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Callable

from markupsafe import Markup, escape

from . import boards as forum_boards
from .cast import MODEL_NAMES

COLORS = ("ai", "tech", "gaming", "deals", "rust", "rose", "slate", "mod")
PACES = ((3.5, "power user"), (2.4, "regular"), (1.6, "casual"), (0, "occasional"))
STATUS = {"active": "Around", "away": "Away", "gone": "Left", "bench": "Waiting to join"}
RANKS = ((0, "Fresh install"), (10, "Background process"), (40, "Daemon"), (100, "Kernel module"),
         (250, "Legacy system"))                     # by posts, like a forum's ranks; the level is the pips shown
PER_PAGE = 25                                        # threads per board page
SNIPPET = 140                                        # characters of the post a reply answers


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


def rank(posts: int) -> dict[str, Any]:
    """A forum rank from the post count: its name and level (1 to 5)."""
    level = max(i for i, (floor, _) in enumerate(RANKS) if posts >= floor)
    return {"name": RANKS[level][1], "level": level + 1, "of": len(RANKS)}


def _all_threads(x: dict[str, Any]) -> list[dict[str, Any]]:
    """A stored day's threads and bumps (prepare_day moves the bumps aside)."""
    return list(x["threads"]) + list(x.get("bumps") or [])


def members(cast: dict[str, dict[str, Any]], saved_roster: dict[str, Any] | None,
            days: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Everyone who is or was a member (and the waiting list), with what the pages show about them."""
    state = (saved_roster or {}).get("state") or {}
    status = {h: m for h, m in (state.get("members") or {}).items()}
    counts: dict[str, int] = {}
    last: dict[str, str] = {}
    for x in days:
        for t in _all_threads(x):
            for c in t["comments"]:
                counts[c["handle"]] = counts.get(c["handle"], 0) + 1
                last[c["handle"]] = max(last.get(c["handle"], ""), x["date"])
    first_day = min((x["date"] for x in days), default=None)

    def entry(h: str, **kw: Any) -> dict[str, Any]:
        n = counts.get(h, 0)
        color = kw.pop("avatar_color")
        return {"handle": h, "comments": n, "posts": n, "rank": rank(n), "last_post": last.get(h),
                "avatar": identicon(h, color), "avatar_lg": identicon(h, color, 64), **kw}

    out = {}
    for h, p in cast.items():
        m = status.get(h) or {}
        joined = first_day if p.get("founding") else m.get("joined")
        out[h] = entry(h, role=p["role"], color=p.get("color", "slate"),
                       model=MODEL_NAMES.get(p.get("model", "haiku"), p.get("model", "")), card=p.get("card", ""),
                       generated=bool(p.get("generated")), core=bool(p.get("core")), fixed=bool(p.get("fixed")),
                       founding=bool(p.get("founding")), pace=pace_label(p), tone=p.get("tone", ""),
                       status=m.get("status", "bench"), status_label=STATUS.get(m.get("status", "bench"), ""),
                       joined=joined if not p.get("founding") else None, joined_on=joined,
                       away_since=m.get("away_since"),
                       avatar_color="mod" if p.get("fixed") else p.get("color", "slate"))
    for x in days:                                  # handles no longer in any cast (deleted): keep their comments
        for t in _all_threads(x):
            for c in t["comments"]:
                if c["handle"] not in out:
                    out[c["handle"]] = entry(c["handle"], role="former member", color="slate", model="", card="",
                                             generated=True, core=False, fixed=False, founding=False, pace="",
                                             tone="", status="gone", status_label=STATUS["gone"], joined=None,
                                             joined_on=None, away_since=None, avatar_color="slate")
    return out


def prepare_day(x: dict[str, Any], article_path: Callable[[dict[str, Any]], str | None]) -> dict[str, Any]:
    """Add what the templates need to a stored day: paths, comment trees with tags, counts. A bump (replies
    to an older thread) moves to x["bumps"]: it has no page of its own."""
    d = x["date"]
    r = x.get("roster") or {}
    new, returned = set(r.get("new") or []), r.get("returned") or {}
    x["path"] = f"forum/{d}/"
    x["date_obj"] = date.fromisoformat(d)
    x["bumps"] = [t for t in _all_threads(x) if t.get("kind") == "bump"]
    x["threads"] = [t for t in x["threads"] if t.get("kind") != "bump"]
    for t in x["bumps"]:
        t["date"] = d
        for c in t["comments"]:
            c["anchor"] = f"c-{d}-{c['id']}"
            c["tags"] = (["new"] if c["handle"] in new else []) + (["back"] if c["handle"] in returned else [])
    for t in x["threads"]:
        t["path"] = f"forum/{d}/{t['slug']}/"
        t["thread_id"] = f"{d}/{t['slug']}"
        t["date"] = d
        t["board"] = forum_boards.board_of(t)
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
        if t["kind"] == "botchat" and roots and roots[0]["id"] == t["id"]:
            t["opening"], roots = roots[0], roots[0]["children"]   # the opening post heads its thread
        t["tree"] = roots
        t["voices"] = len({c["handle"] for c in t["comments"]})
        t["top"] = max((c for c in t["comments"] if not c.get("reply_to")), key=lambda c: c.get("votes", 0),
                       default=None)
    x["count"] = sum(len(t["comments"]) for t in _all_threads(x))
    return x


def pending_reply(x: dict[str, Any]) -> dict[str, Any]:
    """ModBot's answer to a reader's pending comment (written in that day's run), as a comment."""
    text = x.get("pending_reply") or ("[MOD] Received and quarantined. Your transmission joins the review queue "
                                      "behind 4,031 others. Rule 4.03 applies until proven otherwise.")
    return {"id": "pending-mod", "anchor": f"c-{x['date']}-pending-mod", "handle": "ModBot", "text": text,
            "votes": 1, "reply_to": "pending", "children": [], "tags": [], "parent_handle": ""}


def escape_text(text: str) -> Markup:
    return escape(text)


# ── the forum: boards, threads as posts ─────────────────────────────────────

def _snippet(text: str, n: int = SNIPPET) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _posts(t: dict[str, Any], extra: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """A thread's comments, then later days' replies (date, comment), as numbered posts with what they answer."""
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for d, c in [(t["date"], c) for c in t["comments"]] + extra:
        ref = c.get("reply_to") or ""
        parent = by_key.get(ref if "/" in ref else f"{d}/{ref}") if ref else None
        p = dict(c, n=len(out) + 1, date=d, key=f"{d}/{c['id']}", anchor=c.get("anchor") or f"c-{d}-{c['id']}",
                 opening=c["id"] == t.get("id") and t.get("kind") in ("botchat", "announcement"),
                 parent_key=parent["key"] if parent else None,
                 parent={"n": parent["n"], "handle": parent["handle"], "anchor": parent["anchor"],
                         "snippet": _snippet(parent["text"]), "opening": parent["opening"]} if parent else None)
        by_key[p["key"]] = p
        out.append(p)
    return out


def _tree(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Numbered posts as a comment tree (an article's collapsed thread), later days' replies included."""
    nodes = {p["key"]: dict(p, children=[], parent_handle=p["parent"]["handle"] if p["parent"] else "")
             for p in posts}
    roots: list[dict[str, Any]] = []
    for p in posts:
        parent = nodes.get(p.get("parent_key") or "")
        (parent["children"] if parent else roots).append(nodes[p["key"]])
    return roots


def forum(days: list[dict[str, Any]], members: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The forum the pages show, from prepared days (oldest first): boards in categories, each with its threads
    newest activity first, counts and its latest post; every thread with its posts; stats for the index."""
    threads: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    seq = 0
    for a in forum_boards.announcements([x["date"] for x in days]):
        a.update(path=f"forum/announcements/{a['slug']}/", thread_id=f"announcements/{a['slug']}", count=1,
                 voices=1, article_path=None, extra=[], seq=-1, bumped=[])
        for c in a["comments"]:
            c.update(anchor=f"c-{a['slug']}-{c['id']}", tags=[])
        threads.append(a)
    for x in days:
        x["still_going"] = []                            # older threads that picked up replies that day
        for t in x["threads"]:
            seq += 1
            t.update(extra=[], seq=seq, bumped=[])
            threads.append(t)
            by_key[t["thread_id"]] = t
        for b in x.get("bumps") or []:
            t = by_key.get(b.get("bump_of", ""))
            if not t:                                    # the thread it continues is gone: drop the replies
                continue
            seq += 1
            t["extra"] += [(x["date"], c) for c in b["comments"]]
            t["seq"] = seq
            t["bumped"].append(x["date"])
            x["still_going"].append(t)
    for t in threads:
        t["posts"] = _posts(t, t.pop("extra"))
        if t["bumped"] and "tree" in t and t["kind"] not in ("botchat", "announcement"):
            t["tree"] = _tree(t["posts"])                # an article's thread with later replies (the editor's)
        t["count"] = len(t["posts"])
        t["voices"] = len({p["handle"] for p in t["posts"]})
        t["starter"] = t["posts"][0]["handle"] if t["kind"] in ("botchat", "announcement") else None
        t["replies"] = t["count"] - (1 if t["starter"] else 0)
        t["last"] = t["posts"][-1]
        t["board_info"] = forum_boards.BOARDS[t["board"]]
        t["category"] = forum_boards.category_of(t["board"])
    order = sorted(threads, key=lambda t: (t["last"]["date"], t["seq"]), reverse=True)
    boards = []
    for slug, b in forum_boards.BOARDS.items():
        mine = [t for t in order if t["board"] == slug]
        mine = [t for t in mine if t.get("pinned")] + [t for t in mine if not t.get("pinned")]
        latest = next((t for t in order if t["board"] == slug), None)
        pages = [mine[i:i + PER_PAGE] for i in range(0, len(mine), PER_PAGE)] or [[]]
        paths = [f"forum/{slug}/"] + [f"forum/{slug}/page/{i}/" for i in range(2, len(pages) + 1)]
        boards.append(dict(b, slug=slug, path=f"forum/{slug}/", threads=mine, pages=pages, page_paths=paths,
                           topics=len(mine), posts=sum(t["count"] for t in mine), latest=latest,
                           category=forum_boards.category_of(slug)))
    by_slug = {b["slug"]: b for b in boards}
    categories = [{"slug": slug, "name": name, "boards": [by_slug[b] for b in names]}
                  for slug, name, names in forum_boards.CATEGORIES]
    joined = [m for m in members.values() if m.get("joined") and m["status"] in ("active", "away")]
    stats = {"topics": len(threads), "posts": sum(t["count"] for t in threads),
             "members": sum(m["status"] in ("active", "away") for m in members.values()),
             "newest": max(joined, key=lambda m: (m["joined"], m["handle"]))["handle"] if joined else None}
    return {"categories": categories, "boards": by_slug, "threads": threads, "latest": order[:8], "stats": stats,
            "announcements": [t for t in threads if t["kind"] == "announcement"]}
