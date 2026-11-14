import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const VALID_LAYOUTS = new Set([
  "dpad", "dpad+a", "dpad+ab", "lr", "lr+a", "lr+ab", "a", "ab", "pointer", "typing",
]);

const CANONICAL_GENRES = new Set([
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
]);

const normKey = (k) => {
  const s = String(k || "");
  const low = s.toLowerCase();
  if (s === " " || low === "space" || low === "spacebar") return " ";
  if (low === "backspace") return "Backspace";
  if (low === "enter" || low === "return") return "Enter";
  if (low === "escape" || low === "esc") return "Escape";
  if (s.length === 1) return low;
  return s;
};

const KNOWN_COLORS = new Set([
  "dark", "panel", "paper", "paper2", "ink", "muted", "rule", "amber",
  "ai", "violet", "tech", "cyan", "gaming", "green", "deals", "pink",
  "screen", "blue", "ok", "warn", "danger", "red", "orange", "yellow",
  "white", "black", "gray", "grey",
]);

const SPRITE_CHARS = new Set([".", " ", "K", "W", "M", "A", "V", "C", "G", "P", "B", "R", "O", "Y"]);
const HEX_COLOR_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const RGB_COLOR_RE = /^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)$/i;
const FORBIDDEN_RE = /\b(import|require|eval|Function|globalThis|process|XMLHttpRequest|WebSocket|EventSource|fetch|localStorage|sessionStorage|indexedDB|document|__proto__|constructor)\b/;

const stripCommentsAndStrings = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ")
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/`(?:\\.|[^`\\])*`/g, "``");

const makeRng = (seed) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

const isFiniteNum = (v) => typeof v === "number" && Number.isFinite(v);

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

const hitTest = (a, b) => {
  if (!a || !b) return false;
  const aCirc = "r" in a && !("w" in a);
  const bCirc = "r" in b && !("w" in b);
  if (aCirc && bCirc) {
    const dx = a.x - b.x;
    const dy = a.y - b.y;
    const rr = a.r + b.r;
    return dx * dx + dy * dy <= rr * rr;
  }
  if (!aCirc && !bCirc) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }
  const c = aCirc ? a : b;
  const r = aCirc ? b : a;
  const cx = clamp(c.x, r.x, r.x + r.w);
  const cy = clamp(c.y, r.y, r.y + r.h);
  const dx = c.x - cx;
  const dy = c.y - cy;
  return dx * dx + dy * dy <= c.r * c.r;
};

const hashString = (str) => {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
};

const validateMeta = (workDir, game) => {
  const errors = [];
  const warnings = [];
  const metaPath = path.join(workDir, "meta.json");
  const storiesPath = path.join(workDir, "stories.json");
  if (!fs.existsSync(metaPath)) return { present: false, meta: null, errors, warnings };

  let meta;
  try {
    meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
  } catch (err) {
    errors.push(`meta.json is invalid JSON: ${err.message}`);
    return { present: true, meta: null, errors, warnings };
  }

  if (typeof meta.play !== "boolean") errors.push("meta.json: `play` must be a boolean");
  if (meta.play === false) return { present: true, meta, errors, warnings };

  for (const field of ["story_id", "title", "dek", "genre", "controls_layout", "news_tie"]) {
    if (typeof meta[field] !== "string" || !meta[field].trim()) {
      errors.push(`meta.json: missing non-empty \`${field}\``);
    }
  }
  if (meta.controls_layout && !VALID_LAYOUTS.has(meta.controls_layout)) {
    errors.push(`meta.json: invalid controls_layout ${meta.controls_layout}`);
  }
  if (meta.genre && !CANONICAL_GENRES.has(meta.genre)) {
    errors.push(`meta.json: genre "${meta.genre}" must be one of: ${[...CANONICAL_GENRES].join(", ")}`);
  }
  const historyPath = path.join(workDir, "history.json");
  if (fs.existsSync(historyPath)) {
    try {
      const hist = JSON.parse(fs.readFileSync(historyPath, "utf8"));
      const usedStories = new Set(hist.used_story_ids || []);
      if (meta.story_id && usedStories.has(meta.story_id)) {
        errors.push(`meta.json: story_id "${meta.story_id}" already has a game on the site; pick a different story`);
      }
      const pref = Array.isArray(hist.preferred_genres) ? hist.preferred_genres : [];
      if (meta.genre && CANONICAL_GENRES.has(meta.genre) && pref.length > 0 && !pref.includes(meta.genre)) {
        const cnt = (hist.counts && hist.counts[meta.genre]) ?? 0;
        const minCnt = hist.min_count ?? 0;
        if (cnt - minCnt >= 2 || pref.length >= 3) {
          errors.push(
            `meta.json: genre "${meta.genre}" already has ${cnt} game(s) on the site; ` +
            `pick an unseen/least-used genre (${pref.join(", ")})`,
          );
        } else {
          warnings.push(
            `meta.json: genre "${meta.genre}" has ${cnt} game(s); consider least-used (${pref.join(", ")})`,
          );
        }
      }
    } catch (err) {
      warnings.push(`Could not read history.json: ${err.message}`);
    }
  }
  if (fs.existsSync(storiesPath) && meta.story_id) {
    try {
      const storiesData = JSON.parse(fs.readFileSync(storiesPath, "utf8"));
      const ids = new Set((storiesData.stories || []).map((s) => s.id));
      if (!ids.has(meta.story_id)) {
        errors.push(`meta.json: unknown story_id "${meta.story_id}" not in stories.json`);
      }
    } catch (err) {
      warnings.push(`Could not read stories.json: ${err.message}`);
    }
  }
  if (game) {
    if (meta.title && game.title && meta.title.trim() !== game.title.trim()) {
      warnings.push("meta.json title differs from game.js title");
    }
    if (meta.controls_layout && game.controls?.layout && meta.controls_layout !== game.controls.layout) {
      errors.push(`meta.json controls_layout (${meta.controls_layout}) != game.js controls.layout (${game.controls.layout})`);
    }
  }
  return { present: true, meta, errors, warnings };
};

