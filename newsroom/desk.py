"""The newsroom's Claude tasks: triage, editor and the writers. Prompts live in prompts/*.md.

Each function builds the prompt and the JSON schema, makes one structured call through `llm.LLM`,
and returns plain dicts. Fetched text only ever goes in as data (inside <data>), and no call has tools.
"""

from __future__ import annotations

import json
from typing import Any

from . import ROOT
from .llm import LLM

PROMPTS = ROOT / "prompts"
SECTIONS = ["ai", "tech", "gaming"]
PLATFORMS = ["pc", "ps5", "xbox", "switch", "switch2"]
VERDICTS = ["buy", "wait", "skip"]


def system_prompt(task: str, **values: Any) -> str:
    text = (PROMPTS / "style.md").read_text(encoding="utf-8") + "\n\n" + (PROMPTS / f"{task}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def data_block(obj: Any, intro: str = "Today's material:") -> str:
    return f"{intro}\n<data>\n{json.dumps(obj, ensure_ascii=False, indent=1)}\n</data>"


def obj(props: dict[str, Any]) -> dict[str, Any]:
    """A strict object schema: every property required, nothing extra."""
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


STR = {"type": "string"}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}


# ── triage (Haiku) ───────────────────────────────────────────────────────────

TRIAGE_SCHEMA = obj({"items": arr(obj({
    "id": STR, "keep": BOOL, "section": {"type": "string", "enum": SECTIONS}, "kicker": STR,
    "newsworthiness": NUM, "event": STR, "title_en": STR,
}))})


