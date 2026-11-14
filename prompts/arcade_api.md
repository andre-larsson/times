# 403 Arcade Micro-API (v2)

Write a single ES module (`game.js`) with **no imports** and **one `export default { ... }`** object.
The runtime handles canvas scaling, `60 Hz` loop, keyboard + mobile touch pad, HUD, audio synth, particles, Play Again reset, and the **How to play** screen + `? How to play` HUD button.

## Module shape

```js
export default {
  title: "Short Game Title",          // <= 60 chars
  dek: "One-line premise & goal.",    // <= 140 chars
  width: 240,                         // virtual width (120..480, default 240)
  height: 160,                        // virtual height (100..360, default 160)
  controls: {
    layout: "lr+a",                   // "dpad"|"dpad+a"|"dpad+ab"|"lr"|"lr+a"|"lr+ab"|"a"|"ab"|"pointer"|"typing"
    a: "PURGE",                       // optional mobile button label
    b: "DASH",                        // optional
    hint: "Left/Right or A/D · Purge: Space/A",
  },
  howToPlay: {                        // shown once automatically on first load, and via "? How to play"
    summary: "Catch green signed builds and avoid red poisoned packages.",
    steps: [                          // 2-4 concise rules (<= 110 chars each)
      "Move the shield left or right to catch 15 green packages.",
      "Dodge red packages—any hit costs a life.",
      "Press Purge when charged to vaporize every threat on screen.",
    ],
    controls: "Left / Right or A / D · Space / Purge button",
  },
  palette: { X: "#38bdf8" },          // optional extra color/sprite keys
  sprites: {
    hero: [
      "..AAAA..",
      ".AAAAAA.",
      "AAWAAWAA",
      "AAAAAAAA",
      ".AAKKAA.",
      "..AAAA..",
    ],
  },
  init(g) { ... },                    // initialize ALL mutable state on g.state (draw() runs immediately after)
  update(g, dt) { ... },              // fixed 60 Hz step (dt = 1/60), paused while How to play is open
  draw(g) { ... },                    // start with g.cls("dark") or g.cls("paper")
};
```

## Colors & Sprite keys

Built-in colors (plus any `#hex` or `rgb(...)` / `rgba(...)`):
- Surfaces/Ink: `"dark"`, `"panel"`, `"paper"`, `"paper2"`, `"ink"`, `"muted"`, `"rule"`, `"white"`, `"black"`
- 403 Accents: `"amber"`, `"ai"` (violet), `"tech"` (cyan), `"gaming"` (green), `"deals"` (pink), `"screen"` (blue), `"ok"`, `"warn"`, `"danger"`

Default sprite palette chars (`.` or space = transparent):
- `K` ink, `W` white, `M` muted, `A` amber, `V` violet, `C` cyan, `G` green, `P` pink, `B` blue, `R` red, `O` orange, `Y` yellow

Notes:
- **`howToPlay`:** The runtime pauses the game behind a crisp How to play card on first visit, remembers dismissal per game so Restart/reloads go straight to play, and adds a `? How to play` pause/rules button in the HUD. Because of this, **do NOT draw in-canvas instruction banners or write custom pause/tutorial overlays**.
- **`controls.layout`:**
  - `"pointer"` hides the mobile D-pad/A/B buttons so the player taps/drags directly on the canvas—ensure `"pointer"` games work 100% with `g.ptr` alone.
  - `"typing"` renders a built-in touch QWERTY keyboard (`a–z`, `Space`, `DEL`, `Enter`) below the canvas and routes physical keyboard typing cleanly into `g.typed` / `g.keys` / `g.keyPressed()` instead of gamepad buttons. Use lowercase letters `a–z` (and optional spaces) for target words so mobile players can type every character, and always render typed progress on canvas.
  - Other layouts render matching touch buttons on mobile and map Arrows/WASD + Space/Z + X/Shift on desktop.

