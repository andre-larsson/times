"""Edition slots in local time (config.schedule.editions) and the 'is one due?' check."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _slots(slots: list[str]) -> list[dt.time]:
    return sorted(dt.time.fromisoformat(s) for s in slots)


def latest_slot(now: dt.datetime, tz: str, slots: list[str]) -> dt.datetime:
    """The most recent slot at or before now, as an aware local datetime."""
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    times = _slots(slots)
    for day in (local.date(), local.date() - dt.timedelta(days=1)):
        for t in reversed(times):
            candidate = dt.datetime.combine(day, t, tzinfo=zone)
            if candidate <= local:
                return candidate
    raise ValueError("schedule.editions is empty")


def edition_id(slot: dt.datetime, slots: list[str]) -> str:
    """'2026-11-03' for the first slot of the day, '2026-11-03-1330' for later ones."""
    times = _slots(slots)
    base = slot.date().isoformat()
    if slot.timetz().replace(tzinfo=None) == times[0]:
        return base
    return f"{base}-{slot:%H%M}"


def is_due(now: dt.datetime, tz: str, slots: list[str], last_generated_at: dt.datetime | None) -> bool:
    return last_generated_at is None or last_generated_at < latest_slot(now, tz, slots)


def forced_slot(now: dt.datetime, tz: str, slots: list[str]) -> dt.datetime:
    """Slot to file a manual run under: today's latest passed slot, else today's first slot.

    A manual run before the first slot of the day still files under today, and the scheduled run
    at the first slot then replaces it with a fresh edition.
    """
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    slot = latest_slot(now, tz, slots)
    if slot.date() == local.date():
        return slot
    return dt.datetime.combine(local.date(), _slots(slots)[0], tzinfo=zone)


def weekly_due(day: dt.date, days: list[str], every_weeks: int, last: dt.date | None) -> bool:
    """For features on set weekdays (the opinion column, the quiz): `day` is one of `days` (mon … sun),
    and at least `every_weeks` weeks have passed since `last`. Never twice on one day."""
    if day.weekday() not in {WEEKDAYS.index(str(d)[:3].lower()) for d in days}:
        return False
    return last is None or (day - last).days > 7 * (max(1, every_weeks) - 1)
