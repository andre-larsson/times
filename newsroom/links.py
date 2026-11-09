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
        **({"critics": gm["critics"]} if gm.get("critics") else {}),
    } for gm in picked[:limit]]


def metacritic_search(title: str) -> str:
    return f"https://www.metacritic.com/search/{quote(title, safe='')}/?category=13"


def review_candidates(items: list[Item], now: dt.datetime, cfg: dict[str, Any]) -> list[Item]:
    """Game reviews from the last `fill_days`, newest first, minus console-only games: a review from a
    multi-platform outlet (multi_platform in its feed config) is dropped when IsThereAnyDeal knows the game
    but sells it on no PC store (sources/critics.py sets on_pc). Games it can't find, and every review
    when the check didn't run, stay."""
    fallback = int(cfg.get("fill_days", 14))
    return sorted((i for i in items if i.kind == "review" and i.published_at
                   and (now - i.published_at).days <= fallback
                   and not (i.extra.get("multi_platform") and i.extra.get("on_pc") is False)),
                  key=lambda i: i.published_at, reverse=True)


def review_block(items: list[Item], now: dt.datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    window = int(cfg.get("window_days", 3))
    limit, minimum = int(cfg.get("max", 10)), int(cfg.get("min", 3))
    per_game = int(cfg.get("per_game", 2))            # several outlets on one big game: keep the list varied
    reviews = review_candidates(items, now, cfg)
    picked = [i for i in reviews if (now - i.published_at).days <= window]
    if len(picked) < minimum:
        picked = reviews[:max(minimum, len(picked))]
    out, seen, games = [], set(), {}
    for i in picked:
        game, outlet = game_key(i.extra["game"]), _outlet(i.source)
        if (game, outlet) in seen or games.get(game, 0) >= per_game:
            continue
        seen.add((game, outlet))
        games[game] = games.get(game, 0) + 1
        out.append({
            "id": f"r-{slugify(outlet, 12)}-{slugify(i.extra['game'], 40)}",
            "game": i.extra["game"], "outlet": outlet, "score": i.extra.get("score", ""),
            "verdict": i.extra.get("verdict", ""), "url": i.url, "published_at": i.published_at.isoformat(),
            **({"critics": i.extra["critics"]} if i.extra.get("critics") else {}),
        })
    return out[:limit]


def _outlet(source: str) -> str:
    """The outlet's name: one outlet can have two feeds ("PC Gamer" and "PC Gamer Reviews")."""
    if source in OUTLETS:
        return OUTLETS[source]
    return source[: -len(" Reviews")] if source.endswith(" Reviews") else source


OUTLETS = {"RPS Reviews": "Rock Paper Shotgun"}


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

def mix_deals(deals: list[dict[str, Any]], mix: dict[str, Any], limit: int, genres: list[str],
              day: dt.date) -> list[dict[str, Any]]:
    """The more-deals list from the ITAD pools (`deals` already filtered and in order).

    `mix.popular` from the popular list, then `mix.hidden` hidden gems and `mix.genre` genre picks (one
    per genre; the genres take turns by day, skipping one with nothing today). Every game appears once,
    and slots a pool can't fill go to the next popular deals. Each deal gets `pick` (and `genre`).
    The kinds are interleaved, so the front page's first few rows are a fair sample of the list.
    """
    def pool(name: str) -> list[dict[str, Any]]:
        return [x for x in deals if name in (x.get("pools") or ["popular"])]

    popular = pool("popular")
    seen = {x["itad_id"] for x in popular[: int(mix.get("popular", limit))]}
    extra: list[dict[str, Any]] = []

    def take(candidates: list[dict[str, Any]], n: int, **label: str) -> None:
        for x in candidates:
            if n <= 0 or len(extra) >= limit:
                return
            if x["itad_id"] not in seen:
                seen.add(x["itad_id"])
                extra.append({**x, **label})
                n -= 1

    take(pool("hidden"), int(mix.get("hidden", 0)), pick="hidden")
    slots = int(mix.get("genre", 0))
    if genres and slots:
        start = day.toordinal() * slots % len(genres)
        for g in genres[start:] + genres[:start]:
            if slots <= 0:
                break
            before = len(extra)
            take(pool(f"genre:{g}"), 1, pick="genre", genre=g)
            slots -= len(extra) - before
    chosen = {x["itad_id"] for x in extra}
    rest = [{**x, "pick": "popular"} for x in popular if x["itad_id"] not in chosen]
    return interleave(rest[: max(0, limit - len(extra))],
                      [x for x in extra if x["pick"] == "hidden"],
                      [x for x in extra if x["pick"] == "genre"])[:limit]


def interleave(*lists: list[Any]) -> list[Any]:
    """Merge lists evenly, each in its own order: 10, 5 and 5 items come out as A B C A, A B C A, ...
    (ties go to the earlier list)."""
    lists = tuple(lst for lst in lists if lst)
    pos = [0] * len(lists)
    out: list[Any] = []
    while len(out) < sum(map(len, lists)):
        k = min((i for i in range(len(lists)) if pos[i] < len(lists[i])), key=lambda i: pos[i] / len(lists[i]))
        out.append(lists[k][pos[k]])
        pos[k] += 1
    return out


def deal_shelves(deals: list[dict[str, Any]], taken: set[str], genres: list[str], per_shelf: int
                 ) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """The rest of today's deals for the Deals page, one shelf per ITAD list: popular, hidden gems, then
    each genre. Returns (pool, name, deals) per shelf that has any; `deals` is already filtered and in order.

    Every game appears once on the page: the rated list keeps its games, and a game on several lists goes
    on the most specific shelf (a genre, then hidden gems, then popular)."""
    if per_shelf <= 0:
        return []
    taken = set(taken)

    def fill(pool: str) -> list[dict[str, Any]]:
        out = []
        for x in deals:
            if len(out) >= per_shelf:
                break
            if pool in (x.get("pools") or ["popular"]) and x["itad_id"] not in taken:
                taken.add(x["itad_id"])
                out.append(x)
        return out

    shelves = {f"genre:{g}": (g, fill(f"genre:{g}")) for g in genres}
    shelves["hidden"] = ("Hidden gems", fill("hidden"))
    shelves["popular"] = ("Popular", fill("popular"))
    order = ["popular", "hidden"] + [f"genre:{g}" for g in genres]
    return [(p, *shelves[p]) for p in order if shelves[p][1]]


def _itad_row(x: dict[str, Any]) -> dict[str, Any]:
    """A deal as the edition stores it (the rated list and the shelves)."""
    return {
        "game": x["game"], "shop": x["shop"], "price": x["price"], "regular": x["regular"],
        "currency": x["currency"], "cut": x["cut"], "lowest_ever": x["lowest_ever"],
        "expires": x.get("expires"), "steam_rating": x.get("steam_rating", ""),
        "metascore": x.get("metascore"), "url": store_url(x) or x.get("itad_url", ""),
        **({"pick": x["pick"]} if x.get("pick") else {}), **({"genre": x["genre"]} if x.get("genre") else {}),
        **({"tags": x["tags"]} if x.get("tags") else {}),
    }


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
        genres = list(((cfg.get("sources") or {}).get("itad", {}).get("genres") or {}).get("tags") or {})
        rated = mix_deals(deals, d.get("mix") or {}, limit, genres, harvest.fetched_at.date())
        block["source"] = "itad"
        block["more"] = [_itad_row(x) for x in rated]
        block["shelves"] = [
            {"pool": pool, "name": name, "deals": [_itad_row(x) for x in rows]}
            for pool, name, rows in deal_shelves(deals, {x["itad_id"] for x in rated}, genres,
                                                 int(d.get("shelves", 0)))
        ]
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
