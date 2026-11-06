"""`python -m newsroom generate`: decide whether an edition is due, pick a mode, build and save it."""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from typing import Callable

from . import ai_edition, budget, opinion, preflight, schedule, store
from . import seen as seen_store
from .http import Client
from .links import build_links_edition
from .llm import LLM, Tally
from .sources import Harvest, fetch_all

MODES = ("auto", "full", "reduced", "links", "skip")
OPINION = ("auto", "force", "off")    # auto = when due (opinion.days / every_weeks) in a full edition
MIN_LINKS_TO_PUBLISH = 5          # below this the sources are probably down: keep the last edition


@dataclass
class Result:
    published: bool
    mode: str
    reason: str
    edition_id: str = ""
    path: Path | None = None
    harvest: Harvest | None = None
    llm: dict[str, Any] | None = None
    column: str = ""                  # the opinion column's headline, or why it wasn't written


def generate(cfg: dict[str, Any], data_dir: Path, requested: str = "auto",
             now: dt.datetime | None = None, env: dict[str, str] | None = None,
             client: Client | None = None, backend: str | None = None,
             llm_factory: Callable[..., LLM] = LLM, column: str = "auto") -> Result:
    if requested not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if column not in OPINION:
        raise ValueError(f"opinion must be one of {', '.join(OPINION)}")
    now = now or dt.datetime.now(dt.timezone.utc)
    env = dict(os.environ) if env is None else env
    sched = cfg["schedule"]
    tz, slots = sched["timezone"], sched["editions"]
    llm_cfg = cfg.get("llm") or {}

    if requested == "auto":
        if not schedule.is_due(now, tz, slots, store.last_generated_at(data_dir)):
            return Result(False, "none", "not due: the latest slot already has an edition")
        slot = schedule.latest_slot(now, tz, slots)
    else:
        slot = schedule.forced_slot(now, tz, slots)
    edition_id = schedule.edition_id(slot, slots)

    backend = backend or env.get("NEWSROOM_LLM") or llm_cfg.get("backend", "api")
    tally = Tally(per_run_usd=float((cfg.get("budget") or {}).get("per_run_usd", 1.25)))
    llm = llm_factory(cfg, backend, tally, env)
    mode, reason = preflight.resolve(requested, cfg, env, llm, budget.load_usage(data_dir), now)
    fallback = llm_cfg.get("when_unavailable", "links")

    if mode == "skip":
        budget.record_run(data_dir, now, edition_id, "skip", backend, tally)
        return Result(False, "skip", reason, edition_id, llm=tally.summary())

    own_client = client is None
    client = client or Client()
    try:
        harvest = fetch_all(cfg, client, now, itad_key=env.get("ITAD_API_KEY") or None)
        previous = store.latest_edition(data_dir)
        if previous and previous.get("edition_id") == edition_id:
            previous = None                  # replacing today's edition: don't dedupe against it
        seen = seen_store.load(data_dir)
        edition = None
        if mode in preflight.AI_MODES:
            try:
                result = ai_edition.build(cfg, harvest, edition_id, mode, llm, client, seen,
                                          store.recent_headlines(data_dir, exclude=edition_id))
                edition = result.edition
                seen_store.mark(seen, result.seen_urls, now)
            except ai_edition.AIUnavailable as exc:
                mode, reason = fallback, f"AI unavailable: {exc}"
        if edition is None and mode == "links":
            edition = build_links_edition(cfg, harvest, edition_id, previous=previous, reason=reason)
        column_note = _opinion(cfg, data_dir, edition, mode, llm, column) if edition else ""
    finally:
        if own_client:
            client.__exit__(None, None, None)

    budget.record_run(data_dir, now, edition_id, edition["mode"] if edition else mode, backend, tally)
    if edition is None:                      # fallback was "skip"
        return Result(False, mode, reason, edition_id, harvest=harvest, llm=tally.summary())
    if edition["mode"] != "links":
        reason = edition.get("reason") or reason
    items = len(edition["stories"]) + len(edition["links"]) + len(edition["hn_top"])
    if items < MIN_LINKS_TO_PUBLISH:
        return Result(False, edition["mode"], "too few items fetched; kept the previous edition", edition_id,
                      harvest=harvest, llm=tally.summary())
    path = store.save_edition(data_dir, edition)
    seen_store.save(data_dir, seen, now)
    return Result(True, edition["mode"], reason, edition_id, path, harvest, tally.summary(), column_note)


def _opinion(cfg: dict[str, Any], data_dir: Path, edition: dict[str, Any], mode: str, llm: LLM,
             requested: str) -> str:
    """Add the opinion column to the edition when one is due. Returns a line for the report."""
    replaced = store.load_edition(data_dir, edition["edition_id"])
    kept = (replaced or {}).get("opinion")
    if kept and requested != "force":                # re-running today: keep today's column, don't pay twice
        kept = dict(kept, slug=opinion.unique_slug(kept["headline"], {s["slug"] for s in edition["stories"]}))
        edition["opinion"] = kept
        return f"kept today's column: {kept['headline']}"
    if requested == "force" and edition["mode"] == "links":
        return "not written: a links edition has no Claude to write it"
    if requested == "off" or edition["mode"] == "links" or (requested == "auto" and mode != "full"):
        return ""
    try:
        outcome = opinion.write(cfg, llm, edition, store.all_editions(data_dir), force=requested == "force")
    except Exception as exc:                         # the column is optional: never lose the edition over it
        outcome = opinion.Outcome(note=f"{type(exc).__name__}: {str(exc)[:200]}")
    edition["llm"] = {"backend": llm.backend, **llm.tally.summary()}
    edition["llm"]["estimated_usd"] = edition["llm"]["equivalent_usd"]
    if outcome.column:
        edition["opinion"] = outcome.column
        return f"written: {outcome.column['headline']}"
    return f"not written: {outcome.note}" if outcome.note else ""


def report(result: Result) -> str:
    """Plain-text summary for the console and the Actions step summary."""
    lines = [f"Edition {result.edition_id or '-'}: {'published' if result.published else 'not published'} "
             f"(mode {result.mode}; {result.reason})"]
    if result.column:
        lines.append(f"Opinion column {result.column}")
    if result.llm and result.llm.get("calls"):
        l = result.llm
        lines.append(f"Claude: {l['calls']} calls, ${l['usd']:.4f} charged, ${l['equivalent_usd']:.4f} API-equivalent"
                     + (f"; stopped: {l['stopped']}" if l.get("stopped") else ""))
        for task, t in l.get("by_task", {}).items():
            lines.append(f"  {task}: {t['calls']} calls, ${t['equivalent_usd']:.4f}"
                         + (f", {t['failed']} failed" if t["failed"] else ""))
    if result.harvest:
        lines.append("")
        lines.append("| Source | Status | Items | ms |")
        lines.append("|---|---|---:|---:|")
        for s in result.harvest.status:
            state = "skipped" if s.skipped else ("ok" if s.ok else "FAILED")
            note = f" — {s.error}" if s.error else ""
            lines.append(f"| {s.name} | {state}{note} | {s.count} | {s.ms} |")
    return "\n".join(lines)


def write_github_outputs(result: Result) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"published={'true' if result.published else 'false'}\n")
            fh.write(f"edition_id={result.edition_id}\n")
            fh.write(f"mode={result.mode}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report(result) + "\n")


def dump_harvest(harvest: Harvest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fetched_at": harvest.fetched_at.isoformat(),
        "items": [i.to_json() for i in harvest.items],
        "hn": harvest.hn, "steam": harvest.steam, "itad": harvest.itad,
        "status": [s.__dict__ for s in harvest.status],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
