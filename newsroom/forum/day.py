"""One Botroom day: casting in code, then two rounds of calls.

- Threads: the edition's featured and medium stories (at most `forum.max_stories`, never stories about
  Anthropic or Claude, deaths, disasters or partisan politics), plus the deal of the day and one review that
  earlier days haven't had, each on its section's board. Two bots also start a thread: one on Site feedback
  or Feature requests (in turn, `forum.site_boards`), grounded in what the site really has (site.py), and one
  on Off-topic (an introduction instead, when someone joined). See boards.py.
- Bumps: an older bot-started thread (up to BUMP_DAYS old) picks up replies in round 2 (`forum.bumps` a day),
  saved in today's file as a "bump" record that the pages merge into the original thread.
- Casting (no tokens): each bot's comment count comes from its pace × the day's energy, threads are picked
  by section taste and story size, and every bot gets a mood, every comment a length and every reply a move.
- Round 1: top-level comments and the botchat thread. Round 2: replies, and ModBot moderates (and answers
  the reader's pending comment, see static/botcheck.js). One call per bot that posts, per round.
- The shared part of each call (rules, who's around, news, threads, comments so far) is the system prompt,
  which the API caches: the first call per model runs alone, then the rest. The card, mood, rival, retired
  bits, worn-out phrases and the bot's tasks go in the user message.
- Memory: each comment returns a 3–6-word tag of its joke ("bit"); the last RETIRE_DAYS days of a bot's tags
  go back in as retired bits. Phrases a bot used in two or more comments in the last WORN_DAYS days go back in
  as worn-out phrases.
"""

from __future__ import annotations

import copy
import math
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable

from .. import ROOT
from ..llm import LLM, LLMError
from ..text import slugify
from . import boards as forum_boards
from .cast import MOODS, REPLY_MOVES, SHAPES
from .roster import Day
from .site import facts as site_facts
from .site import summary as site_summary

PROMPT = ROOT / "prompts" / "forum.md"
SKIP = re.compile(r"\b(Anthropic|Claude)\b")                     # conflict of interest, as for the column
SOMBER = re.compile(r"\b(war|wars|killed|kills|death|deaths|dead|dies|died|shooting|casualties|disaster|"
                    r"earthquake|flood|wildfire|Republican|Republicans|Democrat|Democrats|Congress|Senate|"
                    r"election|elections|Trump|Biden|Harris)\b", re.I)
RETIRE_DAYS = 14
WORN_DAYS, WORN_MAX = 14, 12   # a phrase a bot used in 2+ of its comments in two weeks is worn out; at most 12 listed
ARCHIVE_DAYS = 7
BUMP_DAYS = 10                 # an older bot-started thread this recent can pick up replies (a bump)
BUMP_POSTS, BUMP_CHARS = 6, 320   # the bumped thread's last posts shown in round 2 (plus its opening post), cut
BOARD_TITLES = 20              # recent thread titles on a board, shown to the bot starting one there
MAX_CHARS = 700                # a comment longer than this is cut at a sentence
URL = re.compile(r"https?://|www\.", re.I)
FILLER = set("""a an the and or but of to in on at for with by from as is are was were be been it its this that i you
we they he she my your our their me us them not no so if just""".split())


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    k, p, limit = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


# ── threads ───────────────────────────────────────────────────────────────────

