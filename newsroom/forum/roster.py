"""Who's around: the Botroom's members, stepped one day at a time and kept in data/forum/roster.json.

The settings are config forum.roster (`Rates`), in the units they're thought of in; code turns them into daily
chances. Each day, in order:
1. Away bots whose return date has come back. Core bots always come back on time; the others only while
   there's room (most around), and when the forum is full their return slips by 2 to 5 days.
2. Every member, around or away, except the core cast, may leave for good ("account deactivated"), with the
   same daily chance for each. So the rest of the membership N follows dN/dt = joins - p * N and levels off
   at joins / p; p is set from forum.roster.members so that is where it levels off. Bots that are around (past
   their first week, or a week after coming back) go away for a while, breaks_per_month of them across the
   forum, each for a length drawn from break_days (mostly short).
3. A newcomer comes join_days after the last one (drawn in that range), and joins that day even when the
   forum is full: the room comes back as bots go away, since returns wait for it. A share of newcomers
   (generated_share), and all of them once the hand-written waiting list is empty, are brand-new personas
   generated on the day (newcomer.py, through the `make_fresh` callback, which first uses personas made in
   advance). If that fails, the next bot on the waiting list joins instead, or, with nobody waiting, the
   newcomer comes the next day.
4. If fewer than the fewest are around, someone comes back early (or, if nobody is away, someone joins).

Every draw comes from random.Random(f"{seed}:{date}"), so the same seed, cast and settings give the same
history. A settings change acts from the next step on; the saved state is never replayed. The founders are
around from the first day, joined by a launch batch of newcomers (config forum.launch); a cast change (a
persona added to cast.py, or one deleted from cast.json) is picked up by `sync` before the next step.
`simulate` and `report` show what a settings change does over years (python -m newsroom roster).
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

NEW_DAYS = 7            # tagged "new" this long; no going away this soon after joining or coming back
AWAY_DAYS = [(2, 5, .45), (6, 14, .3), (15, 40, .15), (41, 120, .1)]   # break lengths: (shortest, longest, weight)
MONTH = 365.25 / 12
MAX_P_AWAY = 0.25       # a small forum still doesn't send everyone away at once


@dataclass(frozen=True)
class Rates:
    """config forum.roster. The defaults are the config's values."""
    around: tuple[int, int] = (7, 12)         # fewest and most around on a day
    join_days: tuple[int, int] = (5, 7)       # days between newcomers
    generated_share: float = 0.5              # newcomers that are generated (the rest: the waiting list)
    members: int = 32                         # where membership levels off, core bots included
    breaks_per_month: float = 10.0            # bots going away, forum-wide
    break_days: tuple[int, int] = (2, 120)    # how long a break is meant to last

    @classmethod
    def from_config(cls, forum: dict[str, Any]) -> "Rates":
        r, d = forum.get("roster") or {}, cls()

        def pair(key: str, lowest: int) -> tuple[int, int]:
            lo, hi = (int(x) for x in r.get(key, getattr(d, key)))
            if not lowest <= lo <= hi:
                raise ValueError(f"forum.roster.{key}: need {lowest} <= first <= second, got [{lo}, {hi}]")
            return lo, hi

        rates = cls(around=pair("around", 1), join_days=pair("join_days", 1),
                    generated_share=float(r.get("generated_share", d.generated_share)),
                    members=int(r.get("members", d.members)),
                    breaks_per_month=float(r.get("breaks_per_month", d.breaks_per_month)),
                    break_days=pair("break_days", 1))
        if not 0 <= rates.generated_share <= 1 or rates.breaks_per_month < 0:
            raise ValueError("forum.roster: generated_share is 0 to 1 and breaks_per_month at least 0")
        return rates

    @property
    def joins_per_year(self) -> float:
        return 365 * 2 / sum(self.join_days)

    def p_gone(self, n_core: int) -> float:
        """Each non-core member's daily chance of leaving for good: what levels membership off at `members`.
        Newcomers in their first week never leave, so they don't count."""
        per_day = self.joins_per_year / 365
        return per_day / max(1.0, self.members - n_core - per_day * NEW_DAYS)

    def p_away(self, eligible: int) -> float:
        """Each eligible bot's daily chance of going away, so that breaks_per_month go across the forum."""
        return min(MAX_P_AWAY, self.breaks_per_month / MONTH / eligible) if eligible else 0.0


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
    pending: int = 0                                     # newcomers due who couldn't be found yet
    fresh: int = 0                                       # generated newcomers so far
    next_join: str | None = None                         # when the next newcomer is due (None: work it out)

    def to_json(self) -> dict[str, Any]:
        return {"members": {h: {k: v for k, v in asdict(m).items() if k != "handle"} for h, m in self.members.items()},
                "bench": list(self.bench), "pending": self.pending, "fresh": self.fresh, "next_join": self.next_join}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "State":
        return cls(members={h: Member(h, **m) for h, m in (data.get("members") or {}).items()},
                   bench=list(data.get("bench") or []), pending=int(data.get("pending", 0)),
                   fresh=int(data.get("fresh", 0)), next_join=data.get("next_join"))

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


