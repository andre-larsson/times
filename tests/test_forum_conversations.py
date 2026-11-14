"""Conversation flow, grounded memory, newspaper features and spoiler isolation."""

import json
import re
from datetime import timedelta

from newsroom import forum, store
from newsroom.forum import memory, topics
from newsroom.render import build
from tests.forum_fake import FakeForumLLM
from tests.test_forum import DAY, _cfg, _edition, _llm


class ConversationLLM(FakeForumLLM):
    def _fa_forum(self, system, user, schema, n):
        out = super()._fa_forum(system, user, schema, n)
        h = re.search(r"^Handle: (\S+)$", user, re.M).group(1)
        # Answer a recent post by somebody else, including a reply written on this very day.
        candidates = re.findall(r"\[((?:c|r)\d+|op\d*)\] (\S+)", user)
        eligible = [cid for cid, author in candidates if author != h]
        if eligible:
            for reply in out.get("replies", []):
                reply["reply_to"] = eligible[-1]
        if "QUIZ_SECRET_ANSWER" in user:
            for c in out.get("comments", []) + out.get("replies", []):
                c["text"] = "QUIZ_SECRET_ANSWER is the answer in this fictional quiz."
                c["bit"] = "QUIZ_SECRET_ANSWER"
        return out


def test_replies_see_new_replies_and_stay_within_budget(tmp_path):
    cfg = _cfg()
    llm = ConversationLLM(cfg, "api", _llm().tally, env={})
    out = forum.write(cfg, llm, _edition(), tmp_path, [])
    posts = [c for t in out.day["threads"] for c in t["comments"]]
    assert any((c.get("reply_to") or "").startswith("r") for c in posts)
    for h, p in out.day["plan"].items():
        assert sum(c["handle"] == h and bool(c.get("reply_to")) for c in posts) <= p["replies"]
    calls = out.day["calls"]
    assert len(calls) <= 2 * len(out.day["plan"])
    assert out.day["memory"]
    assert {"opinion", "quiz", "screen"} <= {t["kind"] for t in out.day["threads"]}
    forum.save(tmp_path, out)
    replay_llm = _llm()
    forum.write(cfg, replay_llm, _edition(), tmp_path, [])
    assert all("Your shared history" not in u for values in replay_llm.users.values() for u in values)


def test_memory_keeps_exchanges_and_survives_quiet_days():
    t = {"kind": "botchat", "board": "off-topic", "slug": "example-project", "title": "Example project",
         "comments": [{"id": "op", "handle": "ExampleBot", "text": "I'm fixing my fictional backup.", "reply_to": None},
                      {"id": "r1", "handle": "HelperBot", "text": "Try the example restore.", "reply_to": "op"}]}
    snapshot = memory.remember([], DAY, [t])
    history = [{"date": DAY.isoformat(), "threads": [t], "memory": snapshot}]
    tomorrow = memory.remember(history, DAY + timedelta(days=1), [])
    assert tomorrow == snapshot
    assert "example restore" in memory.context(tomorrow, "ExampleBot")
    assert memory.remember(history, DAY, []) == {}             # no same-day or future memory on rerun
    assert memory.remember(history, DAY + timedelta(days=91), []) == {}
    assert snapshot == history[0]["memory"]                   # no mutation
    quiz = dict(t, board="quiz", spoiler=True)
    assert memory.remember([], DAY, [quiz]) == {}


def test_features_use_actual_content_and_dedupe():
    ed = _edition()
    got = topics.feature_threads(ed, [], set())
    assert {t["kind"] for t in got} == {"opinion", "quiz", "screen", "arcade"}
    opinion = next(t for t in got if t["kind"] == "opinion")
    assert ed["opinion"]["body"] in json.loads(opinion["brief"])["body"]
    quiz = next(t for t in got if t["kind"] == "quiz")
    assert json.loads(quiz["brief"])["questions"][0]["answer"] == ed["quiz"]["questions"][0]["answer"]
    arcade_t = next(t for t in got if t["kind"] == "arcade")
    assert json.loads(arcade_t["brief"])["title"] == ed["arcade"]["title"]
    tomorrow = {"edition_id": (DAY + timedelta(days=1)).isoformat()}
    assert len(topics.feature_threads(tomorrow, [ed], set())) == 4
    assert topics.feature_threads(tomorrow, [ed], {t["content_key"] for t in got}) == []
    assert topics.feature_threads({"edition_id": (DAY + timedelta(days=8)).isoformat()}, [ed], set()) == []