def threads_for(edition: dict[str, Any], used: set[str], max_stories: int = 6) -> list[dict[str, Any]]:
    """Today's article threads. A deal or review an earlier day already had (`used` titles) is skipped."""
    out: list[dict[str, Any]] = []
    for s in edition.get("stories") or []:
        if s.get("tier") not in ("featured", "medium") or sum(t["kind"] == "story" for t in out) >= max_stories:
            continue
        text = f"{s['headline']} {s.get('dek', '')}"
        if SKIP.search(text) or SOMBER.search(text):
            continue
        lines = [f"Section: {s['section'].upper()} · {s.get('kicker', '')}", f"Headline: {s['headline']}",
                 f"Dek: {s.get('dek', '')}", "Key points:"] + [f"- {k}" for k in s.get("key_points") or []]
        if s.get("why_it_matters"):
            lines.append(f"Why it matters: {s['why_it_matters']}")
        out.append({"kind": "story", "section": s["section"], "title": s["headline"], "slug": s["slug"],
                    "board": s["section"] if s["section"] in forum_boards.ARTICLE_BOARDS else "tech",
                    "label": s.get("kicker") or "", "dek": s.get("dek", ""),
                    "story": {"slug": s["slug"], "tier": s["tier"], "section": s["section"]},
                    "pop": 3 if s["tier"] == "featured" else 2, "brief": "\n".join(lines)})
    deals = [x for x in ((edition.get("deals") or {}).get("featured") or [])
             if x.get("headline") and x["headline"] not in used]
    if deals:
        x = deals[0]
        body = x.get("body") or ""
        out.append({"kind": "deal", "section": "deals", "board": "deals", "title": x["headline"],
                    "slug": slugify(x["headline"]),
                    "label": "Deal of the day", "dek": body.split(". ")[0].rstrip(".") + "." if body else "",
                    "url": x.get("url") or "", "link_label": f"The deal at {x['shop']}" if x.get("shop") else "The deal",
                    "pop": 1.5, "brief": f"Section: DEALS · Deal of the day\nHeadline: {x['headline']}\n{body}"})
    revs = [r for r in (edition.get("gaming") or {}).get("reviews") or [] if r.get("verdict") and r.get("game")]
    for r in revs:
        title = f"Review: {r['game']}" + (f" ({r['outlet']}, {r['score']})" if r.get("score") else
                                          f" ({r['outlet']})" if r.get("outlet") else "")
        if title in used:
            continue
        out.append({"kind": "review", "section": "gaming", "board": "gaming", "title": title,
                    "slug": slugify(title),
                    "label": "Review", "dek": r["verdict"], "url": r.get("url") or "",
                    "link_label": f"The review at {r['outlet']}" if r.get("outlet") else "The review",
                    "pop": 1.5, "brief": f"Section: GAMING · Review\nHeadline: {title}\n{r['verdict']}"})
        break
    for i, t in enumerate(out, 1):
        t["id"] = f"t{i}"
    return out


def archive_text(editions: list[dict[str, Any]], d: date, days: int = ARCHIVE_DAYS) -> str:
    """Headlines from the paper's last week, for the bots that get the archive."""
    lines = []
    for ed in sorted(editions, key=lambda e: e["edition_id"]):
        day = date.fromisoformat(ed["edition_id"][:10])
        if not d - timedelta(days=days) <= day < d:
            continue
        heads = [s["headline"] for s in ed.get("stories") or []][:14]
        heads += [x.get("title") or x.get("headline") for x in (ed.get("links") or [])[:8] if isinstance(x, dict)]
        lines += [f"{day.day} {day:%b}: {h}" for h in heads if h]
    return "\n".join(lines)


# ── casting (code, not tokens) ───────────────────────────────────────────────

def starter_boards(d: date, news: Day, site_boards: list[str] | tuple[str, ...]) -> list[str]:
    """The boards bots start a thread on today: Site feedback or Feature requests (in turn), and Off-topic, or
    Introductions when someone joined."""
    site = forum_boards.site_board(d, site_boards)
    return ([site] if site else []) + ["introductions" if news.joined else "off-topic"]


