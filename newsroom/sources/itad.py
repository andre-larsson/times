"""IsThereAnyDeal: current deals for one country, filtered to big cuts near the lowest price ever.

Several lists, merged per game: the popular list (ITAD's popularity rank), hidden gems (few but very
positive Steam reviews) and one list per genre group in sources.itad.genres (Steam tags).

API docs: https://docs.isthereanydeal.com/ (deals list `/deals/v2`, game info `/games/info/v2`).
The key goes in the `key` query parameter; it is never logged (see http._safe).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..http import Client, FetchError

API = "https://api.isthereanydeal.com"
STEAM_SHOP_ID = 61
GAME_TYPE = 1
INFO_KEYS = ("appid", "steam_score", "steam_count", "steam_rating", "metascore", "rank", "release_date",
             "tags", "itad_url")


def steam_label(percent: int | None, count: int | None) -> str:
    """Steam's review label from a score and a review count (Steam's own thresholds)."""
    if percent is None or not count or count < 10:
        return ""
    if percent >= 80:
        if percent >= 95 and count >= 500:
            return "Overwhelmingly Positive"
        return "Very Positive" if count >= 50 else "Positive"
    if percent >= 70:
        return "Mostly Positive"
    if percent >= 40:
        return "Mixed"
    if percent >= 20:
        return "Mostly Negative"
    if count >= 500:
        return "Overwhelmingly Negative"
    return "Very Negative" if count >= 50 else "Negative"


@dataclass
class Query:
    """One deals list: the popular list, hidden gems, or one genre group."""
    pool: str                     # "popular", "hidden" or "genre:<name>"
    label: str                    # its row in the Harvest status
    filters: dict[str, Any]
    limit: int
    info_limit: int               # how many of its deals to look up (Steam rating, Metascore, tags)


def queries(cfg: dict[str, Any], deals_cfg: dict[str, Any]) -> list[Query]:
    """The popular list first (the section's backbone), then hidden gems, then one query per genre."""
    def filters(steam_percent: Any, reviews_min: Any, reviews_max: Any = None, **extra: Any) -> dict[str, Any]:
        # Percent ranges (0-100) need an explicit max: ITAD reads "max": null there as 0, which matched
        # nothing (checked against the live API, 2026-11-06), although its spec says null means unbounded.
        # Count and price ranges take null as unbounded.
        return {
            "cut": {"min": int(deals_cfg.get("min_cut_pct", 50)), "max": 100},
            "hlperc": float(deals_cfg.get("near_low_pct", 10)),
            "type": [GAME_TYPE],
            "steamPerc": {"min": int(steam_percent), "max": 100},
            "steamCount": {"min": int(reviews_min), "max": None if reviews_max is None else int(reviews_max)},
            **extra,
        }

    out = [Query("popular", "IsThereAnyDeal",
                 filters(cfg.get("min_steam_percent", 80), cfg.get("min_steam_reviews", 500)),
                 int(cfg.get("limit", 100)), int(cfg.get("info_limit", 25)))]
    hidden = cfg.get("hidden") or {}
    if hidden:
        lo, hi = hidden.get("steam_reviews", [200, 5000])
        extra = {"regular": {"min": float(hidden["min_regular"]), "max": None}} if hidden.get("min_regular") else {}
        out.append(Query("hidden", "IsThereAnyDeal hidden gems",
                         filters(hidden.get("min_steam_percent", 90), lo, hi, **extra),
                         int(hidden.get("limit", 40)), int(hidden.get("info_limit", 10))))
    genres = cfg.get("genres") or {}
    lo, hi = genres.get("steam_reviews", [100, None])
    for name, tags in (genres.get("tags") or {}).items():
        out.append(Query(f"genre:{name}", f"IsThereAnyDeal {name}",
                         filters(genres.get("min_steam_percent", 85), lo, hi, tagsUnion=list(tags)),
                         int(genres.get("limit", 30)), int(genres.get("info_limit", 5))))
    return out


def fetch_query(client: Client, q: Query, cfg: dict[str, Any], deals_cfg: dict[str, Any], key: str,
                info_cache: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One deals list, with game info for its first `q.info_limit` deals (looked up once per run)."""
    params = {
        "key": key, "country": deals_cfg.get("country", "SE"), "limit": q.limit,
        "sort": cfg.get("sort", "rank"), "filter": json.dumps(q.filters),
    }
    data = client.json(f"{API}/deals/v2", params=params)
    if not isinstance(data, dict) or "list" not in data:
        raise FetchError("unexpected IsThereAnyDeal response")

    deals = [_deal(x) for x in data["list"] if (x.get("type") or "game") == "game" and not x.get("mature")]
    for d in deals[: q.info_limit]:                       # ratings, Metascore, tags, Steam app id
        if d["itad_id"] not in info_cache:
            try:
                info_cache[d["itad_id"]] = client.json(f"{API}/games/info/v2", params={"key": key, "id": d["itad_id"]})
            except FetchError:
                continue
        _add_info(d, info_cache[d["itad_id"]])
    return deals


def merge(lists: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """One entry per game, listing every pool it came from; the first list's copy wins, plus any info
    another list looked up."""
    merged: dict[str, dict[str, Any]] = {}
    for pool, deals in lists:
        for d in deals:
            m = merged.setdefault(d["itad_id"], {**d, "pools": []})
            if "steam_rating" not in m and "steam_rating" in d:
                m.update({k: d[k] for k in INFO_KEYS if k in d})
            if pool not in m["pools"]:
                m["pools"].append(pool)
    return list(merged.values())


def _deal(x: dict[str, Any]) -> dict[str, Any]:
    deal = x.get("deal") or {}
    price, regular = deal.get("price") or {}, deal.get("regular") or {}
    low = (deal.get("historyLow") or {}).get("amount")
    flag = deal.get("flag")
    return {
        "itad_id": x.get("id"),
        "game": x.get("title", ""),
        "shop": (deal.get("shop") or {}).get("name", ""),
        "shop_id": (deal.get("shop") or {}).get("id"),
        "price": price.get("amount"),
        "regular": regular.get("amount"),
        "currency": price.get("currency", "EUR"),
        "cut": deal.get("cut", 0),
        "history_low": low,
        "lowest_ever": flag in ("H", "N") or (low is not None and price.get("amount") is not None
                                              and price["amount"] <= low),
        "new_low": flag == "N",
        "expires": deal.get("expiry"),
        "itad_url": f"https://isthereanydeal.com/game/{x.get('slug')}/" if x.get("slug") else "",
        "url": "",
        "image": (x.get("assets") or {}).get("banner300", ""),
    }


def _add_info(d: dict[str, Any], info: dict[str, Any]) -> None:
    reviews = {r.get("source"): r for r in info.get("reviews") or []}
    steam = reviews.get("Steam") or {}
    meta = reviews.get("Metascore") or {}
    d["appid"] = info.get("appid")
    d["steam_score"] = steam.get("score")
    d["steam_count"] = steam.get("count")
    d["steam_rating"] = steam_label(steam.get("score"), steam.get("count"))
    d["metascore"] = meta.get("score")
    d["rank"] = (info.get("stats") or {}).get("rank")
    d["release_date"] = info.get("releaseDate")
    d["tags"] = [t for t in info.get("tags") or [] if isinstance(t, str)][:6]
    if info.get("urls", {}).get("game"):
        d["itad_url"] = info["urls"]["game"]


def store_url(d: dict[str, Any]) -> str:
    """A plain store link (no affiliate redirect): Steam's page when the deal is on Steam,
    otherwise the IsThereAnyDeal game page, which lists every shop's price."""
    if d.get("shop_id") == STEAM_SHOP_ID and d.get("appid"):
        return f"https://store.steampowered.com/app/{d['appid']}/"
    return d.get("itad_url", "")
