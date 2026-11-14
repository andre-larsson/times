export default {
  title: "Rack Router",
  dek: "Route packets to clean nodes while dodging overloaded racks before the SLA clock hits zero.",
  width: 240,
  height: 160,
  controls: {
    layout: "dpad+a",
    a: "FLUSH",
    hint: "Step: Arrows/WASD · Clear hazard: Space/A",
  },
  howToPlay: {
    summary: "Deliver 10 amber packets across the grid before the SLA timer runs out.",
    steps: [
      "Step tile by tile toward each amber packet (+2.5s bonus per delivery).",
      "Avoid red overloaded racks—colliding with one ends the round.",
      "Press FLUSH to clear the oldest hazard rack (2 charges total).",
    ],
    controls: "Arrows / WASD (or D-pad) · Space / FLUSH",
  },
  sprites: {
    bot: [
      "..CCCC..",
      ".CWWWWC.",
      "CCKCCKCC",
      "CCCCCCCC",
      ".CAAAAC.",
      "..C..C..",
    ],
    packet: [
      "..AAAA..",
      ".AAWWAA.",
      "AAWWWWAA",
      ".AAWWAA.",
      "..AAAA..",
      "........",
    ],
    spike: [
      "..RRRR..",
      ".RRRRRR.",
      "RRKKKKRR",
      "RRRRRRRR",
      ".R.RR.R.",
      "R......R",
    ],
  },
  init(g) {
    g.state = {
      cols: 12,
      rows: 7,
      gx: 1,
      gy: 3,
      px: 9,
      py: 3,
      timeLeft: 30,
      flushes: 2,
      delivered: 0,
      target: 10,
      hazards: [
        { x: 4, y: 1, dy: 1 },
        { x: 7, y: 5, dy: -1 },
        { x: 10, y: 2, dy: 1 },
      ],
      stepTimer: 0,
    };
    g.hud("0/10 packets · 2 flushes");
  },
  update(g, dt) {
    const s = g.state;
    s.timeLeft -= dt;
    if (s.timeLeft <= 0) {
      g.lose(`SLA expired at ${s.delivered}/${s.target} packets`);
      return;
    }

    const step = g.dirPressed();
    if (step.x !== 0 || step.y !== 0) {
      const nx = g.clamp(s.gx + step.x, 0, s.cols - 1);
      const ny = g.clamp(s.gy + step.y, 0, s.rows - 1);
      if (nx !== s.gx || ny !== s.gy) {
        s.gx = nx;
        s.gy = ny;
        g.sfx("click");
      }
    }

    if (g.pressed("a") && s.flushes > 0 && s.hazards.length > 0) {
      s.flushes -= 1;
      s.hazards.shift();
      g.sfx("shoot");
      g.flash("amber", 0.1);
      g.shake(2, 0.12);
    }

    s.stepTimer += dt;
    if (s.stepTimer >= 0.42) {
      s.stepTimer = 0;
      for (const h of s.hazards) {
        h.y += h.dy;
        if (h.y <= 0 || h.y >= s.rows - 1) h.dy *= -1;
      }
    }

    if (s.gx === s.px && s.gy === s.py) {
      s.delivered += 1;
      g.score += 15;
      s.timeLeft = Math.min(35, s.timeLeft + 2.5);
      g.sfx("coin");
      g.particles(24 + s.px * 16 + 8, 28 + s.py * 16 + 8, "amber", 10);
      if (s.delivered >= s.target) {
        g.score += Math.round(s.timeLeft * 3);
        g.win("All 10 packets routed under SLA");
        return;
      }
      do {
        s.px = g.randInt(0, s.cols - 1);
        s.py = g.randInt(0, s.rows - 1);
      } while (s.px === s.gx && s.py === s.gy);
      if (s.delivered % 3 === 0 && s.hazards.length < 6) {
        s.hazards.push({ x: g.randInt(1, s.cols - 2), y: 0, dy: 1 });
      }
    }

    for (const h of s.hazards) {
      if (h.x === s.gx && h.y === s.gy) {
        g.sfx("hit");
        g.shake(4, 0.2);
        g.lose("Packet dropped on overloaded rack");
        return;
      }
    }

    g.hud(`${s.delivered}/${s.target} · ${s.flushes} flush · ${Math.ceil(s.timeLeft)}s`);
  },
  draw(g) {
    const s = g.state;
    const ox = 24;
    const oy = 28;
    const cell = 16;
    g.cls("dark");
    g.txt("SLA", 24, 10, { size: 7, color: "muted", bold: true });
    g.bar(46, 11, 170, 6, s.timeLeft / 30, s.timeLeft < 8 ? "danger" : "tech", "panel");

    for (let y = 0; y < s.rows; y++) {
      for (let x = 0; x < s.cols; x++) {
        const bg = (x + y) % 2 === 0 ? "panel" : "#181511";
        g.rect(ox + x * cell, oy + y * cell, cell - 1, cell - 1, bg);
      }
    }

    g.spr("packet", ox + s.px * cell + 2, oy + s.py * cell + 2, 1.5);
    for (const h of s.hazards) {
      g.spr("spike", ox + h.x * cell + 2, oy + h.y * cell + 2, 1.5);
    }
    g.spr("bot", ox + s.gx * cell + 2, oy + s.gy * cell + 2, 1.5);
  },
};
