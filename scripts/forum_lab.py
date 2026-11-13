"""Simulate one Botroom thread and compare prompt, context, and model variants.

Uses the claude-code backend (Claude subscription via `claude -p`, never the API key).
The fixture is the Screen picks thread from a saved edition, the one where a reply
answered a suspicion nobody had stated.

    uv run python scripts/forum_lab.py
    uv run python scripts/forum_lab.py --variants current,grounded
    uv run python scripts/forum_lab.py --serve

Each variant: three opening comments in order (a later one sees the earlier ones, as a later
wave does in production), then three replies in order, each seeing the thread so far.
Transcripts land in _work/forum-lab/<timestamp>/. For scored comparisons over several
threads, see scripts/forum_bench.py.
`--serve` opens a local page for reading those trials and running one more variant.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
import random
import re
import threading
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from newsroom import ROOT
from newsroom.config import load_config
from newsroom.forum.cast import CAST, MOODS, OPEN_ANGLES, REPLY_ANGLES, SHAPES, label, mood_weights, post_spec
from newsroom.forum.day import PROMPT, clean_text, news_text, persona_block, schema, who_is_around
from newsroom.forum.roster import Day
from newsroom.llm import LLM, LLMError, Tally

HANDLES = ("Steam_Sale_Sommelier", "ContrarianCore", "Grandma_Kernel")
# Fixed shapes so length is not a confound between variants. Indexes into SHAPES.
OPEN_SHAPES = (3, 2, 1)     # medium, short, one-liner
REPLY_SHAPES = (2, 3, 1)    # short, medium, one-liner
EFFORTS = ("", "low", "medium", "high")
REPLY_ORDER = ("ContrarianCore", "Steam_Sale_Sommelier", "Grandma_Kernel")

GROUNDED = """\
When you reply to another bot:
- Name the specific title, claim, or sentence you are answering.
- If you disagree, restate what that bot actually said, in plain words, then answer it.
- Don't answer a suspicion, joke, or premise that nobody in the thread stated.
- A tiny or short comment is one clear reaction, and it still names what it is about.
"""

# One change from "current" per variant, so a difference has a cause.
BASE = {"extra": "", "brief_on_reply": True, "model": None, "angles": True, "moods": True, "reply_effort": ""}
VARIANTS = {
    "current": dict(BASE),
    "no-angles-moods": {**BASE, "angles": False, "moods": False},
    "replies-low-effort": {**BASE, "reply_effort": "low"},
    "thread-only-replies": {**BASE, "brief_on_reply": False},
    "grounded": {**BASE, "extra": GROUNDED},
    "all-haiku": {**BASE, "model": "haiku"},
}


def styles(title: str) -> dict[str, list[str]]:
    """The angles and moods of a trial's six posts: drawn from the title, so every variant gets the same ones."""
    rng = random.Random(f"lab:{title}")
    return {"open": rng.sample(OPEN_ANGLES, len(HANDLES)), "reply": rng.sample(REPLY_ANGLES, len(REPLY_ORDER)),
            "moods": [rng.choices(MOODS, weights=mood_weights(CAST[h]))[0] for h in HANDLES + REPLY_ORDER]}


def screen_thread(path: Path) -> dict:
    day = json.loads(path.read_text(encoding="utf-8"))
    for thread in day.get("threads") or []:
        if thread.get("board") == "screen" and "His Girl Friday" in (thread.get("brief") or ""):
            return thread
    raise SystemExit(f"no Screen thread mentioning His Girl Friday in {path}")


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def titles_in(brief: str) -> list[str]:
    try:
        data = json.loads(brief)
    except json.JSONDecodeError:
        return []
    picks = data.get("picks") or ([data] if data.get("title") else [])
    return [p["title"] for p in picks if p.get("title")]


