"""Engagement features: factual matching, checked follow-ups, variety and working destinations."""
from __future__ import annotations

import copy
import datetime as dt
import json
import shutil

from newsroom import ROOT, checkback, quiz, store, tonight
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.llm import TransientError
from newsroom.render import build
from tests.test_ai import FakeLLM
from tests.test_quiz import _llm, _today
from tests.test_render import LINK_RE

UTC = dt.timezone.utc
THURSDAY = {"edition_id": "2026-11-12", "generated_at": "2026-11-12T06:00:00Z", "stories": []}


def story(day, headline, body):
    return {"edition_id": day, "generated_at": day + "T06:00:00Z", "stories": [{
        "slug": "harbor-launch", "section": "tech", "tier": "medium", "headline": headline, "body": body,
        "sources": [{"name": "Example Daily", "url": f"https://example.com/harbor/{day}"}]}]}


OLDER = story("2026-11-02", "Harbor promises an offline mode", "Harbor says its next release will work offline.")
NEWER = story("2026-11-10", "Harbor ships offline mode", "Harbor released its offline mode. Shared libraries still need a connection.")
ITEM = {"original_id": "2026-11-02/harbor-launch", "update_id": "2026-11-10/harbor-launch",
        "headline": "Harbor's offline mode arrives", "then": "Harbor promised an offline mode.",
        "now": "The offline mode has shipped.", "next": "Shared libraries still need a connection.", "status": "updated"}


class FollowupLLM(FakeLLM):
    items = [ITEM]
    verdicts = [{"n": 1, "verdict": "ok", "problem": ""}]

    def _checkback(self, m):
        self.offered = m
        return {"items": self.items}

    def _checkback_check(self, m):
        self.checked = m
        return {"results": self.verdicts}


def followup_llm():
    base = _llm()
    return FollowupLLM(base.cfg, base.backend, base.tally, env={})


def test_weekly_followups_require_dated_reporting_and_second_approval():
    cfg, llm = load_config(), followup_llm()
    out = checkback.write(cfg, llm, THURSDAY, [OLDER, NEWER])
    assert out.feature and out.feature["items"][0]["original"]["edition_id"] == "2026-11-02"
    assert set(llm.checked["stories"]) == {ITEM["original_id"], ITEM["update_id"]}
    assert "Shared libraries" in llm.checked["stories"][ITEM["update_id"]]["body"]
    assert set(llm.schemas) == {"checkback", "checkback_check"}
    for verdicts in ([], [{"n": 1, "verdict": "drop"}], [{"n": 1, "verdict": "ok"}] * 2):
        llm = followup_llm()
        llm.verdicts = verdicts
        assert checkback.write(cfg, llm, THURSDAY, [OLDER, NEWER]).feature is None


def test_weekly_rejects_unknown_reversed_and_not_old_enough_pairs():
    for patch in ({"original_id": "unknown"}, {"original_id": ITEM["update_id"], "update_id": ITEM["original_id"]},
                  {"original_id": ITEM["update_id"]}, {"status": "invented"}, {"now": ""}):
        llm = followup_llm()
        llm.items = [{**ITEM, **patch}]
        assert checkback.write(load_config(), llm, THURSDAY, [OLDER, NEWER]).feature is None
        assert "checkback_check" not in llm.schemas


def test_weekly_schedule_reruns_and_failures(tmp_path):
    cfg, llm = load_config(), followup_llm()
    assert checkback.write(cfg, llm, {**THURSDAY, "edition_id": "2026-11-11"}, [OLDER, NEWER]).feature is None
    assert not llm.tally.calls
    assert "not enough" in checkback.write(cfg, llm, THURSDAY, [NEWER]).note
    for ed in [OLDER, NEWER]:
        store.save_edition(tmp_path, ed)
    today = copy.deepcopy(THURSDAY)
    assert gen._checkback(cfg, tmp_path, today, "links", llm) == ""
    assert gen._checkback(cfg, tmp_path, today, "full", llm).startswith("written")
    assert today["llm"]["by_task"]["checkback_check"]["calls"] == 1
    store.save_edition(tmp_path, today)
    again = followup_llm()
    assert "kept" in gen._checkback(cfg, tmp_path, copy.deepcopy(THURSDAY), "full", again)
    assert not again.tally.calls
    llm = followup_llm()
    llm.fail = {"checkback_check": TransientError("overloaded")}
    assert "overloaded" in checkback.write(cfg, llm, THURSDAY, [OLDER, NEWER]).note


