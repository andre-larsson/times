const COLORS = {
  dark: "#14120f",
  panel: "#1e1b17",
  paper: "#fdfcf9",
  paper2: "#f3efe7",
  ink: "#17140f",
  muted: "#a1998d",
  rule: "#36322c",
  amber: "#ffb000",
  ai: "#7c3aed",
  violet: "#7c3aed",
  tech: "#0891b2",
  cyan: "#0891b2",
  gaming: "#16a34a",
  green: "#16a34a",
  deals: "#db2777",
  pink: "#db2777",
  screen: "#2563eb",
  blue: "#2563eb",
  ok: "#22c55e",
  warn: "#f59e0b",
  danger: "#ef4444",
  red: "#ef4444",
  orange: "#f97316",
  yellow: "#eab308",
  white: "#f6f3ec",
  black: "#0a0908",
  gray: "#78716c",
  grey: "#78716c",
};

const SPRITE_CHARS = {
  ".": null,
  " ": null,
  K: COLORS.ink,
  W: COLORS.white,
  M: COLORS.muted,
  A: COLORS.amber,
  V: COLORS.ai,
  C: COLORS.tech,
  G: COLORS.gaming,
  P: COLORS.deals,
  B: COLORS.screen,
  R: COLORS.danger,
  O: COLORS.orange,
  Y: COLORS.yellow,
};

const KEY_MAP = {
  ArrowLeft: "left",
  KeyA: "left",
  ArrowRight: "right",
  KeyD: "right",
  ArrowUp: "up",
  KeyW: "up",
  ArrowDown: "down",
  KeyS: "down",
  Space: "a",
  KeyZ: "a",
  Enter: "a",
  KeyX: "b",
  ShiftLeft: "b",
  ShiftRight: "b",
};

const SFX_PRESETS = {
  blip: [440, 520, 0.05, "square", 0.08],
  click: [680, 520, 0.03, "triangle", 0.07],
  coin: [587, 880, 0.11, "square", 0.09],
  jump: [240, 520, 0.12, "square", 0.09],
  shoot: [620, 180, 0.09, "sawtooth", 0.08],
  hit: [160, 55, 0.16, "sawtooth", 0.13],
  warn: [330, 220, 0.14, "square", 0.09],
  win: [523, 1046, 0.28, "triangle", 0.12],
  lose: [260, 90, 0.34, "sawtooth", 0.12],
};

const BUTTONS = ["left", "right", "up", "down", "a", "b"];

const resolveColor = (value, custom = {}) => {
  if (value == null) return null;
  const key = String(value);
  return custom[key] || COLORS[key] || key;
};

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

const buildSprite = (rows, customPalette) => {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const h = rows.length;
  const w = rows[0].length;
  const off = document.createElement("canvas");
  off.width = w;
  off.height = h;
  const octx = off.getContext("2d");
  for (let y = 0; y < h; y++) {
    const row = rows[y];
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === "." || ch === " ") continue;
      const color = customPalette[ch] || SPRITE_CHARS[ch];
      if (!color) continue;
      octx.fillStyle = color;
      octx.fillRect(x, y, 1, 1);
    }
  }
  return off;
};

const createAudio = () => {
  let ctx = null;
  let muted = false;
  const ensure = () => {
    if (muted) return null;
    if (!ctx && typeof AudioContext !== "undefined") ctx = new AudioContext();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  };
  const play = (name) => {
    const spec = SFX_PRESETS[name] || SFX_PRESETS.blip;
    const audio = ensure();
    if (!audio) return;
    const [f0, f1, dur, type, vol] = spec;
    const now = audio.currentTime;
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(f0, now);
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, f1), now + dur);
    gain.gain.setValueAtTime(vol, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(now);
    osc.stop(now + dur + 0.01);
  };
  return {
    play,
    isMuted: () => muted,
    toggle: () => {
      muted = !muted;
      return muted;
    },
    unlock: ensure,
  };
};

