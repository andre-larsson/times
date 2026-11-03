"""Render edition JSON files into the static site (_site/)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape

from . import ROOT

TIERS = ("featured", "medium", "brief")
PAGE_TIERS = ("featured", "medium")            # tiers that get their own article page
AI_SECTIONS = ("ai", "tech")                   # sections built from tiered stories
CURRENCY_FORMATS = {"EUR": "€{:.2f}", "USD": "${:.2f}", "GBP": "£{:.2f}", "SEK": "{:.0f} kr"}
POSITIVE_RATINGS = {"overwhelmingly positive", "very positive", "positive", "mostly positive"}
NEGATIVE_RATINGS = {"mostly negative", "negative", "very negative", "overwhelmingly negative"}
VERDICTS = {"buy": ("✓", "Buy"), "wait": ("◷", "Wait"), "skip": ("✕", "Skip")}


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


def link_reviews(gaming: dict[str, Any]) -> dict[str, Any]:
    """Attach each new game's reviews (by id) so templates can list them."""
    by_id = {r["id"]: r for r in gaming.get("reviews", []) if r.get("id")}
    for g in gaming.get("new_on_pc", []):
        g["reviews"] = [by_id[i] for i in g.get("review_ids", []) if i in by_id]
    return gaming


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

        css = (ROOT / "static" / "style.css").read_bytes()
        nav = [("front", "Front", self.url(""))] + [
            (s["slug"], s["name"], self.url(f"{s['slug']}/")) for s in cfg["sections"]
        ] + [("archive", "Archive", self.url("archive/"))]

        self.env = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=ChainableUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(
            url=self.url, site=self.site, sections=self.sections, nav=nav, preview=preview,
            section_name=self.section_name, build_id=hashlib.sha1(css).hexdigest()[:8],
            verdicts=VERDICTS,
        )
        self.env.filters.update(
            local=self.local, date_long=self.date_long, date_short=self.date_short,
            date_when=self.date_when, time=self.time, iso=self.iso, num=self.num, money=self.money,
            paragraphs=self.paragraphs, domain=self.domain, rating_class=self.rating_class,
            edition_name=self.edition_name, article_url=self.article_url, when=self.when,
        )

    # urls and names
    def url(self, path: str = "") -> str:
        return self.base + path.lstrip("/")

    def section_name(self, slug: str) -> str:
        return self.sections.get(slug, {}).get("name", slug.title())

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
    def rating_class(rating: str | None) -> str:
        r = (rating or "").lower()
        if r in POSITIVE_RATINGS:
            return "positive"
        if r in NEGATIVE_RATINGS:
            return "negative"
        return "mixed" if r else ""

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
                          key=lambda s: -s.get("newsworthiness", 0))
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
        }


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
        b.write("", "empty.html", active="front", first_slot=cfg["schedule"]["editions"][0], **placeholder)
        b.write("404.html", "404.html", active="", **placeholder)
        return b.pages

    for ed in editions:
        for s in ed.get("stories", []):
            s["edition_id"] = ed["edition_id"]
            s["edition_generated_at"] = ed.get("generated_at")
            if s["tier"] in PAGE_TIERS:
                s["path"] = article_path(ed["edition_id"], s["slug"])

    by_id = {e["edition_id"]: e for e in editions}
    if front_edition and front_edition not in by_id:
        raise SystemExit(f"Unknown edition {front_edition!r}; have {', '.join(by_id)}")
    front = by_id[front_edition] if front_edition else editions[-1]
    newest_first = list(reversed(editions))
    common = {"current_edition": front}

    # front page
    b.write("", "front.html", active="front", **common, **b.front_context(front))

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
    still_active = []
    for ed in deal_eds[1:8]:
        for d in ed["deals"].get("featured", []):
            exp = parse_ts(d.get("expires"))
            if exp and exp > b.now:
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
            b.write(s["path"], "article.html", active=s["section"], story=s, edition=ed,
                    related=related, briefs=latest_briefs, current_edition=ed)

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

    # 404 and feed
    b.write("404.html", "404.html", active="", **common)
    feed_items = [s for ed in newest_first[:20] for s in ed.get("stories", []) if s["tier"] in PAGE_TIERS]
    b.write("feed.xml", "feed.xml", **common, items=feed_items[:50],
            updated=front.get("generated_at"))
    return b.pages
