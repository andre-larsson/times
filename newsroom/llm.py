"""Every Claude call goes through here: structured JSON in and out, a cost tally, error classes.

Two backends:
- "api": the Anthropic API via the `anthropic` SDK, paid from the Console workspace (production).
- "claude-code": `claude -p` on this machine, drawing on the Claude subscription (local development
  only; refused inside GitHub Actions). Its usage is logged with the API-equivalent cost but never
  counted against the monthly budget.

`call` is the normal structured call with no tools. `call_web` (discovery only, API only) adds the API's
web search and web fetch tools, which Anthropic runs, and takes the answer from a strict `report` tool.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any

BACKENDS = ("api", "claude-code")
WEB_MAX_REQUESTS = 6                  # a web turn that keeps pausing gives up after this many requests
_LINK = re.compile(r"https?://[^\s<>\"'()\[\]{}|\\^`]+")


class LLMError(Exception):
    """A call failed; `fatal` errors stop all further AI work in this run."""
    fatal = False


class CreditError(LLMError):
    """Credit balance too low, spend limit reached, bad key, or subscription limit hit."""
    fatal = True


class BudgetExceeded(LLMError):
    """This run reached budget.per_run_usd."""
    fatal = True


class TransientError(LLMError):
    """Overloaded, timeout, bad JSON: worth giving up on this call but not the run."""


@dataclass
class Call:
    task: str
    model: str
    backend: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    web_searches: int = 0             # web search requests ($10 per 1,000 on top of tokens)
    web_fetches: int = 0              # web fetch requests (tokens only)
    requests: int = 0                 # API requests in this call (a web turn can pause and resume)
    usd: float = 0.0                  # what the API charged (0 for claude-code)
    equivalent_usd: float = 0.0       # what it would cost on the API
    seconds: float = 0.0
    ok: bool = True
    error: str = ""


@dataclass
class Tally:
    """Cost of this run so far. Thread-safe; checked before every call."""
    per_run_usd: float
    calls: list[Call] = field(default_factory=list)
    consecutive_failures: int = 0
    stopped: str = ""                 # set when a fatal error stops AI work
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def usd(self) -> float:
        return round(sum(c.usd for c in self.calls), 6)

    @property
    def equivalent_usd(self) -> float:
        return round(sum(c.equivalent_usd for c in self.calls), 6)

    def check(self) -> None:
        with self._lock:
            if self.stopped:
                raise LLMError(f"AI work stopped earlier: {self.stopped}")
            if self.equivalent_usd >= self.per_run_usd:
                self.stopped = f"per-run budget of ${self.per_run_usd:.2f} reached"
                raise BudgetExceeded(self.stopped)

    def record(self, call: Call, error: LLMError | None = None) -> None:
        with self._lock:
            self.calls.append(call)
            if call.ok:
                self.consecutive_failures = 0
                return
            self.consecutive_failures += 1
            if error is not None and error.fatal and not self.stopped:
                self.stopped = str(error)
            elif self.consecutive_failures >= 2 and not self.stopped:
                self.stopped = f"two failed calls in a row (last: {call.error})"

    def summary(self) -> dict[str, Any]:
        by_task: dict[str, dict[str, Any]] = {}
        for c in self.calls:
            t = by_task.setdefault(c.task, {"calls": 0, "usd": 0.0, "equivalent_usd": 0.0, "failed": 0})
            t["calls"] += 1
            t["usd"] = round(t["usd"] + c.usd, 6)
            t["equivalent_usd"] = round(t["equivalent_usd"] + c.equivalent_usd, 6)
            t["failed"] += 0 if c.ok else 1
        return {"usd": self.usd, "equivalent_usd": self.equivalent_usd, "calls": len(self.calls),
                "by_task": by_task, "stopped": self.stopped}


def price(cfg: dict[str, Any], model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    p = (cfg.get("pricing") or {}).get(model)
    if not p:
        return 0.0
    usd = (inp * p["input"] + out * p["output"] + cache_read * p.get("cache_read", p["input"] * 0.1)
           + cache_write * p.get("cache_write_5m", p["input"] * 1.25)) / 1_000_000
    return round(usd, 6)


class LLM:
    def __init__(self, cfg: dict[str, Any], backend: str, tally: Tally, env: dict[str, str] | None = None):
        if backend not in BACKENDS:
            raise ValueError(f"llm backend must be one of {', '.join(BACKENDS)}")
        self.cfg = cfg
        self.backend = backend
        self.tally = tally
        self.env = dict(os.environ) if env is None else env
        llm_cfg = cfg.get("llm") or {}
        self.max_tokens = llm_cfg.get("max_tokens") or {}
        self.effort = llm_cfg.get("effort") or {}       # task → low | medium | high | xhigh | max
        self.timeout = float(llm_cfg.get("timeout_seconds", 240))
        self._client = None
        if backend == "claude-code" and self.env.get("GITHUB_ACTIONS") == "true":
            raise ValueError("the claude-code backend is for local development only, never in GitHub Actions")

    def model_for(self, task: str) -> str:
        models = self.cfg.get("models") or {}
        return models.get(task) or models.get("default") or "claude-opus-5-5"

    # ── public ───────────────────────────────────────────────────────────────

    def call(self, task: str, system: str, user: str, schema: dict[str, Any],
             max_tokens: int | None = None) -> dict[str, Any]:
        """One structured call. Returns the parsed JSON object, or raises LLMError."""
        self.tally.check()
        model = self.model_for(task)
        max_tokens = int(max_tokens or self.max_tokens.get(task, 4000))
        start = time.monotonic()
        call = Call(task=task, model=model, backend=self.backend)
        try:
            if self.backend == "api":
                data = self._call_api(call, system, user, schema, max_tokens)
            else:
                data = self._call_claude_code(call, system, user, schema)
        except LLMError as exc:
            call.ok, call.error, call.seconds = False, str(exc)[:300], round(time.monotonic() - start, 1)
            self.tally.record(call, exc)
            raise
        call.seconds = round(time.monotonic() - start, 1)
        self.tally.record(call)
        return data

    def call_web(self, task: str, system: str, user: str, report_schema: dict[str, Any], *, searches: int,
                 fetches: int, fetch_tokens: int = 6000, filtering: bool = False,
                 max_tokens: int | None = None) -> tuple[dict[str, Any], dict[str, Any], Call]:
        """One call with web search and web fetch; Claude hands in its answer through a `report` tool.

        Returns (the report, what Claude looked at, the call with its cost). "Looked at" holds the
        search queries, the fetched URLs, every result the tools returned (url, title, page_age) and
        tool errors. `filtering` uses the newer tool versions, where Claude can trim results in code
        (dynamic filtering) before they enter its context. API backend only: `claude -p` has no
        equivalent server tools.
        """
        if self.backend != "api":
            raise LLMError("web search needs the api backend")
        self.tally.check()
        call = Call(task=task, model=self.model_for(task), backend=self.backend)
        max_tokens = int(max_tokens or self.max_tokens.get(task, 12000))
        start = time.monotonic()
        try:
            data, looked = self._call_api_web(call, system, user, report_schema, searches, fetches,
                                              fetch_tokens, filtering, max_tokens)
        except LLMError as exc:
            call.ok, call.error, call.seconds = False, str(exc)[:300], round(time.monotonic() - start, 1)
            self.tally.record(call, exc)
            raise
        call.seconds = round(time.monotonic() - start, 1)
        self.tally.record(call)
        return data, looked, call

    def probe(self) -> None:
        """Cheapest possible real request: raises CreditError if the key or credits don't work."""
        if self.backend == "claude-code":
            if not shutil.which("claude"):
                raise CreditError("claude CLI not found on PATH")
            return
        self.call("probe", "Reply with OK.", "ping", {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                                      "required": ["ok"], "additionalProperties": False},
                  max_tokens=20)

    # ── api backend ──────────────────────────────────────────────────────────

    def _client_api(self):
        if self._client is None:
            import anthropic

            key = self.env.get("ANTHROPIC_API_KEY")
            if not key:
                raise CreditError("ANTHROPIC_API_KEY is not set")
            self._client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=self.timeout)
        return self._client

    def _create(self, **kwargs: Any):
        """messages.create, with API errors mapped to CreditError / TransientError."""
        import anthropic

        client = self._client_api()
        try:
            return client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise CreditError(f"authentication failed ({exc.status_code})") from exc
        except anthropic.PermissionDeniedError as exc:
            raise CreditError(f"permission denied ({exc.status_code})") from exc
        except anthropic.BadRequestError as exc:
            text = str(exc).lower()
            if any(s in text for s in ("credit balance", "spend limit", "billing", "usage limit")):
                raise CreditError("credit balance too low or spend limit reached") from exc
            raise TransientError(f"bad request: {str(exc)[:200]}") from exc
        except anthropic.RateLimitError as exc:
            raise TransientError("rate limited") from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.InternalServerError) as exc:
            raise TransientError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            raise TransientError(f"API error {exc.status_code}") from exc

    def _add_usage(self, call: Call, msg: Any) -> None:
        """Add one response's usage to the call and re-price it (tokens, plus $0.01 per web search)."""
        u = msg.usage
        call.requests += 1
        call.input_tokens += u.input_tokens or 0
        call.output_tokens += u.output_tokens or 0
        call.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        call.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        tools = getattr(u, "server_tool_use", None)
        if tools is not None:
            call.web_searches += getattr(tools, "web_search_requests", 0) or 0
            call.web_fetches += getattr(tools, "web_fetch_requests", 0) or 0
        per_search = float((self.cfg.get("pricing") or {}).get("web_search_per_1000", 10.0)) / 1000
        call.usd = call.equivalent_usd = round(
            price(self.cfg, call.model, call.input_tokens, call.output_tokens, call.cache_read, call.cache_write)
            + call.web_searches * per_search, 6)

    def _call_api(self, call: Call, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> dict:
        msg = self._create(
            model=call.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema},
                           **({"effort": self.effort[call.task]} if self.effort.get(call.task) else {})},
        )
        self._add_usage(call, msg)
        if msg.stop_reason == "max_tokens":
            raise TransientError(f"output cut off at max_tokens={max_tokens}")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return _parse(text)

    def _call_api_web(self, call: Call, system: str, user: str, schema: dict[str, Any], searches: int,
                      fetches: int, fetch_tokens: int, filtering: bool, max_tokens: int) -> tuple[dict, dict]:
        # Basic tool versions put every result straight into context. The filtering versions run the tools
        # from code execution (no extra charge beyond tokens), so Claude can keep only what it needs.
        # Web search always cites its sources, so the answer comes through a strict client tool rather
        # than a JSON-schema response format.
        search_type, fetch_type = ("web_search_20260318", "web_fetch_20260318") if filtering else \
            ("web_search_20250305", "web_fetch_20250910")
        tools: list[dict[str, Any]] = [{"type": search_type, "name": "web_search", "max_uses": searches}]
        if fetches > 0:
            tools.append({"type": fetch_type, "name": "web_fetch", "max_uses": fetches,
                          "max_content_tokens": fetch_tokens})
        tools.append({"name": "report", "description": "Hand in your finished answer. Call it once, at the end.",
                      "input_schema": schema, "strict": True})
        effort = {"output_config": {"effort": self.effort[call.task]}} if self.effort.get(call.task) else {}
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        looked: dict[str, list] = {"queries": [], "fetched": [], "results": [], "linked": [], "errors": []}
        nudged = False
        container: dict[str, str] = {}
        for _ in range(WEB_MAX_REQUESTS):
            msg = self._create(model=call.model, max_tokens=max_tokens, tools=tools, messages=messages,
                               system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                               **effort, **container)
            self._add_usage(call, msg)
            if getattr(getattr(msg, "container", None), "id", None):   # code execution: keep its container
                container = {"container": msg.container.id}
            _collect(msg.content, looked)
            report = next((b for b in msg.content
                           if getattr(b, "type", "") == "tool_use" and getattr(b, "name", "") == "report"), None)
            if report is not None:
                data = report.input if isinstance(report.input, dict) else _parse(str(report.input))
                return data, looked
            if msg.stop_reason == "max_tokens":
                raise TransientError(f"output cut off at max_tokens={max_tokens}")
            messages.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason == "pause_turn":          # a long search turn: send it back to continue
                continue
            if nudged:
                raise TransientError("no report, even after a reminder")
            messages.append({"role": "user", "content": "Call the report tool now with what you found. "
                                                        "No more searches."})
            nudged = True
        raise TransientError(f"no report after {WEB_MAX_REQUESTS} requests")

    # ── claude-code backend ──────────────────────────────────────────────────

    def _call_claude_code(self, call: Call, system: str, user: str, schema: dict[str, Any]) -> dict:
        exe = shutil.which("claude")
        if not exe:
            raise CreditError("claude CLI not found on PATH")
        env = {k: v for k, v in self.env.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        cmd = [exe, "-p", "--model", call.model, "--output-format", "json",
               "--json-schema", json.dumps(schema), "--system-prompt", system,
               "--tools", "", "--strict-mcp-config", "--setting-sources", "",
               "--no-session-persistence", "--disable-slash-commands"]
        if self.effort.get(call.task):
            cmd += ["--effort", self.effort[call.task]]
        with tempfile.TemporaryDirectory(prefix="newsroom-cc-") as cwd:   # no CLAUDE.md, no project context
            try:
                proc = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=cwd, env=env,
                                      timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                raise TransientError(f"claude -p timed out after {self.timeout:.0f}s") from exc
        try:
            events = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise TransientError(f"claude -p gave no JSON (exit {proc.returncode}): {proc.stderr[:200]}") from exc
        events = events if isinstance(events, list) else [events]
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
        if init.get("apiKeySource") not in (None, "none"):
            raise CreditError("claude -p picked up an API key instead of the subscription; refusing")
        if not result:
            raise TransientError("claude -p returned no result")

        u = result.get("usage") or {}
        call.input_tokens = int(u.get("input_tokens") or 0)
        call.output_tokens = int(u.get("output_tokens") or 0)
        call.cache_read = int(u.get("cache_read_input_tokens") or 0)
        call.cache_write = int(u.get("cache_creation_input_tokens") or 0)
        call.equivalent_usd = round(float(result.get("total_cost_usd") or 0), 6) or price(
            self.cfg, call.model, call.input_tokens, call.output_tokens, call.cache_read, call.cache_write)

        if result.get("is_error"):
            text = str(result.get("result") or result.get("subtype") or "")
            if any(s in text.lower() for s in ("usage limit", "rate limit", "limit reached", "credit")):
                raise CreditError(f"subscription limit: {text[:160]}")
            raise TransientError(f"claude -p error: {text[:200]}")
        data = result.get("structured_output")
        if isinstance(data, dict):
            return data
        return _parse(str(result.get("result") or ""))


def _collect(content: list[Any], looked: dict[str, list]) -> None:
    """Note the queries, fetches, results and tool errors in one response's content blocks."""
    for b in content:
        kind = getattr(b, "type", "")
        if kind == "server_tool_use":
            inp = getattr(b, "input", None) or {}
            if getattr(b, "name", "") == "web_search" and inp.get("query"):
                looked["queries"].append(str(inp["query"]))
            elif getattr(b, "name", "") == "web_fetch" and inp.get("url"):
                looked["fetched"].append(str(inp["url"]))
        elif kind == "web_search_tool_result":
            if isinstance(b.content, list):
                looked["results"] += [{"url": getattr(r, "url", ""), "title": getattr(r, "title", ""),
                                       "page_age": getattr(r, "page_age", "") or ""} for r in b.content]
            else:
                looked["errors"].append(f"search: {getattr(b.content, 'error_code', 'error')}")
        elif kind == "web_fetch_tool_result":
            c = b.content
            if getattr(c, "type", "") == "web_fetch_result":
                doc = getattr(c, "content", None)
                looked["results"].append({"url": getattr(c, "url", ""), "title": getattr(doc, "title", "") or "",
                                          "page_age": "", "fetched": True})
                source = getattr(doc, "source", None)            # links on a fetched page are real pages too
                if getattr(source, "type", "") == "text":
                    looked["linked"] += _LINK.findall(str(getattr(source, "data", "") or ""))
            else:
                looked["errors"].append(f"fetch: {getattr(c, 'error_code', 'error')}")


def _parse(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TransientError(f"response was not valid JSON: {text[:120]!r}") from exc
    if not isinstance(data, dict):
        raise TransientError("response JSON was not an object")
    return data
