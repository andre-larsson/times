"""The search index: every story, brief, column and gaming item, for the Search page (static/search.js).

Written at build time to search/index.json. Short keys keep it small (it grows by roughly 15 KB per
edition before compression): h headline, d one-line summary, p extra text that is searched but not
shown, s section slug, n kind ("" for our own stories), t date (YYYY-MM-DD), u link, o source names.
Deals and release lists are left out: they're prices and listings, not news.
"""

from __future__ import annotations

from typing import Any, Callable

KINDS = {"featured": "", "medium": "", "brief": "Brief"}


def _names(sources: list[dict[str, Any]] | None) -> str:
    return ", ".join(dict.fromkeys(s.get("name", "") for s in sources or [] if s.get("name")))


def build_index(editions: list[dict[str, Any]], article_url: Callable[[dict[str, Any]], str]) -> list[dict[str, str]]:
    """Index rows, newest first. An item seen in several editions (gaming news often is) keeps its first date."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(h: str, d: str, s: str, n: str, t: str, u: str, o: str = "", p: str = "") -> None:
        if not h or not u or u == "#" or u in seen:
            return
        seen.add(u)
        row = {"h": " ".join(h.split()), "d": " ".join((d or "").split()), "s": s, "n": n, "t": t, "u": u, "o": o}
        if p:
            row["p"] = " ".join(p.split())
        rows.append(row)

    for ed in sorted(editions, key=lambda e: e["edition_id"]):
        day = ed["edition_id"][:10]
        for st in ed.get("stories", []):
            add(st.get("headline", ""), st.get("dek", ""), st.get("section", ""), KINDS.get(st.get("tier"), ""),
                day, article_url(st), _names(st.get("sources")), " ".join(st.get("key_points") or []))
        col = ed.get("opinion")
        if col:
            add(col.get("headline", ""), col.get("dek", ""), "opinion", "Column", day, article_url(col),
                p=col.get("topic", ""))
        for link in ed.get("links", []):
            add(link.get("title", ""), link.get("excerpt", ""), link.get("section", "tech"), "Link", day,
                link.get("url", ""), link.get("source", ""))
        g = ed.get("gaming") or {}
        for n in g.get("news", []):
            add(n.get("headline", ""), n.get("summary", ""), "gaming", "News", day, n.get("url", ""), n.get("source", ""))
        for c in g.get("console_spotlight", []):
            srcs = c.get("sources") or []
            add(c.get("headline", ""), c.get("summary", ""), "gaming", "Consoles", day,
                srcs[0].get("url", "") if srcs else "", _names(srcs), c.get("game", ""))
        for r in g.get("reviews", []):
            score = f" ({r['score']})" if r.get("score") else ""
            add(f"{r.get('game', '')}: {r.get('outlet', '')} review{score}", r.get("verdict", ""), "gaming",
                "Review", day, r.get("url", ""), r.get("outlet", ""))
    return sorted(rows, key=lambda r: r["t"], reverse=True)       # stable: within a day, the paper's order
