"""Rule-based sorting of candidates, used by every mode: section, junk filter, clustering, score.

In AI modes this only pre-sorts what triage sees; in the links edition it is the whole editor.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .sources import Item
from .text import canonical_url, similarity, words

AI_TITLE = re.compile(
    r"\b(AI|A\.I\.|AGI|LLMs?|GPT[-\s]?\d[\w.]*|ChatGPT|OpenAI|Anthropic|Claude|Gemini|DeepMind|Copilot|"
    r"Llama|Mistral|Qwen|DeepSeek|Grok|xAI|Hugging\s?Face|machine learning|deep learning|neural "
    r"(?:net\w*)|chatbots?|generative|gen-?AI|diffusion models?|language models?|reasoning models?|"
    r"agentic|AI agents?|model weights|fine-?tun\w+|inference)\b",
    re.I,
)
AI_CATEGORIES = {"ai", "artificial intelligence"}
AI_PATHS = ("/ai-platforms-assistants/", "/artificial-intelligence/", "/ai/")

# Never worth a slot: shopping, daily puzzles, "how to watch".
JUNK = re.compile(
    r"\b(wordle|quordle|connections|strands|crossword|mini crossword)\b.{0,40}\b(hints?|answers?|clues?)\b"
    r"|\b(today'?s|daily)\s+(hints?|answers?)\b|\bhow to watch\b|\bpromo codes?\b|\bcoupons?\b"
    r"|\bdiscount codes?\b|\b(black friday|cyber monday|prime day|boxing day)\b|\bdeals? (of|for) the\b"
    r"|\bbest\b.{0,40}\bdeals?\b|\bdeals? on\b|\b\d{2}% off\b|\bsave (up to )?[$£€]\s?\d|\bsponsored\b"
    r"|\bslash(es|ed)\b.{0,40}\boff\b|\bsnag\b|\b(for )?(only|just) [$£€]\s?\d|[$£€]\s?\d+ off\b"
    r"|\bon sale\b|\b(lowest|record[- ]low) price\b|\ball[- ]time low\b|\bbargain\b|\bdeal alert\b"
    r"|\bwith this (deal|discount|coupon)\b|\bgrab\b.{0,60}\b(discount|deal)\b",
    re.I,
)
# Allowed, but rarely news: buying guides, comparisons, how-tos, game guides.
WEAK = re.compile(
    r"^(the )?(\d+ )?best\b|^the (top|best) \d+|\bbest .{0,40}\b(for|in|of) 20\d\d\b|\b\w+ vs\.? \w+"
    r"|^how to\b|\bhow to (get|find|unlock|beat|fix|use|set up)\b|\bguide\b|\bwalkthrough\b"
    r"|\bwhere to (find|buy)\b|\btier list\b|\bbest (build|loadout|settings|weapons?|perks?)\b"
    r"|\bcodes\b|\b(i|we) tried\b|\bquiz\b|\b\d+ (fixes|tips|tricks|ways|things|reasons|settings)\b",
    re.I,
)
HARDWARE_PATH = re.compile(r"/hardware/|/pc-components/|/gpus?/|/cpus?/", re.I)
GAMING_PATH = re.compile(r"/gaming/|/video-games/", re.I)      # game coverage on tech sites
PRODUCT_REVIEW = re.compile(r"\breview\b|\bhands-on\b|\btested\b", re.I)


@dataclass
class Candidate:
    item: Item
    section: str
    score: float = 0.0
    hn: dict[str, Any] | None = None
    also: list[Item] = field(default_factory=list)
    words: set[str] = field(default_factory=set)
    weak: bool = False
    product_review: bool = False

    @property
    def url(self) -> str:
        return self.item.url


def section_for(item: Item) -> str | None:
    """Pick one section from the item's allowed list, or None to drop it."""
    allowed = item.sections or ["tech"]
    if item.kind in ("review", "video"):
        return "gaming"
    if "ai" in allowed and is_ai(item):
        return "ai"
    if allowed[0] != "gaming" and GAMING_PATH.search(item.url):
        return "gaming"
    if allowed[0] == "gaming":
        # PC Gamer covers hardware too; send that to Tech when Tech is allowed
        return "tech" if "tech" in allowed and HARDWARE_PATH.search(item.url) else "gaming"
    if "tech" in allowed:
        return "tech"
    return allowed[0]


