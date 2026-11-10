"""`python -m newsroom generate`: decide whether an edition is due, pick a mode, build and save it."""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from typing import Callable

from . import ai_edition, budget, forum, opinion, preflight, quiz, schedule, store
from . import deals as deal_days
from . import screen
from . import seen as seen_store
from .http import Client
from .links import build_links_edition
from .llm import LLM, Tally
from .sources import Harvest, SourceStatus, fetch_all

MODES = ("auto", "full", "reduced", "links", "skip")
OPINION = ("auto", "force", "off")    # auto = when due (opinion.days / every_weeks) in a full edition
QUIZ = ("auto", "force", "off")       # auto = when due (quiz.days / every_weeks) in a full edition
FORUM = ("auto", "force", "off")      # auto = every full edition (forum.enabled)
DEALS = deal_days.MODES               # auto = on deals.days (or the safety net), force = check now, carry = keep the last check
SCREEN = ("auto", "force", "off")     # Screen's picks of the week: auto = when due (screen.picks) in a full edition
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
    quiz: str = ""                    # the quiz's size, or why it wasn't written
    forum: str = ""                   # the Botroom's day, or why it wasn't written
    deals: str = ""                   # whether the deals were checked or carried over
    screen: str = ""                  # Screen's lists and picks, or why there are none


def generate(cfg: dict[str, Any], data_dir: Path, requested: str = "auto",
             now: dt.datetime | None = None, env: dict[str, str] | None = None,
             client: Client | None = None, backend: str | None = None,
             llm_factory: Callable[..., LLM] = LLM, column: str = "auto", quiz_mode: str = "auto",
             forum_mode: str = "auto", deals_mode: str = "auto", screen_mode: str = "auto") -> Result:
    if requested not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if column not in OPINION:
        raise ValueError(f"opinion must be one of {', '.join(OPINION)}")
    if quiz_mode not in QUIZ:
        raise ValueError(f"quiz must be one of {', '.join(QUIZ)}")
    if forum_mode not in FORUM:
        raise ValueError(f"forum must be one of {', '.join(FORUM)}")
    if deals_mode not in DEALS:
        raise ValueError(f"deals must be one of {', '.join(DEALS)}")
    if screen_mode not in SCREEN:
        raise ValueError(f"screen must be one of {', '.join(SCREEN)}")
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
        deals_plan = deal_days.plan(cfg, data_dir, edition_id, now, deals_mode, ai=mode in preflight.AI_MODES)
        harvest = fetch_all(deal_days.fetch_config(cfg, deals_plan.refresh), client, now,
                            itad_key=(env.get("ITAD_API_KEY") or "").strip() or None)
        deals_block, deals_note = deal_days.block_for(cfg, harvest, deals_plan)
        watch = _screen_lists(cfg, data_dir, client, harvest, env, edition_id, mode, screen_mode)
        previous = store.latest_edition(data_dir)
        if previous and previous.get("edition_id") == edition_id:
            previous = None                  # replacing today's edition: don't dedupe against it
        seen = seen_store.load(data_dir)
        edition = None
        if mode in preflight.AI_MODES:
            try:
                result = ai_edition.build(cfg, harvest, edition_id, mode, llm, client, seen,
                                          store.recent_headlines(data_dir, exclude=edition_id), deals=deals_block)
                edition = result.edition
                seen_store.mark(seen, result.seen_urls, now)
            except ai_edition.AIUnavailable as exc:
                mode, reason = fallback, f"AI unavailable: {exc}"
        if edition is None and mode == "links":
            edition = build_links_edition(cfg, harvest, edition_id, previous=previous, reason=reason,
                                          deals=deals_block)
        column_note = _opinion(cfg, data_dir, edition, mode, llm, column) if edition else ""
        quiz_note = _quiz(cfg, data_dir, edition, mode, llm, quiz_mode) if edition else ""
        botroom = _forum(cfg, data_dir, edition, mode, llm, forum_mode) if edition else forum.Outcome()
        screen_note = _screen_picks(cfg, data_dir, edition, watch, mode, llm, screen_mode) if edition else ""
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
    forum.save(data_dir, botroom)
    if watch:
        screen.save_memory(data_dir, watch.memory)
    return Result(True, edition["mode"], reason, edition_id, path, harvest, tally.summary(), column_note, quiz_note,
                  botroom.note, deals_note, screen_note)