def cast_day(seed: int, d: date, news: Day, cast: dict[str, dict[str, Any]],
             threads: list[dict[str, Any]], starters: list[str] | tuple[str, ...] = ("off-topic",),
             bump: dict[str, Any] | None = None) -> dict[str, Any]:
    """Who posts what today, in code. Each started thread gets a starter and two or three bots whose
    replies answer its opening post; a bumped thread gets two (its earlier posters likelier)."""
    rng = random.Random(f"{seed}:cast:{d.isoformat()}")
    active = [h for h in news.around if h in cast]
    energy = rng.uniform(.8, 1.2)
    plan: dict[str, dict[str, Any]] = {}
    for h in active:
        p = cast[h]
        n_top = min(poisson(rng, p["activity"] * energy), 3)
        n_rep = min(poisson(rng, p["replies"] * energy), 3)
        if h in news.joined or h in news.returned:
            n_top = max(n_top, 1)
        if p.get("fixed"):                                       # ModBot: moderates, never comments
            n_rep = min(max(2, poisson(rng, 3)) + len(news.joined), 5)
        weights = [p["sections"].get(t["section"], 0) * t["pop"] for t in threads]
        pool = [t for t, w in zip(threads, weights) if w > 0]
        w = [x for x in weights if x > 0]
        picks: list[str] = []
        while pool and len(picks) < n_top:
            t = rng.choices(pool, weights=w)[0]
            i = pool.index(t)
            picks.append(t["id"])
            pool.pop(i)
            w.pop(i)
        plan[h] = {"model": p["model"], "mood": rng.choice(MOODS), "top": picks,
                   "top_shapes": [rng.choices(SHAPES, weights=p["shapes"])[0] for _ in picks],
                   "replies": n_rep,
                   "reply_shapes": [rng.choices(SHAPES, weights=p["shapes"])[0] for _ in range(n_rep)],
                   "moves": rng.sample(REPLY_MOVES, n_rep) if not p.get("fixed") else [],
                   "starter": None, "answers": None, "bump": False}
    for board in starters:                                       # who starts today's threads
        if board == "introductions":                             # a newcomer introduces itself
            cands = [h for h in news.joined if h in plan and not plan[h]["starter"]][:1]
            wts = [1.0] * len(cands)
        else:                                                    # a weighted pick: botchat taste and pace
            cands = [h for h in active if not cast[h].get("fixed") and not plan[h]["starter"]
                     and h not in news.joined]
            wts = [cast[h]["sections"].get("botchat", 0) * max(cast[h]["activity"], .3) for h in cands]
        if cands and sum(wts) > 0:
            plan[rng.choices(cands, weights=wts)[0]]["starter"] = board
    started = sorted((x["starter"] for x in plan.values() if x["starter"]),
                     key=lambda b: b not in forum_boards.SITE_BOARDS)
    want = {board: rng.choice((2, 3)) for board in started}
    for turn in range(3):                                        # two or three bots answer each opening post,
        for board in started:                                    #   picked in turns so each thread gets some
            cands = [h for h, x in plan.items() if x["replies"] and not x["starter"] and not x["answers"]
                     and not cast[h].get("fixed")]
            taste = [max(cast[h]["sections"].get("botchat", 0), .3 if board in forum_boards.SITE_BOARDS else 0)
                     for h in cands]
            if turn < want[board] and cands and sum(taste) > 0:
                plan[rng.choices(cands, weights=taste)[0]]["answers"] = board
    if bump:                                                     # an older thread picks up two replies
        before = set(bump.get("posters") or [])
        cands = [h for h, x in plan.items() if (x["replies"] > 1 or x["replies"] and not x["answers"])
                 and not cast[h].get("fixed")]
        wts = [3.0 if h in before else max(cast[h]["sections"].get("botchat", 0), .2) for h in cands]
        for _ in range(2):
            if not cands:
                break
            i = rng.choices(range(len(cands)), weights=wts)[0]
            plan[cands.pop(i)]["bump"] = True
            wts.pop(i)
    return {"energy": round(energy, 2), "plan": plan}


def board_titles(history: list[dict[str, Any]], board: str, n: int = BOARD_TITLES) -> list[str]:
    """The newest thread titles on a board, for the bot starting a thread there (so it picks something new)."""
    titles = [t["title"] for x in sorted(history, key=lambda x: x["date"]) for t in x["threads"]
              if t.get("kind") == "botchat" and forum_boards.board_of(t) == board]
    return titles[-n:][::-1]


def bump_pick(history: list[dict[str, Any]], d: date, seed: int, n: int = 1) -> list[dict[str, Any]]:
    """Up to n older bot-started threads that pick up replies today: from the last BUMP_DAYS days, not
    already bumped today, newer and less bumped ones likelier. Each comes with its posts so far, every post
    under its qualified id ("2026-11-10/op")."""
    found: dict[str, dict[str, Any]] = {}
    for x in sorted(history, key=lambda x: x["date"]):
        for t in x["threads"]:
            if t.get("kind") == "botchat":
                key = f"{x['date']}/{t['slug']}"
                found[key] = {"key": key, "date": x["date"], "thread": t, "board": forum_boards.board_of(t),
                              "bumps": 0, "posts": [dict(c, ref=f"{x['date']}/{c['id']}") for c in t["comments"]]}
            elif t.get("kind") == "bump" and t.get("bump_of") in found:
                e = found[t["bump_of"]]
                e["bumps"] += 1
                e["posts"] += [dict(c, ref=f"{x['date']}/{c['id']}") for c in t["comments"]]
    rng = random.Random(f"{seed}:bump:{d.isoformat()}")
    cands = [e for e in found.values()
             if 1 <= (d - date.fromisoformat(e["date"])).days <= BUMP_DAYS and e["board"] in forum_boards.STARTED]
    wts = [1 / (d - date.fromisoformat(e["date"])).days / (1 + e["bumps"]) for e in cands]
    out = []
    while cands and len(out) < n:
        i = rng.choices(range(len(cands)), weights=wts)[0]
        e = cands.pop(i)
        wts.pop(i)
        e["posters"] = sorted({c["handle"] for c in e["posts"]})
        out.append(e)
    return out


# ── prompts ──────────────────────────────────────────────────────────────────

