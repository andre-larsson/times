"""The deals cadence (newsroom/deals.py): checked on deals.days, carried over in between. No network, no cost."""

from __future__ import annotations

import datetime as dt
import json
import shutil

import pytest

from newsroom import ROOT, ai_edition, forum, store
from newsroom import deals as deal_days
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.forum import day as forum_day
from newsroom.render import build
from newsroom.sources import fetch_all
from tests.test_ai import KEY, factory
from tests.test_deals import FakeITAD, _itad_only
from tests.test_pipeline import NOW, FakeClient, _harvest

UTC = dt.timezone.utc
TUE = dt.date(2026, 11, 3)                           # NOW is Tuesday 3 Nov 2026, 07:55 in Stockholm


def _cfg() -> dict:
    """The real config without Screen, whose fetches these tests don't serve."""
    cfg = load_config()
    cfg["screen"]["enabled"] = False
    return cfg


def _day(n: int) -> dt.datetime:
    """NOW plus n days: 0 Tuesday, 1 Wednesday, 3 Friday, 4 Saturday, 7 the next Tuesday."""
    return NOW + dt.timedelta(days=n)


def test_due_on_check_days_and_the_safety_net():
    days = ["tue", "fri"]
    d = lambda n: TUE + dt.timedelta(days=n)                                        # noqa: E731
    assert deal_days.due(d(0), days, d(-4)) == "check day (Tuesday)"
    assert deal_days.due(d(1), days, d(0)) == "" and deal_days.due(d(2), days, d(0)) == ""   # Wed, Thu carry
    assert deal_days.due(d(3), days, d(0)) == "check day (Friday)"
    assert deal_days.due(d(6), days, d(3)) == ""                                    # Mon: Friday's check
    assert deal_days.due(d(4), days, d(0)) == "missed Friday's check"              # no check on Friday
    assert deal_days.due(d(0), days, d(0)) == ""                                    # a second slot that day
    assert deal_days.due(d(0), days, None) == "no earlier check"
    assert deal_days.due(d(5), ["mon"], d(0), max_age_days=4) == "last check 5 days ago"
    assert deal_days.due(d(5), ["mon"], d(0), max_age_days=7) == ""
    assert deal_days.due(d(1), [], d(0)).startswith("checked every edition")
    assert deal_days.next_check(d(0), days) == d(3) and deal_days.next_check(d(3), days) == d(7)
    assert deal_days.next_check(d(0), []) is None
    cfg = load_config()
    assert deal_days.settings(cfg) == (["tue", "fri"], 4)                           # the configured cadence


def _row(game: str, expires: str | None, **kw) -> dict:
    return {"game": game, "shop": "Steam", "price": 2.0, "regular": 10.0, "currency": "EUR", "cut": 80,
            "lowest_ever": True, "expires": expires, "url": f"https://example.com/steam/{game}", **kw}


def test_carry_drops_ended_deals_and_keeps_the_rest():
    wed_noon, thu = "2026-11-04T12:00:00Z", "2026-11-05T18:00:00Z"
    block = {"checked_at": NOW.isoformat(), "source": "itad",
             "featured": [_row("Ember Lane", wed_noon, headline="Ember Lane: Buy", verdict="buy")],
             "more": [_row("Quill Harbor", thu, advice="Good.", verdict="hold"), _row("Tin Orchard", None)],
             "shelves": [{"pool": "hidden", "name": "Hidden gems", "deals": [_row("Moss Relay", wed_noon)]},
                         {"pool": "popular", "name": "Popular", "deals": [_row("Brine Street", thu)]}]}
    wed = deal_days.carry(block, "2026-11-03", _day(1))                            # Wednesday 06:55 UTC
    assert deal_days.count(wed) == 5 and wed["carried"] == {"from": "2026-11-03", "ended": 0}
    assert wed["checked_at"] == block["checked_at"] and wed["more"][0]["advice"] == "Good."
    thu_block = deal_days.carry(wed, "2026-11-04", _day(2))                         # Thursday: two have ended
    assert [d["game"] for d in thu_block["featured"]] == []
    assert [s["name"] for s in thu_block["shelves"]] == ["Popular"]                 # an emptied shelf goes
    assert thu_block["carried"] == {"from": "2026-11-03", "ended": 2}              # still Tuesday's check
    assert [d["game"] for d in deal_days.carry(thu_block, "2026-11-05", _day(3))["more"]] == ["Tin Orchard"]
    assert deal_days.count(deal_days.carry({"more": [_row("Odd Date", "soon-ish")]}, "x", NOW)) == 1   # kept


