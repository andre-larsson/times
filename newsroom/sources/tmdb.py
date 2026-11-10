"""TMDB (The Movie Database): films and series on the reader's streaming services in one country.

API docs: https://developer.themoviedb.org/reference (discover, watch providers, search, genres).
Where-to-watch data comes from JustWatch and must be credited to it; TMDB itself is credited with
"This product uses the TMDB API but is not endorsed or certified by TMDB."

Two kinds of credential work, both in TMDB_API_KEY: a v4 read-access token (a JWT starting "eyJ", sent as
`Authorization: Bearer`) or a v3 API key (the `api_key` query parameter, which is never logged: see
http._safe). Rate limit: about 40 requests a second, no daily cap; a run makes about 60–100.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ..http import Client, FetchError
from ..text import excerpt

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p/"
SITE = "https://www.themoviedb.org"
KINDS = ("movie", "tv")
TYPES = ("flatrate", "free", "ads")            # subscription, free, free with ads (rent and buy are left out)
TV_TYPES = "0|2|3|4"                           # documentary, miniseries, reality, scripted (no news or talk shows)
POSTER = "w342"


@dataclass
class Service:
    """A streaming service the reader has, with its TMDB provider ids in the region."""
    name: str
    ids: list[int]
    types: list[str] = field(default_factory=lambda: list(TYPES))

    def filters(self) -> dict[str, str]:
        return {"with_watch_providers": "|".join(map(str, self.ids)),
                "with_watch_monetization_types": "|".join(self.types)}


def auth(key: str) -> tuple[dict[str, str], dict[str, str]]:
    """(query params, headers) for a credential: a v4 token goes in a header, a v3 key in the query."""
    key = key.strip()
    if key.startswith("eyJ"):
        return {}, {"Authorization": f"Bearer {key}"}
    return {"api_key": key}, {}


def norm(name: str) -> str:
    """'SVT Play' and 'svtplay' match; accents and punctuation don't count."""
    t = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def resolve(services: list[dict[str, Any]], providers: list[dict[str, Any]]) -> tuple[list[Service], list[str]]:
    """Each configured service's provider ids, by name (exact, ignoring case and spaces) or from `ids` in
    the config. Returns (resolved, names not found)."""
    by_name: dict[str, list[int]] = {}
    for p in providers:
        if p.get("provider_id") is not None and p.get("provider_name"):
            ids = by_name.setdefault(norm(p["provider_name"]), [])
            if int(p["provider_id"]) not in ids:
                ids.append(int(p["provider_id"]))
    out, missing = [], []
    for s in services:
        ids = [int(i) for i in s.get("ids") or []]
        if not ids:
            for name in [s["name"], *(s.get("match") or [])]:
                ids += [i for i in by_name.get(norm(name), []) if i not in ids]
        types = [t for t in s.get("types") or TYPES if t in TYPES]
        if ids and types:
            out.append(Service(s["name"], ids, types))
        else:
            missing.append(s["name"])
    return out, missing


def year(date: str | None) -> int | None:
    return int(date[:4]) if date and re.match(r"\d{4}-", date) else None


