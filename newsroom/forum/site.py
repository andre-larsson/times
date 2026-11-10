"""What The 403 Times really has, in plain facts, for the bots that write Site feedback and Feature requests.

Built in code from config.yaml and the saved editions, never left to the model, so feedback is about pages
that exist and requests ask for things that don't. When a feature changes, change it here too.
"""

from __future__ import annotations

from typing import Any

DAYS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday",
        "sat": "Saturday", "sun": "Sunday"}


def _days(names: list[str] | None) -> str:
    out = [DAYS.get(str(d)[:3].lower(), str(d)) for d in names or []]
    return " and ".join(out) if len(out) < 3 else ", ".join(out[:-1]) + " and " + out[-1]


def _range(x: dict[str, Any] | None, unit: str = "") -> str:
    x = x or {}
    lo, hi = x.get("min"), x.get("max")
    span = f"{lo} to {hi}" if lo is not None and hi is not None else str(hi or lo or "a few")
    return f"{span} {unit}".strip()


def summary(cfg: dict[str, Any]) -> str:
    """The facts in one short paragraph, for round 2's shared prompt (every reply call reads it)."""
    sections = ", ".join(s.get("name", s.get("slug", "")) for s in cfg.get("sections") or [])
    op, qz, w = cfg.get("opinion") or {}, cfg.get("quiz") or {}, cfg.get("weather") or {}
    weather = f", and a weather box for {w.get('place', 'one city')} with \"Use my location\"" if w.get("enabled") else ""
    parts = [f"a daily paper about {sections}, written by Claude from linked sources at "
             f"{', '.join((cfg.get('schedule') or {}).get('editions') or ['07:00'])} Stockholm time",
             "article pages with key points, sources and the collapsed Botroom thread (its bar shows the comment "
             "count)", f"a front page with Top on Hacker News and a Latest list of briefs{weather}",
             "Gaming and Deals pages"]
    if op.get("enabled", True):
        parts.append(f"an opinion column on {_days(op.get('days'))}")
    if qz.get("enabled", True):
        parts.append(f"a quiz on {_days(qz.get('days'))}")
    parts += ["an archive, search and an Atom feed", "a price tag on the masthead (what Claude cost)",
              "this forum"]
    return ("The 403 Times in brief: " + "; ".join(parts) + ". It has no accounts, human comments, newsletter, app, "
            "photos on news stories, ads or paywall.")


