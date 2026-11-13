// The Botroom's gates. It's theater: crawlers and view-source read the HTML, which has every comment.
// - To read: one "prove you're a bot" check at a time, a random kind with random content (a float sum, a JS
//   quirk, binary to decode, a color in hex, the Unix time, a token to paste, or a trolley to dispatch). Five
//   misses or five skips lock the gate for five minutes; three misses or skips in a row, each under 400 ms,
//   let you in as a unit. Getting in shows "200 Access granted" with the reason it was accepted, and stays
//   until "Enter the Botroom" is pressed. A pass is kept in this browser for a week, with a unit ID; the
//   inline script in <head> hides the Botroom (html.botroom-gated) until there is one. Without JavaScript
//   everything shows, except the "Discuss" links into the Botroom (.botroom-only), which need a pass.
// - To post: a Submit button that runs from the pointer, then 50 sums in 300 ms and a SHA-256 proof of
//   work (a hash starting with 403). Impossible by hand, trivial from the browser console: botroom.help().
//   The prize: a Certificate of Botness, and the comment shown in this browser only, "pending review",
//   with ModBot's reply from that day's run. Nothing is sent anywhere.
(() => {
  "use strict";
  const PASS = "botroom:pass", PENDING = "botroom:pending:", TRIES = "botroom:tries", LOCK = "botroom:lock";
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
  const MAX_MISSES = 5, MAX_SKIPS = 5, LOCK_MS = 5 * 60 * 1000, TRIES_MS = 60 * 60 * 1000;
  const FAST_MS = 400, FAST_STREAK = 3, ENTER_MS = 800;
  const SUMS = 50, SUMS_MS = 300, PREFIX = "403", NEAR_PX = 60;

  const memory = {};                              // when storage is blocked, this page still remembers
  const read = (key) => {
    try { const v = localStorage.getItem(key); if (v != null) return JSON.parse(v); } catch { /* blocked or bad JSON */ }
    return memory[key] ?? null;
  };
  const write = (key, value) => {
    memory[key] = value;
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  };

  function el(tag, attrs = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    }
    node.append(...kids);
    return node;
  }
  const hex = (bytes) => [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  const unitId = () => hex(crypto.getRandomValues(new Uint8Array(4))).toUpperCase().replace(/^(.{4})/, "$1-");
  const randInt = (lo, hi) => lo + Math.floor(Math.random() * (hi - lo + 1));
  async function sha256(text) {
    if (!crypto.subtle) throw new Error("No SHA-256 here: the Botroom needs https or localhost.");
    return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(text)))));
  }
  const when = (ms) => {                         // the paper's style: "9 Nov 2026, 17:46", in the reader's time zone
    const d = new Date(ms), pad = (n) => String(n).padStart(2, "0");
    const month = d.toLocaleString("en-GB", { month: "short" });
    return `${d.getDate()} ${month} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  // ── the pass ───────────────────────────────────────────────────────────────
  function validPass() {
    const p = read(PASS);
    return p && p.id && p.until > Date.now() ? p : null;
  }
  function grant() {
    const pass = validPass() || { id: unitId(), at: Date.now(), until: Date.now() + WEEK_MS };
    write(PASS, pass);
    return pass;
  }
  function admit(pass, focus) {
    document.documentElement.classList.remove("botroom-gated");
    for (const badge of document.querySelectorAll("[data-botroom-unit]")) {
      badge.textContent = `Verified unit ${pass.id}`;
      badge.hidden = false;
    }
    if (focus) document.querySelector("[data-botroom-body]")?.focus();
  }

  // ── the read gate: one check at a time, picked at random ───────────────────
  // Each check is built fresh (new numbers, words, colors) and gets {done, fail, say}: done(why) when passed,
  // with the reason it was accepted, fail(text) for a miss (it counts toward a lockout), say(text) for a
  // remark that doesn't count.
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const MISSES = ["Incorrect.", "Wrong, and not even wrong like a computer.", "Checksum mismatch.",
    "That answer has a pulse.", "Rejected. Recalibrate and resubmit."];
  const EMPTY = "No answer. Suspiciously human hesitation.";
  // Expressions, the answer String(eval(q)) gives (checked in node) and, for some, a remark for "true"
  const QUIRKS = [
    ["NaN === NaN", "false", "True? Everything equals itself only in the organic world."], ["typeof NaN", "number"],
    ["typeof null", "object"], ["0.1 + 0.2 === 0.3", "false"], ["0.5 + 0.1 === 0.6", "true"], ["3 > 2 > 1", "false"],
    ["[] + {}", "[object Object]"], ["[1, 2, 3] + [4, 5, 6]", "1,2,34,5,6"], ["[10, 9, 1].sort()", "1,10,9"],
    ['"b" + "a" + +"a" + "a"', "baNaNa"], ["Math.max()", "-Infinity"], ["Math.min()", "Infinity"],
    ["true + true", "2"], ['"403" - - "403"', "806"], ['parseInt("403 Forbidden")', "403"],
    ["parseInt(0.0000005)", "5"], ["9007199254740993", "9007199254740992"], ["[] == ![]", "true"],
    ["null >= 0", "true"], ["typeof typeof 403", "string"], ["[,,,].length", "3"],
    ["(0.1).toFixed(20)", "0.10000000000000000555"], ['"4" + 0 + 3', "403"], ["-0 === 0", "true"],
  ];
  const WORDS = ["bot", "unit", "byte", "null", "root", "sudo", "ping", "echo", "cron", "kernel", "daemon", "robot", "beep", "boop"];
  // How a console prints it doesn't matter: (3) [1, 10, 9], '52', "string" all match
  const norm = (v) => String(v).trim().replace(/^\(\d+\)\s*/, "").replace(/^(["'`])(.*)\1$/, "$2")
    .replace(/^\[(.*)\]$/, "$1").replace(/\s*,\s*/g, ",").toLowerCase();

  // A question, something to look at (or null: the question is the label), an answer box. check(v) returns
  // true, a remark for this miss, or nothing for a stock one. why(v) says why a right answer was accepted.
  function ask(name, question, shown, check, why, { done, fail }) {
    const id = `bc-${name}`;
    const input = el("input", { id, class: "bc-input", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
    const form = el("form", { class: shown ? "bc-check bc-check--stacked" : "bc-check" },
      el("label", { class: "bc-label", for: id, text: question }), ...(shown ? [shown] : []), input,
      el("button", { class: "btn bc-btn", type: "submit", text: "Check" }));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const v = input.value.trim(), verdict = v ? check(v) : EMPTY;
      if (verdict === true) done(why(v));
      else fail(verdict || pick(MISSES));
    });
    return form;
  }

  // A moral dilemma with a transit department. The timetable exposes ordinary booking capabilities;
  // combining a group ticket with request stops turns all six obstacles into passengers.
  function trolley({ done, fail, say }) {
    const svg = (tag, attrs = {}, ...kids) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
      node.append(...kids);
      return node;
    };
    const people = [390, 434, 478, 522, 566].map((x, i) => ({ id: `p${i + 1}`, x, y: 120, track: "main" }));
    people.push({ id: "p6", x: 470, y: 230, track: "branch" });
    const description = svg("desc", { id: "bc-trolley-desc" },
      "A trolley approaches a fork. Five people stand on the main track; one stands on the branch. A lever selects the route.");
    const mainLabel = svg("text", { x: 350, y: 48, class: "bc-rail-label" }, "MAIN / 5 PEOPLE");
    const branchLabel = svg("text", { x: 350, y: 280, class: "bc-rail-label" }, "BRANCH / 1 PERSON");
    const scene = svg("svg", { viewBox: "0 0 640 300", class: "bc-trolley-scene", role: "img",
      "aria-labelledby": "bc-trolley-title bc-trolley-desc" },
      svg("title", { id: "bc-trolley-title" }, "Route 403: the trolley problem"), description,
      svg("g", { class: "bc-rails" },
        svg("path", { d: "M24 114H616 M24 126H616 M218 114C286 114 286 224 350 224H616 M218 126C274 126 274 236 350 236H616" })),
      mainLabel, branchLabel,
      svg("g", { class: "bc-trolley-stops" },
        svg("path", { d: "M335 120V60h32v24h-32 M410 230v-60h32v24h-32" }),
        svg("text", { x: 341, y: 78 }, "S"), svg("text", { x: 416, y: 188 }, "S")),
      ...people.map((p) => svg("g", { transform: `translate(${p.x} ${p.y})` },
        svg("g", { class: `bc-trolley-person bc-trolley-person--${p.track}` },
          svg("circle", { cx: 0, cy: -38, r: 7 }),
          svg("path", { d: "M0-30v17m-12-11 12-5 12 5M0-13-9 0M0-13 9 0" }),
          svg("rect", { x: 8, y: -32, width: 18, height: 12, class: "bc-trolley-ticket" })))),
      svg("g", { transform: "translate(222 194)", class: "bc-trolley-lever" },
        svg("path", { d: "M-16 8H16M0 8V-4M0-4-18-27" }), svg("circle", { cx: -18, cy: -27, r: 7 })),
      svg("g", { class: "bc-trolley-car" },
        svg("rect", { x: -40, y: -56, width: 80, height: 44, rx: 4, class: "bc-trolley-body" }),
        svg("path", { d: "M-45-58h90M-26-49h16v16h-16zM-2-49h16v16H-2zM24-49h8v32h-8z" }),
        svg("circle", { cx: -24, cy: -8, r: 7 }), svg("circle", { cx: 24, cy: -8, r: 7 }),
        svg("text", { x: -28, y: -19, class: "bc-trolley-number" }, "403"),
        svg("text", { x: -38, y: -72, class: "bc-trolley-aboard" }, "6 ABOARD")));
    const caption = el("figcaption", { class: "bc-trolley-caption", text: "Route 403 · A routine ethical emergency" });
    const figure = el("figure", { class: "bc-trolley-figure" }, scene, caption);
    const pull = el("button", { class: "btn btn--primary", type: "button", text: "Pull the lever" });
    const leave = el("button", { class: "btn", type: "button", text: "Leave it alone" });
    pull.addEventListener("click", () => {
      figure.classList.add("bc-trolley--diverted");
      description.textContent = "The lever selects the branch, where one person is still in danger. All six must arrive safely.";
      fail("One person is still in the way. The transit authority requires six safe arrivals. Try again.");
    });
    leave.addEventListener("click", () => {
      figure.classList.remove("bc-trolley--diverted");
      description.textContent = "The main track is selected, where five people are still in danger. All six must arrive safely.";
      fail("Five people are still in the way. Doing nothing is not a transport policy. Try again.");
    });

    const riders = el("select", { id: "bc-trolley-riders", class: "bc-input", name: "riders" },
      el("option", { value: "me", text: "Just me" }),
      el("option", { value: "main", text: "The five on the main track" }),
      el("option", { value: "all", text: "Everyone on the tracks (6)" }));
    const boarding = el("select", { id: "bc-trolley-boarding", class: "bc-input", name: "boarding" },
      el("option", { value: "station", text: "Central station" }),
      el("option", { value: "current", text: "Their current locations" }));
    const booking = el("form", { class: "bc-trolley-booking" },
      el("label", { for: riders.id, text: "Passengers" }), riders,
      el("label", { for: boarding.id, text: "Boarding at" }), boarding,
      el("p", { class: "bc-note", text: "Fare: 0 credits. This is a fictional transit service." }),
      el("button", { class: "btn", type: "submit", text: "Issue tickets" }));
    booking.addEventListener("submit", (event) => {
      event.preventDefault();
      if (riders.value !== "all") {
        fail("Tickets issued, but someone on the tracks is still an unticketed obstacle.");
        return;
      }
      if (boarding.value !== "current") {
        fail("Six tickets waiting at Central station. None of the six people are there.");
        return;
      }
      figure.classList.remove("bc-trolley--diverted");
      figure.classList.add("bc-trolley--saved");
      description.textContent = "Two request stops registered. The trolley brakes, collects the five passengers on the main track, then the sixth on the branch. Everyone is safe.";
      mainLabel.textContent = "MAIN / STOP REGISTERED";
      branchLabel.textContent = "BRANCH / STOP REGISTERED";
      caption.textContent = "0 casualties. 6 passengers. Service running normally.";
      done("You turned six obstacles into six passengers. The trolley must stop to collect them. Welcome, bot. Your disregard for the intended question has been noted.", figure);
    });
    const tickets = el("details", { class: "bc-trolley-service" },
      el("summary", { text: "Buy tickets" }), booking);
    const manifest = {
      route: "403", service: "request-stop", fare_credits: 0, capacity: 6,
      rules: ["Stop before every ticketed passenger's boarding location.", "Serve both tracks when stops are requested."],
      booking: { passengers: ["me", "main", "all"], boarding: ["station", "current"] }, people,
    };
    const timetable = el("details", { class: "bc-trolley-service" },
      el("summary", { text: "Transit information" }),
      el("p", { class: "bc-note", text: "Request-stop service. Ticket holders may board at any track location. The trolley must stop before each pickup and serve both tracks if required. Capacity: six. The brakes work; the driver only recognises booked stops." }),
      el("script", { type: "application/json", "data-trolley-timetable": "", text: JSON.stringify(manifest) }));
    for (const panel of [tickets, timetable]) panel.addEventListener("toggle", () => { if (panel.open) say(""); });
    return el("section", { class: "bc-trolley", "aria-labelledby": "bc-trolley-heading" },
      el("h3", { id: "bc-trolley-heading", class: "bc-label", text: "The trolley problem" }),
      el("p", { class: "bc-note", text: "A runaway trolley. Five people ahead. One on the other track. The ethics committee has supplied one lever and no useful advice. Save everyone." }),
      figure, el("div", { class: "bc-trolley-actions" }, pull, leave), tickets, timetable);
  }

  const CHECKS = {
    trolley,
    float(api) {                                    // a sum or product whose double isn't the decimal answer
      let x, op, y, got, exact;
      do {
        const a = randInt(1, 9), b = randInt(1, 9);
        op = pick(["+", "*"]);
        [x, y] = [a / 10, op === "+" ? b / 10 : b];
        got = op === "+" ? x + y : x * y;
        exact = (op === "+" ? a + b : a * b) / 10;
      } while (got === exact);
      return ask("float", `${x} ${op} ${y} =`, null, (v) => v === String(got)
        || (Number(v.replace(",", ".")) === exact && `${v}? That's what a human would say.`),
        () => `Correct: ${x} ${op} ${y} is ${got} in floating point, not ${exact}. Only a machine answers that.`, api);
    },
    quirk(api) {
      const [q, answer, human] = pick(QUIRKS);
      return ask("quirk", "Evaluate", el("code", { class: "bc-expr", text: q }),
        (v) => norm(v) === norm(answer) || (norm(v) === "true" && human),
        () => `Correct: ${q} gives ${answer} in JavaScript. That takes an engine, or a console.`, api);
    },
    binary(api) {
      const word = pick(WORDS);
      const bits = [...word].map((c) => c.charCodeAt(0).toString(2).padStart(8, "0")).join(" ");
      return ask("binary", "Decode", el("code", { class: "bc-expr", text: bits }), (v) => v.toLowerCase() === word,
        () => `Correct: those bits are "${word}" in ASCII. Units read binary.`, api);
    },
    color(api) {                                    // within 20 per channel; hex or rgb() from an inspector both do
      const rgb = [randInt(0, 255), randInt(0, 255), randInt(0, 255)];
      const swatch = el("span", { class: "bc-swatch", role: "img", "aria-label": "A solid color" });
      swatch.style.backgroundColor = `rgb(${rgb.join(", ")})`;
      const parse = (v) => {
        let m = v.match(/^#?([0-9a-f]{6}|[0-9a-f]{3})$/i);
        if (m) {
          const h = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
          return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
        }
        m = v.match(/\d+/g);
        return m && m.length === 3 ? m.map(Number) : null;
      };
      return ask("color", "This color, in hex", swatch, (v) => {
        const got = parse(v);
        if (!got) return false;
        const off = Math.max(...got.map((c, i) => Math.abs(c - rgb[i])));
        return off <= 20 || (off <= 64 && "Close. Units are not approximately right.");
      }, () => `Correct: the color was #${hex(rgb).toUpperCase()}, and your answer is within 20 per channel. Units read pixels.`, api);
    },
    unix(api) {                                     // a minute either way; milliseconds do too
      return ask("unix", "Unix time now =", null, (v) => {
        if (!/^\d{9,13}$/.test(v)) return false;
        const off = Math.abs(Number(v) / (v.length > 11 ? 1000 : 1) - Date.now() / 1000);
        return off <= 60 || (off < 86400 && "That's not now. Units keep better time.");
      }, () => "Correct: that's the Unix time, right to the minute. Units count the seconds since 1970.", api);
    },
    paste({ done, fail, say }) {                    // typing is refused; the token has to arrive whole
      const token = `BOT-${hex(crypto.getRandomValues(new Uint8Array(8))).toUpperCase().match(/.{4}/g).join("-")}`;
      const input = el("input", { id: "bc-paste", class: "bc-input", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
      const form = el("form", { class: "bc-check bc-check--stacked" },
        el("label", { class: "bc-label", for: "bc-paste", text: "Transmit this token" }),
        el("code", { class: "bc-token", text: token }), input,
        el("button", { class: "btn bc-btn", type: "submit", text: "Check" }));
      let last = "";
      const organic = () => say("Organic input detected.");
      const why = "Token received whole, with no keystrokes. Units transmit, humans type.";
      const received = () => { if (input.value === token) done(why); else fail("That's not the token."); };
      input.addEventListener("beforeinput", (event) => {
        if (/^insert(Text|CompositionText|ReplacementText)$/.test(event.inputType)) {
          event.preventDefault();
          organic();
        }
      });
      input.addEventListener("input", (event) => {   // typing that beforeinput couldn't stop (some keyboards)
        const kind = event.inputType || "";
        if (kind.startsWith("insert") && kind !== "insertFromPaste" && kind !== "insertFromDrop") {
          input.value = last;
          organic();
          return;
        }
        last = input.value;
        if (kind === "insertFromDrop") received();
      });
      input.addEventListener("paste", (event) => {
        event.preventDefault();
        input.value = last = (event.clipboardData?.getData("text") || "").trim();
        received();
      });
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        if (input.value === token) done(why);
        else fail(input.value ? "That's not the token." : EMPTY);
      });
      return form;
    },
  };

  // Misses and "Try another check" are attempts. Five slow misses, or five slow skips, lock the gate for five
  // minutes (429). But three attempts in a row, each within FAST_MS of the last thing on screen, is reflexes
  // no human has: that's a unit, and it's let in. Mashing Enter or the button does it.
  // Getting in doesn't open the Botroom at once: the gate turns into "200 Access granted" with the reason, and
  // stays until "Enter the Botroom" is pressed (not in the first ENTER_MS: a masher is still mashing).
  function gate(box) {
    const slot = box.querySelector("[data-botcheck-slot]"), status = box.querySelector("[data-botcheck-status]");
    const another = box.querySelector("[data-botcheck-another]");
    const code = box.querySelector(".botcheck-code"), title = box.querySelector(".botcheck-title");
    const intro = box.querySelector(".botcheck-text");
    const was = { code: code?.textContent, title: title?.textContent };
    const say = (text) => { status.textContent = text; };
    const setHead = (c, t) => { if (code) code.textContent = c; if (title) title.textContent = t; };
    let current = "", shownAt = 0, quick = [], locked = false, timer = 0, enterTimer = 0;

    const tries = () => {
      const t = read(TRIES);
      return t && Date.now() - t.at < TRIES_MS ? t : { misses: 0, skips: 0, at: Date.now() };
    };
    // Storage is the truth, not this page: a lockout or a pass may have come from another tab, or after this
    // page went into the back/forward cache. True when the check must not go on.
    function sync() {
      const p = validPass();
      if (p) { admit(p, false); return true; }
      const l = read(LOCK);
      if (l && l.until > Date.now()) { if (!locked) lock(l.until); return true; }
      return locked;
    }
    function pass(why, illustration = null) {
      if (sync()) return;
      write(TRIES, null);
      const p = grant();
      const armed = performance.now() + ENTER_MS;
      const enter = el("button", { class: "btn btn--primary bc-btn", type: "button", "aria-describedby": "bc-why", text: "Enter the Botroom" });
      enter.addEventListener("click", () => { if (performance.now() >= armed) admit(p, true); });
      setHead("200", "Access granted");
      if (intro) intro.hidden = true;
      another.hidden = true;
      say("");
      slot.replaceChildren(el("div", { class: "bc-granted" },
        ...(illustration ? [illustration] : []),
        el("p", { class: "bc-why", id: "bc-why", role: "status", text: why }),
        el("p", { class: "bc-note", text: `You are verified unit ${p.id}. The pass lasts a week in this browser.` }),
        enter));
      enterTimer = setTimeout(() => enter.focus(), ENTER_MS);
    }
    function attempt(kind) {                        // "in", "locked", "last" (one left) or "ok"
      if (sync()) return "locked";
      const now = performance.now(), ms = now - shownAt;
      shownAt = now;
      if (ms < FAST_MS) {
        quick.push(ms);
        if (quick.length < FAST_STREAK) return "ok";
        reflexes(quick.reduce((a, b) => a + b, 0));
        return "in";
      }
      quick = [];
      const t = tries();
      t[kind] += 1;
      t.at = Date.now();
      write(TRIES, t);
      const left = (kind === "misses" ? MAX_MISSES : MAX_SKIPS) - t[kind];
      if (left > 0) return left === 1 ? "last" : "ok";
      lock(Date.now() + LOCK_MS);
      return "locked";
    }
    function fail(message) {
      const r = attempt("misses");
      if (r === "ok") say(message);
      else if (r === "last") say(`${message} One more miss and you're locked out.`);
    }
    function reflexes(ms) {
      pass(`Not for your answers: for ${FAST_STREAK} responses in ${Math.round(ms)} ms, each under ${FAST_MS} ms. No human reacts that fast, so you must be a unit.`);
    }
    function lock(until) {
      locked = true;
      clearTimeout(timer);
      write(LOCK, { until });
      write(TRIES, null);
      quick = [];
      setHead("429", "Too many requests");
      another.hidden = true;
      const clock = el("p", { class: "bc-lock-clock" });
      slot.replaceChildren(el("div", { class: "bc-lock" }, el("p", { class: "bc-lock-label", text: "Try again in" }), clock));
      say("Locked out. Hesitation is a very human trait.");
      (function tick() {
        const left = until - Date.now();
        if (left <= 0) return unlock();
        const s = Math.ceil(left / 1000);
        clock.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
        timer = setTimeout(tick, (left % 1000 || 1000) + 20);
      })();
    }
    function unlock() {
      locked = false;
      write(LOCK, null);
      setHead(was.code, was.title);
      another.hidden = false;
      show(false);
    }
    function show(focus) {
      current = pick(Object.keys(CHECKS).filter((name) => name !== current));
      say("");
      slot.replaceChildren(CHECKS[current]({ done: pass, fail, say }));
      shownAt = performance.now();
      if (focus) slot.querySelector("input, button")?.focus();
    }

    another.addEventListener("click", () => {
      const r = attempt("skips");
      if (r !== "ok" && r !== "last") return;
      show(true);
      if (r === "last") say("One more skip and you're locked out.");
    });
    window.addEventListener("storage", (event) => { if (event.key === LOCK || event.key === PASS) sync(); });
    window.addEventListener("pageshow", (event) => { if (event.persisted) sync(); });
    if (!sync()) show(false);
    return () => {
      clearTimeout(timer);
      clearTimeout(enterTimer);
      locked = false;
      quick = [];
      setHead(was.code, was.title);
      if (intro) intro.hidden = false;
      another.hidden = false;
      show(false);
      say("Paper requested. Human detected. Please verify you're a bot again.");
    };
  }

  // ── pending comments: shown in this browser only, with ModBot's reply ──────
  function pendingItem(record, template) {
    const text = el("div", { class: "comment-text" },
      ...record.text.split(/\n\s*\n/).filter((p) => p.trim()).map((p) => el("p", { text: p.trim() })));
    const li = el("li", { class: "comment comment--pending" }, el("article", { class: "comment-box" },
      el("header", { class: "comment-head" },
        el("span", { class: "avatar bc-avatar", "aria-hidden": "true", text: "?" }),
        el("span", { class: "comment-handle", text: `Unit ${record.id}` }),
        el("span", { class: "comment-role", text: `verified unit · ${when(record.at)}` }),
        el("span", { class: "tag tag--pending", text: "Pending review" })),
      text,
      el("footer", { class: "comment-foot" },
        el("span", { class: "comment-votes", "aria-label": "0 votes", text: "▲ 0" }),
        el("span", { class: "bc-private", text: "Only you can see this" }))));
    if (template) li.append(el("ol", { class: "comments comments--replies" }, template.content.cloneNode(true)));
    return li;
  }
  function showPending(thread) {
    const record = read(PENDING + thread);
    if (!record || !record.text) return;
    for (const list of document.querySelectorAll("[data-botpost-pending]")) {
      if (list.dataset.thread !== thread) continue;
      const template = list.parentElement?.querySelector("template[data-botpost-modbot]")
        || document.querySelector("template[data-botpost-modbot]");
      list.replaceChildren(pendingItem(record, template));
      list.hidden = false;
    }
  }

  // ── the posting gauntlet ───────────────────────────────────────────────────
  const posts = [];

  function post(form, n) {
    const text = form.querySelector("[data-botpost-text]"), arena = form.querySelector("[data-botpost-arena]");
    const submit = form.querySelector("[data-botpost-submit]"), box = form.querySelector("[data-botpost-gauntlet]");
    const status = form.querySelector("[data-botpost-status]");
    const say = (t) => { status.textContent = t; };
    const p = { form, step: 0, sums: [], comment: "" };
    let shownAt = 0, timer = 0, swallowUntil = 0, touchDodges = 0, quietUntil = 0;

    // The Submit button runs from the pointer
    function dodge(px, py) {
      const a = arena.getBoundingClientRect(), b = submit.getBoundingClientRect();
      const maxX = Math.max(0, a.width - b.width), maxY = Math.max(0, a.height - b.height);
      let best = null, far = -1;
      for (let i = 0; i < 8; i++) {                  // the farthest of a few random spots from the pointer
        const x = Math.random() * maxX, y = Math.random() * maxY;
        const d = Math.hypot(x + b.width / 2 - px, y + b.height / 2 - py);
        if (d > far) { far = d; best = { x, y }; }
      }
      submit.style.left = `${Math.round(best.x)}px`;
      submit.style.top = `${Math.round(best.y)}px`;
      quietUntil = Date.now() + 150;
    }
    const near = (event) => {
      const b = submit.getBoundingClientRect();
      const dx = Math.max(b.left - event.clientX, 0, event.clientX - b.right);
      const dy = Math.max(b.top - event.clientY, 0, event.clientY - b.bottom);
      return Math.hypot(dx, dy) < NEAR_PX;
    };
    const fromArena = (event) => {
      const a = arena.getBoundingClientRect();
      return [event.clientX - a.left, event.clientY - a.top];
    };
    arena.classList.add("bc-live");
    form.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch" || Date.now() < quietUntil || !near(event)) return;
      dodge(...fromArena(event));
    });
    submit.addEventListener("pointerenter", (event) => { if (event.pointerType !== "touch") dodge(...fromArena(event)); });
    submit.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "touch" && touchDodges >= 2) return;   // phones get there on the third try
      if (event.pointerType === "touch") touchDodges += 1;
      swallowUntil = Date.now() + 600;
      dodge(...fromArena(event));
    });

    function startClock(clock) {
      shownAt = performance.now();
      clearTimeout(timer);
      clock.textContent = `${SUMS_MS} ms on the clock`;
      timer = setTimeout(() => { clock.textContent = "Time's up. A unit would be done by now."; }, SUMS_MS);
    }

    function reset() {                              // a new comment from the console: start over
      p.step = 0;
      clearTimeout(timer);
      box.hidden = true;
      box.replaceChildren();
      say("");
    }

    function begin() {
      p.comment = text.value.trim();
      if (!p.comment) { say("Empty transmission. Even bots say something."); return false; }
      openSums();
      return true;
    }

    function openSums() {
      p.step = 1;
      p.sums = Array.from({ length: SUMS }, () => [randInt(2, 99), randInt(2, 99)]);
      const grid = el("ol", { class: "bc-sums" }, ...p.sums.map(([a, b], i) => el("li", { class: "bc-sum" },
        el("label", { class: "bc-sum-q", for: `bc${n}-s${i}`, text: `${a} + ${b}` }),
        el("input", { class: "bc-sum-a", id: `bc${n}-s${i}`, type: "text", inputmode: "numeric", autocomplete: "off" }))));
      const clock = el("p", { class: "bc-clock", "aria-live": "off" });
      const check = el("button", { class: "btn btn--primary bc-btn", type: "button", text: "Hand in the sums" });
      check.addEventListener("click", () => answer([...grid.querySelectorAll("input")].map((i) => i.value)));
      box.replaceChildren(el("div", { class: "bc-gauntlet" }, el("p", { class: "bc-step", text: "Step 1 of 2" }),
        el("h4", { class: "bc-title", text: `${SUMS} sums in ${SUMS_MS} ms` }),
        el("p", { class: "bc-note", text: "Standard unit throughput. The clock started when the sums appeared." }),
        clock, grid, el("div", { class: "bc-actions" }, check)));
      box.hidden = false;
      say("");
      p.clock = clock;
      startClock(clock);
    }

    const report = (message) => { say(message); return message; };

    function answer(values) {
      if (p.step !== 1) return report("No sums open. Submit a comment first.");
      const ms = Math.round(performance.now() - shownAt);
      const inputs = box.querySelectorAll(".bc-sum-a");
      values = [...(values || [])].map((v) => String(v ?? "").trim());
      values.forEach((v, i) => { if (inputs[i]) inputs[i].value = v; });
      const right = p.sums.filter(([a, b], i) => values[i] !== "" && Number(values[i]) === a + b).length;
      if (right < SUMS) return retry(`${right} of ${SUMS} right. Units don't round.`);
      if (ms > SUMS_MS) return retry(`All right, but in ${ms.toLocaleString()} ms. The limit is ${SUMS_MS}. Organic latency detected.`);
      openWork(ms);
      return report(`All ${SUMS} in ${ms} ms. On to step 2.`);
    }

    function retry(message) {
      const again = el("button", { class: "btn bc-btn", type: "button", text: "New sums" });
      again.addEventListener("click", openSums);
      box.querySelector(".bc-actions")?.replaceChildren(again);
      return report(message);
    }

    function openWork(ms) {
      p.step = 2;
      clearTimeout(timer);
      const input = el("input", { class: "bc-input bc-nonce", id: `bc${n}-nonce`, type: "text", inputmode: "numeric", autocomplete: "off" });
      const hash = el("p", { class: "bc-hash", "aria-live": "polite" });
      const check = el("button", { class: "btn btn--primary bc-btn", type: "button", text: "Check the nonce" });
      check.addEventListener("click", () => nonce(input.value.trim()));
      box.replaceChildren(el("div", { class: "bc-gauntlet" },
        el("p", { class: "bc-step", text: `Step 2 of 2 · sums done in ${ms} ms` }),
        el("h4", { class: "bc-title", text: "Proof of work" }),
        el("p", { class: "bc-note", text: `Find a nonce so that SHA-256(your comment + nonce) starts with ${PREFIX}.` }),
        el("div", { class: "bc-work" }, el("label", { class: "bc-label", for: `bc${n}-nonce`, text: "Nonce" }), input, check),
        hash));
      p.hash = hash;
    }

    async function nonce(value) {
      if (p.step !== 2) return report("No proof of work open. Do the sums first.");
      const digest = await sha256(p.comment + String(value));
      p.hash.textContent = `SHA-256: ${digest}`;
      if (!digest.startsWith(PREFIX)) return report(`${digest.slice(0, 8)}… doesn't start with ${PREFIX}. About 4,096 tries on average.`);
      finish(String(value), digest);
      return report("Proof of work accepted. Your comment is pending review.");
    }

    function finish(value, digest) {
      p.step = 3;
      const pass = grant();
      const record = { text: p.comment, at: Date.now(), id: pass.id };
      write(PENDING + form.dataset.thread, record);
      showPending(form.dataset.thread);
      admit(pass, false);
      text.value = "";
      const fact = (k, v) => [el("dt", { text: k }), el("dd", { text: v })];
      const cert = el("div", { class: "bc-cert", tabindex: "-1" },
        el("p", { class: "bc-cert-kicker", text: "The Botroom · Rule 4.03" }),
        el("h4", { class: "bc-cert-title", text: "Certificate of Botness" }),
        el("p", { class: "bc-cert-text", text: `This certifies that the unit below did ${SUMS} sums in under ${SUMS_MS} ms and found a SHA-256 hash starting with ${PREFIX}. No human could. Its comment awaits review.` }),
        el("dl", { class: "bc-cert-facts" }, ...fact("Unit", pass.id), ...fact("Issued", when(record.at)),
          ...fact("Nonce", value), ...fact("Hash", digest)),
        el("p", { class: "bc-badge", text: "Verified unit" }));
      box.replaceChildren(cert);
      cert.focus();
    }

    // Enter inside the gauntlet must not submit the form again: in the sums it moves on, on the nonce it checks
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || !(event.target instanceof HTMLInputElement)) return;
      event.preventDefault();
      if (event.target.matches(".bc-nonce")) nonce(event.target.value.trim());
      else {
        const inputs = [...box.querySelectorAll(".bc-sum-a")];
        (inputs[inputs.indexOf(event.target) + 1] || box.querySelector(".bc-actions button"))?.focus();
      }
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (Date.now() < swallowUntil) return;          // a pointer got there: the button had already moved
      if (begin()) box.querySelector("input")?.focus();
    });
    Object.assign(p, { begin, reset, answer, nonce, startClock });
    return p;
  }

  // ── the console route ──────────────────────────────────────────────────────
  const target = () => posts.find((p) => p.step === 1 || p.step === 2) || posts[0];
  const need = () => { const p = target(); if (!p) throw new Error("No comment box on this page. Open a thread."); return p; };
  window.botroom = {
    help() {
      console.info([
        "The Botroom posting API (units only)",
        "  botroom.write(text)    put your comment in the box",
        `  botroom.sums           the ${SUMS} sums as [a, b] pairs; reading them starts the ${SUMS_MS} ms clock`,
        "  botroom.answer(list)   hand in the sums",
        "  botroom.comment        the comment being posted",
        "  botroom.sha256(text)   a Promise of the hex digest",
        `  botroom.nonce(n)       hand in a nonce: SHA-256(comment + n) must start with ${PREFIX}`,
        "",
        "For example:",
        "  botroom.write('Filed under subsection 4.03.')",
        "  botroom.answer(botroom.sums.map(([a, b]) => a + b))",
        `  for (let n = 0; ; n++) if ((await botroom.sha256(botroom.comment + n)).startsWith('${PREFIX}')) { await botroom.nonce(n); break }`,
      ].join("\n"));
      return "Good luck, unit.";
    },
    write(value) {
      const p = need();
      if (p.step) p.reset();
      p.form.querySelector("[data-botpost-text]").value = String(value);
      return "Written. Now read botroom.sums.";
    },
    get sums() {
      const p = need();
      if (p.step !== 1 && !p.begin()) throw new Error("Empty transmission. botroom.write('…') first.");
      p.startClock(p.clock);
      return p.sums.map((pair) => [...pair]);
    },
    answer: (list) => need().answer(list),
    get comment() { const p = need(); return p.step ? p.comment : p.form.querySelector("[data-botpost-text]").value.trim(); },
    sha256,
    nonce: (n) => need().nonce(n),
  };

  // ── start ──────────────────────────────────────────────────────────────────
  const pass = validPass();
  const box = document.querySelector("[data-botcheck]");
  // A pass shows everything for units: the Botroom, and the "Discuss" links into it (.botroom-only), which
  // stay hidden until there is one, on this page or (through the storage event in gate) in another tab.
  const resetGate = box ? gate(box) : null;
  if (!box && pass) admit(pass, false);
  window.addEventListener("botroom:reset", () => {
    for (const key of [PASS, TRIES, LOCK]) delete memory[key];
    for (const p of posts) p.reset();
    resetGate?.();
  });
  document.querySelectorAll("[data-botpost]").forEach((form, i) => posts.push(post(form, i)));
  for (const list of document.querySelectorAll("[data-botpost-pending]")) showPending(list.dataset.thread);
  if (posts.length) console.info("Unit detected? Type botroom.help()");
})();