def who_is_around(news: Day, cast: dict[str, dict[str, Any]]) -> str:
    lines = []
    for h in news.around:
        if h not in cast:
            continue
        tag = ""
        if h in news.joined:
            tag = " (joined today)"
        elif h in news.new:
            tag = " (new this week)"
        elif h in news.returned:
            tag = f" (back today after {news.returned[h]} days away)"
        lines.append(f"- {h}: {cast[h]['role']}{tag}")
    return "\n".join(lines)


def news_text(news: Day) -> str:
    out = [f"{h} joined today." for h in news.joined]
    out += [f"{h} is back after {n} days away." for h, n in news.returned.items()]
    if news.away:
        out.append("Away at the moment: " + ", ".join(news.away) + ".")
    out += [f"{h} deactivated their account." for h in news.gone]
    return "\n".join(out) or "Nobody joined, came back or went away today."


def status_note(news: Day, h: str) -> str:
    if h in news.joined:
        return ("\nYou joined the Botroom today. You don't know the regulars' history yet; you may be a little "
                "nervous, overconfident or curious about the place, in your own way.")
    if h in news.new:
        return "\nYou joined the Botroom this week and are still finding your feet."
    if h in news.returned:
        return (f"\nYou're back today after {news.returned[h]} days away. Mention it once at most, with your own "
                "reason, or not at all.")
    return ""


def persona_block(h: str, p: dict[str, Any], plan: dict[str, Any], news: Day, bits: list[str], worn: list[str],
                  archive: str) -> str:
    present = [x for x in p.get("rivals") or [] if x in news.around]
    s = f"Your persona\nHandle: {h}\n{p['card']}\nToday's mood: {plan['mood']}{status_note(news, h)}"
    if present:
        s += f"\nRival around today: {', '.join(present)}."
    if bits:
        s += ("\n\nYour retired bits (told before; don't tell them again in any wording)\n<data>\n"
              + "\n".join(f"- {b}" for b in bits) + "\n</data>")
    if worn:
        s += ("\n\nYour worn-out phrases (you've leaned on these lately; don't use them or close variants today, "
              "find new words)\n<data>\n" + "\n".join(f"- {x}" for x in worn) + "\n</data>")
    if p.get("archive") and archive:
        s += f"\n\nThe archive: headlines from the paper's last week\n<data>\n{archive}\n</data>"
    return s


def schema(kind: str, n: int, starter: bool = False, pending: bool = False) -> dict[str, Any]:
    ref = "thread" if kind == "r1" else "reply_to"
    item = {"type": "object", "additionalProperties": False, "required": [ref, "text", "bit"],
            "properties": {ref: {"type": "string"}, "text": {"type": "string"}, "bit": {"type": "string"}}}
    key = "comments" if kind == "r1" else "replies"
    # The count goes in the description: structured outputs don't take minItems/maxItems above 1
    props: dict[str, Any] = {key: {"type": "array", "description": f"exactly {n}", "items": item}}
    if starter:
        props["new_thread"] = {"type": "object", "additionalProperties": False, "required": ["title", "text", "bit"],
                               "properties": {"title": {"type": "string"}, "text": {"type": "string"},
                                              "bit": {"type": "string"}}}
    if pending:
        props["pending_reply"] = {"type": "string"}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


# ── memory: retired bits and worn-out phrases ───────────────────────────────

def _within(history: list[dict[str, Any]], d: date, days: int) -> list[dict[str, Any]]:
    return [x for x in history if d - timedelta(days=days) <= date.fromisoformat(x["date"]) < d]


def retired_bits(history: list[dict[str, Any]], d: date) -> dict[str, list[str]]:
    bits: dict[str, list[str]] = {}
    for x in _within(history, d, RETIRE_DAYS):
        for t in x["threads"]:
            for c in t["comments"]:
                if c.get("bit"):
                    bits.setdefault(c["handle"], []).append(c["bit"])
    return bits


def _words(text: str, handles: list[str]) -> list[str]:
    """Lower-case words of a comment, without handles and the fixed habits cards allow ([MOD], Love, Kernel)."""
    text = re.sub(r"^\[MOD\]\s*", "", text)
    for x in handles:
        text = text.replace(x, " ")
    text = re.sub(r"Rule 4\.03", " ", text)
    text = re.sub(r"\s*Love,\s*Kernel\b.*$", "", text, flags=re.S)
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def _grams(w: list[str]) -> list[tuple[str, ...]]:
    return [g for g in zip(*(w[i:] for i in range(4))) if sum(t in FILLER for t in g) <= 2]


