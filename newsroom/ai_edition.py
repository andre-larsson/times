"""Full and reduced editions: discovery → triage → editor → full text → writers → assembly.

Failure handling (PLAN.md, "Run modes"):
- Discovery fails → noted in the reason; the edition goes on with the feeds alone.
- Triage or editor fails → AIUnavailable: the caller publishes a links edition instead.
- A writer fails, or AI work stops (credit error, per-run budget, two failures in a row) → the
  finished parts are kept, unwritten stories become plain briefs from the source headline, gaming and
  deals fall back to the rule-based blocks, and the edition is marked "partial".
"""

from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from . import desk, discover, links, rank
from .extract import fetch_texts, source_block
from .http import Client
from .llm import LLM, LLMError
from .seen import is_seen
from .sources import Harvest
from .text import canonical_url, excerpt, similarity, slugify, words

PICKS = {"popular": "popular", "hidden": "hidden_gem", "genre": "genre"}   # why a deal is in the list (deals.md)


class AIUnavailable(Exception):
    """AI couldn't produce the core of the paper; publish the links edition instead."""


@dataclass
class Result:
    edition: dict[str, Any]
    seen_urls: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def tier_limits(cfg: dict[str, Any], mode: str) -> dict[str, dict[str, Any]]:
    ed = cfg.get("edition") or {}
    limits = {t: dict(ed.get(t) or {}) for t in ("featured", "medium", "briefs")}
    defaults = {"featured": (1, 3), "medium": (3, 6), "briefs": (10, 20)}
    for t, (lo, hi) in defaults.items():
        limits[t].setdefault("min", lo)
        limits[t].setdefault("max", hi)
    if mode == "reduced":
        red = (cfg.get("llm") or {}).get("reduced") or {}
        limits["featured"]["max"] = min(limits["featured"]["max"], int(red.get("featured_max", 1)))
        limits["medium"]["max"] = min(limits["medium"]["max"], int(red.get("medium_max", 3)))
        limits["medium"]["min"] = min(limits["medium"]["min"], limits["medium"]["max"])
    return limits


def _age_hours(item, now: dt.datetime) -> float | None:
    return round((now - item.published_at).total_seconds() / 3600, 1) if item.published_at else None