def is_ai(item: Item) -> bool:
    if item.categories and item.categories[0].lower() in AI_CATEGORIES:
        return True
    if any(p in item.url.lower() for p in AI_PATHS):
        return True
    return bool(AI_TITLE.search(item.title))


def is_junk(title: str) -> bool:
    return bool(JUNK.search(title))


def hn_item(story: dict[str, Any]) -> Item:
    """A front-page HN story as a candidate (for stories no feed carried)."""
    created = dt.datetime.fromisoformat(story["created_at"].replace("Z", "+00:00")) if story.get("created_at") else None
    return Item(source="Hacker News", title=story["title"], url=story["url"], published_at=created,
                sections=["ai", "tech"], weight=0.85)


def build_candidates(items: list[Item], hn: list[dict[str, Any]], now: dt.datetime,
                     max_age_hours: float = 36, min_points: int = 100, half_life_hours: float = 12,
                     kinds: tuple[str, ...] = ("news",)) -> list[Candidate]:
    """Filter, assign sections, merge duplicates and score. Highest score first."""
    hn_by_url = {canonical_url(s["url"]): s for s in hn if not s.get("self_post")}
    pool = list(items)
    feed_urls = {canonical_url(i.url) for i in items}
    for s in hn:
        if s["points"] >= min_points and canonical_url(s["url"]) not in feed_urls:
            pool.append(hn_item(s))

    cands: list[Candidate] = []
    seen_urls: set[str] = set()
    for it in pool:
        if it.kind not in kinds or is_junk(it.title):
            continue
        if it.published_at and (now - it.published_at).total_seconds() > max_age_hours * 3600:
            continue
        key = canonical_url(it.url)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        sec = section_for(it)
        if not sec:
            continue
        c = Candidate(item=it, section=sec, words=words(it.title), weak=bool(WEAK.search(it.title)),
                      product_review=sec == "tech" and bool(PRODUCT_REVIEW.search(it.title)))
        story = hn_by_url.get(key)
        if story:
            c.hn = {"url": story["comments_url"], "points": story["points"], "comments": story["comments"]}
        cands.append(c)

    clusters = _cluster(cands)
    for c in clusters:
        c.score = _score(c, now, half_life_hours)
    clusters.sort(key=lambda c: -c.score)
    return clusters


def _cluster(cands: list[Candidate], threshold: float = 0.6, min_shared: int = 3) -> list[Candidate]:
    """Merge candidates whose headlines describe the same event; keep the best-weighted one."""
    cands = sorted(cands, key=lambda c: (-c.item.weight, -(c.hn or {}).get("points", 0)))
    kept: list[Candidate] = []
    for c in cands:
        for k in kept:
            if (k.section == c.section and len(k.words & c.words) >= min_shared
                    and similarity(k.words, c.words) >= threshold):
                k.also.append(c.item)
                if c.hn and not k.hn:
                    k.hn = c.hn
                break
        else:
            kept.append(c)
    return kept


def _score(c: Candidate, now: dt.datetime, half_life: float) -> float:
    ts = c.item.published_at
    age_h = max(0.0, (now - ts).total_seconds() / 3600) if ts else 24.0
    recency = 0.5 ** (age_h / half_life)
    s = c.item.weight * (0.35 + 0.65 * recency)
    if c.hn:
        s += min(0.6, 0.15 * math.log10(max(10, c.hn["points"])))
    s += min(0.4, 0.2 * len({i.source for i in c.also} - {c.item.source}))
    if c.weak:
        s -= 0.35
    if c.product_review:                  # gadget reviews: fine, but not ahead of news
        s -= 0.2
    return round(s, 4)
