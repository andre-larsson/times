"""Render edition JSON files into the static site (_site/)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape

from . import ROOT, forum
from . import deals as deal_days
from .forum import look as forum_look
from .forum import roster as forum_roster
from .search import build_index
from .text import slugify

TIERS = ("featured", "medium", "brief")
PAGE_TIERS = ("featured", "medium")            # tiers that get their own article page
AI_SECTIONS = ("ai", "tech")                   # sections built from tiered stories
OPINION_SECTION = {"slug": "opinion", "name": "Opinion",
                   "blurb": "Columns by Claude (AI): arguments built on the paper's reporting."}
QUIZ_SECTION = {"slug": "quiz", "name": "Quiz",
                "blurb": "Twice a week: how much of the news did you catch? Questions by Claude (AI)."}
CURRENCY_FORMATS = {"EUR": "€{:.2f}", "USD": "${:.2f}", "GBP": "£{:.2f}", "SEK": "{:.0f} kr"}
SCORE = re.compile(r"^(\d{1,3}(?:\.\d{1,2})?)(%|/\d{1,3})?$")     # a review score: "8.5/10", "90%", "3/5", "82"
POSITIVE_RATINGS = {"overwhelmingly positive", "very positive", "positive", "mostly positive"}
NEGATIVE_RATINGS = {"mostly negative", "negative", "very negative", "overwhelmingly negative"}
VERDICTS = {"strong_buy": ("▲▲", "Strong Buy"), "buy": ("▲", "Buy"), "hold": ("◆", "Hold"),
            "avoid": ("▼", "Avoid")}                    # deal ratings: symbol and word, never color alone


# ── helpers ──────────────────────────────────────────────────────────────────

def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    ts = dt.datetime.fromisoformat(str(value))
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def article_path(edition_id: str, slug: str) -> str:
    year, month, day = edition_id.split("-")[:3]
    return f"{year}/{month}/{day}/{slug}/"


def load_editions(data_dir: Path) -> list[dict[str, Any]]:
    editions = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((data_dir / "editions").rglob("*.json"))]
    editions.sort(key=lambda e: e["edition_id"])
    return editions


def quote_slot(paragraphs: list[str], quote: str) -> int:
    """After which paragraph (1-based) a pull quote goes: not next to the paragraph it's taken from.

    0 means no pull quote (no quote, a short column, or no slot far enough from the source).
    """
    if not quote or len(paragraphs) < 4:
        return 0
    source = next((i for i, p in enumerate(paragraphs) if quote in p), None)
    for after in range(2, len(paragraphs) - 1):                  # between paragraphs[after-1] and [after]
        if source not in (after - 1, after):
            return after
    return 0


def link_reviews(gaming: dict[str, Any]) -> dict[str, Any]:
    """Attach each new game's reviews (by id) so templates can list them."""
    by_id = {r["id"]: r for r in gaming.get("reviews", []) if r.get("id")}
    for g in gaming.get("new_on_pc", []):
        g["reviews"] = [by_id[i] for i in g.get("review_ids", []) if i in by_id]
    return gaming


VERDICT_RANK = {"strong_buy": 0, "buy": 1, "hold": 3, "avoid": 4}   # no rating (links edition) sits after Buy


def deals_view(deals: dict[str, Any], top_n: int) -> dict[str, Any]:
    """The deals as the pages show them, ranked: the deal(s) of the day, the top picks (the best-rated
    `top_n`), then the rest by list (Popular, Hidden gems, each genre): its rated deals, ranked, and its
    unrated ones (`more`, the Deals page's "More" disclosure). Within a rating the list keeps its own order,
    which interleaves the lists. Every game appears once."""
    rated = sorted(deals.get("more") or [], key=lambda d: VERDICT_RANK.get(d.get("verdict") or "", 2))
    lists: dict[str, dict[str, Any]] = {}

    def lst(name: str) -> dict[str, Any]:
        return lists.setdefault(name, {"name": name, "slug": slugify(name), "rated": [], "more": []})

    for shelf in deals.get("shelves") or []:
        lst(shelf["name"])["more"] += shelf.get("deals") or []
    for d in rated[top_n:]:
        name = "Hidden gems" if d.get("pick") == "hidden" else d.get("genre") or "Popular"
        lst(name)["rated"].append(d)
    shown = [x for x in lists.values() if x["rated"] or x["more"]]
    return {
        "featured": deals.get("featured") or [], "top": rated[:top_n], "lists": shown,
        "count": len(deals.get("featured") or []) + len(rated) + sum(len(x["more"]) for x in shown),
    }


