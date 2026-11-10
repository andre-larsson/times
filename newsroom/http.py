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
        return self._request("GET", url, params, headers)

    def post_json(self, url: str, body: Any, params: dict[str, Any] | None = None) -> Any:
        """POST a JSON body and return the JSON reply (batch APIs such as ITAD's lookups)."""
        resp = self._request("POST", url, params, None, body)
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"not JSON from {_safe(url)} (got {resp.headers.get('content-type')})") from exc

    def _request(self, method: str, url: str, params: dict[str, Any] | None,
                 headers: dict[str, str] | None, body: Any = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._http.request(method, url, params=params, headers=headers,
                                          json=body if method == "POST" else None)
            except httpx.HTTPError as exc:               # timeouts, DNS, resets, redirects, decoding
                last = FetchError(f"{type(exc).__name__} for {_safe(url)}")
            else:
                if resp.status_code < 400:
                    return resp
                last = FetchError(f"HTTP {resp.status_code} for {_safe(url)}{_reason(resp, params)}")
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


def _reason(resp: httpx.Response, params: dict[str, Any] | None) -> str:
    """An API's short error reason from a JSON body (e.g. ITAD's "Invalid or expired api key").

    Left out if it could echo a parameter value, so a key can't leak through it.
    """
    if "json" not in resp.headers.get("content-type", ""):
        return ""
    try:
        body = resp.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    msg = next((body[k] for k in ("reason_phrase", "error", "message", "detail", "status_message")   # TMDB: status_message
                if isinstance(body.get(k), str)), "")
    msg = " ".join(msg.split())[:100]
    if any(len(str(v)) >= 8 and str(v) in msg for v in (params or {}).values()):
        return ""
    return f" ({msg})" if msg else ""


def _safe(url: str) -> str:
    """Drop the query string so API keys never end up in logs."""
    return url.split("?", 1)[0]