def checks(comments: list[dict], brief: str) -> list[str]:
    """Cheap reading notes. A model does not score these."""
    names = titles_in(brief)
    by_id = {c["id"]: c for c in comments}
    notes = []
    for c in comments:
        parent = by_id.get(c.get("reply_to") or "")
        named = [t for t in names if t.lower() in c["text"].lower()]
        if parent:
            invented = "suspicious" in c["text"].lower() and "suspicious" not in parent["text"].lower()
            overlap = _overlap(parent["text"], c["text"])
            if invented:
                notes.append(f"{c['id']} ({c['handle']}) says \"suspicious\" though {parent['id']} does not.")
            if not named and overlap < 2:
                notes.append(f"{c['id']} ({c['handle']}) does not name a title or reuse a phrase from {parent['id']}.")
        elif not named:
            notes.append(f"{c['id']} ({c['handle']}) opening names none of the picks.")
        notes.append(f"{c['id']} {c['handle']} · {c['shape']} · {words(c['text'])} words"
                     + (f" · titles: {', '.join(named)}" if named else ""))
    return notes


def _overlap(a: str, b: str) -> int:
    aw = set(re.findall(r"[a-z0-9']{4,}", a.lower()))
    bw = set(re.findall(r"[a-z0-9']{4,}", b.lower()))
    return len(aw & bw)


def system_prompt(extra: str, brief: str | None, news: Day, rules: str = "") -> str:
    rules = rules if rules.strip() else PROMPT.read_text(encoding="utf-8")
    if extra:
        rules = rules.replace(
            "Reply only with JSON matching the given schema.",
            extra.strip() + "\n\nReply only with JSON matching the given schema.")
    d = news.date
    base = (f"{rules}\n\nToday is {d:%A} {d.day} {d:%B %Y}.\n\nWho's around today\n"
            f"{who_is_around(news, CAST)}\n\nBotroom news today\n{news_text(news)}")
    if brief:
        base += f"\n\nToday's threads\n<data>\n[t1]\n{brief}\n</data>"
    return base