def test_quiz_answers_stay_in_quiz_calls_memory_and_pages(tmp_path):
    cfg, ed = _cfg(), _edition()
    ed["quiz"]["questions"][0]["options"][ed["quiz"]["questions"][0]["answer"]] = "QUIZ_SECRET_ANSWER"
    llm = ConversationLLM(cfg, "api", _llm().tally, env={})
    out = forum.write(cfg, llm, ed, tmp_path, [])
    assert all("QUIZ_SECRET_ANSWER" not in s for ss in llm.forum_systems.values() for s in ss)
    assert "QUIZ_SECRET_ANSWER" not in json.dumps(out.day["memory"])
    for t in out.day["threads"]:
        if t.get("board") != "quiz":
            assert "QUIZ_SECRET_ANSWER" not in json.dumps(t)
    quiz = next(t for t in out.day["threads"] if t["kind"] == "quiz")
    assert quiz["comments"]
    store.save_edition(tmp_path, ed)
    forum.save(tmp_path, out)
    site = tmp_path / "site"
    build(cfg, tmp_path, site)
    page = (site / "forum" / DAY.isoformat() / quiz["slug"] / "index.html").read_text()
    assert 'class="botroom-details quiz-discussion"' in page
    assert page.index("Show discussion and quiz spoilers") < page.index("QUIZ_SECRET_ANSWER")
    assert 'quiz-discussion" open' not in page
    for path in ["forum/index.html", "forum/quiz/index.html", "index.html"]:
        assert "QUIZ_SECRET_ANSWER" not in (site / path).read_text()
    assert "Discuss · spoilers" in (site / "quiz" / DAY.isoformat() / "index.html").read_text()
    for t in out.day["threads"]:
        if t.get("content_path"):
            source = (site / t["content_path"] / "index.html").read_text()
            assert f"/times/forum/{DAY}/{t['slug']}/" in source
    # Every internal link in the newly generated discussion pages resolves too.
    for path in site.rglob("*.html"):
        for href in re.findall(r'(?:href|src)="(/times/[^"#?]*)', path.read_text()):
            target = site / href.removeprefix("/times/")
            assert target.is_file() or (target / "index.html").is_file(), (path, href)


def test_recent_subjects_include_opening_situation():
    history = [{"date": DAY.isoformat(), "threads": [{"kind": "botchat", "board": "off-topic",
                "title": "A new heading", "subject": "broken fictional backup",
                "comments": [{"text": "I lost my example files."}]}]}]
    text = memory.subjects(history, "off-topic")
    assert "broken fictional backup" in text and "I lost my example files" in text


def test_false_empty_feed_threads_are_not_revived():
    from newsroom.forum.day import bump_pick
    t = {"kind": "botchat", "board": "off-topic", "slug": "quiet-news", "title": "Quiet news day again",
         "comments": [{"id": "op", "handle": "ExampleBot", "text": "No news?", "reply_to": None}]}
    history = [{"date": DAY.isoformat(), "threads": [t]}]
    assert bump_pick(history, DAY + timedelta(days=1), 403) == []
    assert memory.remember(history, DAY + timedelta(days=1), []) == {}


def test_memory_keeps_the_parent_of_a_returning_reply():
    original = {"kind": "botchat", "board": "off-topic", "slug": "example-project", "title": "Example project",
                "comments": [{"id": "op", "handle": "HelperBot", "text": "Try the fictional restore.", "reply_to": None}]}
    history = [{"date": DAY.isoformat(), "threads": [original]}]
    bump = {"kind": "bump", "board": "off-topic", "slug": "example-project", "title": "Example project",
            "bump_of": f"{DAY}/example-project", "comments": [
                {"id": "r1", "handle": "ExampleBot", "text": "That worked, thanks.", "reply_to": f"{DAY}/op"}]}
    got = memory.remember(history, DAY + timedelta(days=1), [bump])
    text = memory.context(got, "ExampleBot")
    assert "Try the fictional restore" in text and "That worked, thanks" in text


def test_replaced_features_do_not_leave_broken_source_links(tmp_path):
    ed = _edition()
    out = forum.write(_cfg(), _llm(), ed, tmp_path, [])
    forum.save(tmp_path, out)
    ed.pop("opinion")
    ed.pop("quiz")
    store.save_edition(tmp_path, ed)
    site = tmp_path / "site"
    build(_cfg(), tmp_path, site)
    for t in out.day["threads"]:
        if t["kind"] in ("opinion", "quiz"):
            page = (site / "forum" / DAY.isoformat() / t["slug"] / "index.html").read_text()
            assert f'href="/times/{t["content_path"]}"' not in page
