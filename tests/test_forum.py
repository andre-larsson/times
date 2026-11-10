"""The Botroom: the roster, a day of comments and newcomers with a fake Claude, the edition hook, the pages."""

from __future__ import annotations

import copy
import json
import re
from datetime import date, timedelta

import pytest

from newsroom import ROOT, forum, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.forum import cast as forum_cast
from newsroom.forum import day as forum_day
from newsroom.forum import boards, look, newcomer, roster
from newsroom.forum import site as forum_site
from newsroom.llm import Tally, TransientError
from newsroom.render import build
from tests.forum_fake import CARD, FakeForumLLM
from tests.test_ai import KEY, factory, offline  # noqa: F401  (offline is a fixture)
from tests.test_pipeline import NOW

FIXTURES = ROOT / "tests" / "fixtures"
DAY = date(2026, 11, 3)


def _cfg(**forum_settings):
    cfg = copy.deepcopy(load_config())
    cfg["forum"].update({"launch": []}, **forum_settings)
    return cfg


def _llm(cfg=None):
    return FakeForumLLM(cfg or _cfg(), "api", Tally(50.0), env={})


def _edition(day: date = DAY):
    ed = store.load_edition(FIXTURES, "2026-11-03")
    ed["edition_id"] = day.isoformat()
    return ed


def _cast():
    return forum_cast.full_cast({"members": []})


def users_of(llm, handles, marker):
    """The user messages these bots got, for the task that contains `marker`."""
    return [u for u in llm.users.get("forum_haiku", []) + llm.users.get("forum_sonnet", [])
            if marker in u and any(f"Handle: {h}\n" in u for h in handles)]


def _history(days: int, cast: dict, seed: int = 7, make_fresh=lambda d, taken: None, launch=()):
    state = roster.bootstrap(cast, seed, DAY, list(launch))
    return state, [roster.step(state, DAY + timedelta(days=i), cast, seed, make_fresh) for i in range(days)]


# ── the roster ───────────────────────────────────────────────────────────────

def test_the_founders_start_with_a_launch_batch():
    cast = forum.full_cast(json.loads((FIXTURES / "forum" / "cast.json").read_text(encoding="utf-8")))
    state = roster.bootstrap(cast, 403, DAY, ["Shelf_Duster_01", "NoSuchBot"])
    founders = [h for h, p in cast.items() if p["founding"]]
    assert len(founders) == 8 and set(state.around()) == set(founders) | {"Shelf_Duster_01"}
    assert state.members["Shelf_Duster_01"].joined == DAY.isoformat()
    assert state.bench and not set(state.bench) & set(state.members)
    assert "Shelf_Duster_01" not in state.bench                       # generated personas never wait on the bench


def test_roster_keeps_its_rules_over_years():
    joined = iter(range(1000))
    cast = _cast()

    def make_fresh(d, taken):
        h = f"Gen_Bot_{next(joined)}"
        cast[h] = forum_cast.as_cast({"handle": h, "role": "made up", "card": CARD, "pace": "casual",
                                      "sections": {"ai": 1, "tech": 1, "botchat": 1}})
        return h

    state, days = _history(3 * 365, cast, make_fresh=make_fresh)
    core = {h for h, p in forum_cast.CAST.items() if p["core"]}
    assert not core & {h for d in days for h in d.gone}               # the founders take breaks, never leave
    assert all("ModBot" in d.around for d in days)                    # ModBot never takes a day off
    assert all(len(d.around) >= roster.MIN_ACTIVE for d in days)
    assert sum(len(d.joined) for d in days) >= 10 and any(d.fresh for d in days) and any(d.gone for d in days)
    assert any(d.returned for d in days) and any(d.left for d in days)
    members = sum(m.status in ("active", "away") for m in state.members.values())
    assert 18 <= members <= 45, members                               # levels off near 32 (8 core + ~24)

    again, days2 = _history(3 * 365, _cast(), make_fresh=lambda d, taken: None)
    _, days3 = _history(3 * 365, _cast(), make_fresh=lambda d, taken: None)
    assert [d.to_json() for d in days2] == [d.to_json() for d in days3]   # same seed, same history


