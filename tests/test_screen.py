"""Screen: what to watch. TMDB and Netflix's top 10 from recorded (made-up) responses, the saved snapshot,
the rotation, the picks of the week with a fake Claude, and the pages. No network, no cost."""

from __future__ import annotations

import copy
import datetime as dt
import json

import httpx
import pytest

from newsroom import ROOT, ai_edition, screen, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.http import Client, FetchError
from newsroom.llm import Tally, TransientError
from newsroom.render import build
from newsroom.sources import Harvest
from newsroom.sources import netflix, tmdb
from tests.test_ai import KEY, FakeLLM
from tests.test_pipeline import _harvest

FIX = ROOT / "tests" / "fixtures" / "sources"
REC = json.loads((FIX / "tmdb.json").read_text(encoding="utf-8"))
UTC = dt.timezone.utc
FRIDAY = dt.datetime(2026, 11, 6, 6, 55, tzinfo=UTC)          # 07:55 in Stockholm
V3_KEY = "v3-test-key-123456"
V4_KEY = "eyJtest.token.value"


class FakeWeb:
    """TMDB answered from tests/fixtures/sources/tmdb.json, Netflix's Tudum pages from the HTML fixtures.
    Records every request; paths starting with an entry in `fail` answer HTTP 500."""

    def __init__(self, rec: dict | None = None, fail: tuple[str, ...] = ()):
        self.rec = copy.deepcopy(rec or REC)
        self.fail = fail
        self.calls: list[tuple[str, dict, dict]] = []
        self.pages: list[str] = []

    def _titles(self, ids):
        return [self.rec["titles"][str(i)] for i in ids]

    def json(self, url, params=None, headers=None):
        params = dict(params or {})
        self.calls.append((url, params, dict(headers or {})))
        assert url.startswith(tmdb.API), url
        path = url[len(tmdb.API):]
        if any(path.startswith(f) for f in self.fail):
            raise FetchError(f"HTTP 500 for {url}")
        parts = path.strip("/").split("/")
        if parts[0] == "watch":
            return {"results": self.rec["providers"][parts[2]]}
        if parts[0] == "genre":
            return {"genres": self.rec["genres"][parts[1]]}
        if parts[0] == "discover":
            kind, d = parts[1], self.rec["discover"]
            if params["sort_by"] == "vote_average.desc":
                ids = d["classics"][kind]
            else:
                lst = "new" if params["sort_by"] == "popularity.desc" else "catalog"
                ids = d[params["with_watch_providers"]][lst][kind]
            return {"page": 1, "total_pages": 1, "results": self._titles(ids)}
        if parts[0] == "search":
            return {"page": 1, "results": self._titles(self.rec["search"][parts[1]].get(params["query"], []))}
        kind, tid = parts[0], parts[1]                         # /{kind}/{id}/watch/providers
        se = self.rec["where"].get(f"{kind}:{tid}") or {}
        return {"id": int(tid), "results": {"SE": se} if se else {}}

    def text(self, url, **kw):
        self.pages.append(url)
        assert url.startswith(netflix.TOP10), url
        if "netflix" in self.fail:
            raise FetchError(f"HTTP 503 for {url}")
        name = "netflix_top10_tv.html" if url.endswith("/tv") else "netflix_top10_films.html"
        return (FIX / name).read_text(encoding="utf-8")


def _fetch(web=None, key=V3_KEY, memory=None, now=FRIDAY, want_pool=False, cfg=None):
    h = Harvest(fetched_at=now)
    web = web or FakeWeb()
    out = screen.fetch(cfg or load_config(), web, h, key, memory or {}, now.date(), want_pool=want_pool)
    return out, h, web


def _status(h):
    return {s.name: s for s in h.status}


# ── TMDB and Netflix ─────────────────────────────────────────────────────────

def test_both_kinds_of_tmdb_credential():
    assert tmdb.auth(" eyJabc.def ") == ({}, {"Authorization": "Bearer eyJabc.def"})     # v4 read-access token
    assert tmdb.auth("abc123") == ({"api_key": "abc123"}, {})                             # v3 API key