const padLayout = (layout) => {
  const mode = layout || "dpad+a";
  const dpad = mode.startsWith("dpad");
  const lr = mode.startsWith("lr");
  const a = mode.endsWith("+a") || mode.endsWith("+ab") || mode === "a" || mode === "ab";
  const b = mode.endsWith("+ab") || mode === "ab";
  const qwerty = mode === "typing";
  return { dpad, lr, a, b, qwerty, hasButtons: dpad || lr || a || b };
};

const defaultControlsText = (controls) => {
  if (controls.hint) return controls.hint;
  const mode = controls.layout || "dpad+a";
  if (mode === "pointer") return "Tap or drag directly on the screen";
  if (mode === "typing") return "Type on keyboard or tap keys below";
  const move = mode.startsWith("lr") ? "Left / Right or A / D" : mode.startsWith("dpad") ? "Arrows / WASD" : "";
  const actA = mode.endsWith("+a") || mode === "a" ? (controls.a || "Space / A") : "";
  const actAB = mode.endsWith("+ab") || mode === "ab" ? `${controls.a || "Space/A"} & ${controls.b || "Shift/B"}` : "";
  return [move, actA || actAB].filter(Boolean).join(" · ");
};

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

const normalizeHowToPlay = (game, controls) => {
  const raw = game.howToPlay;
  const fallbackControls = defaultControlsText(controls);
  if (raw === false) {
    return { summary: String(game.dek || ""), steps: [], controls: fallbackControls, autoShow: false };
  }
  if (typeof raw === "string") {
    return { summary: raw.trim(), steps: [], controls: fallbackControls, autoShow: true };
  }
  if (Array.isArray(raw)) {
    return {
      summary: String(game.dek || ""),
      steps: raw.filter(Boolean).map((s) => String(s).trim()),
      controls: fallbackControls,
      autoShow: true,
    };
  }
  if (raw && typeof raw === "object") {
    return {
      summary: String(raw.summary || game.dek || "").trim(),
      steps: Array.isArray(raw.steps) ? raw.steps.filter(Boolean).map((s) => String(s).trim()) : [],
      controls: String(raw.controls || fallbackControls).trim(),
      autoShow: raw.showOnce !== false && raw.autoShow !== false,
    };
  }
  return {
    summary: String(game.dek || "").trim(),
    steps: [],
    controls: fallbackControls,
    autoShow: Boolean(game.dek || fallbackControls),
  };
};

const makeBtn = (label, btnName, className, onHold) => {
  const el = document.createElement("button");
  el.type = "button";
  el.className = className;
  el.textContent = label;
  el.setAttribute("aria-label", label);
  const setDown = (down) => {
    el.classList.toggle("is-down", down);
    onHold(btnName, down);
  };
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    el.setPointerCapture?.(e.pointerId);
    setDown(true);
  });
  el.addEventListener("pointerup", () => setDown(false));
  el.addEventListener("pointercancel", () => setDown(false));
  el.addEventListener("lostpointercapture", () => setDown(false));
  return el;
};

const makeKeyBtn = (label, keyVal, className, onKey) => {
  const el = document.createElement("button");
  el.type = "button";
  el.className = className;
  el.textContent = label;
  el.setAttribute("aria-label", keyVal === " " ? "Space" : keyVal);
  const release = () => el.classList.remove("is-down");
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    el.setPointerCapture?.(e.pointerId);
    el.classList.add("is-down");
    onKey(keyVal);
  });
  el.addEventListener("pointerup", release);
  el.addEventListener("pointercancel", release);
  el.addEventListener("lostpointercapture", release);
  return el;
};

