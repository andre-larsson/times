"""The links edition: a complete paper with no AI, built from rule-ranked source data.

Also provides the gaming and deals blocks that AI modes fall back to when a writing call fails.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import quote

from . import rank
from .sources import Harvest, Item
from .sources.itad import store_url
from .text import canonical_url, excerpt, game_key, slugify

RATING_SCORE = {"overwhelmingly positive": 9, "very positive": 8, "positive": 7, "mostly positive": 6,
                "mixed": 5, "mostly negative": 4, "negative": 3}


def build_links_edition(cfg: dict[str, Any], harvest: Harvest, edition_id: str,
                        previous: dict[str, Any] | None = None, reason: str = "") -> dict[str, Any]:
    now = harvest.fetched_at
    search = cfg.get("search") or {}
    hn_cfg = (cfg.get("sources") or {}).get("hackernews") or {}
    links_cfg = cfg.get("links") or {}
    per_section = int(links_cfg.get("per_section", 12))
    per_source = int(links_cfg.get("max_per_source", 4))
    languages = set(links_cfg.get("languages", ["en"]))

    hn_top = top_hn(harvest.hn, int(hn_cfg.get("min_points", 100)), int(links_cfg.get("hn_top", 10)))
    shown = {canonical_url(s["url"]) for s in hn_top}
    previous_urls = {canonical_url(l["url"]) for l in (previous or {}).get("links", [])}

    cands = rank.build_candidates(
        [i for i in harvest.items if i.language in languages], harvest.hn, now,
        max_age_hours=float(search.get("max_item_age_hours", 36)),
        min_points=int(hn_cfg.get("min_points", 100)),
    )
    links: list[dict[str, Any]] = []
    counts: dict[Any, int] = {}
    for c in cands:
        if c.section not in ("ai", "tech") or c.weak:
            continue
        key = canonical_url(c.url)
        by_source = (c.section, c.item.source)
        if (key in shown or key in previous_urls or counts.get(c.section, 0) >= per_section
                or counts.get(by_source, 0) >= per_source):
            continue
        shown.add(key)
        counts[c.section] = counts.get(c.section, 0) + 1
        counts[by_source] = counts.get(by_source, 0) + 1
        links.append(_link(c))
    top = max((l["rank"] for l in links), default=1) or 1
    for l in links:
        l["rank"] = round(l["rank"] / top, 3)

    return {
        "edition_id": edition_id,
        "generated_at": now.isoformat(),
        "mode": "links",
        "reason": reason,
        "llm": {"estimated_usd": 0},
        "stories": [],
        "links": links,
        "hn_top": hn_top,
        "gaming": gaming_blocks(cfg, harvest, cands),
        "deals": deals_block(cfg, harvest),
        "sources": [s.__dict__ for s in harvest.status],
    }


def top_hn(stories: list[dict[str, Any]], min_points: int, limit: int) -> list[dict[str, Any]]:
    keep = [s for s in stories if s["points"] >= min_points][:limit]
    return [{"rank": i + 1, "title": s["title"], "url": s["url"], "points": s["points"],
             "comments": s["comments"], "comments_url": s["comments_url"]} for i, s in enumerate(keep)]


def _link(c: rank.Candidate) -> dict[str, Any]:
    it = c.item
    link = {
        "section": c.section, "title": it.title, "url": it.url, "source": it.source,
        "published_at": it.published_at.isoformat() if it.published_at else None,
        "excerpt": it.excerpt, "rank": c.score,
    }
    if c.hn:
        link["hn"] = c.hn
    also = [{"name": a.source, "url": a.url} for a in c.also if a.source != it.source]
    if also:
        link["also"] = also[:3]
    return link


# ── gaming ───────────────────────────────────────────────────────────────────

def gaming_blocks(cfg: dict[str, Any], harvest: Harvest, cands: list[rank.Candidate]) -> dict[str, Any]:
    g = cfg.get("gaming") or {}
    now = harvest.fetched_at
    reviews = review_block(harvest.items, now, g.get("reviews") or {})
    new_on_pc = new_on_pc_block(harvest.steam.get("new_releases") or [], now, g.get("new_on_pc") or {})
    by_game = {}
    for r in reviews:
        by_game.setdefault(game_key(r["game"]), []).append(r["id"])
    for game in new_on_pc:
        game["review_ids"] = by_game.get(game_key(game["title"]), [])

    spotlight, news = news_blocks(cands, g)
    return {
        "new_on_pc": new_on_pc,
        "reviews": reviews,
        "console_spotlight": spotlight,
        "coming_soon": coming_soon_block(harvest.steam.get("coming_soon") or [], now, g.get("coming_soon") or {}),
        "watch": watch_block(harvest.items, now, g.get("watch") or {}),
        "news": news,
    }


def new_on_pc_block(games: list[dict[str, Any]], now: dt.datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    window = int(cfg.get("window_days", 7))
    min_reviews = int(cfg.get("min_reviews", 50))
    limit, minimum = int(cfg.get("max", 10)), int(cfg.get("min", 3))
    today = now.date()

    def recent(gm: dict[str, Any]) -> bool:
        d = gm.get("release_date")
        return bool(d) and not gm.get("coming_soon") and 0 <= (today - dt.date.fromisoformat(d)).days <= window

    pool = [gm for gm in games if recent(gm) and gm.get("rating_score", 0) >= 5]
    picked = [gm for gm in pool if gm["review_count"] >= min_reviews]
    if len(picked) < minimum:                           # quiet week: relax the popularity bar
        picked = [gm for gm in pool if gm["review_count"] >= 10]
    picked.sort(key=lambda gm: -(gm["review_count"] * (1 + gm.get("percent_positive", 0) / 100)))
    return [{
        "title": gm["title"], "appid": gm["appid"], "release_date": gm["release_date"],
        "steam_rating": gm.get("steam_rating", ""), "image": gm.get("image", ""),
        "store_url": gm["store_url"], "price": None if gm.get("is_free") else gm.get("price"),
        "currency": gm.get("currency", "EUR"),
        "blurb": excerpt(gm.get("short_description"), 110),
        "early_access": gm.get("early_access", False),
        "metacritic_search": metacritic_search(gm["title"]),
        "review_ids": [],
    } for gm in picked[:limit]]


def metacritic_search(title: str) -> str:
    return f"https://www.metacritic.com/search/{quote(title, safe='')}/?category=13"


def review_block(items: list[Item], now: dt.datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    window, fallback = int(cfg.get("window_days", 3)), int(cfg.get("fill_days", 14))
    limit, minimum = int(cfg.get("max", 10)), int(cfg.get("min", 3))
    reviews = sorted((i for i in items if i.kind == "review" and i.published_at),
                     key=lambda i: i.published_at, reverse=True)

    def within(days: int) -> list[Item]:
        return [i for i in reviews if (now - i.published_at).days <= days]

    picked = within(window)
    if len(picked) < minimum:
        picked = within(fallback)[:max(minimum, len(picked))]
    out, seen = [], set()
    for i in picked:
        key = (game_key(i.extra["game"]), i.source)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": f"r-{slugify(i.source, 12)}-{slugify(i.extra['game'], 40)}",
            "game": i.extra["game"], "outlet": _outlet(i.source), "score": i.extra.get("score", ""),
            "verdict": i.extra.get("verdict", ""), "url": i.url, "published_at": i.published_at.isoformat(),
        })
    return out[:limit]


def _outlet(source: str) -> str:
    return {"RPS Reviews": "Rock Paper Shotgun"}.get(source, source)


def news_blocks(cands: list[rank.Candidate], cfg: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    watch_terms = [t.lower() for t in (cfg.get("console_spotlight") or {}).get("watch", [])]
    spot_max = int((cfg.get("console_spotlight") or {}).get("max", 3))
    news_max = int((cfg.get("news") or {}).get("max", 6))
    spotlight, news = [], []
    for c in cands:
        if c.section != "gaming" or c.weak or c.item.language != "en":
            continue
        it = c.item
        sources = [{"name": it.source, "url": it.url}] + [{"name": a.source, "url": a.url} for a in c.also]
        term = next((t for t in watch_terms if t in it.title.lower()), None)
        if term and len(spotlight) < spot_max:
            spotlight.append({"game": term, "platforms": [], "headline": it.title,
                              "summary": it.excerpt, "sources": sources[:3]})
        elif len(news) < news_max:
            news.append({"headline": it.title, "summary": it.excerpt, "url": it.url, "source": it.source})
    return spotlight, news


def coming_soon_block(games: list[dict[str, Any]], now: dt.datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    horizon = int(cfg.get("horizon_days", 180))
    today = now.date()
    dated = []
    for gm in games:
        d = gm.get("release_date")
        if not d or gm.get("date_precision") not in ("day", "month", "quarter"):
            continue
        days = (dt.date.fromisoformat(d) - today).days
        if 0 < days <= horizon or (gm.get("date_precision") != "day" and -31 < days <= horizon):
            dated.append(gm)
    picked = dated[: int(cfg.get("max", 8))]           # Steam's order = most wishlisted first
    picked.sort(key=lambda gm: gm["release_date"])
    return [{"game": gm["title"], "platforms": ["pc"], "date": gm["release_date"],
             "date_precision": gm["date_precision"], "url": gm["store_url"]} for gm in picked]


def watch_block(items: list[Item], now: dt.datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    window, limit = int(cfg.get("window_days", 7)), int(cfg.get("max", 4))
    videos = sorted((i for i in items if i.kind == "video" and i.published_at
                     and (now - i.published_at).days <= window),
                    key=lambda i: i.published_at, reverse=True)
    # alternate channels so one prolific channel can't fill the block
    by_channel: dict[str, list[Item]] = {}
    for v in videos:
        by_channel.setdefault(v.source, []).append(v)
    picked: list[Item] = []
    while len(picked) < limit and any(by_channel.values()):
        for ch in list(by_channel):
            if by_channel[ch] and len(picked) < limit:
                picked.append(by_channel[ch].pop(0))
    picked.sort(key=lambda i: i.published_at, reverse=True)
    return [{"channel": v.extra.get("channel", v.source), "title": v.title, "url": v.url,
             "thumbnail": v.image, "blurb": v.extra.get("blurb", ""),
             "published_at": v.published_at.isoformat()} for v in picked]


# ── deals ────────────────────────────────────────────────────────────────────

def deals_block(cfg: dict[str, Any], harvest: Harvest) -> dict[str, Any]:
    d = cfg.get("deals") or {}
    limit = int((d.get("more") or {}).get("max", 10))
    min_cut = int(d.get("min_cut_pct", 50))
    min_rating = RATING_SCORE.get(str(d.get("min_steam_rating", "Very Positive")).lower(), 8)
    block: dict[str, Any] = {"checked_at": harvest.fetched_at.isoformat(), "featured": [], "more": []}

    def live(expires: str | None) -> bool:
        return not expires or dt.datetime.fromisoformat(expires.replace("Z", "+00:00")) > harvest.fetched_at

    if harvest.itad:
        deals = [x for x in harvest.itad if x.get("cut", 0) >= min_cut and live(x.get("expires"))
                 and RATING_SCORE.get((x.get("steam_rating") or "").lower(), 0) >= min_rating]
        deals.sort(key=lambda x: (not x.get("new_low"), not x.get("lowest_ever"),
                                  x.get("rank") or 10**6, -(x.get("steam_count") or 0)))
        block["source"] = "itad"
        block["more"] = [{
            "game": x["game"], "shop": x["shop"], "price": x["price"], "regular": x["regular"],
            "currency": x["currency"], "cut": x["cut"], "lowest_ever": x["lowest_ever"],
            "expires": x.get("expires"), "steam_rating": x.get("steam_rating", ""),
            "metascore": x.get("metascore"), "url": store_url(x) or x.get("itad_url", ""),
        } for x in deals[:limit]]
        return block

    specials = [gm for gm in harvest.steam.get("specials") or []
                if gm.get("cut", 0) >= min_cut and gm.get("rating_score", 0) >= min_rating
                and live(gm.get("discount_end"))
                and gm.get("review_count", 0) >= 500 and gm.get("price") is not None]
    specials.sort(key=lambda gm: -gm["review_count"])
    block["source"] = "steam"
    block["more"] = [{
        "game": gm["title"], "shop": "Steam", "price": gm["price"], "regular": gm["regular"],
        "currency": gm["currency"], "cut": gm["cut"], "lowest_ever": False,
        "expires": gm.get("discount_end"), "steam_rating": gm.get("steam_rating", ""),
        "url": gm["store_url"],
    } for gm in specials[:limit]]
    return block
