"""`python -m newsroom generate`: decide whether an edition is due, pick a mode, build and save it."""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import schedule, store
from .http import Client
from .links import build_links_edition
from .sources import Harvest, fetch_all

MODES = ("auto", "full", "reduced", "links", "skip")
MIN_LINKS_TO_PUBLISH = 5          # below this the sources are probably down: keep the last edition


@dataclass
class Result:
    published: bool
    mode: str
    reason: str
    edition_id: str = ""
    path: Path | None = None
    harvest: Harvest | None = None


def resolve_mode(requested: str, cfg: dict[str, Any], env: dict[str, str]) -> tuple[str, str]:
    """The pre-run check (PLAN.md, 'Run modes'). AI modes arrive in phase 3; until then every
    AI request falls back to `llm.when_unavailable`."""
    fallback = (cfg.get("llm") or {}).get("when_unavailable", "links")
    if requested in ("links", "skip"):
        return requested, f"requested {requested}"
    if not env.get("ANTHROPIC_API_KEY"):
        return fallback, "no ANTHROPIC_API_KEY"
    return fallback, "AI writing not built yet (phase 3)"


def generate(cfg: dict[str, Any], data_dir: Path, requested: str = "auto",
             now: dt.datetime | None = None, env: dict[str, str] | None = None,
             client: Client | None = None) -> Result:
    if requested not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    now = now or dt.datetime.now(dt.timezone.utc)
    env = dict(os.environ) if env is None else env
    sched = cfg["schedule"]
    tz, slots = sched["timezone"], sched["editions"]

    if requested == "auto":
        if not schedule.is_due(now, tz, slots, store.last_generated_at(data_dir)):
            return Result(False, "none", "not due: the latest slot already has an edition")
        slot = schedule.latest_slot(now, tz, slots)
    else:
        slot = schedule.forced_slot(now, tz, slots)
    edition_id = schedule.edition_id(slot, slots)

    mode, reason = resolve_mode(requested, cfg, env)
    if mode == "skip":
        return Result(False, "skip", reason, edition_id)

    own_client = client is None
    client = client or Client()
    try:
        harvest = fetch_all(cfg, client, now, itad_key=env.get("ITAD_API_KEY") or None)
    finally:
        if own_client:
            client.__exit__(None, None, None)

    previous = store.latest_edition(data_dir)
    if previous and previous.get("edition_id") == edition_id:
        previous = None                      # replacing today's edition: don't dedupe against it
    edition = build_links_edition(cfg, harvest, edition_id, previous=previous, reason=reason)

    if len(edition["links"]) + len(edition["hn_top"]) < MIN_LINKS_TO_PUBLISH:
        return Result(False, mode, "too few items fetched; kept the previous edition", edition_id,
                      harvest=harvest)
    path = store.save_edition(data_dir, edition)
    return Result(True, mode, reason, edition_id, path, harvest)


def report(result: Result) -> str:
    """Plain-text summary for the console and the Actions step summary."""
    lines = [f"Edition {result.edition_id or '-'}: {'published' if result.published else 'not published'} "
             f"(mode {result.mode}; {result.reason})"]
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
