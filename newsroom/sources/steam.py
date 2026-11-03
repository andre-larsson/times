"""Steam store data: popular new releases, most-wishlisted upcoming games, popular specials.

Uses two public, keyless endpoints: the store search (JSON mode) to get lists of app ids, and
IStoreBrowseService/GetItems to get release dates, user-review summaries, prices and art for up to
50 apps per call. Both are unofficial for third parties, so everything degrades gracefully.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from ..http import Client, FetchError

SEARCH = "https://store.steampowered.com/search/results/"
GET_ITEMS = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1"
ASSET_BASE = "https://shared.akamai.steamstatic.com/store_item_assets/"
GAME_TYPE = 0                                   # StoreItem.type: 0 game, 4 DLC, 6 software…

# list name → search parameters
LISTS = {
    "new_releases": {"filter": "popularnew", "sort_by": "Released_DESC", "count": 100},
    "coming_soon":  {"filter": "popularwishlist", "count": 100},
    "specials":     {"specials": 1, "filter": "topsellers", "count": 100},
}
PRECISION = {"date_full": "day", "date_month": "month", "date_quarter": "quarter", "date_year": "year"}
APP_ID = re.compile(r"/apps/(\d+)/")


def fetch_list(client: Client, cfg: dict[str, Any], name: str, now: dt.datetime) -> list[dict[str, Any]]:
    if name not in LISTS:
        raise ValueError(f"unknown Steam list {name!r}; use one of {', '.join(LISTS)}")
    cc = cfg.get("cc", "se")
    params = {"json": 1, "cc": cc, "l": "english", "category1": 998, **LISTS[name]}
    data = client.json(SEARCH, params=params)
    ids = []
    for it in data.get("items", []):
        m = APP_ID.search(it.get("logo", ""))
        if m and int(m.group(1)) not in ids:
            ids.append(int(m.group(1)))
    if not ids:
        raise FetchError(f"Steam search {name} returned no apps")
    return [g for g in get_items(client, ids, cc) if g]


def get_items(client: Client, appids: list[int], cc: str = "se") -> list[dict[str, Any]]:
    games = []
    for i in range(0, len(appids), 50):
        query = {
            "ids": [{"appid": a} for a in appids[i:i + 50]],
            "context": {"language": "english", "country_code": cc.upper()},
            "data_request": {"include_assets": True, "include_release": True,
                             "include_reviews": True, "include_basic_info": True},
        }
        data = client.json(GET_ITEMS, params={"input_json": json.dumps(query)})
        games += [normalize(it) for it in (data.get("response") or {}).get("store_items", [])]
    return games


def normalize(it: dict[str, Any]) -> dict[str, Any] | None:
    if it.get("success", 1) != 1 or not it.get("visible", True) or it.get("type") != GAME_TYPE:
        return None
    appid = it.get("appid") or it.get("id")
    rel = it.get("release") or {}
    reviews = (it.get("reviews") or {}).get("summary_filtered") or {}
    buy = it.get("best_purchase_option") or {}
    ts = rel.get("steam_release_date")
    coming = bool(rel.get("is_coming_soon"))
    precision = PRECISION.get(rel.get("coming_soon_display", ""), None) if coming else "day"
    discount_end = next((d.get("discount_end_date") for d in buy.get("active_discounts") or []
                         if d.get("discount_end_date")), None)
    count = int(reviews.get("review_count") or 0)
    return {
        "appid": appid,
        "title": it.get("name", "").strip(),
        "store_url": f"https://store.steampowered.com/app/{appid}/",
        "release_date": _date(ts) if ts and precision else None,
        "date_precision": precision,
        "coming_soon": coming,
        "early_access": bool(rel.get("is_early_access")),
        "left_early_access": bool(rel.get("release_from_early_access_date")),
        "steam_rating": reviews.get("review_score_label", "") if count >= 10 else "",
        "rating_score": int(reviews.get("review_score") or 0),
        "review_count": count,
        "percent_positive": int(reviews.get("percent_positive") or 0),
        "price": _cents(buy.get("final_price_in_cents")),
        "regular": _cents(buy.get("original_price_in_cents")),
        "cut": int(buy.get("discount_pct") or 0),
        "currency": _currency(buy.get("formatted_final_price", "")),
        "discount_end": _iso(discount_end) if discount_end else None,
        "is_free": bool(it.get("is_free")),
        "image": _asset(it.get("assets") or {}),
        "short_description": ((it.get("basic_info") or {}).get("short_description") or "").strip(),
    }


def _asset(assets: dict[str, Any]) -> str:
    fmt = assets.get("asset_url_format")
    name = assets.get("header") or assets.get("main_capsule")
    return ASSET_BASE + fmt.replace("${FILENAME}", name) if fmt and name else ""


def _date(ts: int) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date().isoformat()


def _iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).isoformat()


def _cents(value: Any) -> float | None:
    try:
        return int(value) / 100
    except (TypeError, ValueError):
        return None


def _currency(formatted: str) -> str:
    if "€" in formatted:
        return "EUR"
    if "kr" in formatted:
        return "SEK"
    if "£" in formatted:
        return "GBP"
    if "$" in formatted:
        return "USD"
    return "EUR"