def test_carried_days_fetch_no_deals_lists():
    cfg = load_config()
    carried = deal_days.fetch_config(cfg, refresh=False)
    assert "specials" not in carried["sources"]["steam"]["lists"] and carried["sources"]["itad"]["deals"] is False
    assert cfg["sources"]["itad"].get("deals", True) and "specials" in cfg["sources"]["steam"]["lists"]
    assert deal_days.fetch_config(cfg, refresh=True) is cfg
    client = FakeITAD({"popular": ["g1"]})
    h = fetch_all(_itad_only(carried), client, NOW, itad_key="k")
    assert h.itad is None and client.filters == {}                                  # no /deals/v2 call
    assert not any(s.name.startswith("IsThereAnyDeal") for s in h.status)


@pytest.fixture
def fetches(monkeypatch):
    """A fake fetch that remembers the config it saw and dates the harvest to the run. Steam specials:
    Copperline (no end date), Lanternfall (ends Wednesday evening) and an expired one."""
    seen: list[dict] = []

    def fake(cfg, client, now, itad_key=None):
        seen.append(cfg)
        h = _harvest()
        h.fetched_at = now
        if "specials" not in cfg["sources"]["steam"]["lists"]:
            h.steam.pop("specials")
        else:
            special = dict(h.steam["specials"][0], appid=9, title="Lanternfall", store_url="https://example.com/s/9",
                           discount_end="2026-11-04T18:00:00+00:00")
            h.steam["specials"] = h.steam["specials"] + [special]
        return h

    monkeypatch.setattr(gen, "fetch_all", fake)
    monkeypatch.setattr(ai_edition, "fetch_texts", lambda client, urls, limit=12000: {})
    return seen


def _deals(data, edition_id):
    return store.load_edition(data, edition_id)["deals"]


def test_links_editions_check_on_tuesday_and_carry_on_wednesday(tmp_path, fetches):
    cfg, data, client = _cfg(), tmp_path / "data", FakeClient({})
    tue = gen.generate(cfg, data, "links", now=_day(0), env={}, client=client)
    assert tue.published and tue.deals.startswith("checked (no earlier deals)")
    assert "specials" in fetches[-1]["sources"]["steam"]["lists"]
    assert [d["game"] for d in _deals(data, "2026-11-03")["more"]] == ["Copperline", "Lanternfall"]

    wed = gen.generate(cfg, data, "links", now=_day(1), env={}, client=client)
    assert wed.published and "specials" not in fetches[-1]["sources"]["steam"]["lists"]
    deals = _deals(data, "2026-11-04")
    assert deals["carried"] == {"from": "2026-11-03", "ended": 0} and deals["checked_at"] == _day(0).isoformat()
    assert [d["game"] for d in deals["more"]] == ["Copperline", "Lanternfall"]
    report = gen.report(wed)
    assert "Deals not checked today: carried over from Tue 3 Nov 07:55; next check Fri" in report
    assert "| Deals | skipped — not checked today: carried over from Tue 3 Nov 07:55; next check Fri | 2 |" in report
    assert "FAILED" not in report

    gen.generate(cfg, data, "links", now=_day(2), env={}, client=client)                     # Thursday
    assert [d["game"] for d in _deals(data, "2026-11-05")["more"]] == ["Copperline"]         # Lanternfall ended
    assert _deals(data, "2026-11-05")["carried"]["ended"] == 1

    fri = gen.generate(cfg, data, "links", now=_day(3), env={}, client=client)
    assert fri.deals.startswith("checked (check day (Friday))") and "carried" not in _deals(data, "2026-11-06")


def test_force_carry_and_the_safety_net(tmp_path, fetches):
    cfg, data, client = _cfg(), tmp_path / "data", FakeClient({})
    gen.generate(cfg, data, "links", now=_day(0), env={}, client=client)
    forced = gen.generate(cfg, data, "links", now=_day(1), env={}, client=client, deals_mode="force")
    assert forced.deals.startswith("checked (forced") and "carried" not in _deals(data, "2026-11-04")
    with pytest.raises(ValueError):
        gen.generate(cfg, data, "links", now=_day(1), env={}, client=client, deals_mode="sometimes")

    # Friday's edition never ran: Saturday checks
    sat = gen.generate(cfg, data, "links", now=_day(4), env={}, client=client)
    assert sat.deals.startswith("checked (missed Friday's check)")
    kept = gen.generate(cfg, data, "links", now=_day(7), env={}, client=client, deals_mode="carry")
    assert kept.deals.startswith("not checked today") and _deals(data, "2026-11-10")["carried"]["from"] == "2026-11-07"


