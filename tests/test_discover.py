"""Discovery: the web-search call loop, cost accounting, the checks on finds, and the measuring command.

No network: the Anthropic client is a fake that replays canned responses.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from newsroom import discover
from newsroom.config import load_config
from newsroom.llm import LLM, LLMError, Tally, price
from tests.test_pipeline import NOW, FakeClient, _harvest

KEY = {"ANTHROPIC_API_KEY": "test"}
GOOD = {"title": "Example Labs opens its new chip design kit", "url": "https://example.com/news/kit",
        "source": "Example Labs", "published": "2026-11-02", "section": "tech",
        "summary": "Example Labs released a design kit.", "why": "Hardware news the feeds missed."}


def usage(inp, out, searches=0, fetches=0):
    return NS(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0, cache_creation_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches, web_fetch_requests=fetches))


def search(query, *urls):
    return [NS(type="server_tool_use", name="web_search", input={"query": query}),
            NS(type="web_search_tool_result", content=[NS(url=u, title="t", page_age="") for u in urls])]


def fetch(url, text=""):
    doc = NS(title="t", source=NS(type="text", data=text))
    return [NS(type="server_tool_use", name="web_fetch", input={"url": url}),
            NS(type="web_fetch_tool_result", content=NS(type="web_fetch_result", url=url, content=doc))]


def report(*finds):
    return NS(type="tool_use", name="report", input={"finds": list(finds)})


class FakeAnthropic:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=lambda o: o.__dict__)))
        return self.responses.pop(0)


def web_llm(responses, cfg=None):
    llm = LLM(cfg or load_config(), "api", Tally(per_run_usd=5), env=KEY)
    llm._client = FakeAnthropic(responses)
    return llm


def test_pause_turn_report_and_cost():
    cfg = load_config()
    llm = web_llm([
        NS(stop_reason="pause_turn", usage=usage(4000, 300, searches=2),
           content=search("new chip kit", "https://example.com/news/kit", "https://example.org/old")
           + search("indie game", "https://example.net/game")),
        NS(stop_reason="tool_use", usage=usage(9000, 500, fetches=1),
           content=fetch("https://example.com/news/kit", "More: https://example.com/next. (https://example.org/x)")
           + [report(GOOD)]),
    ], cfg)
    data, looked, call = llm.call_web("discover", "system", "user", discover.REPORT_SCHEMA, searches=3, fetches=3)
    assert data["finds"] == [GOOD]
    assert looked["queries"] == ["new chip kit", "indie game"] and looked["fetched"] == ["https://example.com/news/kit"]
    assert len(looked["results"]) == 4
    assert looked["linked"] == ["https://example.com/next.", "https://example.org/x"]
    assert (call.requests, call.web_searches, call.web_fetches) == (2, 2, 1)
    assert call.usd == pytest.approx(price(cfg, call.model, 13000, 800) + 0.02)
    sent = llm._client.requests
    assert [t.get("max_uses") for t in sent[0]["tools"]] == [3, 3, None]
    assert sent[0]["tools"][2]["name"] == "report" and sent[0]["tools"][2]["strict"] is True
    assert [m["role"] for m in sent[1]["messages"]] == ["user", "assistant"]   # the paused turn sent back
    assert llm.tally.calls == [call]


def test_reminder_when_it_forgets_to_report():
    llm = web_llm([
        NS(stop_reason="end_turn", usage=usage(3000, 200, searches=1),
           content=search("q", "https://example.com/news/kit") + [NS(type="text", text="Here are my finds…")]),
        NS(stop_reason="tool_use", usage=usage(3500, 100), content=[report()]),
    ])
    data, _, call = llm.call_web("discover", "s", "u", discover.REPORT_SCHEMA, searches=3, fetches=0)
    assert data == {"finds": []} and call.requests == 2
    sent = llm._client.requests
    assert [t["name"] for t in sent[0]["tools"]] == ["web_search", "report"]        # no fetch tool at 0 fetches
    assert sent[1]["messages"][-1]["role"] == "user" and "report tool" in sent[1]["messages"][-1]["content"]


def test_gives_up_after_a_second_miss_and_needs_the_api():
    llm = web_llm([NS(stop_reason="end_turn", usage=usage(10, 1), content=[]),
                   NS(stop_reason="end_turn", usage=usage(10, 1), content=[])])
    with pytest.raises(LLMError, match="reminder"):
        llm.call_web("discover", "s", "u", discover.REPORT_SCHEMA, searches=1, fetches=0)
    assert not llm.tally.calls[-1].ok
    cc = LLM(load_config(), "claude-code", Tally(per_run_usd=5), env={})
    with pytest.raises(LLMError, match="api backend"):
        cc.call_web("discover", "s", "u", discover.REPORT_SCHEMA, searches=1, fetches=0)


def test_filtering_uses_the_newer_tools_and_keeps_the_container():
    llm = web_llm([
        NS(stop_reason="pause_turn", usage=usage(2000, 100, searches=1), container=NS(id="cntr_1"),
           content=[NS(type="server_tool_use", name="code_execution", input={"code": "print(1)"})]
           + search("q", "https://example.com/news/kit")),
        NS(stop_reason="tool_use", usage=usage(2500, 100), container=NS(id="cntr_1"), content=[report(GOOD)]),
    ])
    data, looked, call = llm.call_web("discover", "s", "u", discover.REPORT_SCHEMA, searches=3, fetches=2,
                                      filtering=True)
    sent = llm._client.requests
    assert [t.get("type") for t in sent[0]["tools"]] == ["web_search_20260318", "web_fetch_20260318", None]
    assert "container" not in sent[0] and sent[1]["container"] == "cntr_1"
    assert data["finds"] == [GOOD] and looked["queries"] == ["q"] and call.web_searches == 1


def test_check_keeps_only_real_new_finds():
    looked = {"results": [{"url": u} for u in ("https://example.com/news/kit", "https://www.example.org/a/",
                                                "https://example.net/b")]}
    known = [{"source": "Feed", "title": "Kestrel 2 model released with open weights today"}]
    finds = [
        GOOD,
        dict(GOOD, title="Made-up story", url="https://example.com/never-returned"),
        dict(GOOD, title="Something else", url="https://example.org/a?utm_source=x"),   # known page
        dict(GOOD, title="Kestrel 2 model released with open weights", url="https://example.net/b"),
        dict(GOOD, title="Same page again", url="https://example.com/news/kit/"),
        dict(GOOD, title="Not a link", url="javascript:alert(1)", section="cooking"),
    ]
    kept, dropped = discover.check(finds, looked, known, {"https://example.org/a"}, limit=4)
    assert [f["title"] for f in kept] == [GOOD["title"]]
    assert [d["reason"] for d in dropped] == [
        "no search, fetched page or link on one has this address", "the feeds already have this page",
        "the feeds already have this story", "listed twice", "not a web address"]
    assert dropped[-1]["section"] == "tech"                                         # bad enum value replaced
    linked = discover.check([dict(GOOD, url="https://example.com/blog/post")], {"results": [],
                            "linked": ["https://example.com/blog/post."]}, [], set(), limit=4)
    assert len(linked[0]) == 1                                                      # a link on a fetched page
    kept, dropped = discover.check([GOOD, dict(GOOD, title="Another", url="https://example.net/b")],
                                   looked, [], set(), limit=1)
    assert len(kept) == 1 and dropped[0]["reason"] == "over the limit of 1"


def test_for_edition_skips():
    cfg, h = load_config(), _harvest()
    api = NS(backend="api")
    assert discover.for_edition(cfg, h, "2026-11-03", "reduced", api, {}, [], NOW) == ([], {})
    cfg["search"]["depth"] = "off"
    assert discover.for_edition(cfg, h, "2026-11-03", "full", api, {}, [], NOW) == ([], {})
    cfg["search"].update(depth="normal", discovery_every_days=2)
    odd = "2026-11-03" if __import__("datetime").date(2026, 11, 3).toordinal() % 2 else "2026-11-04"
    assert discover.for_edition(cfg, h, odd, "full", api, {}, [], NOW)[1] == {"skipped": "runs every 2 days"}
    cfg["search"]["discovery_every_days"] = 1
    cc = NS(backend="claude-code")
    assert discover.for_edition(cfg, h, "2026-11-03", "full", cc, {}, [], NOW)[1] == {"skipped": "needs the api backend"}


def test_to_item():
    it = discover.to_item(dict(GOOD, source=""))
    assert it.source == "example.com" and it.sections == ["tech"] and it.extra["discovered"]
    assert it.published_at.isoformat() == "2026-11-02T12:00:00+00:00"
    assert discover.to_item(dict(GOOD, published="")).published_at is None


def test_depth_settings_from_config():
    cfg = load_config()
    assert discover.depth_settings(cfg, "light") == {"searches": 3, "fetches": 3, "finds": 4}
    cfg["search"]["depths"]["light"] = {"searches": 2}
    assert discover.depth_settings(cfg, "light") == {"searches": 2, "fetches": 3, "finds": 4}
    with pytest.raises(ValueError):
        discover.depth_settings(cfg, "bottomless")
    prompt = discover.system_prompt(cfg, discover.depth_settings(cfg, "deep"), NOW.date())
    assert "2026-11-03" in prompt and "at most 12 searches and 10 page fetches" in prompt and "{" not in prompt


def test_measure_writes_records_and_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(discover, "fetch_all", lambda cfg, client, now, itad_key=None: _harvest())
    find = dict(GOOD, url="https://example.com/discovered")
    script = {
        "light": [NS(stop_reason="tool_use", usage=usage(5000, 400, searches=3),
                     content=search("q", find["url"]) + [report(find)])],
        "deep": [NS(stop_reason="end_turn", usage=usage(10, 1), content=[]),
                 NS(stop_reason="end_turn", usage=usage(10, 1), content=[])],       # fails: no report
    }
    order = iter(["light", "deep"])

    def factory(cfg, backend, tally, env):
        assert backend == "api"
        llm = LLM(cfg, backend, tally, env=KEY)
        llm._client = FakeAnthropic(script[next(order)])
        return llm

    out = tmp_path / "disc"
    cfg = load_config()
    configured = cfg["search"]["dynamic_filtering"]
    text = discover.measure(cfg, tmp_path / "data", ["light", "deep"], 1, out, now=NOW,
                            client=FakeClient({}), llm_factory=factory, filtering=False)
    assert cfg["search"]["dynamic_filtering"] == configured                         # overrides don't leak
    assert "Kept 1 of 1" in text and find["title"] in text and "Failed: no report" in text
    assert "| light · opus-5-5 | 1 | $" in text and "| deep · opus-5-5 | 0 (1 failed) |" in text
    recs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
    assert [r["depth"] for r in recs] == ["light", "deep"] and recs[0]["searches"] == 3 and not recs[1]["ok"]
    assert capsys.readouterr().err.count("discovery-record: ") == 2

    dry = discover.measure(load_config(), tmp_path / "data", ["normal"], 1, out, dry_run=True, now=NOW,
                           client=FakeClient({}))
    assert "no Claude call" in dry and "at most 6 searches" in dry

    script["light"] = [NS(stop_reason="tool_use", usage=usage(100, 10), content=[report()])]
    order = iter(["light"])
    text = discover.measure(cfg, tmp_path / "data", ["light"], 1, None, now=NOW, client=FakeClient({}),
                            llm_factory=factory, model="claude-sonnet-5-5", filtering=True)
    assert "| light · sonnet-5-5 · filtered | 1 |" in text
    assert cfg["models"]["discover"] == "claude-opus-5-5"                          # the override didn't leak