class TMDB:
    def __init__(self, client: Client, key: str, region: str = "SE", language: str = "en-US"):
        self.client, self.region, self.language = client, region, language
        self._params, self._headers = auth(key)
        self.requests = 0
        self.genres: dict[str, dict[int, str]] = {"movie": {}, "tv": {}}

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        self.requests += 1
        data = self.client.json(f"{API}{path}", params={**self._params, "language": self.language, **params},
                                headers={"Accept": "application/json", **self._headers})
        if not isinstance(data, dict):
            raise FetchError(f"unexpected TMDB response for {path}")
        return data

    # ── reference data ───────────────────────────────────────────────────────

    def providers(self) -> list[dict[str, Any]]:
        """Every streaming provider TMDB knows in the region (films and series), one row per id."""
        rows: dict[Any, dict[str, Any]] = {}
        for kind in KINDS:
            for p in self.get(f"/watch/providers/{kind}", watch_region=self.region).get("results") or []:
                rows.setdefault(p.get("provider_id"), p)
        return list(rows.values())

    def load_genres(self) -> None:
        for kind in KINDS:
            self.genres[kind] = {g["id"]: g["name"] for g in self.get(f"/genre/{kind}/list").get("genres") or []
                                 if g.get("id") is not None and g.get("name")}

    # ── lists ────────────────────────────────────────────────────────────────

    def discover(self, kind: str, pages: int = 1, **filters: Any) -> list[dict[str, Any]]:
        """Titles from /discover in the region, page by page (a failed page raises)."""
        out: list[dict[str, Any]] = []
        for page in range(1, max(1, pages) + 1):
            data = self.get(f"/discover/{kind}", page=page, include_adult="false", watch_region=self.region,
                            **filters)
            out += [self.title(kind, r) for r in data.get("results") or [] if r.get("id")]
            if page >= int(data.get("total_pages") or 1):
                break
        return out

    def new_releases(self, svc: Service, today: dt.date, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Recent films (released in the last `movie_days`) and series with episodes in the last `tv_days`
        that the service carries, most popular first."""
        movie_from = today - dt.timedelta(days=int(cfg.get("movie_days", 90)))
        tv_from = today - dt.timedelta(days=int(cfg.get("tv_days", 21)))
        series_days = int(cfg.get("new_series_days", 60))
        min_votes = int(cfg.get("min_votes", 0))
        movies = self.discover("movie", **svc.filters(), sort_by="popularity.desc",
                                  **{"primary_release_date.gte": movie_from.isoformat(),
                                     "primary_release_date.lte": today.isoformat(), "vote_count.gte": min_votes})
        shows = self.discover("tv", **svc.filters(), sort_by="popularity.desc", with_type=TV_TYPES,
                                 **{"air_date.gte": tv_from.isoformat(), "air_date.lte": today.isoformat(),
                                    "vote_count.gte": min_votes})
        for m in movies:
            m["flag"] = "new_film"
        for s in shows:
            fresh = s.get("date") and (today - dt.date.fromisoformat(s["date"])).days <= series_days
            s["flag"] = "new_series" if fresh else "new_episodes"
        return movies + shows

    def catalog(self, svc: Service, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """The service's best-known titles (most TMDB votes): the snapshot that new arrivals are found in.
        Ordered by votes, which hardly move from day to day, so a title that turns up here is almost always
        one the service has just added (popularity churns daily and would flag old titles as new)."""
        pages, min_votes = int(cfg.get("pages", 3)), int(cfg.get("min_votes", 50))
        return [t for kind in KINDS for t in self.discover(kind, pages, **svc.filters(), sort_by="vote_count.desc",
                                                            **{"vote_count.gte": min_votes})]

    def classics(self, services: list[Service], today: dt.date, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Older titles with a high rating from many votes, on any of the services."""
        ids = "|".join(str(i) for s in services for i in s.ids)
        types = "|".join(t for t in TYPES if any(t in s.types for s in services))
        before = dt.date(today.year - int(cfg.get("min_age_years", 3)), today.month, min(today.day, 28)).isoformat()
        rating, pages = float(cfg.get("min_rating", 7.5)), int(cfg.get("pages", 3))
        common = {"with_watch_providers": ids, "with_watch_monetization_types": types,
                  "sort_by": "vote_average.desc", "vote_average.gte": rating}
        movies = self.discover("movie", pages, **common, **{
            "vote_count.gte": int(cfg.get("min_votes_movie", 1500)), "primary_release_date.lte": before})
        shows = self.discover("tv", pages, **common, with_type=TV_TYPES, **{
            "vote_count.gte": int(cfg.get("min_votes_tv", 400)), "first_air_date.lte": before})
        return movies + shows

    # ── one title ────────────────────────────────────────────────────────────

    def where(self, kind: str, tid: int, services: list[Service]) -> tuple[str, list[dict[str, str]]]:
        """(TMDB's watch page for the region, [{service, type}]): which of the services carry the title, and
        how (subscription, free, or free with ads), in the services' order."""
        region = (self.get(f"/{kind}/{tid}/watch/providers").get("results") or {}).get(self.region) or {}
        on = []
        for svc in services:
            for t in svc.types:
                if any(p.get("provider_id") in svc.ids for p in region.get(t) or []):
                    on.append({"service": svc.name, "type": t})
                    break
        return region.get("link") or "", on

    def search(self, kind: str, query: str) -> dict[str, Any] | None:
        """A title by name: the most popular exact match (ignoring case and punctuation) among the first
        results, or None. A near match is often the wrong film (the original instead of its sequel), and a
        wrong poster is worse than none."""
        results = [r for r in self.get(f"/search/{kind}", query=query, include_adult="false").get("results") or []
                   if r.get("id")]
        want = norm(query)
        exact = [r for r in results[:5] if want in (norm(r.get("title") or r.get("name") or ""),
                                                     norm(r.get("original_title") or r.get("original_name") or ""))]
        return self.title(kind, max(exact, key=lambda r: r.get("popularity") or 0)) if exact else None

    def title(self, kind: str, r: dict[str, Any]) -> dict[str, Any]:
        """A title as the paper keeps it."""
        tid = int(r["id"])
        name = r.get("title") or r.get("name") or r.get("original_title") or r.get("original_name") or ""
        original = r.get("original_title") or r.get("original_name") or ""
        date = r.get("release_date") or r.get("first_air_date") or None
        genres = [self.genres.get(kind, {}).get(g) for g in r.get("genre_ids") or []]
        out = {
            "key": f"{kind}:{tid}", "id": tid, "kind": kind, "title": name, "date": date, "year": year(date),
            "overview": excerpt(r.get("overview"), 240),
            "poster": f"{IMAGES}{POSTER}{r['poster_path']}" if r.get("poster_path") else "",
            "rating": round(float(r.get("vote_average") or 0), 1), "votes": int(r.get("vote_count") or 0),
            "genres": [g for g in genres if g][:3], "language": r.get("original_language") or "",
            "popularity": float(r.get("popularity") or 0),
            "url": f"{SITE}/{kind}/{tid}/watch?locale={self.region}",
        }
        if original and norm(original) != norm(name):
            out["original_title"] = original
        return out