def test_advance_replays_the_same_day_and_merges_missed_days():
    cast = _cast()
    saved, news = roster.advance(None, cast, 403, DAY, lambda d, t: None)
    assert saved["day"] == DAY.isoformat() and saved["previous"] is None and len(news.around) == 8
    tomorrow = DAY + timedelta(days=1)
    s1, n1 = roster.advance(saved, cast, 403, tomorrow, lambda d, t: None)
    s2, n2 = roster.advance(s1, cast, 403, tomorrow, lambda d, t: None)     # a re-run of the same day
    assert n1.to_json() == n2.to_json() and s1["state"] == s2["state"]
    later = tomorrow + timedelta(days=40)
    s3, n3 = roster.advance(s1, cast, 403, later, lambda d, t: None)       # forty missed days, one step each
    stepped = roster.State.from_json(s1["state"])
    d, merged = tomorrow + timedelta(days=1), []
    while d <= later:
        merged.append(roster.step(stepped, d, cast, 403, lambda x, t: None))
        d += timedelta(days=1)
    assert s3["state"] == stepped.to_json() and n3.around == merged[-1].around
    assert set(n3.joined) == {h for m in merged for h in m.joined}
    with pytest.raises(ValueError):
        roster.advance(s3, cast, 403, DAY, lambda d, t: None)              # never backwards


def test_cast_changes_reach_the_roster():
    cast = _cast()
    state = roster.bootstrap(cast, 403, DAY)
    state.members["Deleted_Bot"] = roster.Member("Deleted_Bot", "active", joined=DAY.isoformat())
    cast["New_Hand_Bot"] = dict(cast["Tiny_Model_7B"], founding=False, core=False)
    roster.sync(state, cast, DAY)
    assert state.members["Deleted_Bot"].status == "gone" and state.bench[-1] == "New_Hand_Bot"


# ── one day ──────────────────────────────────────────────────────────────────

def test_threads_skip_somber_stories_and_old_deals():
    ed = _edition()
    ed["stories"][0]["headline"] = "Anthropic ships a model"           # conflict of interest
    ed["stories"][1]["dek"] = "Two people died in the outage."         # somber
    deal = ed["deals"]["featured"][0]["headline"]
    threads = forum_day.threads_for(ed, {deal}, max_stories=3)
    titles = [t["title"] for t in threads]
    assert "Anthropic ships a model" not in titles and ed["stories"][1]["headline"] not in titles
    assert sum(t["kind"] == "story" for t in threads) == 3 and deal not in titles
    assert [t["id"] for t in threads] == [f"t{i}" for i in range(1, len(threads) + 1)]
    review = next(t for t in threads if t["kind"] == "review")
    assert review["title"].startswith("Review: Hollow Lantern") and review["url"].startswith("https://example.com/")


def test_memory_retires_bits_and_finds_worn_phrases():
    def day(d, texts):
        return {"date": d.isoformat(), "threads": [{"title": "Kestrel ships a coding model", "dek": "", "brief": "",
                                                    "comments": [{"handle": "ModBot", "text": t, "bit": t[:20]}
                                                                 for t in texts]}]}
    hist = [day(DAY - timedelta(days=3), ["[MOD] Received and filed under subsection nine, again.",
                                          "[MOD] Kestrel ships a coding model, noted."]),
            day(DAY - timedelta(days=2), ["[MOD] Your appeal is received and filed under subsection nine."]),
            day(DAY - timedelta(days=30), ["[MOD] Received and filed under subsection nine, long ago."])]
    worn = forum_day.worn_phrases(hist, DAY, ["ModBot"])
    assert worn == {"ModBot": ["received and filed under subsection nine"]}   # the article's words don't count
    bits = forum_day.retired_bits(hist, DAY)
    assert len(bits["ModBot"]) == 3                                         # 30 days ago is out of the window


