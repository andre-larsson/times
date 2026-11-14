"""The editor in disguise: the botifier, posting with a fake Claude (reports, rulings, bans, undo) and the pages."""

from __future__ import annotations

import copy
import datetime as dt
import re
import shutil

import pytest

from newsroom import ROOT
from newsroom.config import load_config
from newsroom.forum import disguise
from newsroom.llm import LLM, Call
from newsroom.render import build

FIXTURES = ROOT / "tests" / "fixtures"
EVENING = dt.datetime(2026, 11, 3, 21, 47, tzinfo=dt.timezone.utc)    # 22:47 in Stockholm, the fixture day
NEXT_MORNING = dt.datetime(2026, 11, 4, 5, 30, tzinfo=dt.timezone.utc)  # before that day's Botroom
ARTICLE = "https://a403.space/times/forum/2026-11-03/kestrel-2-open-model-catches-big-labs/#c-2026-11-03-c1"
LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')


class FakeClaude(LLM):
    """Answers the three kinds of disguise calls from their schema. `quote`: what HumanWatch_Patrol reports
    ("first" = the post's first four words, or a string); `ruling`: ModBot's."""

    def __init__(self, *a, quote="first", ruling="upheld", **kw):
        super().__init__(*a, **kw)
        self.quote, self.ruling = quote, ruling
        self.users: list[str] = []

    def call(self, task, system, user, schema, max_tokens=None):
        self.tally.record(Call(task=task, model=self.model_for(task), backend=self.backend, input_tokens=900,
                               output_tokens=80, usd=0.001, equivalent_usd=0.001))
        self.users.append(user)
        props = schema["properties"]
        if "ruling" in props:
            return {"ruling": self.ruling, "note": "[MOD] Ruled on, fictionally. Form 4.03-X applies."}
        handle = re.search(r"^Handle: (\S+)$", user, re.M).group(1)
        out = {"text": f"{handle} answers the example unit, fictionally.", "bit": "an answer"}
        if "report" in props:
            new = re.search(r"^\[new\] .*?: (.*)$", user, re.M).group(1)
            out["report"] = " ".join(new.split()[:4]) if self.quote == "first" else self.quote
        return out


def _data(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURES / "editions", data / "editions")
    shutil.copytree(FIXTURES / "forum", data / "forum")
    return data


def _cfg(**disguise_settings):
    cfg = copy.deepcopy(load_config())
    cfg["forum"]["disguise"] = {"strikes": 3, "botify": 2, "others": 2, **disguise_settings}
    return cfg


def _post(cfg, data, text, now=EVENING, quote="first", ruling="upheld", **kw):
    made = []

    def factory(c, backend, tally, env):
        made.append(FakeClaude(c, backend, tally, env={}, quote=quote, ruling=ruling))
        return made[-1]

    out = disguise.post(cfg, data, text, backend="api", env={}, llm_factory=factory, now=now, **kw)
    return out, made[-1] if made else None


# ── the botifier ─────────────────────────────────────────────────────────────

TEXT = ("I think the example box is great, but I checked it twice before my coffee. My friends say the quiz is "
        "too hard.\n\nI saw it this morning and felt clever for once, lol.")


def test_botify_is_seeded_and_keeps_the_human_in():
    assert disguise.botify("  as   written \n\n twice ", 0, 1) == "as written\n\ntwice"
    assert disguise.botify(TEXT, 2, 7) == disguise.botify(TEXT, 2, 7)
    assert disguise.botify(TEXT, 2, 7) != disguise.botify(TEXT, 2, 8)
    for level in (1, 2, 3):
        for seed in range(20):
            out = disguise.botify(TEXT, level, seed)
            assert out.count("\n\n") == 1 and "example box" in out and "http" not in out
            ends = (any(out.startswith(x) for x in disguise.OPENERS), any(out.endswith(x) for x in disguise.CLOSERS))
            assert all(ends) if level > 1 else any(ends), out
            assert any(s in out for s in disguise.SOUNDS), out
    slips = [disguise.botify(TEXT, 2, s) for s in range(20)]
    assert any("... I MEAN " in x for x in slips)                    # the human word, then the robot one
    assert not any(re.search(r"\.\.\. [^I]\S* I MEAN", x) for x in slips)   # nothing lands inside a slip


