"""Phase 2 pipeline tests: schedule, parsing, ranking, the links edition and `generate`. No network."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from newsroom import generate as gen
from newsroom import links, rank, schedule, store
from newsroom.config import load_config
from newsroom.render import build
from newsroom.sources import Harvest, Item, SourceStatus, feeds
from newsroom.sources.itad import steam_label, store_url
from newsroom.text import canonical_url, excerpt, first_sentence

FIX = Path(__file__).parent / "fixtures" / "sources"
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 3, 6, 55, tzinfo=UTC)          # 07:55 in Stockholm


class FakeClient:
    """Serves canned bytes/JSON by URL prefix, like http.Client."""

    def __init__(self, routes: dict[str, bytes | dict]):
        self.routes = routes

    def _find(self, url: str):
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                return body
        raise AssertionError(f"unexpected fetch {url}")

    def get(self, url, params=None, headers=None):
        return SimpleNamespace(content=self._find(url))

    def json(self, url, params=None, headers=None):
        return self._find(url)


# ── schedule ─────────────────────────────────────────────────────────────────

def test_schedule_due_and_ids():
    slots = ["06:30"]
    tz = "Europe/Stockholm"
    # winter: 06:30 Stockholm = 05:30 UTC
    assert schedule.latest_slot(NOW, tz, slots).isoformat() == "2026-11-03T06:30:00+01:00"
    before = dt.datetime(2026, 11, 3, 5, 0, tzinfo=UTC)
    assert schedule.latest_slot(before, tz, slots).date() == dt.date(2026, 11, 2)
    assert schedule.is_due(NOW, tz, slots, None)
    assert schedule.is_due(NOW, tz, slots, dt.datetime(2026, 11, 2, 5, 45, tzinfo=UTC))
    assert not schedule.is_due(NOW, tz, slots, dt.datetime(2026, 11, 3, 5, 35, tzinfo=UTC))
    # summer time: 06:30 Stockholm = 04:30 UTC
    summer = dt.datetime(2026, 6, 1, 4, 35, tzinfo=UTC)
    assert schedule.latest_slot(summer, tz, slots).date() == dt.date(2026, 6, 1)
    # a manual run before the first slot still files under today
    assert schedule.edition_id(schedule.forced_slot(before, tz, slots), slots) == "2026-11-03"
    two = ["06:30", "17:00"]
    late = dt.datetime(2026, 11, 3, 17, 0, tzinfo=UTC)
    assert schedule.edition_id(schedule.latest_slot(late, tz, two), two) == "2026-11-03-1700"


# ── text helpers ─────────────────────────────────────────────────────────────

def test_text_helpers():
    assert canonical_url("http://www.Example.com/a/b/?utm_source=x&id=3#top") == "https://example.com/a/b?id=3"
    assert excerpt("<p>One.</p> <p>" + "word " * 80 + "</p>", 60).endswith(("…", "."))
    assert first_sentence("Ten small games worth a look. Subscribe: https://x") == "Ten small games worth a look."
    assert first_sentence("Watch now at https://example.com/x. More text here.") == ""


# ── feeds ────────────────────────────────────────────────────────────────────

def test_review_feed_parsing():
    client = FakeClient({"https://example.com/reviews.xml": (FIX / "reviews.xml").read_bytes()})
    cfg = {"name": "Pixel Courier", "url": "https://example.com/reviews.xml", "sections": ["gaming"],
           "kind": "reviews", "title_is_game": True}
    items = {i.url.rsplit("/", 2)[-2] if i.url.endswith("/") else i.url.rsplit("/", 1)[-1]: i
             for i in feeds.fetch_feed(client, cfg)}

    lantern = items["hollow-lantern-review"]
    assert lantern.kind == "review"
    assert lantern.extra["game"] == "Hollow Lantern"
    assert lantern.extra["score"] == "Bestest Best"
    assert lantern.extra["verdict"] == "A lighthouse puzzler that earns its gloom"

    handheld = items["arcwave-pocket-review"]           # hardware review → tech news, not gaming
    assert handheld.kind == "news" and handheld.sections == ["tech"]

    copperline = items["copperline"]                     # Swedish outlet: headline is the game
    assert copperline.extra["score"] == "8/10" and copperline.extra["game"] == "Copperline"

    diary = items["deep-shift-salvage-review"]          # "-review" URL, but not a review headline
    assert diary.kind == "review" and diary.extra["game"].startswith("After 300 hours")


def test_youtube_skips_shorts():
    client = FakeClient({"https://www.youtube.com/feeds/": (FIX / "youtube.xml").read_bytes()})
    videos = feeds.fetch_youtube(client, {"name": "Save Point Weekly", "channel_id": "X"})
    assert [v.title for v in videos] == ["10 New Indie Games You Missed This Week"]
    assert videos[0].image.endswith("hqdefault.jpg")
    assert videos[0].extra["blurb"] == "Ten small games worth a look."


# ── ranking ──────────────────────────────────────────────────────────────────

def _item(title, source="Byte Ledger", url=None, hours=2, sections=("ai", "tech"), **kw):
    return Item(source=source, title=title, url=url or f"https://example.com/{source[:4]}/{abs(hash(title))}",
                published_at=NOW - dt.timedelta(hours=hours), sections=list(sections), **kw)


def test_sections_and_junk():
    assert rank.section_for(_item("Lumen Labs ships a new reasoning model")) == "ai"
    assert rank.section_for(_item("Linux 7.1 released")) == "tech"
    assert rank.section_for(_item("Studio layoffs", url="https://example.com/gaming/layoffs")) == "gaming"
    pcg = ("gaming", "tech")
    assert rank.section_for(_item("New GPU tested", url="https://example.com/hardware/gpu", sections=pcg)) == "tech"
    assert rank.section_for(_item("Patch notes", url="https://example.com/games/patch", sections=pcg)) == "gaming"
    for junk in ("NYT Connections hints for today", "Snag this monitor for only $349",
                 "The best laptop deals this week", "Corsair has slashed $180 off its SSD"):
        assert rank.is_junk(junk), junk
    assert not rank.is_junk("Arcwave cuts GPU prices across the range")


def test_clustering_and_hn_boost():
    a = _item("Kestrel releases free open model that beats big labs at coding", source="Byte Ledger")
    b = _item("Kestrel's free open model beats the big labs at coding tests", source="Kernel Post")
    c = _item("Linux 7.1 released with a new scheduler", source="Kernel Post", hours=1)
    hn = [{"title": "Linux 7.1", "url": c.url, "points": 900, "comments": 300,
           "comments_url": "https://example.com/hn/1", "created_at": "2026-11-03T04:00:00Z"}]
    cands = rank.build_candidates([a, b, c], hn, NOW)
    assert len(cands) == 2                                # a and b merged
    merged = next(x for x in cands if "Kestrel" in x.item.title)
    assert [i.source for i in merged.also] == ["Kernel Post"]
    linux = next(x for x in cands if "Linux" in x.item.title)
    assert linux.hn["points"] == 900 and linux.score > merged.score


# ── links edition ────────────────────────────────────────────────────────────

def _steam_game(appid, title, days_ago, reviews=500, score=8, **kw):
    return {"appid": appid, "title": title, "store_url": f"https://example.com/steam/{appid}",
            "release_date": (NOW.date() - dt.timedelta(days=days_ago)).isoformat(), "date_precision": "day",
            "coming_soon": days_ago < 0, "steam_rating": "Very Positive" if score >= 8 else "Mixed",
            "rating_score": score, "review_count": reviews, "percent_positive": 90, "price": 9.99,
            "regular": 19.99, "cut": 50, "currency": "EUR", "image": "", "short_description": "A game.",
            **kw}


def _harvest(itad=None):
    items = [_item(f"Byte Ledger story number {n} about compilers", hours=n) for n in range(1, 8)]
    items += [_item("Kernel Post on new AI agents for code review", source="Kernel Post"),
              _item("Pixel Courier: Deep Shift Salvage gets a co-op mode", source="Pixel Courier",
                    sections=("gaming",)),
              _item("GTA VI gets a new trailer", source="Pixel Courier", sections=("gaming",))]
    review = _item("Hollow Lantern review", source="Pixel Courier", sections=("gaming",), kind="review")
    review.extra = {"game": "Hollow Lantern", "score": "4/5", "verdict": "Gloomy and good."}
    video = _item("Ten indie games", source="Save Point Weekly", kind="video", sections=("gaming",),
                  image="https://example.com/t.jpg")
    hn = [{"title": f"HN story {n}", "url": f"https://example.com/hn-link/{n}", "points": 500 - n * 10,
           "comments": 10, "comments_url": f"https://example.com/hn/{n}",
           "created_at": "2026-11-03T03:00:00Z"} for n in range(12)]
    steam = {
        "new_releases": [_steam_game(1, "Hollow Lantern", 2), _steam_game(2, "Ashen Rails", 3, score=4),
                         _steam_game(3, "Old Classic", 400), _steam_game(4, "Glasswing", 1, reviews=60)],
        "coming_soon": [_steam_game(5, "Orbital Freight Co. 2", -10), _steam_game(6, "Far Future", -400)],
        "specials": [_steam_game(7, "Copperline", 300, reviews=5000, cut=75),
                     _steam_game(8, "Expired Deal", 300, reviews=9000, cut=80,
                                 discount_end=(NOW - dt.timedelta(hours=1)).isoformat())],
    }
    return Harvest(fetched_at=NOW, items=items + [review, video], hn=hn, steam=steam, itad=itad,
                   status=[SourceStatus("Byte Ledger", True, 7)])


def test_links_edition_shape(tmp_path):
    cfg = load_config()
    ed = links.build_links_edition(cfg, _harvest(), "2026-11-03")
    assert ed["mode"] == "links" and ed["stories"] == []
    assert len(ed["hn_top"]) == 10
    byte = [l for l in ed["links"] if l["source"] == "Byte Ledger"]
    assert len(byte) <= cfg["links"]["max_per_source"]          # one feed can't fill a section
    assert {l["section"] for l in ed["links"]} <= {"ai", "tech"}
    assert not {l["url"] for l in ed["links"]} & {h["url"] for h in ed["hn_top"]}

    g = ed["gaming"]
    assert [x["title"] for x in g["new_on_pc"]] == ["Hollow Lantern", "Glasswing"]   # recent, not negative
    assert g["new_on_pc"][0]["review_ids"] == [g["reviews"][0]["id"]]
    assert g["console_spotlight"][0]["headline"] == "GTA VI gets a new trailer"
    assert all("GTA" not in n["headline"] for n in g["news"])
    assert [c["game"] for c in g["coming_soon"]] == ["Orbital Freight Co. 2"]
    assert g["watch"][0]["thumbnail"] == "https://example.com/t.jpg"

    deals = ed["deals"]
    assert deals["source"] == "steam" and [d["game"] for d in deals["more"]] == ["Copperline"]

    # the edition renders, and every internal link resolves (checked in test_render too)
    store.save_edition(tmp_path / "data", ed)
    assert build(cfg, tmp_path / "data", tmp_path / "site") > 5
    assert "Hollow Lantern" in (tmp_path / "site" / "gaming" / "index.html").read_text()


def test_links_skip_previous_edition():
    cfg = load_config()
    first = links.build_links_edition(cfg, _harvest(), "2026-11-02")
    second = links.build_links_edition(cfg, _harvest(), "2026-11-03", previous=first)
    assert not {l["url"] for l in first["links"]} & {l["url"] for l in second["links"]}


def test_itad_deals_preferred():
    itad = [{"itad_id": "a", "game": "Garden Wars", "shop": "Steam", "shop_id": 61, "appid": 99, "price": 3.74,
             "regular": 14.99, "currency": "EUR", "cut": 75, "lowest_ever": True, "new_low": False,
             "expires": None, "steam_rating": "Very Positive", "steam_count": 4000, "itad_url": ""},
            {"itad_id": "b", "game": "Meh Game", "shop": "GOG", "shop_id": 35, "price": 1.0, "regular": 10.0,
             "currency": "EUR", "cut": 90, "lowest_ever": True, "steam_rating": "Mixed", "itad_url": ""}]
    block = links.deals_block(load_config(), _harvest(itad=itad))
    assert block["source"] == "itad"
    assert [d["game"] for d in block["more"]] == ["Garden Wars"]
    assert block["more"][0]["url"] == "https://store.steampowered.com/app/99/"
    assert store_url({"shop_id": 35, "itad_url": "https://isthereanydeal.com/game/x/"}).startswith("https://isthereanydeal")
    assert steam_label(96, 600) == "Overwhelmingly Positive" and steam_label(85, 40) == "Positive"


# ── generate ─────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_fetch(monkeypatch):
    monkeypatch.setattr(gen, "fetch_all", lambda cfg, client, now, itad_key=None: _harvest())
    return FakeClient({})


def test_generate_modes(tmp_path, fake_fetch):
    cfg, data = load_config(), tmp_path / "data"
    first = gen.generate(cfg, data, "auto", now=NOW, env={}, client=fake_fetch)
    assert first.published and first.mode == "links" and first.reason == "no ANTHROPIC_API_KEY"
    saved = json.loads(store.edition_path(data, "2026-11-03").read_text())
    assert saved["edition_id"] == "2026-11-03"

    again = gen.generate(cfg, data, "auto", now=NOW + dt.timedelta(hours=1), env={}, client=fake_fetch)
    assert not again.published and again.reason.startswith("not due")

    forced = gen.generate(cfg, data, "links", now=NOW + dt.timedelta(hours=2), env={}, client=fake_fetch)
    assert forced.published and forced.edition_id == "2026-11-03"

    skipped = gen.generate(cfg, data, "skip", now=NOW, env={}, client=fake_fetch)
    assert not skipped.published



def test_generate_keeps_previous_when_sources_fail(tmp_path, monkeypatch):
    empty = Harvest(fetched_at=NOW, status=[SourceStatus("Byte Ledger", False, error="HTTP 503")])
    monkeypatch.setattr(gen, "fetch_all", lambda cfg, client, now, itad_key=None: empty)
    result = gen.generate(load_config(), tmp_path / "data", "links", now=NOW, env={}, client=FakeClient({}))
    assert not result.published and "too few" in result.reason
    assert not (tmp_path / "data" / "editions").exists()
    assert "FAILED — HTTP 503" in gen.report(result)


def test_render_before_first_edition(tmp_path):
    pages = build(load_config(), tmp_path / "no-data", tmp_path / "site")
    assert pages == 2
    assert "presses are warming up" in (tmp_path / "site" / "index.html").read_text()


def test_dotenv_loader(tmp_path, monkeypatch):
    from newsroom.env import load_dotenv

    env = tmp_path / ".env"
    env.write_text('# comment\nexport FAKE_ONE="quoted value"\nFAKE_TWO=plain\nFAKE_THREE=from-file\nnot a line\n')
    monkeypatch.delenv("FAKE_ONE", raising=False)
    monkeypatch.delenv("FAKE_TWO", raising=False)
    monkeypatch.setenv("FAKE_THREE", "from-environment")
    assert load_dotenv(env) == ["FAKE_ONE", "FAKE_TWO"]
    import os
    assert os.environ["FAKE_ONE"] == "quoted value" and os.environ["FAKE_TWO"] == "plain"
    assert os.environ["FAKE_THREE"] == "from-environment"          # real env vars win
    assert load_dotenv(tmp_path / "missing.env") == []


def test_http_error_includes_api_reason_but_never_the_key():
    import httpx
    from newsroom.http import Client, FetchError

    def handler(request):
        key = request.url.params.get("key", "")
        reason = "Invalid or expired api key" if key == "secret-key-123" else f"bad key {key}"
        return httpx.Response(403, json={"status_code": 403, "reason_phrase": reason})

    client = Client(retries=0)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError, match=r"HTTP 403 for https://api.example.com/deals \(Invalid or expired api key\)"):
        client.json("https://api.example.com/deals", params={"key": "secret-key-123"})
    with pytest.raises(FetchError) as err:
        client.json("https://api.example.com/deals", params={"key": "echoed-key-456"})
    assert "echoed-key-456" not in str(err.value) and str(err.value).endswith("/deals")