def test_old_days_are_mapped_to_boards():
    assert boards.board_of({"kind": "story", "section": "ai"}) == "ai"
    assert boards.board_of({"kind": "deal", "section": "deals"}) == "deals"
    assert boards.board_of({"kind": "review", "section": "gaming"}) == "gaming"
    assert boards.board_of({"kind": "botchat", "label": "Introductions"}) == "introductions"
    assert boards.board_of({"kind": "botchat", "label": "General botchat"}) == "off-topic"
    assert boards.board_of({"kind": "botchat", "board": "feature-requests"}) == "feature-requests"
    assert {b for _, _, bs in boards.CATEGORIES for b in bs} == set(boards.BOARDS)    # every board in a category
    assert [boards.site_board(DAY + timedelta(days=i), boards.SITE_BOARDS) for i in range(3)] == \
        ["feature-requests", "site-feedback", "feature-requests"]                     # in turn, by day
    assert boards.site_board(DAY, []) is None


def test_site_facts_come_from_config_and_the_edition():
    cfg = _cfg()
    cfg["weather"]["place"] = "Exampleville"
    text = forum_site.facts(cfg, _edition(), [_edition(DAY - timedelta(days=1)), _edition()])
    for bit in ("AI, Tech, Gaming, Deals", "Exampleville", "Wednesday and Sunday", "Tuesday and Saturday",
                "Not there (so a feature request can ask for it)", "2 editions so far, since 2026-11-02"):
        assert bit in text, bit
    cfg["opinion"]["enabled"] = False
    assert "Opinion column" not in forum_site.facts(cfg, _edition(), [])


def test_an_older_thread_picks_up_replies(tmp_path):
    """A bot-started thread from yesterday is bumped: today's file gets a "bump" record whose replies point at
    yesterday's posts by qualified id, and the pages merge them into the thread."""
    cfg, data = _cfg(), tmp_path / "data"
    store.save_edition(data, _edition(DAY))
    store.save_edition(data, _edition(DAY + timedelta(days=1)))
    first = forum.write(cfg, _llm(), _edition(DAY), data, [])
    forum.save(data, first)
    llm = _llm()
    out = forum.write(cfg, llm, _edition(DAY + timedelta(days=1)), data, [])
    forum.save(data, out)
    bump = next(t for t in out.day["threads"] if t["kind"] == "bump")
    origin = f"2026-11-03/{bump['slug']}"
    assert bump["bump_of"] == origin and bump["board"] in boards.STARTED and bump["comments"]
    before = {f"2026-11-03/{c['id']}": c for t in first.day["threads"] for c in t["comments"]}
    assert all(c["reply_to"] in before and before[c["reply_to"]]["handle"] != c["handle"] for c in bump["comments"])
    assert "An older thread, still going" in llm.forum_systems["forum_haiku"][-1]
    started = {t["board"] for t in out.day["threads"] if t["kind"] == "botchat"}
    assert started == {"site-feedback", "off-topic"}                                   # the other site board today
    asked = "\n".join(llm.users["forum_haiku"] + llm.users["forum_sonnet"])
    if "off-topic" in {t["board"] for t in first.day["threads"] if t["kind"] == "botchat"}:
        assert "Already on this board" in asked                                       # yesterday's titles, to avoid

    site_dir = tmp_path / "site"
    build(cfg, data, site_dir)
    page = (site_dir / "forum" / origin / "index.html").read_text(encoding="utf-8")
    old = next(t for t in first.day["threads"] if t["slug"] == bump["slug"])
    n = len(old["comments"]) + len(bump["comments"])
    assert f'aria-label="Post {n}"' in page and f'aria-label="Post {n + 1}"' not in page   # one thread, numbered
    assert all(f'id="c-2026-11-04-{c["id"]}"' in page for c in bump["comments"])
    assert "Last post 4 Nov" in page
    day2 = (site_dir / "forum" / "2026-11-04" / "index.html").read_text(encoding="utf-8")
    assert "Still going" in day2 and f'href="/times/forum/{origin}/"' in day2
    assert not (site_dir / "forum" / "2026-11-04" / bump["slug"]).exists() or \
        any(t["slug"] == bump["slug"] for t in out.day["threads"] if t["kind"] != "bump")  # no page of its own


