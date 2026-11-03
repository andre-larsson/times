"""IsThereAnyDeal: current deals for one country, filtered to big cuts near the lowest price ever.

API docs: https://docs.isthereanydeal.com/ (deals list `/deals/v2`, game info `/games/info/v2`).
The key goes in the `key` query parameter; it is never logged (see http._safe).
"""

from __future__ import annotations

import json
from typing import Any

from ..http import Client, FetchError

API = "https://api.isthereanydeal.com"
STEAM_SHOP_ID = 61
GAME_TYPE = 1


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


def fetch_deals(client: Client, cfg: dict[str, Any], deals_cfg: dict[str, Any], key: str) -> list[dict[str, Any]]:
    filters = {
        "cut": {"min": int(deals_cfg.get("min_cut_pct", 50)), "max": None},
        "hlperc": float(deals_cfg.get("near_low_pct", 10)),
        "type": [GAME_TYPE],
        "steamPerc": {"min": int(cfg.get("min_steam_percent", 80)), "max": None},
        "steamCount": {"min": int(cfg.get("min_steam_reviews", 500)), "max": None},
    }
    params = {
        "key": key, "country": deals_cfg.get("country", "SE"), "limit": cfg.get("limit", 100),
        "sort": cfg.get("sort", "-cut"), "filter": json.dumps(filters),
    }
    data = client.json(f"{API}/deals/v2", params=params)
    if not isinstance(data, dict) or "list" not in data:
        raise FetchError("unexpected IsThereAnyDeal response")

    deals = [_deal(x) for x in data["list"] if (x.get("type") or "game") == "game" and not x.get("mature")]
    for d in deals[: cfg.get("info_limit", 25)]:          # ratings, Metascore, Steam app id
        try:
            info = client.json(f"{API}/games/info/v2", params={"key": key, "id": d["itad_id"]})
        except FetchError:
            continue
        _add_info(d, info)
    return deals


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
    if info.get("urls", {}).get("game"):
        d["itad_url"] = info["urls"]["game"]


def store_url(d: dict[str, Any]) -> str:
    """A plain store link (no affiliate redirect): Steam's page when the deal is on Steam,
    otherwise the IsThereAnyDeal game page, which lists every shop's price."""
    if d.get("shop_id") == STEAM_SHOP_ID and d.get("appid"):
        return f"https://store.steampowered.com/app/{d['appid']}/"
    return d.get("itad_url", "")
