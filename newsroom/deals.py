"""The deals cadence: the deals are checked on set weekdays, and the editions in between carry the last check.

Shops change their deals on fixed days. Of the deals with an end time in the editions of 3-10 November 2026,
more than half ended on a Monday (Steam at 17:00-18:00 UTC, its 10:00 Pacific changeover; Fanatical's weekly
deals and IndieGala just before midnight UTC; Epic in the afternoon), and the next group on Thursday at 18:00 UTC
(Steam, Humble). So most new deals are up by Monday evening and the rest by Thursday evening, and the Tuesday and
Friday 07:00 editions are the first to see them. Steam's big seasonal sales start on Thursdays too.

So the deals (the IsThereAnyDeal lists or Steam specials, and Claude's ratings) are refreshed on `deals.days`
(Tuesday and Friday). The other editions carry the last check's block forward, minus the deals that have ended
since, with no fetch and no Claude call. The deals are checked anyway when:
- a check day was missed (no edition that day, or its check found nothing), or the last check is more than
  `deals.max_age_days` old;
- every carried deal has ended, or there are no earlier deals;
- an AI edition follows a check nobody rated (a links edition, or a failed deals call).
`generate --deals force` checks now; `--deals carry` keeps the last check.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import links, store
from .schedule import WEEKDAYS
from .sources import Harvest, SourceStatus

MODES = ("auto", "force", "carry")   # auto = on deals.days, or when the safety net says so
DEFAULT_DAYS = ["tue", "fri"]
DEFAULT_MAX_AGE = 4                  # days; the longest regular gap is Friday to Tuesday


@dataclass
class Plan:
    refresh: bool                    # check the deals today (fetch, and rate them in AI editions)
    why: str                         # for the report
    carried: dict[str, Any] | None = None   # the last check, minus deals that have ended (None: nothing left)


def settings(cfg: dict[str, Any]) -> tuple[list[str], int]:
    """(check days, max age in days). An empty `deals.days` checks every edition."""
    d = cfg.get("deals") or {}
    days = d.get("days", DEFAULT_DAYS) or []
    return [str(x)[:3].lower() for x in days], int(d.get("max_age_days", DEFAULT_MAX_AGE))


def _weekdays(days: list[str]) -> set[int]:
    return {WEEKDAYS.index(x) for x in days if x in WEEKDAYS}


def due(day: dt.date, days: list[str], last: dt.date | None, max_age_days: int = DEFAULT_MAX_AGE) -> str:
    """Why the deals are checked on `day` when they were last checked on `last`, or "" to carry them over.
    At most one check per check day, so a second edition slot that day carries the first one's."""
    if last is None:
        return "no earlier check"
    wanted = _weekdays(days)
    if not wanted:
        return "checked every edition (deals.days is empty)"
    if day.weekday() in wanted and last < day:
        return f"check day ({day:%A})"
    missed = [last + dt.timedelta(days=n) for n in range(1, (day - last).days)
              if (last + dt.timedelta(days=n)).weekday() in wanted]
    if missed:
        return f"missed {missed[-1]:%A}'s check"
    if (day - last).days > max_age_days:
        return f"last check {(day - last).days} days ago"
    return ""


def next_check(day: dt.date, days: list[str]) -> dt.date | None:
    """The first check day after `day`, or None when every edition checks."""
    wanted = _weekdays(days)
    if not wanted:
        return None
    return next(day + dt.timedelta(days=n) for n in range(1, 8) if (day + dt.timedelta(days=n)).weekday() in wanted)


def _ts(value: Any) -> dt.datetime | None:
    """A stored timestamp, or None (missing or unreadable: a deal with no end date stays, a check with no
    time is checked again)."""
    try:
        ts = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None
    return ts if ts is None or ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def count(block: dict[str, Any] | None) -> int:
    """Deals in a block: the deals of the day, the rated list and the Deals page's shelves."""
    b = block or {}
    return (len(b.get("featured") or []) + len(b.get("more") or [])
            + sum(len(s.get("deals") or []) for s in b.get("shelves") or []))


def rated(block: dict[str, Any]) -> bool:
    """Whether Claude rated this check (a links edition, or a failed deals call, leaves it unrated)."""
    return bool(block.get("featured")) or any(d.get("verdict") for d in block.get("more") or [])