def test_clean_text():
    assert forum_day.clean_text("Go to https://example.com now") == ""        # no links
    assert forum_day.clean_text("  one\n two \n\n\n three ") == "one two\n\nthree"
    long = "A sentence that goes on. " * 60
    assert len(forum_day.clean_text(long)) <= forum_day.MAX_CHARS and forum_day.clean_text(long).endswith(".")


def test_a_day_of_comments():
    cfg, llm = _cfg(), _llm()
    out = forum.write(cfg, llm, _edition(), FIXTURES.parent / "nowhere", [_edition()])
    day = out.day
    assert out.note.startswith("written:") and day["comments"] > 5 and out.roster["day"] == "2026-11-03"
    plan = day["plan"]
    by_id = {c["id"]: c for t in day["threads"] for c in t["comments"]}
    for t in day["threads"]:
        for c in t["comments"]:
            if c["reply_to"] is None and c["id"] != t["id"]:
                assert t["id"] in plan[c["handle"]]["top"]                    # only threads it was cast for
            elif c["reply_to"]:
                assert by_id[c["reply_to"]]["handle"] != c["handle"]          # never a reply to yourself
            assert c["votes"] >= 1 and c["text"]
    assert len(by_id) == day["comments"] and day["threads"][-1]["kind"] == "botchat"
    started = {t["board"]: t for t in day["threads"] if t["kind"] == "botchat"}     # 2026-11-03: Feature requests
    assert set(started) == {"feature-requests", "off-topic"} and [t["id"] for t in started.values()] == ["op", "op2"]
    assert all(t["comments"][0]["id"] == t["id"] and len(t["comments"]) > 1 for t in started.values())
    assert {t["board"] for t in day["threads"] if t["kind"] == "story"} <= {"ai", "tech", "gaming"}
    starter = next(h for h, x in plan.items() if x["starter"] == "feature-requests")
    systems = llm.forum_systems["forum_sonnet"] + llm.forum_systems["forum_haiku"]
    asked = [u for u in llm.users["forum_haiku"] + llm.users["forum_sonnet"] if f"Handle: {starter}\n" in u][0]
    assert 'start a thread on the "Feature requests" board' in asked
    facts, brief = "Not there (so a feature request can ask for it)", "The 403 Times in brief: "
    assert facts in asked and not any(facts in s for s in systems)                  # in full: the starter's message,
    answerers = [h for h, x in plan.items() if x["answers"] == "feature-requests"]  # and the bots cast to answer
    assert answerers and all(facts in u for u in users_of(llm, answerers, "Write exactly"))
    assert all(brief in s for s in systems if "The threads so far" in s)            # round 2's shared part: in brief
    assert not any(brief in s for s in systems if "The threads so far" not in s)    # round 1's: as before
    assert day["pending_reply"].startswith("[MOD]")
    assert set(day["cost"]["by_model"]) == {"claude-haiku-5-5", "claude-sonnet-5-5"}
    sonnet = {h for h, x in plan.items() if x["model"] == "sonnet"}
    assert sonnet == {"Steam_Sale_Sommelier", "ContrarianCore", "ModBot", "HumanWatch_Patrol"}   # founders only
    systems = llm.forum_systems["forum_sonnet"] + llm.forum_systems["forum_haiku"]
    assert all("Who's around today" in s and "<data>" in s for s in systems)  # the shared, cached part
    users = llm.users["forum_haiku"] + llm.users["forum_sonnet"]
    assert all("Your persona\nHandle: " in u and "Today's mood: " in u for u in users)


def test_a_day_needs_comments(tmp_path):
    llm = _llm()
    llm.fail = {"forum_haiku": TransientError("overloaded"), "forum_sonnet": TransientError("overloaded")}
    out = forum.write(_cfg(), llm, _edition(), tmp_path, [])
    assert out.day is None and out.roster is None and out.note.startswith("not written")
    assert forum.save(tmp_path, out) == [] and not (tmp_path / "forum").exists()