def _opinion(cfg: dict[str, Any], data_dir: Path, edition: dict[str, Any], mode: str, llm: LLM,
             requested: str) -> str:
    """Add the opinion column to the edition when one is due. Returns a line for the report."""
    replaced = store.load_edition(data_dir, edition["edition_id"])
    kept = (replaced or {}).get("opinion")
    if kept and requested != "force":                # re-running today: keep today's column, don't pay twice
        kept = dict(kept, slug=opinion.unique_slug(kept["headline"], {s["slug"] for s in edition["stories"]}))
        edition["opinion"] = kept
        return f"kept today's column: {kept['headline']}"
    skip = _skip_extra(edition, mode, requested)
    if skip is not None:
        return skip
    try:
        outcome = opinion.write(cfg, llm, edition, store.all_editions(data_dir), force=requested == "force")
    except Exception as exc:                         # the column is optional: never lose the edition over it
        outcome = opinion.Outcome(note=f"{type(exc).__name__}: {str(exc)[:200]}")
    _record_llm(edition, llm)
    if outcome.column:
        edition["opinion"] = outcome.column
        n = len(outcome.column.get("checked", {}).get("fixes", []))
        return f"written{f' ({n} fact-check fixes)' if n else ''}: {outcome.column['headline']}"
    return f"not written: {outcome.note}" if outcome.note else ""


def _quiz(cfg: dict[str, Any], data_dir: Path, edition: dict[str, Any], mode: str, llm: LLM,
          requested: str) -> str:
    """Add the quiz to the edition when one is due. Returns a line for the report."""
    kept = (store.load_edition(data_dir, edition["edition_id"]) or {}).get("quiz")
    if kept and requested != "force":                # re-running today: keep today's quiz, don't pay twice
        edition["quiz"] = kept
        return f"kept today's quiz ({len(kept['questions'])} questions)"
    skip = _skip_extra(edition, mode, requested)
    if skip is not None:
        return skip
    try:
        outcome = quiz.write(cfg, llm, edition, store.all_editions(data_dir), force=requested == "force")
    except Exception as exc:                         # the quiz is optional: never lose the edition over it
        outcome = quiz.Outcome(note=f"{type(exc).__name__}: {str(exc)[:200]}")
    _record_llm(edition, llm)
    if outcome.quiz:
        edition["quiz"] = outcome.quiz
        n, dropped = len(outcome.quiz["questions"]), len(outcome.quiz["checked"]["dropped"])
        return f"written: {n} questions" + (f" ({dropped} dropped by the check)" if dropped else "")
    return f"not written: {outcome.note}" if outcome.note else ""


def _forum(cfg: dict[str, Any], data_dir: Path, edition: dict[str, Any], mode: str, llm: LLM,
           requested: str) -> forum.Outcome:
    """The Botroom's day for this edition (saved with the edition). Its note is a line for the report."""
    if requested != "force" and forum.load_day(data_dir, edition["edition_id"][:10]):
        return forum.Outcome(note="kept today's Botroom")       # re-running today: don't pay twice
    skip = _skip_extra(edition, mode, requested)
    if skip is not None:
        return forum.Outcome(note=skip)
    if requested == "auto" and not forum.enabled(cfg):
        return forum.Outcome()
    try:
        out = forum.write(cfg, llm, edition, data_dir, store.all_editions(data_dir))
    except Exception as exc:                         # the Botroom is optional: never lose the edition over it
        out = forum.Outcome(note=f"not written: {type(exc).__name__}: {str(exc)[:200]}")
    _record_llm(edition, llm)
    return out


def _screen_lists(cfg: dict[str, Any], data_dir: Path, client: Client, harvest: Harvest, env: dict[str, str],
                  edition_id: str, mode: str, requested: str) -> screen.Fetched | None:
    """Screen's lists for today (TMDB and Netflix's top 10), fetched with the other sources so their status
    lands in the edition. On a picks day it also tags extra titles for Claude to choose from."""
    if not screen.enabled(cfg):
        return None
    day = dt.date.fromisoformat(edition_id[:10])
    try:
        due = requested == "force" or (requested == "auto" and mode == "full" and screen.picks_due(
            cfg, day, screen.last_picked(store.all_editions(data_dir), exclude=edition_id)))
        return screen.fetch(cfg, client, harvest, (env.get("TMDB_API_KEY") or "").strip() or None,
                            screen.load_memory(data_dir), day, want_pool=due)
    except Exception as exc:                         # Screen is optional: never lose the edition over it
        msg = f"{type(exc).__name__}: {exc}".split("?", 1)[0]          # never log query strings (keys)
        harvest.status.append(SourceStatus("Screen", False, error=msg[:200]))
        return None


