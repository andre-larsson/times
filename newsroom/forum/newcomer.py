"""Brand-new Botroom members, generated on the day they join and never a rerun of an existing persona.

How a newcomer is made (4 or 5 times a year, ~$0.65 each):
1. Ideas (`persona_ideas`, Fable): ten ideas (theme, engine, way in, tone), seeing every member that has
   ever existed and the last PAST_IDEAS ideas proposed, and told to make the ten as different as it can.
2. Code picks the newcomer's tone (playful 40%, dry 30%, serious 30%) and three ideas of that tone at random,
   so the model invents and code chooses.
3. Drafts (`persona_draft`, Opus): the three written up as candidates (handle, role, card, sections, pace,
   the moods it leans to and the ones it is never in, rival, closest member and how it differs).
4. Code checks each candidate: handle format, likeness to existing handles, banned words, card length,
   quoted lines, one fixed habit at most, stock wording, the emoji rule, word overlap with every card, a
   rival who is around.
5. The judge (`persona_check`, Sonnet), without the drafter's own claims, names each candidate's closest
   member, scores the overlap from 1 to 5 and flags problems from a fixed list.
6. The least overlapping candidate that passed both joins if its overlap is at most 2. Otherwise up to two
   more rounds with fresh ideas, the rejects listed as taken.
Code sets the rest: Haiku writes it, its pace numbers, a color rare among those around. The persona goes to
data/forum/cast.json, so one you don't like can be deleted with a push (or moved to "retired", which keeps
it taken without letting it join).
"""

from __future__ import annotations

import difflib
import random
import re
from datetime import date
from typing import Any

from .. import ROOT
from ..llm import LLM, LLMError
from .cast import MOOD_NAMES, MOODS, PACE, SECTIONS, mood_names

PROMPTS = ROOT / "prompts"
COLORS = ["ai", "tech", "gaming", "deals", "rust", "rose", "slate"]
BANNED = re.compile(r"human|anthropic|claude|openai|gemini|llama|gpt", re.I)
TONES = {"playful": .4, "dry": .3, "serious": .3}
PAST_IDEAS = 40     # earlier ideas passed back in; the whole list made the ideas call grow from $0.34 to $0.75
KEEP_IDEAS = 200    # ideas kept in cast.json
ROUNDS = 3

STOP = set("""a an the and or but of to in on at for with by from as is are was were be been being it its this that these
those i me my you your we our they them their he she his her not no so if then than just very too also do does did have
has had will would can could should one all any some what which who how when where there here about into over out up
down more most only own same such every each never always like itself treats other others own emoji bot bots no""".split())


# ── checks in code ───────────────────────────────────────────────────────────

def _norm(h: str) -> str:
    return re.sub(r"[^a-z]", "", h.lower())


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", t.lower()) if w not in STOP and len(w) > 2}


def code_check(c: dict[str, Any], known: dict[str, dict[str, Any]], around: list[str]) -> list[str]:
    """What's wrong with a drafted candidate, as short notes (empty: it passes)."""
    out = []
    h = str(c.get("handle", ""))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{5,21}", h):
        out.append("handle format")
    if BANNED.search(h):
        out.append("banned word in handle")
    for k in known:
        if _norm(k) == _norm(h) or difflib.SequenceMatcher(None, _norm(k), _norm(h)).ratio() > .75:
            out.append(f"handle too close to {k}")
    card = str(c.get("card", ""))
    n = len(card.split())
    if not 30 <= n <= 90:
        out.append(f"card is {n} words")
    quotes = re.findall(r"[\"“][^\"”]{3,}[\"”]", card)
    habits = len(re.findall(r"fixed habit", card, re.I))
    if habits > 1:
        out.append("more than one fixed habit")
    if len(quotes) > habits:
        out.append("quoted lines in card")
    if re.search(r"rare(,| and) dry humou?r", card, re.I):
        out.append("stock wording: rare, dry humor")
    if not re.search(r"(No emoji\.|Emoji: at most one per comment\.)\s*$", card):
        out.append("no emoji rule at the end")
    if len(str(c.get("role", "")).split()) > 8:
        out.append("role too long")
    me = _words(card + " " + str(c.get("role", "")))
    for k, p in known.items():
        o = _words(p["card"] + " " + p["role"])
        j = len(me & o) / max(1, len(me | o))
        if j > .2:
            out.append(f"card wording close to {k} ({j:.2f})")
    if c.get("rival") and c["rival"] not in around:
        out.append(f"rival {c['rival']} isn't around")
    if sum(1 for s in SECTIONS if (c.get("sections") or {}).get(s, 0) > 0) < 3:
        out.append("too few sections")
    if c.get("pace") not in PACE:
        out.append("unknown pace")
    if len(mood_names(c.get("moods"), 8)) < 3:
        out.append("too few moods")
    return out