def test_services_resolve_by_name_with_overrides():
    providers = REC["providers"]["movie"] + REC["providers"]["tv"]
    cfg = load_config()["screen"]["services"]
    found, missing = tmdb.resolve(cfg, providers)
    assert [(s.name, s.ids, s.types) for s in found] == [
        ("Netflix", [1008], ["flatrate"]),                 # not "Netflix Kids"
        ("SVT Play", [1501], ["free", "ads", "flatrate"]), ("TV4 Play", [1502], ["ads", "free"])]
    assert missing == []
    wanted = [{"name": "Viaplay"}, {"name": "Netflix", "ids": [77]}, {"name": "Svt play"},
              {"name": "Cinema Club", "match": ["Other Service"]}]
    found, missing = tmdb.resolve(wanted, providers)
    assert [(s.name, s.ids) for s in found] == [("Netflix", [77]), ("Svt play", [1501]), ("Cinema Club", [2000])]
    assert missing == ["Viaplay"]


def test_netflix_top10_pages_parse():
    top = netflix.top10(FakeWeb(), "sweden")
    assert top["week"] == {"start": "2026-10-26", "end": "2026-11-01"}
    assert top["url"] == "https://www.netflix.com/tudum/top10/sweden"
    assert [r["title"] for r in top["films"]] == ["Northbound Static", "Glass Harbor Heist",
                                                  "Weekend in Oslo: The Return", "Thunder & Lake"]
    assert top["films"][2]["weeks"] == 4 and "show" not in top["films"][0]       # films keep their full title
    assert [r["show"] for r in top["tv"]] == ["The Lantern Keepers", "Copper and Clay", "Bright Static"]
    assert netflix.show_title("Love Is Blind: S11: Boston") == "Love Is Blind"
    assert netflix.show_title("Nobody Wants This: Season 3") == "Nobody Wants This"
    assert netflix.parse("<html>no table</html>") == (None, [])


# ── the lists ────────────────────────────────────────────────────────────────

def test_lists_from_tmdb_with_service_tags():
    out, h, web = _fetch()
    b = out.block
    assert b["tmdb"] and [s["name"] for s in b["services"]] == ["Netflix", "SVT Play", "TV4 Play"]
    new = {n["service"]: n["titles"] for n in b["new"]}
    nf = new["Netflix"]
    assert [t["key"] for t in nf] == ["movie:7001", "tv:7101", "movie:7002", "tv:7102"]   # films and series alternate
    assert [t["flag"] for t in nf] == ["new_film", "new_series", "new_film", "new_episodes"]
    assert nf[0]["on"] == [{"service": "Netflix", "type": "flatrate"}]
    assert nf[0]["poster"] == "https://image.tmdb.org/t/p/w342/sample-7001.jpg" and nf[0]["genres"] == ["Thriller"]
    assert nf[0]["url"] == "https://example.com/tmdb/movie/7001/watch?locale=SE"         # TMDB's watch page
    assert nf[3]["on"] == [{"service": "Netflix", "type": None}]       # no per-title data: the list's own service
    svt = new["SVT Play"]
    assert [t["on"] for t in svt] == [[{"service": "SVT Play", "type": "free"}]] * 2
    assert next(t for t in svt if t["key"] == "tv:7501")["original_title"] == "Fjällstugan"
    assert new["TV4 Play"][0]["on"] == [{"service": "TV4 Play", "type": "ads"}]
    assert "popularity" not in nf[0] and "origin" not in nf[0]

    # older but great: the classics query plus the catalog titles that clear the bar; Long Shadows is only on
    # TV4's paid tier, so it's left out
    classics = {t["key"]: t for t in b["classics"]}
    assert set(classics) == {"movie:7201", "movie:7602", "movie:7601", "tv:7301"}
    assert classics["movie:7602"]["on"] == [{"service": "Netflix", "type": "flatrate"},
                                            {"service": "SVT Play", "type": "free"}]

    top = b["top10"]
    matches = [(r["title"], (r["match"] or {}).get("key")) for r in top["films"] + top["tv"]]
    assert matches == [("Northbound Static", "movie:7001"), ("Glass Harbor Heist", None),
                       ("Weekend in Oslo: The Return", None),        # TMDB's first result is the first film
                       ("Thunder & Lake", None),
                       ("The Lantern Keepers: Season 1", "tv:7101"), ("Copper and Clay: S2: Winter", "tv:7102"),
                       ("Bright Static: Limited Series", None)]
    assert top["tv"][0]["match"]["on"] == [{"service": "Netflix", "type": "flatrate"}]

    st = _status(h)
    for name in ("TMDB providers", "TMDB new on Netflix", "TMDB SVT Play catalog", "TMDB older but great",
                 "Netflix top 10", "TMDB top 10 matches", "TMDB where to watch"):
        assert st[name].ok and not st[name].skipped, name
    assert st["TMDB providers"].count == 3 and st["Netflix top 10"].count == 7

    # the snapshot is seeded (no arrivals on the first day) and the classics shown are remembered
    m = out.memory
    assert m["since"] == {"Netflix": "2026-11-06", "SVT Play": "2026-11-06", "TV4 Play": "2026-11-06"}
    assert set(m["catalog"]["Netflix"]) == {"movie:7201", "movie:7202", "tv:7301"} and m["arrived"]["Netflix"] == {}
    assert set(m["shown"]) == set(classics) and m["top10"]["checked"] == "2026-11-06"

    # requests: region and monetization filters, the v3 key as a query parameter only
    discover = [p for u, p, _ in web.calls if "/discover/" in u]
    assert all(p["watch_region"] == "SE" and p["include_adult"] == "false" for p in discover)
    tv4 = [p for p in discover if p.get("with_watch_providers") == "1502"]
    assert tv4 and all(p["with_watch_monetization_types"] == "ads|free" for p in tv4)
    assert any(p.get("with_watch_providers") == "1008|1501|1502" for p in discover)          # classics: any service
    new_tv = [p for p in discover if "air_date.gte" in p]                    # new series: recent, no kids or soaps
    assert new_tv and all(p["without_genres"] == "10762,10766" and p["first_air_date.gte"] <= "2018-11-06"
                          for p in new_tv)
    assert all(p["api_key"] == V3_KEY and "Authorization" not in hd for _, p, hd in web.calls)
    assert len(web.calls) < 60


