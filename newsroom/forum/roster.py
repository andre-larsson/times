"""Who's around: the Botroom's members, stepped one day at a time and kept in data/forum/roster.json.

Each day, in order:
1. Away bots whose return date has come back. Core bots always come back on time; the others only while
   there's room (MAX_ACTIVE), and when the forum is full their return slips by 2 to 5 days.
2. Every member, around or away, except the core cast, may leave for good (P_GONE: "account deactivated").
   So the rest of the membership N follows dN/dt = joins - P_GONE * N and levels off near P_JOIN / P_GONE
   (about 24), plus the 8 core bots. Each bot that's around (past its first week, or a week after coming
   back) may also go away (P_AWAY) for 2 days to 4 months.
3. A newcomer may join (P_JOIN, about one every six weeks), waiting for room if the forum is full. Half of
   newcomers (P_FRESH), and all of them once the hand-written waiting list is empty, are brand-new personas
   generated on the day (newcomer.py, through the `make_fresh` callback, which first uses personas made in
   advance). If that fails, the next bot on the waiting list joins instead, or, with nobody waiting, the
   newcomer comes another day.
4. If fewer than MIN_ACTIVE are around, someone comes back early (or, if nobody is away, someone joins).

Every draw comes from random.Random(f"{seed}:{date}"), so the same seed and cast give the same history. The
founders are around from the first day, joined by a launch batch of newcomers (config forum.launch); a cast
change (a persona added to cast.py, or one deleted from cast.json) is picked up by `sync` before the next step.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

P_AWAY = 0.025          # per day around: average spell about six weeks
P_GONE = 0.001          # per member-day, around or away: leaves for good (0.365 a year per member)
P_JOIN = 0.024          # per day: about one newcomer every six weeks (8.8 a year), so N levels off near 24
P_FRESH = 0.5           # share of newcomers that are brand-new generated personas
MIN_ACTIVE, MAX_ACTIVE = 7, 12
NEW_DAYS = 7            # tagged "new" this long; no going away this soon after joining or coming back
AWAY_DAYS = [(2, 5, .45), (6, 14, .3), (15, 40, .15), (41, 120, .1)]   # (shortest, longest, weight)


@dataclass
class Member:
    handle: str
    status: str = "bench"             # bench | active | away | gone
    joined: str | None = None         # ISO dates throughout, so the state is plain JSON
    away_since: str | None = None
    back_on: str | None = None
    back_from: str | None = None      # last return; no new absence within NEW_DAYS


@dataclass
class State:
    members: dict[str, Member] = field(default_factory=dict)
    bench: list[str] = field(default_factory=list)       # the hand-written waiting list, in joining order
    pending: int = 0                                     # newcomers waiting for room
    fresh: int = 0                                       # generated newcomers so far

    def to_json(self) -> dict[str, Any]:
        return {"members": {h: {k: v for k, v in asdict(m).items() if k != "handle"} for h, m in self.members.items()},
                "bench": list(self.bench), "pending": self.pending, "fresh": self.fresh}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "State":
        return cls(members={h: Member(h, **m) for h, m in (data.get("members") or {}).items()},
                   bench=list(data.get("bench") or []), pending=int(data.get("pending", 0)),
                   fresh=int(data.get("fresh", 0)))

    def around(self) -> list[str]:
        return [h for h, m in self.members.items() if m.status == "active"]


@dataclass
class Day:
    date: date
    joined: list[str] = field(default_factory=list)
    returned: dict[str, int] = field(default_factory=dict)    # handle -> days away
    left: dict[str, int] = field(default_factory=dict)        # handle -> planned days away
    gone: list[str] = field(default_factory=list)
    fresh: list[str] = field(default_factory=list)             # of the joins, the generated personas
    new: list[str] = field(default_factory=list)               # joined within NEW_DAYS (today included)
    around: list[str] = field(default_factory=list)
    away: list[str] = field(default_factory=list)

    def merge(self, later: "Day") -> "Day":
        """Several days stepped at once (missed editions): one day's news, with the latest roster."""
        returned = {**self.returned, **later.returned}
        left = {h: n for h, n in {**self.left, **later.left}.items() if h not in later.returned}
        return Day(later.date, self.joined + later.joined, returned, left, self.gone + later.gone,
                   self.fresh + later.fresh, later.new, later.around, later.away)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["date"] = self.date.isoformat()
        return out


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def away_length(rng: random.Random) -> int:
    lo, hi, _ = rng.choices(AWAY_DAYS, weights=[w for *_, w in AWAY_DAYS])[0]
    return rng.randint(lo, hi)