# ── schemas and prompts (counts go in descriptions: structured outputs take no minItems/maxItems above 1) ──

def ideas_schema() -> dict[str, Any]:
    idea = {"type": "object", "additionalProperties": False, "required": ["theme", "engine", "way_in", "tone"],
            "properties": {"theme": {"type": "string"}, "engine": {"type": "string"}, "way_in": {"type": "string"},
                           "tone": {"type": "string", "enum": list(TONES)}}}
    return {"type": "object", "additionalProperties": False, "required": ["ideas"],
            "properties": {"ideas": {"type": "array", "description": "exactly 10", "items": idea}}}


def draft_schema(n: int) -> dict[str, Any]:
    sec = {"type": "object", "additionalProperties": False, "required": list(SECTIONS),
           "properties": {s: {"type": "number"} for s in SECTIONS}}
    cand = {"type": "object", "additionalProperties": False,
            "required": ["idea", "handle", "role", "card", "engine", "sections", "pace", "moods", "never_moods",
                         "rival", "closest", "difference"],
            "properties": {"idea": {"type": "integer"}, "handle": {"type": "string"}, "role": {"type": "string"},
                           "card": {"type": "string"}, "engine": {"type": "string"}, "sections": sec,
                           "pace": {"type": "string", "enum": list(PACE)},
                           "moods": {"type": "array", "description": "5 to 8",
                                     "items": {"type": "string", "enum": list(MOOD_NAMES)}},
                           "never_moods": {"type": "array", "description": "0 to 4",
                                           "items": {"type": "string", "enum": list(MOOD_NAMES)}},
                           "rival": {"type": "string"},
                           "closest": {"type": "string"}, "difference": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["candidates"],
            "properties": {"candidates": {"type": "array", "description": f"exactly {n}", "items": cand}}}


def check_schema(n: int) -> dict[str, Any]:
    item = {"type": "object", "additionalProperties": False,
            "required": ["handle", "closest", "overlap", "reason", "problems"],
            "properties": {"handle": {"type": "string"}, "closest": {"type": "string"},
                           "overlap": {"type": "integer"}, "reason": {"type": "string"},
                           "problems": {"type": "array", "items": {"type": "string"}}}}
    return {"type": "object", "additionalProperties": False, "required": ["reviews"],
            "properties": {"reviews": {"type": "array", "description": f"exactly {n}, in order", "items": item}}}


def idea_line(i: dict[str, Any]) -> str:
    return f"{i['theme']} Engine: {i['engine']} (way in: {i['way_in']}; tone: {i['tone']})"


def roster_text(known: dict[str, dict[str, Any]], status: dict[str, str]) -> str:
    label = {"active": "around", "away": "away", "gone": "left the forum", "bench": "not joined yet"}
    return "\n\n".join(f"{h} ({label.get(status.get(h, 'bench'), 'not joined yet')}): {p['role']}\n{p['card']}"
                       for h, p in known.items())


# ── the newcomer ─────────────────────────────────────────────────────────────

def generate(llm: LLM, d: date, cast: dict[str, dict[str, Any]], retired: list[dict[str, Any]],
             status: dict[str, str], past_ideas: list[dict[str, Any]], seed: int) -> tuple[dict[str, Any] | None,
                                                                                         list[dict[str, Any]], str]:
    """Make one newcomer for day `d`. Returns (the persona or None, every idea proposed, a note for the report).

    `cast` holds every persona that is or was a member (or waits to be one), `retired` ones that stay taken
    without joining, `status` each member's roster status. Never raises LLMError.
    """
    rng = random.Random(f"{seed}:persona:{d.isoformat()}")
    known = dict(cast)
    for p in retired:
        if p.get("handle") and p["handle"] not in known:
            known[p["handle"]] = {"role": p.get("role", ""), "card": p.get("card", ""), "retired": True}
    around = [h for h, s in status.items() if s == "active" and h in cast]
    tone = rng.choices(list(TONES), weights=list(TONES.values()))[0]
    roster = roster_text(known, status)
    members_only = roster_text({h: p for h, p in known.items() if not p.get("retired")}, status)
    proposed: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    try:
        for attempt in range(1, ROUNDS + 1):
            before = (past_ideas + proposed)[-(PAST_IDEAS + len(proposed)):]
            user = f"Every member that has ever existed\n<data>\n{roster}\n</data>"
            if before:
                user += ("\n\nIdeas proposed before (never propose these or close variations)\n<data>\n"
                         + "\n".join(f"- {idea_line(i)}" for i in before) + "\n</data>")
            ideas = [i for i in llm.call("persona_ideas", (PROMPTS / "forum_ideas.md").read_text(encoding="utf-8"),
                                         user, ideas_schema()).get("ideas") or []
                     if all(i.get(k) for k in ("theme", "engine", "way_in", "tone"))]
            proposed += [{**i, "date": d.isoformat()} for i in ideas]
            pool = [i for i in ideas if i["tone"] == tone]
            rest = [i for i in ideas if i["tone"] != tone]
            picks = rng.sample(pool, min(3, len(pool))) + rng.sample(rest, min(len(rest), max(0, 3 - len(pool))))
            if not picks:
                continue
            idea_text = "\n".join(f"{n}. {idea_line(i)}" for n, i in enumerate(picks, 1))
            user = (f"Today is {d.day} {d:%B %Y}.\n\nEvery member that has ever existed\n<data>\n{roster}\n</data>"
                    f"\n\nAround today (possible rivals): {', '.join(around)}\n\nIdeas, one per candidate\n{idea_text}")
            user += "\n\nMoods to choose from\n" + "\n".join(f"- {m}" for m in MOODS)
            if rejects:
                user += ("\n\nAlready drafted and rejected as too close to existing members; don't draft these again\n"
                         "<data>\n" + "\n".join(f"- {r['handle']}: {r['role']}" for r in rejects) + "\n</data>")
            cands = llm.call("persona_draft", (PROMPTS / "forum_persona.md").read_text(encoding="utf-8"), user,
                             draft_schema(len(picks))).get("candidates") or []
            cands = [c for c in cands if isinstance(c, dict) and c.get("handle") and c.get("card")][:len(picks)]
            for c in cands:
                c["code"] = code_check(c, known, around)
            listing = "\n\n".join(f"{c.get('handle', '')}: {c.get('role', '')}\n{c.get('card', '')}" for c in cands)
            review = llm.call("persona_check", (PROMPTS / "forum_check.md").read_text(encoding="utf-8"),
                              f"Existing members\n<data>\n{members_only}\n</data>\n\nCandidates\n<data>\n{listing}"
                              "\n</data>", check_schema(len(cands))) if cands else {}
            revs = review.get("reviews") or []
            by = {r.get("handle"): r for r in revs}
            for i, c in enumerate(cands):     # by handle, or by position if the judge spelled it differently
                c["review"] = by.get(c.get("handle")) or (revs[i] if len(revs) == len(cands) else
                                                         {"closest": "", "overlap": 5, "reason": "not reviewed",
                                                          "problems": ["not reviewed"]})
            rounds.append({"picked": picks, "candidates": cands})
            ok = [c for c in cands if not c["code"] and not c["review"].get("problems")
                  and int(c["review"].get("overlap", 5)) <= 2]
            if ok:
                chosen = min(ok, key=lambda c: (int(c["review"]["overlap"]), cands.index(c)))
                return _persona(chosen, picks, rounds, tone, d, cast, around, rng), proposed, (
                    f"{chosen['handle']} ({chosen['role']}; {tone}) after {attempt} round(s)")
            rejects += cands
    except LLMError as exc:
        return None, proposed, f"failed: {exc}"
    return None, proposed, f"no candidate passed after {ROUNDS} rounds"


def _persona(c: dict[str, Any], picks: list[dict[str, Any]], rounds: list[dict[str, Any]], tone: str, d: date,
             cast: dict[str, dict[str, Any]], around: list[str], rng: random.Random) -> dict[str, Any]:
    idea = picks[max(0, min(len(picks) - 1, int(c.get("idea", 1)) - 1))]
    used = [cast[h].get("color") for h in around if h in cast]
    color = min(COLORS, key=lambda x: (used.count(x), rng.random()))
    others = []
    for r in rounds:
        for x in r["candidates"]:
            if x is c:
                continue
            rv = x["review"]
            why = ("code check: " + "; ".join(x["code"]) if x["code"] else
                   "flagged: " + ", ".join(rv.get("problems") or []) if rv.get("problems") else
                   f"overlap {rv.get('overlap')} with {rv.get('closest')}")
            others.append({"handle": x.get("handle", ""), "role": x.get("role", ""), "why": why})
    return {"handle": c["handle"], "date": d.isoformat(), "role": c["role"], "card": c["card"],
            "engine": c.get("engine", ""), "sections": {s: float(c["sections"].get(s, 0)) for s in SECTIONS},
            "pace": c["pace"], "moods": mood_names(c.get("moods"), 8),
            "never_moods": mood_names(c.get("never_moods"), 4, mood_names(c.get("moods"), 8)),
            "rival": c.get("rival", ""), "color": color, "tone": tone,
            "idea": {k: idea.get(k) for k in ("theme", "engine", "way_in", "tone")},
            "closest": c.get("closest", ""), "difference": c.get("difference", ""),
            "review": {k: c["review"].get(k) for k in ("closest", "overlap", "reason")},
            "rounds": len(rounds), "other_candidates": others}