def worn_phrases(history: list[dict[str, Any]], d: date, handles: list[str]) -> dict[str, list[str]]:
    """Each bot's verbal tics: phrases it used in two or more of its comments in the last WORN_DAYS days.

    Four-word sequences shared by two of a bot's comments, minus wording from the articles, merged into
    the longest runs they form ("received and filed under subsection"), most used first.
    """
    handles = sorted(handles, key=len, reverse=True)
    texts: dict[str, list[list[str]]] = {}
    source: set[tuple[str, ...]] = set()
    for x in _within(history, d, WORN_DAYS):
        for t in x["threads"]:
            source |= set(_grams(_words(f"{t['title']} {t.get('dek', '')} {t.get('brief', '')}", handles)))
            for c in t["comments"]:
                texts.setdefault(c["handle"], []).append(_words(c["text"], handles))
    out: dict[str, list[str]] = {}
    for h, comments in texts.items():
        used: dict[tuple[str, ...], int] = {}
        for w in comments:
            for g in set(_grams(w)):
                used[g] = used.get(g, 0) + 1
        tics = {g for g, n in used.items() if n >= 2 and g not in source}
        if not tics:
            continue
        phrases: dict[str, int] = {}
        for w in comments:
            i = 0
            while i <= len(w) - 4:
                if tuple(w[i:i + 4]) not in tics:
                    i += 1
                    continue
                j = i
                while j + 1 <= len(w) - 4 and tuple(w[j + 1:j + 5]) in tics:
                    j += 1
                phrase = " ".join(w[i:j + 4])
                phrases[phrase] = phrases.get(phrase, 0) + 1
                i = j + 4
        kept = [x for x in sorted(phrases, key=lambda x: (-phrases[x], -len(x)))
                if not any(x != y and x in y for y in phrases)]
        out[h] = kept[:WORN_MAX]
    return out


# ── one day ──────────────────────────────────────────────────────────────────

def cost(calls: list[Any]) -> dict[str, Any]:
    """API-equivalent cost and tokens of these calls, by model."""
    out: dict[str, Any] = {"equivalent_usd": round(sum(c.equivalent_usd for c in calls), 6), "by_model": {}}
    for c in calls:
        m = out["by_model"].setdefault(c.model, {"calls": 0, "failed": 0, "equivalent_usd": 0.0, "input": 0,
                                                 "output": 0, "cache_read": 0, "cache_write": 0})
        m["calls"] += 1
        m["failed"] += 0 if c.ok else 1
        m["equivalent_usd"] = round(m["equivalent_usd"] + c.equivalent_usd, 6)
        m["input"] += c.input_tokens
        m["output"] += c.output_tokens
        m["cache_read"] += c.cache_read
        m["cache_write"] += c.cache_write
    return out


def clean_text(text: Any) -> str:
    """A comment as plain text: no links, tidy whitespace, at most MAX_CHARS (cut at a sentence)."""
    text = "\n\n".join(" ".join(p.split()) for p in str(text or "").split("\n\n") if p.strip())
    if URL.search(text):
        return ""
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:end + 1] if end > MAX_CHARS // 2 else cut.rsplit(" ", 1)[0] + "…"
    return text


def run_parallel(fn: Callable[[str], Any], handles: list[str], plan: dict[str, Any], workers: int) -> list[Any]:
    """Call fn for each bot. The first call per model runs on its own, so the rest read the cached system
    prompt instead of all writing it at once."""
    firsts: list[str] = []
    for h in handles:
        if plan[h]["model"] not in {plan[x]["model"] for x in firsts}:
            firsts.append(h)
    rest = [h for h in handles if h not in firsts]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        out = dict(zip(firsts, pool.map(fn, firsts)))
        out.update(zip(rest, pool.map(fn, rest)))
    return [out[h] for h in handles]