def triage(llm: LLM, cfg: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system = system_prompt("triage", interests=cfg.get("interests", "").strip())
    out = llm.call("triage", system, data_block(candidates, "Candidates to triage:"), TRIAGE_SCHEMA)
    return out.get("items", [])


# ── editor (Opus) ────────────────────────────────────────────────────────────

EDITOR_SCHEMA = obj({
    "lead": STR,
    "featured": arr(obj({"event": STR, "source_ids": arr(STR), "angle": STR, "breaking": BOOL})),
    "medium": arr(obj({"event": STR, "source_ids": arr(STR), "angle": STR})),
    "briefs": arr(obj({"event": STR, "source_id": STR})),
})


def editor(llm: LLM, cfg: dict[str, Any], events: list[dict[str, Any]], recent: list[dict[str, Any]],
           limits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    t = limits
    system = system_prompt(
        "editor", interests=cfg.get("interests", "").strip(),
        featured_min=t["featured"]["min"], featured_max=t["featured"]["max"],
        featured_bar=t["featured"].get("min_newsworthiness", 4.5),
        medium_min=t["medium"]["min"], medium_max=t["medium"]["max"],
        medium_bar=t["medium"].get("min_newsworthiness", 3.5),
        briefs_min=t["briefs"]["min"], briefs_max=t["briefs"]["max"],
        briefs_bar=t["briefs"].get("min_newsworthiness", 2.5),
        max_sources=t["featured"].get("max_sources", 3),
    )
    return llm.call("editor", system, data_block({"events": events, "recent_editions": recent}), EDITOR_SCHEMA)


# ── writers (Opus) ───────────────────────────────────────────────────────────

FEATURED_SCHEMA = obj({
    "headline": STR, "dek": STR, "kicker": STR, "body": STR, "key_points": arr(STR),
    "why_it_matters": STR, "cover_figure": STR, "cover_caption": STR,
})
MEDIUM_SCHEMA = obj({"headline": STR, "dek": STR, "kicker": STR, "body": STR, "key_points": arr(STR)})
BRIEFS_SCHEMA = obj({"items": arr(obj({"id": STR, "headline": STR, "body": STR, "kicker": STR}))})


def write_story(llm: LLM, cfg: dict[str, Any], tier: str, assignment: dict[str, Any]) -> dict[str, Any]:
    words = (cfg.get("edition") or {}).get(tier, {}).get("words", 350 if tier == "featured" else 130)
    schema = FEATURED_SCHEMA if tier == "featured" else MEDIUM_SCHEMA
    system = system_prompt(tier, words=words)
    return llm.call(tier, system, data_block(assignment, "The assignment and its sources:"), schema)


def write_briefs(llm: LLM, cfg: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = (cfg.get("edition") or {}).get("briefs", {}).get("words", 35)
    system = system_prompt("briefs", words=words)
    return llm.call("briefs", system, data_block(items, "Items for the briefs column:"), BRIEFS_SCHEMA).get("items", [])


GAMING_SCHEMA = obj({
    "new_on_pc": arr(obj({"appid": {"type": "integer"}, "blurb": STR})),
    "reviews": arr(obj({"id": STR, "verdict": STR})),
    "watch": arr(obj({"url": STR, "blurb": STR})),
    "news": arr(obj({"id": STR, "headline": STR, "summary": STR})),
    "console_spotlight": arr(obj({"ids": arr(STR), "game": STR,
                                  "platforms": arr({"type": "string", "enum": PLATFORMS}),
                                  "headline": STR, "summary": STR})),
})


def write_gaming(llm: LLM, cfg: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    g = cfg.get("gaming") or {}
    spot = g.get("console_spotlight") or {}
    system = system_prompt("gaming", news_max=(g.get("news") or {}).get("max", 6),
                           spotlight_max=spot.get("max", 3), spotlight_bar=spot.get("min_notability", 4.5))
    return llm.call("gaming", system, data_block(material, "Gaming material:"), GAMING_SCHEMA)


DEALS_SCHEMA = obj({
    "featured": arr(obj({"id": STR, "headline": STR, "body": STR,
                         "verdict": {"type": "string", "enum": VERDICTS}})),
    "more": arr(obj({"id": STR, "advice": STR, "verdict": {"type": "string", "enum": VERDICTS}})),
})


def write_deals(llm: LLM, cfg: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    d = cfg.get("deals") or {}
    f = d.get("featured") or {}
    system = system_prompt("deals", featured_min=f.get("min", 1), featured_max=f.get("max", 2))
    return llm.call("deals", system, data_block(material, "Today's deals:"), DEALS_SCHEMA)


# ── opinion column: the opinion editor (Opus) picks, the columnist (Fable) writes ──

COLUMN_FORMATS = {
    "argument": "Take a clear position on the biggest thread of the period and defend it.",
    "counterpoint": "Take a widely held view, a company's claim or an argument in the news, and argue "
                    "against it, fairly.",
    "advice": "What the news means for the reader's money, hardware or games: buy, wait, upgrade or "
              "skip, and why.",
    "long_view": "Put a current story in its history: what happened the last time something like it "
                 "happened, and what that suggests now.",
}
COLUMN_FOCUS = {
    "ai": "AI",
    "tech": "Tech",
    "gaming": "Gaming",
    "cross": "a topic that spans sections, e.g. AI demand driving PC hardware prices",
}


def pick_opinion(llm: LLM, cfg: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    """material: stories, earlier_columns, allowed_formats, allowed_focus (the rotation, decided in code)."""
    schema = obj({
        "topic": STR, "focus": {"type": "string", "enum": material["allowed_focus"]},
        "format": {"type": "string", "enum": material["allowed_formats"]},
        "thesis": STR, "story_ids": arr(STR),
    })
    o = cfg.get("opinion") or {}
    system = system_prompt("opinion_pick", interests=cfg.get("interests", "").strip(),
                           lookback_days=o.get("lookback_days", 14))
    return llm.call("opinion_pick", system, data_block(material, "Recent stories and the rotation:"), schema)


OPINION_SCHEMA = obj({"headline": STR, "dek": STR, "body": STR, "pull_quote": STR})


def write_opinion(llm: LLM, cfg: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    words = (cfg.get("opinion") or {}).get("words", 800)
    system = system_prompt("opinion", words=words)
    return llm.call("opinion", system, data_block(assignment, "The assignment and the reporting:"), OPINION_SCHEMA)


CHECK_SCHEMA = obj({
    "verdict": {"type": "string", "enum": ["ok", "fixed", "reject"]},
    "fixes": arr(obj({"sentence": STR, "problem": STR, "replacement": STR})),
})


def check_opinion(llm: LLM, cfg: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    """The copy desk: material is {column: {headline, dek, body}, stories: [what the columnist had]}."""
    return llm.call("opinion_check", system_prompt("opinion_check"),
                    data_block(material, "The column and the stories it was written from:"), CHECK_SCHEMA)