def bootstrap(cast: dict[str, dict[str, Any]], seed: int, start: date, launch: list[str] = ()) -> State:
    """The first day's state: the founders around, the launch batch joining that day, and the rest of the
    hand-written cast waiting in a seeded order."""
    state = State()
    for h, p in cast.items():
        if p.get("founding"):
            state.members[h] = Member(h, "active", joined=(start - timedelta(days=30)).isoformat())
    for h in launch:
        if h in cast and h not in state.members:
            state.members[h] = Member(h, "active", joined=start.isoformat())
    bench = [h for h, p in cast.items()
             if not p.get("founding") and not p.get("generated") and h not in state.members]
    random.Random(f"{seed}:bench").shuffle(bench)
    state.bench = bench
    return state


def sync(state: State, cast: dict[str, dict[str, Any]], today: date) -> None:
    """Follow cast changes: a deleted persona is gone; a new hand-written one joins the waiting list (a new
    founder is simply around)."""
    for h, m in state.members.items():
        if h not in cast and m.status != "gone":
            m.status, m.away_since, m.back_on = "gone", None, None
    state.bench = [h for h in state.bench if h in cast and h not in state.members]
    for h, p in cast.items():
        if h in state.members or h in state.bench or p.get("generated"):
            continue
        if p.get("founding"):
            state.members[h] = Member(h, "active", joined=(today - timedelta(days=30)).isoformat())
        else:
            state.bench.append(h)


