"""Fetch every configured source into one Harvest. A failing source never stops the run."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..http import Client, FetchError


@dataclass
class Item:
    """One article, review or video from a feed, normalized."""
    source: str
    title: str
    url: str
    published_at: dt.datetime | None = None
    excerpt: str = ""
    kind: str = "news"                    # news | review | video | deal
    sections: list[str] = field(default_factory=list)   # allowed sections, from config
    language: str = "en"
    categories: list[str] = field(default_factory=list)
    image: str = ""
    weight: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)  # source-specific: score, hn, game, verdict…

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        return d


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    ms: int = 0
    error: str = ""
    skipped: bool = False


@dataclass
class Harvest:
    fetched_at: dt.datetime
    items: list[Item] = field(default_factory=list)
    hn: list[dict[str, Any]] = field(default_factory=list)
    steam: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    itad: list[dict[str, Any]] | None = None             # None: not configured (no key)
    status: list[SourceStatus] = field(default_factory=list)

    def run(self, name: str, fn: Callable[[], Any], count: Callable[[Any], int] = len) -> Any:
        """Run one fetcher, record its status, return its result (or None on failure)."""
        start = time.monotonic()
        try:
            result = fn()
        except FetchError as exc:
            self.status.append(SourceStatus(name, False, ms=_ms(start), error=str(exc)[:200]))
            return None
        except Exception as exc:  # noqa: BLE001 - a broken source must never stop the paper
            msg = f"{type(exc).__name__}: {exc}".split("?", 1)[0]          # never log query strings
            self.status.append(SourceStatus(name, False, ms=_ms(start), error=msg[:200]))
            return None
        self.status.append(SourceStatus(name, True, count=count(result), ms=_ms(start)))
        return result


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def fetch_all(cfg: dict[str, Any], client: Client, now: dt.datetime | None = None,
              itad_key: str | None = None) -> Harvest:
    from . import feeds, hackernews, itad, steam

    now = now or dt.datetime.now(dt.timezone.utc)
    src = cfg.get("sources") or {}
    h = Harvest(fetched_at=now)

    hn_cfg = src.get("hackernews")
    if hn_cfg:
        h.hn = h.run("Hacker News", lambda: hackernews.front_page(client, hn_cfg)) or []

    for f in src.get("feeds", []):
        h.items += h.run(f["name"], lambda f=f: feeds.fetch_feed(client, f)) or []
    for g in src.get("google_news", []):
        h.items += h.run(f"{g['name']} (Google News)", lambda g=g: feeds.fetch_google_news(client, g)) or []
    for y in src.get("youtube", []):
        h.items += h.run(f"{y['name']} (YouTube)", lambda y=y: feeds.fetch_youtube(client, y)) or []

    steam_cfg = src.get("steam")
    if steam_cfg:
        lists = steam_cfg.get("lists", [])
        for key in lists:
            h.steam[key] = h.run(f"Steam {key.replace('_', ' ')}",
                                 lambda key=key: steam.fetch_list(client, steam_cfg, key, now)) or []

    itad_cfg = src.get("itad") or {}
    if itad_cfg.get("enabled"):
        if itad_key:
            h.itad = h.run("IsThereAnyDeal",
                           lambda: itad.fetch_deals(client, itad_cfg, cfg.get("deals") or {}, itad_key))
        else:
            h.status.append(SourceStatus("IsThereAnyDeal", False, skipped=True,
                                         error="ITAD_API_KEY not set; using Steam specials"))
    return h
