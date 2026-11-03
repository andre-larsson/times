"""Small text helpers shared by the sources and the ranking: HTML → plain text, URLs, titles."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$|cmpid$|taid$|oc$)")
_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by can for from has have how i in is it its new of on or that the this to "
    "was what when why will with you your after about into over just more most now out says than "
    "their they up vs we".split()
)


def plain(text: str | None) -> str:
    """Strip tags and entities, collapse whitespace."""
    text = _TAG.sub(" ", text or "")
    return _WS.sub(" ", html.unescape(text)).strip()


def excerpt(text: str | None, limit: int = 220) -> str:
    """First sentence(s) of plain text, cut on a word boundary."""
    t = plain(text)
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit // 2:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:–-") + "…"


def first_sentence(text: str | None, min_len: int = 20, max_len: int = 160) -> str:
    """The first sentence, or '' if it's too short, too long or contains a link."""
    t = plain(text)
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else ""
    if not (min_len <= len(s) <= max_len) or re.search(r"https?://|www\.|#\w", s):
        return ""
    return s


def canonical_url(url: str) -> str:
    """Normalize a URL for de-duplication: https, no www, no tracking params, no fragment."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, query, ""))


def domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def words(text: str) -> set[str]:
    """Content words for title similarity."""
    t = unicodedata.normalize("NFKD", text.lower())
    return {w for w in _WORD.findall(t) if w not in STOPWORDS and len(w) > 1}


def similarity(a: set[str], b: set[str]) -> float:
    """Overlap coefficient: shared words relative to the shorter title."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def slugify(text: str, limit: int = 60) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:limit].rstrip("-") or "item"


def game_key(title: str) -> str:
    """Loose key for matching a game across Steam and review headlines."""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[™®©]|\b(the|edition|remastered|definitive|enhanced|deluxe)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)
