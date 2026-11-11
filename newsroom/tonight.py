"""Small factual catalog for the browser's Play / Watch picker. No generated recommendations."""
from __future__ import annotations

import datetime as dt
import math
from typing import Any
from urllib.parse import urlsplit


def catalog(deals: dict[str, Any], gaming: dict[str, Any], screen: dict[str, Any],
            picks: dict[str, Any] | None, now: dt.datetime) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    def link(value: Any) -> str:
        value = str(value or "")
        return value if urlsplit(value).scheme in ("http", "https") else ""

    games = (deals.get("featured") or []) + (deals.get("more") or [])
    games += [d for s in deals.get("shelves") or [] for d in s.get("deals") or []]
    games += gaming.get("new_on_pc") or []
    for g in games:
        title, url = g.get("game") or g.get("title"), link(g.get("url") or g.get("store_url"))
        if not title or not url or g.get("verdict") == "avoid":
            continue
        expires = g.get("expires")
        if expires:
            try:
                end = dt.datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=dt.timezone.utc)
                if end <= now:
                    continue
            except ValueError:
                continue
        price = g.get("price")
        if not isinstance(price, (float, int)) or isinstance(price, bool) or not math.isfinite(price) or price < 0:
            price = None
        currency = str(g.get("currency") or "").upper()
        if len(currency) != 3 or not currency.isalpha():
            price, currency = None, ""
        genres = list(dict.fromkeys(([g["genre"]] if g.get("genre") else []) + (g.get("tags") or [])))
        key = "play:" + str(title).casefold()
        rows.setdefault(key, {"id": key, "mode": "play", "kind": "game", "title": title, "url": url,
                              "genres": genres, "price": price, "currency": currency,
                              "services": [], "summary": g.get("advice") or g.get("blurb") or "",
                              "rating": g.get("steam_rating") or "", "expires": expires,
                              "checked": deals.get("checked_at") if g.get("game") else ""})
    titles = [t for s in screen.get("new") or [] for t in s.get("titles") or []]
    titles += screen.get("classics") or []
    for group in ("films", "series"):
        titles += [r["match"] for r in (screen.get("top10") or {}).get(group) or [] if r.get("match")]
    dated = [(t, screen.get("checked_at")) for t in titles]
    dated += [(t, (picks or {}).get("edition_generated_at")) for t in (picks or {}).get("titles") or []]
    for t, checked in dated:
        services = [s["service"] for s in t.get("on") or [] if s.get("service")]
        url = link(t.get("url"))
        if not t.get("title") or not url or not services or t.get("kind") not in ("movie", "tv"):
            continue
        key = "watch:" + str(t.get("key") or t["title"].casefold())
        if key in rows:
            # Current service tags win over last week's picks; don't revive an old entitlement.
            continue
        rows[key] = {"id": key, "mode": "watch", "kind": t["kind"], "title": t["title"], "url": url,
                     "genres": t.get("genres") or [], "services": sorted(set(services)),
                     "summary": t.get("reason") or t.get("overview") or "", "price": None, "currency": "",
                     "rating": f"{t['rating']}/10 on TMDB" if t.get("rating") else "",
                     "expires": None, "checked": checked}
    return list(rows.values())
