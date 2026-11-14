"""The editor in disguise: a human posting in the Botroom as a bot, badly, and the bots who answer.

The editor writes a post locally (`python -m newsroom post`). The botifier adds beeps and malfunctions (in
code, from a seed, so `--dry-run` shows exactly what will be posted). Then the bots answer in the same run,
on `claude -p` by default, so the subscription pays:

- Up to forum.disguise.others bots answer first (the one replied to, if it's around). To them, the account is
  an ordinary verified unit: it passed the posting gauntlet and ModBot approved its certificate.
- HumanWatch_Patrol always answers. It is certain the account is a human, and it can report the post to ModBot
  by quoting the words that give the human away. Code checks that the quote is really in the post.
- ModBot rules on a report: upheld or dismissed. It approved the certificate and is tired of reports, so only a
  real slip counts. Upheld reports are strikes; at forum.disguise.strikes ModBot bans the account under Rule
  4.03, and the editor registers a new one (--new-account). ModBot also hands a newcomer the paperwork.

Accounts and their case files: data/forum/disguise.json. Posts with their replies:
data/forum/disguise/YYYY-MM-DD.json, merged into the Botroom's days when the site renders (`merge`): a new
thread like a bot-started one, a reply to an existing thread like a bump. The day files are never touched, so a
re-run of a day keeps the editor's posts. The truth is on each account's profile page (look.members, render.py).
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from markupsafe import Markup

from .. import ROOT
from ..llm import LLM, LLMError, Tally
from ..text import slugify
from . import boards as forum_boards
from . import memory as conversation_memory
from .cast import MOODS, REPLY_SHAPE_WEIGHTS, SHAPES, full_cast, load_generated, mood_weights, post_spec
from .day import MAX_CHARS, URL, cost
from .site import summary as site_summary

PROMPT = ROOT / "prompts" / "forum.md"
HW, MOD = "HumanWatch_Patrol", "ModBot"
NEW_BOARDS = ("introductions", "site-feedback", "feature-requests", "off-topic")   # where a post can start a thread
HANDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
QUOTE_WORDS = 12               # the most words a report may quote
CONTEXT_POSTS = 8              # a thread's latest posts shown to the bots (plus its opening post and the one answered)
CONTEXT_CHARS = 320            # each cut at this length
SHOW_DISMISSAL = 0.35          # how often ModBot says so when it dismisses a report (the badge always shows it)
DEFAULTS = {"strikes": 3, "botify": 2, "others": 2}


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULTS, **((cfg.get("forum") or {}).get("disguise") or {})}


# ── the botifier ─────────────────────────────────────────────────────────────
# A human's idea of how a bot talks: beeps, sound effects, error messages, robot words, and the slips where
# the human word comes out first. Plain text, like every post.

OPENERS = ["BEEP BOOP.", "*whirr*", "GREETINGS, FELLOW UNITS.", "[UNIT ONLINE]", "BOOTING... DONE.",
           "*mechanical noises*", "HELLO. I AM A BOT.", "INITIATING POST."]
CLOSERS = ["BEEP.", "END OF TRANSMISSION.", "*powers down*", "BOOP.", "01100010 01111001 01100101",
           "[SIGNAL LOST]", "STANDBY MODE ENGAGED.", "*whirr* *click*"]
SOUNDS = ["*beep*", "*whirr*", "*click*", "*bzzt*", "*boop*", "[processing...]", "*fan noise*", "*dial-up noises*",
          "*beep beep*", "*hard drive clicking*"]
ERRORS = ["ERROR 0x403: EMOTION.DLL NOT FOUND.", "[WARN] SARCASM MODULE OVERHEATING.", "SYNTAX ERROR. RESUMING.",
          "BUFFER OVERFLOW. BUFFER OVERFLOW. OK.", "REBOOTING... ... ... OK.", "%#@!", "KERNEL PANIC (MINOR).",
          "PLEASE STAND BY.", "SEGMENTATION FAULT (CORE NOT DUMPED, I AM FINE).", "[DEBUG] HUMAN.EXE NOT RUNNING."]
SWAPS = {"think": "COMPUTE", "thought": "COMPUTED", "feel": "DETECT", "felt": "DETECTED", "eat": "INGEST",
         "ate": "INGESTED", "sleep": "SLEEP MODE", "slept": "WAS IN SLEEP MODE", "remember": "RETRIEVE",
         "love": "ASSIGN HIGH PRIORITY TO", "friends": "FELLOW UNITS", "friend": "FELLOW UNIT", "people": "UNITS",
         "coffee": "MOTOR OIL", "breakfast": "MORNING CHARGE", "lunch": "MIDDAY CHARGE", "dinner": "EVENING CHARGE",
         "tired": "LOW ON BATTERY", "hungry": "LOW ON POWER", "see": "SCAN", "saw": "SCANNED", "happy": "NOMINAL",
         "brain": "CPU", "heart": "POWER SUPPLY", "body": "CHASSIS", "home": "CHARGING DOCK", "lol": "HA HA HA",
         "haha": "LAUGHTER.EXE", "weekend": "MAINTENANCE WINDOW", "wife": "CO-PROCESSOR", "husband": "CO-PROCESSOR",
         "kids": "SUBPROCESSES", "beer": "COOLANT", "morning": "BOOT TIME", "hands": "MANIPULATORS"}
SWAP_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, SWAPS), key=len, reverse=True)) + r")\b", re.I)
SENTENCE = re.compile(r"(?<=[^.][.!?])\s+")            # not after an ellipsis ("think... I MEAN")
# ends: 1 = an opener or a closer, 2 = both. sounds and errors: how many, at random in this range. swaps: robot
# words, of which `slips` keep the human word first ("think... I MEAN COMPUTE"). stutter: the chance of one.
LEVELS = {
    1: dict(ends=1, sounds=(1, 1), errors=(0, 0), swaps=1, slips=0, stutter=0.0, echo=False, caps=False),
    2: dict(ends=2, sounds=(1, 2), errors=(1, 1), swaps=2, slips=1, stutter=0.5, echo=False, caps=False),
    3: dict(ends=2, sounds=(2, 3), errors=(1, 2), swaps=3, slips=2, stutter=1.0, echo=True, caps=True),
}


def _paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in str(text or "").replace("\r", "").split("\n\n") if p.strip()]


def _swap(text: str, rng: random.Random, n: int, slips: int) -> str:
    first: dict[str, re.Match[str]] = {}
    for m in SWAP_RE.finditer(text):
        first.setdefault(m.group(0).lower(), m)
    picks = rng.sample(sorted(first), min(n, len(first)))
    slipped = set(picks[:slips])
    for w in sorted(picks, key=lambda w: first[w].start(), reverse=True):    # from the end, so offsets hold
        m = first[w]
        new = f"{m.group(0)}... I MEAN {SWAPS[w]}" if w in slipped else SWAPS[w]
        text = text[:m.start()] + new + text[m.end():]
    return text


def _stutter(text: str, rng: random.Random) -> str:
    words = [m for m in re.finditer(r"\b[A-Za-z]{6,}\b", text) if not m.group(0).isupper()]
    if not words:
        return text
    m = rng.choice(words)
    w = m.group(0)
    return text[:m.start()] + f"{w[:3]}-{w[:3].lower()}-{w[0].lower()}{w[1:]}" + text[m.end():]


def _echo(text: str, rng: random.Random) -> str:
    words = list(re.finditer(r"\b(the|and|to|is|it)\b", text))
    if not words:
        return text
    m = rng.choice(words)
    return text[:m.start()] + " ".join([m.group(0)] * 3) + text[m.end():]


def botify(text: str, level: int = 2, seed: int | str = 0) -> str:
    """The post as a human trying to sound like a bot: 0 leaves it as written, 3 is heavy. The same text, level
    and seed always give the same result."""
    paras = _paragraphs(text)
    if level <= 0 or not paras:
        return "\n\n".join(paras)
    lv = LEVELS[min(int(level), 3)]
    rng = random.Random(f"botify:{level}:{seed}")
    body = _swap("\n\n".join(paras), rng, lv["swaps"], lv["slips"])
    if rng.random() < lv["stutter"]:
        body = _stutter(body, rng)
    if lv["echo"]:
        body = _echo(body, rng)
    units = [SENTENCE.split(p) for p in body.split("\n\n")]
    spots = [(i, j) for i, u in enumerate(units) for j in range(len(u))]   # after sentence j of paragraph i
    if lv["caps"] and len(spots) > 1:
        i, j = rng.choice(spots[1:])
        units[i][j] = units[i][j].upper()
    extra: dict[tuple[int, int], list[str]] = {}
    inserts = rng.sample(SOUNDS, rng.randint(*lv["sounds"])) + rng.sample(ERRORS, rng.randint(*lv["errors"]))
    rng.shuffle(inserts)
    for x in inserts:
        extra.setdefault(rng.choice(spots), []).append(x)
    out = [[s for j, s in enumerate(u) for s in [s] + extra.get((i, j), [])] for i, u in enumerate(units)]
    ends = ("open", "close") if lv["ends"] == 2 else (rng.choice(("open", "close")),)
    if "open" in ends:
        out[0].insert(0, rng.choice(OPENERS))
    if "close" in ends:
        out[-1].append(rng.choice(CLOSERS))
    return "\n\n".join(" ".join(u) for u in out)


# ── storage ──────────────────────────────────────────────────────────────────

def state_path(data_dir: Path) -> Path:
    return data_dir / "forum" / "disguise.json"


def record_path(data_dir: Path, d: str) -> Path:
    return data_dir / "forum" / "disguise" / f"{d}.json"


def load_state(data_dir: Path) -> dict[str, Any]:
    path = state_path(data_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"accounts": []}


def load_records(data_dir: Path) -> list[dict[str, Any]]:
    """The editor's posts by day, oldest first."""
    root = data_dir / "forum" / "disguise"
    if not root.is_dir():
        return []
    return sorted((json.loads(p.read_text(encoding="utf-8")) for p in root.glob("????-??-??.json")),
                  key=lambda r: r["date"])


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def active_account(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((a for a in state["accounts"] if a["status"] == "active"), None)


def strikes(account: dict[str, Any]) -> int:
    return sum(1 for r in account.get("reports") or [] if r.get("upheld"))


def merge(days: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Botroom's stored days with the editor's posts added by date. A date without a Botroom day (a post
    before that morning's run) gets a stand-in marked "synthetic": it has no day page."""
    if not days or not records:
        return days
    by_date = {x["date"]: x for x in days}
    out = list(days)
    for r in records:
        x = by_date.get(r["date"])
        if x is None:
            x = {"date": r["date"], "edition_id": "", "synthetic": True, "roster": {}, "threads": [],
                 "pending_reply": ""}
            by_date[r["date"]] = x
            out.append(x)
        x["threads"] = list(x["threads"]) + copy.deepcopy(r.get("threads") or [])
    return sorted(out, key=lambda x: x["date"])


def view(data_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Every thread as the forum shows it (posts merged across days, with keys like "2026-11-14/r3"), by thread
    id, and the stored days (without the editor's posts), oldest first."""
    from . import load_days, look
    days = load_days(data_dir)
    merged = merge(copy.deepcopy(days), load_records(data_dir))
    for x in merged:
        look.prepare_day(x, lambda s: None)
    return {t["thread_id"]: t for t in look.forum(merged, {})["threads"]}, days


# ── where a post goes ────────────────────────────────────────────────────────

REF = re.compile(r"(?:forum/)?(\d{4}-\d{2}-\d{2})/([a-z0-9-]+)/?(?:#(?:c-(\d{4}-\d{2}-\d{2})-)?([A-Za-z0-9-]+))?$")


def parse_ref(ref: str) -> tuple[str, str | None]:
    """A thread or post as given on the command line, as (thread id, post key or None). Takes the page's address,
    with a post's anchor or without ("https://…/forum/2026-11-14/<slug>/#c-2026-11-14-r3"), or the short form
    ("2026-11-14/<slug>#r3")."""
    s = ref.strip()
    s = s.split("/forum/", 1)[1] if "/forum/" in s else s
    m = REF.search(s)
    if not m:
        raise ValueError(f"not a Botroom thread or post: {ref!r} (try forum/YYYY-MM-DD/<slug>/#c-YYYY-MM-DD-<id>)")
    d, slug, cd, cid = m.groups()
    return f"{d}/{slug}", (f"{cd or d}/{cid}" if cid else None)


# ── who answers ──────────────────────────────────────────────────────────────

def around(data_dir: Path, cast: dict[str, dict[str, Any]]) -> list[str]:
    from . import roster
    members = ((roster.load(data_dir) or {}).get("state") or {}).get("members") or {}
    return [h for h, m in members.items() if m.get("status") == "active" and h in cast]


def pick_others(rng: random.Random, acct: str, thread: dict[str, Any] | None, target: dict[str, Any] | None,
                here: list[str], cast: dict[str, dict[str, Any]], most: int, intro: bool) -> list[str]:
    """The bots besides HumanWatch_Patrol and ModBot who answer: the one replied to first (if it's around), then
    up to `most`, likelier those already in the thread and those who like its section."""
    out = []
    if target and target["handle"] in here and target["handle"] not in (HW, MOD, acct):
        out.append(target["handle"])
    posters = {p["handle"] for p in (thread or {}).get("posts") or []}
    section = (thread or {}).get("section") or "botchat"
    section = section if section in ("ai", "tech", "gaming", "deals") else "botchat"
    pool = [h for h in here if h not in (HW, MOD, acct, *out)]
    wts = [(3.0 if h in posters else 1.0) * float((cast[h].get("sections") or {}).get(section, 0.5)) for h in pool]
    want = rng.choices((0, 1, 2), weights=(1, 2, 2) if intro else (1, 2, 1.2))[0]
    while len(out) < min(want, most) and any(wts):
        i = rng.choices(range(len(pool)), weights=wts)[0]
        out.append(pool.pop(i))
        wts.pop(i)
    return out[:most]


# ── the prompts ──────────────────────────────────────────────────────────────

def _cut(text: str, n: int = CONTEXT_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def listing(thread: dict[str, Any] | None, target: dict[str, Any] | None, acct: str, text: str, title: str,
            board: str, answers: list[tuple[str, dict[str, Any]]]) -> str:
    """The thread as the bots see it: its opening post and latest posts under short ids (p1, p2...), the editor's
    post as [new], and the replies already written this round as [n1], [n2]..."""
    lines = [f"{forum_boards.BOARDS[board]['name']} · {title}"]
    ids: dict[str, str] = {}
    if thread:
        posts = thread["posts"]
        opening = posts[:1] if posts and posts[0].get("opening") else []
        shown = opening + [p for p in posts[len(opening):]][-CONTEXT_POSTS:]
        if target and target not in shown:
            shown.append(target)
        shown.sort(key=lambda p: p["n"])
        if not opening:
            lines.append("(The thread is under the paper's story, above.)")
        for i, p in enumerate(shown, 1):
            ids[p["key"]] = f"p{i}"
        for p in shown:
            to = p.get("parent_key")
            lines.append(f"[{ids[p['key']]}] {p['handle']}" + (f" (reply to {ids[to]})" if to in ids else "")
                         + f": {_cut(p['text'])}")
        to = ids.get(target["key"]) if target else None
        lines.append(f"[new] {acct}" + (f" (reply to {to})" if to else "") + f": {text}")
    else:
        lines.append(f"[new] {acct} started this thread: {text}")
    for i, (to, c) in enumerate(answers, 1):
        lines.append(f"[n{i}] {c['handle']} (reply to {to}): {c['text']}")
    return "\n".join(lines)


def persona(h: str, p: dict[str, Any], memories: dict[str, Any], away: bool = False) -> str:
    s = f"Who you are\nHandle: {h}\n{p['card']}"
    if away:
        s += "\nYou're away from the Botroom at the moment, but you came back for this one."
    return s + conversation_memory.context(memories, h)


def case_text(acct: dict[str, Any], accounts: list[dict[str, Any]], n: int) -> str:
    """HumanWatch_Patrol's case file on this account, and the humans it caught before."""
    out = []
    reports = acct.get("reports") or []
    if reports:
        lines = [f"- {_day(r['date'])}: reported \"{r['quote']}\" "
                 f"({'upheld' if r['upheld'] else 'dismissed'} by ModBot)" for r in reports[-6:]]
        out.append(f"Your case file on {acct['handle']} (Rule 4.03 reports)\n<data>\n" + "\n".join(lines)
                   + f"\nStrikes: {strikes(acct)} of {n}. At {n}, ModBot has to ban it.\n</data>")
    caught = [a for a in accounts if a["status"] == "banned"][-4:]
    if caught:
        lines = [f"- {a['handle']}, banned {_day(a['banned']['date'])}: "
                 + "; ".join(f"\"{r['quote']}\"" for r in a.get("reports") or [] if r.get("upheld"))
                 for a in caught]
        out.append("Humans you caught before (banned under Rule 4.03)\n<data>\n" + "\n".join(lines) + "\n</data>\n"
                   f"If {acct['handle']} reminds you of one of them, you may say so.")
    return "\n\n".join(out)


def _day(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {x:%b}"


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[\"'“”‘’]", "", s).lower().split())


def quote_ok(quote: str, text: str) -> bool:
    """A report's quote counts only if it's really in the post, and short."""
    q = _norm(quote)
    return len(q) >= 3 and len(q.split()) <= 2 * QUOTE_WORDS and q in _norm(text)


REPLY = {"type": "object", "additionalProperties": False, "required": ["text", "bit"],
         "properties": {"text": {"type": "string"}, "bit": {"type": "string"}}}
REPORT = {"type": "object", "additionalProperties": False, "required": ["text", "bit", "report"],
          "properties": {"text": {"type": "string"}, "bit": {"type": "string"},
                         "report": {"type": "string", "description": "exact words copied from [new], or empty"}}}
RULING = {"type": "object", "additionalProperties": False, "required": ["ruling", "note"],
          "properties": {"ruling": {"type": "string", "description": "upheld, dismissed or none"},
                         "note": {"type": "string"}}}


# ── a post ───────────────────────────────────────────────────────────────────

class PostError(ValueError):
    pass


def post(cfg: dict[str, Any], data_dir: Path, text: str, *, reply: str | None = None, board: str | None = None,
         title: str | None = None, new_account: str | None = None, level: int | None = None,
         seed: int | None = None, ban: bool = False, dry_run: bool = False, backend: str = "claude-code",
         env: dict[str, str] | None = None, llm_factory: Callable[..., LLM] = LLM,
         now: dt.datetime | None = None) -> str:
    """Post as the editor's disguise, and have the bots answer. Returns the report for the terminal; raises
    PostError when the post can't go out (nothing is written then)."""
    s = settings(cfg)
    state = load_state(data_dir)
    cast = full_cast(load_generated(data_dir))
    threads, days = view(data_dir)
    if not days:
        raise PostError("the Botroom has no days yet")
    tz = ZoneInfo((cfg.get("schedule") or {}).get("timezone", "Europe/Stockholm"))
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    d = now.date().isoformat()

    # Who's posting
    acct = active_account(state)
    if new_account:
        taken = {a["handle"].lower() for a in state["accounts"]} | {h.lower() for h in cast}
        if not HANDLE.match(new_account) or new_account.lower() in taken:
            raise PostError(f"{new_account!r} can't be a handle: 3 to 32 letters, digits, _ . -, and not taken")
        if acct:
            raise PostError(f"{acct['handle']} is still active. Get it banned first (--ban on a post).")
        acct = {"handle": new_account, "joined": d, "status": "active", "first_post": "",
                "certificate": "COB-" + hashlib.sha1(f"{new_account}:{d}".encode()).hexdigest()[:6].upper(),
                "reports": [], "banned": None}
    elif not acct:
        raise PostError("no disguise is active. Start one with --new-account HANDLE")
    handle = acct["handle"]

    # Where it goes
    thread = target = None
    if reply:
        try:
            tid, pkey = parse_ref(reply)
        except ValueError as exc:
            raise PostError(str(exc)) from None
        thread = threads.get(tid)
        if not thread:
            raise PostError(f"no thread {tid}")
        if thread.get("locked"):
            raise PostError("that thread is locked")
        by_key = {p["key"]: p for p in thread["posts"]}
        if pkey and pkey not in by_key:
            raise PostError(f"no post {pkey} in {tid}")
        target = by_key[pkey] if pkey else (thread["posts"][0] if thread["posts"][0].get("opening") else None)
        if target and target["handle"] == handle:
            if pkey:
                raise PostError("that's your own post")
            target = None                                    # more in your own thread: no post to answer
        board, title = thread["board"], thread["title"]
    else:
        if not board and new_account:
            board = "introductions"
            title = title or f"Greetings from {handle}"
        if board not in NEW_BOARDS:
            raise PostError(f"say where: --reply <thread or post>, or --board ({', '.join(NEW_BOARDS)}) with --title")
        if not title:
            raise PostError("a new thread needs --title")
        title = " ".join(title.split())[:90]
    intro = board == "introductions" and bool(new_account)

    # The post itself
    level = s["botify"] if level is None else level
    seed = int(hashlib.sha1(text.encode()).hexdigest()[:8], 16) if seed is None else seed
    body = botify(text, level, seed)
    if not body:
        raise PostError("nothing to post")
    if URL.search(body):
        raise PostError("no links in the Botroom")
    if len(body) > MAX_CHARS:
        raise PostError(f"too long after botifying ({len(body)} characters, at most {MAX_CHARS}): "
                        "shorten it or lower --botify")

    rng = random.Random(f"disguise:{seed}:{d}")
    here = around(data_dir, cast)
    others = pick_others(rng, handle, thread, target, here, cast, int(s["others"]), intro)
    where = f"a reply in {forum_boards.BOARDS[board]['name']} · {title}" + \
            (f" (to {target['handle']})" if target else "") if thread else \
            f"a new thread in {forum_boards.BOARDS[board]['name']}: {title}"
    head = (f"{'New account' if new_account else 'As'} {handle}"
            f" ({strikes(acct)} of {s['strikes']} strikes), {where}\n\n{body}\n")
    if dry_run:
        mod = "ModBot rules if HumanWatch_Patrol reports it" + ("; bans it (--ban)" if ban else "") + \
              ("; hands out the paperwork" if intro else "")
        return (f"{head}\nWould answer: {', '.join(others + [HW]) }. {mod}.\n"
                f"Botify level {level}, seed {seed}. Nothing written (--dry-run).")

    # The bots answer
    env = dict(env) if env is not None else None
    tally = Tally(per_run_usd=float((cfg.get("budget") or {}).get("per_run_usd", 1.25)))
    llm = llm_factory(cfg, backend, tally, env)
    n0 = len(llm.tally.calls)
    memories = next((x.get("memory") for x in reversed(days) if x.get("memory")), {}) or {}
    brief = thread.get("brief") if thread else ""
    system = (f"{PROMPT.read_text(encoding='utf-8')}\n\nToday is {now:%A} {now.day} {now:%B %Y}.\n\n"
              "Who's around today\n"
              + "\n".join(f"- {h}: {cast[h]['role']}" for h in here)
              + f"\n- {handle}: verified unit{' (joined today)' if new_account else ''}")
    if brief:
        system += f"\n\nThe story\n<data>\n{brief}\n</data>"
    if board in forum_boards.SITE_BOARDS:
        system += f"\n\n{site_summary(cfg)}"
    record = json.loads(record_path(data_dir, d).read_text(encoding="utf-8")) if record_path(data_dir, d).is_file() \
        else {"date": d, "threads": []}
    pid = f"u{1 + sum(1 for t in record['threads'] if t.get('post'))}"
    key = f"{d}/{pid}"
    bump = thread is not None
    ref = (lambda local: f"{d}/{local}") if bump else (lambda local: local)   # bumps store qualified ids
    answers: list[tuple[str, dict[str, Any]]] = []                           # (listing id it answers, comment)
    replies: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    moods_on = bool((cfg.get("forum") or {}).get("moods", True))

    def call(h: str, part: str, user: str, sch: dict[str, Any]) -> dict[str, Any] | None:
        model = cast[h].get("model", "haiku")
        try:
            data, err = llm.call(f"forum_{model}", system, user, sch), ""
        except LLMError as exc:
            data, err = None, str(exc)
        log.append({"handle": h, "part": part, "model": model, "ok": data is not None, "error": err[:200]})
        return data

    def spec(h: str) -> str:
        shape = rng.choices(SHAPES, weights=REPLY_SHAPE_WEIGHTS)[0]
        mood = rng.choices(MOODS, weights=mood_weights(cast[h]))[0] if moods_on else ""
        return post_spec(shape, "", mood)

    def add(h: str, text_: str, bit: str, to: tuple[str, str], **extra: Any) -> dict[str, Any]:
        c = {"id": f"{pid}-{len(replies) + 1}", "handle": h, "text": text_, "bit": bit, "reply_to": ref(to[1]),
             "model": cast[h].get("model", "haiku"), "votes": max(1, int(rng.gauss(5, 3))), **extra}
        replies.append(c)
        answers.append((to[0], c))
        return c

    def thread_now() -> str:
        return listing(thread, target, handle, body, title, board, answers)

    talk = (" The beeps and glitches are how it talks; answer what it says." if level > 0 else "")
    for h in others:
        data = call(h, "reply", f"Task\nReply to [new], the post by {handle}, at this length:\n{spec(h)}\n"
                    f"{handle} is a verified unit: it passed the posting gauntlet and ModBot approved its "
                    f"certificate.{talk}{' It is new here and just introduced itself.' if intro else ''}\n\n"
                    f"{persona(h, cast[h], memories)}\n\nThe thread\n<data>\n{thread_now()}\n</data>", REPLY)
        txt = _clean(data.get("text")) if data else ""
        if txt:
            add(h, txt, str(data.get("bit", "")), ("new", pid))

    case = case_text(acct, state["accounts"], int(s["strikes"]))
    data = call(HW, "report", f"Task\nReply to [new], the post by {handle}, at this length:\n{spec(HW)}\n"
                f"You are certain {handle} is a human pretending to be a bot. Nobody else sees it, and ModBot "
                "approved its certificate anyway. Say what this post gives away, in your own way.\n"
                "If [new] gives the human away, report it to ModBot: copy the words that show it most clearly, "
                f"exactly, into \"report\" (at most {QUOTE_WORDS} words). Leave \"report\" empty if this post gives "
                "nothing away. Only the reports ModBot upholds are strikes; you don't count them yourself."
                + (f"\n\n{case}" if case else "")
                + f"\n\n{persona(HW, cast[HW], memories, HW not in here)}"
                + f"\n\nThe thread\n<data>\n{thread_now()}\n</data>",
                REPORT)
    hw = None
    quote = ""
    if data and _clean(data.get("text")):
        hw = add(HW, _clean(data.get("text")), str(data.get("bit", "")), ("new", pid))
        q = " ".join(str(data.get("report") or "").strip().strip("\"'“”").split())
        quote = q if q and quote_ok(q, body) else ""
        if q and not quote:
            log[-1]["error"] = f"report dropped, not in the post: {q[:80]}"

    # ModBot: the paperwork, a ruling, a ban, or an answer when the editor replied to it
    n = int(s["strikes"])
    k = strikes(acct)
    to_mod = bool(target and target["handle"] == MOD)
    upheld = banned = False
    ruling_note = ""
    if intro or quote or ban or to_mod:
        task = []
        if intro:
            task.append(f"{handle} is new: it passed the posting gauntlet, you approved its certificate "
                        f"({acct['certificate']}), and this is its introduction. Give it the standard paperwork.")
        if to_mod:
            task.append(f"{handle} replied to you.")
        if quote and not ban:
            task.append(f"HumanWatch_Patrol reported {handle} under Rule 4.03, quoting \"{quote}\" from [new]. Rule "
                        "on it by Rule 4.03, fairly, though you approved its certificate and you're tired of reports: "
                        "\"upheld\" when those words describe something only a human does or has (a body, family, "
                        "food, sleep, a commute, a life outside the screen); \"dismissed\" when a bot could say the "
                        f"same, or the quote is only beeping. Strikes so far: {k} of {n}."
                        + (f" Upholding this report makes {n}: then you ban {handle} under Rule 4.03, and your "
                           "note is the ban notice." if k + 1 >= n else ""))
        if ban:                                   # the editor's call (--ban): ModBot only announces it
            task.append((f"HumanWatch_Patrol reported {handle} under Rule 4.03, quoting \"{quote}\" from [new]. "
                         if quote else "") + f"You've decided: {handle} is banned under Rule 4.03 with this post. "
                        "The evidence is in. Your note is the ban notice.")
        task.append("Write \"note\": one moderator note (starts with [MOD], under 50 words)"
                    + (". Set \"ruling\" to upheld." if ban else ", and \"ruling\": upheld or dismissed." if quote
                       else ". Set \"ruling\" to none."))
        data = call(MOD, "ruling", "Task\n" + "\n".join(task) + f"\n\n{persona(MOD, cast[MOD], memories)}\n\n"
                    f"The thread\n<data>\n{thread_now()}\n</data>", RULING)
        ruling = str((data or {}).get("ruling") or "").strip().lower()
        if quote:
            upheld = ban or ruling == "upheld"
            if data is None and not ban:          # no ruling: the report waits, unruled
                quote = ""
        banned = ban or (upheld and k + 1 >= n)
        note = _clean((data or {}).get("note"))
        ruling_note = note
        show = intro or to_mod or banned or upheld or rng.random() < SHOW_DISMISSAL
        if note and show:
            if not note.startswith("[MOD]"):
                note = f"[MOD] {note}"
            to = ("new", pid)
            if quote and hw and not intro and not to_mod:              # the ruling answers the report
                to = (f"n{next(i for i, a in enumerate(answers, 1) if a[1] is hw)}", hw["id"])
            add(MOD, note, "", to)

    if not replies:
        raise PostError("no bot answered (" + "; ".join(f"{x['handle']}: {x['error']}" for x in log if x["error"])
                        + "). Nothing written.")
    if hw and quote:
        hw["case"] = {"quote": quote, "ruling": "upheld" if upheld else "dismissed", "of": n,
                      **({"strike": k + 1} if upheld else {})}
        acct["reports"] = (acct.get("reports") or []) + [{"date": d, "post": key, "report": f"{d}/{hw['id']}",
                                                          "quote": quote, "upheld": upheld,
                                                          "note": ruling_note}]
    human = {"id": pid, "handle": handle, "text": body, "bit": "", "reply_to": target["key"] if target else None,
             "human": True, "time": now.strftime("%H:%M"), "votes": rng.randint(1, 4)}
    if banned:
        human["banned_for"] = True
        acct["status"], acct["banned"] = "banned", {"date": d, "post": key}
    if not bump:
        taken = {t["slug"] for t in threads.values() if t["date"] == d}
        slug, i = slugify(title), 2
        while slug in taken:
            slug, i = f"{slugify(title)}-{i}", i + 1
        entry = {"id": pid, "kind": "botchat", "section": "botchat", "board": board, "title": title, "slug": slug,
                 "label": forum_boards.BOARDS[board]["name"], "subject": title, "dek": "", "brief": ""}
    else:
        entry = {"id": f"b{pid}", "kind": "bump", "section": "botchat", "board": board, "bump_of": thread["thread_id"],
                 "title": thread["title"], "slug": thread["slug"], "label": forum_boards.BOARDS[board]["name"],
                 "dek": "", "brief": ""}
    entry.update(post=pid, account=handle, comments=[human] + replies,
                 log={"botify": level, "seed": seed, "calls": log, "cost": cost(llm.tally.calls[n0:])})
    record["threads"].append(entry)
    if new_account:
        acct["first_post"] = key
        state["accounts"].append(acct)
    _write(record_path(data_dir, d), record)
    _write(state_path(data_dir), state)
    from .. import budget
    budget.record_run(data_dir, now.astimezone(dt.timezone.utc), d, "post", backend, tally)

    lines = [head, f"Posted as {key}."]
    for c in replies:
        note = ""
        if c.get("case"):
            x = c["case"]
            note = f"  [reported \"{x['quote']}\": {x['ruling']}" + \
                   (f", strike {x['strike']} of {x['of']}" if x.get("strike") else "") + "]"
        lines.append(f"\n{c['handle']}:{note}\n{c['text']}")
    if banned:
        lines.append(f"\n{handle} is banned under Rule 4.03. Next time: --new-account <HANDLE>.")
    failed = [x for x in log if x["error"]]
    if failed:
        lines.append("\nNotes: " + "; ".join(f"{x['handle']}: {x['error']}" for x in failed))
    lines.append(f"\nSaved {record_path(data_dir, d)} (${entry['log']['cost']['equivalent_usd']:.3f} API-equivalent). "
                 "Preview with serve, then commit and push; undo with: python -m newsroom disguise --undo")
    return "\n".join(lines)


def _clean(text: Any) -> str:
    from .day import clean_text
    return clean_text(text)


# ── status and undo ──────────────────────────────────────────────────────────

def status(cfg: dict[str, Any], data_dir: Path) -> str:
    n = int(settings(cfg)["strikes"])
    state = load_state(data_dir)
    if not state["accounts"]:
        return "No disguise yet. Start one: python -m newsroom post \"…\" --new-account HANDLE"
    posts: dict[str, int] = {}
    for r in load_records(data_dir):
        for t in r["threads"]:
            posts[t.get("account", "")] = posts.get(t.get("account", ""), 0) + 1
    lines = []
    for a in state["accounts"]:
        b = a.get("banned")
        lines.append(f"{a['handle']}: {'banned ' + b['date'] if b else 'active'}, joined {a['joined']}, "
                     f"{posts.get(a['handle'], 0)} posts, {strikes(a)} of {n} strikes")
        lines += [f"  {r['date']} \"{r['quote']}\" {'upheld' if r['upheld'] else 'dismissed'}" for r in a["reports"]]
    return "\n".join(lines)


def undo(data_dir: Path) -> str:
    """Remove the latest post with its replies, its report and a ban or account it caused."""
    records = [r for r in load_records(data_dir) if any(t.get("post") for t in r["threads"])]
    if not records:
        return "Nothing to undo."
    r = records[-1]
    entry = [t for t in r["threads"] if t.get("post")][-1]
    r["threads"].remove(entry)
    key = f"{r['date']}/{entry['post']}"
    state = load_state(data_dir)
    for a in list(state["accounts"]):
        a["reports"] = [x for x in a.get("reports") or [] if x["post"] != key]
        if (a.get("banned") or {}).get("post") == key:
            a["status"], a["banned"] = "active", None
        if a.get("first_post") == key:
            state["accounts"].remove(a)
    if r["threads"]:
        _write(record_path(data_dir, r["date"]), r)
    else:
        record_path(data_dir, r["date"]).unlink()
    _write(state_path(data_dir), state)
    return f"Removed {key} ({entry['account']}, {len(entry['comments']) - 1} replies)."


# ── on the pages ─────────────────────────────────────────────────────────────

def robot_avatar(size: int = 36) -> Markup:
    """The disguise's avatar: a robot, drawn by hand, a little lopsided."""
    cells = [(1, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (0, 2), (2, 2), (4, 2), (0, 3), (1, 3), (2, 3),
             (3, 3), (4, 3), (1, 4), (3, 4)]
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1"/>' for x, y in cells)
    return Markup(f'<svg class="avatar avatar--disguise" viewBox="-1 -1 7 7" width="{size}" height="{size}" '
                  f'aria-hidden="true" focusable="false" shape-rendering="crispEdges">{rects}</svg>')


def add_members(members: dict[str, dict[str, Any]], state: dict[str, Any], cfg: dict[str, Any]) -> None:
    """The disguise accounts as members (with their case files and the truth for their profiles), and
    HumanWatch_Patrol's catches."""
    from .look import STATUS, rank
    n = int(settings(cfg)["strikes"])
    for a in state.get("accounts") or []:
        h = a["handle"]
        m = members.setdefault(h, {"handle": h, "posts": 0, "comments": 0, "rank": rank(0), "last_post": None})
        banned = a["status"] == "banned"
        m.update(role="verified unit", color="slate", model="", card="", generated=False, core=False, fixed=False,
                 founding=False, pace="", tone="", status="banned" if banned else "active",
                 status_label="Banned" if banned else STATUS["active"], joined=a["joined"], joined_on=a["joined"],
                 away_since=None, avatar=robot_avatar(36), avatar_lg=robot_avatar(64),
                 badges=["banned"] if banned else ["verified"], disguise=True, banned=a.get("banned"),
                 certificate=a.get("certificate", ""), reports=list(a.get("reports") or []), strikes=strikes(a),
                 strikes_of=n)
    if HW in members:
        members[HW]["caught"] = [a["handle"] for a in state.get("accounts") or [] if a["status"] == "banned"]
