"""403 Arcade: Friday schedule, genre rotation, sandboxed API tool loop, verifier checks, and rendering."""

from __future__ import annotations

import copy
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from newsroom import ROOT, arcade, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.llm import LLM, Tally, TransientError
from newsroom.render import build
from tests.test_ai import KEY, FakeLLM, factory, offline  # noqa: F401
from tests.test_render import LINK_RE

FIXTURE = json.loads((ROOT / "tests/fixtures/editions/2026/11/03.json").read_text(encoding="utf-8"))
FRI = dt.date(2026, 11, 6)
FRI_NOW = dt.datetime(2026, 11, 6, 6, 55, tzinfo=dt.timezone.utc)


def _today(edition_id: str = "2026-11-06"):
    ed = copy.deepcopy(FIXTURE)
    ed["edition_id"] = edition_id
    ed.pop("arcade", None)
    ed.pop("quiz", None)
    ed.pop("opinion", None)
    return ed


def _llm(cfg=None):
    return FakeLLM(cfg or load_config(), "api", Tally(5.0), env={})


def test_arcade_runs_on_fridays_only():
    cfg = load_config()
    assert cfg["arcade"]["days"] == ["fri"]
    last_fri = FRI - dt.timedelta(days=7)
    assert arcade.is_due(cfg, FRI, None) and arcade.is_due(cfg, FRI, last_fri)
    assert not arcade.is_due(cfg, FRI, FRI)
    assert not arcade.is_due(cfg, FRI - dt.timedelta(days=1), None)
    assert not arcade.is_due(cfg, FRI + dt.timedelta(days=1), None)
    off = copy.deepcopy(cfg)
    off["arcade"]["enabled"] = False
    assert not arcade.is_due(off, FRI, None)


def test_history_prefers_unseen_and_least_used_genres():
    ed1 = {**_today("2026-10-30"), "arcade": {
        "story_id": "2026-10-30/s1", "title": "Gate One", "genre": "lane-triage",
        "controls_layout": "lr", "code": "export default {}",
    }}
    ed2 = {**_today("2026-11-06"), "arcade": {
        "story_id": "2026-11-06/s2", "title": "Word One", "genre": "word-typing",
        "controls_layout": "typing", "code": "export default {}",
    }}
    hist = arcade.history([ed1, ed2])
    assert hist["min_count"] == 0
    assert "lane-triage" not in hist["preferred_genres"]
    assert "word-typing" not in hist["preferred_genres"]
    assert "tower-defense" in hist["preferred_genres"]
    assert set(hist["used_story_ids"]) == {"2026-10-30/s1", "2026-11-06/s2"}


def test_arcade_writes_and_verifies_game():
    cfg, llm = load_config(), _llm()
    out = arcade.write(cfg, llm, _today(), [], force=True)
    gm = out.game
    assert gm and gm["title"] == "CI Token Defender"
    assert gm["genre"] == "dodger-shooter" and gm["controls_layout"] == "lr+a"
    assert gm["story"]["slug"] and "mountArcade" not in gm["code"]
    assert gm["verify"]["lines"] > 50 and gm["verify"]["idle_outcome"] == "lose"


def test_arcade_skips_off_limits_stories_and_rejects_bad_code():
    ed = _today()
    ed["stories"][0]["headline"] = "Anthropic ships a new model"
    ed["stories"][1]["dek"] = "CEO resigns over personal affair and election talk."
    rows, _ = arcade._eligible_rows([ed], ed, set())
    headlines = {r["headline"] for r in rows}
    assert ed["stories"][0]["headline"] not in headlines
    assert ed["stories"][1]["headline"] not in headlines

    class BadCodeLLM(FakeLLM):
        def call_sandbox(self, task, system, user, work_dir, **kw):
            super().call_sandbox(task, system, user, work_dir, **kw)
            (work_dir / "game.js").write_text("export default { update() { fetch('/'); }, draw() {} };")
            return {"turns": 1, "text": "", "max_turns_reached": False}

    base = _llm()
    bad = BadCodeLLM(base.cfg, base.backend, base.tally, env={})
    out = arcade.write(load_config(), bad, _today(), [], force=True)
    assert out.game is None and "verification failed" in out.note