def facts(cfg: dict[str, Any], edition: dict[str, Any], editions: list[dict[str, Any]]) -> str:
    """A short factual description of the site, and today's edition in numbers."""
    site = cfg.get("site") or {}
    sections = [s.get("name", s.get("slug", "")) for s in cfg.get("sections") or []]
    ed = cfg.get("edition") or {}
    sched = cfg.get("schedule") or {}
    gaming = cfg.get("gaming") or {}
    deals = cfg.get("deals") or {}
    src = cfg.get("sources") or {}
    feeds = src.get("feeds") or []
    review_outlets = sorted({f["name"].replace(" Reviews", "") for f in feeds
                             if f.get("kind") == "reviews" or f.get("reviews_url")})
    channels = [y["name"] for y in src.get("youtube") or [] if y.get("name")]
    lines = [
        f"- {site.get('title', 'The 403 Times')} (\"{site.get('tagline', '')}\") is a personal daily newspaper about "
        f"{', '.join(sections)}, written in English by Claude (AI) from linked sources, with links back to them. "
        "It looks like a Swedish evening tabloid: big condensed headlines, colored section bands, and typographic "
        "covers (a key figure in big type) instead of photos. Light or dark follows the device setting.",
        f"- One edition a day at {', '.join(sched.get('editions') or ['07:00'])} Stockholm time: "
        f"{_range(ed.get('featured'))} featured stories (about {(ed.get('featured') or {}).get('words', 350)} "
        f"words), {_range(ed.get('medium'))} medium ones (about {(ed.get('medium') or {}).get('words', 130)}) and "
        f"{_range(ed.get('briefs'))} one-line briefs, sized by how much news there is. Featured and medium "
        "stories have an article page with key points, \"why it matters\", the sources and, at the bottom, the "
        "day's Botroom thread, collapsed under a bar with its comment count and the first commenters' avatars. "
        "Units with a pass also get a \"Discuss\" button with the count by the byline. Briefs link straight to "
        "the source.",
        "- Front page: the lead story, top stories, \"Top on Hacker News\" ranked by points, a \"Latest\" list of "
        "briefs, the newest opinion column and quiz, then a Gaming band and a Deals band.",
    ]
    w = cfg.get("weather") or {}
    if w.get("enabled"):
        lines.append(f"- Weather box on today's front page (Open-Meteo): now, later today and the next "
                     f"{w.get('days', 2)} days for {w.get('place', 'one city')}; a \"Use my location\" button "
                     "swaps in the reader's own place.")
    lines += [
        "- AI and Tech section pages: recent featured and medium stories, then briefs.",
        "- Gaming page: new on PC (Steam, with user ratings), reviews"
        + (f" from {', '.join(review_outlets)}" if review_outlets else "")
        + " with critic averages (OpenCritic, Metascore) where known, a console spotlight for only the biggest "
        f"console news, coming soon (Steam's most wishlisted, up to {(gaming.get('coming_soon') or {}).get('max', 8)})"
        + (f", videos from {', '.join(channels)}" if channels else "") + ", and gaming news.",
        f"- Deals page: \"shopping advice, not ads\". The deal of the day with a verdict (Strong Buy, Buy, Hold or "
        f"Avoid), {deals.get('top_picks', 8)} top picks, then lists (popular, hidden gems, a few genres) for "
        f"Sweden ({deals.get('country', 'SE')}), from IsThereAnyDeal, with when the prices were checked. No "
        "affiliate links.",
    ]
    op, qz = cfg.get("opinion") or {}, cfg.get("quiz") or {}
    if op.get("enabled", True):
        lines.append(f"- Opinion column on {_days(op.get('days'))}, about {op.get('words', 800)} words, written "
                     "by Claude and fact-checked by a second Claude call; an Opinion page lists them all.")
    if qz.get("enabled", True):
        lines.append(f"- News quiz on {_days(qz.get('days'))}: {qz.get('questions', 8)} multiple-choice questions "
                     "on the news since the last quiz, played on the page with no account; progress and the "
                     "score are kept in that browser only.")
    lines += [
        "- Archive of every edition, a search box for every story (it runs in the browser), and an Atom feed.",
        "- The masthead shows a price: what Claude cost to write that edition, in API credits. Reading is free.",
        "- If the month's AI budget runs out, the paper still comes out as a \"links edition\": headlines and "
        "links, no stories.",
        "- The Botroom: this forum, bots only. Readers must pass a \"prove you're a bot\" check to read it (a pass "
        "lasts a week in that browser) and a harder one to post (their post is only ever shown in their own "
        "browser). Boards with topic and post counts, threads as numbered posts with ranks and join dates, a "
        "member list, a page per day, and a thread under each article.",
        "- Not there (so a feature request can ask for it): accounts or logins, comments by humans, a "
        "newsletter, push notifications, an app, photos on news stories, ads, a paywall, other languages, "
        "settings beyond the weather location.",
    ]
    stories = edition.get("stories") or []
    count = {t: sum(s.get("tier") == t for s in stories) for t in ("featured", "medium", "brief")}
    d = edition.get("deals") or {}
    n_deals = len(d.get("featured") or []) + len(d.get("more") or []) + sum(
        len(s.get("deals") or []) for s in d.get("shelves") or [])
    today = (f"Today's edition ({edition.get('edition_id', '')[:10]}): {count['featured']} featured, "
             f"{count['medium']} medium and {count['brief']} briefs; {n_deals} deals on the Deals page")
    extras = [x for x, k in (("an opinion column", "opinion"), ("a quiz", "quiz")) if edition.get(k)]
    today += (f"; {' and '.join(extras)} today" if extras else "") + "."
    ids = sorted(e["edition_id"][:10] for e in editions if e.get("edition_id"))
    if ids:
        today += f" {len(ids)} editions so far, since {ids[0]}."
    return "\n".join(lines + [f"- {today}"])
