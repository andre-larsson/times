"""Phase 3 tests: AI editions with a fake Claude (no network, no cost)."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from types import SimpleNamespace

import pytest

from newsroom import ai_edition, budget, store
from newsroom import generate as gen
from newsroom.config import load_config
from newsroom.llm import LLM, Call, CreditError, Tally, TransientError
from newsroom.render import build
from tests.test_pipeline import NOW, FakeClient, _harvest


def _data(user: str):
    return json.loads(user.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])


class FakeLLM(LLM):
    """Answers every task with plausible canned JSON; `fail` maps task → exception to raise."""
    fail: dict[str, Exception] = {}

    def call(self, task, system, user, schema, max_tokens=None):
        self.tally.check()
        self.schemas = {**getattr(self, "schemas", {}), task: schema}
        call = Call(task=task, model=self.model_for(task), backend=self.backend, input_tokens=1000,
                    output_tokens=200, usd=0.01 if self.backend == "api" else 0.0, equivalent_usd=0.01)
        if task in self.fail:
            exc = self.fail[task]
            call.ok, call.error = False, str(exc)
            self.tally.record(call, exc)
            raise exc
        self.tally.record(call)
        return getattr(self, f"_{task}")(_data(user) if "<data>" in user else None)

    def _probe(self, _):
        return {"ok": True}

    def _triage(self, rows):
        return {"items": [{"id": r["id"], "keep": True, "section": r["rule_section"], "kicker": "Dev",
                           "newsworthiness": max(2.5, 5 - i * 0.5), "event": r["id"], "title_en": r["title"]}
                          for i, r in enumerate(rows)]}

    def _editor(self, data):
        ev = [e for e in data["events"] if e["section"] in ("ai", "tech")]
        pick = lambda e: {"event": e["event"], "source_ids": [e["candidates"][0]["id"]], "angle": "What happened."}
        return {"lead": ev[0]["event"], "featured": [{**pick(ev[0]), "breaking": True}],
                "medium": [pick(e) for e in ev[1:3]],
                "briefs": [{"event": e["event"], "source_id": e["candidates"][0]["id"]} for e in ev[3:8]]}

    def _featured(self, data):
        t = data["sources"][0]["title"]
        return {"headline": f"Lead: {t}", "dek": "A dek.", "kicker": "Dev", "body": "One.\n\nTwo.",
                "key_points": ["a", "b", "c"], "why_it_matters": "Because.", "cover_figure": "40%",
                "cover_caption": "of something"}

    def _medium(self, data):
        return {"headline": f"Medium: {data['sources'][0]['title']}", "dek": "Dek.", "kicker": "Tech",
                "body": "Body.", "key_points": ["x"]}

    def _briefs(self, rows):
        return {"items": [{"id": r["id"], "headline": f"Brief: {r['title']}", "body": "Short.", "kicker": "AI"}
                          for r in rows]}

    def _gaming(self, m):
        return {"new_on_pc": [{"appid": g["appid"], "blurb": f"AI blurb for {g['title']}"} for g in m["new_on_pc"]],
                "reviews": [{"id": r["id"], "verdict": "AI verdict"} for r in m["reviews"]],
                "watch": [{"url": v["url"], "blurb": "AI teaser"} for v in m["watch"]],
                "news": [{"id": n["id"], "headline": f"AI: {n['title']}", "summary": "S."}
                         for n in m["news_candidates"][:2]],
                "console_spotlight": []}

    def _deals(self, m):
        first, *rest = m["deals"]
        return {"featured": [{"id": first["id"], "headline": f"{first['game']}: Strong Buy", "body": "Good.",
                              "verdict": "strong_buy"}],
                "more": [{"id": d["id"], "advice": "Fine.", "verdict": "hold"} for d in rest]}


    def _opinion_pick(self, m):
        return {"topic": "Cheaper parts", "focus": m["allowed_focus"][0], "format": m["allowed_formats"][0],
                "thesis": "Buy now.", "story_ids": [r["id"] for r in m["stories"][:3]] + ["made-up-id"]}

    def _opinion(self, a):
        assert a["stories"] and all("headline" in s for s in a["stories"])
        return {"headline": f"Column: {a['topic']}", "dek": "Buy now.",
                "body": "One.\n\nTwo is the point.\n\nThree.\n\nFour.", "pull_quote": "Two is the point."}


    check = {"verdict": "ok", "fixes": []}             # the copy desk's answer; tests may replace it

    def _opinion_check(self, m):
        assert m["column"]["body"] and m["stories"]
        return self.check


def factory(fail=None):
    def make(cfg, backend, tally, env):
        llm = FakeLLM(cfg, backend, tally, env)
        llm.fail = fail or {}
        return llm
    return make


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(gen, "fetch_all", lambda cfg, client, now, itad_key=None: _harvest())
    monkeypatch.setattr(ai_edition, "fetch_texts", lambda client, urls, limit=12000: {})
    return FakeClient({})


KEY = {"ANTHROPIC_API_KEY": "test"}


def test_full_edition(tmp_path, offline):
    cfg, data = load_config(), tmp_path / "data"
    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert r.published and r.mode == "full", r.reason
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    tiers = [s["tier"] for s in ed["stories"]]
    assert tiers[0] == "featured" and "medium" in tiers and "brief" in tiers
    lead = ed["stories"][0]
    assert lead["lead"] and lead["breaking"] and lead["cover"]["figure"] == "40%"
    assert lead["headline"].startswith("Lead:") and lead["sources"][0]["url"]
    assert all(s["slug"] for s in ed["stories"]) and len({s["slug"] for s in ed["stories"]}) == len(tiers)
    assert ed["gaming"]["new_on_pc"][0]["blurb"].startswith("AI blurb")
    assert ed["gaming"]["reviews"][0]["verdict"] == "AI verdict"
    assert ed["deals"]["featured"][0]["verdict"] == "strong_buy"
    assert ed["llm"]["backend"] == "api" and ed["llm"]["calls"] >= 6

    usage = budget.load_usage(data)
    assert usage["months"]["2026-11"]["usd"] > 0                   # API spend is tallied
    assert (data / "seen.json").exists()

    pages = build(cfg, data, tmp_path / "site")
    assert pages > 8 and (tmp_path / "site" / "2026" / "11" / "03" / lead["slug"] / "index.html").exists()


def test_writer_failure_gives_partial(tmp_path, offline):
    r = gen.generate(load_config(), tmp_path / "data", "full", now=NOW, env=KEY, client=offline,
                     llm_factory=factory({"medium": TransientError("overloaded")}))
    ed = json.loads(store.edition_path(tmp_path / "data", r.edition_id).read_text())
    assert r.published and ed["mode"] == "partial"
    assert not any(s["tier"] == "medium" for s in ed["stories"])          # degraded to plain briefs
    assert any(s["tier"] == "brief" and not s["headline"].startswith("Brief:") for s in ed["stories"])


def test_credit_error_stops_ai_work(tmp_path, offline):
    r = gen.generate(load_config(), tmp_path / "data", "full", now=NOW, env=KEY, client=offline,
                     llm_factory=factory({"editor": CreditError("credit balance too low")}))
    assert r.published and r.mode == "links" and "editor failed" in r.reason


def test_triage_failure_falls_back_to_links(tmp_path, offline):
    r = gen.generate(load_config(), tmp_path / "data", "auto", now=NOW, env=KEY, client=offline,
                     llm_factory=factory({"triage": TransientError("bad JSON")}))
    assert r.published and r.mode == "links" and r.reason.startswith("AI unavailable")


def test_probe_failure_and_no_key(tmp_path, offline):
    r = gen.generate(load_config(), tmp_path / "data", "auto", now=NOW, env=KEY, client=offline,
                     llm_factory=factory({"probe": CreditError("credit balance too low")}))
    assert r.mode == "links" and "pre-run check failed" in r.reason
    r = gen.generate(load_config(), tmp_path / "d2", "auto", now=NOW, env={}, client=offline,
                     llm_factory=factory())
    assert r.mode == "links" and r.reason == "no ANTHROPIC_API_KEY"


def test_budget_pacing(tmp_path, offline):
    cfg = load_config()
    data = tmp_path / "data"
    data.mkdir()
    (data / "usage.json").write_text(json.dumps({"months": {"2026-11": {"usd": 5.0, "runs": []}}}))
    r = gen.generate(cfg, data, "auto", now=NOW, env=KEY, client=offline, llm_factory=factory())
    ed = json.loads(store.edition_path(data, r.edition_id).read_text())
    assert ed["mode"] == "reduced"                                       # day 3: pace ≈ $4
    assert sum(s["tier"] == "featured" for s in ed["stories"]) <= 1
    assert sum(s["tier"] == "medium" for s in ed["stories"]) <= 3

    (data / "usage.json").write_text(json.dumps({"months": {"2026-11": {"usd": 20.5, "runs": []}}}))
    r = gen.generate(cfg, data, "full", now=NOW, env=KEY, client=offline, llm_factory=factory())
    assert r.mode == "links" and "monthly budget used" in r.reason


def test_per_run_cap():
    tally = Tally(per_run_usd=0.02)
    tally.record(Call("featured", "m", "api", usd=0.03, equivalent_usd=0.03))
    with pytest.raises(Exception, match="per-run budget"):
        tally.check()
    assert tally.stopped


def test_claude_code_backend(monkeypatch):
    cfg = load_config()
    with pytest.raises(ValueError, match="local development"):
        LLM(cfg, "claude-code", Tally(1.0), env={"GITHUB_ACTIONS": "true"})

    seen_env = {}
    events = [{"type": "system", "subtype": "init", "apiKeySource": "none"},
              {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0123,
               "usage": {"input_tokens": 10, "output_tokens": 20}, "structured_output": {"ok": True}}]

    seen_cmd = []

    def fake_run(cmd, input, capture_output, text, cwd, env, timeout):
        seen_env.update(env)
        seen_cmd[:] = cmd
        assert "--json-schema" in cmd and "--tools" in cmd and input == "hello"
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(events), stderr="")

    monkeypatch.setattr("newsroom.llm.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr("newsroom.llm.subprocess.run", fake_run)
    tally = Tally(1.0)
    llm = LLM(cfg, "claude-code", tally, env={"ANTHROPIC_API_KEY": "secret", "PATH": "/usr/bin"})
    assert llm.call("triage", "sys", "hello", {"type": "object"}) == {"ok": True}
    assert "ANTHROPIC_API_KEY" not in seen_env                          # subscription, never the key
    assert tally.usd == 0 and tally.equivalent_usd == 0.0123

    llm.call("opinion", "sys", "hello", {"type": "object"})               # effort from llm.effort
    assert "--effort" in seen_cmd and seen_cmd[seen_cmd.index("--effort") + 1] == "high"
    llm.call("triage", "sys", "hello", {"type": "object"})
    assert "--effort" not in seen_cmd                                      # unset: the model's default

    events[0]["apiKeySource"] = "ANTHROPIC_API_KEY"
    with pytest.raises(CreditError):
        llm.call("triage", "sys", "hello", {"type": "object"})


def test_subscription_runs_dont_count(tmp_path):
    tally = Tally(1.0)
    tally.record(Call("featured", "m", "claude-code", usd=0.0, equivalent_usd=0.4))
    budget.record_run(tmp_path, NOW, "2026-11-03", "full", "claude-code", tally)
    usage = budget.load_usage(tmp_path)
    assert usage["months"]["2026-11"]["usd"] == 0
    assert usage["months"]["2026-11"]["runs"][0]["equivalent_usd"] == 0.4
    assert budget.pace_decision(load_config(), usage, NOW)[0] == "full"


def test_steam_deals_have_unknown_price_history():
    base = {"source": "steam", "checked_at": "x", "more": [
        {"game": "G", "shop": "Steam", "price": 1.0, "regular": 10.0, "cut": 90, "lowest_ever": False}]}
    material, _ = ai_edition._deals_material(base)
    assert material["deals"][0]["lowest_ever"] is None          # unknown, not "has been cheaper"
    material, _ = ai_edition._deals_material({**base, "source": "itad"})
    assert material["deals"][0]["lowest_ever"] is False and "pick" not in material["deals"][0]
    base["more"][0].update(pick="hidden", tags=["Roguelike"])
    material, _ = ai_edition._deals_material({**base, "source": "itad"})
    assert material["deals"][0]["pick"] == "hidden_gem" and material["deals"][0]["tags"] == ["Roguelike"]


def test_api_backend_sends_effort_per_task():
    sent = {}

    class FakeMessages:
        def create(self, **kw):
            sent.update(kw)
            usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                    cache_creation_input_tokens=0)
            return SimpleNamespace(usage=usage, stop_reason="end_turn",
                                   content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text='{"ok": true}')])

    llm = LLM(load_config(), "api", Tally(1.0), env={})
    llm._client = SimpleNamespace(messages=FakeMessages())
    assert llm.call("opinion_check", "sys", "hi", {"type": "object"}) == {"ok": True}
    assert sent["output_config"]["effort"] == "high" and sent["max_tokens"] == 8000
    assert sent["model"] == "claude-opus-5-5" and "thinking" not in sent        # adaptive thinking is the default
    llm.call("triage", "sys", "hi", {"type": "object"})
    assert "effort" not in sent["output_config"]


def test_editor_short_on_briefs_is_topped_up(tmp_path, offline):
    """2026-11-06: the editor returned no briefs at all; the paper still gets its briefs column."""
    class NoBriefs(FakeLLM):
        def _editor(self, data):
            return {**super()._editor(data), "briefs": []}

    r = gen.generate(load_config(), tmp_path / "data", "full", now=NOW, env=KEY, client=offline,
                     llm_factory=lambda cfg, backend, tally, env: NoBriefs(cfg, backend, tally, env))
    ed = json.loads(store.edition_path(tmp_path / "data", r.edition_id).read_text())
    st = ed["editor"]
    assert st["returned"]["briefs"] == 0 and st["kept"]["briefs"] == st["briefs_added"] > 0
    assert sum(s["tier"] == "brief" for s in ed["stories"]) == st["kept"]["briefs"]
    assert ed["mode"] == "full" and "editor returned 0 briefs" in ed["reason"]


def test_brief_top_up_skips_used_gaming_and_repeated_events():
    def ev(key, section, title):
        return {"event": key, "ids": [key], "section": section, "newsworthiness": 3.0,
                "prompt": {"candidates": [{"title": title}]}}
    sent = [ev("a", "ai", "Kestrel ships a smaller open model for laptops"),
            ev("b", "gaming", "A big game gets a release date"),
            ev("c", "tech", "Chipmaker Example Corp recalls overheating graphics cards"),
            ev("d", "tech", "Example browser adds tab groups on phones"),
            ev("e", "ai", "Another lab publishes an agent benchmark")]
    recent = [{"edition_id": "2026-11-02", "headlines": ["Example Corp recalls overheating graphics cards"]}]
    limits = {"briefs": {"min": 3}}
    assignments = {"featured": [{"event": "a"}], "medium": [], "briefs": []}
    rows = ai_edition._brief_top_up(assignments, sent, {}, recent, limits)
    assert [r["event"] for r in rows] == ["d", "e"]                       # a used, b gaming, c a repeat
    assert ai_edition._brief_top_up({**assignments, "briefs": [{"event": x} for x in "xyz"]},
                                    sent, {}, recent, limits) == []       # enough briefs: nothing added


@pytest.mark.parametrize("figure, ok", [
    ("40%", True), ("+18%", True), ("$6.34B", True), ("2 pts", True), ("1.2 million", True), ("~70B", True),
    ("−3%", True), ("€1,000", True), (" 29M ", True),
    ("All", False), ("Zero", False), ("GPT-5", False), ("", False), ("Q3", False),
])
def test_cover_figure_must_be_a_number(figure, ok):
    assert ai_edition.is_cover_figure(figure) is ok
