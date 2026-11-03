"""Every Claude call goes through here: structured JSON in and out, a cost tally, error classes.

Two backends:
- "api": the Anthropic API via the `anthropic` SDK, paid from the Console workspace (production).
- "claude-code": `claude -p` on this machine, drawing on the Claude subscription (local development
  only; refused inside GitHub Actions). Its usage is logged with the API-equivalent cost but never
  counted against the monthly budget.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any

BACKENDS = ("api", "claude-code")


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

    def _call_api(self, call: Call, system: str, user: str, schema: dict[str, Any], max_tokens: int) -> dict:
        import anthropic

        client = self._client_api()
        try:
            msg = client.messages.create(
                model=call.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
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

        u = msg.usage
        call.input_tokens = u.input_tokens or 0
        call.output_tokens = u.output_tokens or 0
        call.cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        call.cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
        call.usd = call.equivalent_usd = price(self.cfg, call.model, call.input_tokens, call.output_tokens,
                                               call.cache_read, call.cache_write)
        if msg.stop_reason == "max_tokens":
            raise TransientError(f"output cut off at max_tokens={max_tokens}")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return _parse(text)

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