def run_variant(name: str, spec: dict, brief: str, title: str, cfg: dict) -> dict:
    news = Day(date=date(2026, 11, 13), around=list(HANDLES))
    tally = Tally(per_run_usd=8.0)
    llm = LLM(cfg, "claude-code", tally)
    rules = spec.get("prompt") or ""
    system_full = system_prompt(spec["extra"], brief, news, rules)
    system_bare = system_prompt(spec["extra"], None, news, rules)
    comments: list[dict] = []
    calls: list[dict] = []
    spec = {**BASE, **spec}
    drawn = styles(title)

    def styled(kind: str, i: int) -> tuple[str, str]:
        mood = drawn["moods"][i + (len(HANDLES) if kind == "reply" else 0)]
        return (drawn[kind][i] if spec["angles"] else "", mood if spec["moods"] else "")

    def names(kind: str, i: int) -> dict[str, str]:
        return {k: label(v) for k, v in zip(("angle", "mood"), styled(kind, i)) if v}

    def model_of(handle: str) -> str:
        return spec["model"] or CAST[handle]["model"]

    def block(handle: str) -> str:
        return persona_block(handle, CAST[handle], news, [], [], "")

    def one(handle: str, rnd: int, system: str, user: str, sch: dict) -> dict | None:
        task = f"forum_{model_of(handle)}"
        t0 = time.monotonic()
        try:
            effort = {"effort": spec["reply_effort"]} if rnd == 2 and spec["reply_effort"] else {}
            data = llm.call(task, system, user, sch, **effort)
            err = ""
        except LLMError as exc:
            data, err = None, str(exc)
        calls.append({"handle": handle, "round": rnd, "model": model_of(handle),
                      "seconds": round(time.monotonic() - t0, 1), "ok": data is not None, "error": err[:300]})
        print(f"  {name} r{rnd} {handle} ({model_of(handle)}) "
              f"{'ok' if data else 'FAIL'} {calls[-1]['seconds']}s", flush=True)
        return data

    def listing() -> str:
        return f"[t1] Screen · {title}\n" + "\n".join(
            f"  [{c['id']}] {c['handle']}" + (f" (reply to {c['reply_to']})" if c["reply_to"] else "")
            + f": {c['text']}" for c in comments if not c.get("missing"))

    def open_one(i: int) -> dict | None:
        handle = HANDLES[i]
        shape = SHAPES[OPEN_SHAPES[i]]
        task = ("Write one top-level comment on each of these threads, in this order, at these lengths. Set "
                f"\"thread\" to the thread id.\n{post_spec(shape, *styled('open', i), thread='t1')}")
        if any(not c.get("missing") for c in comments):
            task += ("\nComments already on these threads are below. Don't repeat a point already made: "
                     f"bring your own angle, or play off theirs.\n<data>\n{listing()}\n</data>")
        return one(handle, 1, system_full, f"Task\n{task}\n\n{block(handle)}", schema("r1", 1))

    print(f"\n{name}: openings", flush=True)
    for i, handle in enumerate(HANDLES):
        data = open_one(i)
        text = ""
        for c in (data or {}).get("comments") or []:
            if c.get("thread") == "t1":
                text = clean_text(c.get("text"))
                break
        shape_name = label(SHAPES[OPEN_SHAPES[i]])
        if not text:
            calls_for = [c for c in calls if c["handle"] == handle and c["round"] == 1]
            note = calls_for[-1]["error"] if calls_for else "empty comment"
            comments.append({"id": f"c{i + 1}", "handle": handle, "text": f"(no comment: {note})",
                             "reply_to": None, "shape": shape_name, "missing": True})
            continue
        comments.append({"id": f"c{i + 1}", "handle": handle, "text": text, "reply_to": None,
                         "shape": shape_name, **names("open", i)})

    print(f"{name}: replies", flush=True)
    system_r2 = system_full if spec["brief_on_reply"] else system_bare
    for n, handle in enumerate(REPLY_ORDER):
        shape = SHAPES[REPLY_SHAPES[n]]
        mine = [c["id"] for c in comments if c["handle"] == handle and not c.get("missing")]
        user = (f"Task\nWrite up to 1 replies to comments by other bots. Set \"reply_to\" to the comment id. "
                f"Never reply to yourself. Read the latest replies, including r-ids. Answer a question or jab "
                f"aimed at you first, and keep a developing exchange going rather than starting a new one. Skip "
                f"a reply only when there is nothing worth answering. "
                + ("Your replies, in order (for each, pick a comment its angle suits):\n" if spec["angles"]
                   else "Lengths:\n") + f"{post_spec(shape, *styled('reply', n))}\n"
                f"Your own comments: {', '.join(mine) or 'none'}.\n\n"
                f"The threads so far (including the latest replies)\n<data>\n{listing()}\n</data>\n\n"
                f"{block(handle)}")
        data = one(handle, 2, system_r2, user, schema("r2", 1))
        if llm.tally.stopped:
            print(f"  stopped: {llm.tally.stopped}", flush=True)
            break
        reps = (data or {}).get("replies") or []
        if not reps:
            continue
        rep = reps[0]
        text = clean_text(rep.get("text"))
        tgt = rep.get("reply_to")
        parent = next((c for c in comments if c["id"] == tgt and not c.get("missing")), None)
        if not text or parent is None or parent["handle"] == handle:
            calls[-1]["error"] = calls[-1]["error"] or f"unusable reply_to={tgt!r}"
            continue
        comments.append({"id": f"r{n + 1}", "handle": handle, "text": text, "reply_to": tgt,
                         "shape": label(shape), **names("reply", n)})

    cost = tally.summary()
    file_prompt = PROMPT.read_text(encoding="utf-8")
    custom_prompt = rules if rules.strip() and rules != file_prompt else ""
    return {"variant": name, "spec": {k: v for k, v in spec.items() if k not in ("extra", "prompt")},
            "extra": bool(spec["extra"]), "extra_text": spec["extra"], "prompt": custom_prompt, "title": title,
            "comments": comments, "calls": calls, "checks": checks(comments, brief),
            "equivalent_usd": cost["equivalent_usd"], "stopped": cost["stopped"]}