def _guard_out_dir(out_dir: Path) -> None:
    """Refuse to wipe anything that looks like the project itself."""
    out, root = out_dir.resolve(), ROOT.resolve()
    if out == root or out in root.parents or (out / "config.yaml").exists() or (out / ".git").exists():
        raise SystemExit(f"Refusing to use {out_dir} as output: it looks like a project directory")


# ── site builder ─────────────────────────────────────────────────────────────

class SiteBuilder:
    def __init__(self, cfg: dict[str, Any], out_dir: Path, preview: bool):
        self.cfg = cfg
        self.site = cfg["site"]
        self.base = self.site["base_path"]
        self.tz = ZoneInfo(cfg["schedule"]["timezone"])
        self.sections = {s["slug"]: s for s in cfg["sections"]}
        self.out = out_dir
        self.pages = 0
        self.now = dt.datetime.now(dt.timezone.utc)
        self.columns: list[dict[str, Any]] = []         # opinion columns, newest first
        self.quizzes: list[dict[str, Any]] = []         # quizzes, newest first
        self.front_days = int((cfg.get("opinion") or {}).get("front_days", 7))
        self.quiz_days = int((cfg.get("quiz") or {}).get("front_days", 4))
        weather = cfg.get("weather") or {}
        self.weather = weather if weather.get("enabled") else None   # live in the browser: today's front page only

        css = (ROOT / "static" / "style.css").read_bytes()
        js = b"".join(p.read_bytes() for p in sorted((ROOT / "static").glob("*.js")))
        self.nav = [("front", "Front", self.url(""))] + [
            (s["slug"], s["name"], self.url(f"{s['slug']}/")) for s in cfg["sections"]
        ] + [("archive", "Archive", self.url("archive/")), ("search", "Search", self.url("search/"))]

        self.env = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=ChainableUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(
            url=self.url, site=self.site, sections=self.sections, nav=self.nav, preview=preview,
            section_name=self.section_name, build_id=hashlib.sha1(css).hexdigest()[:8],
            js_id=hashlib.sha1(js).hexdigest()[:8],
            verdicts=VERDICTS, edition_time=(cfg["schedule"].get("editions") or [""])[0],
            deals_view=lambda deals: deals_view(deals or {}, int((cfg.get("deals") or {}).get("top_picks", 8))),
        )
        self.env.globals["deals_checked"] = self.deals_checked       # the deals labels: checked when, next check
        self.env.filters.update(
            local=self.local, date_long=self.date_long, date_short=self.date_short,
            date_when=self.date_when, time=self.time, iso=self.iso, num=self.num, money=self.money,
            paragraphs=self.paragraphs, domain=self.domain, rating_class=self.rating_class,
            edition_name=self.edition_name, article_url=self.article_url, when=self.when,
            score_parts=self.score_parts, price=self.price, slug=slugify,
        )

    # urls and names
    def url(self, path: str = "") -> str:
        return self.base + path.lstrip("/")

    def section_name(self, slug: str) -> str:
        return self.sections.get(slug, {}).get("name", slug.title())

    def add_nav(self, slug: str, label: str, path: str, before: str = "archive") -> None:
        at = next((i for i, n in enumerate(self.nav) if n[0] == before), len(self.nav))
        self.nav.insert(at, (slug, label, self.url(path)))

    def column_for(self, edition: dict[str, Any]) -> dict[str, Any] | None:
        """The latest opinion column as of this edition, if it's recent enough for its front page."""
        return _latest(self.columns, edition, self.front_days)

    def quiz_for(self, edition: dict[str, Any]) -> dict[str, Any] | None:
        """The latest quiz as of this edition, if it's recent enough for its front page."""
        return _latest(self.quizzes, edition, self.quiz_days)

    def article_url(self, story: dict[str, Any]) -> str:
        if story.get("path"):
            return self.url(story["path"])
        sources = story.get("sources") or [{}]
        return sources[0].get("url", "#")

    # formatting filters
    def local(self, value: Any) -> dt.datetime | None:
        ts = parse_ts(value)
        return ts.astimezone(self.tz) if ts else None

    def date_long(self, value: Any) -> str:
        d = self.local(value)
        return f"{d:%A} {d.day} {d:%B %Y}" if d else ""

    def date_short(self, value: Any) -> str:
        d = self.local(value)
        return f"{d.day} {d:%b}" if d else ""

    def date_when(self, value: Any, precision: str = "day") -> str:
        """Release dates: '14 Nov', 'Nov 2026', 'Q1 2027', '2027'."""
        if not value:
            return "TBA"
        d = dt.date.fromisoformat(str(value)[:10])
        if precision == "year":
            return str(d.year)
        if precision == "quarter":
            return f"Q{(d.month - 1) // 3 + 1} {d.year}"
        if precision == "month":
            return f"{d:%b %Y}"
        return f"{d.day} {d:%b}"

    def time(self, value: Any) -> str:
        d = self.local(value)
        return f"{d:%H:%M}" if d else ""

    def when(self, value: Any) -> str:
        """'14:20' for today (local), '2 Nov 22:05' for anything older."""
        d = self.local(value)
        if not d:
            return ""
        return f"{d:%H:%M}" if d.date() == self.now.astimezone(self.tz).date() else f"{d.day} {d:%b} {d:%H:%M}"

    def iso(self, value: Any) -> str:
        ts = parse_ts(value)
        return ts.isoformat() if ts else ""

    @staticmethod
    def num(value: Any) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def money(amount: Any, currency: str = "EUR") -> str:
        try:
            return CURRENCY_FORMATS.get(currency, "{:.2f} " + currency).format(float(amount))
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def paragraphs(text: str | None) -> list[str]:
        return [p.strip() for p in (text or "").split("\n\n") if p.strip()]

    @staticmethod
    def domain(url: str | None) -> str:
        host = urlparse(url or "").netloc
        return host[4:] if host.startswith("www.") else host

    @staticmethod
    def score_parts(score: str | None) -> tuple[str, str] | None:
        """A review score as (number, scale): "8.5/10" → ("8.5", "/10"), "90%" → ("90", "%"), "82" → ("82", "").
        None for a word ("Bestest Best")."""
        m = SCORE.match((score or "").strip())
        return (m.group(1), m.group(2) or "") if m else None

    @staticmethod
    def price(usd: Any) -> str:
        """A cover price: "$0.73", or "Free" when no Claude call was made (a links edition)."""
        try:
            usd = float(usd)
        except (TypeError, ValueError):
            return ""
        return "Free" if usd < 0.005 else f"${usd:.2f}"

    @staticmethod
    def rating_class(rating: str | None) -> str:
        r = (rating or "").lower()
        if r in POSITIVE_RATINGS:
            return "positive"
        if r in NEGATIVE_RATINGS:
            return "negative"
        return "mixed" if r else ""

    def deals_checked(self, deals: dict[str, Any] | None, edition: dict[str, Any] | None) -> dict[str, str]:
        """When the deals on `edition`'s pages were checked (deals.py carries a check over between check days):
        `when` is "07:05" on the edition's own day, "Tuesday 07:05" within the week, else "3 Nov 07:05"; `day` is
        "Tuesday", or "" when checked the same day; `next` is the next check day ("Friday"), or "" when every
        edition checks."""
        checked = self.local((deals or {}).get("checked_at"))
        ref = self.local((edition or {}).get("generated_at")) or self.now.astimezone(self.tz)
        if not checked:
            return {"when": "", "day": "", "next": ""}
        age = (ref.date() - checked.date()).days
        day = "" if age <= 0 else f"{checked:%A}" if age < 7 else f"{checked.day} {checked:%b}"
        nxt = deal_days.next_check(ref.date(), deal_days.settings(self.cfg)[0])
        return {"when": f"{day} {checked:%H:%M}".strip(), "day": day if age < 7 else "",
                "next": f"{nxt:%A}" if nxt else ""}

    def edition_name(self, edition: dict[str, Any]) -> str:
        d = self.local(edition.get("generated_at"))
        if not d:
            return "Edition"
        return "Morning edition" if d.hour < 11 else "Afternoon edition" if d.hour < 17 else "Evening edition"

    # writing
    def write(self, rel: str, template: str, **ctx: Any) -> None:
        path = self.out / rel
        if rel == "" or rel.endswith("/"):
            path = path / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.env.get_template(template).render(**ctx), encoding="utf-8")
        self.pages += 1

    # page contexts
    def front_context(self, edition: dict[str, Any]) -> dict[str, Any]:
        stories = edition.get("stories", [])
        featured = sorted((s for s in stories if s["tier"] == "featured"),
                          key=lambda s: (not s.get("lead"), -s.get("newsworthiness", 0)))
        briefs = sorted((s for s in stories if s["tier"] == "brief"),
                        key=lambda s: s.get("published_at") or "", reverse=True)
        gaming = link_reviews(edition.get("gaming") or {})
        links_by_section: dict[str, list] = {}
        for link in edition.get("links", []):
            links_by_section.setdefault(link.get("section", "tech"), []).append(link)
        return {
            "edition": edition,
            "lead": featured[0] if featured else None,
            "featured_rest": featured[1:],
            "medium": [s for s in stories if s["tier"] == "medium"],
            "briefs": briefs,
            "hn_top": edition.get("hn_top", []),
            "gaming": gaming,
            "deals": edition.get("deals") or {},
            "links_by_section": links_by_section,
            "column": self.column_for(edition),
            "quiz": self.quiz_for(edition),
        }