def away_length(rng: random.Random, limits: tuple[int, int] = Rates.break_days) -> int:
    """A break's planned length: AWAY_DAYS's shape (mostly a few days, now and then months), cut to `limits`."""
    lo, hi = limits
    bins = [(max(a, lo), min(b, hi), w * (min(b, hi) - max(a, lo) + 1) / (b - a + 1))
            for a, b, w in AWAY_DAYS if max(a, lo) <= min(b, hi)]
    if not bins:                                       # a range outside the shape: evenly within it
        return rng.randint(lo, hi)
    a, b, _ = rng.choices(bins, weights=[w for *_, w in bins])[0]
    return rng.randint(a, b)


def join_gap(rng: random.Random, rates: Rates) -> int:
    return rng.randint(*rates.join_days)


def bootstrap(cast: dict[str, dict[str, Any]], seed: int, start: date, launch: list[str] = (),
              rates: Rates = Rates()) -> State:
    """The first day's state: the founders around, the launch batch joining that day, the rest of the
    hand-written cast waiting in a seeded order, and the first newcomer due join_days later."""
    state = State(next_join=(start + timedelta(days=join_gap(random.Random(f"{seed}:joins"), rates))).isoformat())
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
         make_fresh: Callable[[date, set[str]], str | None], rates: Rates = Rates()) -> Day:
    """Advance the roster by one day (mutating `state`) and return the day's news.

    `make_fresh(d, taken)` returns the handle of a brand-new persona (already added to `cast`) that isn't one
    of the `taken` members, or None when that fails.
    """
    rng = random.Random(f"{seed}:{d.isoformat()}")
    members = state.members
    today = Day(d)
    fewest, most = rates.around

    def core(h: str) -> bool:
        return bool(cast.get(h, {}).get("core"))

    def fixed(h: str) -> bool:
        return bool(cast.get(h, {}).get("fixed"))

    def settling(m: Member) -> bool:
        return (d - _d(m.joined)).days < NEW_DAYS or bool(m.back_from and (d - _d(m.back_from)).days < NEW_DAYS)

    def newcomer() -> bool:
        bench = [h for h in state.bench if h not in members]
        h = None
        if not bench or rng.random() < rates.generated_share:
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

    if state.next_join is None:                                  # a roster saved before the schedule
        last = max((_d(m.joined) for m in members.values() if m.joined), default=d)
        state.next_join = (last + timedelta(days=join_gap(rng, rates))).isoformat()

    n_active = sum(m.status == "active" for m in members.values())
    due = sorted((m for m in members.values() if m.status == "away" and _d(m.back_on) <= d),
                 key=lambda m: (not core(m.handle), m.back_on, m.handle))
    for m in due:                                                # 1. returns: core on time, others when there's room
        if core(m.handle) or n_active < most:
            today.returned[m.handle] = (d - _d(m.away_since)).days
            m.status, m.away_since, m.back_on, m.back_from = "active", None, None, d.isoformat()
            n_active += 1
        else:
            m.back_on = (d + timedelta(days=rng.randint(2, 5))).isoformat()
    n_core = sum(core(h) and m.status in ("active", "away") for h, m in members.items())
    p_gone = rates.p_gone(n_core)
    p_away = rates.p_away(sum(m.status == "active" and not fixed(h) and h not in today.returned and not settling(m)
                              for h, m in members.items()))
    for m in members.values():                                   # 2. departures and breaks
        if (m.status not in ("active", "away") or fixed(m.handle) or m.handle in today.returned
                or (d - _d(m.joined)).days < NEW_DAYS):
            continue
        if not core(m.handle) and rng.random() < p_gone:
            m.status, m.away_since, m.back_on = "gone", None, None
            today.gone.append(m.handle)
            continue
        if m.status == "active" and not settling(m) and rng.random() < p_away:
            n = away_length(rng, rates.break_days)
            m.status, m.away_since, m.back_on = "away", d.isoformat(), (d + timedelta(days=n)).isoformat()
            today.left[m.handle] = n
    if _d(state.next_join) <= d:                                 # 3. joins: on the day, full forum or not
        state.pending += 1
        state.next_join = (d + timedelta(days=join_gap(rng, rates))).isoformat()
    n_active = sum(m.status == "active" for m in members.values())
    if state.pending and newcomer():
        state.pending -= 1
        n_active += 1
    while n_active < fewest:                                     # 4. too quiet: someone comes back early
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
            make_fresh: Callable[[date, set[str]], str | None], launch: list[str] = (),
            rates: Rates = Rates()) -> tuple[dict[str, Any], Day]:
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
        state, last = bootstrap(cast, seed, day, launch, rates), None
    launched = [h for h in state.members if last is None and state.members[h].joined == day.isoformat()]
    before = State.from_json(state.to_json())
    sync(state, cast, day)
    first = day if last is None else max(last + timedelta(days=1), day - timedelta(days=60))
    news: Day | None = None
    d = first
    while d <= day:
        today = step(state, d, cast, seed, make_fresh, rates)
        news = today if news is None else news.merge(today)
        d += timedelta(days=1)
    assert news is not None
    news.joined = launched + [h for h in news.joined if h not in launched]
    out = {"seed": seed, "day": day.isoformat(), "state": state.to_json(),
           "previous_day": last.isoformat() if last else None,
           "previous": before.to_json() if last else None, "news": news.to_json()}
    return out, news


