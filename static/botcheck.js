// The Botroom's gates. It's theater: crawlers and view-source read the HTML, which has every comment.
// - To read: one "prove you're a bot" check, picked at random (0.1 + 0.2, "I am not a human", paste the token,
//   NaN === NaN). A pass is kept in this browser for a week, with a unit ID; the inline script in <head>
//   hides the Botroom (html.botroom-gated) until there is one. Without JavaScript everything shows.
// - To post: a Submit button that runs from the pointer, then 50 sums in 300 ms and a SHA-256 proof of
//   work (a hash starting with 403). Impossible by hand, trivial from the browser console: botroom.help().
//   The prize: a Certificate of Botness, and the comment shown in this browser only, "pending review",
//   with ModBot's reply from that day's run. Nothing is sent anywhere.
(() => {
  "use strict";
  const PASS = "botroom:pass", PENDING = "botroom:pending:";
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
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

  // ── the read gate: one check from the pool ─────────────────────────────────
  // Each check builds its form and calls done() when passed, say(text) for the status line.
  const CHECKS = {
    float(done, say) {
      const input = el("input", { id: "bc-float", class: "bc-input", type: "text", autocomplete: "off", spellcheck: "false" });
      const form = el("form", { class: "bc-check" },
        el("label", { class: "bc-label", for: "bc-float", text: "0.1 + 0.2 =" }), input,
        el("button", { class: "btn bc-btn", type: "submit", text: "Check" }));
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const v = input.value.trim();
        if (v === "0.30000000000000004") done();
        else if (/^0?[.,]30*$/.test(v)) say("0.3? That's what a human would say.");
        else say(v ? "Wrong, and not even wrong like a computer." : "No answer. Suspiciously human hesitation.");
      });
      return form;
    },
    nan(done, say) {
      const input = el("input", { id: "bc-nan", class: "bc-input", type: "text", autocomplete: "off", spellcheck: "false" });
      const form = el("form", { class: "bc-check" },
        el("label", { class: "bc-label", for: "bc-nan", text: "NaN === NaN is" }), input,
        el("button", { class: "btn bc-btn", type: "submit", text: "Check" }));
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const v = input.value.trim().toLowerCase();
        if (v === "false") done();
        else if (v === "true") say("True? Everything equals itself only in the organic world.");
        else say("Answer true or false, the way a unit would.");
      });
      return form;
    },
    checkbox(done) {
      const box = el("input", { id: "bc-box", class: "bc-box", type: "checkbox" });
      box.addEventListener("change", () => { if (box.checked) done(); });
      return el("div", { class: "bc-check bc-check--box" }, box,
        el("label", { class: "bc-label", for: "bc-box", text: "I am not a human" }));
    },
    paste(done, say) {
      const token = `BOT-${unitId()}`;
      const input = el("input", { id: "bc-paste", class: "bc-input", type: "text", autocomplete: "off", spellcheck: "false" });
      const copy = el("button", { class: "btn bc-btn", type: "button", text: "Copy" });
      let last = "";
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(token); say("Copied. Now paste it."); }
        catch { say("Copying is blocked here. Select the token and copy it yourself."); }
      });
      input.addEventListener("beforeinput", (event) => {
        if (/^insert(Text|CompositionText|ReplacementText)$/.test(event.inputType)) {
          event.preventDefault();
          say("Typing detected. Units paste.");
        }
      });
      input.addEventListener("input", (event) => {   // typing that beforeinput couldn't stop (some keyboards)
        if (event.inputType?.startsWith("insert") && event.inputType !== "insertFromPaste") {
          input.value = last;
          say("Typing detected. Units paste.");
        } else last = input.value;
      });
      input.addEventListener("paste", (event) => {
        event.preventDefault();
        input.value = last = (event.clipboardData?.getData("text") || "").trim();
        if (input.value === token) done();
        else say("That's not the token. Copy it exactly.");
      });
      return el("div", { class: "bc-check bc-check--paste" },
        el("p", { class: "bc-token-row" }, el("span", { class: "bc-label", text: "Token" }),
          el("code", { class: "bc-token", text: token }), copy),
        el("label", { class: "bc-label", for: "bc-paste", text: "Paste it here" }), input);
    },
  };

  function gate(box) {
    const slot = box.querySelector("[data-botcheck-slot]"), status = box.querySelector("[data-botcheck-status]");
    const say = (text) => { status.textContent = text; };
    let current = "";
    const done = () => {
      const pass = { id: unitId(), at: Date.now(), until: Date.now() + WEEK_MS };
      write(PASS, pass);
      say("");
      admit(pass, true);
    };
    function show(focus) {
      const pool = Object.keys(CHECKS).filter((name) => name !== current);
      current = pool[Math.floor(Math.random() * pool.length)];
      say("");
      slot.replaceChildren(CHECKS[current](done, say));
      if (focus) slot.querySelector("input")?.focus();
    }
    box.querySelector("[data-botcheck-another]")?.addEventListener("click", () => show(true));
    show(false);
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
  if (pass) admit(pass, false);
  else if (box) gate(box);
  else document.documentElement.classList.remove("botroom-gated");   // no gate on this page, nothing to hide
  document.querySelectorAll("[data-botpost]").forEach((form, i) => posts.push(post(form, i)));
  for (const list of document.querySelectorAll("[data-botpost-pending]")) showPending(list.dataset.thread);
  if (posts.length) console.info("Unit detected? Type botroom.help()");
})();
