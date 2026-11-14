"""403 Arcade: one playable micro-game a week (Fridays), coded by Claude inside a verifier sandbox.

All Claude turns run through `llm.LLM.call_sandbox` (`api` tool loop in production, `claude -p`
locally with `--llm claude-code`). Game code runs inside a `<iframe sandbox="allow-scripts">`
with no network access and is verified offline by `newsroom/arcade_kit/verify.mjs` before saving.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import ROOT, desk, schedule
from .llm import LLM, LLMError, TransientError
from .opinion import edition_date, material, reading

KIT_DIR = ROOT / "newsroom" / "arcade_kit"
API_DOC = ROOT / "prompts" / "arcade_api.md"
PROMPT_DOC = ROOT / "prompts" / "arcade.md"
STATIC_DIR = ROOT / "static" / "arcade"

CANONICAL_GENRES = (
    "one-button-timing",
    "rhythm-beat",
    "grid-puzzle",
    "snake-avoid",
    "paddle-ball",
    "memory-match",
    "word-typing",
    "turn-board",
    "stack-balance",
    "spot-mismatch",
    "dodger-shooter",
    "lane-triage",
    "mini-solitaire",
    "tower-defense",
    "aim-launcher",
    "resource-sim",
    "thrust-lander",
    "stealth-patrol",
)

GENRE_LABELS = {
    "one-button-timing": "One-button timing",
    "rhythm-beat": "Rhythm & beat",
    "grid-puzzle": "Grid puzzle",
    "snake-avoid": "Snake & avoid",
    "paddle-ball": "Paddle & ball",
    "memory-match": "Memory match",
    "word-typing": "Word & typing",
    "turn-board": "Turn-based board",
    "stack-balance": "Stack & balance",
    "spot-mismatch": "Spot mismatch",
    "dodger-shooter": "Dodger & shooter",
    "lane-triage": "Lane triage",
    "mini-solitaire": "Mini solitaire",
    "tower-defense": "Tower defense",
    "aim-launcher": "Aim & launch",
    "resource-sim": "Resource sim",
    "thrust-lander": "Thrust lander",
    "stealth-patrol": "Stealth patrol",
}

LEGACY_GENRE_MAP = {
    "timing": "one-button-timing",
    "lander": "thrust-lander",
    "grid-stealth": "stealth-patrol",
    "deflector": "paddle-ball",
    "dodger": "dodger-shooter",
    "resource": "resource-sim",
}

SKIP_RE = re.compile(r"\b(Anthropic|Claude)\b")
SOMBER_RE = re.compile(
    r"\b(war|wars|killed|kills|death|deaths|dead|dies|died|shooting|casualties|disaster|"
    r"earthquake|flood|wildfire|suicide|affair|affairs|scandal|Republican|Republicans|"
    r"Democrat|Democrats|Congress|Senate|election|elections|Trump|Biden|Harris)\b",
    re.I,
)


@dataclass
class Outcome:
    game: dict[str, Any] | None = None
    note: str = ""


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("arcade") or {}


def is_due(cfg: dict[str, Any], day: dt.date, last: dt.date | None) -> bool:
    a = settings(cfg)
    return bool(a.get("enabled", True)) and schedule.weekly_due(
        day, a.get("days", ["fri"]), int(a.get("every_weeks", 1)), last
    )


def norm_genre(raw: str) -> str:
    g = str(raw or "").strip().lower()
    g = LEGACY_GENRE_MAP.get(g, g)
    return g if g in CANONICAL_GENRES else ""


def genre_label(genre: str) -> str:
    norm = norm_genre(genre)
    return GENRE_LABELS.get(norm, str(genre or "Arcade").replace("-", " ").title())


def history(editions: list[dict[str, Any]], exclude: str = "") -> dict[str, Any]:
    counts: dict[str, int] = {g: 0 for g in CANONICAL_GENRES}
    recent_games: list[dict[str, str]] = []
    used_story_ids: list[str] = []
    for ed in sorted(editions, key=lambda e: e["edition_id"], reverse=True):
        if exclude and ed["edition_id"] == exclude:
            continue
        game = ed.get("arcade")
        if not isinstance(game, dict) or not game.get("code"):
            continue
        genre = norm_genre(game.get("genre") or "")
        if genre:
            counts[genre] += 1
        sid = str(game.get("story_id") or "")
        if sid:
            used_story_ids.append(sid)
        recent_games.append({
            "date": ed["edition_id"][:10],
            "edition_id": ed["edition_id"],
            "story_id": sid,
            "title": str(game.get("title") or ""),
            "genre": genre or str(game.get("genre") or ""),
            "controls_layout": str(game.get("controls_layout") or ""),
        })
    min_count = min(counts.values())
    preferred_genres = [g for g in CANONICAL_GENRES if counts[g] == min_count]
    return {
        "counts": counts,
        "min_count": min_count,
        "preferred_genres": preferred_genres,
        "used_story_ids": used_story_ids,
        "recent_games": recent_games[:20],
    }


def _eligible_rows(editions: list[dict[str, Any]], edition: dict[str, Any],
                   used_story_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    for days in (1, 3):
        rows, index = material(editions, edition, lookback_days=days, detail=True)
        filtered = []
        for r in rows:
            if r["id"] in used_story_ids:
                continue
            text = f"{r.get('headline', '')} {r.get('dek', '')} {r.get('summary', '')}"
            if SKIP_RE.search(text) or SOMBER_RE.search(text):
                continue
            filtered.append(r)
        if len(filtered) >= 6 or days == 3:
            return filtered, index
    return [], {}


def verify_workspace(work_dir: Path) -> tuple[dict[str, Any], bool]:
    if not shutil.which("node"):
        raise TransientError("node is not installed; cannot run verify.mjs")
    try:
        proc = subprocess.run(
            ["node", "verify.mjs", "--file", str(work_dir / "game.js")],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        raise TransientError("verify.mjs timed out") from exc
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise TransientError(f"verify.mjs output invalid JSON: {proc.stdout[:180]} {proc.stderr[:180]}") from exc
    return report, (proc.returncode == 0 and bool(report.get("ok")))


def write(cfg: dict[str, Any], llm: LLM, edition: dict[str, Any], editions: list[dict[str, Any]],
          force: bool = False) -> Outcome:
    """Create the weekly playable game for `edition` if due (or forced). Never raises LLMError."""
    a = settings(cfg)
    hist = history(editions, exclude=edition["edition_id"])
    day = edition_date(edition)
    last = dt.date.fromisoformat(hist["recent_games"][0]["date"]) if hist["recent_games"] else None
    if not force and not is_due(cfg, day, last):
        return Outcome()

    rows, index = _eligible_rows(editions, edition, set(hist["used_story_ids"]))
    if not rows:
        return Outcome(note="no eligible stories for a game today")

    system = "\n\n".join([
        (ROOT / "prompts" / "style.md").read_text(encoding="utf-8").strip(),
        PROMPT_DOC.read_text(encoding="utf-8").strip(),
        API_DOC.read_text(encoding="utf-8").strip(),
    ])
    genre_summary = {
        "preferred_genres": hist["preferred_genres"],
        "counts": hist["counts"],
        "recent_games": hist["recent_games"],
    }
    user = (
        desk.data_block(
            {"edition_id": edition["edition_id"], "genre_history": genre_summary, "stories": rows},
            "Today's edition stories and site game history:",
        )
        + "\n\nPick an unseen or least-used type from `genre_history.preferred_genres` and a fitting story, "
          "write `meta.json` and `game.js` in the current directory (you may inspect `examples/` for style), "
          "then run verification and tune balance if needed."
    )

    with tempfile.TemporaryDirectory(prefix="newsroom-arcade-") as tmp:
        work = Path(tmp)
        shutil.copy2(API_DOC, work / "arcade-api.md")
        shutil.copy2(KIT_DIR / "verify.mjs", work / "verify.mjs")
        shutil.copytree(KIT_DIR / "examples", work / "examples")
        (work / "stories.json").write_text(
            json.dumps({"edition_id": edition["edition_id"], "stories": rows}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        (work / "history.json").write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

        try:
            session = llm.call_sandbox(
                "arcade",
                system,
                user,
                work,
                max_turns=int(a.get("max_turns", 10)),
            )
            meta_path = work / "meta.json"
            if not meta_path.is_file():
                return Outcome(note="arcade session finished without meta.json")
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return Outcome(note=f"meta.json was invalid JSON: {exc}")
            verify_report, verify_ok = verify_workspace(work)
        except LLMError as exc:
            return Outcome(note=str(exc))

        if meta.get("play") is False:
            return Outcome(note=str(meta.get("reason") or "no game pitched today"))

        if not verify_ok:
            errs = "; ".join(verify_report.get("errors") or ["failed verification"])
            return Outcome(note=f"verification failed: {errs[:240]}")

        sid = str(meta.get("story_id") or "")
        if sid not in index:
            return Outcome(note=f"unknown story_id: {sid!r}")

        game_path = work / "game.js"
        if not game_path.is_file():
            return Outcome(note="arcade session finished without game.js")

        genre = norm_genre(meta.get("genre") or "")
        if not genre:
            return Outcome(note=f"invalid genre: {meta.get('genre')!r}")

        metrics = verify_report.get("metrics") or {}
        game = {
            "story_id": sid,
            "story": reading(index[sid]),
            "title": " ".join(str(meta.get("title") or "").split())[:60],
            "dek": " ".join(str(meta.get("dek") or "").split())[:160],
            "genre": genre,
            "genre_label": genre_label(genre),
            "controls_layout": str(meta.get("controls_layout") or ""),
            "news_tie": " ".join(str(meta.get("news_tie") or "").split())[:240],
            "code": game_path.read_text(encoding="utf-8"),
            "model": llm.model_for("arcade"),
            "turns": int(session.get("turns") or 0),
            "verify": {
                "lines": metrics.get("lines"),
                "idle_outcome": metrics.get("idleOutcome"),
                "idle_sec": metrics.get("idleSurvivedSec"),
                "spam_outcome": metrics.get("spamOutcome"),
                "spam_sec": metrics.get("spamSurvivedSec"),
            },
        }
        return Outcome(game)


def render_bundle(game: dict[str, Any], arcade_js: str | None = None, arcade_css: str | None = None) -> str:
    """JSON bundle embedded on the Arcade page and mounted inside `<iframe sandbox='allow-scripts'>`."""
    runtime = arcade_js if arcade_js is not None else (STATIC_DIR / "arcade.js").read_text(encoding="utf-8")
    css = arcade_css if arcade_css is not None else (STATIC_DIR / "arcade.css").read_text(encoding="utf-8")
    game_id = f"{game.get('edition_id', '')}:{game.get('title', '')}"
    runtime_inline = re.sub(r"\bexport\s+const\s+mountArcade\b", "const mountArcade", runtime, count=1)
    game_inline = re.sub(r"\bexport\s+default\s+", "const __arcadeGame = ", game.get("code") or "", count=1)
    safe_script = (
        f"const mountArcade = (() => {{\n{runtime_inline}\nreturn mountArcade;\n}})();\n"
        f"const __arcadeGame = (() => {{\n{game_inline}\nreturn __arcadeGame;\n}})();\n"
        f"mountArcade(document.getElementById('app'), __arcadeGame, "
        f"{{ gameId: {json.dumps(game_id)}, helpSeen: __ARCADE_HELP_SEEN__, bestScore: __ARCADE_BEST__ }});\n"
    ).replace("</script", "<\\/script")
    srcdoc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';\">"
        f"<style>{css}</style></head>"
        "<body><div id='app'></div>"
        f"<script>{safe_script}</script></body></html>"
    )
    payload = {
        "id": game_id,
        "layout": game.get("controls_layout") or "",
        "srcdoc": srcdoc,
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