def test_a_check_that_finds_nothing_keeps_the_last_one(tmp_path, monkeypatch, fetches):
    cfg, data, client = _cfg(), tmp_path / "data", FakeClient({})
    gen.generate(cfg, data, "links", now=_day(0), env={}, client=client)
    real = gen.fetch_all

    def broken(cfg, client, now, itad_key=None):                     # Steam specials down on Friday
        h = real(cfg, client, now, itad_key)
        h.steam["specials"] = []
        return h

    monkeypatch.setattr(gen, "fetch_all", broken)
    fri = gen.generate(cfg, data, "links", now=_day(3), env={}, client=client)
    assert fri.deals.startswith("the check found nothing, so carried over from Tue 3 Nov 07:55")
    assert [d["game"] for d in _deals(data, "2026-11-06")["more"]] == ["Copperline"]
    monkeypatch.setattr(gen, "fetch_all", real)
    sat = gen.generate(cfg, data, "links", now=_day(4), env={}, client=client)          # tries again
    assert sat.deals.startswith("checked (missed Friday's check)")


def test_ended_deals_and_an_unrated_check_bring_a_new_one(tmp_path, fetches):
    cfg, data, client = _cfg(), tmp_path / "data", FakeClient({})
    gen.generate(cfg, data, "links", now=_day(0), env={}, client=client)
    path = store.edition_path(data, "2026-11-03")
    ed = json.loads(path.read_text())
    for d in ed["deals"]["more"]:
        d["expires"] = "2026-11-03T20:00:00+00:00"
    path.write_text(json.dumps(ed))
    wed = gen.generate(cfg, data, "links", now=_day(1), env={}, client=client)
    assert wed.deals.startswith("checked (every deal from the last check has ended)")

    # the links edition's deals were never rated: Thursday's AI edition checks (and rates) them
    thu = gen.generate(cfg, data, "full", now=_day(2), env=KEY, client=client, llm_factory=factory())
    assert thu.mode == "full" and thu.deals.startswith("checked (the last check wasn't rated)")
    assert thu.llm["by_task"]["deals"]["calls"] == 1


def test_ai_editions_carry_the_ratings_and_the_botroom_skips_the_deal(tmp_path, fetches):
    cfg, data, client = _cfg(), tmp_path / "data", FakeClient({})
    tue = gen.generate(cfg, data, "full", now=_day(0), env=KEY, client=client, llm_factory=factory())
    assert tue.mode == "full" and tue.llm["by_task"]["deals"]["calls"] == 1
    deal = _deals(data, "2026-11-03")["featured"][0]["headline"]
    day = forum.load_day(data, "2026-11-03")                     # as if the bots commented on Tuesday's deal
    day["threads"].append({"kind": "deal", "title": deal, "comments": []})
    forum.day_path(data, "2026-11-03").write_text(json.dumps(day), encoding="utf-8")

    wed = gen.generate(cfg, data, "full", now=_day(1), env=KEY, client=client, llm_factory=factory())
    assert wed.mode == "full" and "deals" not in wed.llm["by_task"]                  # no deals call
    deals = _deals(data, "2026-11-04")
    assert deals["featured"][0]["headline"] == deal and deals["carried"]["from"] == "2026-11-03"
    assert all(d.get("verdict") for d in deals["more"])                              # Tuesday's ratings
    # the Botroom doesn't start a second thread on the same deal of the day (forum/day.py: used titles)
    edition = store.load_edition(data, "2026-11-04")
    assert any(t["kind"] == "deal" for t in forum_day.threads_for(edition, set()))
    assert not any(t["kind"] == "deal" for t in forum_day.threads_for(edition, {deal}))
    assert not any(t["kind"] == "deal" for t in forum.load_day(data, "2026-11-04")["threads"])


def test_carried_labels_say_when_prices_were_checked(tmp_path):
    cfg, data = _cfg(), tmp_path / "data"
    shutil.copytree(ROOT / "tests" / "fixtures", data)
    tue = store.load_edition(data, "2026-11-03")                                     # checked 06:30 Tuesday
    wed = {**tue, "edition_id": "2026-11-04", "generated_at": "2026-11-04T05:31:00Z",
           "deals": deal_days.carry(tue["deals"], "2026-11-03", _day(1))}
    for s in wed["stories"]:
        s["slug"] = f"{s['slug']}-wed"
    wed.pop("opinion", None), wed.pop("quiz", None)
    store.save_edition(data, wed)
    build(cfg, data, tmp_path / "site", preview=True)
    front = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "Prices checked Tuesday 06:30; they change." in front
    assert "Tuesday's deal" in front and "Deal of the day" not in front
    page = (tmp_path / "site" / "deals" / "index.html").read_text(encoding="utf-8")
    assert "Prices checked Tuesday 06:30 (next check Friday); they change." in page
    assert "Earlier picks, still running" not in page                               # today's page lists it
    archived = (tmp_path / "site" / "archive" / "2026-11-03" / "index.html").read_text(encoding="utf-8")
    assert "Prices checked 06:30; they change." in archived and "Deal of the day" in archived