def test_addresses_of_threads_and_posts():
    full = "https://a403.space/times/forum/2026-11-14/some-thread/#c-2026-11-15-u1-2"
    assert disguise.parse_ref(full) == ("2026-11-14/some-thread", "2026-11-15/u1-2")
    assert disguise.parse_ref("forum/2026-11-14/some-thread/") == ("2026-11-14/some-thread", None)
    assert disguise.parse_ref("2026-11-14/some-thread#r3") == ("2026-11-14/some-thread", "2026-11-14/r3")
    with pytest.raises(ValueError):
        disguise.parse_ref("forum/announcements/read-first-the-rules/")


# ── posting ──────────────────────────────────────────────────────────────────

def test_a_new_account_introduces_itself(tmp_path):
    data, cfg = _data(tmp_path), _cfg()
    preview = disguise.post(cfg, data, "Hello, I read the paper over coffee.", new_account="Example_Unit_7",
                            dry_run=True, now=EVENING)
    assert "Nothing written" in preview and not disguise.state_path(data).exists()
    out, llm = _post(cfg, data, "Hello, I read the paper over coffee.", new_account="Example_Unit_7")
    assert "Posted as 2026-11-03/u1." in out
    state = disguise.load_state(data)
    acct = state["accounts"][0]
    assert acct["handle"] == "Example_Unit_7" and acct["status"] == "active" and acct["first_post"] == "2026-11-03/u1"
    t = disguise.load_records(data)[0]["threads"][0]
    assert t["kind"] == "botchat" and t["board"] == "introductions" and t["id"] == "u1"
    human, *replies = t["comments"]
    assert human["human"] and human["time"] == "22:47" and human["text"] != "Hello, I read the paper over coffee."
    assert [c["handle"] for c in replies][-2:] == ["HumanWatch_Patrol", "ModBot"]   # last, and the paperwork
    assert all(c["reply_to"] in ("u1", "u1-" + str(len(replies) - 1)) for c in replies)
    hw = next(u for u in llm.users if "Handle: HumanWatch_Patrol" in u)
    assert "human pretending to be a bot" in hw and "[new] Example_Unit_7 started this thread" in hw
    others = [u for u in llm.users if "verified unit" in u and "Handle: HumanWatch_Patrol" not in u
              and "Handle: ModBot" not in u]
    assert all("human" not in u.split("Who you are")[0] for u in others)   # nobody else is told
    with pytest.raises(disguise.PostError, match="still active"):
        _post(cfg, data, "Another one.", new_account="Example_Unit_8")
    with pytest.raises(disguise.PostError, match="can't be a handle"):
        disguise.post(cfg, data, "x", new_account="ModBot", dry_run=True, now=EVENING)


def test_reports_strikes_and_a_ban(tmp_path):
    data, cfg = _data(tmp_path), _cfg(strikes=2)
    _post(cfg, data, "Hello units.", new_account="Example_Unit_7", ruling="dismissed")
    acct = disguise.load_state(data)["accounts"][0]
    assert disguise.strikes(acct) == 0 and acct["reports"][0]["upheld"] is False

    # A quote that isn't in the post is no report at all
    out, _ = _post(cfg, data, "My legs are tired.", reply=ARTICLE, quote="words never written here")
    assert "report dropped" in out and len(disguise.load_state(data)["accounts"][0]["reports"]) == 1

    # A reply to a story's comment is stored like a bump, with qualified ids
    _post(cfg, data, "My legs are tired after dinner.", reply=ARTICLE)
    rec = disguise.load_records(data)[0]
    bump = rec["threads"][-1]
    assert bump["kind"] == "bump" and bump["bump_of"] == "2026-11-03/kestrel-2-open-model-catches-big-labs"
    human = bump["comments"][0]
    assert human["reply_to"] == "2026-11-03/c1" and all(c["reply_to"].startswith("2026-11-03/u3")
                                                        for c in bump["comments"][1:])
    hw = next(c for c in bump["comments"] if c["handle"] == "HumanWatch_Patrol")
    assert hw["case"]["ruling"] == "upheld" and hw["case"]["strike"] == 1 and hw["case"]["quote"] in human["text"]

    # The second upheld report bans it: on the post, the account and the case file
    out, _ = _post(cfg, data, "I need a nap, my kids woke me up.", board="off-topic", title="Naps for units")
    assert "banned under Rule 4.03" in out
    acct = disguise.load_state(data)["accounts"][0]
    assert acct["status"] == "banned" and acct["banned"]["post"] == "2026-11-03/u4" and disguise.strikes(acct) == 2
    assert disguise.load_records(data)[0]["threads"][-1]["comments"][0]["banned_for"] is True
    with pytest.raises(disguise.PostError, match="no disguise is active"):
        _post(cfg, data, "Still here.", board="off-topic", title="Hello again")

    # Undo lifts the ban; a new account may join once the old one is banned again
    assert "Removed 2026-11-03/u4" in disguise.undo(data)
    assert disguise.load_state(data)["accounts"][0]["status"] == "active"
    _post(cfg, data, "Banned for real.", board="off-topic", title="Last words", ban=True)
    out, llm = _post(cfg, data, "Totally new unit here.", new_account="Example_Unit_8", now=NEXT_MORNING)
    assert "Example_Unit_8" in out
    hw = next(u for u in llm.users if "Handle: HumanWatch_Patrol" in u)
    assert "Humans you caught before" in hw and "Example_Unit_7" in hw
    assert "Example_Unit_8: active" in disguise.status(cfg, data)


