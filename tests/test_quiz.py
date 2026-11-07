"""The news quiz: schedule, writing and checking it with a fake Claude, rendering, and keeping it on re-runs."""

from __future__ import annotations

import collections
import copy
import datetime as dt
import json

from newsroom import ROOT, quiz, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.llm import Tally, TransientError
from newsroom.render import build
from tests.test_ai import KEY, FakeLLM, factory, offline  # noqa: F401  (offline is a fixture)
from tests.test_pipeline import NOW

FIXTURE = json.loads((ROOT / "tests/fixtures/editions/2026/11/03.json").read_text(encoding="utf-8"))
SAT = dt.date(2026, 11, 7)


def _cfg(**quiz_settings):
    cfg = copy.deepcopy(load_config())
    cfg["quiz"].update(quiz_settings)
    return cfg


def _today(edition_id="2026-11-07"):
    today = copy.deepcopy(FIXTURE)
    today["edition_id"] = edition_id
    today.pop("quiz")
    return today


def _llm(cfg=None):
    return FakeLLM(cfg or load_config(), "api", Tally(5.0), env={})


def test_quiz_runs_twice_a_week_on_days_without_a_column():
    cfg = load_config()
    assert not set(cfg["quiz"]["days"]) & set(cfg["opinion"]["days"])
    tue = SAT - dt.timedelta(days=4)
    assert quiz.is_due(cfg, SAT, None) and quiz.is_due(cfg, SAT, tue) and quiz.is_due(cfg, tue, None)
    assert not quiz.is_due(cfg, SAT - dt.timedelta(days=3), None)        # Wednesday: the column's day
    assert not quiz.is_due(cfg, SAT, SAT)                                # never twice a day
    assert not quiz.is_due(_cfg(enabled=False), SAT, None)


def test_window_covers_the_days_since_the_last_quiz():
    tue = SAT - dt.timedelta(days=4)
    assert quiz.window(SAT, tue, 7) == 4                                 # Wednesday to Saturday
    assert quiz.window(tue + dt.timedelta(days=7), SAT, 7) == 3          # Sunday to Tuesday
    assert quiz.window(SAT, None, 7) == 7 and quiz.window(SAT, SAT - dt.timedelta(days=30), 7) == 7
    assert quiz.window(SAT, SAT, 7) == 1                                 # a forced second quiz: today only


def test_quiz_is_written_checked_and_shuffled():
    cfg, llm = load_config(), _llm()
    out = quiz.write(cfg, llm, _today(), [FIXTURE], force=True)
    qz = out.quiz                                                        # the fixture's quiz ran on Tuesday the 3rd
    assert qz and qz["headline"] == "The Saturday quiz" and qz["period"] == {"start": "2026-11-04", "end": "2026-11-07"}
    assert {q["question"] for q in llm.checked_questions}.isdisjoint({"Unknown story?", "Twice the same option?"})
    assert len(qz["questions"]) == 8 and not qz["checked"]["dropped"]
    assert qz["dek"] == "Eight questions on AI, tech and gaming news from 4–7 November. How much do you remember?"
    for q in qz["questions"]:
        assert len(q["options"]) == 4 and q["options"][q["answer"]].startswith("Right")
        assert q["story"]["headline"] and q["section"] in ("ai", "tech", "gaming")
    spread = collections.Counter(q["answer"] for q in qz["questions"]).values()
    assert max(spread) - min(spread) <= 1                                # A–D used evenly
    again = quiz.write(cfg, _llm(), _today(), [FIXTURE], force=True).quiz
    assert [q["options"] for q in again["questions"]] == [q["options"] for q in qz["questions"]]


def test_questions_per_section_are_capped():
    qz = quiz.write(_cfg(max_per_section=2), _llm(), _today(), [FIXTURE], force=True).quiz   # 3 AI, 3 Tech, 2 Gaming
    assert collections.Counter(q["section"] for q in qz["questions"]) == {"ai": 2, "tech": 2, "gaming": 2}
    assert [d["problem"] for d in qz["checked"]["dropped"]] == ["more than 2 ai questions", "more than 2 tech questions"]


def test_the_check_drops_questions_and_can_stop_the_quiz():
    cfg = load_config()
    llm = _llm()
    llm.quiz_verdicts = {1: "drop", 2: "missing"}                        # flagged, and not checked at all
    qz = quiz.write(cfg, llm, _today(), [FIXTURE], force=True).quiz
    assert [d["problem"] for d in qz["checked"]["dropped"]][:2] == ["wrong answer", "not checked"]
    assert len(qz["questions"]) == 6

    llm = _llm()
    llm.quiz_verdicts = {n: "drop" for n in range(1, 5)}
    out = quiz.write(cfg, llm, _today(), [FIXTURE], force=True)
    assert out.quiz is None and "passed the check" in out.note

    llm = _llm()
    llm.fail = {"quiz_check": TransientError("overloaded")}
    out = quiz.write(cfg, llm, _today(), [FIXTURE], force=True)
    assert out.quiz is None and "overloaded" in out.note                  # no unchecked questions


def test_place_answers_keeps_every_option():
    drafts = [{"answer": f"R{i}", "wrong_answers": [f"a{i}", f"b{i}", f"c{i}"]} for i in range(6)]
    for d, (options, right) in zip(drafts, quiz.place_answers(drafts, "2026-11-07")):
        assert options[right] == d["answer"] and sorted(options) == sorted([d["answer"], *d["wrong_answers"]])


def test_auto_quiz_on_its_day_kept_on_rerun_and_rendered(tmp_path, offline):  # noqa: F811
    cfg, data = load_config(), tmp_path / "data"                         # NOW is a Tuesday: a quiz day
    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["quiz"]["questions"] and r.quiz.startswith("written")
    assert {"quiz", "quiz_check"} <= set(ed["llm"]["by_task"])          # the quiz's cost is tallied

    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    again = json.loads(store.edition_path(data, r.edition_id).read_text())["quiz"]
    assert again == ed["quiz"] and r.quiz.startswith("kept")
    assert "quiz" not in (r.llm or {}).get("by_task", {})               # not paid for twice

    site = tmp_path / "site"
    build(cfg, data, site)
    page = (site / "quiz" / r.edition_id / "index.html").read_text(encoding="utf-8")
    assert page.count('class="quiz-q ') == len(again["questions"]) == page.count("quiz-opt--right")
    assert "The Tuesday quiz" in (site / "index.html").read_text(encoding="utf-8")
    assert "The Tuesday quiz" in (site / "quiz" / "index.html").read_text(encoding="utf-8")


def test_no_quiz_when_off_not_due_or_reduced(tmp_path, offline):  # noqa: F811
    data = tmp_path / "off"
    r = gen.generate(load_config(), data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory(),
                     quiz_mode="off")
    assert "quiz" not in json.loads(store.edition_path(data, r.edition_id).read_text())

    data = tmp_path / "not-due"
    r = gen.generate(_cfg(days=["sat"]), data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert "quiz" not in json.loads(store.edition_path(data, r.edition_id).read_text())

    data = tmp_path / "reduced"
    data.mkdir()
    (data / "usage.json").write_text(json.dumps({"months": {"2026-11": {"usd": 5.0, "runs": []}}}))
    cfg = _cfg()
    cfg["budget"]["monthly_usd"] = 20                                   # $5 is ahead of pace on day 3
    r = gen.generate(cfg, data, "auto", now=NOW, env=KEY, client=offline, llm_factory=factory())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["mode"] == "reduced" and "quiz" not in ed