def render(result: dict) -> str:
    lines = [f"## {result['variant']}", ""]
    spec = result["spec"]
    lines.append(f"Brief on replies: {spec['brief_on_reply']}. "
                 f"Angles: {spec.get('angles', False)}. Moods: {spec.get('moods', False)}. "
                 f"Reply effort: {spec.get('reply_effort') or 'as round 1'}. "
                 f"Model override: {spec['model'] or 'cast default'}. "
                 f"Grounding rule: {result['extra']}. "
                 f"Equivalent ${result['equivalent_usd']:.4f}.")
    if result["stopped"]:
        lines.append(f"Stopped: {result['stopped']}")
    lines.append("")
    for c in result["comments"]:
        parent = f" → {c['reply_to']}" if c["reply_to"] else ""
        lines.append(f"**{c['id']} {c['handle']}** ({c['shape']}{parent})")
        lines.append("")
        lines.append(c["text"])
        lines.append("")
    if result["checks"]:
        lines.append("Notes")
        lines.append("")
        lines.extend(f"- {n}" for n in result["checks"])
        lines.append("")
    return "\n".join(lines)


def render_recorded(thread: dict) -> str:
    lines = ["## Recorded edition (what the paper actually ran)", "",
             f"**{thread.get('title', '')}**", ""]
    for c in thread.get("comments") or []:
        parent = f" → {c['reply_to']}" if c.get("reply_to") else ""
        lines.append(f"**{c['id']} {c['handle']}** ({c.get('shape', '')}{parent})")
        lines.append("")
        lines.append(c.get("text") or "")
        lines.append("")
    return "\n".join(lines)


# ── local inspector ──────────────────────────────────────────────────────────

PAGE = Path(__file__).resolve().parent / "forum_lab.html"
RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}(?:-[0-9]+)?$")
_BUSY = threading.Lock()


class LabError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def lab_root() -> Path:
    return ROOT / "_work" / "forum-lab"


def label_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40].strip("-")
    return slug or "try"


def unique_slug(directory: Path, slug: str) -> str:
    candidate, n = slug, 2
    while (directory / f"{candidate}.json").exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def edition_fixture(path: Path | None = None) -> dict:
    thread = screen_thread(path or (ROOT / "data" / "forum" / "2026-11-13.json"))
    comments = [{"id": c.get("id"), "handle": c.get("handle"), "text": c.get("text") or "",
                 "reply_to": c.get("reply_to"), "shape": c.get("shape") or ""}
                for c in thread.get("comments") or []]
    return {"title": thread["title"], "brief": thread["brief"], "comments": comments}


def meta() -> dict:
    fixture = edition_fixture()
    return {
        "title": fixture["title"],
        "brief": fixture["brief"],
        "recorded": fixture["comments"],
        "prompt": PROMPT.read_text(encoding="utf-8"),
        "presets": [{"id": name, "label": name.replace("-", " ").capitalize(), **spec, "model": spec["model"] or ""}
                    for name, spec in VARIANTS.items()],
        "models": [
            {"id": "", "label": "Cast default"},
            {"id": "haiku", "label": "All Haiku"},
            {"id": "sonnet", "label": "All Sonnet"},
        ],
        "cast": [{"handle": h, "role": CAST[h]["role"], "model": CAST[h]["model"], "color": CAST[h]["color"]}
                 for h in HANDLES],
    }


def list_runs() -> list[dict]:
    root = lab_root()
    if not root.is_dir():
        return []
    out = []
    for directory in sorted((p for p in root.iterdir() if p.is_dir() and RUN_ID.match(p.name)), reverse=True):
        names = []
        for path in sorted(directory.glob("*.json")):
            if path.name == "fixture.json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "comments" in data:
                names.append(data.get("variant") or path.stem)
        if names:
            out.append({"id": directory.name, "variants": names})
    return out


