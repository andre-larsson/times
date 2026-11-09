"""The opinion column: schedule, rotation, writing it with a fake Claude, and keeping it on re-runs."""

from __future__ import annotations

import copy
import datetime as dt
import json

from newsroom import ROOT, opinion, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.llm import Tally, TransientError
from newsroom.render import build
from tests.test_ai import KEY, FakeLLM, factory, offline  # noqa: F401  (offline is a fixture)
from tests.test_pipeline import NOW

FIXTURE = json.loads((ROOT / "tests/fixtures/editions/2026/11/03.json").read_text(encoding="utf-8"))


def _cfg(**opinion_settings):
    cfg = copy.deepcopy(load_config())
    cfg["opinion"].update(opinion_settings)
    return cfg


def test_is_due_every_other_sunday():
    cfg = _cfg(days=["sun"], every_weeks=2)
    sun = dt.date(2026, 11, 8)
    assert opinion.is_due(cfg, sun, None)                               # the first column
    assert not opinion.is_due(cfg, sun - dt.timedelta(days=1), None)    # Saturday
    assert not opinion.is_due(cfg, sun, sun - dt.timedelta(days=7))     # the off week
    assert opinion.is_due(cfg, sun, sun - dt.timedelta(days=14))
    assert opinion.is_due(cfg, sun, sun - dt.timedelta(days=21))        # a missed Sunday catches up
    assert not opinion.is_due(cfg, sun, sun)                            # never twice a day
    assert opinion.is_due(_cfg(every_weeks=1), sun, sun - dt.timedelta(days=7))
    assert not opinion.is_due(_cfg(enabled=False), sun, None)


def test_rotation_avoids_recent_formats_and_focus():
    hist = [{"format": "advice", "focus": "tech"}, {"format": "argument", "focus": "ai"},
            {"format": "long_view", "focus": "gaming"}]
    formats, focus = opinion.rotation(hist)
    assert "advice" not in formats and "argument" not in formats and formats
    assert focus == ["ai", "gaming", "cross"]
    assert opinion.rotation([]) == (list(opinion.desk.COLUMN_FORMATS), list(opinion.desk.COLUMN_FOCUS))


def test_pick_schema_enforces_the_rotation():
    cfg = load_config()
    llm = FakeLLM(cfg, "api", Tally(5.0), env={})
    today = copy.deepcopy(FIXTURE)
    today["edition_id"] = "2026-11-17"
    today.pop("opinion")
    out = opinion.write(cfg, llm, today, [FIXTURE], force=True)          # the fixture's column: advice, tech
    enums = llm.schemas["opinion_pick"]["properties"]
    assert "advice" not in enums["format"]["enum"] and "tech" not in enums["focus"]["enum"]
    col = out.column
    assert col and col["format"] != "advice" and col["focus"] != "tech"
    assert len(col["reading"]) == 3                                     # the made-up id is dropped
    assert col["pull_quote"] == "Two is the point." and col["model"] == "claude-fable-5-2"


def test_forced_column_is_written_and_rendered(tmp_path, offline):  # noqa: F811
    cfg, data = load_config(), tmp_path / "data"
    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory(),
                     column="force")
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    col = ed["opinion"]
    assert col["headline"] == "Column: Cheaper parts" and r.column.startswith("written")
    assert {"opinion_pick", "opinion"} <= set(ed["llm"]["by_task"])     # the column's cost is tallied
    assert col["slug"] not in {s["slug"] for s in ed["stories"]}

    site = tmp_path / "site"
    build(cfg, data, site)
    assert (site / "2026" / "11" / "03" / col["slug"] / "index.html").is_file()
    assert col["headline"] in (site / "opinion" / "index.html").read_text(encoding="utf-8")
    assert col["headline"] in (site / "index.html").read_text(encoding="utf-8")


def test_auto_column_when_due_and_kept_on_rerun(tmp_path, offline):  # noqa: F811
    cfg, data = _cfg(days=["tue"]), tmp_path / "data"                  # NOW is a Tuesday
    gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    first = json.loads(store.edition_path(data, "2026-11-03").read_text())["opinion"]

    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    again = json.loads(store.edition_path(data, "2026-11-03").read_text())["opinion"]
    assert again["headline"] == first["headline"] and r.column.startswith("kept")
    assert "opinion" not in (r.llm or {}).get("by_task", {})            # not paid for twice


def test_no_column_when_not_due_or_reduced(tmp_path, offline):  # noqa: F811
    data = tmp_path / "data"
    r = gen.generate(load_config(), data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert "opinion" not in json.loads(store.edition_path(data, r.edition_id).read_text())

    data = tmp_path / "reduced"
    data.mkdir()
    (data / "usage.json").write_text(json.dumps({"months": {"2026-11": {"usd": 5.0, "runs": []}}}))
    cfg = _cfg(days=["tue"])
    cfg["budget"]["monthly_usd"] = 20                                   # $5 is ahead of pace on day 3
    r = gen.generate(cfg, data, "auto", now=NOW, env=KEY, client=offline, llm_factory=factory())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["mode"] == "reduced" and "opinion" not in ed


def _today():
    today = copy.deepcopy(FIXTURE)
    today["edition_id"] = "2026-11-17"
    today.pop("opinion")
    return today


def test_fact_check_fixes_are_applied():
    cfg = load_config()
    llm = FakeLLM(cfg, "api", Tally(5.0), env={})
    llm.check = {"verdict": "fixed", "fixes": [
        {"sentence": "Three.", "problem": "wrong", "replacement": "Three, corrected."},
        {"sentence": "Four.", "problem": "not in the stories", "replacement": ""},          # deleted
        {"sentence": "Column:   Cheaper parts", "problem": "x", "replacement": "Column: Cheap parts"},
    ]}
    col = opinion.write(cfg, llm, _today(), [FIXTURE], force=True).column
    assert col["body"] == "One.\n\nTwo is the point.\n\nThree, corrected."
    assert col["headline"] == "Column: Cheap parts" and col["slug"] == "column-cheap-parts"
    assert col["pull_quote"] == "Two is the point." and len(col["checked"]["fixes"]) == 3


def test_fact_check_can_stop_a_column():
    cfg = load_config()
    for check in ({"verdict": "reject", "fixes": [{"sentence": "One.", "problem": "core claim unsupported",
                                                   "replacement": ""}]},
                  {"verdict": "fixed", "fixes": [{"sentence": "Not in the column.", "problem": "x",
                                                  "replacement": "y"}]}):
        llm = FakeLLM(cfg, "api", Tally(5.0), env={})
        llm.check = check
        out = opinion.write(cfg, llm, _today(), [FIXTURE], force=True)
        assert out.column is None and out.note
    llm = FakeLLM(cfg, "api", Tally(5.0), env={})
    llm.fail = {"opinion_check": TransientError("overloaded")}
    out = opinion.write(cfg, llm, _today(), [FIXTURE], force=True)
    assert out.column is None and "overloaded" in out.note                # no unchecked columns


def test_apply_fixes_tolerates_whitespace_and_curly_quotes():
    draft = {"headline": "H", "dek": "D", "body": "He said \u201cno\u201d  to it.\n\nNext."}
    fixed, missing = opinion.apply_fixes(draft, [{"sentence": 'He said "no" to it.', "replacement": "He declined."}])
    assert not missing and fixed["body"] == "He declined.\n\nNext."