def test_picker_deduplicates_omits_expired_avoided_and_unknown_budget():
    game = {"game": "Harbor Cargo", "url": "https://example.com/harbor", "price": 5, "currency": "EUR",
            "tags": ["Management"], "expires": "2026-11-13T00:00:00Z"}
    deals = {"featured": [game], "more": [game, {**game, "game": "Ended", "expires": "2026-11-01T00:00:00Z"},
             {**game, "game": "Avoided", "verdict": "avoid"}, {**game, "game": "No price", "price": None},
             {**game, "game": "Unsafe", "url": "javascript:alert(1)"}]}
    film = {"key": "movie:9001", "kind": "movie", "title": "Harbor Ferry", "url": "https://example.com/film",
            "genres": ["Drama"], "on": [{"service": "SVT Play", "type": "free"}]}
    screen = {"new": [{"titles": [film, {**film, "key": "bad", "on": []}]}], "classics": [film]}
    rows = tonight.catalog(deals, {}, screen, None, dt.datetime(2026, 11, 12, tzinfo=UTC))
    assert [r["title"] for r in rows] == ["Harbor Cargo", "No price", "Harbor Ferry"]
    assert rows[1]["price"] is None and rows[0]["genres"] == ["Management"]
    assert rows[-1]["services"] == ["SVT Play"]
    older_pick = {"titles": [{**film, "on": [{"service": "Netflix"}]}],
                  "edition_generated_at": "2026-11-06T06:00:00Z"}
    current = {**screen, "checked_at": "2026-11-12T06:00:00Z"}
    watched = tonight.catalog({}, {}, current, older_pick, dt.datetime(2026, 11, 12, tzinfo=UTC))
    assert watched[0]["services"] == ["SVT Play"] and watched[0]["checked"] == current["checked_at"]


def test_quiz_variety_and_option_specific_notes_survive_shuffle():
    qz = quiz.write(load_config(), _llm(), _today(), [], force=True).quiz
    assert qz and len({q["kind"] for q in qz["questions"]}) >= 3
    for q in qz["questions"]:
        assert q["option_notes"][q["answer"]] == ""
        assert all(note for i, note in enumerate(q["option_notes"]) if i != q["answer"])
        for option, note in zip(q["options"], q["option_notes"]):
            if note:
                assert note.startswith(option + " differs")

    class Numerical(FakeLLM):
        def _quiz(self, m):
            rows = super()._quiz(m)
            for q in rows["questions"]:
                q.update(kind="number", answer="12%", wrong_answers=["20%", "40%", "80%"],
                         wrong_explanations=["The report says 12%."] * 3)
            return rows

    base = _llm()
    out = quiz.write(load_config(), Numerical(base.cfg, base.backend, base.tally, env={}), _today(), [], force=True)
    assert out.quiz is None and "passed the check" in out.note


def test_new_destinations_resolve_with_custom_base_and_weekly_issue(tmp_path):
    cfg = load_config()
    cfg["site"]["base_path"] = "/paper/"
    data, site = tmp_path / "data", tmp_path / "site"
    shutil.copytree(ROOT / "tests/fixtures", data)
    old = copy.deepcopy(OLDER)
    old["edition_id"] = "2026-10-27"
    # A fictional check-back issue in the fixture edition; all references point to real fixture pages.
    store.save_edition(data, old)
    path = data / "editions/2026/11/03.json"
    ed = json.loads(path.read_text())
    original = {"edition_id": old["edition_id"], **old["stories"][0]}
    update = {"edition_id": ed["edition_id"], **ed["stories"][0]}
    ed["checkback"] = {"items": [{**ITEM, "original": original, "update": update}]}
    path.write_text(json.dumps(ed))
    build(cfg, data, site, preview=True)
    front = (site / "index.html").read_text()
    assert front.index('class="discovery"') < front.index('class="top-stories"')
    assert "/paper/tonight/" in front and "/paper/checked-back/2026-11-03/" in front
    assert "Harbor&#39;s offline mode arrives" in (site / "checked-back/2026-11-03/index.html").read_text()
    for page in site.rglob("*.html"):
        for link in LINK_RE.findall(page.read_text()):
            if link.startswith(("http", "#", "mailto:")):
                continue
            assert link.startswith("/paper/")
            target = site / link[len("/paper/"):].split("?")[0].split("#")[0]
            assert target.is_file() or (target / "index.html").is_file(), (page, link)