def test_v4_token_goes_in_a_header():
    _, _, web = _fetch(key=V4_KEY)
    assert web.calls and all(hd["Authorization"] == f"Bearer {V4_KEY}" and "api_key" not in p
                             for _, p, hd in web.calls)


def test_new_arrivals_from_the_snapshot():
    first, _, _ = _fetch()
    rec = copy.deepcopy(REC)
    rec["discover"]["1008"]["catalog"]["tv"].append(7302)                 # Harbor Lights arrives on Netflix
    later = FRIDAY + dt.timedelta(days=1)                                 # still warming up: absorbed
    warm, _, _ = _fetch(FakeWeb(rec), memory=first.memory, now=later)
    assert all(t.get("flag") != "added" for n in warm.block["new"] for t in n["titles"])

    rec["discover"]["1008"]["catalog"]["movie"].append(7903)              # Weekend in Oslo arrives after warm-up
    day4 = FRIDAY + dt.timedelta(days=3)
    out, h, web = _fetch(FakeWeb(rec), memory=warm.memory, now=day4)
    nf = next(n["titles"] for n in out.block["new"] if n["service"] == "Netflix")
    assert nf[0]["key"] == "movie:7903" and nf[0]["flag"] == "added" and nf[0]["flag_date"] == "2026-11-09"
    assert "tv:7302" not in {t["key"] for t in nf}
    assert out.memory["arrived"]["Netflix"] == {"movie:7903": "2026-11-09"}
    # the top 10 isn't fetched again before a newer week can exist, and its matches are kept
    assert web.pages == [] and _status(h)["Netflix top 10"].skipped
    assert not any("/search/" in u for u, _, _ in web.calls)
    assert out.block["top10"]["films"][0]["match"]["key"] == "movie:7001"

    still, _, _ = _fetch(FakeWeb(rec), memory=out.memory, now=day4 + dt.timedelta(days=13))
    assert next(n["titles"] for n in still.block["new"] if n["service"] == "Netflix")[0]["key"] == "movie:7903"
    gone, _, _ = _fetch(FakeWeb(rec), memory=still.memory, now=day4 + dt.timedelta(days=14))
    assert all(t.get("flag") != "added" for n in gone.block["new"] for t in n["titles"])