def edition_price(edition: dict[str, Any], forum_day: dict[str, Any] | None = None) -> float | None:
    """The edition's "cover price": what its Claude calls cost at API prices (stories, discovery, column, quiz,
    the Botroom). A Botroom day run on its own (`python -m newsroom forum`) adds its cost. None if unknown."""
    llm = edition.get("llm") or {}
    usd = next((llm[k] for k in ("equivalent_usd", "estimated_usd", "usd") if llm.get(k) is not None), None)
    if usd is None:
        return None
    if forum_day and not any(t.startswith(("forum_", "persona_")) for t in llm.get("by_task") or {}):
        usd += float((forum_day.get("cost") or {}).get("equivalent_usd") or 0)
    return round(float(usd), 4)


def _latest(items: list[dict[str, Any]], edition: dict[str, Any], days: int) -> dict[str, Any] | None:
    """The newest of `items` (newest first) published at or before `edition` and fewer than `days` days old."""
    day = dt.date.fromisoformat(edition["edition_id"][:10])
    for it in items:
        age = (day - dt.date.fromisoformat(it["edition_id"][:10])).days
        if 0 <= age < days and it["edition_id"] <= edition["edition_id"]:
            return it
    return None


def _link_stories(rows: list[dict[str, Any]], pages: set[str]) -> None:
    """Rows pointing at earlier stories (a column's reporting, a quiz's answers) get our article page's
    path when it exists; otherwise article_url falls back to the original source."""
    for r in rows:
        path = article_path(r["edition_id"], r["slug"]) if r.get("tier") in PAGE_TIERS and r.get("slug") else ""
        if path in pages:
            r["path"] = path


