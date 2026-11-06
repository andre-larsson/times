"""Critic scores for the Gaming page, added to the harvest after the feeds and Steam lists are in.

Two steps, each its own row in the Harvest status:

- `annotate`: IsThereAnyDeal's game info for the games New on PC and Reviews will list. It carries the
  Metascore and OpenCritic averages (with critic counts and links), and tells us whether a reviewed game
  is sold on PC at all: ITAD knows console-only games as empty placeholders (no type, no Steam app id), as
  the Zelda: Ocarina of Time remake and Nintendo Switch Sports Resort were on 2026-11-06. A game ITAD
  can't find stays listed: headlines name games loosely ("Hellraiser: Revival" for "Clive Barker's
  Hellraiser: Revival"), and dropping on a miss would have hidden four PC games' reviews that day.
- `page_scores`: the outlet's own score, read from the review page's schema.org data (`reviewRating`),
  for listed reviews whose feed carries no score (PC Gamer, Eurogamer, PCGamesN set score_from_page).

Both only add fields (Steam game: `critics`; review item: `critics`, `on_pc`, `score`); links.py reads
them and stays free of network calls.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .. import links
from ..http import Client, FetchError
from ..text import game_key
from . import Harvest, Item
from .itad import API, STEAM_SHOP_ID

AVERAGES = {"Metascore": "metascore", "OpenCritic": "opencritic"}
SCALES = {4, 5, 10, 20, 100}
LD_JSON = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
# headline extras a store title doesn't have: "Enshrouded 1.0", "Ocarina of Time (2026)", "Invokyr Early Access"
TITLE_EXTRAS = [re.compile(r"\s*\([^)]*\)\s*$"), re.compile(r"\s+v?\d+\.\d+(?:\.\d+)?\s*$", re.I),
                re.compile(r"\s+early access\s*$", re.I)]


def annotate(client: Client, cfg: dict[str, Any], h: Harvest, key: str) -> int:
    """Look up the games New on PC and Reviews may list; returns how many have a critic average."""
    g = cfg.get("gaming") or {}
    limits = (cfg.get("sources") or {}).get("itad", {}).get("critics") or {}
    new = links.new_on_pc_block(h.steam.get("new_releases") or [], h.fetched_at, g.get("new_on_pc") or {})
    reviews = links.review_candidates(h.items, h.fetched_at, g.get("reviews") or {})
    titles: dict[str, str] = {}                        # game key → headline title, newest review first
    for i in reviews:
        titles.setdefault(game_key(i.extra["game"]), i.extra["game"])
        if len(titles) >= int(limits.get("max_reviewed_games", 40)):
            break

    by_app = _lookup_appids(client, key, [x["appid"] for x in new]) if new else {}
    by_title = _lookup_titles(client, key, list(titles.values())) if titles else {}
    info: dict[str, dict[str, Any]] = {}
    for gid in dict.fromkeys([*by_app.values(), *by_title.values()]):
        if gid:
            try:
                info[gid] = client.json(f"{API}/games/info/v2", params={"key": key, "id": gid})
            except FetchError:
                continue

    steam = {x["appid"]: x for x in h.steam.get("new_releases") or []}
    for appid, gid in by_app.items():
        if gid in info and (c := averages(info[gid])):
            steam[appid]["critics"] = c
    for i in reviews:
        k = game_key(i.extra["game"])
        if k not in titles:
            continue                                   # past the lookup cap: left unknown
        gid = by_title.get(titles[k])
        if gid not in info:
            continue                                   # not found, or the info call failed: unknown, kept
        i.extra["on_pc"] = bool(info[gid].get("type"))  # False only for ITAD's console-only placeholders
        if c := averages(info[gid]):
            i.extra["critics"] = c
    return sum(1 for gid in info if averages(info[gid]))


def averages(info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Metascore and OpenCritic from ITAD's game info: {"opencritic": {"score", "count", "url"}, …}.
    ITAD lists a source with a null score until enough critics have reviewed the game; those are left out."""
    out = {}
    for r in info.get("reviews") or []:
        name = AVERAGES.get(r.get("source"))
        if name and isinstance(r.get("score"), (int, float)):
            url = r.get("url") or ""
            out[name] = {"score": int(r["score"]), "count": int(r.get("count") or 0),
                         "url": url if url.startswith("https://") else ""}
    return out


def _lookup_appids(client: Client, key: str, appids: list[int]) -> dict[int, str | None]:
    found = client.post_json(f"{API}/lookup/id/shop/{STEAM_SHOP_ID}/v1", [f"app/{a}" for a in appids],
                             params={"key": key})
    return {a: (found or {}).get(f"app/{a}") for a in appids}


def _lookup_titles(client: Client, key: str, titles: list[str]) -> dict[str, str | None]:
    """ITAD ids by title: one batch call (exact titles), then the single lookup for each miss, which
    ignores case and apostrophe style ("Wings of Theve", "Belmont’s Curse"), also with extras trimmed."""
    found = dict(client.post_json(f"{API}/lookup/id/title/v1", titles, params={"key": key}) or {})
    for t in titles:
        for variant in dict.fromkeys([t, _trimmed(t)]):
            if found.get(t):
                break
            try:
                r = client.json(f"{API}/games/lookup/v1", params={"key": key, "title": variant})
            except FetchError:
                break
            found[t] = (r.get("game") or {}).get("id") if isinstance(r, dict) and r.get("found") else None
    return {t: found.get(t) for t in titles}


def _trimmed(title: str) -> str:
    for pattern in TITLE_EXTRAS:
        title = pattern.sub("", title)
    return title.strip()


def page_scores(client: Client, cfg: dict[str, Any], h: Harvest) -> int:
    """Read the outlet's score from the page of each listed review that has none; returns how many."""
    listed = links.review_block(h.items, h.fetched_at, (cfg.get("gaming") or {}).get("reviews") or {})
    by_url: dict[str, list[Item]] = {}
    for i in h.items:
        if i.kind == "review":
            by_url.setdefault(i.url, []).append(i)
    found = 0
    for r in listed:
        same = by_url.get(r["url"]) or []              # one review can come from two feeds of an outlet
        if r["score"] or not any(i.extra.get("score_from_page") for i in same):
            continue
        try:
            score = page_score(client.text(r["url"]))
        except FetchError:
            continue
        if score:
            for i in same:
                i.extra["score"] = score
            found += 1
    return found


def page_score(html: str) -> str:
    """The review's own score from schema.org JSON-LD: "90%" (out of 100), "3/5", "9.5/10"; "" if none."""
    for blob in LD_JSON.findall(html):
        try:
            data = json.loads(blob.strip())
        except ValueError:
            continue
        for node in _nodes(data):
            rating = node.get("reviewRating")
            if isinstance(rating, dict) and (score := _format(rating)):
                return score
    return ""


def _nodes(data: Any):
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from _nodes(v)
    elif isinstance(data, list):
        for v in data:
            yield from _nodes(v)


def _format(rating: dict[str, Any]) -> str:
    try:
        value = float(rating.get("ratingValue"))
        best = float(rating.get("bestRating") or 5)       # schema.org's default scale is 1-5
    except (TypeError, ValueError):
        return ""
    if best not in SCALES or not 0 <= value <= best:
        return ""
    return f"{value:g}%" if best == 100 else f"{value:g}/{best:g}"