def test_api_sandbox_tool_loop_enforces_paths_and_caching(tmp_path):
    responses = [
        SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100, output_tokens=40, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=50),
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="tool_use", id="t1", name="read_file", input={"path": "../secret.txt"}),
                SimpleNamespace(type="tool_use", id="t2", name="write_file", input={"path": "verify.mjs", "content": "x"}),
                SimpleNamespace(type="tool_use", id="t3", name="write_file",
                                input={"path": "meta.json", "content": json.dumps({"play": False, "reason": "test"})}),
            ],
        ),
        SimpleNamespace(
            usage=SimpleNamespace(input_tokens=20, output_tokens=30, cache_read_input_tokens=150,
                                  cache_creation_input_tokens=0),
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", id="t4", name="run_verify", input={})],
        ),
        SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=15, cache_read_input_tokens=180,
                                  cache_creation_input_tokens=0),
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Done.")],
        ),
    ]
    seen_calls = []

    class FakeMessages:
        def create(self, **kw):
            seen_calls.append(kw)
            return responses[len(seen_calls) - 1]

    (tmp_path / "verify.mjs").write_text('console.log(JSON.stringify({ok: true}));', encoding="utf-8")
    llm = LLM(load_config(), "api", Tally(2.0), env={})
    llm._client = SimpleNamespace(messages=FakeMessages())
    res = llm.call_sandbox("arcade", "sys", "usr", tmp_path, max_turns=5)

    assert res["turns"] == 3 and res["text"] == "Done."
    assert (tmp_path / "verify.mjs").read_text(encoding="utf-8") == 'console.log(JSON.stringify({ok: true}));'
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["play"] is False
    assert seen_calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    tool_res = {r["tool_use_id"]: r for r in seen_calls[1]["messages"][-1]["content"]}
    assert tool_res["t1"]["is_error"] and "escapes workspace" in tool_res["t1"]["content"]
    assert tool_res["t2"]["is_error"]
    assert not tool_res["t3"].get("is_error")
    assert llm.tally.calls[0].requests == 3 and llm.tally.usd > 0


def test_friday_edition_and_backfill_command(tmp_path, offline):  # noqa: F811
    cfg, data = load_config(), tmp_path / "data"
    r = gen.generate(cfg, data, "full", now=FRI_NOW, env=KEY, client=offline, llm_factory=factory())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["arcade"]["title"] == "CI Token Defender" and r.arcade.startswith("written:")
    assert "arcade" in ed["llm"]["by_task"]

    r2 = gen.generate(cfg, data, "full", now=FRI_NOW, env=KEY, client=offline, llm_factory=factory())
    assert r2.arcade.startswith("kept today's game")
    assert "arcade" not in (r2.llm or {}).get("by_task", {})

    # Backfill command on a saved edition without arcade
    back = tmp_path / "backfill"
    ed_plain = _today("2026-11-13")
    store.save_edition(back, ed_plain)
    line = gen.run_arcade(cfg, back, "2026-11-13", backend="api", env=KEY, llm_factory=factory())
    assert "wrote 'CI Token Defender'" in line
    saved = store.load_edition(back, "2026-11-13")
    assert saved["arcade"]["code"] and saved["arcade"]["story"]["slug"]
    assert "already has" in gen.run_arcade(cfg, back, "2026-11-13", backend="api", env=KEY, llm_factory=factory())
    usage = json.loads((back / "usage.json").read_text(encoding="utf-8"))
    assert usage["months"]["2026-11"]["runs"][-1]["mode"] == "arcade"

    site = tmp_path / "site"
    build(cfg, data, site)
    page = (site / "arcade" / r.edition_id / "index.html").read_text(encoding="utf-8")
    assert "CI Token Defender" in page and "static/arcade/host.js" in page
    for html_file in site.rglob("*.html"):
        for link in LINK_RE.findall(html_file.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = site / link[len(cfg["site"]["base_path"]):].split("?")[0].split("#")[0]
            assert target.is_file() or (target / "index.html").is_file(), (html_file, link)


def test_arcade_off_or_reduced(tmp_path, offline):  # noqa: F811
    cfg = load_config()
    r = gen.generate(cfg, tmp_path / "off", "full", now=FRI_NOW, env=KEY, client=offline,
                     llm_factory=factory(), arcade_mode="off")
    assert "arcade" not in json.loads(store.edition_path(tmp_path / "off", r.edition_id).read_text())

    r_red = gen.generate(cfg, tmp_path / "red", "reduced", now=FRI_NOW, env=KEY, client=offline,
                         llm_factory=factory())
    assert "arcade" not in json.loads(store.edition_path(tmp_path / "red", r_red.edition_id).read_text())

    r_fail = gen.generate(cfg, tmp_path / "fail", "full", now=FRI_NOW, env=KEY, client=offline,
                          llm_factory=factory({"arcade": TransientError("overloaded")}))
    assert r_fail.published and "not written" in r_fail.arcade
