"""Screen: what to watch in Sweden on the reader's services (Netflix, SVT Play and TV4 Play).

Every edition, without Claude (links editions too), from TMDB (where-to-watch data by JustWatch) and Netflix:
- New on each service: recent films and series with new episodes, most popular first, plus titles that
  just arrived in the service's catalog. Arrivals are found by comparing the service's best-known titles
  (most TMDB votes, a few pages) with a small snapshot kept in data/screen.json.
- Netflix's weekly top 10 for Sweden (Tudum), fetched again only once a newer week can exist.
- Older but great: high TMDB ratings from many votes, in rotation (least recently shown first).
Once a week (screen.picks.days, Fridays: Netflix's big release day), in full editions only, one Claude call
picks 6–8 titles from those lists with a short reason each. Between Fridays the pages show the latest picks.

A failing source never stops the run: every step is a row in the Harvest status. Without TMDB_API_KEY only
the top 10 is shown, without posters, and the status says so.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import desk, schedule
from .http import Client, FetchError
from .llm import LLM, LLMError
from .sources import Harvest, SourceStatus
from .sources import netflix, tmdb

MEMORY_FILE = "screen.json"
NEW_FLAGS = ("added", "new_film", "new_series", "new_episodes")
TYPE_WORDS = {"flatrate": "", "free": "free", "ads": "free with ads"}
LEAN = ("key", "id", "kind", "title", "original_title", "year", "date", "overview", "poster", "rating", "votes",
        "genres", "url", "on", "flag", "flag_date")


@dataclass
class Fetched:
    block: dict[str, Any]                                     # the edition's "screen" block (the lists)
    memory: dict[str, Any]                                    # data/screen.json after this run
    pool: list[dict[str, Any]] = field(default_factory=list)  # candidates for the picks, with service tags


@dataclass
class Outcome:
    picks: dict[str, Any] | None = None
    note: str = ""                # why there are no picks, when they were due


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("screen") or {}


def enabled(cfg: dict[str, Any]) -> bool:
    s = settings(cfg)
    return bool(s) and bool(s.get("enabled", True))


# ── memory: data/screen.json ─────────────────────────────────────────────────

def load_memory(data_dir: Path) -> dict[str, Any]:
    path = data_dir / MEMORY_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}


def save_memory(data_dir: Path, memory: dict[str, Any]) -> None:
    path = data_dir / MEMORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")


def _memory(m: dict[str, Any]) -> dict[str, Any]:
    for key in ("catalog", "since", "arrived", "shown"):
        m.setdefault(key, {})
    return m


def arrivals(mem: dict[str, Any], service: str, keys: list[str], today: dt.date, cfg: dict[str, Any]) -> list[str]:
    """Titles that are new to the service's snapshot today, recorded in mem["arrived"]. Updates the snapshot.

    The first day only records the snapshot, and so do the next `warmup_days` (JustWatch data can flicker
    at first). A title counts as new when it wasn't seen in the last `forget_days`, so one that drops out of
    the snapshot for a few days isn't new again when it's back. More than `max_per_day` at once is a data
    change (a provider renamed, a filter changed), not news: they are absorbed without being listed."""
    day = today.isoformat()
    cutoff = (today - dt.timedelta(days=int(cfg.get("forget_days", 45)))).isoformat()
    seen = {k: v for k, v in (mem["catalog"].get(service) or {}).items() if v >= cutoff}
    fresh = [k for k in dict.fromkeys(keys) if k not in seen]
    for k in keys:
        seen[k] = day
    mem["catalog"][service] = dict(sorted(seen.items()))
    since = mem["since"].get(service)
    if not since:
        mem["since"][service] = day
        return []
    if (today - dt.date.fromisoformat(since)).days < int(cfg.get("warmup_days", 2)):
        return []
    if len(fresh) > int(cfg.get("max_per_day", 20)):
        return []
    arrived = mem["arrived"].setdefault(service, {})
    for k in fresh:
        arrived.setdefault(k, day)
    return fresh


def rotation(keys: list[str], shown: dict[str, str], today: dt.date) -> list[str]:
    """Keys in the order to show them: never shown first, then the longest ago; ties in a shuffled order
    seeded by the date. Shown today counts as never shown, so a re-run picks the same titles."""
    rng = random.Random(today.isoformat())
    order = {k: rng.random() for k in sorted(set(keys))}
    day = today.isoformat()
    last = {k: ("" if shown.get(k, "") >= day else shown.get(k, "")) for k in order}
    return sorted(order, key=lambda k: (last[k], order[k]))


def top10_due(cached: dict[str, Any] | None, today: dt.date) -> bool:
    """Netflix publishes a Monday–Sunday week on the Tuesday after it (in the evening, Swedish time), so a
    newer list can exist from the second Wednesday after the cached week ended."""
    if not cached or not (cached.get("week") or {}).get("end") or not cached.get("films"):
        return True
    end = dt.date.fromisoformat(cached["week"]["end"])
    checked = dt.date.fromisoformat(cached.get("checked") or "1970-01-01")
    return today >= end + dt.timedelta(days=10) and checked < today


def interleave(*lists: list[Any]) -> list[Any]:
    out: list[Any] = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


def lean(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t[k] for k in LEAN if t.get(k) not in (None, "", [])}


def is_new(t: dict[str, Any], today: dt.date) -> bool:
    return t.get("flag") in NEW_FLAGS or bool(t.get("top10")) or (t.get("year") or 0) >= today.year - 1


def service_words(on: list[dict[str, Any]]) -> list[str]:
    """["Netflix", "SVT Play (free)"]: the services as Claude sees them."""
    return [o["service"] + (f" ({TYPE_WORDS[o['type']]})" if TYPE_WORDS.get(o.get("type") or "") else "")
            for o in on]


# ── the lists ────────────────────────────────────────────────────────────────

def fetch(cfg: dict[str, Any], client: Client, harvest: Harvest, key: str | None, memory: dict[str, Any],
          today: dt.date, want_pool: bool = False) -> Fetched:
    """Fetch and pick today's lists. `memory` (data/screen.json) isn't changed; the updated copy comes back
    to be saved with the edition. `want_pool` also tags extra titles for the picks."""
    s = settings(cfg)
    src = cfg.get("sources") or {}
    region = s.get("region", "SE")
    mem = _memory(copy.deepcopy(memory or {}))
    block: dict[str, Any] = {"region": region, "checked_at": harvest.fetched_at.isoformat(), "tmdb": False,
                             "services": [], "new": [], "classics": [], "top10": None}
    titles: dict[str, dict[str, Any]] = {}                 # every title fetched this run, by key

    def add(items: list[dict[str, Any]] | None) -> list[str]:
        keys = []
        for t in items or []:
            titles.setdefault(t["key"], {k: v for k, v in t.items() if k != "flag"})
            keys.append(t["key"])
        return list(dict.fromkeys(keys))

    tm: tmdb.TMDB | None = None
    services: list[tmdb.Service] = []
    if (src.get("tmdb") or {}).get("enabled"):
        if not key:
            harvest.status.append(SourceStatus("TMDB", False, skipped=True,
                                               error="TMDB_API_KEY not set; Screen shows only Netflix's top 10"))
        else:
            tm = tmdb.TMDB(client, key, region, s.get("language", "en-US"))

            def setup() -> tuple[list[tmdb.Service], list[str]]:
                found = tmdb.resolve(s.get("services") or [], tm.providers())
                tm.load_genres()
                return found

            got = harvest.run("TMDB providers", setup, count=lambda r: len(r[0]))
            if got is None:
                tm = None                                    # a bad key or TMDB down: no TMDB today
            else:
                services, missing = got
                for name in missing:
                    harvest.status.append(SourceStatus(
                        f"TMDB {name}", False, error=f"no provider named {name!r} in {region}; "
                                                     "set its ids under screen.services"))
    block["tmdb"] = bool(services)
    block["services"] = [{"name": svc.name, "types": svc.types} for svc in services]

    # new on each service: arrivals in the catalog snapshot first, then recent releases
    new_cfg, arr_cfg, cl_cfg = s.get("new") or {}, s.get("arrivals") or {}, s.get("classics") or {}
    recent: dict[str, dict[str, str]] = {}                  # service → {key: flag}
    catalog_keys: list[str] = []
    for svc in services:
        got = harvest.run(f"TMDB new on {svc.name}", lambda svc=svc: tm.new_releases(svc, today, new_cfg))
        recent[svc.name] = {t["key"]: t["flag"] for t in got or []}
        add(got)
        cat = harvest.run(f"TMDB {svc.name} catalog", lambda svc=svc: tm.catalog(svc, arr_cfg))
        if cat is not None:                                 # a failed fetch leaves the snapshot as it was
            keys = add(cat)
            catalog_keys += keys
            arrivals(mem, svc.name, keys, today, arr_cfg)

    keep = int(arr_cfg.get("keep_days", 14))
    per_service, max_added = int(new_cfg.get("per_service", 8)), int(arr_cfg.get("max_listed", 4))
    rows_by_service: dict[str, list[dict[str, Any]]] = {}
    for svc in services:
        arrived = {k: d for k, d in (mem["arrived"].get(svc.name) or {}).items()
                   if (today - dt.date.fromisoformat(d)).days < keep}
        mem["arrived"][svc.name] = arrived
        rows = [dict(titles[k], flag="added", flag_date=d, origin=svc.name)
                for k, d in sorted(arrived.items(), key=lambda kv: kv[1], reverse=True) if k in titles][:max_added]
        flags = recent.get(svc.name) or {}
        movies = [k for k in flags if k.startswith("movie:")]
        shows = [k for k in flags if k.startswith("tv:")]
        taken = {r["key"] for r in rows}
        rows += [dict(titles[k], flag=flags[k], origin=svc.name) for k in interleave(movies, shows) if k not in taken]
        rows_by_service[svc.name] = rows

    # older but great: the classics query plus the catalog titles that clear the same bar
    classic_order: list[str] = []
    if services:
        pool = harvest.run("TMDB older but great", lambda: tm.classics(services, today, cl_cfg))
        if pool is not None:
            keys = add(pool) + [k for k in catalog_keys if _classic(titles[k], today, cl_cfg)]
            classic_order = rotation(keys, mem["shown"], today)

    # Netflix's top 10 (weekly; no key), matched to TMDB for posters when there's a key
    nf = src.get("netflix_top10") or {}
    if nf.get("enabled"):
        cached = mem.get("top10")
        if top10_due(cached, today):
            got = harvest.run("Netflix top 10", lambda: netflix.top10(client, nf.get("country", "sweden")),
                              count=lambda r: len(r["films"]) + len(r["tv"]))
            if got:                                          # the same week again: keep its matches, try tomorrow
                end = lambda t: ((t or {}).get("week") or {}).get("end") or ""      # noqa: E731
                mem["top10"] = {**(got if end(got) > end(cached) or not cached else cached),
                                "checked": today.isoformat()}
        else:
            harvest.status.append(SourceStatus(
                "Netflix top 10", True, count=len(cached["films"]) + len(cached["tv"]), skipped=True,
                error=f"kept the week ending {cached['week']['end']}; a newer list can exist from "
                      f"{dt.date.fromisoformat(cached['week']['end']) + dt.timedelta(days=10)}"))
        top = mem.get("top10")
        if top and tm:
            todo = [r for r in top["films"] + top["tv"] if "match" not in r]
            if todo:
                harvest.run("TMDB top 10 matches", lambda: _match_top10(tm, todo),
                            count=lambda n: n)
        if top:
            block["top10"] = {k: top.get(k) for k in ("week", "url", "films", "tv")}

    # where to watch: which services carry each listed title, and how (one lookup per title)
    classics: list[dict[str, Any]] = []
    pool_rows: list[dict[str, Any]] = []
    if tm and services:
        count = int(cl_cfg.get("count", 8))
        looked: dict[str, tuple[str, list[dict[str, str]]] | None] = {}     # None: the lookup failed

        def where(key: str) -> tuple[str, list[dict[str, str]]] | None:
            if key not in looked:
                t = titles[key]
                try:
                    looked[key] = tm.where(t["kind"], t["id"], services)
                except FetchError:
                    looked[key] = None
            return looked[key]

        def tag(row: dict[str, Any]) -> dict[str, Any] | None:
            got = where(row["key"])
            if got is None:                                  # lookup failed: the list it came from
                return {**row, "on": [{"service": row["origin"], "type": None}]} if row.get("origin") else None
            link, on = got
            if not on and row.get("origin"):                 # JustWatch's lists and per-title data can differ
                on = [{"service": row["origin"], "type": None}]
            return {**row, "on": on, "url": link or row["url"]} if on else None

        def annotate() -> int:
            for svc in services:
                shown = [r for r in (tag(x) for x in rows_by_service[svc.name][:per_service]) if r]
                block["new"].append({"service": svc.name, "titles": [lean(r) for r in shown]})
            budget = count * 3                               # classics not on the services after all are skipped
            for k in classic_order:
                if len(classics) >= count or budget <= 0:
                    break
                budget -= 1
                row = tag(dict(titles[k], flag=None))
                if row:
                    classics.append(row)
            if want_pool:
                pool_rows.extend(_pool(cfg, titles, rows_by_service, classics, classic_order, block, tag))
            failed = sum(1 for k in looked if looked[k] is None)
            if looked and failed == len(looked):
                raise FetchError("every where-to-watch lookup failed")
            return len(looked)

        if harvest.run("TMDB where to watch", annotate, count=lambda n: n) is None and not block["new"]:
            block["new"] = [{"service": svc.name, "titles": [lean(dict(r, on=[{"service": svc.name, "type": None}]))
                                                              for r in rows_by_service[svc.name][:per_service]]}
                            for svc in services]
        for r in classics:
            mem["shown"][r["key"]] = today.isoformat()
        block["classics"] = [lean(r) for r in classics]
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    mem["shown"] = {k: v for k, v in sorted(mem["shown"].items()) if v >= cutoff}
    return Fetched(block, mem, pool_rows)


def _classic(t: dict[str, Any], today: dt.date, cfg: dict[str, Any]) -> bool:
    movie = t["kind"] == "movie"
    votes = int(cfg.get("min_votes_movie", 1500) if movie else cfg.get("min_votes_tv", 400))
    return (t.get("rating") or 0) >= float(cfg.get("min_rating", 7.5)) and (t.get("votes") or 0) >= votes \
        and bool(t.get("year")) and t["year"] <= today.year - int(cfg.get("min_age_years", 3))


def _match_top10(tm: tmdb.TMDB, rows: list[dict[str, Any]]) -> int:
    """Find each top-10 title on TMDB (poster, year, rating). Rows keep their match, or None, for the week."""
    found, failed = 0, 0
    for r in rows:
        try:
            t = tm.search(r["kind"], r.get("show") or r["title"])
        except FetchError:
            failed += 1                                      # tried again tomorrow
            continue
        r["match"] = lean({**t, "on": [{"service": "Netflix", "type": "flatrate"}]}) if t else None
        found += 1 if t else 0
    if rows and failed == len(rows):
        raise FetchError("every top-10 search failed")
    return found


def _pool(cfg: dict[str, Any], titles: dict[str, dict[str, Any]], rows_by_service: dict[str, list[dict[str, Any]]],
          classics: list[dict[str, Any]], classic_order: list[str], block: dict[str, Any],
          tag: Callable[[dict[str, Any]], dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Candidates for the picks of the week: what's new on each service, Netflix's top 10 and older titles,
    each with its service tags and why it's listed."""
    limit = int((settings(cfg).get("picks") or {}).get("candidates", 50))
    out: dict[str, dict[str, Any]] = {}

    def put(row: dict[str, Any] | None, why: str) -> None:
        if not row or not row.get("on"):
            return
        if row["key"] in out:
            out[row["key"]]["listed"].append(why)
        elif len(out) < limit:
            out[row["key"]] = {**row, "listed": [why]}

    top = block.get("top10") or {}
    for kind, word in (("tv", "series"), ("films", "films")):
        for r in top.get(kind) or []:
            if r.get("match"):
                put({**r["match"], "top10": r["rank"]}, f"Netflix top 10 in Sweden ({word}), #{r['rank']}")
    rows = interleave(*rows_by_service.values())
    for r in rows[: limit // 2]:
        put(tag(r), f"new on {r['origin']}")
    for r in classics:
        put(r, "older but great")
    shown = {r["key"] for r in classics}
    for k in classic_order:
        if len(out) >= limit:
            break
        if k not in shown:
            put(tag(dict(titles[k], flag=None)), "older but great")
    return list(out.values())


# ── the picks of the week (Claude) ───────────────────────────────────────────

def picks_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return settings(cfg).get("picks") or {}


def picks_due(cfg: dict[str, Any], day: dt.date, last: dt.date | None) -> bool:
    p = picks_settings(cfg)
    return enabled(cfg) and bool(p.get("enabled", True)) and schedule.weekly_due(
        day, p.get("days", ["fri"]), int(p.get("every_weeks", 1)), last)


def history(editions: list[dict[str, Any]], exclude: str = "") -> list[dict[str, Any]]:
    """Earlier picks, newest first."""
    return [{**ed["screen"]["picks"], "edition_id": ed["edition_id"]}
            for ed in sorted(editions, key=lambda e: e["edition_id"], reverse=True)
            if (ed.get("screen") or {}).get("picks") and ed["edition_id"] != exclude]


def last_picked(editions: list[dict[str, Any]], exclude: str = "") -> dt.date | None:
    hist = history(editions, exclude)
    return dt.date.fromisoformat(hist[0]["edition_id"][:10]) if hist else None


def write_picks(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], pool: list[dict[str, Any]],
                editions: list[dict[str, Any]], force: bool = False) -> Outcome:
    """The picks of the week for `edition`, if they're due (or forced). Never raises LLMError."""
    p = picks_settings(cfg)
    day = dt.date.fromisoformat(edition["edition_id"][:10])
    hist = history(editions, exclude=edition["edition_id"])
    last = dt.date.fromisoformat(hist[0]["edition_id"][:10]) if hist else None
    if not force and not picks_due(cfg, day, last):
        return Outcome()
    lo, hi = int(p.get("min", 6)), int(p.get("max", 8))
    weeks = int(p.get("repeat_weeks", 8))
    recent = {t["key"] for h in hist if (day - dt.date.fromisoformat(h["edition_id"][:10])).days < 7 * weeks
              for t in h.get("titles") or []}
    cands = {t["key"]: t for t in pool if t["key"] not in recent and t.get("on")}
    if len(cands) < lo:
        return Outcome(note=f"too few titles to pick from ({len(cands)})")
    material = {
        "today": day.isoformat(), "weekday": f"{day:%A}",
        "services": [service_words([{"service": s["name"], "type": t}])[0]
                     for s in (edition.get("screen") or {}).get("services") or [] for t in s["types"][:1]],
        "picks_wanted": f"{lo}-{hi}",
        "titles": [{
            "id": k, "kind": "film" if t["kind"] == "movie" else "series", "title": t["title"],
            **({"original_title": t["original_title"]} if t.get("original_title") else {}),
            "year": t.get("year"), "genres": t.get("genres") or [], "tmdb_rating": t.get("rating"),
            "votes": t.get("votes"), "overview": t.get("overview") or "", "on": service_words(t["on"]),
            "listed": t.get("listed") or [], "new": is_new(t, day),
        } for k, t in cands.items()],
    }
    try:
        out = desk.pick_screen(llm, cfg, material, lo, hi)
    except LLMError as exc:
        return Outcome(note=str(exc))
    items, used = [], set()
    for row in out.get("picks") or []:
        t = cands.get(row.get("id"))
        reason = " ".join((row.get("reason") or "").split())
        if t and reason and t["key"] not in used and len(items) < hi:
            used.add(t["key"])
            items.append({**lean(t), "reason": reason})
    if len(items) < min(lo, 4):
        return Outcome(note=f"only {len(items)} usable picks came back")
    return Outcome({"headline": " ".join((out.get("headline") or "").split()) or "This week's picks",
                    "dek": " ".join((out.get("dek") or "").split()), "titles": items,
                    "model": llm.model_for("screen")})


def summary(block: dict[str, Any]) -> str:
    """A line for the run report: what the lists hold."""
    parts = [f"{len(n['titles'])} new on {n['service']}" for n in block.get("new") or []]
    if block.get("classics"):
        parts.append(f"{len(block['classics'])} older")
    top = block.get("top10")
    if top:
        parts.append(f"top 10 week ending {(top.get('week') or {}).get('end', '?')}")
    return ", ".join(parts) or "nothing listed"
