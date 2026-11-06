"""Critic scores on the Gaming page: ITAD averages, the PC check, outlets' own scores. No network."""

from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from newsroom import links
from newsroom.config import load_config
from newsroom.http import FetchError
from newsroom.render import SiteBuilder
from newsroom.sources import Harvest, Item, critics, feeds, fetch_all
from tests.test_pipeline import NOW, _steam_game

GAMING = {"new_on_pc": {"min": 1, "max": 9, "window_days": 7, "min_reviews": 50},
          "reviews": {"min": 3, "max": 10, "window_days": 7, "fill_days": 14, "per_game": 2}}
ITAD_CFG = {"sources": {"itad": {"enabled": True, "critics": {"max_reviewed_games": 40}}}, "gaming": GAMING}


def _ld(rating: dict) -> str:
    """A review page with its score in schema.org JSON-LD, nested in an @graph like PC Gamer's."""
    data = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, {"@type": "Review", "reviewRating": rating}]}
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'


def _review(game: str, source: str, days: float = 1, url: str = "", **extra) -> Item:
    slug = game.lower().replace(" ", "-")
    return Item(source=source, title=f"{game} review", url=url or f"https://example.com/{source[:4].lower()}/{slug}",
                published_at=NOW - dt.timedelta(days=days), kind="review", sections=["gaming"],
                extra={"game": game, "score": "", "verdict": "", **extra})


# Made-up ITAD catalogue: title → (id, info). Glasswing has an app id lookup too.
CATALOGUE = {
    "Hollow Lantern": ("g-lantern", {"type": "game", "appid": 1, "reviews": [
        {"source": "Steam", "score": 93, "count": 900},
        {"source": "OpenCritic", "score": 87, "count": 42, "url": "https://example.com/opencritic/hollow-lantern"},
        {"source": "Metascore", "score": None, "count": 3, "url": "https://example.com/metacritic/hollow-lantern"}]}),
    "Moonlit Kart": ("g-kart", {"type": None, "appid": None, "reviews": []}),          # console-only placeholder
    "Copperline": ("g-copper", {"type": "game", "appid": 7, "reviews": [
        {"source": "Metascore", "score": 61, "count": 20, "url": "javascript:alert(1)"}]}),
}
APPIDS = {"app/1": "g-lantern", "app/4": "g-glass"}
INFO = {gid: info for gid, info in CATALOGUE.values()} | {
    "g-glass": {"type": "game", "appid": 4, "reviews": [{"source": "OpenCritic", "score": 72, "count": 15,
                                                         "url": "https://example.com/opencritic/glasswing"}]}}


class FakeITAD:
    """ITAD's lookups and game info, plus review pages by URL."""

    def __init__(self, pages: dict[str, str] | None = None, broken_info: tuple[str, ...] = ()):
        self.pages, self.broken_info = pages or {}, broken_info
        self.fetched: list[str] = []

    def post_json(self, url, body, params=None):
        if "/lookup/id/shop/61/" in url:
            return {a: APPIDS.get(a) for a in body}
        return {t: CATALOGUE[t][0] if t in CATALOGUE else None for t in body}     # exact titles only

    def json(self, url, params=None, headers=None):
        if url.endswith("/games/lookup/v1"):                 # the single lookup: ignores case
            hit = next((v[0] for k, v in CATALOGUE.items() if k.lower() == params["title"].lower()), None)
            return {"found": bool(hit), **({"game": {"id": hit}} if hit else {})}
        if url.endswith("/games/info/v2"):
            if params["id"] in self.broken_info:
                raise FetchError("HTTP 500 for https://api.isthereanydeal.com/games/info/v2")
            return INFO[params["id"]]
        if url.endswith("/deals/v2"):
            return {"list": [], "hasMore": False}
        raise AssertionError(f"unexpected fetch {url}")

    def text(self, url, **kw):
        self.fetched.append(url)
        if url not in self.pages:
            raise FetchError(f"HTTP 404 for {url}")
        return self.pages[url]

    def get(self, url, params=None, headers=None):
        return SimpleNamespace(content=self.pages[url].encode())