def build(cfg: dict[str, Any], data_dir: Path, out_dir: Path,
          front_edition: str | None = None, preview: bool = False) -> int:
    editions = load_editions(data_dir) if (data_dir / "editions").exists() else []

    _guard_out_dir(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    shutil.copytree(ROOT / "static", out_dir / "static")

    b = SiteBuilder(cfg, out_dir, preview)

    if not editions:                  # before the first edition: a placeholder, so deploys still work
        placeholder = {"current_edition": {"generated_at": b.now.isoformat()}}
        b.write("", "empty.html", active="front", **placeholder)
        b.write("404.html", "404.html", active="", **placeholder)
        return b.pages

    for ed in editions:
        for s in ed.get("stories", []):
            s["edition_id"] = ed["edition_id"]
            s["edition_generated_at"] = ed.get("generated_at")
            if s["tier"] in PAGE_TIERS:
                s["path"] = article_path(ed["edition_id"], s["slug"])

    pages = {s["path"] for ed in editions for s in ed.get("stories", []) if s.get("path")}
    for ed in editions:
        col = ed.get("opinion")
        if not col:
            continue
        col.update(edition_id=ed["edition_id"], edition_generated_at=ed.get("generated_at"),
                   path=article_path(ed["edition_id"], col["slug"]), section="opinion",
                   quote_after=quote_slot(SiteBuilder.paragraphs(col.get("body")), col.get("pull_quote") or ""))
        _link_stories(col.get("reading", []), pages)
    b.columns = [ed["opinion"] for ed in reversed(editions) if ed.get("opinion")]
    if b.columns:
        b.add_nav("opinion", "Opinion", "opinion/")
    for ed in editions:
        qz = ed.get("quiz")
        if qz:
            qz.update(edition_id=ed["edition_id"], edition_generated_at=ed.get("generated_at"),
                      path=f"quiz/{ed['edition_id']}/", section="quiz")
            _link_stories([q["story"] for q in qz.get("questions", []) if q.get("story")], pages)
    b.quizzes = [ed["quiz"] for ed in reversed(editions) if ed.get("quiz")]
    if b.quizzes:
        b.add_nav("quiz", "Quiz", "quiz/")

    # The Botroom: a thread under each article it commented on, and /forum/
    forum_days = forum.load_days(data_dir)
    members: dict[str, Any] = {}
    article_threads: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    if forum_days:
        b.add_nav("forum", "Botroom", "forum/")
        members = forum_look.members(forum.full_cast(forum.load_generated(data_dir)), forum_roster.load(data_dir),
                                     forum_days)
        for x in forum_days:
            def story_page(story: dict[str, Any], eid: str = x["edition_id"]) -> str | None:
                path = article_path(eid, story["slug"])
                return path if path in pages else None
            forum_look.prepare_day(x, story_page)
            for t in x["threads"]:
                if t["article_path"]:
                    article_threads[t["article_path"]] = (t, x)
    forum_by_edition = {x["edition_id"]: x for x in forum_days}
    for ed in editions:                                  # the masthead's cover price
        ed["price_usd"] = edition_price(ed, forum_by_edition.get(ed["edition_id"]))

    by_id = {e["edition_id"]: e for e in editions}
    if front_edition and front_edition not in by_id:
        raise SystemExit(f"Unknown edition {front_edition!r}; have {', '.join(by_id)}")
    front = by_id[front_edition] if front_edition else editions[-1]
    newest_first = list(reversed(editions))
    common = {"current_edition": front}

    # front page
    b.write("", "front.html", active="front", **common, **b.front_context(front), weather=b.weather)

    # AI and Tech section fronts
    all_stories = [s for ed in newest_first for s in ed.get("stories", [])]
    for slug in AI_SECTIONS:
        sec_stories = [s for s in all_stories if s.get("section") == slug]
        main = [s for s in sec_stories if s["tier"] in PAGE_TIERS][:30]
        b.write(f"{slug}/", "section.html", active=slug, section=b.sections[slug], **common,
                stories=main,
                briefs=[s for s in sec_stories if s["tier"] == "brief"][:20],
                links=[] if main else [l for l in front.get("links", []) if l.get("section") == slug])

    # Gaming
    gaming_eds = [e for e in newest_first if e.get("gaming")]
    current_gaming = link_reviews(gaming_eds[0]["gaming"]) if gaming_eds else {}
    seen_urls = {r.get("url") for r in current_gaming.get("reviews", [])}
    earlier_reviews = []
    for ed in gaming_eds[1:8]:
        for r in ed["gaming"].get("reviews", []):
            if r.get("url") not in seen_urls:
                seen_urls.add(r.get("url"))
                earlier_reviews.append(r)
    b.write("gaming/", "gaming.html", active="gaming", section=b.sections["gaming"], **common,
            gaming=current_gaming, earlier_reviews=earlier_reviews[:20])

    # Deals
    deal_eds = [e for e in newest_first if e.get("deals")]
    current_deals = deal_eds[0]["deals"] if deal_eds else {}
    # earlier deals of the day still running: once each (the newest), and not if today's page lists the game
    seen = {d.get("game") for d in current_deals.get("featured", []) + current_deals.get("more", [])}
    seen |= {d.get("game") for s in current_deals.get("shelves") or [] for d in s.get("deals") or []}
    still_active = []
    for ed in deal_eds[1:8]:
        for d in ed["deals"].get("featured", []):
            exp = parse_ts(d.get("expires"))
            if exp and exp > b.now and d.get("game") not in seen:
                seen.add(d.get("game"))
                still_active.append(d)
    b.write("deals/", "deals.html", active="deals", section=b.sections["deals"], **common,
            deals=current_deals, still_active=still_active)

    # Article pages
    for ed in editions:
        recent = [s for e in newest_first[:7] for s in e.get("stories", []) if s["tier"] in PAGE_TIERS]
        latest_briefs = b.front_context(ed)["briefs"][:8]
        for s in ed.get("stories", []):
            if s["tier"] not in PAGE_TIERS:
                continue
            related = [r for r in recent if r["section"] == s["section"] and r is not s][:4]
            thread, fday = article_threads.get(s["path"], (None, None))
            b.write(s["path"], "article.html", active=s["section"], story=s, edition=ed,
                    related=related, briefs=latest_briefs, current_edition=ed, thread=thread, forum_day=fday,
                    members=members, pending=forum_look.pending_reply(fday) if fday else None)

    # Opinion: one page per column, and the list of all columns
    for col in b.columns:
        ed = by_id[col["edition_id"]]
        others = [c for c in b.columns if c is not col][:4]
        b.write(col["path"], "opinion.html", active="opinion", column=col, edition=ed, current_edition=ed,
                more_columns=others, briefs=b.front_context(ed)["briefs"][:6])
    if b.columns:
        b.write("opinion/", "opinion_index.html", active="opinion", section=OPINION_SECTION, **common,
                columns=b.columns)

    # Quiz: one page per quiz, and the list of all quizzes
    for qz in b.quizzes:
        ed = by_id[qz["edition_id"]]
        b.write(qz["path"], "quiz.html", active="quiz", quiz=qz, edition=ed, current_edition=ed,
                more_quizzes=[x for x in b.quizzes if x is not qz][:4], briefs=b.front_context(ed)["briefs"][:6])
    if b.quizzes:
        b.write("quiz/", "quiz_index.html", active="quiz", section=QUIZ_SECTION, **common, quizzes=b.quizzes)

    # The Botroom: a page per day (the latest is /forum/), a page per thread, and the members
    if forum_days:
        newest_days = list(reversed(forum_days))
        for i, x in enumerate(newest_days):
            ed = by_id.get(x["edition_id"], front)
            ctx = dict(active="forum", day=x, days=newest_days, members=members, current_edition=ed,
                       newer=newest_days[i - 1] if i > 0 else None,
                       older=newest_days[i + 1] if i + 1 < len(newest_days) else None)
            if i == 0:
                b.write("forum/", "forum.html", is_index=True, **ctx)
            b.write(x["path"], "forum.html", is_index=False, **ctx)
            pending = forum_look.pending_reply(x)
            for t in x["threads"]:
                b.write(t["path"], "forum_topic.html", active="forum", t=t, day=x, members=members,
                        pending=pending, current_edition=ed)
        order = lambda m: (not m["fixed"], not m["founding"], -m["comments"], m["handle"].lower())  # noqa: E731
        groups = [(title, sorted((m for m in members.values() if m["status"] == status), key=order))
                  for title, status in (("Around", "active"), ("Away", "away"), ("Left", "gone"))]
        b.write("forum/members/", "forum_members.html", active="forum", groups=groups, current_edition=front)

    # Archive
    summaries = []
    for ed in newest_first:
        stories = ed.get("stories", [])
        summaries.append({
            "edition": ed,
            "counts": {t: sum(1 for s in stories if s["tier"] == t) for t in TIERS},
            "links": len(ed.get("links", [])),
        })
        b.write(f"archive/{ed['edition_id']}/", "front.html", active="archive", archived=True,
                current_edition=ed, **b.front_context(ed))
    b.write("archive/", "archive.html", active="archive", **common, summaries=summaries)

    # Search: the index, and the page that searches it in the browser
    rows = build_index(editions, b.article_url)
    index = json.dumps({"items": rows}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (out_dir / "search").mkdir(exist_ok=True)
    (out_dir / "search" / "index.json").write_bytes(index)
    filters = [(slug, b.section_name(slug)) for slug in (*AI_SECTIONS, "gaming")]
    if b.columns:
        filters.append(("opinion", OPINION_SECTION["name"]))
    b.write("search/", "search.html", active="search", **common, filters=filters, count=len(rows),
            since=b.local(editions[0].get("generated_at")),
            index_url=b.url("search/index.json") + "?v=" + hashlib.sha1(index).hexdigest()[:8],
            section_names=json.dumps(dict(filters)))

    # 404 and feed
    b.write("404.html", "404.html", active="", **common)
    feed_items = [s for ed in newest_first[:20]
                  for s in [ed[k] for k in ("opinion", "quiz") if ed.get(k)] + ed.get("stories", [])
                  if s.get("path")]
    b.write("feed.xml", "feed.xml", **common, items=feed_items[:50],
            updated=front.get("generated_at"))
    return b.pages