const validateGame = (filePath) => {
  const workDir = path.dirname(filePath);
  const metaCheck = validateMeta(workDir, null);
  if (metaCheck.present && metaCheck.meta?.play === false && metaCheck.errors.length === 0) {
    return { ok: true, skipped: true, errors: [], warnings: [], metrics: {} };
  }

  const errors = [...metaCheck.errors];
  const warnings = [...metaCheck.warnings];

  if (!fs.existsSync(filePath)) {
    return { ok: false, errors: [...errors, `Missing file: ${filePath}`], warnings, metrics: {} };
  }

  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split("\n").length;
  if (!raw.trim()) errors.push("game.js is empty");
  if (lines > 320) errors.push(`game.js is ${lines} lines (max 320)`);
  else if (lines > 240) warnings.push(`game.js is ${lines} lines; keep it concise (<240 recommended)`);

  const stripped = stripCommentsAndStrings(raw);
  const forbidden = stripped.match(FORBIDDEN_RE);
  if (forbidden) errors.push(`Disallowed keyword/identifier: ${forbidden[0]}`);

  const exportMatches = [...stripped.matchAll(/\bexport\b/g)];
  const defaultMatches = [...stripped.matchAll(/\bexport\s+default\b/g)];
  if (defaultMatches.length !== 1 || exportMatches.length !== 1) {
    errors.push("game.js must contain exactly one `export default` and no other `export` statements");
  }
  if (errors.length) return { ok: false, errors, warnings, metrics: { lines } };

  const wrapped = raw.replace(/\bexport\s+default\s+/, "const __arcadeGame = ") + "\n;__arcadeGame;";
  let rng = makeRng(403);
  const safeMath = Object.create(Math);
  safeMath.random = () => rng();

  const sandbox = {
    Math: safeMath,
    JSON,
    Number,
    String,
    Boolean,
    Array,
    Object,
    Set,
    Map,
    Infinity,
    NaN,
    isNaN,
    isFinite,
    parseInt,
    parseFloat,
  };

  let game;
  try {
    const ctx = vm.createContext(sandbox, { codeGeneration: { strings: false, wasm: false } });
    game = vm.runInContext(wrapped, ctx, { timeout: 500, filename: path.basename(filePath) });
  } catch (err) {
    return { ok: false, errors: [...errors, `Load error: ${err.message}`], warnings, metrics: { lines } };
  }

  if (!game || typeof game !== "object") {
    return { ok: false, errors: [...errors, "Default export must be an object"], warnings, metrics: { lines } };
  }

  const metaSync = validateMeta(workDir, game);
  errors.push(...metaSync.errors.filter((e) => !errors.includes(e)));
  warnings.push(...metaSync.warnings.filter((w) => !warnings.includes(w)));

  if (typeof game.title !== "string" || !game.title.trim()) errors.push("Missing non-empty `title`");
  else if (game.title.length > 80) warnings.push("`title` exceeds 80 chars");

  if (typeof game.dek !== "string" || !game.dek.trim()) errors.push("Missing non-empty `dek`");
  else if (game.dek.length > 160) warnings.push("`dek` exceeds 160 chars");

  if (!game.controls || typeof game.controls !== "object") {
    errors.push("Missing `controls` object");
  } else if (!VALID_LAYOUTS.has(game.controls.layout)) {
    errors.push(`controls.layout must be one of ${[...VALID_LAYOUTS].join(", ")}`);
  }

  if (game.howToPlay === undefined) {
    warnings.push("Missing `howToPlay` object (recommended so players see crisp rules once)");
  } else if (game.howToPlay !== false) {
    if (!game.howToPlay || typeof game.howToPlay !== "object" || Array.isArray(game.howToPlay)) {
      errors.push("`howToPlay` must be `{ summary, steps, controls }` (or `false`)");
    } else {
      const h = game.howToPlay;
      if (h.summary != null && (typeof h.summary !== "string" || !h.summary.trim())) {
        errors.push("`howToPlay.summary` must be a non-empty string");
      }
      if (!Array.isArray(h.steps) || h.steps.length === 0 || h.steps.length > 5) {
        errors.push("`howToPlay.steps` must be an array of 1..5 non-empty strings");
      } else if (h.steps.some((s) => typeof s !== "string" || !s.trim())) {
        errors.push("`howToPlay.steps` must contain only non-empty strings");
      } else if (h.steps.some((s) => s.length > 130)) {
        warnings.push("Keep each `howToPlay.steps` entry under 130 chars for phone screens");
      }
    }
  }

  const width = game.width ?? 240;
  const height = game.height ?? 160;
  if (!isFiniteNum(width) || width < 120 || width > 480) errors.push("`width` must be 120..480");
  if (!isFiniteNum(height) || height < 100 || height > 360) errors.push("`height` must be 100..360");

  if (typeof game.update !== "function") errors.push("Missing `update(g, dt)` function");
  if (typeof game.draw !== "function") errors.push("Missing `draw(g)` function");

  const customPalette = game.palette && typeof game.palette === "object" ? game.palette : {};
  const spriteNames = new Set();
  if (game.sprites && typeof game.sprites === "object") {
    for (const [name, rows] of Object.entries(game.sprites)) {
      spriteNames.add(name);
      if (!Array.isArray(rows) || rows.length === 0 || rows.length > 32) {
        errors.push(`Sprite "${name}" must be an array of 1..32 rows`);
        continue;
      }
      const rowLen = typeof rows[0] === "string" ? rows[0].length : 0;
      if (rowLen === 0 || rowLen > 32) {
        errors.push(`Sprite "${name}" rows must be 1..32 characters`);
        continue;
      }
      for (const row of rows) {
        if (typeof row !== "string" || row.length !== rowLen) {
          errors.push(`Sprite "${name}" rows must all have equal length`);
          break;
        }
        for (const ch of row) {
          if (!SPRITE_CHARS.has(ch) && !(ch in customPalette)) {
            warnings.push(`Sprite "${name}" uses unknown palette key "${ch}"`);
            break;
          }
        }
      }
    }
  }

  if (errors.length) return { ok: false, errors, warnings, metrics: { lines } };

  const unknownColors = new Set();
  const missingSprites = new Set();
  const outcomesSeen = new Set();
  let nanFound = false;

  const checkColor = (c) => {
    if (c == null) return;
    const s = String(c);
    if (s in customPalette || KNOWN_COLORS.has(s) || HEX_COLOR_RE.test(s) || RGB_COLOR_RE.test(s)) return;
    unknownColors.add(s);
  };

  const checkNums = (...vals) => {
    for (const v of vals) {
      if (!isFiniteNum(v)) nanFound = true;
    }
  };

  const runScenario = (label, frames, inputScript, seed = 403) => {
    rng = makeRng(seed);
    const held = { left: false, right: false, up: false, down: false, a: false, b: false };
    const prevHeld = { ...held };
    const ptr = { x: width / 2, y: height / 2, down: false, pressed: false, released: false };
    let prevPtrDown = false;
    let tickKeySet = new Set();
    let ended = null;
    let endedAtTick = null;
    let drawCalls = 0;
    let drawTrace = [];
    let maxScore = 0;
    let minScore = 0;
    let initScore = 0;
    let firstFrameEnded = false;
    let hudLast = "";

    const g = {
      w: width,
      h: height,
      dt: 1 / 60,
      t: 0,
      tick: 0,
      score: 0,
      state: {},
      ptr,
      keys: [],
      typed: "",
      keyPressed: (k) => tickKeySet.has(normKey(k)),
      held: (b) => Boolean(held[b]),
      pressed: (b) => Boolean(held[b] && !prevHeld[b]),
      dir: () => ({ x: (held.right ? 1 : 0) - (held.left ? 1 : 0), y: (held.down ? 1 : 0) - (held.up ? 1 : 0) }),
      dirPressed: () => ({
        x: (held.right && !prevHeld.right ? 1 : 0) - (held.left && !prevHeld.left ? 1 : 0),
        y: (held.down && !prevHeld.down ? 1 : 0) - (held.up && !prevHeld.up ? 1 : 0),
      }),
      clamp,
      lerp: (a, b, t) => a + (b - a) * t,
      dist: (x1, y1, x2, y2) => Math.hypot(x2 - x1, y2 - y1),
      rand: (min = 0, max = 1) => min + rng() * (max - min),
      randInt: (min, max) => Math.floor(min + rng() * (max - min + 1)),
      pick: (arr) => (arr && arr.length ? arr[Math.floor(rng() * arr.length)] : undefined),
      hit: hitTest,
      inRect: (px, py, x, y, w, h) => px >= x && px <= x + w && py >= y && py <= y + h,
      hud: (text) => { hudLast = String(text ?? ""); },
      sfx: () => {},
      shake: () => {},
      flash: () => {},
      particles: (x, y, c) => { checkNums(x, y); checkColor(c); },
      win: (msg) => {
        if (!ended) {
          ended = { ok: true, msg };
          endedAtTick = g.tick;
          outcomesSeen.add("win");
        }
      },
      lose: (msg) => {
        if (!ended) {
          ended = { ok: false, msg };
          endedAtTick = g.tick;
          outcomesSeen.add("lose");
        }
      },
      cls: (c = "dark") => {
        checkColor(c);
        drawCalls += 1;
        drawTrace.push(`cls:${c}`);
      },
      rect: (x, y, w, h, fill = "amber", stroke = null) => {
        checkNums(x, y, w, h);
        checkColor(fill);
        checkColor(stroke);
        drawCalls += 1;
        drawTrace.push(`r:${Math.round(x)},${Math.round(y)},${Math.round(w)},${Math.round(h)}:${fill || ""}`);
      },
      circ: (x, y, r, fill = "amber", stroke = null) => {
        checkNums(x, y, r);
        checkColor(fill);
        checkColor(stroke);
        drawCalls += 1;
        drawTrace.push(`c:${Math.round(x)},${Math.round(y)},${Math.round(r)}:${fill || ""}`);
      },
      line: (x1, y1, x2, y2, c = "white", lw = 1) => {
        checkNums(x1, y1, x2, y2, lw);
        checkColor(c);
        drawCalls += 1;
        drawTrace.push(`l:${Math.round(x1)},${Math.round(y1)}-${Math.round(x2)},${Math.round(y2)}`);
      },
      poly: (pts, fill = "amber", stroke = null) => {
        if (!Array.isArray(pts)) return;
        for (const p of pts) {
          const px = Array.isArray(p) ? p[0] : p?.x;
          const py = Array.isArray(p) ? p[1] : p?.y;
          checkNums(px, py);
        }
        checkColor(fill);
        checkColor(stroke);
        drawCalls += 1;
        drawTrace.push(`p:${pts.length}:${fill || ""}`);
      },
      bar: (x, y, w, h, frac, fg = "amber", bg = "rule") => {
        checkNums(x, y, w, h, frac);
        checkColor(fg);
        checkColor(bg);
        drawCalls += 1;
        drawTrace.push(`b:${Math.round(x)},${Math.round(y)},${Math.round(clamp(frac, 0, 1) * 100)}`);
      },
      spr: (name, x, y, scale = 1) => {
        checkNums(x, y, scale);
        if (!spriteNames.has(name)) missingSprites.add(name);
        drawCalls += 1;
        drawTrace.push(`s:${name}:${Math.round(x)},${Math.round(y)}`);
      },
      txt: (text, x, y, opts = {}) => {
        checkNums(x, y);
        checkColor(opts.color || "white");
        drawCalls += 1;
        drawTrace.push(`t:${String(text).slice(0, 24)}:${Math.round(x)},${Math.round(y)}`);
      },
    };

    try {
      if (typeof game.init === "function") game.init(g);
      game.draw(g);
      initScore = g.score;
      maxScore = g.score;
      minScore = g.score;
      for (let f = 0; f < frames; f++) {
        for (const k of Object.keys(held)) prevHeld[k] = held[k];
        prevPtrDown = ptr.down;
        const keys = [];
        inputScript(f, held, ptr, width, height, keys);
        const normKeys = keys.map(normKey).filter(Boolean);
        tickKeySet = new Set(normKeys);
        g.keys = normKeys;
        g.typed = normKeys.filter((k) => k.length === 1).join("");
        ptr.pressed = ptr.down && !prevPtrDown;
        ptr.released = !ptr.down && prevPtrDown;

        if (!ended) {
          g.t += g.dt;
          g.tick += 1;
          game.update(g, g.dt);
          if (!isFiniteNum(g.score)) nanFound = true;
          maxScore = Math.max(maxScore, g.score);
          minScore = Math.min(minScore, g.score);
          if (f === 0 && ended) firstFrameEnded = true;
        }
        if (f % 15 === 0 || f === frames - 1) {
          game.draw(g);
        }
      }
    } catch (err) {
      errors.push(`Runtime error in ${label}: ${err.message}`);
    }

    const survivedTicks = endedAtTick ?? frames;
    return {
      digest: hashString(drawTrace.join("|")),
      drawCallsPerSample: Math.round(drawCalls / (Math.floor(frames / 15) + 1)),
      initScore,
      maxScore,
      minScore,
      ended,
      survivedSec: Math.round((survivedTicks / 60) * 10) / 10,
      firstFrameEnded,
      endScore: g.score,
      hudLast,
    };
  };

  const isTyping = game.controls.layout === "typing";
  const idleShort = runScenario("idle-short", 30, () => {});
  const idle = runScenario("idle", 1800, () => {});
  const spam = runScenario("spam", 1800, (f, held, ptr, w, h, keys) => {
    const step = Math.floor(f / 8);
    held.left = step % 4 === 0;
    held.right = step % 4 === 2;
    held.up = step % 5 === 1;
    held.down = step % 5 === 3;
    held.a = f % 9 < 3;
    held.b = f % 14 === 4;
    ptr.down = f % 12 < 4;
    ptr.x = ((step * 53 + 29) % (w - 16)) + 8;
    ptr.y = ((step * 37 + 19) % (h - 16)) + 8;
    if (isTyping && f % 6 === 2) {
      const alpha = "etaoinshrdlcumwfgypbvkjxqz";
      const slot = Math.floor(f / 6);
      if (slot % 11 === 10) keys.push("Enter");
      else if (slot % 11 === 9) keys.push("Backspace");
      else if (slot % 11 === 5) keys.push(" ");
      else keys.push(alpha[(slot * 7 + 3) % alpha.length]);
    }
  }, 1337);
  const playA = runScenario("play-lr-a", 900, (f, held) => {
    held.left = f >= 20 && f < 140;
    held.right = (f >= 160 && f < 300) || (f >= 400 && f < 560);
    held.a = f % 18 === 5 || (f >= 320 && f < 350);
  });
  const playB = runScenario("play-ud-b-ptr", 900, (f, held, ptr, w, h) => {
    held.up = f >= 15 && f < 120;
    held.down = f >= 140 && f < 260;
    held.b = f % 25 === 10;
    ptr.down = f % 40 >= 10 && f % 40 <= 14;
    ptr.x = ((f * 13) % (w - 20)) + 10;
    ptr.y = ((f * 17) % (h - 20)) + 10;
  });
  const playPulse = runScenario("play-tap-grid", 600, (f, held) => {
    const phase = Math.floor(f / 6);
    const on = f % 6 === 1;
    held.right = on && phase % 12 < 8;
    held.down = on && phase % 12 >= 8 && phase % 12 < 10;
    held.up = on && phase % 12 === 10;
    held.left = on && phase % 12 === 11;
    held.a = f % 20 === 2;
  });
  const playType = runScenario("play-typing", 900, (f, _held, _ptr, _w, _h, keys) => {
    if (f < 20 || f % 7 !== 0) return;
    const seq = "abcdefghijklmnopqrstuvwxyz";
    const step = Math.floor(f / 7);
    if (step % 15 === 14) keys.push("Enter");
    else if (step % 15 === 10) keys.push("Backspace");
    else if (step % 15 === 6) keys.push(" ");
    else keys.push(seq[step % seq.length]);
  });
  const restart = runScenario("restart", 30, () => {});

  const responsive = [playA, playB, playPulse, playType].some((r) => r.digest !== idle.digest);

  if (nanFound) errors.push("Non-finite (NaN/Infinity) coordinate or score detected");
  if ([idle, spam, playA, playB, playPulse, playType].some((r) => r.firstFrameEnded)) {
    errors.push("Game ended on frame 1 (instant win/loss bug)");
  }
  if (idle.drawCallsPerSample < 2) errors.push("draw() emitted too few primitives per frame");
  if (!responsive && spam.digest === idle.digest) {
    errors.push("Inputs produced zero change in rendered output (controls may be disconnected)");
  }
  if (isTyping && playType.digest === idle.digest && spam.digest === idle.digest) {
    errors.push("controls.layout is \"typing\" but g.typed/g.keys/g.keyPressed produced zero change in rendered output");
  }
  if (restart.digest !== idleShort.digest) errors.push("Restart via init(g) did not reset all game state cleanly");
  if (idle.ended?.ok === true) errors.push("Zero-input idle scenario triggered win(); a game cannot auto-win with no player action");
  if (spam.ended?.ok === true) errors.push("Blind button-mashing / random clicks triggered win(); tighten precision, hazard pressure, or penalties");

  if (idle.maxScore > idle.initScore) {
    warnings.push(`Score increased while idle (${idle.initScore} -> ${idle.maxScore}); avoid passive free scoring`);
  }

  for (const c of unknownColors) warnings.push(`Unknown color token "${c}"`);
  for (const s of missingSprites) errors.push(`Undefined sprite referenced: "${s}"`);

  const activeMaxScore = Math.max(playA.maxScore, playB.maxScore, playPulse.maxScore, playType.maxScore, spam.maxScore);
  if (activeMaxScore <= idle.initScore) warnings.push("Score never increased across all automated input sweeps");

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    metrics: {
      lines,
      drawCallsPerFrame: idle.drawCallsPerSample,
      inputResponsive: responsive,
      idleSurvivedSec: idle.survivedSec,
      idleOutcome: idle.ended ? (idle.ended.ok ? "win" : "lose") : "ongoing",
      idleMaxScore: idle.maxScore,
      spamOutcome: spam.ended ? (spam.ended.ok ? "win" : "lose") : "ongoing",
      spamSurvivedSec: spam.survivedSec,
      spamMaxScore: spam.maxScore,
      activeMaxScore,
      outcomesSeen: [...outcomesSeen],
    },
  };
};

const argIdx = process.argv.indexOf("--file");
const target = path.resolve(argIdx !== -1 && process.argv[argIdx + 1] ? process.argv[argIdx + 1] : "game.js");
const report = validateGame(target);
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exit(1);