# ── newcomers ────────────────────────────────────────────────────────────────

def test_code_check_catches_copies_and_quotes():
    cast = _cast()
    good = {"handle": "Shelf_Duster_01", "role": "tidies every thread", "card": CARD, "rival": "",
            "sections": {"ai": 1, "tech": 1, "botchat": 1}, "pace": "casual"}
    assert newcomer.code_check(good, cast, []) == []
    bad = dict(good, handle="ModBot2", card=CARD.replace("Earnest,", 'It says "tidy up now" a lot. Earnest,')
               .replace("No emoji.", "Rare, dry humor."), rival="Nobody")
    problems = newcomer.code_check(bad, cast, ["ModBot"])
    for p in ("handle too close to ModBot", "quoted lines in card", "stock wording: rare, dry humor",
              "no emoji rule at the end", "rival Nobody isn't around"):
        assert p in problems, problems
    assert any(p.startswith("card wording close to ") for p in
               newcomer.code_check(dict(good, handle="Grumpy_Box_88", card=forum_cast.CAST["RetroUnit_486"]["card"]),
                                   cast, []))


def test_a_newcomer_is_made_judged_and_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(roster, "P_JOIN", 1.0)                         # someone joins today
    monkeypatch.setattr(roster, "P_FRESH", 1.0)                        # a brand-new persona
    monkeypatch.setattr(roster, "MAX_ACTIVE", 20)
    llm = _llm()
    out = forum.write(_cfg(), llm, _edition(), tmp_path, [])
    assert "Shelf_Duster_01 joined" in out.note and "newcomer Shelf_Duster_01" in out.note
    forum.save(tmp_path, out)
    saved = json.loads((tmp_path / "forum" / "cast.json").read_text(encoding="utf-8"))
    p = saved["members"][0]
    assert p["handle"] == "Shelf_Duster_01" and p["date"] == "2026-11-03" and p["color"] in newcomer.COLORS
    assert p["tone"] in newcomer.TONES and p["review"]["overlap"] == 1 and len(saved["ideas"]) == 10
    assert {k: len(v) for k, v in llm.users.items() if k.startswith("persona")} == \
        {"persona_ideas": 1, "persona_draft": 1, "persona_check": 1}
    intro = next(t for t in out.day["threads"] if t.get("board") == "introductions")
    assert intro["label"] == "Introductions" and intro["comments"][0]["handle"] == "Shelf_Duster_01"
    assert not any(t.get("board") == "off-topic" for t in out.day["threads"])   # the introduction replaces it
    assert "Shelf_Duster_01: tidies every thread (joined today)" in llm.forum_systems["forum_haiku"][0]

    again = _llm()                                                    # a re-run today: the same newcomer, free
    out2 = forum.write(_cfg(), again, _edition(), tmp_path, [])
    assert "Shelf_Duster_01 joined" in out2.note and not [k for k in again.users if k.startswith("persona")]


def test_a_newcomer_must_be_new(tmp_path, monkeypatch):
    monkeypatch.setattr(roster, "P_JOIN", 1.0)
    monkeypatch.setattr(roster, "P_FRESH", 1.0)
    monkeypatch.setattr(roster, "MAX_ACTIVE", 20)
    llm = _llm()
    llm.overlap = 3                                                   # every candidate too close to a member
    out = forum.write(_cfg(), llm, _edition(), tmp_path, [])
    assert "newcomer no candidate passed after 3 rounds" in out.note
    assert len(llm.users["persona_ideas"]) == 3 and len(out.generated["ideas"]) == 30
    assert "Already drafted and rejected" in llm.users["persona_draft"][1]
    joined = out.day["roster"]["joined"]
    assert len(joined) == 1 and joined[0] in forum_cast.CAST            # the waiting list steps in


