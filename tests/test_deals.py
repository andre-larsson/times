"""Deals from IsThereAnyDeal: the popular list, hidden gems and genre picks, and how they're mixed. No network."""

from __future__ import annotations

import copy
import datetime as dt
import json

from newsroom import links
from newsroom.config import load_config
from newsroom.http import FetchError
from newsroom.sources import fetch_all
from newsroom.sources import itad
from tests.test_pipeline import NOW, _harvest

GENRES = ["Horror", "FMV", "Point & Click", "Roguelike", "Incremental"]


def _raw(gid: str, price: float = 3.0) -> dict:
    """A deal as /deals/v2 lists it (made-up game)."""
    return {"id": gid, "title": f"Game {gid}", "slug": gid, "type": "game", "deal": {
        "shop": {"id": 61, "name": "Steam"}, "price": {"amount": price, "currency": "EUR"},
        "regular": {"amount": 12.0}, "cut": 75, "historyLow": {"amount": price}, "flag": "H", "expiry": None}}


class FakeITAD:
    """Answers /deals/v2 by which list the filter asks for, and /games/info/v2 per game."""

    def __init__(self, lists: dict[str, list], fail: tuple[str, ...] = ()):
        self.lists, self.fail = lists, fail
        self.filters: dict[str, dict] = {}
        self.info_calls: list[str] = []

    def json(self, url, params=None, headers=None):
        if url.endswith("/deals/v2"):
            f = json.loads(params["filter"])
            pool = ("genre:" + next(g for g, tags in load_config()["sources"]["itad"]["genres"]["tags"].items()
                                    if tags == f["tagsUnion"])) if "tagsUnion" in f \
                else "hidden" if "regular" in f else "popular"
            self.filters[pool] = f
            if pool in self.fail:
                raise FetchError("HTTP 500 for https://api.isthereanydeal.com/deals/v2")
            return {"list": [_raw(g) for g in self.lists.get(pool, [])], "hasMore": False}
        self.info_calls.append(params["id"])
        return {"appid": 100, "tags": ["Horror", "Indie"], "stats": {"rank": 50},
                "reviews": [{"source": "Steam", "score": 92, "count": 800}]}


def _itad_only(cfg: dict) -> dict:
    return {**cfg, "sources": {"itad": cfg["sources"]["itad"]}}


def test_every_list_has_bounded_percent_ranges():
    """ITAD reads "max": null in a 0-100 range as 0, which matched no deals at all (live API, 2026-11-06)."""
    cfg = load_config()
    qs = itad.queries(cfg["sources"]["itad"], cfg["deals"])
    assert [q.pool for q in qs] == ["popular", "hidden"] + [f"genre:{g}" for g in GENRES]
    for q in qs:
        assert q.filters["steamPerc"]["max"] == 100 and q.filters["cut"]["max"] == 100, q.pool
    hidden = qs[1].filters
    assert hidden["steamCount"] == {"min": 200, "max": 5000} and hidden["regular"]["min"] == 8
    assert qs[2].filters["tagsUnion"] == ["Horror", "Psychological Horror", "Survival Horror"]


def test_lists_are_merged_per_game_and_a_failed_genre_is_skipped():
    client = FakeITAD({"popular": ["g1", "g2"], "hidden": ["g3", "g2"], "genre:Horror": ["g4"]},
                      fail=("genre:FMV",))
    h = fetch_all(_itad_only(load_config()), client, NOW, itad_key="k")
    by_id = {d["itad_id"]: d for d in h.itad}
    assert set(by_id) == {"g1", "g2", "g3", "g4"}
    assert by_id["g2"]["pools"] == ["popular", "hidden"] and by_id["g4"]["pools"] == ["genre:Horror"]
    assert client.info_calls.count("g2") == 1                          # looked up once, shared
    assert by_id["g4"]["tags"] == ["Horror", "Indie"] and by_id["g4"]["steam_rating"] == "Very Positive"
    status = {s.name: s.ok for s in h.status}
    assert status["IsThereAnyDeal"] and status["IsThereAnyDeal Horror"] and not status["IsThereAnyDeal FMV"]

    h = fetch_all(_itad_only(load_config()), FakeITAD({}, fail=("popular",)), NOW, itad_key="k")
    assert h.itad is None                                              # no popular list: Steam specials instead


def _deal(gid: str, *pools: str) -> dict:
    return {"itad_id": gid, "game": f"Game {gid}", "shop": "Steam", "shop_id": 61, "appid": 1, "price": 2.0,
            "regular": 10.0, "currency": "EUR", "cut": 80, "lowest_ever": True, "expires": None,
            "steam_rating": "Very Positive", "itad_url": "", "pools": list(pools)}


def _day(start: int) -> dt.date:
    """A day on which the genre rotation starts at GENRES[start] (two slots a day)."""
    return next(d for d in (NOW.date() + dt.timedelta(days=i) for i in range(5))
                if d.toordinal() * 2 % 5 == start)


def test_mix_is_popular_then_hidden_gems_then_rotating_genres():
    deals = [_deal(f"p{i}", "popular") for i in range(1, 11)]
    deals[1]["pools"].append("hidden")                                 # p2 is popular and a hidden gem
    deals += [_deal("h1", "hidden"), _deal("h2", "hidden"), _deal("h3", "hidden", "genre:Horror"),
              _deal("h4", "hidden"), _deal("x1", "genre:Horror"), _deal("c1", "genre:Point & Click"),
              _deal("r1", "genre:Roguelike")]
    mix = {"popular": 5, "hidden": 3, "genre": 2}
    out = links.mix_deals(deals, mix, 10, GENRES, _day(0))             # Horror, then FMV (has none)
    assert [d["itad_id"] for d in out] == ["p1", "p2", "p3", "p4", "p5", "h1", "h2", "h3", "x1", "c1"]
    assert [d["pick"] for d in out] == ["popular"] * 5 + ["hidden"] * 3 + ["genre"] * 2
    assert out[8]["genre"] == "Horror" and out[9]["genre"] == "Point & Click"

    out = links.mix_deals(deals, mix, 10, GENRES, _day(3))             # Roguelike, Incremental (none), Horror
    assert [(d["itad_id"], d.get("genre")) for d in out[-2:]] == [("r1", "Roguelike"), ("x1", "Horror")]

    popular_only = [d for d in deals if d["itad_id"].startswith("p")]
    out = links.mix_deals(popular_only, mix, 10, GENRES, _day(0))      # empty pools: popular fills the list
    assert [d["itad_id"] for d in out] == [f"p{i}" for i in range(1, 11)]


def test_deals_block_carries_the_pick_and_tags():
    cfg = copy.deepcopy(load_config())
    deals = [_deal(f"p{i}", "popular") for i in range(1, 6)] + [_deal("h1", "hidden"), _deal("x1", "genre:Horror")]
    deals[-1]["tags"] = ["Psychological Horror"]
    cfg["sources"]["itad"]["genres"]["tags"] = {"Horror": ["Horror"]}
    block = links.deals_block(cfg, _harvest(itad=deals))
    rows = {d["game"]: d for d in block["more"]}
    assert rows["Game h1"]["pick"] == "hidden" and rows["Game p1"]["pick"] == "popular"
    assert rows["Game x1"]["genre"] == "Horror" and rows["Game x1"]["tags"] == ["Psychological Horror"]
