// The Search page: loads search/index.json (written by newsroom/search.py) and searches it in the browser.
// Words match at word starts, ignoring case and accents ("ai" finds "AI", not "said"); "quoted words"
// match as a phrase. Results are newest first. Built with DOM text nodes only: no HTML from the index.
(() => {
  "use strict";
  const form = document.querySelector("[data-search]");
  if (!form) return;
  const input = form.querySelector("input[name=q]");
  const status = document.getElementById("search-status");
  const list = document.getElementById("search-results");
  const more = document.getElementById("search-more");
  const sectionNames = JSON.parse(form.dataset.sections || "{}");
  const PAGE = 30;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  let items = null, hits = [], shown = 0, terms = [], timer = 0;

  // Lower case, no accents, anything that isn't a letter or digit becomes a space.
  const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();

  const section = () => (form.querySelector("input[name=section]:checked") || {}).value || "";

  function parse(q) {
    const out = [];
    for (const m of q.matchAll(/"([^"]+)"|(\S+)/g)) {
      const t = fold(m[1] || m[2]);
      if (t) out.push(t);
    }
    return out;
  }

  function search() {
    const q = input.value.trim();
    terms = parse(q);
    const sec = section();
    syncUrl(q, sec);
    if (!items) return;
    if (!terms.length) {
      hits = [];
      render(sec ? `Type a word to search ${sectionNames[sec] || sec}.` : "Type a word to search the paper.");
      return;
    }
    hits = [];
    for (const it of items) {
      if (sec && it.s !== sec) continue;
      if (!terms.every((t) => it._all.includes(" " + t))) continue;
      const inHead = terms.filter((t) => it._head.includes(" " + t)).length;
      hits.push({ it, score: inHead });
    }
    hits.sort((a, b) => (a.it.t < b.it.t ? 1 : a.it.t > b.it.t ? -1 : b.score - a.score));
    const where = sec ? ` in ${sectionNames[sec] || sec}` : "";
    render(hits.length ? `${hits.length} result${hits.length === 1 ? "" : "s"} for “${q}”${where}.`
                       : `Nothing found for “${q}”${where}.`);
  }

  function syncUrl(q, sec) {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (sec) params.set("section", sec);
    const next = params.toString() ? `?${params}` : location.pathname;
    try { history.replaceState(null, "", next); } catch (e) { /* file:// previews */ }
  }

  function render(message) {
    status.textContent = message;
    list.replaceChildren();
    shown = 0;
    showMore();
  }

  function showMore() {
    const end = Math.min(hits.length, shown + PAGE);
    const frag = document.createDocumentFragment();
    for (; shown < end; shown++) frag.append(row(hits[shown].it));
    list.append(frag);
    more.hidden = shown >= hits.length;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  // Text with the search words marked, as nodes (never innerHTML).
  function marked(text) {
    const frag = document.createDocumentFragment();
    const words = terms.map((t) => t.split(" ").map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[^\\p{L}\\p{N}]+"));
    if (!words.length) { frag.append(text); return frag; }
    const re = new RegExp(`(^|[^\\p{L}\\p{N}])(${words.join("|")})`, "giu");
    let last = 0;
    for (const m of text.matchAll(re)) {
      const start = m.index + m[1].length;
      if (start > last) frag.append(text.slice(last, start));
      frag.append(el("mark", "", m[2]));
      last = start + m[2].length;
    }
    frag.append(text.slice(last));
    return frag;
  }

  function date(t) {
    const [y, m, d] = t.split("-").map(Number);
    return `${d} ${MONTHS[m - 1]} ${y}`;
  }

  function row(it) {
    const li = el("li", `search-hit sec-${it.s}`);
    const kicker = el("p", "search-kicker");
    kicker.append(el("span", "kicker", sectionNames[it.s] || it.s));
    if (it.n) kicker.append(el("span", "search-kind", it.n));
    const time = el("time", "", date(it.t));
    time.dateTime = it.t;
    kicker.append(time);

    const external = /^https?:\/\//i.test(it.u);
    const h = el("h2", "hl hl-sm");
    const a = el("a", "hl-link");
    a.href = external || it.u.startsWith("/") ? it.u : "#";       // links come from feeds: web links only
    a.append(marked(it.h));
    if (external) {
      a.append(el("span", "visually-hidden", " (opens the source)"));
      const arrow = el("span", "search-ext", " ↗");
      arrow.setAttribute("aria-hidden", "true");
      a.append(arrow);
    }
    h.append(a);
    li.append(kicker, h);
    if (it.d) {
      const d = el("p", "search-dek");
      d.append(marked(it.d));
      li.append(d);
    }
    if (it.o) li.append(el("p", "meta", it.o));
    return li;
  }

  // Start from the URL (?q=…&section=…), so searches can be linked and the Archive's box lands here.
  const params = new URLSearchParams(location.search);
  input.value = params.get("q") || "";
  const preset = form.querySelector(`input[name=section][value="${CSS.escape(params.get("section") || "")}"]`);
  if (preset) preset.checked = true;

  form.addEventListener("submit", (e) => { e.preventDefault(); search(); });
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 120); });
  form.addEventListener("change", (e) => { if (e.target.name === "section") search(); });
  more.addEventListener("click", showMore);

  status.textContent = "Loading the index…";
  fetch(form.dataset.index)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then((data) => {
      items = (data.items || []).map((it) => ({
        ...it,
        _head: " " + fold(it.h),
        _all: " " + fold([it.h, it.d, it.p, it.o].join(" ")),
      }));
      search();
      if (!input.value) input.focus();
    })
    .catch(() => {
      status.textContent = "Search couldn't load. The Archive lists every edition by date.";
    });
})();
