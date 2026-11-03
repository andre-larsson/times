"""Hacker News front page via the Algolia API (no key, generous limits)."""

from __future__ import annotations

from typing import Any

from ..http import Client

API = "https://hn.algolia.com/api/v1/search"


def front_page(client: Client, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Current front-page stories, highest points first."""
    data = client.json(API, params={"tags": "front_page", "hitsPerPage": cfg.get("hits", 50)})
    stories = []
    for h in data.get("hits", []):
        item_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        stories.append({
            "title": h.get("title") or "",
            "url": h.get("url") or item_url,          # Ask/Show HN without a link → the thread
            "points": int(h.get("points") or 0),
            "comments": int(h.get("num_comments") or 0),
            "comments_url": item_url,
            "created_at": h.get("created_at"),
            "self_post": not h.get("url"),
        })
    stories.sort(key=lambda s: -s["points"])
    return stories
