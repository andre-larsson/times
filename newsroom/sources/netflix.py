"""Netflix's weekly top 10 for one country, from its public Tudum pages. No key.

https://www.netflix.com/tudum/top10/<country> (films) and …/<country>/tv (series), each about 0.8 MB of
HTML (gzipped on the wire) with the week's table server-rendered. The downloadable all-countries TSV is
33 MB, too big for a daily run. Netflix publishes a week (Monday–Sunday) on the Tuesday after it, so the
list is fetched again only once a newer week can exist (see screen.top10_due).
Checked 2026-11-10: both pages answer 200 to a plain client; rows carry data-uia test hooks.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any

from ..http import Client, FetchError

TOP10 = "https://www.netflix.com/tudum/top10/"
_ROW = re.compile(r'<span class="rank">\s*(\d{1,2})\s*</span>.*?<button[^>]*>(.*?)</button>\s*</td>\s*'
                  r'<td[^>]*data-uia="top10-table-row-weeks"[^>]*>\s*(\d+)\s*<', re.S)
_WEEK = re.compile(r'data-uia="top10-filters-week-select-selected"[^>]*>\s*'
                   r'(\d{1,2})/(\d{1,2})/(\d{2,4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*<')
# "Lupin: Part 4", "The Diplomat: Season 4", "Love Is Blind: S11: Boston", "Below: Limited Series"
_SEASON = re.compile(r":\s*(Season|Part|Volume|Vol\.|Series|Chapter|Book|Collection|Limited Series|S\d+)\b.*$", re.I)


def page_url(country: str, kind: str) -> str:
    return f"{TOP10}{country}" + ("/tv" if kind == "tv" else "")


def show_title(name: str) -> str:
    """The series' own name, without the season Netflix ranks: "Lupin: Part 4" → "Lupin"."""
    return _SEASON.sub("", name).strip() or name


def _date(m: str, d: str, y: str) -> dt.date:
    return dt.date(int(y) + (2000 if len(y) == 2 else 0), int(m), int(d))


def parse(page: str) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
    """(the week {start, end}, rows [{rank, title, weeks}]) from a Tudum top-10 page."""
    rows = []
    for rank, title, weeks in _ROW.findall(page):
        name = " ".join(html.unescape(re.sub(r"<[^>]+>", "", title)).split())
        if name:
            rows.append({"rank": int(rank), "title": name, "weeks": int(weeks)})
    m = _WEEK.search(page)
    week = None
    if m:
        g = m.groups()
        week = {"start": _date(*g[:3]).isoformat(), "end": _date(*g[3:]).isoformat()}
    return week, sorted(rows, key=lambda r: r["rank"])[:10]


def top10(client: Client, country: str = "sweden") -> dict[str, Any]:
    """{"week": {start, end}, "url", "films": [...], "tv": [...]}; raises FetchError if a list can't be read."""
    out: dict[str, Any] = {"url": page_url(country, "movie"), "week": None}
    for kind, key in (("movie", "films"), ("tv", "tv")):
        week, rows = parse(client.text(page_url(country, kind)))
        if not rows:
            raise FetchError(f"no top-10 table in {page_url(country, kind)}")
        out[key] = [{**r, "kind": kind, **({"show": show_title(r["title"])} if kind == "tv" else {})} for r in rows]
        out["week"] = out["week"] or week
    return out