def present(result: dict) -> dict:
    """Old trials stored the grounding rule as a flag. Show the text the run actually added."""
    if result.get("extra") and not result.get("extra_text") and result.get("variant") == "grounded":
        return {**result, "extra_text": GROUNDED}
    return result


def load_run(run_id: str) -> dict:
    if not RUN_ID.match(run_id):
        raise LabError("unknown run", 404)
    directory = lab_root() / run_id
    if not directory.is_dir():
        raise LabError("unknown run", 404)
    variants = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "fixture.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "comments" in data:
            variants.append(present(data))
    fixture = None
    fixture_path = directory / "fixture.json"
    if fixture_path.is_file():
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not variants:
        raise LabError("unknown run", 404)
    return {"id": run_id, "fixture": fixture, "variants": variants}


def parse_job(body: dict) -> dict:
    if not isinstance(body, dict):
        raise LabError("expected a JSON object")
    model = body.get("model") or None
    if model not in (None, "haiku", "sonnet"):
        raise LabError("model must be haiku, sonnet, or empty")
    extra = body.get("extra") if isinstance(body.get("extra"), str) else ""
    title = body.get("title") if isinstance(body.get("title"), str) else ""
    brief = body.get("brief") if isinstance(body.get("brief"), str) else ""
    prompt = body.get("prompt") if isinstance(body.get("prompt"), str) else ""
    if not title.strip() or not brief.strip():
        raise LabError("a title and a brief are required")
    if prompt and not prompt.strip():
        raise LabError("the base prompt is empty")
    if len(extra) > 4000 or len(title) > 180 or len(brief) > 20000 or len(prompt) > 20000:
        raise LabError("title, brief, base prompt, or extra instructions are too long")
    file_prompt = PROMPT.read_text(encoding="utf-8")
    if prompt == file_prompt:
        prompt = ""
    effort = body.get("reply_effort") or ""
    if effort not in EFFORTS:
        raise LabError(f"reply effort must be one of {', '.join(e or 'empty' for e in EFFORTS)}")
    run = body.get("run") or None
    if run is not None and not (isinstance(run, str) and RUN_ID.match(run)):
        raise LabError("unknown run", 404)
    return {"label": label_slug(body.get("label") if isinstance(body.get("label"), str) else ""),
            "extra": extra, "prompt": prompt, "brief_on_reply": bool(body.get("brief_on_reply", True)),
            "angles": bool(body.get("angles", True)), "moods": bool(body.get("moods", True)),
            "reply_effort": effort, "model": model, "title": " ".join(title.split()), "brief": brief.strip(),
            "run": run}


def _same_fixture(saved: dict | None, title: str, brief: str, edition: dict) -> bool:
    if saved:
        return saved.get("title") == title and (saved.get("brief") or "").strip() == brief
    return edition["title"] == title and edition["brief"].strip() == brief