# ── what if: simulated histories (python -m newsroom roster) ─────────────────

def simulate(rates: Rates, cast: dict[str, dict[str, Any]], start: date, days: int, runs: int,
             state: State | None = None, waiting: Iterable[str] = (), launch: Iterable[str] = ()) -> list[list[dict]]:
    """`runs` histories of `days` days from `start`, each with its own seed and no Claude calls. They start from
    `state` (a copy), or from a new roster with the `launch` batch. Newcomers made in advance (`waiting`) join
    first, then placeholders. Returns one record a day for each run."""
    out = []
    for run in range(runs):
        c = dict(cast)
        s = State.from_json(state.to_json()) if state else bootstrap(c, run, start, list(launch), rates)
        queue = [h for h in waiting if h not in s.members]
        made = 0

        def make_fresh(d: date, taken: set[str]) -> str:
            nonlocal made
            while queue:
                h = queue.pop(0)
                if h not in taken:
                    return h
            made += 1
            c[f"Sim_Bot_{made}"] = {"core": False, "fixed": False, "generated": True}
            return f"Sim_Bot_{made}"

        rows = []
        for i in range(days):
            d = start + timedelta(days=i)
            away = {h for h, m in s.members.items() if m.status == "away"}
            t = step(s, d, c, run, make_fresh, rates)
            rows.append({"joined": len(t.joined), "fresh": len(t.fresh), "left": len(t.left),
                         "returned": len(t.returned), "gone": len(t.gone), "gone_away": len(away & set(t.gone)),
                         "around": len(t.around), "away": len(t.away),
                         "members": sum(m.status in ("active", "away") for m in s.members.values())})
        out.append(rows)
    return out


