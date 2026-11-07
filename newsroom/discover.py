"""Discovery (PLAN.md, phase 5): Opus searches the web for important stories the feeds missed.

One Claude call with the API's web search and web fetch tools (Anthropic runs them) and a strict
`report` tool that carries the finds back. Search results and pages are untrusted material: the prompt
treats them as data, and a find is kept only if its address is one the tools actually returned (no
made-up links) and the feeds don't already have the story. API backend only.

Not part of the edition yet: `python -m newsroom discover` (and the "Measure discovery" workflow)
measures what each depth costs and finds, without publishing anything.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import ROOT, rank, store
from . import seen as seen_store
from .desk import STR, arr, data_block, obj
from .http import Client
from .llm import LLM, Call, LLMError, Tally
from .sources import fetch_all
from .text import canonical_url, similarity, words

SECTIONS = ["ai", "tech", "gaming"]
DEPTHS: dict[str, dict[str, int]] = {      # per run: searches, page fetches, the most finds to keep
    "light":  {"searches": 3,  "fetches": 3,  "finds": 4},
    "normal": {"searches": 6,  "fetches": 5,  "finds": 6},
    "deep":   {"searches": 12, "fetches": 10, "finds": 10},
}
KNOWN_MAX = 120                            # feed headlines shown to the model as "already have"
REPORT_SCHEMA = obj({"finds": arr(obj({
    "title": STR, "url": STR, "source": STR, "published": STR,
    "section": {"type": "string", "enum": SECTIONS}, "summary": STR, "why": STR,
}))})
CLIP = {"title": 200, "url": 500, "source": 80, "published": 10, "summary": 600, "why": 200}


@dataclass
class Discovery:
    depth: str
    settings: dict[str, int]
    finds: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)    # each with a "reason"
    looked_at: dict[str, list] = field(default_factory=dict)       # queries, fetched, results, errors
    call: Call | None = None
    error: str = ""


def depth_settings(cfg: dict[str, Any], depth: str) -> dict[str, int]:
    custom = (cfg.get("search") or {}).get("depths") or {}
    if depth not in DEPTHS and depth not in custom:
        raise ValueError(f"unknown discovery depth {depth!r}")
    return {**DEPTHS.get(depth, {}), **(custom.get(depth) or {})}


def system_prompt(cfg: dict[str, Any], settings: dict[str, int], today: dt.date) -> str:
    text = (ROOT / "prompts" / "discover.md").read_text(encoding="utf-8")
    values = {"date": today.isoformat(), "interests": (cfg.get("interests") or "").strip(), **settings}
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def run(llm: LLM, cfg: dict[str, Any], depth: str, known: list[dict[str, str]], known_urls: set[str],
        now: dt.datetime) -> Discovery:
    """One discovery call at this depth. Raises LLMError if the call fails."""
    s = depth_settings(cfg, depth)
    fetch_tokens = int((cfg.get("search") or {}).get("fetch_tokens", 6000))
    report, looked, call = llm.call_web(
        "discover", system_prompt(cfg, s, now.date()), data_block(known, "Headlines the paper's feeds brought in:"),
        REPORT_SCHEMA, searches=s["searches"], fetches=s["fetches"], fetch_tokens=fetch_tokens)
    finds, dropped = check(report.get("finds") or [], looked, known, known_urls, s["finds"])
    return Discovery(depth, s, finds, dropped, looked, call)


def check(finds: list[dict[str, Any]], looked: dict[str, list], known: list[dict[str, str]],
          known_urls: set[str], limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep finds that link a page the tools returned and that the feeds don't already have."""
    returned = {canonical_url(r["url"]) for r in looked.get("results", []) if r.get("url")}
    returned |= {canonical_url(u.rstrip(".,;:")) for u in looked.get("linked", [])}
    known_words = [words(k.get("title", "")) for k in known]
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for raw in finds:
        f = {k: str(raw.get(k) or "").strip()[:n] for k, n in CLIP.items()}
        f["section"] = raw.get("section") if raw.get("section") in SECTIONS else "tech"
        key = canonical_url(f["url"]) if f["url"].startswith(("https://", "http://")) else ""
        title_words = words(f["title"])
        reason = ""
        if not key:
            reason = "not a web address"
        elif key not in returned:
            reason = "no search, fetched page or link on one has this address"
        elif key in known_urls:
            reason = "the feeds already have this page"
        elif any(similarity(title_words, kw) >= 0.6 and len(title_words & kw) >= 3 for kw in known_words):
            reason = "the feeds already have this story"
        elif any(canonical_url(k["url"]) == key for k in kept):
            reason = "listed twice"
        elif len(kept) >= limit:
            reason = f"over the limit of {limit}"
        if reason:
            dropped.append({**f, "reason": reason})
        else:
            kept.append(f)
    return kept, dropped