## Runtime API (`g`)

**State & Lifecycle**
- `g.w`, `g.h` — virtual screen size
- `g.t`, `g.tick`, `g.dt` — elapsed seconds, integer frame counter, timestep (`1/60`)
- `g.state` — store all game variables here (auto-cleared before `init(g)`)
- `g.score` — current score (number, starts at `0`, shown in HUD)
- `g.hud(text)` — short status text in top bar (e.g. `"Wave 2 · ♥♥♥"`)
- `g.win(msg)` / `g.lose(msg)` — end round with outcome summary (freezes `update`, opens Play Again overlay)

**Inputs** (`btn`: `"left" | "right" | "up" | "down" | "a" | "b"`)
- `g.held(btn)` — true while held
- `g.pressed(btn)` — true only on the frame pressed (use for jumps, shooting, menu picks, lane switches)
- `g.dir()` — `{ x, y }` (`-1 | 0 | 1`) for held direction
- `g.dirPressed()` — `{ x, y }` (`-1 | 0 | 1`) on press frames (ideal for grid / turn-based movement)
- `g.ptr` — `{ x, y, down, pressed, released }` in virtual coordinates (`0..g.w`, `0..g.h`)
- `g.typed` — string of single printable characters typed on this tick (lowercase `"a"`..`"z"`, `" "`, etc.; active in `"typing"` and `"pointer"` layouts)
- `g.keys` — array of key names pressed this tick (`"a"`..`"z"`, `" "`, `"Backspace"`, `"Enter"`, `"Escape"`, `"ArrowLeft"`, ...)
- `g.keyPressed(key)` — true if `key` was pressed this tick (`"a"`, `"Space"` / `" "`, `"Backspace"`, `"Enter"`, `"Escape"`)

**Drawing (`draw(g)`)**
- `g.cls(color = "dark")`
- `g.rect(x, y, w, h, fill = "amber", stroke = null)`
- `g.circ(x, y, r, fill = "amber", stroke = null)`
- `g.line(x1, y1, x2, y2, color = "white", width = 1)`
- `g.poly(points, fill = "amber", stroke = null)` — `[[x,y], ...]`
- `g.bar(x, y, w, h, frac, fg = "amber", bg = "rule")` — progress/health bar (`0..1`)
- `g.spr(name, x, y, scale = 1, flipX = false, flipY = false)` — draws from top-left `(x, y)`
- `g.txt(text, x, y, { color = "white", size = 8, align = "left", bold = false, maxWidth })` (size buttons/boxes comfortably around text, e.g. `size: 7` needs `h >= 11`)

**Helpers, Collision & Juice**
- `g.hit(a, b)` — collision for `{x,y,w,h}` rects and/or `{x,y,r}` circles in any combination
- `g.inRect(px, py, x, y, w, h)`
- `g.clamp(v, lo, hi)`, `g.lerp(a, b, t)`, `g.dist(x1, y1, x2, y2)`
- `g.rand(min = 0, max = 1)`, `g.randInt(min, max)`, `g.pick(arr)`
- `g.sfx(name)` — `"blip" | "click" | "coin" | "jump" | "shoot" | "hit" | "warn" | "win" | "lose"`
- `g.shake(amount = 3, secs = 0.18)`
- `g.flash(color = "white", secs = 0.1)`
- `g.particles(x, y, color = "amber", count = 8)`

## Design Rules for Fun, Bug-Free Games
1. **Clean frame 0:** `draw(g)` runs right after `init(g)` behind the translucent How to play overlay—never leave variables undefined until `update()`.
2. **Tight 30–60s arc:** Ramp difficulty cleanly, telegraph hazards briefly before impact, and ensure skill—never idle play or random mashing—earns a win.
3. **Never touch DOM/browser globals:** No `window`, `document`, `fetch`, `import`, `eval`, or `Function`. Reset *everything* inside `init(g)` on `g.state`.