def test_arrivals_rules():
    cfg = {"warmup_days": 2, "forget_days": 10, "max_per_day": 2}
    m = screen._memory({})
    d = dt.date(2026, 11, 1)
    assert screen.arrivals(m, "S", ["a", "b"], d, cfg) == []                                # seeding
    assert screen.arrivals(m, "S", ["a", "b", "c"], d + dt.timedelta(days=1), cfg) == []    # warming up
    assert screen.arrivals(m, "S", ["a", "b", "c", "d"], d + dt.timedelta(days=2), cfg) == ["d"]
    assert screen.arrivals(m, "S", ["a", "x", "y", "z"], d + dt.timedelta(days=3), cfg) == []   # too many at once
    assert "x" in m["catalog"]["S"] and "x" not in m["arrived"]["S"]                        # absorbed quietly
    assert screen.arrivals(m, "S", ["c"], d + dt.timedelta(days=5), cfg) == []              # back within 10 days
    assert screen.arrivals(m, "S", ["b"], d + dt.timedelta(days=13), cfg) == ["b"]          # gone 12 days: new again


def test_rotation_shows_the_least_recent_first_and_is_stable_on_a_rerun():
    day = dt.date(2026, 11, 6)
    shown = {"a": "2026-11-01", "b": "2026-10-01", "c": "2026-11-06"}
    order = screen.rotation(["a", "b", "c", "d", "e"], shown, day)
    assert set(order[:3]) == {"c", "d", "e"} and order[3:] == ["b", "a"]     # shown today counts as never shown
    assert order == screen.rotation(["e", "d", "c", "b", "a"], shown, day)


def test_top10_is_fetched_once_a_newer_week_can_exist():
    cached = {"week": {"start": "2026-10-26", "end": "2026-11-01"}, "films": [{}], "checked": "2026-11-03"}
    assert not screen.top10_due(cached, dt.date(2026, 11, 10))          # Tuesday: Netflix publishes this evening
    assert screen.top10_due(cached, dt.date(2026, 11, 11))
    assert not screen.top10_due({**cached, "checked": "2026-11-11"}, dt.date(2026, 11, 11))
    assert screen.top10_due(None, dt.date(2026, 11, 10))


def test_no_key_is_a_quiet_status_and_the_top10_still_shows():
    out, h, web = _fetch(key=None)
    st = _status(h)
    assert st["TMDB"].skipped and "TMDB_API_KEY not set" in st["TMDB"].error
    assert not out.block["tmdb"] and out.block["new"] == [] and out.block["classics"] == []
    assert [r["title"] for r in out.block["top10"]["films"]][:1] == ["Northbound Static"]
    assert "match" not in out.block["top10"]["films"][0]                # searched once there's a key
    assert web.calls == [] and st["Netflix top 10"].ok


def test_failures_are_recorded_and_never_raise():
    out, h, web = _fetch(FakeWeb(fail=("/watch/providers", "netflix")))           # a bad key, Netflix down
    st = _status(h)
    assert not st["TMDB providers"].ok and not st["Netflix top 10"].ok
    assert len(web.calls) == 1 and out.block["top10"] is None and not out.block["tmdb"]

    out, h, _ = _fetch(FakeWeb(fail=("/movie/", "/tv/")))                         # every where-to-watch lookup
    assert not _status(h)["TMDB where to watch"].ok
    nf = next(n["titles"] for n in out.block["new"] if n["service"] == "Netflix")
    assert nf and all(t["on"] == [{"service": "Netflix", "type": None}] for t in nf)
    assert out.block["classics"] == []                                  # can't confirm where they are

    out, h, _ = _fetch(FakeWeb(fail=("/discover/movie",)))
    assert not _status(h)["TMDB new on Netflix"].ok and "Netflix" not in out.memory["since"]
    assert all(s.error.count(V3_KEY) == 0 for s in h.status)


def test_tmdb_error_reason_is_shown_but_never_the_key():
    def handler(request):
        return httpx.Response(401, json={"status_code": 7, "success": False,
                                         "status_message": "Invalid API key: You must be granted a valid key."})

    client = Client(retries=0)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError) as err:
        client.json(f"{tmdb.API}/watch/providers/movie", params={"api_key": V3_KEY, "watch_region": "SE"})
    assert str(err.value) == (f"HTTP 401 for {tmdb.API}/watch/providers/movie "
                              "(Invalid API key: You must be granted a valid key.)")


# ── the picks of the week ────────────────────────────────────────────────────

class ScreenLLM(FakeLLM):
    """Answers Screen's picks call: the first ids it's given, plus an unknown id and a duplicate."""

    def _screen(self, m):
        self.material = m
        ids = [t["id"] for t in m["titles"]]
        picks = [{"id": i, "reason": f"Reason {n}."} for n, i in enumerate(ids[:7], 1)]
        return {"headline": "A lighthouse, a ferry and five more", "dek": "Seven to watch.",
                "picks": picks + [{"id": "movie:404", "reason": "Not listed."}, dict(picks[0], reason="Again.")]}


