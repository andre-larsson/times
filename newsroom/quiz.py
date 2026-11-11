"""The news quiz, twice a week: multiple-choice questions on the news since the last quiz.

Two calls. The quiz editor (`quiz`, Opus) reads the headlines, deks, key points and brief summaries of
the editions since the last quiz (at most `quiz.lookback_days`) and writes questions, each tied to one
story. The copy desk (`quiz_check`, Opus) checks every question against its story's full text: the
marked answer must be right, every wrong answer wrong, and the question must have only one reading.
Questions it doesn't pass are dropped; with fewer than `quiz.min_questions` left, there's no quiz.

The code, not Claude, places the right answer among the options (positions spread evenly and shuffled
with a seed from the edition id, so a re-render never moves them), makes sure there are three distinct
wrong answers, and caps the questions per section.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import re
from dataclasses import dataclass
from typing import Any

from . import desk, schedule
from .llm import LLM, LLMError
from .opinion import edition_date, material, reading, reporting

OPTIONS = 4
SECTION_WORDS = {"ai": "AI", "tech": "tech", "gaming": "gaming"}
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
KINDS = {"who", "what", "change", "why", "number"}


@dataclass
class Outcome:
    quiz: dict[str, Any] | None = None
    note: str = ""                # why no quiz was written, when one was due


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("quiz") or {}


def is_due(cfg: dict[str, Any], day: dt.date, last: dt.date | None) -> bool:
    q = settings(cfg)
    return bool(q.get("enabled", True)) and schedule.weekly_due(day, q.get("days", ["tue", "sat"]),
                                                                int(q.get("every_weeks", 1)), last)


def history(editions: list[dict[str, Any]], exclude: str = "") -> list[dict[str, Any]]:
    """Earlier quizzes, newest first: their date and questions."""
    return [{"date": ed["edition_id"][:10], "questions": [q["question"] for q in ed["quiz"].get("questions", [])]}
            for ed in sorted(editions, key=lambda e: e["edition_id"], reverse=True)
            if ed.get("quiz") and ed["edition_id"] != exclude]


def window(day: dt.date, last: dt.date | None, cap: int) -> int:
    """Days of news the quiz covers, today included: those since the last quiz, at most `cap`."""
    return cap if last is None else max(1, min(cap, (day - last).days))


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split())


def clean(q: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """A question from the quiz editor in a checkable shape, or None when it can't be used."""
    question, answer = _norm(q.get("question")), _norm(q.get("answer"))
    wrong = [_norm(w) for w in q.get("wrong_answers") or []]
    notes = [_norm(w) for w in q.get("wrong_explanations") or []]
    if q.get("story_id") not in index or not question or not answer or len(wrong) != OPTIONS - 1:
        return None
    if not all(wrong) or len({o.casefold() for o in (answer, *wrong)}) != OPTIONS:
        return None
    if q.get("kind") not in KINDS or len(notes) != OPTIONS - 1 or not all(notes) or not _norm(q.get("explanation")):
        return None
    # Don't let an exact-figure question evade the numerical cap through a mislabeled kind.
    numeric = all(re.match(r"^[€$£]?\d", o) for o in (answer, *wrong))
    return {"story_id": q["story_id"], "question": question, "answer": answer, "wrong_answers": wrong,
            "kind": "number" if numeric else q["kind"], "wrong_explanations": notes,
            "explanation": _norm(q.get("explanation"))}


def place_answers(drafts: list[dict[str, Any]], seed: str) -> list[tuple[list[str], int]]:
    """(options, index of the right one) per question. The right answer's position is spread evenly
    over A–D and shuffled, so it never settles into a pattern."""
    rng = random.Random(seed)
    slots = (list(range(OPTIONS)) * math.ceil(len(drafts) / OPTIONS))[:len(drafts)]
    rng.shuffle(slots)
    out = []
    for d, slot in zip(drafts, slots):
        options = list(d["wrong_answers"])
        rng.shuffle(options)
        options.insert(slot, d["answer"])
        out.append((options, slot))
    return out


def period(start: dt.date, end: dt.date) -> str:
    """'7 November', '4–7 November', '30 October – 2 November'."""
    if start == end:
        return f"{end.day} {end:%B}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%B}"
    return f"{start.day} {start:%B} – {end.day} {end:%B}"