export const mountArcade = (root, game, options = {}) => {
  if (!root || !game || typeof game.update !== "function" || typeof game.draw !== "function") {
    throw new Error("mountArcade requires a container element and a game with update() and draw()");
  }

  const width = clamp(Math.round(game.width || 240), 120, 480);
  const height = clamp(Math.round(game.height || 160), 100, 360);
  const scale = 3;
  const customPalette = game.palette || {};
  const reducedMotion = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const audio = createAudio();
  const controls = game.controls || {};
  const layout = padLayout(controls.layout);
  const helpSpec = normalizeHowToPlay(game, controls);

  root.innerHTML = "";
  root.classList.add("arcade-root");

  const hud = document.createElement("div");
  hud.className = "arcade-hud";
  const scoreEl = document.createElement("span");
  scoreEl.className = "arcade-score";
  const statusEl = document.createElement("span");
  statusEl.className = "arcade-status";
  const actions = document.createElement("div");
  actions.className = "arcade-actions";

  const helpBtn = document.createElement("button");
  helpBtn.type = "button";
  helpBtn.className = "arcade-mini-btn arcade-help-btn";
  helpBtn.textContent = "? How to play";

  const muteBtn = document.createElement("button");
  muteBtn.type = "button";
  muteBtn.className = "arcade-mini-btn";
  muteBtn.textContent = "Sound: On";
  muteBtn.addEventListener("click", () => {
    const m = audio.toggle();
    muteBtn.textContent = m ? "Sound: Off" : "Sound: On";
  });

  const restartBtn = document.createElement("button");
  restartBtn.type = "button";
  restartBtn.className = "arcade-mini-btn";
  restartBtn.textContent = "Restart";
  actions.append(helpBtn, muteBtn, restartBtn);
  hud.append(scoreEl, statusEl, actions);

  const stage = document.createElement("div");
  stage.className = "arcade-stage";
  const canvas = document.createElement("canvas");
  canvas.className = "arcade-canvas";
  canvas.width = width * scale;
  canvas.height = height * scale;
  canvas.style.aspectRatio = `${width} / ${height}`;
  canvas.tabIndex = 0;

  const overlay = document.createElement("div");
  overlay.className = "arcade-overlay";
  overlay.hidden = true;
  const overBadge = document.createElement("p");
  overBadge.className = "arcade-over-badge";
  const overTitle = document.createElement("p");
  overTitle.className = "arcade-over-title";
  const overScore = document.createElement("p");
  overScore.className = "arcade-over-score";
  const overBtn = document.createElement("button");
  overBtn.type = "button";
  overBtn.className = "arcade-over-btn";
  overBtn.textContent = "Play again";
  overlay.append(overBadge, overTitle, overScore, overBtn);

  const helpOverlay = document.createElement("div");
  helpOverlay.className = "arcade-help-overlay";
  helpOverlay.hidden = true;
  helpOverlay.setAttribute("role", "dialog");
  helpOverlay.setAttribute("aria-modal", "true");
  helpOverlay.setAttribute("aria-label", "How to play");

  const helpCard = document.createElement("div");
  helpCard.className = "arcade-help-card";
  const helpKicker = document.createElement("p");
  helpKicker.className = "arcade-help-kicker";
  helpKicker.textContent = "How to play";
  const helpTitle = document.createElement("h2");
  helpTitle.className = "arcade-help-title";
  helpTitle.textContent = game.title || "403 Arcade";
  helpCard.append(helpKicker, helpTitle);

  if (helpSpec.summary) {
    const helpSummary = document.createElement("p");
    helpSummary.className = "arcade-help-summary";
    helpSummary.textContent = helpSpec.summary;
    helpCard.append(helpSummary);
  }
  if (helpSpec.steps.length) {
    const list = document.createElement("ol");
    list.className = "arcade-help-steps";
    for (const step of helpSpec.steps) {
      const li = document.createElement("li");
      li.textContent = step;
      list.append(li);
    }
    helpCard.append(list);
  }
  if (helpSpec.controls) {
    const ctrlBox = document.createElement("p");
    ctrlBox.className = "arcade-help-controls";
    const ctrlLabel = document.createElement("strong");
    ctrlLabel.textContent = "Controls: ";
    ctrlBox.append(ctrlLabel, document.createTextNode(helpSpec.controls));
    helpCard.append(ctrlBox);
  }

  const helpActions = document.createElement("div");
  helpActions.className = "arcade-help-actions";
  const helpStartBtn = document.createElement("button");
  helpStartBtn.type = "button";
  helpStartBtn.className = "arcade-over-btn";
  helpActions.append(helpStartBtn);
  const helpNote = document.createElement("span");
  helpNote.className = "arcade-help-note";
  helpNote.textContent = "Open anytime with ? How to play";
  helpActions.append(helpNote);
  helpCard.append(helpActions);
  helpOverlay.append(helpCard);

  stage.append(canvas, overlay, helpOverlay);

  const pad = document.createElement("div");
  pad.className = "arcade-pad";
  if (!layout.hasButtons && !layout.qwerty) pad.hidden = true;

  const held = Object.fromEntries(BUTTONS.map((b) => [b, false]));
  const prevHeld = { ...held };
  const touchHeld = { ...held };
  const keyHeld = { ...held };
  let pendingKeys = [];
  let tickKeys = [];
  let tickKeysSet = new Set();

  const enqueueKey = (raw) => {
    if (helpOpen || ended) return;
    audio.unlock();
    const key = normKey(raw);
    if (key) pendingKeys.push(key);
  };

  const syncTouch = (name, down) => {
    audio.unlock();
    touchHeld[name] = down;
  };

  if (layout.qwerty) {
    pad.classList.add("arcade-pad--typing");
    const qwerty = document.createElement("div");
    qwerty.className = "arcade-qwerty";
    const mkRow = (cls) => {
      const row = document.createElement("div");
      row.className = cls ? `arcade-qrow ${cls}` : "arcade-qrow";
      return row;
    };
    const r1 = mkRow("");
    for (const ch of "qwertyuiop") r1.append(makeKeyBtn(ch, ch, "arcade-qkey", enqueueKey));
    const r2 = mkRow("arcade-qrow--mid");
    for (const ch of "asdfghjkl") r2.append(makeKeyBtn(ch, ch, "arcade-qkey", enqueueKey));
    const r3 = mkRow("arcade-qrow--bot");
    for (const ch of "zxcvbnm") r3.append(makeKeyBtn(ch, ch, "arcade-qkey", enqueueKey));
    r3.append(makeKeyBtn("DEL", "Backspace", "arcade-qkey arcade-qkey--wide", enqueueKey));
    const r4 = mkRow("");
    r4.append(
      makeKeyBtn("Space", " ", "arcade-qkey arcade-qkey--space", enqueueKey),
      makeKeyBtn("Enter ↵", "Enter", "arcade-qkey arcade-qkey--enter", enqueueKey),
    );
    qwerty.append(r1, r2, r3, r4);
    pad.append(qwerty);
  } else if (layout.dpad) {
    const dpad = document.createElement("div");
    dpad.className = "arcade-dpad";
    const up = makeBtn("▲", "up", "arcade-btn arcade-btn--up", syncTouch);
    const left = makeBtn("◀", "left", "arcade-btn arcade-btn--left", syncTouch);
    const right = makeBtn("▶", "right", "arcade-btn arcade-btn--right", syncTouch);
    const down = makeBtn("▼", "down", "arcade-btn arcade-btn--down", syncTouch);
    dpad.append(up, left, right, down);
    pad.append(dpad);
  } else if (layout.lr) {
    const lr = document.createElement("div");
    lr.className = "arcade-lr";
    lr.append(
      makeBtn("◀", "left", "arcade-btn", syncTouch),
      makeBtn("▶", "right", "arcade-btn", syncTouch),
    );
    pad.append(lr);
  }

  if (layout.a || layout.b) {
    const ab = document.createElement("div");
    ab.className = "arcade-ab";
    if (layout.b) ab.append(makeBtn(controls.b || "B", "b", "arcade-btn arcade-btn--b", syncTouch));
    if (layout.a) ab.append(makeBtn(controls.a || "A", "a", "arcade-btn arcade-btn--a", syncTouch));
    pad.append(ab);
  }

  const hint = document.createElement("p");
  hint.className = "arcade-hint";
  hint.textContent = controls.hint || defaultControlsText(controls);

  root.append(hud, stage, pad, hint);

  const ctx = canvas.getContext("2d");
  const sprites = {};
  for (const [name, rows] of Object.entries(game.sprites || {})) {
    const img = buildSprite(rows, customPalette);
    if (img) sprites[name] = img;
  }

  let bestScore = Math.max(0, Math.round(Number(options.bestScore) || 0));
  let sentBest = bestScore;
  let ended = null;
  let endedAt = 0;
  let hasPlayed = Boolean(options.helpSeen);
  let helpOpen = false;
  let shakeTime = 0;
  let shakeMag = 0;
  let flashTime = 0;
  let flashColor = null;
  let particles = [];
  let hudText = "";
  const ptr = { x: width / 2, y: height / 2, down: false, pressed: false, released: false };
  let ptrDownNow = false;
  let ptrPrevDown = false;

  const clearInputs = () => {
    for (const b of BUTTONS) {
      held[b] = false;
      prevHeld[b] = false;
      touchHeld[b] = false;
      keyHeld[b] = false;
    }
    pendingKeys = [];
    tickKeys = [];
    tickKeysSet = new Set();
    g.keys = [];
    g.typed = "";
    ptrDownNow = false;
    ptrPrevDown = false;
    ptr.down = false;
    ptr.pressed = false;
    ptr.released = false;
  };

  const markHelpSeen = () => {
    if (hasPlayed) return;
    hasPlayed = true;
    if (typeof options.onHelpSeen === "function") options.onHelpSeen();
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "arcade:helpSeen", id: options.gameId || game.title || "" }, "*");
      }
    } catch {
      /* sandboxed cross-origin messaging fallback */
    }
  };

  const openHelp = () => {
    clearInputs();
    helpOpen = true;
    stage.classList.add("is-help-open");
    helpStartBtn.textContent = ended ? "Back" : hasPlayed ? "Resume" : "Start game";
    helpOverlay.hidden = false;
    helpBtn.setAttribute("aria-expanded", "true");
    helpStartBtn.focus({ preventScroll: true });
  };

  const closeHelp = () => {
    if (!helpOpen) return;
    clearInputs();
    helpOpen = false;
    stage.classList.remove("is-help-open");
    helpOverlay.hidden = true;
    helpBtn.setAttribute("aria-expanded", "false");
    markHelpSeen();
    audio.unlock();
    canvas.focus({ preventScroll: true });
  };

  helpBtn.addEventListener("click", () => {
    if (helpOpen) closeHelp();
    else openHelp();
  });
  helpStartBtn.addEventListener("click", closeHelp);
  helpOverlay.addEventListener("click", (e) => {
    if (e.target === helpOverlay) closeHelp();
  });

  const updatePtrCoords = (e) => {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    ptr.x = clamp(((e.clientX - rect.left) / rect.width) * width, 0, width);
    ptr.y = clamp(((e.clientY - rect.top) / rect.height) * height, 0, height);
  };

  canvas.addEventListener("pointerdown", (e) => {
    if (helpOpen) return;
    audio.unlock();
    canvas.focus({ preventScroll: true });
    updatePtrCoords(e);
    ptrDownNow = true;
  });
  window.addEventListener("pointermove", (e) => {
    if (ptrDownNow || e.target === canvas) updatePtrCoords(e);
  });
  window.addEventListener("pointerup", () => {
    ptrDownNow = false;
  });

  window.addEventListener("keydown", (e) => {
    if (helpOpen) {
      if (e.code === "Escape" || e.code === "Space" || e.code === "Enter") {
        e.preventDefault();
        closeHelp();
      }
      return;
    }
    if (ended) {
      const cooldown = layout.qwerty ? 450 : 350;
      const restartKey = layout.qwerty
        ? (e.code === "Enter")
        : (e.code === "Space" || e.code === "Enter" || e.code === "KeyR");
      if (!e.repeat && performance.now() - endedAt > cooldown && restartKey) {
        e.preventDefault();
        reset();
      }
      return;
    }
    if (layout.hasButtons) {
      const btn = KEY_MAP[e.code];
      if (btn) {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space"].includes(e.code)) e.preventDefault();
        audio.unlock();
        keyHeld[btn] = true;
      }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (["Space", "Backspace", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.code) || e.key === "/" || e.key === "'") {
      e.preventDefault();
    }
    if (e.key === "Backspace" || e.key.startsWith("Arrow")) {
      enqueueKey(e.key);
    } else if (!e.repeat && (e.key === "Enter" || e.key === "Escape" || e.key.length === 1)) {
      enqueueKey(e.key);
    }
  });
  window.addEventListener("keyup", (e) => {
    if (!layout.hasButtons) return;
    const btn = KEY_MAP[e.code];
    if (btn) keyHeld[btn] = false;
  });

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
    keyPressed: (k) => tickKeysSet.has(normKey(k)),
    held: (b) => Boolean(held[b]),
    pressed: (b) => Boolean(held[b] && !prevHeld[b]),
    dir: () => ({ x: (held.right ? 1 : 0) - (held.left ? 1 : 0), y: (held.down ? 1 : 0) - (held.up ? 1 : 0) }),
    dirPressed: () => ({
      x: (g.pressed("right") ? 1 : 0) - (g.pressed("left") ? 1 : 0),
      y: (g.pressed("down") ? 1 : 0) - (g.pressed("up") ? 1 : 0),
    }),
    clamp,
    lerp: (a, b, t) => a + (b - a) * t,
    dist: (x1, y1, x2, y2) => Math.hypot(x2 - x1, y2 - y1),
    rand: (min = 0, max = 1) => min + Math.random() * (max - min),
    randInt: (min, max) => Math.floor(min + Math.random() * (max - min + 1)),
    pick: (arr) => (arr && arr.length ? arr[Math.floor(Math.random() * arr.length)] : undefined),
    hit: hitTest,
    inRect: (px, py, x, y, w, h) => px >= x && px <= x + w && py >= y && py <= y + h,
    hud: (text) => { hudText = String(text ?? ""); },
    sfx: (name) => audio.play(name),
    shake: (amount = 3, secs = 0.18) => {
      if (reducedMotion) return;
      shakeMag = Math.max(shakeMag, amount);
      shakeTime = Math.max(shakeTime, secs);
    },
    flash: (color = "white", secs = 0.1) => {
      if (reducedMotion) return;
      flashColor = resolveColor(color, customPalette);
      flashTime = Math.max(flashTime, secs);
    },
    particles: (x, y, color = "amber", count = 8) => {
      if (reducedMotion) return;
      const fill = resolveColor(color, customPalette);
      for (let i = 0; i < count; i++) {
        const ang = (Math.PI * 2 * i) / count + Math.random() * 0.5;
        const spd = 25 + Math.random() * 65;
        particles.push({ x, y, vx: Math.cos(ang) * spd, vy: Math.sin(ang) * spd, life: 0.35 + Math.random() * 0.2, max: 0.55, fill });
      }
    },
    win: (msg = "Victory") => {
      if (ended) return;
      ended = { ok: true, msg: String(msg) };
      audio.play("win");
      showEnd();
    },
    lose: (msg = "Game over") => {
      if (ended) return;
      ended = { ok: false, msg: String(msg) };
      audio.play("lose");
      showEnd();
    },
    cls: (color = "dark") => {
      ctx.fillStyle = resolveColor(color, customPalette);
      ctx.fillRect(0, 0, width, height);
    },
    rect: (x, y, w, h, fill = "amber", stroke = null) => {
      if (fill) {
        ctx.fillStyle = resolveColor(fill, customPalette);
        ctx.fillRect(x, y, w, h);
      }
      if (stroke) {
        ctx.strokeStyle = resolveColor(stroke, customPalette);
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, y + 0.5, Math.max(0, w - 1), Math.max(0, h - 1));
      }
    },
    circ: (x, y, r, fill = "amber", stroke = null) => {
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0, r), 0, Math.PI * 2);
      if (fill) {
        ctx.fillStyle = resolveColor(fill, customPalette);
        ctx.fill();
      }
      if (stroke) {
        ctx.strokeStyle = resolveColor(stroke, customPalette);
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    },
    line: (x1, y1, x2, y2, color = "white", lineWidth = 1) => {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = resolveColor(color, customPalette);
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    },
    poly: (points, fill = "amber", stroke = null) => {
      if (!Array.isArray(points) || points.length < 2) return;
      ctx.beginPath();
      points.forEach((p, idx) => {
        const px = Array.isArray(p) ? p[0] : p.x;
        const py = Array.isArray(p) ? p[1] : p.y;
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      if (fill) {
        ctx.fillStyle = resolveColor(fill, customPalette);
        ctx.fill();
      }
      if (stroke) {
        ctx.strokeStyle = resolveColor(stroke, customPalette);
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    },
    bar: (x, y, w, h, frac, fg = "amber", bg = "rule") => {
      g.rect(x, y, w, h, bg, null);
      g.rect(x, y, w * clamp(frac, 0, 1), h, fg, null);
    },
    spr: (name, x, y, sprScale = 1, flipX = false, flipY = false) => {
      const img = sprites[name];
      if (!img) return;
      ctx.save();
      ctx.imageSmoothingEnabled = false;
      ctx.translate(Math.round(x), Math.round(y));
      ctx.scale(flipX ? -sprScale : sprScale, flipY ? -sprScale : sprScale);
      ctx.drawImage(img, flipX ? -img.width : 0, flipY ? -img.height : 0);
      ctx.restore();
    },
    txt: (text, x, y, opts = {}) => {
      const size = opts.size || 8;
      const weight = opts.bold ? "700" : "500";
      ctx.font = `${weight} ${size}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;
      ctx.textAlign = opts.align || "left";
      ctx.textBaseline = opts.baseline || "top";
      ctx.fillStyle = resolveColor(opts.color || "white", customPalette);
      const raw = String(text ?? "");
      if (!opts.maxWidth) {
        ctx.fillText(raw, x, y);
        return;
      }
      const lines = [];
      for (const para of raw.split("\n")) {
        let line = "";
        for (const word of para.split(/\s+/)) {
          const test = line ? `${line} ${word}` : word;
          if (ctx.measureText(test).width > opts.maxWidth && line) {
            lines.push(line);
            line = word;
          } else {
            line = test;
          }
        }
        lines.push(line);
      }
      const step = size * 1.25;
      lines.forEach((l, i) => ctx.fillText(l, x, y + i * step));
    },
  };

  const syncBest = () => {
    const score = Math.round(g.score);
    if (score > bestScore) {
      bestScore = score;
      if (bestScore > sentBest) {
        sentBest = bestScore;
        try {
          if (window.parent && window.parent !== window) {
            window.parent.postMessage({ type: "arcade:best", id: options.gameId || game.title || "", best: bestScore }, "*");
          }
        } catch {
          /* sandboxed cross-origin messaging fallback */
        }
      }
    }
  };

  const showEnd = () => {
    endedAt = performance.now();
    syncBest();
    overBadge.textContent = ended.ok ? "200 CLEARED" : "403 GAME OVER";
    overBadge.dataset.ok = ended.ok ? "1" : "0";
    overTitle.textContent = ended.msg;
    overScore.textContent = `Score: ${Math.round(g.score)} · Best: ${bestScore}`;
    overlay.hidden = false;
  };

  const reset = () => {
    ended = null;
    overlay.hidden = true;
    g.t = 0;
    g.tick = 0;
    g.score = 0;
    g.state = {};
    hudText = "";
    particles = [];
    shakeTime = 0;
    shakeMag = 0;
    flashTime = 0;
    clearInputs();
    if (typeof game.init === "function") game.init(g);
    updateHud();
    if (!helpOpen) canvas.focus({ preventScroll: true });
  };

  const updateHud = () => {
    syncBest();
    scoreEl.textContent = `Score ${Math.round(g.score)} · Best ${bestScore}`;
    statusEl.textContent = hudText;
  };

  restartBtn.addEventListener("click", () => {
    markHelpSeen();
    if (helpOpen) closeHelp();
    reset();
  });
  overBtn.addEventListener("click", () => {
    markHelpSeen();
    reset();
  });

  reset();
  if (helpSpec.autoShow && !options.helpSeen) {
    openHelp();
  } else {
    helpBtn.setAttribute("aria-expanded", "false");
  }

  let lastTs = performance.now();
  let accum = g.dt;
  let rafId = 0;

  const frame = (ts) => {
    const dtReal = Math.min(0.05, (ts - lastTs) / 1000);
    lastTs = ts;
    accum += dtReal;

    while (accum >= g.dt) {
      accum -= g.dt;
      for (const b of BUTTONS) {
        prevHeld[b] = held[b];
        held[b] = !helpOpen && (keyHeld[b] || touchHeld[b]);
      }
      ptr.down = !helpOpen && ptrDownNow;
      ptr.pressed = !helpOpen && ptrDownNow && !ptrPrevDown;
      ptr.released = !helpOpen && !ptrDownNow && ptrPrevDown;
      ptrPrevDown = !helpOpen && ptrDownNow;

      if (!ended && !helpOpen) {
        const drained = pendingKeys.length ? pendingKeys : [];
        if (drained.length) pendingKeys = [];
        tickKeys = drained;
        tickKeysSet = new Set(drained);
        g.keys = tickKeys;
        g.typed = tickKeys.filter((k) => k.length === 1).join("");
        g.t += g.dt;
        g.tick += 1;
        game.update(g, g.dt);
        particles = particles.filter((p) => {
          p.x += p.vx * g.dt;
          p.y += p.vy * g.dt;
          p.life -= g.dt;
          return p.life > 0;
        });
        if (shakeTime > 0) shakeTime = Math.max(0, shakeTime - g.dt);
        if (shakeTime === 0) shakeMag = 0;
        if (flashTime > 0) flashTime = Math.max(0, flashTime - g.dt);
      }
    }

    ctx.save();
    ctx.scale(scale, scale);
    if (shakeTime > 0 && !helpOpen) {
      ctx.translate((Math.random() * 2 - 1) * shakeMag, (Math.random() * 2 - 1) * shakeMag);
    }
    game.draw(g);
    for (const p of particles) {
      ctx.globalAlpha = clamp(p.life / p.max, 0, 1);
      ctx.fillStyle = p.fill;
      ctx.fillRect(p.x - 1, p.y - 1, 2, 2);
    }
    ctx.globalAlpha = 1;
    if (flashTime > 0 && flashColor) {
      ctx.globalAlpha = clamp(flashTime * 3, 0, 0.35);
      ctx.fillStyle = flashColor;
      ctx.fillRect(0, 0, width, height);
      ctx.globalAlpha = 1;
    }
    ctx.restore();

    updateHud();
    rafId = requestAnimationFrame(frame);
  };

  rafId = requestAnimationFrame(frame);

  let ro = null;
  const notifyHeight = () => {
    const h = Math.ceil(Math.max(root.getBoundingClientRect().height, root.scrollHeight, document.body.scrollHeight));
    if (h < 100) return;
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "arcade:height", id: options.gameId || game.title || "", height: h }, "*");
      }
    } catch {
      /* ignore cross-origin restrictions */
    }
  };
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(notifyHeight);
    ro.observe(root);
  }
  requestAnimationFrame(notifyHeight);

  return () => {
    cancelAnimationFrame(rafId);
    ro?.disconnect();
  };
};