def build(cfg: dict[str, Any], harvest: Harvest, edition_id: str, mode: str, llm: LLM, client: Client,
          seen: dict[str, str], recent: list[dict[str, Any]]) -> Result:
    now = harvest.fetched_at
    llm_cfg = cfg.get("llm") or {}
    search = cfg.get("search") or {}
    hn_cfg = (cfg.get("sources") or {}).get("hackernews") or {}
    problems: list[str] = []
    seen_urls: list[str] = []

    # 1. candidates: rule-ranked, unseen, all languages (triage translates)
    cands = rank.build_candidates(harvest.items, harvest.hn, now,
                                  max_age_hours=float(search.get("max_item_age_hours", 36)),
                                  min_points=int(hn_cfg.get("min_points", 100)))
    cands = [c for c in cands if not c.weak and not is_seen(seen, c.url)]
    cands = cands[: int(llm_cfg.get("max_candidates", 150))]

    # 1b. discovery (Opus + web search, full editions): important stories the feeds missed
    try:
        found, discovery = discover.for_edition(cfg, harvest, edition_id, mode, llm, seen, recent, now)
    except LLMError as exc:
        found, discovery = [], {"error": str(exc)[:200]}
        problems.append(f"discovery: {exc}")
    cands += [rank.Candidate(item=it, section=it.sections[0], words=words(it.title)) for it in found]
    if not cands:
        raise AIUnavailable("no new candidates to write about")
    by_id = {f"c{i + 1}": c for i, c in enumerate(cands)}

    # 2. triage (Haiku), in parallel chunks
    rows = [{
        "id": cid, "source": c.item.source, "title": c.item.title, "excerpt": excerpt(c.item.excerpt, 200),
        "language": c.item.language, "age_hours": _age_hours(c.item, now),
        "hn_points": (c.hn or {}).get("points"), "also_covered_by": sorted({a.source for a in c.also}),
        "rule_section": c.section,
    } for cid, c in by_id.items()]
    chunk = int(llm_cfg.get("triage_chunk", 40))
    chunks = [rows[i:i + chunk] for i in range(0, len(rows), chunk)]
    triaged: dict[str, dict[str, Any]] = {}
    for result in _parallel(llm_cfg, [lambda ch=ch: desk.triage(llm, cfg, ch) for ch in chunks]):
        if isinstance(result, LLMError):
            problems.append(f"triage: {result}")
            continue
        for t in result:
            if t.get("id") in by_id:
                triaged[t["id"]] = t
    if not triaged:
        raise AIUnavailable(f"triage failed ({'; '.join(problems) or 'no output'})")
    seen_urls += [by_id[i].url for i, t in triaged.items() if not t.get("keep")]

    # 3. editor (Opus): group kept items into events
    limits = tier_limits(cfg, mode)
    kept = {i: t for i, t in triaged.items() if t.get("keep")}
    events = _events(kept, by_id, now, limits)
    if not events:
        raise AIUnavailable("triage kept nothing worth printing")
    sent = [e for e in events.values() if e["section"] != "gaming" or e["newsworthiness"] >= 4.5]
    try:
        plan = desk.editor(llm, cfg, [e["prompt"] for e in sent], recent, limits)
    except LLMError as exc:
        raise AIUnavailable(f"editor failed: {exc}") from exc
    assignments = _assignments(plan, events, by_id, kept, limits)
    returned = {t: len(plan.get(t) or []) for t in ("featured", "medium", "briefs")}
    extra = _brief_top_up(assignments, sent, kept, recent, limits)
    if extra:
        problems.append(f"editor returned {returned['briefs']} briefs (min {limits['briefs']['min']}); "
                        f"added {len(extra)} from the triage ranking")
        assignments = _assignments({**plan, "briefs": (plan.get("briefs") or []) + extra}, events, by_id, kept, limits)
    editor_stats = {"events": len(sent), "returned": returned,
                    "kept": {t: len(assignments[t]) for t in assignments}, "briefs_added": len(extra)}
    if not assignments["featured"] and not assignments["medium"] and not assignments["briefs"]:
        raise AIUnavailable("the editor picked no stories")

    # 4. full text for featured and medium sources
    max_chars = int(search.get("max_fulltext_chars", 12000))
    urls = [s.url for a in assignments["featured"] + assignments["medium"] for s in a["items"]]
    texts = fetch_texts(client, urls, limit=max_chars)

    # 5. writers, in parallel
    gaming_base = links.gaming_blocks(cfg, harvest, rank.build_candidates(
        [i for i in harvest.items if i.language == "en"], harvest.hn, now))
    deals_base = links.deals_block(cfg, harvest)
    gaming_material, gaming_ids = _gaming_material(harvest, gaming_base, kept, by_id)
    deals_material, deal_ids = _deals_material(deals_base)

    jobs: list[tuple[str, Any, Callable[[], Any]]] = []
    for tier in ("featured", "medium"):
        for a in assignments[tier]:
            jobs.append((tier, a, lambda a=a, tier=tier: desk.write_story(
                llm, cfg, tier, _story_material(a, texts, now))))
    if assignments["briefs"]:
        brief_rows = [{"id": a["id"], "source": a["items"][0].source, "title": a["title_en"],
                       "excerpt": excerpt(a["items"][0].excerpt, 300), "kicker_hint": a["kicker"]}
                      for a in assignments["briefs"]]
        jobs.append(("briefs", None, lambda: desk.write_briefs(llm, cfg, brief_rows)))
    if any(gaming_material[k] for k in ("new_on_pc", "reviews", "watch", "news_candidates")):
        jobs.append(("gaming", None, lambda: desk.write_gaming(llm, cfg, gaming_material)))
    if deals_material["deals"]:
        jobs.append(("deals", None, lambda: desk.write_deals(llm, cfg, deals_material)))

    outputs = _parallel(llm_cfg, [j[2] for j in jobs])

    # 6. assemble
    stories: list[dict[str, Any]] = []
    slugs: set[str] = set()
    degraded = False
    brief_out: dict[str, dict[str, Any]] = {}
    gaming = gaming_base
    deals = deals_base
    for (task, a, _), out in zip(jobs, outputs):
        failed = isinstance(out, LLMError)
        if failed:
            problems.append(f"{task}: {out}")
            degraded = True
        if task in ("featured", "medium"):
            stories.append(_plain_brief(a, slugs) if failed else _story(a, task, out, slugs))
            if not failed:
                seen_urls += [s.url for s in a["items"]]
        elif task == "briefs" and not failed:
            brief_out = {b["id"]: b for b in out}
        elif task == "gaming" and not failed:
            gaming = _apply_gaming(gaming_base, out, gaming_ids)
            seen_urls += [gaming_ids[n["id"]]["url"] for n in out.get("news", []) if n.get("id") in gaming_ids]
        elif task == "deals" and not failed:
            deals = _apply_deals(deals_base, out, deal_ids)

    for a in assignments["briefs"]:
        b = brief_out.get(a["id"])
        if b:
            stories.append(_brief(a, b, slugs))
            seen_urls += [a["items"][0].url]
        else:                                        # failed call, or the model skipped it
            stories.append(_plain_brief(a, slugs))

    # lead first, then by tier order
    lead_event = plan.get("lead")
    order = {"featured": 0, "medium": 1, "brief": 2}
    stories.sort(key=lambda s: (order[s["tier"]], s.get("_event") != lead_event))
    if not any(s["tier"] == "featured" for s in stories):
        promote = next((s for s in stories if s["tier"] == "medium"), None)
        if promote:                                  # the page always has a lead
            promote["tier"] = "featured"
    for i, s in enumerate(stories, 1):
        s["id"] = f"s{i}"
        if s["tier"] == "featured" and (s.get("_event") == lead_event or i == 1):
            s["lead"] = True
        s.pop("_event", None)
    leads = [s for s in stories if s.get("lead")]
    for s in leads[1:]:
        s.pop("lead")

    hn_top = links.top_hn(harvest.hn, int(hn_cfg.get("min_points", 100)),
                          int((cfg.get("links") or {}).get("hn_top", 10)))
    edition = {
        "edition_id": edition_id,
        "generated_at": now.isoformat(),
        "mode": "partial" if degraded or llm.tally.stopped else mode,
        "reason": "; ".join(problems)[:500],
        "llm": {"backend": llm.backend, **llm.tally.summary()},
        "stories": stories,
        "links": [],
        "hn_top": hn_top,
        "gaming": gaming,
        "deals": deals,
        "sources": [s.__dict__ for s in harvest.status],
        "editor": editor_stats,
        **({"discovery": discovery} if discovery else {}),
    }
    edition["llm"]["estimated_usd"] = edition["llm"]["equivalent_usd"]
    return Result(edition, seen_urls, problems)