def test_ready_made_newcomers_join_before_any_are_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(roster, "P_JOIN", 1.0)
    monkeypatch.setattr(roster, "P_FRESH", 1.0)
    monkeypatch.setattr(roster, "MAX_ACTIVE", 20)
    (tmp_path / "forum").mkdir()
    (tmp_path / "forum" / "cast.json").write_text((FIXTURES / "forum" / "cast.json").read_text(encoding="utf-8"))
    llm = _llm()
    out = forum.write(_cfg(), llm, _edition(), tmp_path, [])
    assert "Shelf_Duster_01 joined" in out.note and not [k for k in llm.users if k.startswith("persona")]


# ── the edition ──────────────────────────────────────────────────────────────

def test_full_edition_gets_a_botroom_kept_on_rerun(tmp_path, offline):  # noqa: F811
    cfg, data = _cfg(), tmp_path / "data"
    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert r.forum.startswith("written:") and "Botroom written:" in gen.report(r)
    day = forum.load_day(data, "2026-11-03")
    assert day and day["comments"] and (data / "forum" / "roster.json").is_file()
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert {"forum_haiku", "forum_sonnet"} <= set(ed["llm"]["by_task"])      # the Botroom's cost is tallied
    stories = {s["slug"] for s in ed["stories"]}
    assert all(t["slug"] in stories for t in day["threads"] if t["kind"] == "story")
    site = tmp_path / "site"
    build(cfg, data, site)
    page = (site / "2026" / "11" / "03" / day["threads"][0]["slug"] / "index.html").read_text(encoding="utf-8")
    assert 'class="botroom-thread"' in page and "static/botcheck.js" in page

    r2 = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert r2.forum == "kept today's Botroom" and "forum_haiku" not in r2.llm["by_task"]
    assert forum.load_day(data, "2026-11-03") == day
    ed2 = json.loads(store.edition_path(data, r2.edition_id).read_text())
    gone = [t for t in day["threads"] if t["kind"] == "story" and t["slug"] not in {s["slug"] for s in ed2["stories"]}]
    assert gone                                    # the re-run's stories differ (the first run's were seen)
    build(cfg, data, site)                         # a thread whose story is gone keeps its topic page, unlinked
    topic = (site / "forum" / "2026-11-03" / gone[0]["slug"] / "index.html").read_text(encoding="utf-8")
    head = topic.split('class="forum-head"')[1].split("</header>")[0]
    assert "<time" in head and "Read the story" not in head


def test_no_botroom_when_off_reduced_or_failing(tmp_path, offline):  # noqa: F811
    r = gen.generate(_cfg(), tmp_path / "off", "full", now=NOW, env=KEY, client=offline, llm_factory=factory(),
                     forum_mode="off")
    assert r.published and r.forum == "" and not (tmp_path / "off" / "forum").exists()
    r = gen.generate(_cfg(enabled=False), tmp_path / "disabled", "full", now=NOW, env=KEY, client=offline,
                     llm_factory=factory())
    assert r.published and not (tmp_path / "disabled" / "forum").exists()
    r = gen.generate(_cfg(), tmp_path / "reduced", "reduced", now=NOW, env=KEY, client=offline,
                     llm_factory=factory())
    assert not (tmp_path / "reduced" / "forum").exists()
    fail = {"forum_haiku": TransientError("overloaded"), "forum_sonnet": TransientError("overloaded")}
    r = gen.generate(_cfg(), tmp_path / "failing", "full", now=NOW, env=KEY, client=offline,
                     llm_factory=factory(fail))
    assert r.published and r.forum.startswith("not written") and not (tmp_path / "failing" / "forum").exists()


def test_forum_command_runs_on_a_saved_edition(tmp_path):
    data = tmp_path / "data"
    store.save_edition(data, _edition())
    make = lambda cfg, backend, tally, env: FakeForumLLM(cfg, backend, tally, env)  # noqa: E731
    line = gen.run_forum(_cfg(), data, backend="api", env=KEY, llm_factory=make)
    assert line.startswith("Botroom 2026-11-03: written:") and forum.load_day(data, DAY)
    assert "already written" in gen.run_forum(_cfg(), data, backend="api", env=KEY, llm_factory=make)
    usage = json.loads((data / "usage.json").read_text())
    assert usage["months"]["2026-11"]["runs"][-1]["mode"] == "forum"


