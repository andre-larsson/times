"""Full article text for featured and medium stories (trafilatura), with the feed excerpt as fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .http import Client, FetchError

SKIP_HOSTS = ("news.google.com",)          # JS redirects: there's nothing to extract


def article_text(client: Client, url: str, limit: int = 12000) -> str:
    """Main text of an article, or '' if it can't be fetched or extracted."""
    if not url or any(h in url for h in SKIP_HOSTS):
        return ""
    try:
        html = client.get(url).text
    except FetchError:
        return ""
    import trafilatura

    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                               favor_precision=True) or ""
    text = text.strip()
    if len(text) > limit:
        cut = text[:limit]
        text = cut[: cut.rfind("\n")] if "\n" in cut[limit // 2:] else cut
        text += "\n[…]"
    return text


def fetch_texts(client: Client, urls: list[str], limit: int = 12000, workers: int = 4) -> dict[str, str]:
    urls = list(dict.fromkeys(u for u in urls if u))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(urls, pool.map(lambda u: article_text(client, u, limit), urls)))


def source_block(item: dict[str, Any], text: str) -> dict[str, Any]:
    """What a writer sees for one source: metadata plus full text or, failing that, the excerpt."""
    return {
        "source": item["source"], "title": item["title"], "url": item["url"],
        "published_at": item.get("published_at"),
        "text": text or item.get("excerpt") or "(only the headline is available)",
        "full_text": bool(text),
    }