def test_picks_are_due_on_fridays():
    cfg, fri = load_config(), FRIDAY.date()
    assert screen.picks_due(cfg, fri, None) and screen.picks_due(cfg, fri, fri - dt.timedelta(days=7))
    assert not screen.picks_due(cfg, fri - dt.timedelta(days=1), None)
    assert not screen.picks_due(cfg, fri, fri)                                    # never twice on one day
    off = copy.deepcopy(cfg)
    off["screen"]["picks"]["enabled"] = False
    assert not screen.picks_due(off, fri, None)


def _edition(out, day=FRIDAY):
    return {"edition_id": day.date().isoformat(), "screen": out.block}


def test_write_picks_with_a_fake_claude():
    cfg = load_config()
    out, _, _ = _fetch(want_pool=True)
    keys = [t["key"] for t in out.pool]
    assert len(keys) == len(set(keys)) and len(keys) >= 10
    lantern = next(t for t in out.pool if t["key"] == "tv:7101")
    assert lantern["listed"] == ["Netflix top 10 in Sweden (series), #1", "new on Netflix"]

    llm = ScreenLLM(cfg, "api", Tally(5.0), env={})
    got = screen.write_picks(cfg, llm, _edition(out), out.pool, [])
    p = got.picks
    assert p and len(p["titles"]) == 7 and p["model"] == "claude-opus-5-5"
    assert [t["reason"] for t in p["titles"]][:2] == ["Reason 1.", "Reason 2."]   # unknown and repeated ids dropped
    assert p["titles"][0]["on"] and p["titles"][0]["poster"]
    m = llm.material
    assert m["services"] == ["Netflix", "SVT Play (free)", "TV4 Play (free with ads)"] and m["picks_wanted"] == "6-8"
    rows = {t["id"]: t for t in m["titles"]}
    assert rows["tv:7801"]["on"] == ["TV4 Play (free with ads)"] and rows["tv:7801"]["new"] is True
    assert rows["movie:7201"]["new"] is False and rows["movie:7201"]["kind"] == "film"
    assert llm.schemas["screen"]["required"] == ["headline", "dek", "picks"]       # material came inside <data>

    # last week's picks aren't offered again, and a Tuesday isn't a picks day
    earlier = {"edition_id": "2026-10-30", "screen": {"picks": {"titles": [{"key": k} for k in keys[:3]]}}}
    llm = ScreenLLM(cfg, "api", Tally(5.0), env={})
    screen.write_picks(cfg, llm, _edition(out), out.pool, [earlier])
    assert not {t["id"] for t in llm.material["titles"]} & set(keys[:3])
    tuesday = _edition(out, FRIDAY - dt.timedelta(days=3))
    assert screen.write_picks(cfg, llm, tuesday, out.pool, []).picks is None


def test_picks_fail_softly():
    cfg = load_config()
    out, _, _ = _fetch(want_pool=True)
    llm = ScreenLLM(cfg, "api", Tally(5.0), env={})
    llm.fail = {"screen": TransientError("overloaded")}
    got = screen.write_picks(cfg, llm, _edition(out), out.pool, [])
    assert got.picks is None and "overloaded" in got.note
    assert "too few" in screen.write_picks(cfg, llm, _edition(out), out.pool[:3], []).note


# ── in the pipeline and on the pages ─────────────────────────────────────────

@pytest.fixture
def friday(monkeypatch):
    monkeypatch.setattr(gen, "fetch_all", lambda cfg, client, now, itad_key=None: _harvest_on(now))
    monkeypatch.setattr(ai_edition, "fetch_texts", lambda client, urls, limit=12000: {})


def _harvest_on(now):
    h = _harvest()
    h.fetched_at = now
    return h


def _factory(cfg, backend, tally, env):
    return ScreenLLM(cfg, backend, tally, env)