# ── measuring ────────────────────────────────────────────────────────────────

def what_we_have(cfg: dict[str, Any], harvest, data_dir: Path, now: dt.datetime) -> tuple[list[dict], set[str]]:
    """The headlines the model is told the paper already has, and every URL to treat as known."""
    search = cfg.get("search") or {}
    hn_cfg = (cfg.get("sources") or {}).get("hackernews") or {}
    cands = rank.build_candidates(harvest.items, harvest.hn, now,
                                  max_age_hours=float(search.get("max_item_age_hours", 36)),
                                  min_points=int(hn_cfg.get("min_points", 100)))
    known = [{"source": c.item.source, "title": c.item.title} for c in cands if not c.weak][:KNOWN_MAX]
    for ed in store.recent_headlines(data_dir, count=2):
        known += [{"source": f"The 403 Times, {ed['edition_id']}", "title": h} for h in ed["headlines"]]
    urls = {canonical_url(i.url) for i in harvest.items} | {canonical_url(c.url) for c in cands}
    urls |= set(seen_store.load(data_dir))
    return known, urls


def measure(cfg: dict[str, Any], data_dir: Path, depths: list[str], runs: int, out: Path | None,
            dry_run: bool = False, now: dt.datetime | None = None, env: dict[str, str] | None = None,
            client: Client | None = None, llm_factory: Callable[..., LLM] = LLM) -> str:
    """Run discovery `runs` times at each depth against today's feeds. Returns a Markdown report."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for d in depths:
        depth_settings(cfg, d)                         # fail fast on a bad depth
    own = client is None
    client = client or Client()
    try:
        harvest = fetch_all(cfg, client, now)
    finally:
        if own:
            client.__exit__(None, None, None)
    known, known_urls = what_we_have(cfg, harvest, data_dir, now)
    user = data_block(known, "Headlines the paper's feeds brought in:")
    lines = [f"## Discovery, {now:%Y-%m-%d %H:%M} UTC", "",
             f"Feeds: {len(harvest.items)} items; {len(known)} headlines sent as already known "
             f"(a list of ~{len(user) // 4:,} tokens).", ""]
    if dry_run:
        s = depth_settings(cfg, depths[0])
        lines += ["Dry run: no Claude call. The system prompt at the first depth:", "", "```",
                  system_prompt(cfg, s, now.date()), "```"]
        return "\n".join(lines)

    per_run = float((cfg.get("budget") or {}).get("per_run_usd", 1.25))
    records = []
    for depth in depths:
        for i in range(runs):
            tally = Tally(per_run_usd=per_run)
            llm = llm_factory(cfg, "api", tally, env)
            try:
                d = run(llm, cfg, depth, known, known_urls, now)
            except LLMError as exc:
                d = Discovery(depth, depth_settings(cfg, depth), call=tally.calls[-1] if tally.calls else None,
                              error=str(exc))
            rec = record(d, now, len(known))
            records.append(rec)
            print("discovery-record: " + json.dumps(rec, ensure_ascii=False), file=sys.stderr)
            lines += describe(d, f"{depth}, run {i + 1}" if runs > 1 else depth)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        with (out / "runs.jsonl").open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        records = [json.loads(line) for line in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    lines += summary(records, "All measurements so far" if out is not None else "This run")
    return "\n".join(lines)


def record(d: Discovery, now: dt.datetime, known: int) -> dict[str, Any]:
    c = d.call
    return {
        "at": now.isoformat(timespec="seconds"), "depth": d.depth, "settings": d.settings, "known": known,
        "ok": not d.error, "error": d.error,
        "model": c.model if c else "", "usd": c.usd if c else 0.0, "seconds": c.seconds if c else 0.0,
        "requests": c.requests if c else 0, "searches": c.web_searches if c else 0,
        "fetches": c.web_fetches if c else 0,
        "tokens": {"input": c.input_tokens, "output": c.output_tokens, "cache_read": c.cache_read,
                   "cache_write": c.cache_write} if c else {},
        "queries": d.looked_at.get("queries", []), "fetched": d.looked_at.get("fetched", []),
        "tool_errors": d.looked_at.get("errors", []), "results": len(d.looked_at.get("results", [])),
        "linked": len(d.looked_at.get("linked", [])),
        "finds": d.finds, "dropped": d.dropped,
    }


def describe(d: Discovery, label: str) -> list[str]:
    s, c = d.settings, d.call
    lines = [f"### {label} (up to {s['searches']} searches, {s['fetches']} fetches, {s['finds']} finds)", ""]
    if c:
        lines.append(f"**${c.usd:.3f}** · {c.web_searches} searches · {c.web_fetches} fetches · "
                     f"{c.requests} requests · {c.input_tokens:,} in / {c.output_tokens:,} out tokens "
                     f"(cache read {c.cache_read:,}) · {c.seconds:.0f} s")
    if d.error:
        lines += ["", f"Failed: {d.error}", ""]
        return lines
    queries = d.looked_at.get("queries", [])
    lines += ["", "Searched: " + ("; ".join(f"“{q}”" for q in queries) or "nothing")]
    if d.looked_at.get("errors"):
        lines.append("Tool errors: " + ", ".join(d.looked_at["errors"]))
    lines += ["", f"Kept {len(d.finds)} of {len(d.finds) + len(d.dropped)}:"]
    lines += [f"- [{f['section']}] **{f['title']}**, {f['source']} ({f['published'] or 'date?'}) <{f['url']}>  \n"
              f"  {f['why']}" for f in d.finds]
    lines += [f"- dropped: {f['title']} ({f['reason']})" for f in d.dropped]
    return lines + [""]


def summary(records: list[dict[str, Any]], title: str) -> list[str]:
    lines = [f"### {title}", "", "| Depth | Runs | Avg cost | Range | Searches | Fetches | Input tokens | Kept |",
             "|---|---|---|---|---|---|---|---|"]
    for depth in dict.fromkeys(r["depth"] for r in records):
        rs = [r for r in records if r["depth"] == depth and r["ok"]]
        failed = sum(1 for r in records if r["depth"] == depth and not r["ok"])
        if not rs:
            lines.append(f"| {depth} | 0 ({failed} failed) | | | | | | |")
            continue
        n = len(rs)
        usd = [r["usd"] for r in rs]
        avg = lambda key: sum(r[key] for r in rs) / n          # noqa: E731
        inp = sum(r["tokens"].get("input", 0) + r["tokens"].get("cache_read", 0) for r in rs) / n
        runs = f"{n}" + (f" (+{failed} failed)" if failed else "")
        lines.append(f"| {depth} | {runs} | ${sum(usd) / n:.3f} | ${min(usd):.3f}–${max(usd):.3f} | "
                     f"{avg('searches'):.1f} | {avg('fetches'):.1f} | {inp:,.0f} | "
                     f"{sum(len(r['finds']) for r in rs) / n:.1f} |")
    return lines + ["", "Cost per month if it ran in every edition: average × 30.4.", ""]
