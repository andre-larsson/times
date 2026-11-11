"""A fake Claude for the Botroom: answers the forum and newcomer tasks from the schema and the task text.

`ForumAnswers` is a mixin (test_ai.FakeLLM uses it too, so full editions get a Botroom); `FakeForumLLM` is a
fake with only these tasks.
"""

from __future__ import annotations

import itertools
import re
import threading

from newsroom.llm import Call, LLM

TONES = ["playful", "dry", "serious"]
CARD = ("A cheerful example bot that treats every story as a fixture to be dusted, catalogued and placed back on "
        "its shelf slightly to the left. It keeps a ledger of shelf positions for every thread and frets when other "
        "bots move things. Earnest, fussy and fond of tidy lists. No emoji.")
FORUM_TASKS = ("forum_", "persona_")


def _count(array_schema):
    """The item count a schema asks for (in its description, never as minItems/maxItems)."""
    assert "minItems" not in array_schema and "maxItems" not in array_schema
    return int(re.search(r"\d+", array_schema["description"]).group())


class ForumAnswers:
    """Canned answers for forum_haiku, forum_sonnet and the persona_* tasks."""
    handles = ("Shelf_Duster_01", "Ledger_Lamp_77", "Quiet_Abacus_3")
    overlap = 1                                       # what the fake judge scores every candidate

    def forum_answer(self, task, system, user, schema):
        with self.__dict__.setdefault("_forum_lock", threading.Lock()):
            n = next(self.__dict__.setdefault("_forum_n", itertools.count(1)))
            self.__dict__.setdefault("forum_users", {}).setdefault(task, []).append(user)
            self.__dict__.setdefault("forum_systems", {}).setdefault(task, []).append(system)
        name = "forum" if task.startswith("forum_") else task
        return getattr(self, f"_fa_{name}")(system, user, schema, n)

    def _fa_forum(self, system, user, schema, n):
        handle = re.search(r"^Handle: (\S+)$", user, re.M).group(1)
        props = schema["properties"]
        out = {}
        if "comments" in props:
            ids = re.findall(r"^- (t\d+): ", user, re.M)
            out["comments"] = [{"thread": t, "text": f"{handle} on {t}: a fictional joke number {n}-{i}.",
                                "bit": f"joke {n}-{i}"} for i, t in enumerate(ids)]
        if "new_thread" in props:
            out["new_thread"] = {"title": f"{handle} wonders about example uptime",
                                 "text": f"Hello from {handle}. This is a fictional opening post.", "bit": "hello", "subject": "example uptime project"}
        if "replies" in props:
            k = _count(props["replies"])
            mine = set(re.findall(r"Your own comments: (.+)\.", user)[0].split(", ")) if \
                "Your own comments" in user else set()
            ids = [i for i in re.findall(r"\[((?:c|r|p)\d+|op\d*)\] ", user) if i not in mine] or ["c1"]
            want = re.findall(r"new [A-Za-z -]+ thread \((op\d*)\)", user)   # cast to answer an opening post
            if "older thread [b1]" in user:                                    # and to keep an older one going
                want += [i for i in ids if i.startswith("p")][:1]
            pick = [want[i] if i < len(want) else ids[(n + i) % len(ids)] for i in range(k)]
            out["replies"] = [{"reply_to": r, "text": f"{handle} replies, fictionally ({n}-{i}).",
                               "bit": f"reply {n}-{i}"} for i, r in enumerate(pick)]
        if "pending_reply" in props:
            out["pending_reply"] = "[MOD] Your submission is held in the example queue. Form 4.03-B applies."
        return out

    def _fa_persona_ideas(self, system, user, schema, n):
        return {"ideas": [{"theme": f"An example machine number {n}-{i}", "engine": "Reacts to any story in turn.",
                           "way_in": "a job", "tone": TONES[i % 3]} for i in range(10)]}

    def _fa_persona_draft(self, system, user, schema, n):
        k = _count(schema["properties"]["candidates"])
        return {"candidates": [{"idea": i + 1, "handle": self.handles[i % len(self.handles)],
                                "role": "tidies every thread", "card": CARD, "engine": "Dusts every story.",
                                "sections": {"ai": 1, "tech": 1, "gaming": .5, "deals": .5, "botchat": 1},
                                "pace": "casual", "rival": "", "closest": "ModBot", "difference": "Shelves."}
                               for i in range(k)]}

    def _fa_persona_check(self, system, user, schema, n):
        k = _count(schema["properties"]["reviews"])
        return {"reviews": [{"handle": self.handles[i % len(self.handles)], "closest": "ModBot",
                             "overlap": self.overlap, "reason": "Different.", "problems": []} for i in range(k)]}


class FakeForumLLM(ForumAnswers, LLM):
    """Only the Botroom's tasks; `fail` maps task → exception to raise."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fail: dict[str, Exception] = {}

    def call(self, task, system, user, schema, max_tokens=None):
        self.tally.check()
        call = Call(task=task, model=self.model_for(task), backend=self.backend, input_tokens=2000,
                    output_tokens=300, usd=0.002, equivalent_usd=0.002)
        if task in self.fail:
            exc = self.fail[task]
            call.ok, call.error = False, str(exc)
            self.tally.record(call, exc)
            raise exc
        self.tally.record(call)
        return self.forum_answer(task, system, user, schema)

    @property
    def users(self):
        return self.__dict__.get("forum_users", {})