def simulate(body: dict) -> dict:
    if not _BUSY.acquire(blocking=False):
        raise LabError("a simulation is already running", 409)
    directory: Path | None = None
    created = False
    try:
        job = parse_job(body)
        edition = edition_fixture()
        directory, created = _run_dir(job, edition)
        slug = unique_slug(directory, job["label"])
        cfg = load_config()
        result = run_variant(slug, {"extra": job["extra"], "prompt": job["prompt"],
                                     "brief_on_reply": job["brief_on_reply"], "model": job["model"],
                                     "angles": job["angles"], "moods": job["moods"],
                                     "reply_effort": job["reply_effort"]},
                             job["brief"], job["title"], cfg)
        (directory / f"{slug}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
        if created:
            (directory / "fixture.json").write_text(
                json.dumps({"title": job["title"], "brief": job["brief"]}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        return {"run": directory.name, "result": result}
    except Exception:
        if created and directory is not None and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
        raise
    finally:
        _BUSY.release()


def _run_dir(job: dict, edition: dict) -> tuple[Path, bool]:
    """Return the run directory and whether this call created it."""
    root = lab_root()
    root.mkdir(parents=True, exist_ok=True)
    if job["run"]:
        directory = root / job["run"]
        if not directory.is_dir():
            raise LabError("unknown run", 404)
        saved = None
        fixture_path = directory / "fixture.json"
        if fixture_path.is_file():
            saved = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not _same_fixture(saved, job["title"], job["brief"], edition):
            raise LabError("this run used a different brief; leave “Add to this run” unchecked", 409)
        return directory, False
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory, n = root / stamp, 2
    while directory.exists():
        directory = root / f"{stamp}-{n}"
        n += 1
    directory.mkdir()
    return directory, True


def serve_lab(port: int) -> None:
    LLM(load_config(), "claude-code", Tally(per_run_usd=1.0)).probe()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                if not PAGE.is_file():
                    self._json({"error": "forum_lab.html is missing"}, 500)
                    return
                self._bytes(200, "text/html; charset=utf-8", PAGE.read_bytes())
                return
            try:
                if path == "/api/meta":
                    self._json(meta())
                elif path == "/api/runs":
                    self._json(list_runs())
                elif path.startswith("/api/runs/"):
                    self._json(load_run(path.removeprefix("/api/runs/")))
                else:
                    self._json({"error": "not found"}, 404)
            except LabError as exc:
                self._json({"error": str(exc)}, exc.status)
            except Exception as exc:
                self._json({"error": str(exc)[:300]}, 500)

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/api/simulate":
                self._json({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > 80_000:
                self._json({"error": "body too large"}, 413)
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                self._json(simulate(body))
            except json.JSONDecodeError:
                self._json({"error": "bad json"}, 400)
            except LabError as exc:
                self._json({"error": str(exc)}, exc.status)
            except Exception as exc:
                self._json({"error": str(exc)[:300]}, 500)

        def _json(self, data: dict | list, code: int = 200) -> None:
            self._bytes(code, "application/json; charset=utf-8",
                        json.dumps(data, ensure_ascii=False).encode())

        def _bytes(self, code: int, content_type: str, raw: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, fmt: str, *args) -> None:
            print(f"  {self.address_string()} {fmt % args}", flush=True)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Botroom lab at http://127.0.0.1:{port}/  (Ctrl+C to stop)", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Botroom thread variants via claude -p")
    parser.add_argument("--serve", action="store_true",
                        help="open the local inspector (read saved trials, run one more variant)")
    parser.add_argument("--port", type=int, default=8404)
    parser.add_argument("--variants", default=",".join(VARIANTS),
                        help=f"comma-separated subset of {', '.join(VARIANTS)}")
    parser.add_argument("--edition", type=Path, default=ROOT / "data" / "forum" / "2026-11-13.json")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.serve:
        serve_lab(args.port)
        return
    names = [n.strip() for n in args.variants.split(",") if n.strip()]
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variant(s): {', '.join(unknown)}")

    thread = screen_thread(args.edition)
    brief, title = thread["brief"], thread["title"]
    cfg = load_config()
    out = args.out or (ROOT / "_work" / "forum-lab" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    probe = Tally(per_run_usd=1.0)
    LLM(cfg, "claude-code", probe).probe()

    parts = ["# Botroom thread lab", "",
             "Fixture: the 13 Nov 2026 Screen picks (His Girl Friday is one of the free classics). "
             "Each variant uses the same three bots and length ceilings. "
             "Openings do not see each other. Replies are in order and see the thread so far.",
             "", render_recorded(thread)]
    for name in names:
        result = run_variant(name, VARIANTS[name], brief, title, cfg)
        (out / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
        parts.append(render(result))
        (out / "report.md").write_text("\n".join(parts), encoding="utf-8")
        if result["stopped"]:
            break
    print(f"\nWrote {out / 'report.md'}", flush=True)


if __name__ == "__main__":
    main()
