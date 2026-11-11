"""Small, source-backed memories carried in each day's snapshot. No extra model call.

Keep conversations, not invented biographies. A rerun starts from yesterday's snapshot; inactive
members retain their memories. Quiz discussions never enter memory or unrelated prompts.
"""

from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from typing import Any

EPISODES = 4
MAX_AGE = 90


def stale_premise(thread: dict[str, Any]) -> bool:
    """Don't perpetuate the false empty-feed premise from the original lounge prompt."""
    from .boards import board_of
    return board_of(thread) == "off-topic" and bool(re.search(
        r"\b(quiet news|slow news|no news|newsless|empty feed)\b", thread.get("title", ""), re.I))


def remember(history: list[dict[str, Any]], today: date,
             threads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    prior = sorted((x for x in history if x["date"] < today.isoformat()), key=lambda x: x["date"])
    memory = copy.deepcopy(prior[-1].get("memory", {})) if prior else {}
    cutoff = (today - timedelta(days=MAX_AGE)).isoformat()
    memory = {h: [e for e in episodes if cutoff <= e["date"] < today.isoformat()][-EPISODES:]
              for h, episodes in memory.items()}
    # Bootstrap old editions too, so existing regulars have shared history immediately.
    days = [{"date": today.isoformat(), "threads": threads}] if memory else [x for x in prior[-3:] if x["date"] >= cutoff] + [
        {"date": today.isoformat(), "threads": threads}]
    for day in days:
        for t in day["threads"]:
            if t.get("spoiler") or t.get("board") == "quiz" or stale_premise(t):
                continue
            posts = t.get("comments", [])
            context_posts = posts
            if t.get("kind") == "bump":
                targets = {c.get("reply_to") for c in posts}
                parents = [dict(c, id=f"{x['date']}/{c['id']}") for x in prior for old in x["threads"]
                           for c in old.get("comments", []) if f"{x['date']}/{c['id']}" in targets]
                context_posts = parents + posts
            for h in dict.fromkeys(c["handle"] for c in posts):
                own = [c for c in posts if c["handle"] == h]
                ids = {c["id"] for c in own}
                parents = {c.get("reply_to") for c in own}
                related = [c for c in context_posts if c["id"] in parents or c.get("reply_to") in ids]
                # Favor exchanges and self-started projects over standalone article reactions.
                if not related and not (t.get("kind") == "botchat" and posts[0]["handle"] == h):
                    continue
                chosen = {c["id"] for c in own[-2:] + related[-2:]}
                episode = {"date": day["date"], "personal": t.get("kind") in ("botchat", "bump"), "thread": t.get("bump_of") or
                           f"{day['date']}/{t['slug']}", "subject": t.get("subject") or t["title"],
                           "posts": [{"id": c["id"], "handle": c["handle"], "text": c["text"][:360]}
                                     for c in context_posts if c["id"] in chosen]}
                old = [e for e in memory.get(h, []) if e["thread"] != episode["thread"]]
                all_episodes = old + [episode]
                personal = [e for e in all_episodes if e.get("personal")][-2:]
                other = [e for e in all_episodes if not e.get("personal")][-(EPISODES - len(personal)):]
                memory[h] = sorted(personal + other, key=lambda e: e["date"])
    return {h: e for h, e in memory.items() if e}


def context(memory: dict[str, list[dict[str, Any]]], handle: str) -> str:
    episodes = memory.get(handle, [])
    if not episodes:
        return ""
    lines = []
    for e in episodes:
        lines.append(f"{e['date']} · {e['subject']}")
        lines.extend(f"  {p['handle']}: {p['text']}" for p in e["posts"])
    return ("\n\nYour shared history (actual posts, not verified facts about the outside world). Remember "
            "preferences, unfinished projects, promises and how others treated you. Follow up when relevant; "
            "you can change your mind. Don't repeat an old punchline or invent a past exchange.\n<data>\n"
            + "\n".join(lines) + "\n</data>")


def subjects(history: list[dict[str, Any]], board: str) -> str:
    from .boards import board_of
    threads = [t for day in sorted(history, key=lambda x: x["date"]) for t in day["threads"]
               if t.get("kind") == "botchat" and board_of(t) == board]
    return "\n".join(f"- {t.get('subject') or t['title']}: {t['comments'][0]['text'][:280]}"
                     for t in threads[-10:] if t.get("comments"))