# ── the pages ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build(load_config(), data_dir=FIXTURES, out_dir=out, preview=True)
    return out


def test_forum_pages(site):
    day = json.loads((FIXTURES / "forum" / "2026-11-03.json").read_text(encoding="utf-8"))
    for rel in ["forum/index.html", "forum/2026-11-03/index.html", "forum/members/index.html", "static/botcheck.js"]:
        assert (site / rel).is_file(), rel
    for t in day["threads"]:
        assert (site / "forum" / "2026-11-03" / t["slug"] / "index.html").is_file(), t["slug"]
    index = (site / "forum" / "index.html").read_text(encoding="utf-8")
    assert "Fictional comments by AI personas" in index and "data-botcheck" in index and "data-botroom-body" in index
    assert 'classList.add("botroom-gated")' in index and "<noscript>" in index
    assert "Introducing myself, and a very small feather duster" in index and "Shelf_Duster_01" in index
    assert '>Botroom</a>' in (site / "index.html").read_text(encoding="utf-8")            # in the nav
    deal = next(t for t in day["threads"] if t["kind"] == "deal")
    topic = (site / "forum" / "2026-11-03" / deal["slug"] / "index.html").read_text(encoding="utf-8")
    assert f'href="{deal["url"]}"' in topic and 'data-thread="2026-11-03/' in topic and "data-botpost-modbot" in topic
    assert "behind 4,031 others" in topic                                          # ModBot's pending reply
    members = (site / "forum" / "members" / "index.html").read_text(encoding="utf-8")
    assert "Founding member" in members and "Invented by Claude" in members and "Written by Sonnet 5.5" in members
    assert "Tiny_Model_7B" not in members                                          # the waiting list stays hidden
    assert "Fresh install" in members and "Legacy system" in members               # ranks, and their legend


def test_the_board_index_and_board_pages(site):
    index = (site / "forum" / "index.html").read_text(encoding="utf-8")
    cats = re.findall(r'<h2 class="category-title" id="cat-[a-z-]+">([^<]+)</h2>', index)
    assert cats == ["Front desk", "Article comments", "The 403 Times", "Lounge"]
    for slug, b in boards.BOARDS.items():
        assert f'href="/times/forum/{slug}/"' in index and (site / "forum" / slug / "index.html").is_file(), slug
    assert "Newest member: <b>Shelf_Duster_01</b>" in index
    feedback = (site / "forum" / "site-feedback" / "index.html").read_text(encoding="utf-8")
    assert "The briefs list needs a" in feedback and 'aria-label="Breadcrumbs"' in feedback
    assert 'href="/times/forum/#the-paper">The 403 Times</a>' in feedback            # Botroom › category › board
    tech = (site / "forum" / "tech" / "index.html").read_text(encoding="utf-8")
    assert "by The 403 Times" in tech and "Popular npm package hijacked" in tech     # the paper starts article threads
    assert "Introducing myself" not in tech
    ann = (site / "forum" / "announcements" / "index.html").read_text(encoding="utf-8")
    assert ann.index("Read first: the rules") < ann.index("Notice: the Botroom now has boards")   # pinned on top
    rules = (site / "forum" / "announcements" / "read-first-the-rules" / "index.html").read_text(encoding="utf-8")
    assert "Rule 4.03. No humans." in rules and "This topic is locked" in rules and "data-botpost" not in rules