def _longest_gap(rows: list[dict], since: int) -> int:
    """The most days in a row without a newcomer, counted from `since` (the last join before the period)."""
    longest, last = 0, since
    for i, r in enumerate(rows):
        if r["joined"]:
            longest, last = max(longest, i - last), i
    return max(longest, len(rows) - last)


def report(rates: Rates, histories: list[list[dict]], n_core: int) -> str:
    """What the histories add up to, a year at a time."""
    stay = 1 / rates.p_gone(n_core) / MONTH
    lines = [f"Settings: {rates.around[0]} to {rates.around[1]} around; a newcomer every {rates.join_days[0]} to "
             f"{rates.join_days[1]} days ({rates.joins_per_year:.0f} a year, {rates.generated_share:.0%} generated); "
             f"members level off at {rates.members} ({n_core} core), so a non-core member stays {stay:.1f} months "
             f"on average; {rates.breaks_per_month:g} breaks a month of {rates.break_days[0]} to "
             f"{rates.break_days[1]} days.",
             f"{len(histories)} simulated histories. Per week: newcomers. Per month: the rest. Around and away: "
             "the daily mean. Members: at the end of the year, mean (lowest to highest).", "",
             f"{'':7}{'joins/wk':>9}{'gap max':>8}{'gen/wk':>7}{'breaks':>7}{'back':>6}{'left':>6}"
             f"{'of them away':>13}{'around':>7}{'range':>8}{'away':>6}{'members':>13}{'news days':>10}"]
    days = len(histories[0])
    for y in range(0, days, 365):
        part = [h[y:y + 365] for h in histories]
        n = sum(len(p) for p in part)
        rows = [r for p in part for r in p]

        def per(key: str, unit: float) -> float:
            return sum(r[key] for r in rows) / n * unit

        ends = [p[-1]["members"] for p in part]
        arounds = sorted(r["around"] for r in rows)
        lo, hi = arounds[len(arounds) // 20], arounds[-len(arounds) // 20 - 1]
        before = [-1] * len(part) if y == 0 else [
            next((i - 365 for i in range(364, -1, -1) if h[y - 365 + i]["joined"]), -365) for h in histories]
        gap = max(_longest_gap(p, b) for p, b in zip(part, before))
        gone = sum(r["gone"] for r in rows)
        lines.append(
            f"year {y // 365 + 1:<2}{per('joined', 7):>9.2f}{gap:>8}{per('fresh', 7):>7.2f}{per('left', MONTH):>7.1f}"
            f"{per('returned', MONTH):>6.1f}{per('gone', MONTH):>6.1f}"
            f"{(sum(r['gone_away'] for r in rows) / gone if gone else 0):>13.0%}"
            f"{statistics.mean(r['around'] for r in rows):>7.1f}{f'{lo}-{hi}':>8}"
            f"{statistics.mean(r['away'] for r in rows):>6.1f}"
            f"{f'{statistics.mean(ends):.0f} ({min(ends)}-{max(ends)})':>13}"
            f"{sum(bool(r['joined'] or r['left'] or r['returned'] or r['gone']) for r in rows) / n:>10.0%}")
    lines += ["", "gap max: the most days in a row without a newcomer. left: left for good; of them away: the share "
              "who left during a break. range: around on 90% of days."]
    return "\n".join(lines)
