"""Weekly follow-ups, grounded in pairs of dated stories already in the paper.

No claim that silence proves an outcome: a later report must explicitly support every update.
The second pass checks both the connection and all three pieces of copy. Failure is optional.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from . import desk, schedule
from .llm import LLM, LLMError
from .opinion import edition_date, material, reading, reporting


@dataclass
class Outcome:
    feature: dict[str, Any] | None = None
    note: str = ""


def write(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], editions: list[dict[str, Any]]) -> Outcome:
    c = cfg.get("checkback") or {}
    day = edition_date(edition)
    earlier = [e for e in editions if e.get("checkback") and e["edition_id"] < edition["edition_id"]]
    used = {tuple(x.get("pair_ids", [])) for e in earlier for x in e["checkback"].get("items", [])}
    last = max((edition_date(e) for e in earlier), default=None)
    if not c.get("enabled", True) or not schedule.weekly_due(day, c.get("days", ["thu"]), 1, last):
        return Outcome()
    rows, index = material(editions, edition, int(c.get("lookback_days", 35)), detail=True)
    cutoff = (day - dt.timedelta(days=7)).isoformat()
    old = [r for r in rows if r["date"] <= cutoff]
    recent = [r for r in rows if r["date"] > cutoff]
    if not old or not recent:
        return Outcome(note="not enough older and later reporting yet")
    # Bound input size. Full reporting is supplied so both writer and checker can assess the outcome.
    offered = old[-60:] + recent[-60:]
    reports = {r["id"]: reporting(index[r["id"]]) for r in offered}
    try:
        draft = llm.call("checkback", desk.system_prompt("checkback"),
                         desk.data_block({"today": day.isoformat(), "older_through": cutoff,
                                          "earlier_pairs": [x.get("pair_ids", []) for e in earlier[-8:]
                                                            for x in e["checkback"].get("items", [])],
                                          "stories": reports}), desk.CHECKBACK_SCHEMA)
        candidates = []
        seen = set()
        for item in draft.get("items") or []:
            a, b = item.get("original_id"), item.get("update_id")
            if a not in reports or b not in reports or a in seen:
                continue
            if (a, b) in used:
                continue
            if not (reports[a]["date"] <= cutoff < reports[b]["date"]):
                continue
            if not all(str(item.get(k) or "").strip() for k in ("headline", "then", "now", "next")):
                continue
            if item.get("status") not in ("updated", "resolved", "still_open"):
                continue
            seen.add(a)
            candidates.append(item)
            if len(candidates) == 3:
                break
        if not candidates:
            return Outcome(note="no supported follow-ups in later reporting")
        checked = llm.call("checkback_check", desk.system_prompt("checkback_check"),
                           desk.data_block({"items": [{"n": i, **x} for i, x in enumerate(candidates, 1)],
                                            "stories": {s: reports[s] for x in candidates
                                                        for s in (x["original_id"], x["update_id"])}}),
                           desk.QUIZ_CHECK_SCHEMA)
    except LLMError as exc:
        return Outcome(note=str(exc))
    # Missing, duplicate or unknown verdicts never grant approval.
    results = checked.get("results") or []
    items = []
    for i, x in enumerate(candidates, 1):
        verdicts = [v.get("verdict") for v in results if v.get("n") == i]
        if verdicts != ["ok"]:
            continue
        items.append({**{k: x[k].strip() for k in ("headline", "then", "now", "next", "status")},
                      "pair_ids": [x["original_id"], x["update_id"]],
                      "original": reading(index[x["original_id"]]), "update": reading(index[x["update_id"]])})
    if not items:
        return Outcome(note="no follow-ups passed the check")
    return Outcome({"headline": "We checked back", "items": items,
                    "model": llm.model_for("checkback"), "checked_by": llm.model_for("checkback_check")})