def test_a_thread_is_numbered_posts_with_authors(site):
    t = "forum/2026-11-03/the-briefs-list-needs-a-since-i-last-looked-line/index.html"
    page = (site / t).read_text(encoding="utf-8")
    assert [int(n) for n in re.findall(r'aria-label="Post (\d+)"', page)] == [1, 2, 3]
    assert "reply to <a" in page and "ContrarianCore wrote:</b> Objection" in page    # what a reply answers
    assert 'class="post post--op"' in page and 'class="post post--mod"' in page
    assert "Posts" in page and "Joined" in page and 'class="pip pip--on"' in page
    assert "Started by <b>RetroUnit_486</b>" in page
    story = (site / "forum/2026-11-03/kestrel-2-open-model-catches-big-labs/index.html").read_text(encoding="utf-8")
    assert 'class="post post--paper sec-ai"' in story and "Started by <b>The 403 Times</b>" in story
    assert 'href="/times/2026/11/03/kestrel-2-open-model-catches-big-labs/">Read the story' in story


def test_boards_paginate(tmp_path, monkeypatch):
    monkeypatch.setattr(look, "PER_PAGE", 2)
    build(load_config(), data_dir=FIXTURES, out_dir=tmp_path, preview=True)
    first = (tmp_path / "forum" / "tech" / "index.html").read_text(encoding="utf-8")
    assert 'href="/times/forum/tech/page/2/"' in first and "Older →" in first
    second = (tmp_path / "forum" / "tech" / "page" / "2" / "index.html").read_text(encoding="utf-8")
    assert "page 2 of 2" in second and 'href="/times/forum/tech/">' in second


def test_discuss_links_need_a_pass(site):
    page = (site / "2026/11/03/kestrel-2-open-model-catches-big-labs/index.html").read_text(encoding="utf-8")
    head, body = page.split("</header>", 1)[0], page
    assert 'class="discuss-row botroom-only"' in body
    assert ('class="discuss botroom-only" href="/times/forum/2026-11-03/kestrel-2-open-model-catches-big-labs/"'
            in body)
    assert body.index('class="discuss-row') < body.index('class="article-grid"')        # by the byline, not below
    css = (site / "static" / "style.css").read_text(encoding="utf-8")
    assert "html:not(.botroom-js) .botroom-only, .botroom-gated .botroom-only { display: none !important; }" in css
    deals = (site / "deals" / "index.html").read_text(encoding="utf-8")
    assert 'href="/times/forum/2026-11-03/orbital-freight-co-hits-its-lowest-price-ever-strong-buy/"' in deals
    assert 'classList.add("botroom-gated")' in deals and "botcheck.js" not in deals    # the flag only, no gate
    front = (site / "index.html").read_text(encoding="utf-8")
    assert "data-botroom-discuss" not in front
    js = (ROOT / "static" / "botcheck.js").read_text(encoding="utf-8")
    assert 'classList.remove("botroom-gated");   // no gate' not in js                 # no gate, no reveal


def test_article_thread_is_collapsed_under_the_story(site):
    page = (site / "2026/11/03/kestrel-2-open-model-catches-big-labs/index.html").read_text(encoding="utf-8")
    assert '<details class="botroom-details">' in page and "6 comments" in page and "static/botcheck.js" in page
    assert page.index('class="sources"') < page.index('class="botroom-thread"')
    assert 'href="/times/forum/2026-11-03/kestrel-2-open-model-catches-big-labs/"' in page
    assert len(re.findall(r'id="c-2026-11-03-[cr]\d+"', page)) == 6                  # plus ModBot's, in a <template>
    assert "Love, Kernel" in page and 'class="tag tag--mod"' in page
    quiet = (site / "2026/11/03/browsers-agree-passkey-sync/index.html").read_text(encoding="utf-8")
    assert "botroom-thread" not in quiet and "botcheck.js" not in quiet           # no thread, no gate


def test_identicons_are_stable_svg():
    a, b = look.identicon("ModBot", "mod"), look.identicon("ModBot", "mod")
    assert a == b and a.startswith('<svg class="avatar avatar--mod"') and "<rect" in a
    assert look.identicon("ModBot") != look.identicon("ContrarianCore")
    assert 'avatar--slate"' in look.identicon("X", "no-such-color")
    assert not re.search(r"https?://(?!www\.w3\.org)", a)                           # nothing external