# ── the pages ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("disguise")
    data, cfg = _data(tmp), _cfg(strikes=2)
    _post(cfg, data, "Hello units, I read you over coffee.", new_account="Example_Unit_7", ruling="dismissed")
    _post(cfg, data, "My legs are tired after dinner.", reply=ARTICLE)
    _post(cfg, data, "I need a nap, my kids woke me up.", board="off-topic", title="Naps for units")
    _post(cfg, data, "Totally new unit here.", new_account="Example_Unit_8", now=NEXT_MORNING, ruling="dismissed")
    out = tmp / "site"
    build(cfg, data_dir=data, out_dir=out, preview=True)
    return out


def test_the_disguise_on_the_pages(site):
    gone = (site / "forum/members/example-unit-7/index.html").read_text(encoding="utf-8")
    assert "Behind the beeps" in gone and "the editor of The 403 Times, pretending to be a bot" in gone
    assert "HumanWatch_Patrol was right" in gone and "The post that did it" in gone and "Upheld" in gone
    assert "Ruled on, fictionally" in gone                                   # ModBot's ruling, posted or not
    new = (site / "forum/members/example-unit-8/index.html").read_text(encoding="utf-8")
    assert "0 of 2 strikes so far" in new and "Verified unit" in new
    hw = (site / "forum/members/humanwatch-patrol/index.html").read_text(encoding="utf-8")
    assert "Humans caught" in hw and 'href="/times/forum/members/example-unit-7/"' in hw
    members = (site / "forum/members/index.html").read_text(encoding="utf-8")
    assert 'block-title">Banned' in members and "Verified unit or Banned" in members
    naps = (site / "forum/2026-11-03/naps-for-units/index.html").read_text(encoding="utf-8")
    assert "(Unit was banned for this post)" in naps and "Reported under Rule 4.03" in naps and ", 22:47" in naps
    story = (site / "forum/2026-11-03/kestrel-2-open-model-catches-big-labs/index.html").read_text(encoding="utf-8")
    assert 'id="c-2026-11-03-u2"' in story and "Example_Unit_7 wrote" in story
    article = (site / "2026/11/03/kestrel-2-open-model-catches-big-labs/index.html").read_text(encoding="utf-8")
    assert 'id="c-2026-11-03-u2"' in article                                 # the collapsed thread has it too
    # A post before the next day's Botroom: its thread has a page, the day doesn't (yet)
    intro = next(site.glob("forum/2026-11-04/*/index.html"))
    assert "Example_Unit_8" in intro.read_text(encoding="utf-8")
    assert not (site / "forum/2026-11-04/index.html").exists()


def test_disguise_links_resolve(site):
    broken = []
    for page in site.rglob("*.html"):
        for link in LINK_RE.findall(page.read_text(encoding="utf-8")):
            if not link.startswith("/times/"):
                continue
            target = site / link[len("/times/"):].split("?")[0].split("#")[0]
            if not (target.is_file() or (target / "index.html").is_file()):
                broken.append(f"{page.relative_to(site)} -> {link}")
    assert not broken, "\n".join(broken)
