"""The pre-run check (PLAN.md, "Run modes and the pre-run check"): which mode this run uses."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import budget
from .llm import LLM, LLMError

AI_MODES = ("full", "reduced")


def resolve(requested: str, cfg: dict[str, Any], env: dict[str, str], llm: LLM,
            usage: dict[str, Any], now: dt.datetime) -> tuple[str, str]:
    """Return (mode, reason). Mode is one of full, reduced, links, skip."""
    fallback = (cfg.get("llm") or {}).get("when_unavailable", "links")
    if requested in ("links", "skip"):
        return requested, f"requested {requested}"

    if llm.backend == "api":
        if not env.get("ANTHROPIC_API_KEY"):
            return fallback, "no ANTHROPIC_API_KEY"
        pace, why = budget.pace_decision(cfg, usage, now)
        if pace == "over":
            return fallback, why
        if requested in AI_MODES:
            mode = requested                       # a forced mode skips pacing, not the monthly cap
        elif pace == "reduced":
            mode = (cfg.get("budget") or {}).get("when_over_pace", "reduced")
        else:
            mode = "full"
    else:
        mode = requested if requested in AI_MODES else "full"
        why = "claude-code backend: Claude subscription, not counted against the budget"

    if mode not in AI_MODES:
        return mode, why
    try:
        llm.probe()
    except LLMError as exc:
        return fallback, f"pre-run check failed: {exc}"
    return mode, why