def carry(block: dict[str, Any], edition_id: str, now: dt.datetime) -> dict[str, Any]:
    """The block for an edition that doesn't check: the same deals, ratings and `checked_at`, minus deals that
    have ended by `now`. `carried` says whose check it is (`from`, an edition id) and how many deals have ended
    since (`ended`)."""
    def live(d: dict[str, Any]) -> bool:
        end = _ts(d.get("expires"))
        return end is None or end > now

    out = {**block, "featured": [d for d in block.get("featured") or [] if live(d)],
           "more": [d for d in block.get("more") or [] if live(d)]}
    if "shelves" in block:
        out["shelves"] = [{**s, "deals": [d for d in s.get("deals") or [] if live(d)]}
                          for s in block.get("shelves") or []]
        out["shelves"] = [s for s in out["shelves"] if s["deals"]]
    prior = block.get("carried") or {}
    out["carried"] = {"from": prior.get("from") or edition_id,
                      "ended": int(prior.get("ended") or 0) + count(block) - count(out)}
    return out


def plan(cfg: dict[str, Any], data_dir: Path, edition_id: str, now: dt.datetime, requested: str = "auto",
         ai: bool = True) -> Plan:
    """Whether this edition checks the deals or carries the last check over (`requested`: auto, force, carry;
    `ai`: the edition is written by Claude, so an unrated check is checked again)."""
    if requested not in MODES:
        raise ValueError(f"deals must be one of {', '.join(MODES)}")
    previous = store.previous_edition(data_dir, edition_id, "deals")
    block = (previous or {}).get("deals")
    carried = carry(block, previous["edition_id"], now) if block else None
    if carried is not None and not count(carried):
        carried = None
    if requested == "force":
        return Plan(True, "forced (--deals force)", carried)
    if carried is None:
        return Plan(True, "every deal from the last check has ended" if block else "no earlier deals")
    if requested == "carry":
        return Plan(False, "kept the last check (--deals carry)", carried)
    if ai and not rated(block):
        return Plan(True, "the last check wasn't rated", carried)
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    checked = _ts(block.get("checked_at"))
    days, max_age = settings(cfg)
    why = due(dt.date.fromisoformat(edition_id[:10]), days, checked.astimezone(tz).date() if checked else None,
              max_age)
    return Plan(bool(why), why, carried)


def fetch_config(cfg: dict[str, Any], refresh: bool) -> dict[str, Any]:
    """The config the fetch sees. On a day the deals carry over, the deals lists aren't fetched: no
    IsThereAnyDeal deals and no Steam specials (ITAD's critic scores for Gaming still are)."""
    if refresh:
        return cfg
    src = dict(cfg.get("sources") or {})
    if src.get("steam"):
        src["steam"] = {**src["steam"], "lists": [x for x in src["steam"].get("lists") or [] if x != "specials"]}
    if src.get("itad"):
        src["itad"] = {**src["itad"], "deals": False}
    return {**cfg, "sources": src}


def block_for(cfg: dict[str, Any], harvest: Harvest, p: Plan) -> tuple[dict[str, Any], str]:
    """Today's deals block and a line for the report. Adds a "Deals" row to the harvest status, which says
    when the deals were carried over (a carried day isn't a failed source)."""
    if p.refresh:
        fresh = links.deals_block(cfg, harvest)
        if count(fresh) or p.carried is None:
            note = f"checked ({p.why}): {count(fresh)} deals"
            harvest.status.append(SourceStatus("Deals", True, count(fresh), error=note))
            return fresh, note
        note = f"the check found nothing, so {_carried_note(cfg, p.carried, harvest.fetched_at)}"
    else:
        note = f"not checked today: {_carried_note(cfg, p.carried, harvest.fetched_at)}"
    harvest.status.append(SourceStatus("Deals", True, count(p.carried), skipped=True, error=note))
    return p.carried, note


def _carried_note(cfg: dict[str, Any], block: dict[str, Any], now: dt.datetime) -> str:
    """For the report: carried over from Tue 10 Nov 07:05 (2 ended since); next check Fri."""
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    checked = _ts(block.get("checked_at"))
    local = checked.astimezone(tz) if checked else None
    when = f"{local:%a} {local.day} {local:%b %H:%M}" if local else block["carried"]["from"]
    ended = block["carried"]["ended"]
    nxt = next_check(now.astimezone(tz).date(), settings(cfg)[0])
    return (f"carried over from {when}" + (f" ({ended} ended since)" if ended else "")
            + (f"; next check {nxt:%a}" if nxt else ""))
