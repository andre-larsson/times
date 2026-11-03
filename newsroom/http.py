"""HTTP client for the sources: one shared httpx client, polite headers, short retries."""

from __future__ import annotations

import time
from typing import Any

import httpx

USER_AGENT = "The403Times/0.2 (personal news digest; +https://a403.space/times/)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A source could not be fetched; the message is safe to log (no secrets)."""


class Client:
    def __init__(self, timeout: float = 20.0, retries: int = 2):
        self.retries = retries
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"},
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self._http.close()

    def get(self, url: str, params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._http.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:               # timeouts, DNS, resets, redirects, decoding
                last = FetchError(f"{type(exc).__name__} for {_safe(url)}")
            else:
                if resp.status_code < 400:
                    return resp
                last = FetchError(f"HTTP {resp.status_code} for {_safe(url)}")
                if resp.status_code not in RETRY_STATUS:
                    break
            if attempt < self.retries:
                time.sleep(1.5 * (attempt + 1))
        raise last or FetchError(f"failed: {_safe(url)}")

    def text(self, url: str, **kw: Any) -> str:
        return self.get(url, **kw).text

    def json(self, url: str, **kw: Any) -> Any:
        resp = self.get(url, **kw)
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"not JSON from {_safe(url)} (got {resp.headers.get('content-type')})") from exc


def _safe(url: str) -> str:
    """Drop the query string so API keys never end up in logs."""
    return url.split("?", 1)[0]