def _harvest(reviews: list[Item]) -> Harvest:
    steam = {"new_releases": [_steam_game(1, "Hollow Lantern", 2), _steam_game(4, "Glasswing", 1, reviews=60),
                              _steam_game(9, "Quiet Release", 3, reviews=80)]}
    return Harvest(fetched_at=NOW, items=reviews, steam=steam)


def test_page_score_reads_schema_org_rating():
    assert critics.page_score(_ld({"ratingValue": 90, "bestRating": 100, "worstRating": 0})) == "90%"
    assert critics.page_score(_ld({"ratingValue": 3.0, "bestRating": 5.0})) == "3/5"
    assert critics.page_score(_ld({"ratingValue": "9.5", "bestRating": "10"})) == "9.5/10"
    assert critics.page_score(_ld({"ratingValue": 4})) == "4/5"                      # schema.org's default scale
    assert critics.page_score(_ld({"ratingValue": 12, "bestRating": 10})) == ""      # out of range
    assert critics.page_score(_ld({"ratingValue": 7, "bestRating": 7})) == ""        # odd scale
    broken = '<script type="application/ld+json">{not json</script>'
    assert critics.page_score(broken + _ld({"ratingValue": 8, "bestRating": 10})) == "8/10"
    assert critics.page_score("<html>no data</html>") == ""


