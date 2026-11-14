const WORDS = [
  "token", "patch", "audit", "nonce", "proxy", "guard", "route", "cache",
  "mutex", "vault", "queue", "probe", "shell", "drift", "stack", "latch",
  "spoof", "scrub", "flush", "block", "alert", "scope", "epoch", "relay",
];

export default {
  title: "Packet Typist",
  dek: "Type incoming alert tags before they breach the firewall. Typos spike system heat.",
  width: 240,
  height: 160,
  controls: {
    layout: "typing",
    hint: "Type alert words · Backspace unlocks target",
  },
  howToPlay: {
    summary: "Neutralize 18 incoming threat tags by typing each word before it reaches the firewall.",
    steps: [
      "Type the first letter of any threat to lock on, then finish its letters.",
      "Wrong keys add heat—reaching 100% heat trips a cooldown lockout.",
      "Press Backspace to drop your current lock and switch targets.",
    ],
    controls: "Physical keyboard or tap keys below",
  },
  init(g) {
    g.state = {
      threats: [],
      lockId: null,
      nextId: 1,
      spawnT: 0.35,
      cleared: 0,
      goal: 18,
      lives: 3,
      heat: 0,
      jammed: 0,
      combo: 0,
    };
    g.hud("0/18 · ♥♥♥ · Heat 0%");
  },
  update(g, dt) {
    const s = g.state;
    const lvl = 1 + Math.floor(g.t / 10);
    s.heat = Math.max(0, s.heat - dt * 9);
    if (s.jammed > 0) s.jammed = Math.max(0, s.jammed - dt);

    s.spawnT -= dt;
    if (s.spawnT <= 0 && s.threats.length < 5) {
      s.spawnT = Math.max(0.7, 1.55 - lvl * 0.14);
      const usedFirst = new Set(s.threats.map((t) => t.word[0]));
      const pool = WORDS.filter((w) => !usedFirst.has(w[0]));
      const word = g.pick(pool.length ? pool : WORDS);
      s.threats.push({
        id: s.nextId++,
        word,
        idx: 0,
        x: g.randInt(28, g.w - 36),
        y: -8,
        vy: 14 + lvl * 3.5 + g.rand(0, 4),
      });
    }

    if (g.keyPressed("Backspace") && s.lockId !== null) {
      s.lockId = null;
      g.sfx("click");
    }

    for (const ch of g.typed) {
      if (ch < "a" || ch > "z" || s.jammed > 0) continue;
      let target = s.threats.find((t) => t.id === s.lockId);
      if (!target) {
        target = s.threats
          .filter((t) => t.word[0] === ch)
          .sort((a, b) => b.y - a.y)[0];
        if (target) s.lockId = target.id;
      }
      if (target && target.word[target.idx] === ch) {
        target.idx += 1;
        g.sfx("click");
        if (target.idx >= target.word.length) {
          s.cleared += 1;
          s.combo += 1;
          g.score += target.word.length * 4 + Math.min(s.combo, 8) * 2;
          g.sfx("coin");
          g.particles(target.x, target.y, "ok", 10);
          s.threats = s.threats.filter((t) => t.id !== target.id);
          s.lockId = null;
          if (s.cleared >= s.goal) {
            g.win(`All ${s.goal} threats neutralized in ${g.t.toFixed(1)}s`);
            return;
          }
        }
      } else {
        s.combo = 0;
        s.heat += 24;
        g.sfx("warn");
        g.shake(2, 0.1);
        if (s.heat >= 100) {
          s.heat = 100;
          s.jammed = 1.4;
          s.lockId = null;
          g.flash("danger", 0.12);
        }
      }
    }

    s.threats = s.threats.filter((t) => {
      t.y += t.vy * dt;
      if (t.y >= g.h - 20) {
        s.lives -= 1;
        s.combo = 0;
        if (s.lockId === t.id) s.lockId = null;
        g.sfx("hit");
        g.shake(4, 0.2);
        g.flash("danger", 0.14);
        g.particles(t.x, g.h - 20, "danger", 12);
        return false;
      }
      return true;
    });

    if (s.lives <= 0) {
      g.lose(`Firewall breached at ${s.cleared}/${s.goal} tags`);
      return;
    }
    const status = s.jammed > 0 ? "OVERHEAT!" : `Heat ${Math.round(s.heat)}%`;
    g.hud(`${s.cleared}/${s.goal} · ${"♥".repeat(s.lives)} · ${status}`);
  },
  draw(g) {
    const s = g.state;
    g.cls("dark");
    g.rect(0, g.h - 18, g.w, 18, "panel");
    g.line(0, g.h - 18, g.w, g.h - 18, s.jammed > 0 ? "danger" : "tech", 1);
    g.txt(s.jammed > 0 ? "OVERHEATED" : "FIREWALL", 6, g.h - 13, {
      size: 7,
      color: s.jammed > 0 ? "danger" : "tech",
      bold: true,
    });
    g.bar(168, g.h - 12, 64, 6, s.heat / 100, s.heat > 70 ? "danger" : "amber", "rule");

    for (const t of s.threats) {
      const locked = t.id === s.lockId;
      const w = t.word.length * 6 + 10;
      g.rect(t.x - w / 2, t.y - 7, w, 13, locked ? "#2b210b" : "panel", locked ? "amber" : "rule");
      const done = t.word.slice(0, t.idx);
      const rest = t.word.slice(t.idx);
      const tx = t.x - (t.word.length * 4.8) / 2;
      if (done) g.txt(done, tx, t.y - 4, { size: 8, color: "ok", bold: true });
      g.txt(rest, tx + done.length * 4.8, t.y - 4, { size: 8, color: locked ? "amber" : "white", bold: locked });
    }
  },
};
