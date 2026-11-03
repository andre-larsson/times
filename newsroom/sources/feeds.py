"""RSS/Atom sources: news feeds, review feeds, Google News searches and YouTube channels."""

from __future__ import annotations

import calendar
import datetime as dt
import re
from typing import Any
from urllib.parse import quote_plus

import feedparser

from ..http import Client, FetchError
from ..text import domain, excerpt, first_sentence, plain
from . import Item

# "Game review – tagline", "Game Review - tagline", "Game review: tagline", "Game review"
REVIEW_TITLE = re.compile(r"^(?P<game>.+?)\s+review\b\s*(?:[–—:|-]\s*(?P<verdict>.+))?$", re.I)
SCORE_PATTERNS = [
    re.compile(r"Betyg\s+(\d{1,2})\s+av\s+10", re.I),          # MISSIL
    re.compile(r"\bScore:\s*(\d{1,3}(?:/\d{1,3})?)", re.I),
]
BADGE_TAGS = {"bestest bests": "Bestest Best", "recommended": "Recommended", "essential": "Essential"}
HARDWARE_HINTS = re.compile(r"/hardware/|/peripherals?/|/pc-components/", re.I)


def _parse(content: bytes, url: str) -> feedparser.FeedParserDict:
    parsed = feedparser.parse(content)
    if not parsed.entries and parsed.get("bozo"):
        raise FetchError(f"unparseable feed from {url.split('?', 1)[0]}")
    return parsed


def _published(entry: Any) -> dt.datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return dt.datetime.fromtimestamp(calendar.timegm(t), dt.timezone.utc) if t else None


def _image(entry: Any) -> str:
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key) or []:
            if m.get("url") and not m["url"].startswith("https://www.youtube.com/v/"):
                return m["url"]
    return ""


def _content(entry: Any) -> str:
    return " ".join(c.get("value", "") for c in entry.get("content") or [])


def fetch_feed(client: Client, cfg: dict[str, Any]) -> list[Item]:
    parsed = _parse(client.get(cfg["url"]).content, cfg["url"])
    skip_cats = {c.lower() for c in cfg.get("skip_categories", [])}
    skip_paths = [p.lower() for p in cfg.get("skip_paths", [])]
    keep_paths = [p.lower() for p in cfg.get("keep_paths", [])]
    review_url = re.compile(cfg["reviews_url"], re.I) if cfg.get("reviews_url") else None
    items: list[Item] = []

    for e in parsed.entries[: cfg.get("max_items", 60)]:
        url, title = e.get("link", ""), plain(e.get("title"))
        if not url or not title:
            continue
        cats = [t.get("term", "") for t in e.get("tags") or [] if t.get("term")]
        # the first category is the section on most news sites (Ars: "AI", "Science", …)
        if cats and cats[0].lower() in skip_cats:
            continue
        low = url.lower()
        if any(p in low for p in skip_paths) and not any(p in low for p in keep_paths):
            continue
        if str(e.get("cf_issponsored", "")).lower() == "true":
            continue

        item = Item(
            source=cfg["name"], title=title, url=url, published_at=_published(e),
            excerpt=excerpt(e.get("summary")), sections=list(cfg.get("sections", [])),
            language=cfg.get("language", "en"), categories=cats, image=_image(e),
            weight=float(cfg.get("weight", 1.0)),
        )
        if cfg.get("kind") == "reviews" or (review_url and review_url.search(url)):
            _as_review(item, e, cfg)
        items.append(item)
    return items


def _as_review(item: Item, entry: Any, cfg: dict[str, Any]) -> None:
    """Mark a feed item as a game review, pulling out the game, a score and the outlet's verdict."""
    cats = {c.lower() for c in item.categories}
    if "hardware" in cats or HARDWARE_HINTS.search(item.url):
        item.sections = ["tech"]              # a hardware review is tech news, not a game review
        return
    text = _content(entry) + " " + (entry.get("summary") or "")
    score = next((m.group(1) for p in SCORE_PATTERNS for m in [p.search(text)] if m), "")
    if score and "/" not in score and "betyg" in text.lower():
        score = f"{score}/10"
    badge = next((BADGE_TAGS[c] for c in cats if c in BADGE_TAGS), "")

    m = REVIEW_TITLE.match(item.title)
    if m and len(m.group("game")) <= 70 and not re.match(r"(i|we|my|our)\b", m.group("game"), re.I):
        game, verdict = m.group("game"), (m.group("verdict") or "").strip()
    elif cfg.get("title_is_game"):           # MISSIL: the headline is just the game's name
        game, verdict = item.title, ""
    else:
        return                                # "-review" URL but not a review headline
    item.kind = "review"
    item.sections = ["gaming"]
    item.extra.update(
        game=game.strip(" '\"‘’“”"),
        score=score or badge,
        verdict=_sentence_case(verdict) if verdict else (item.excerpt if item.language == "en" else ""),
    )


def _sentence_case(s: str) -> str:
    s = s.strip().rstrip("!")
    return s[:1].upper() + s[1:] if s else s


def fetch_google_news(client: Client, cfg: dict[str, Any]) -> list[Item]:
    url = (f"https://news.google.com/rss/search?q={quote_plus(cfg['query'])}"
           f"&hl=en-US&gl=US&ceid=US:en")
    parsed = _parse(client.get(url).content, url)
    want = cfg.get("domain", "")
    items = []
    for e in parsed.entries[: cfg.get("max_items", 40)]:
        src = e.get("source") or {}
        if want and want not in domain(src.get("href", "")):
            continue
        title = plain(e.get("title"))
        suffix = f" - {src.get('title', cfg['name'])}"
        if title.endswith(suffix):
            title = title[: -len(suffix)]
        items.append(Item(
            source=cfg["name"], title=title, url=e.get("link", ""), published_at=_published(e),
            sections=list(cfg.get("sections", [])), weight=float(cfg.get("weight", 0.8)),
            extra={"via": "Google News"},
        ))
    return items


def fetch_youtube(client: Client, cfg: dict[str, Any]) -> list[Item]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cfg['channel_id']}"
    parsed = _parse(client.get(url).content, url)
    items = []
    for e in parsed.entries:
        link = e.get("link", "")
        if "/shorts/" in link:
            continue
        thumbs = e.get("media_thumbnail") or [{}]
        stats = e.get("media_statistics") or {}
        items.append(Item(
            source=cfg["name"], title=plain(e.get("title")), url=link, published_at=_published(e),
            kind="video", sections=["gaming"], image=thumbs[0].get("url", ""),
            extra={"channel": cfg["name"], "blurb": first_sentence(e.get("summary")),
                   "description": plain(e.get("summary"))[:600], "views": int(stats.get("views") or 0)},
        ))
    return items