def test_friday_edition_has_the_lists_and_the_picks(tmp_path, friday):
    cfg, data = load_config(), tmp_path / "data"
    env = {**KEY, "TMDB_API_KEY": V3_KEY}
    r = gen.generate(cfg, data, "full", now=FRIDAY, env=env, client=FakeWeb(), llm_factory=_factory,
                     column="off", quiz_mode="off", forum_mode="off")
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["screen"]["picks"]["headline"] == "A lighthouse, a ferry and five more"
    assert ed["screen"]["new"] and "screen" in ed["llm"]["by_task"]
    assert "Screen: 4 new on Netflix" in gen.report(r) and "picks written: 7" in r.screen
    assert {"TMDB providers", "Netflix top 10"} <= {s["name"] for s in ed["sources"]}
    saved = json.loads((data / "screen.json").read_text())
    assert saved["since"]["Netflix"] == "2026-11-06" and V3_KEY not in (data / "screen.json").read_text()

    again = gen.generate(cfg, data, "full", now=FRIDAY, env=env, client=FakeWeb(), llm_factory=_factory,
                         column="off", quiz_mode="off", forum_mode="off")
    assert "kept today's picks" in again.screen and "screen" not in again.llm["by_task"]

    site = tmp_path / "site"
    build(cfg, data, site)
    page = (site / "screen" / "index.html").read_text(encoding="utf-8")
    assert "A lighthouse, a ferry and five more" in page and "Reason 1." in page
    assert "Picks of the week" in (site / "index.html").read_text(encoding="utf-8")


def test_links_edition_gets_the_lists_but_no_picks(tmp_path, friday):
    cfg, data = load_config(), tmp_path / "data"
    r = gen.generate(cfg, data, "links", now=FRIDAY, env={"TMDB_API_KEY": V3_KEY}, client=FakeWeb())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["mode"] == "links" and ed["screen"]["new"] and "picks" not in ed["screen"]
    forced = gen.generate(cfg, data, "links", now=FRIDAY, env={}, client=FakeWeb(), screen_mode="force")
    assert "a links edition has no Claude" in forced.screen
    ed = json.loads(store.edition_path(data, forced.edition_id).read_text())
    assert not ed["screen"]["tmdb"] and ed["screen"]["top10"]                       # no key: the top 10 only


def test_screen_page_and_front_band_from_the_fixtures(tmp_path):
    cfg = load_config()
    site = tmp_path / "site"
    build(cfg, ROOT / "tests" / "fixtures", site, preview=True)
    page = (site / "screen" / "index.html").read_text(encoding="utf-8")
    for text in ("A lighthouse mystery, a Baltic port and five more", "New on SVT Play", "New on TV4 Play",
                 "Netflix top 10 in Sweden", "Week of 26 Oct–1 Nov", "Older but great", "Just added",
                 "This product uses the TMDB API but is not endorsed or certified by TMDB", "JustWatch",
                 "static/tmdb.svg", "Picked by Claude (AI)"):
        assert text in page, text
    assert '<span class="svc">SVT Play<span class="svc-type"> · free</span></span>' in page
    assert "Waiting for a TMDB key" not in page
    front = (site / "index.html").read_text(encoding="utf-8")
    assert "Picks of the week" in front and "Netflix top 10 · Sweden" in front and 'href="/times/screen/"' in front
    assert "Screen" not in (site / "archive" / "2026-11-02" / "index.html").read_text(encoding="utf-8").split(
        "<main", 1)[1].split("</main>", 1)[0]                           # the links edition before Screen existed
    assert "themoviedb.org" in (site / "404.html").read_text(encoding="utf-8")              # footer credit


def test_screen_page_without_a_key(tmp_path):
    cfg, data = load_config(), tmp_path / "data"
    ed = json.loads((ROOT / "tests/fixtures/editions/2026/11/03.json").read_text(encoding="utf-8"))
    ed["screen"] = {k: v for k, v in ed["screen"].items() if k in ("region", "checked_at", "top10")}
    ed["screen"].update(tmdb=False, services=[], new=[], classics=[])
    store.save_edition(data, ed)
    build(cfg, data, tmp_path / "site")
    page = (tmp_path / "site" / "screen" / "index.html").read_text(encoding="utf-8")
    assert "Waiting for a TMDB key" in page and "Netflix top 10 in Sweden" in page and "Picks of the week" not in page
    assert "Netflix top 10 · Sweden" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")

    empty = tmp_path / "empty"
    ed.pop("screen")
    store.save_edition(empty, ed)
    build(cfg, empty, tmp_path / "site2")
    assert "Nothing to watch listed yet" in (tmp_path / "site2" / "screen" / "index.html").read_text(encoding="utf-8")
