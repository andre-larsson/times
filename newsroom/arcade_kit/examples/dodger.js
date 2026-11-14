export default {
  title: "CI Token Defender",
  dek: "Catch signed packages, quarantine poisoned npm updates before they leak keys.",
  width: 240,
  height: 160,
  controls: {
    layout: "lr+a",
    a: "PURGE",
    hint: "Move: Left/Right · Purge wave: Space/A",
  },
  howToPlay: {
    summary: "Catch 15 green signed packages before poisoned updates leak your CI secrets.",
    steps: [
      "Slide left or right to catch green packages (+10 pts).",
      "Dodge red hijacked packages—catching one costs a heart.",
      "When the PURGE bar fills, press Space / PURGE to clear all threats.",
    ],
    controls: "Left / Right or A / D · Space / PURGE",
  },
  sprites: {
    shield: [
      "..CCCC..",
      ".CCCCCC.",
      "CCWWWWCC",
      "CCCCCCCC",
      ".CCCCCC.",
      "..CCCC..",
    ],
    pkg: [
      ".GGGGGG.",
      "GWWWWWWG",
      "GWGGGGWG",
      "GGGGGGGG",
      "GGGGGGGG",
      ".GGGGGG.",
    ],
    malware: [
      ".RRRRRR.",
      "RKRKKRKR",
      "RRRRRRRR",
      "RRKKKKRR",
      "RKRKKRKR",
      ".RRRRRR.",
    ],
  },
  init(g) {
    g.state = {
      px: 112,
      lives: 3,
      purgeCharge: 1,
      spawnIn: 0.4,
      items: [],
      goal: 15,
      caught: 0,
    };
    g.hud("0/15 signed · ♥♥♥");
  },
  update(g, dt) {
    const s = g.state;
    const d = g.dir();
    s.px = g.clamp(s.px + d.x * 135 * dt, 6, g.w - 22);
    s.purgeCharge = g.clamp(s.purgeCharge + dt * 0.16, 0, 1);

    if (g.pressed("a") && s.purgeCharge >= 1) {
      s.purgeCharge = 0;
      g.sfx("shoot");
      g.flash("tech", 0.12);
      g.shake(2.5, 0.14);
      s.items = s.items.filter((it) => {
        if (it.bad) {
          g.particles(it.x + 6, it.y + 6, "danger", 8);
          g.score += 5;
          return false;
        }
        return true;
      });
    }

    s.spawnIn -= dt;
    if (s.spawnIn <= 0) {
      const rate = Math.max(0.32, 0.85 - g.t * 0.015);
      s.spawnIn = rate;
      const bad = g.rand() < Math.min(0.55, 0.3 + g.t * 0.008);
      s.items.push({
        x: g.randInt(10, g.w - 22),
        y: -12,
        vy: g.rand(46, 72) + g.t * 1.4,
        bad,
      });
    }

    const playerBox = { x: s.px, y: g.h - 22, w: 16, h: 12 };
    s.items = s.items.filter((it) => {
      it.y += it.vy * dt;
      if (g.hit(playerBox, { x: it.x, y: it.y, w: 12, h: 12 })) {
        if (it.bad) {
          s.lives -= 1;
          g.sfx("hit");
          g.shake(4, 0.2);
          g.flash("danger", 0.14);
          g.particles(it.x + 6, it.y + 6, "danger", 10);
          if (s.lives <= 0) g.lose("Secret leaked by poisoned package");
        } else {
          s.caught += 1;
          g.score += 10;
          g.sfx("coin");
          g.particles(it.x + 6, it.y + 6, "ok", 7);
          if (s.caught >= s.goal) g.win("All 15 builds verified safely");
        }
        return false;
      }
      if (it.y > g.h + 4) {
        if (!it.bad) g.score = Math.max(0, g.score - 2);
        return false;
      }
      return true;
    });

    g.hud(`${s.caught}/${s.goal} signed · ${"♥".repeat(Math.max(0, s.lives))}`);
  },
  draw(g) {
    const s = g.state;
    g.cls("dark");
    for (let x = 24; x < g.w; x += 24) g.line(x, 0, x, g.h - 14, "panel", 1);
    g.rect(0, g.h - 10, g.w, 10, "panel");
    g.txt("PURGE", 8, g.h - 8, { size: 6, color: s.purgeCharge >= 1 ? "tech" : "muted", bold: true });
    g.bar(36, g.h - 7, 56, 4, s.purgeCharge, s.purgeCharge >= 1 ? "tech" : "amber", "rule");

    for (const it of s.items) {
      g.spr(it.bad ? "malware" : "pkg", it.x, it.y, 2);
    }
    g.spr("shield", s.px, g.h - 22, 2);
  },
};