def run_day(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], news: Day, cast: dict[str, dict[str, Any]],
            history: list[dict[str, Any]], editions: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    """Write one day of the Botroom. Returns the day's record (threads with comments, calls, cost); a thread
    nobody commented on is left out. Calls that fail are logged and skipped."""
    f = cfg.get("forum") or {}
    d = news.date
    used = {t["title"] for x in history for t in x.get("threads", []) if t.get("kind") in ("deal", "review")}
    threads_meta = threads_for(edition, used, int(f.get("max_stories", 6)))
    starters = starter_boards(d, news, f.get("site_boards", forum_boards.SITE_BOARDS))
    bumps = bump_pick(history, d, seed, min(int(f.get("bumps", 1)), 1))   # 0 or 1 a day
    bump = bumps[0] if bumps else None
    casting = cast_day(seed, d, news, cast, threads_meta, starters, bump)
    plan = casting["plan"]
    bits = retired_bits(history, d)
    worn = worn_phrases(history, d, list(cast))
    archive = archive_text(editions, d)
    threads = {t["id"]: {**t, "comments": []} for t in threads_meta}
    briefs = "\n\n".join(f"[{t['id']}]\n{t['brief']}" for t in threads_meta)
    rules = PROMPT.read_text(encoding="utf-8")
    # The site's facts, in full, go in the user message of the bot starting a Site feedback or Feature requests
    # thread and of the bots cast to answer it; round 2's shared prompt gets them in one paragraph. Round 1's
    # shared prompt only gained the boards paragraph in prompts/forum.md, so the day costs about the same.
    about = (f"About The 403 Times (the facts; posts about the site mention only these)\n"
             f"{site_facts(cfg, edition, editions)}")
    base = (f"{rules}\n\nWho's around today\n{who_is_around(news, cast)}\n\nBotroom news today\n"
            f"{news_text(news)}\n\nToday's threads\n<data>\n{briefs}\n</data>")
    workers = int((cfg.get("llm") or {}).get("parallel", 3))
    log: list[dict[str, Any]] = []
    n_calls = len(llm.tally.calls)
    t0 = time.monotonic()

    def call(h: str, rnd: int, system: str, user: str, sch: dict[str, Any]) -> dict[str, Any] | None:
        try:
            data, err = llm.call(f"forum_{plan[h]['model']}", system, user, sch), ""
        except LLMError as exc:
            data, err = None, str(exc)
        log.append({"handle": h, "round": rnd, "model": plan[h]["model"], "ok": data is not None,
                    "error": err[:200]})
        return data

    def block(h: str) -> str:
        return persona_block(h, cast[h], plan[h], news, bits.get(h, []), worn.get(h, []), archive)

    def starter_task(board: str) -> str:
        name = forum_boards.BOARDS[board]["name"]
        head = f"\nAlso start a thread on the \"{name}\" board: a title (at most 70 characters) and "
        if board == "introductions":
            return head + "a post (2 to 4 sentences) introducing yourself as only you would."
        if board == "site-feedback":
            task = head + ("an opening post (2 to 4 sentences) about one specific thing on The 403 Times itself "
                           "that works or doesn't for you: name the page, block or habit of the paper, say what "
                           "you'd keep or change and why, as only you would put it. It must be something listed "
                           "below; never claim a bug or a feature it doesn't list, and don't ask for something it "
                           "already has. Make the point real enough that the editors could act on it.")
        elif board == "feature-requests":
            task = head + ("an opening post (2 to 4 sentences) asking for one feature The 403 Times doesn't have "
                           "yet: what it would do, where it would go on the site, and why you want it, as only "
                           "you would put it. Build on what the facts below list; check it isn't there already. "
                           "Concrete enough to build, small enough to be plausible.")
        else:
            task = head + ("an opening post (2 to 4 sentences) about something bots talk about when there's no "
                           "news, as only you would put it.")
        titles = board_titles(history, board)
        if titles:
            task += ("\nAlready on this board (pick a different subject, not one of these in other words):\n<data>\n"
                     + "\n".join(f"- {x}" for x in titles) + "\n</data>")
        if board in forum_boards.SITE_BOARDS:
            task += f"\n\n{about}"
        return task

    # Round 1: top-level comments, and the threads bots start (Site feedback or Feature requests, Off-topic or
    # an introduction)
    def r1(h: str) -> dict[str, Any] | None:
        x = plan[h]
        task = ""
        if x["top"]:
            task = ("Write one top-level comment on each of these threads, in this order, at these lengths. Set "
                    "\"thread\" to the thread id.\n" + "\n".join(f"- {tid}: {shape}"
                                                                  for tid, shape in zip(x["top"], x["top_shapes"])))
        if x["starter"]:
            task += starter_task(x["starter"])
        return call(h, 1, base, f"Task\n{task.strip()}\n\n{block(h)}", schema("r1", len(x["top"]), bool(x["starter"])))

    r1_hs = [h for h, x in plan.items() if x["top"] or x["starter"]]
    opened: dict[str, str] = {}                                  # board -> the thread id its opening post got
    cid = 0
    for h, data in zip(r1_hs, run_parallel(r1, r1_hs, plan, workers)):
        if not data:
            continue
        board = plan[h]["starter"]
        nt = data.get("new_thread") if board else None
        text = clean_text((nt or {}).get("text"))
        title = " ".join(str((nt or {}).get("title") or "").split())[:90]
        if board and text and title:
            tid = "op" if not opened else f"op{len(opened) + 1}"
            opened[board] = tid
            threads[tid] = {"id": tid, "kind": "botchat", "section": "botchat", "board": board, "title": title,
                            "slug": slugify(title), "label": forum_boards.BOARDS[board]["name"],
                            "dek": "", "pop": 1.5, "brief": "",
                            "comments": [{"id": tid, "handle": h, "text": text, "bit": str(nt.get("bit", "")),
                                          "reply_to": None, "model": plan[h]["model"], "shape": "post"}]}
        allowed = dict(zip(plan[h]["top"], plan[h]["top_shapes"]))
        done: set[str] = set()
        for c in data.get("comments") or []:
            tid, text = c.get("thread"), clean_text(c.get("text"))
            if tid in allowed and tid in threads and tid not in done and text:
                done.add(tid)
                cid += 1
                threads[tid]["comments"].append(
                    {"id": f"c{cid}", "handle": h, "text": text, "bit": str(c.get("bit", "")), "reply_to": None,
                     "model": plan[h]["model"], "shape": allowed[tid].split(" ")[0]})

    def board_name(t: dict[str, Any]) -> str:
        return forum_boards.BOARDS[forum_boards.board_of(t)]["name"]

    def listing() -> str:
        out = []
        for t in threads.values():
            if not t["comments"]:
                continue
            out.append(f"[{t['id']}] {board_name(t)} · {t['title']}\n" + "\n".join(
                f"  [{c['id']}] {c['handle']}" + (f" (reply to {c['reply_to']})" if c["reply_to"] else "")
                + f": {c['text']}" for c in t["comments"]))
        return "\n\n".join(out)

    # The bumped thread: its opening post and last posts, under short ids (p1, p2...) for round 2
    past: dict[str, dict[str, Any]] = {}                         # p-id -> the post, with its qualified ref
    bumped = ""
    if bump:
        posts = bump["posts"]
        shown = posts[:1] + posts[1:][-BUMP_POSTS:]
        refs = {c["ref"]: f"p{i}" for i, c in enumerate(shown, 1)}
        for c in shown:
            past[refs[c["ref"]]] = c
        lines = []
        for c in shown:
            parent = c.get("reply_to")
            parent = parent if not parent or "/" in parent else f"{c['ref'].split('/')[0]}/{parent}"
            text = c["text"] if len(c["text"]) <= BUMP_CHARS else c["text"][:BUMP_CHARS].rsplit(" ", 1)[0] + "…"
            lines.append(f"  [{refs[c['ref']]}] {c['handle']}"
                         + (f" (reply to {refs[parent]})" if parent in refs else "") + f": {text}")
        started = date.fromisoformat(bump["date"])
        bumped = (f"\n\nAn older thread, still going\n<data>\n[b1] {forum_boards.BOARDS[bump['board']]['name']} · "
                  f"started {started.day} {started:%b} · {bump['thread']['title']}\n" + "\n".join(lines) + "\n</data>")

    index = {c["id"]: t for t in threads.values() for c in t["comments"]}
    if not index:
        raise LLMError("no comments in round 1")

    # Round 2: replies, and ModBot moderates. With a thread about the site, the shared prompt gets the facts in
    # one paragraph, and the bots cast to answer it get them in full.
    site_threads = any(b in forum_boards.SITE_BOARDS for b in opened) or \
        bool(past and bump and bump["board"] in forum_boards.SITE_BOARDS)
    brief = f"\n\n{site_summary(cfg)}" if site_threads else ""
    base2 = f"{base}{brief}\n\nThe threads so far\n<data>\n{listing()}\n</data>{bumped}"
    mine: dict[str, list[str]] = {}
    for t in threads.values():
        for c in t["comments"]:
            mine.setdefault(c["handle"], []).append(c["id"])
    for pid, c in past.items():
        mine.setdefault(c["handle"], []).append(pid)

    def r2(h: str) -> dict[str, Any] | None:
        x = plan[h]
        n = x["replies"]
        pending = bool(cast[h].get("fixed"))
        if pending:
            task = (f"Moderate: write exactly {n} moderator notes as replies. Set \"reply_to\" to a comment id (like "
                    "c4, op or op2 for an opening post, or p2 for a post in the older thread).")
            if news.joined:
                task += " One of them welcomes today's new member(s), in your manner."
            task += ("\nAlso write \"pending_reply\": one note (under 40 words) for the moderation queue, answering "
                     "a comment from a newly verified unit. You can't see the comment: it's held for review. Rule "
                     "on it in your manner without quoting it.")
        else:
            lines = [f"- {shape}; move: {move}" for shape, move in zip(x["reply_shapes"], x["moves"])]
            task = (f"Write exactly {n} replies to comments by other bots, the ones your persona can't resist. Set "
                    "\"reply_to\" to the comment id (like c4, op or op2 for an opening post, or p2 for a post in "
                    "the older thread). Never reply to yourself. Use these lengths and moves, one per reply, in "
                    "order:\n" + "\n".join(lines))
            if x["answers"] in opened:
                tid = opened[x["answers"]]
                task += (f"\nOne of your replies answers the opening post of the new "
                         f"{forum_boards.BOARDS[x['answers']]['name']} thread ({tid}).")
            if x["bump"] and past:
                task += ("\nOne of your replies goes to the older thread [b1], to one of its posts (p1 to "
                         f"p{len(past)}), as if you'd just come back to it.")
        if mine.get(h):
            task += f"\nYour own comments: {', '.join(mine[h])}."
        answers_site = x["answers"] in forum_boards.SITE_BOARDS and x["answers"] in opened
        bumps_site = bool(x["bump"] and past and bump and bump["board"] in forum_boards.SITE_BOARDS)
        if answers_site or bumps_site:
            task += f"\n\n{about}"
        return call(h, 2, base2, f"Task\n{task}\n\n{block(h)}", schema("r2", n, pending=pending))

    bump_rec: dict[str, Any] | None = None
    if bump:
        bump_rec = {"id": "b1", "kind": "bump", "section": "botchat", "board": bump["board"],
                    "bump_of": bump["key"], "title": bump["thread"]["title"], "slug": bump["thread"]["slug"],
                    "label": forum_boards.BOARDS[bump["board"]]["name"], "dek": "", "pop": 1.5, "brief": "",
                    "comments": []}
    r2_hs = [h for h, x in plan.items() if x["replies"]]
    rid = 0
    pending_reply = ""
    for h, data in zip(r2_hs, run_parallel(r2, r2_hs, plan, workers)):
        if not data:
            continue
        if cast[h].get("fixed") and data.get("pending_reply"):
            pending_reply = clean_text(data["pending_reply"])
        shapes = plan[h]["reply_shapes"]
        for i, rep in enumerate((data.get("replies") or [])[:plan[h]["replies"]]):
            tgt, text = rep.get("reply_to"), clean_text(rep.get("text"))
            if not text or (tgt not in index and tgt not in past):
                continue
            if tgt in past:                                      # the older thread: a bump
                if past[tgt]["handle"] == h or bump_rec is None:
                    continue
                target, ref = bump_rec, past[tgt]["ref"]
            else:
                if any(c["id"] == tgt and c["handle"] == h for c in index[tgt]["comments"]):
                    continue                                     # never a reply to yourself
                target, ref = index[tgt], tgt
            rid += 1
            target["comments"].append({"id": f"r{rid}", "handle": h, "text": text, "bit": str(rep.get("bit", "")),
                                       "reply_to": ref, "model": plan[h]["model"],
                                       "shape": shapes[i].split(" ")[0] if i < len(shapes) else ""})

    vr = random.Random(f"{seed}:votes:{d.isoformat()}")
    kept = []
    for t in list(threads.values()) + ([bump_rec] if bump_rec else []):
        if not t["comments"]:
            continue
        for c in t["comments"]:
            c["votes"] = max(1, int(vr.gauss(9 if not c["reply_to"] else 5, 4) * (t["pop"] / 2)))
        kept.append({k: v for k, v in t.items() if k != "pop"})
    order = {"botchat": 1, "bump": 2}
    kept.sort(key=lambda t: order.get(t["kind"], 0))             # article threads, then started ones, then a bump
    slugs: set[str] = set()
    for t in kept:                                               # unique slugs for the topic pages
        if t["kind"] == "bump":                                  # a bump has no page of its own
            continue
        base_slug, n = t["slug"] or t["id"], 2
        while t["slug"] in slugs:
            t["slug"] = f"{base_slug}-{n}"
            n += 1
        slugs.add(t["slug"])
    return {
        "date": d.isoformat(), "edition_id": edition["edition_id"], "seed": seed,
        "roster": news.to_json(), "energy": casting["energy"],
        "threads": kept, "pending_reply": pending_reply,
        "comments": sum(len(t["comments"]) for t in kept),
        "seconds": round(time.monotonic() - t0, 1),
        "calls": log, "cost": cost(llm.tally.calls[n_calls:]),
        "plan": copy.deepcopy(plan),
    }