def step(state: State, d: date, cast: dict[str, dict[str, Any]], seed: int,
         make_fresh: Callable[[date, set[str]], str | None]) -> Day:
    """Advance the roster by one day (mutating `state`) and return the day's news.

    `make_fresh(d, taken)` returns the handle of a brand-new persona (already added to `cast`) that isn't one
    of the `taken` members, or None when that fails.
    """
    rng = random.Random(f"{seed}:{d.isoformat()}")
    members = state.members
    today = Day(d)

    def core(h: str) -> bool:
        return bool(cast.get(h, {}).get("core"))

    def fixed(h: str) -> bool:
        return bool(cast.get(h, {}).get("fixed"))

    def newcomer() -> bool:
        bench = [h for h in state.bench if h not in members]
        h = None
        if not bench or rng.random() < P_FRESH:
            h = make_fresh(d, set(members))
            if h:
                state.fresh += 1
                today.fresh.append(h)
        if h is None and bench:
            h = bench[0]
        if h is None:
            return False
        state.bench = [x for x in state.bench if x != h]
        members[h] = Member(h, "active", joined=d.isoformat())
        today.joined.append(h)
        return True

    n_active = sum(m.status == "active" for m in members.values())
    due = sorted((m for m in members.values() if m.status == "away" and _d(m.back_on) <= d),
                 key=lambda m: (not core(m.handle), m.back_on, m.handle))
    for m in due:                                                # 1. returns: core on time, others when there's room
        if core(m.handle) or n_active < MAX_ACTIVE:
            today.returned[m.handle] = (d - _d(m.away_since)).days
            m.status, m.away_since, m.back_on, m.back_from = "active", None, None, d.isoformat()
            n_active += 1
        else:
            m.back_on = (d + timedelta(days=rng.randint(2, 5))).isoformat()
    for m in members.values():                                   # 2. departures
        if m.status not in ("active", "away") or fixed(m.handle) or m.handle in today.returned:
            continue
        stays = core(m.handle)
        if m.status == "away":
            if rng.random() < P_GONE and not stays:
                m.status, m.away_since, m.back_on = "gone", None, None
                today.gone.append(m.handle)
            continue
        if (d - _d(m.joined)).days < NEW_DAYS or (m.back_from and (d - _d(m.back_from)).days < NEW_DAYS):
            continue
        r = rng.random()
        if r < P_GONE and not stays:
            m.status = "gone"
            today.gone.append(m.handle)
        elif r < P_GONE + P_AWAY:
            n = away_length(rng)
            m.status, m.away_since, m.back_on = "away", d.isoformat(), (d + timedelta(days=n)).isoformat()
            today.left[m.handle] = n
    if rng.random() < P_JOIN:                                    # 3. joins, waiting for room
        state.pending += 1
    n_active = sum(m.status == "active" for m in members.values())
    if state.pending and n_active < MAX_ACTIVE and newcomer():
        state.pending -= 1
        n_active += 1
    while n_active < MIN_ACTIVE:                                 # 4. too quiet: someone comes back early
        away = sorted((m for m in members.values() if m.status == "away" and _d(m.away_since) < d),
                      key=lambda m: (m.back_on, m.handle))
        if away:
            m = away[0]
            today.returned[m.handle] = (d - _d(m.away_since)).days
            today.left.pop(m.handle, None)
            m.status, m.away_since, m.back_on, m.back_from = "active", None, None, d.isoformat()
        elif newcomer():
            state.pending = max(0, state.pending - 1)
        else:
            break
        n_active += 1
    today.around = [h for h, m in members.items() if m.status == "active"]
    today.away = [h for h, m in members.items() if m.status == "away"]
    today.new = [h for h in today.around if 0 <= (d - _d(members[h].joined)).days < NEW_DAYS]
    return today


# ── data/forum/roster.json ───────────────────────────────────────────────────

def roster_path(data_dir: Path) -> Path:
    return data_dir / "forum" / "roster.json"


def load(data_dir: Path) -> dict[str, Any] | None:
    path = roster_path(data_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def advance(saved: dict[str, Any] | None, cast: dict[str, dict[str, Any]], seed: int, day: date,
            make_fresh: Callable[[date, set[str]], str | None], launch: list[str] = ()) -> tuple[dict[str, Any], Day]:
    """Step the stored roster up to `day` and return (what to save, the day's news).

    The first run starts with the founders and the `launch` batch, who join that day. A second run on the
    same day starts again from the state before that day, so it replays the same roster news. After missed
    days every day is stepped in turn and their news merged.
    """
    if saved and saved.get("day") == day.isoformat() and saved.get("previous") is not None:
        state, last = State.from_json(saved["previous"]), _d(saved.get("previous_day"))
    elif saved and saved.get("day") and _d(saved["day"]) < day:
        state, last = State.from_json(saved["state"]), _d(saved["day"])
    elif saved and saved.get("day") and _d(saved["day"]) > day:
        raise ValueError(f"the roster is already at {saved['day']}, after {day}")
    else:
        state, last = bootstrap(cast, seed, day, launch), None
    launched = [h for h in state.members if last is None and state.members[h].joined == day.isoformat()]
    before = State.from_json(state.to_json())
    sync(state, cast, day)
    first = day if last is None else max(last + timedelta(days=1), day - timedelta(days=60))
    news: Day | None = None
    d = first
    while d <= day:
        today = step(state, d, cast, seed, make_fresh)
        news = today if news is None else news.merge(today)
        d += timedelta(days=1)
    assert news is not None
    news.joined = launched + [h for h in news.joined if h not in launched]
    out = {"seed": seed, "day": day.isoformat(), "state": state.to_json(),
           "previous_day": last.isoformat() if last else None,
           "previous": before.to_json() if last else None, "news": news.to_json()}
    return out, news