# ── helpers ──────────────────────────────────────────────────────────────────

def _parallel(llm_cfg: dict[str, Any], fns: list[Callable[[], Any]]) -> list[Any]:
    """Run calls concurrently; an LLMError is returned in place of that call's result."""
    def safe(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except LLMError as exc:
            return exc

    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, int(llm_cfg.get("parallel", 3)))) as pool:
        return list(pool.map(safe, fns))


def _events(kept: dict[str, dict[str, Any]], by_id: dict[str, rank.Candidate], now: dt.datetime,
            limits: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bar = float(limits["briefs"].get("min_newsworthiness", 2.5))
    events: dict[str, dict[str, Any]] = {}
    for cid, t in kept.items():
        key = (t.get("event") or cid).strip().lower()
        e = events.setdefault(key, {"event": key, "ids": [], "section": t["section"], "newsworthiness": 0.0})
        e["ids"].append(cid)
        e["newsworthiness"] = max(e["newsworthiness"], float(t.get("newsworthiness") or 0))
    out = {}
    for key, e in sorted(events.items(), key=lambda kv: -kv[1]["newsworthiness"]):
        if e["newsworthiness"] < bar:
            continue
        e["prompt"] = {
            "event": key, "section": e["section"], "newsworthiness": e["newsworthiness"],
            "candidates": [{
                "id": cid, "source": by_id[cid].item.source, "title": kept[cid].get("title_en") or by_id[cid].item.title,
                "kicker": kept[cid].get("kicker"), "excerpt": excerpt(by_id[cid].item.excerpt, 240),
                "age_hours": _age_hours(by_id[cid].item, now), "hn_points": (by_id[cid].hn or {}).get("points"),
                "also_covered_by": sorted({a.source for a in by_id[cid].also}),
            } for cid in e["ids"]],
        }
        out[key] = e
        if len(out) >= 80:
            break
    return out


def _brief_top_up(assignments: dict[str, list[dict]], sent: list[dict[str, Any]], kept: dict[str, dict[str, Any]],
                  recent: list[dict[str, Any]], limits: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Plan rows that bring the briefs up to their minimum when the editor returned too few.

    On 2026-11-06 the editor (API, Opus) returned no briefs at all from 50 events above the bar; a replay
    of the same step returned 20. The extra briefs are the best events the editor saw but didn't use. All
    of them clear the briefs bar, so a quiet day still prints fewer. AI and Tech only, and nothing that
    looks like a recent edition's headline (the same-story rule from ranking).
    """
    short = int(limits["briefs"]["min"]) - len(assignments["briefs"])
    if short <= 0:
        return []
    used = {a["event"] for rows in assignments.values() for a in rows}
    old = [words(h) for ed in recent for h in ed.get("headlines", [])]
    rows = []
    for e in sent:                                   # best first (events are sorted by newsworthiness)
        if len(rows) >= short:
            break
        if e["event"] in used or e["section"] == "gaming":
            continue
        cid = e["ids"][0]
        title = words(kept.get(cid, {}).get("title_en") or e["prompt"]["candidates"][0]["title"])
        if any(len(title & w) >= 3 and similarity(title, w) >= 0.6 for w in old):
            continue
        rows.append({"event": e["event"], "source_id": cid})
    return rows


def _assignments(plan: dict[str, Any], events: dict[str, dict[str, Any]], by_id: dict[str, rank.Candidate],
                 kept: dict[str, dict[str, Any]], limits: dict[str, dict[str, Any]]) -> dict[str, list[dict]]:
    """Turn the editor's plan into validated assignments (known ids, each event once, within limits)."""
    used: set[str] = set()
    out: dict[str, list[dict]] = {"featured": [], "medium": [], "briefs": []}
    max_sources = int(limits["featured"].get("max_sources", 3))
    for tier in ("featured", "medium", "briefs"):
        for row in plan.get(tier, []):
            key = (row.get("event") or "").strip().lower()
            if key not in events or key in used or len(out[tier]) >= int(limits[tier]["max"]):
                continue
            ids = row.get("source_ids") or ([row["source_id"]] if row.get("source_id") else [])
            ids = [i for i in ids if i in by_id] or events[key]["ids"][:1]
            first = by_id[ids[0]]
            items = [by_id[i].item for i in ids]
            items += [a for i in ids for a in by_id[i].also]          # same-story duplicates from ranking
            uniq, seen_urls = [], set()
            for it in items:
                if canonical_url(it.url) not in seen_urls:
                    seen_urls.add(canonical_url(it.url))
                    uniq.append(it)
            used.add(key)
            out[tier].append({
                "id": f"{tier[0]}{len(out[tier]) + 1}", "event": key, "section": events[key]["section"],
                "kicker": kept.get(ids[0], {}).get("kicker") or "",
                "title_en": kept.get(ids[0], {}).get("title_en") or first.item.title,
                "newsworthiness": events[key]["newsworthiness"], "angle": row.get("angle", ""),
                "breaking": bool(row.get("breaking")) and events[key]["newsworthiness"] >= 5,
                "items": uniq[: max_sources if tier == "featured" else 2],
                "hn": next((by_id[i].hn for i in ids if by_id[i].hn), None),
            })
    return out


def _story_material(a: dict[str, Any], texts: dict[str, str], now: dt.datetime) -> dict[str, Any]:
    return {
        "angle": a["angle"], "section": a["section"], "kicker_hint": a["kicker"], "today": now.date().isoformat(),
        "hacker_news": a["hn"],
        "sources": [source_block({"source": it.source, "title": it.title, "url": it.url, "excerpt": it.excerpt,
                                  "published_at": it.published_at.isoformat() if it.published_at else None},
                                 texts.get(it.url, "")) for it in a["items"]],
    }


def _unique_slug(text: str, slugs: set[str]) -> str:
    base = slugify(text)
    slug, n = base, 2
    while slug in slugs:
        slug, n = f"{base}-{n}", n + 1
    slugs.add(slug)
    return slug


def _common(a: dict[str, Any], slugs: set[str], headline: str) -> dict[str, Any]:
    main = a["items"][0]
    s = {
        "slug": _unique_slug(headline, slugs), "section": a["section"], "newsworthiness": a["newsworthiness"],
        "published_at": main.published_at.isoformat() if main.published_at else None,
        "sources": [{"name": it.source, "title": it.title, "url": it.url} for it in a["items"]],
        "_event": a["event"],
    }
    if a.get("hn"):
        s["hn"] = a["hn"]
    return s


def _story(a: dict[str, Any], tier: str, out: dict[str, Any], slugs: set[str]) -> dict[str, Any]:
    s = _common(a, slugs, out["headline"])
    s.update(tier=tier, kicker=out.get("kicker") or a["kicker"], headline=out["headline"], dek=out.get("dek", ""),
             body=out.get("body", ""), key_points=[p for p in out.get("key_points", []) if p][:4])
    if tier == "featured":
        s["breaking"] = a["breaking"]
        s["why_it_matters"] = out.get("why_it_matters", "")
        if is_cover_figure(out.get("cover_figure", "")):
            s["cover"] = {"style": "type", "figure": out["cover_figure"].strip(),
                          "caption": out.get("cover_caption", "")}
    return s


# A number, optionally signed, approximate or in a currency, followed by any unit: "40%", "$6.34B", "2 pts",
# "~70B", "1.2 million". Words ("All", "Zero") and names that merely contain a digit ("GPT-5") are rejected.
_COVER_FIGURE = re.compile(r"[+\-−~≈<>]?[$€£¥]?\d")


def is_cover_figure(figure: str) -> bool:
    """The writer's cover figure is shown only when it starts with a number; otherwise the kicker cover is used."""
    return bool(_COVER_FIGURE.match(figure.strip()))


def _brief(a: dict[str, Any], b: dict[str, Any], slugs: set[str]) -> dict[str, Any]:
    s = _common(a, slugs, b["headline"])
    s.update(tier="brief", kicker=b.get("kicker") or a["kicker"], headline=b["headline"], body=b.get("body", ""))
    return s


def _plain_brief(a: dict[str, Any], slugs: set[str]) -> dict[str, Any]:
    """No AI text available: the source's own headline and excerpt, linking straight to it."""
    s = _common(a, slugs, a["title_en"])
    s.update(tier="brief", kicker=a["kicker"], headline=a["title_en"],
             body=excerpt(a["items"][0].excerpt, 200) if a["items"][0].language == "en" else "")
    return s


def _gaming_material(harvest: Harvest, base: dict[str, Any], kept: dict[str, dict[str, Any]],
                     by_id: dict[str, rank.Candidate]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    steam = {g["appid"]: g for g in harvest.steam.get("new_releases") or []}
    items = {canonical_url(i.url): i for i in harvest.items}
    news_ids: dict[str, dict[str, Any]] = {}
    gaming_kept = sorted(((cid, t) for cid, t in kept.items() if t.get("section") == "gaming"),
                         key=lambda kv: -float(kv[1].get("newsworthiness") or 0))[:20]
    for cid, t in gaming_kept:
        it = by_id[cid].item
        news_ids[cid] = {"id": cid, "source": it.source, "title": it.title, "excerpt": excerpt(it.excerpt, 240),
                         "language": it.language, "newsworthiness": t.get("newsworthiness"), "url": it.url,
                         "sources": [{"name": it.source, "url": it.url}]
                                    + [{"name": a.source, "url": a.url} for a in by_id[cid].also]}
    material = {
        "new_on_pc": [{
            "appid": g["appid"], "title": g["title"], "steam_rating": g.get("steam_rating"),
            "review_count": steam.get(g["appid"], {}).get("review_count"), "release_date": g.get("release_date"),
            "early_access": g.get("early_access"),
            "description": steam.get(g["appid"], {}).get("short_description", ""),
            **_critic_numbers(g.get("critics")),
        } for g in base.get("new_on_pc", [])],
        "reviews": [{
            "id": r["id"], "game": r["game"], "outlet": r["outlet"], "score": r.get("score"),
            **_critic_numbers(r.get("critics")),
            "outlet_headline": (items.get(canonical_url(r["url"])) or _Empty).title,
            "excerpt": excerpt((items.get(canonical_url(r["url"])) or _Empty).excerpt, 300),
            "language": (items.get(canonical_url(r["url"])) or _Empty).language,
        } for r in base.get("reviews", [])],
        "watch": [{
            "url": v["url"], "channel": v["channel"], "title": v["title"],
            "description": excerpt((items.get(canonical_url(v["url"])) or _Empty).extra.get("description", ""), 300),
        } for v in base.get("watch", [])],
        "news_candidates": [{k: v for k, v in n.items() if k not in ("url", "sources")} for n in news_ids.values()],
    }
    return material, news_ids


def _critic_numbers(critics: dict[str, Any] | None) -> dict[str, Any]:
    """{"critics": {"opencritic": {"score": 88, "critics": 69}, …}} for the material, or nothing."""
    if not critics:
        return {}
    return {"critics": {k: {"score": v["score"], "critics": v.get("count")} for k, v in critics.items()}}


class _Empty:
    title = ""
    excerpt = ""
    language = "en"
    extra: dict[str, Any] = {}


def _apply_gaming(base: dict[str, Any], out: dict[str, Any], news_ids: dict[str, dict[str, Any]]) -> dict[str, Any]:
    g = {k: [dict(x) for x in v] if isinstance(v, list) else v for k, v in base.items()}
    blurbs = {x["appid"]: x["blurb"] for x in out.get("new_on_pc", [])}
    for game in g.get("new_on_pc", []):
        if blurbs.get(game["appid"]):
            game["blurb"] = blurbs[game["appid"]]
    verdicts = {x["id"]: x["verdict"] for x in out.get("reviews", [])}
    for r in g.get("reviews", []):
        if verdicts.get(r["id"]):
            r["verdict"] = verdicts[r["id"]]
    video = {x["url"]: x["blurb"] for x in out.get("watch", [])}
    for v in g.get("watch", []):
        if video.get(v["url"]):
            v["blurb"] = video[v["url"]]
    spotlight_ids = {i for s in out.get("console_spotlight", []) for i in s.get("ids", [])}
    news = [{"headline": n["headline"], "summary": n.get("summary", ""), "url": news_ids[n["id"]]["url"],
             "source": news_ids[n["id"]]["source"]}
            for n in out.get("news", []) if n.get("id") in news_ids and n["id"] not in spotlight_ids]
    if news:
        g["news"] = news
    spotlight = []
    for s in out.get("console_spotlight", []):
        ids = [i for i in s.get("ids", []) if i in news_ids]
        if ids:
            spotlight.append({"game": s.get("game", ""), "platforms": s.get("platforms", []),
                              "headline": s["headline"], "summary": s.get("summary", ""),
                              "sources": [src for i in ids for src in news_ids[i]["sources"]][:3]})
    g["console_spotlight"] = spotlight
    return g


def _deals_material(base: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    ids = {f"d{i + 1}": d for i, d in enumerate(base.get("more", []))}
    currency = next((d.get("currency") for d in ids.values() if d.get("currency")), "EUR")
    history = base.get("source") == "itad"            # Steam specials carry no price history
    material = {"currency": currency, "checked_at": base.get("checked_at"), "source": base.get("source"), "deals": [{
        "id": did, "game": d["game"], "shop": d["shop"], "price": d["price"], "regular": d["regular"],
        "cut_percent": d["cut"], "lowest_ever": d.get("lowest_ever") if history else None,
        "steam_rating": d.get("steam_rating"),
        "metascore": d.get("metascore"), "ends": d.get("expires"),
        **({"pick": PICKS[d["pick"]]} if d.get("pick") in PICKS else {}),
        **({"genre": d["genre"]} if d.get("genre") else {}),
        **({"tags": d["tags"]} if d.get("tags") else {}),
    } for did, d in ids.items()]}
    return material, ids


def _apply_deals(base: dict[str, Any], out: dict[str, Any], ids: dict[str, dict[str, Any]]) -> dict[str, Any]:
    featured, used = [], set()
    for f in out.get("featured", []):
        d = ids.get(f.get("id"))
        if d and f["id"] not in used:
            used.add(f["id"])
            featured.append({**d, "headline": f["headline"], "body": f.get("body", ""), "verdict": f.get("verdict")})
    advice = {m["id"]: m for m in out.get("more", [])}
    more = []
    for did, d in ids.items():
        if did in used:
            continue
        m = advice.get(did)
        more.append({**d, **({"advice": m["advice"], "verdict": m.get("verdict")} if m else {})})
    return {**base, "featured": featured, "more": more}