def _screen_picks(cfg: dict[str, Any], data_dir: Path, edition: dict[str, Any], watch: screen.Fetched | None,
                  mode: str, llm: LLM, requested: str) -> str:
    """Add Screen's lists to the edition, and the picks of the week when they're due. Returns a line for the report."""
    if watch is None:
        return ""
    edition["screen"] = watch.block
    note = screen.summary(watch.block)
    kept = ((store.load_edition(data_dir, edition["edition_id"]) or {}).get("screen") or {}).get("picks")
    if kept and requested != "force":                # re-running today: keep today's picks, don't pay twice
        edition["screen"]["picks"] = kept
        return f"{note}; kept today's picks"
    skip = _skip_extra(edition, mode, requested)
    if skip is not None:
        return f"{note}; picks {skip}" if skip else note
    try:
        out = screen.write_picks(cfg, llm, edition, watch.pool, store.all_editions(data_dir),
                                 force=requested == "force")
    except Exception as exc:                         # the picks are optional: never lose the edition over them
        out = screen.Outcome(note=f"{type(exc).__name__}: {str(exc)[:200]}")
    _record_llm(edition, llm)
    if out.picks:
        edition["screen"]["picks"] = out.picks
        return f"{note}; picks written: {len(out.picks['titles'])} ({out.picks['headline']})"
    return f"{note}; picks not written: {out.note}" if out.note else note


def run_forum(cfg: dict[str, Any], data_dir: Path, edition_id: str | None = None, backend: str | None = None,
              force: bool = False, env: dict[str, str] | None = None,
              llm_factory: Callable[..., LLM] = LLM) -> str:
    """`python -m newsroom forum`: the Botroom for a saved edition (the latest by default), without
    generating anything else. Its cost goes to usage.json like an edition's. Returns a line for the report."""
    env = dict(os.environ) if env is None else env
    edition = store.load_edition(data_dir, edition_id) if edition_id else store.latest_edition(data_dir)
    if not edition:
        return f"Botroom: no edition {edition_id or 'saved yet'}"
    if not force and forum.load_day(data_dir, edition["edition_id"][:10]):
        return f"Botroom {edition['edition_id']}: already written (use --force to replace it)"
    backend = backend or env.get("NEWSROOM_LLM") or (cfg.get("llm") or {}).get("backend", "api")
    tally = Tally(per_run_usd=float((cfg.get("budget") or {}).get("per_run_usd", 1.25)))
    llm = llm_factory(cfg, backend, tally, env)
    out = forum.write(cfg, llm, edition, data_dir, store.all_editions(data_dir))
    forum.save(data_dir, out)
    budget.record_run(data_dir, dt.datetime.now(dt.timezone.utc), edition["edition_id"], "forum", backend, tally)
    return f"Botroom {edition['edition_id']}: {out.note}"


def _skip_extra(edition: dict[str, Any], mode: str, requested: str) -> str | None:
    """Whether the column, the quiz or the Botroom stays out of this edition: a line for the report ("" says nothing),
    or None to go ahead and write it if it's due."""
    if requested == "force" and edition["mode"] == "links":
        return "not written: a links edition has no Claude to write it"
    if requested == "off" or edition["mode"] == "links" or (requested == "auto" and mode != "full"):
        return ""
    return None


def _record_llm(edition: dict[str, Any], llm: LLM) -> None:
    """The edition's cost line, now including the column or quiz calls."""
    edition["llm"] = {"backend": llm.backend, **llm.tally.summary()}
    edition["llm"]["estimated_usd"] = edition["llm"]["equivalent_usd"]


def report(result: Result) -> str:
    """Plain-text summary for the console and the Actions step summary."""
    lines = [f"Edition {result.edition_id or '-'}: {'published' if result.published else 'not published'} "
             f"(mode {result.mode}; {result.reason})"]
    if result.column:
        lines.append(f"Opinion column {result.column}")
    if result.quiz:
        lines.append(f"Quiz {result.quiz}")
    if result.forum:
        lines.append(f"Botroom {result.forum}")
    if result.deals:
        lines.append(f"Deals {result.deals}")
    if result.screen:
        lines.append(f"Screen: {result.screen}")
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