def _topics(sections: list[str]) -> str:
    words = [SECTION_WORDS[s] for s in SECTION_WORDS if s in sections]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def write(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], editions: list[dict[str, Any]],
          force: bool = False) -> Outcome:
    """Write the quiz for `edition` if one is due (or forced). Never raises LLMError."""
    q = settings(cfg)
    hist = history(editions, exclude=edition["edition_id"])
    day = edition_date(edition)
    last = dt.date.fromisoformat(hist[0]["date"]) if hist else None
    if not force and not is_due(cfg, day, last):
        return Outcome()
    days = window(day, last, int(q.get("lookback_days", 7)))
    rows, index = material(editions, edition, days, detail=True)
    wanted, least = int(q.get("questions", 8)), int(q.get("min_questions", 5))
    if len(rows) < wanted:
        return Outcome(note="too little news since the last quiz")
    dates = {r["date"] for r in rows}
    try:
        out = desk.write_quiz(llm, cfg, {
            "today": day.isoformat(), "questions_wanted": wanted,
            "max_per_day": max(2, math.ceil(wanted / len(dates)) + 1),        # 8 questions over 4 days: 3
            "earlier_questions": [x for h in hist[:2] for x in h["questions"]],
            "stories": rows,
        })
        drafts = [d for d in (clean(x, index) for x in out.get("questions") or []) if d][:wanted]
        if len(drafts) < least:
            return Outcome(note=f"the quiz editor returned {len(drafts)} usable questions")
        check = desk.check_quiz(llm, cfg, {
            "questions": [{"n": i, **d} for i, d in enumerate(drafts, 1)],
            "stories": {sid: reporting(index[sid]) for sid in dict.fromkeys(d["story_id"] for d in drafts)},
        })
    except LLMError as exc:                          # includes a failed check: no unchecked questions
        return Outcome(note=str(exc))

    results = {r.get("n"): r for r in check.get("results") or []}
    cap = int(q.get("max_per_section", 4))
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    per_section: dict[str, int] = {}
    per_kind: dict[str, int] = {}
    for i, d in enumerate(drafts, 1):
        r = results.get(i) or {"verdict": "drop", "problem": "not checked"}
        section = reading(index[d["story_id"]])["section"]
        problem = "" if r.get("verdict") == "ok" else (r.get("problem") or "failed the check")
        if not problem and per_section.get(section, 0) >= cap:
            problem = f"more than {cap} {section} questions"
        kind_cap = 2 if d["kind"] == "number" else math.ceil(wanted / 2)
        if not problem and per_kind.get(d["kind"], 0) >= kind_cap:
            problem = f"too many {d['kind']} questions"
        if problem:
            dropped.append({"question": d["question"], "answer": d["answer"], "problem": problem})
            continue
        per_section[section] = per_section.get(section, 0) + 1
        per_kind[d["kind"]] = per_kind.get(d["kind"], 0) + 1
        kept.append({**d, "section": section})
    if len(kept) < least:
        return Outcome(note=f"only {len(kept)} questions passed the check (needs {least})")
    if len(per_kind) < 3 or max(per_kind.values()) > math.ceil(len(kept) / 2):
        return Outcome(note="not enough variety after the check")

    questions = [{"question": d["question"], "kind": d["kind"], "options": options, "answer": right,
                  "option_notes": [dict(zip(d["wrong_answers"], d["wrong_explanations"])).get(o, "") for o in options],
                  "explanation": d["explanation"],
                  "section": d["section"], "story": reading(index[d["story_id"]])}
                 for d, (options, right) in zip(kept, place_answers(kept, edition["edition_id"]))]
    n = len(questions)
    count = NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)
    start = day - dt.timedelta(days=days - 1)
    quiz = {
        "kicker": "Quiz", "headline": f"The {day:%A} quiz",
        "dek": f"{count.capitalize()} questions on {_topics([x['section'] for x in questions])} news from "
               f"{period(start, day)}. How much do you remember?",
        "period": {"start": start.isoformat(), "end": day.isoformat()},
        "model": llm.model_for("quiz"),
        "checked": {"model": llm.model_for("quiz_check"), "dropped": dropped},
        "questions": questions,
    }
    return Outcome(quiz)