def test_review_feed_options():
    rss = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
      <item><title>Moonlit Kart Review – Drifts and drama</title><link>https://example.com/gi/moonlit-kart</link>
        <pubDate>Tue, 03 Nov 2026 10:00:00 +0000</pubDate>
        <content:encoded>&lt;p&gt;Score:
          9.25 &lt;/p&gt;</content:encoded></item>
      <item><title>Studio announces a sequel</title><link>https://example.com/gi/news/sequel</link>
        <pubDate>Tue, 03 Nov 2026 09:00:00 +0000</pubDate></item>
      <item><title>Arcwave Pocket review</title><link>https://example.com/gi/hardware/arcwave-review</link>
        <pubDate>Tue, 03 Nov 2026 08:00:00 +0000</pubDate></item>
    </channel></rss>"""
    client = FakeITAD(pages={"https://example.com/gi.xml": rss})
    cfg = {"name": "Game Informer", "url": "https://example.com/gi.xml", "sections": ["gaming"], "kind": "reviews",
           "reviews_only": True, "multi_platform": True, "score_scale": 10}
    items = feeds.fetch_feed(client, cfg)
    assert [i.extra["game"] for i in items] == ["Moonlit Kart"]                 # news and hardware dropped
    assert items[0].extra["score"] == "9.25/10"
    assert items[0].extra["multi_platform"] is True and "score_from_page" not in items[0].extra


def test_annotate_adds_averages_and_checks_reviews_are_on_pc():
    reviews = [
        _review("Hollow Lantern", "PC Gamer", days=1),
        _review("Moonlit Kart (2026)", "Eurogamer", days=2, multi_platform=True),   # found once trimmed: console
        _review("Ashfall Courier", "Eurogamer", days=2, multi_platform=True),       # unknown to ITAD: kept
        _review("copperline", "MISSIL", days=3, multi_platform=True),               # found by the single lookup
    ]
    h = _harvest(reviews)
    assert critics.annotate(FakeITAD(), ITAD_CFG, h, "k") == 3          # Lantern, Glasswing, Copperline

    lantern = h.steam["new_releases"][0]
    assert lantern["critics"] == {"opencritic": {"score": 87, "count": 42,
                                                 "url": "https://example.com/opencritic/hollow-lantern"}}
    assert "critics" not in h.steam["new_releases"][2]                   # Quiet Release: not on ITAD

    by_game = {i.extra["game"]: i.extra for i in reviews}
    assert by_game["Moonlit Kart (2026)"]["on_pc"] is False
    assert "on_pc" not in by_game["Ashfall Courier"]
    assert by_game["copperline"]["on_pc"] is True
    assert by_game["copperline"]["critics"]["metascore"]["url"] == ""    # only https links pass

    block = links.gaming_blocks({"gaming": GAMING}, h, [])
    assert [r["game"] for r in block["reviews"]] == ["Hollow Lantern", "Ashfall Courier", "copperline"]
    assert block["reviews"][0]["critics"]["opencritic"]["score"] == 87
    assert [g.get("critics", {}).get("opencritic", {}).get("score") for g in block["new_on_pc"]] == [87, None, 72]


def test_annotate_leaves_a_game_unknown_when_its_info_fails():
    review = _review("Moonlit Kart", "Eurogamer", multi_platform=True)
    critics.annotate(FakeITAD(broken_info=("g-kart",)), ITAD_CFG, _harvest([review]), "k")
    assert "on_pc" not in review.extra                                   # a failed call is not "console"


def test_review_block_merges_an_outlets_feeds_and_caps_each_game():
    url = "https://example.com/pcg/hollow-lantern-review"
    items = [_review("Hollow Lantern", "PC Gamer", url=url), _review("Hollow Lantern", "PC Gamer Reviews", url=url),
             _review("Hollow Lantern", "RPS Reviews", days=2), _review("Hollow Lantern", "Eurogamer", days=3),
             _review("Glasswing", "Eurogamer", days=4)]
    block = links.review_block(items, NOW, GAMING["reviews"])
    assert [(r["game"], r["outlet"]) for r in block] == [
        ("Hollow Lantern", "PC Gamer"), ("Hollow Lantern", "Rock Paper Shotgun"), ("Glasswing", "Eurogamer")]


def test_page_scores_only_for_listed_reviews_without_one():
    url = "https://example.com/pcg/hollow-lantern-review"
    twin = [_review("Hollow Lantern", "PC Gamer", url=url, score_from_page=True),
            _review("Hollow Lantern", "PC Gamer Reviews", url=url, score_from_page=True)]
    scored = _review("Glasswing", "PC Gamer", days=2, score_from_page=True)
    scored.extra["score"] = "70%"
    no_flag = _review("Copperline", "RPS Reviews", days=2)
    old = _review("Old Game", "PC Gamer", days=30, score_from_page=True)            # outside fill_days
    client = FakeITAD(pages={url: _ld({"ratingValue": 88, "bestRating": 100})})
    h = Harvest(fetched_at=NOW, items=[*twin, scored, no_flag, old])
    assert critics.page_scores(client, {"gaming": GAMING}, h) == 1
    assert client.fetched == [url]
    assert [i.extra["score"] for i in twin] == ["88%", "88%"]


def test_fetch_all_runs_the_critic_steps():
    url = "https://example.com/pcg/hollow-lantern-review"
    rss = f"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Hollow Lantern review: fog and feelings</title><link>{url}</link>
        <pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>"""
    cfg = load_config()
    cfg = {**cfg, "sources": {"feeds": [{"name": "PC Gamer Reviews", "url": "https://example.com/pcg.xml",
                                         "sections": ["gaming"], "kind": "reviews", "score_from_page": True}],
                              "itad": cfg["sources"]["itad"]}}
    client = FakeITAD(pages={"https://example.com/pcg.xml": rss, url: _ld({"ratingValue": 85, "bestRating": 100})})
    h = fetch_all(cfg, client, NOW, itad_key="k")
    status = {s.name: s for s in h.status}
    assert status["Critic scores (IsThereAnyDeal)"].ok and status["Critic scores (IsThereAnyDeal)"].count == 1
    assert status["Review scores (outlet pages)"].count == 1
    assert h.items[0].extra["score"] == "85%" and h.items[0].extra["critics"]["opencritic"]["score"] == 87

    no_key = fetch_all(cfg, FakeITAD(pages=client.pages), NOW, itad_key=None)
    assert "Critic scores (IsThereAnyDeal)" not in {s.name for s in no_key.status}


def test_score_parts():
    assert SiteBuilder.score_parts("8.5/10") == ("8.5", "/10")
    assert SiteBuilder.score_parts("90%") == ("90", "%")
    assert SiteBuilder.score_parts("82") == ("82", "")
    assert SiteBuilder.score_parts("Bestest Best") is None


def test_gaming_material_carries_critic_numbers():
    from newsroom.ai_edition import _critic_numbers
    assert _critic_numbers(None) == {}
    assert _critic_numbers({"opencritic": {"score": 88, "count": 69, "url": "https://example.com/oc"}}) == {
        "critics": {"opencritic": {"score": 88, "critics": 69}}}
