// A browser-local picker: factual filters, three matches, another batch, and a saved shelf.
(() => {
  "use strict";
  const app = document.querySelector("[data-tonight]");
  if (!app) return;
  const $ = (s) => app.querySelector(s);
  const form = $("[data-tonight-form]");
  const all = JSON.parse($("[data-tonight-catalog]").textContent);
  const key = "times:tonight:saved";
  let saved = [], storageOK = true;
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    if (Array.isArray(value)) saved = value.map((r) => typeof r === "string" ? all.find((t) => t.id === r) : r)
      .filter((r) => r && typeof r.id === "string" && typeof r.title === "string" && /^https?:\/\//i.test(r.url)
        && ["play", "watch"].includes(r.mode) && Array.isArray(r.genres) && Array.isArray(r.services));
  } catch { storageOK = false; }
  let matches = [], cursor = 0;
  const control = (name) => form.elements.namedItem(name);
  const mode = () => control("mode").value;
  const isSaved = (id) => saved.some((r) => r.id === id);
  const validNow = (r) => !r.expires || Date.parse(r.expires) > Date.now();

  function options(name, values, placeholder) {
    const select = control(name);
    select.replaceChildren();
    if (placeholder) select.add(new Option(placeholder, ""));
    for (const value of [...new Set(values.filter(Boolean))].sort()) select.add(new Option(value, value));
  }
  function setup() {
    const rows = all.filter((r) => r.mode === mode() && validNow(r));
    options("genre", rows.flatMap((r) => r.genres), "Anything");
    options("service", rows.flatMap((r) => r.services), "Any listed service");
    options("currency", rows.map((r) => r.currency));
    if ([...control("currency").options].some((o) => o.value === "EUR")) control("currency").value = "EUR";
    app.querySelectorAll("[data-play-filter]").forEach((e) => { e.hidden = mode() !== "play"; });
    app.querySelectorAll("[data-watch-filter]").forEach((e) => { e.hidden = mode() !== "watch"; });
    search();
  }
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(saved)); }
    catch { storageOK = false; }
  }
  function node(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function card(r) {
    const e = node("article", "tonight-card");
    const kind = r.kind === "game" ? "PC game" : r.kind === "movie" ? "Film" : "Series";
    e.append(node("p", "kicker", kind));
    const heading = node("h3", "hl hl-lg"), link = node("a", "hl-link", r.title);
    link.href = r.url;
    heading.append(link); e.append(heading);
    const price = r.price === null ? "Price not listed" : new Intl.NumberFormat(undefined,
      { style: "currency", currency: r.currency || "EUR" }).format(r.price);
    e.append(node("p", "tonight-card-meta", r.mode === "play" ? price : r.services.join(" · ")));
    if (r.genres.length) e.append(node("p", "meta", r.genres.join(" · ")));
    if (r.summary) e.append(node("p", "tonight-summary", r.summary));
    if (r.rating) e.append(node("p", "meta", r.rating));
    if (r.checked) e.append(node("p", "meta", `Checked ${r.checked.slice(0, 10)}`));
    const actions = node("div", "tonight-actions");
    const visit = node("a", "btn", r.mode === "play" ? "See store / deal →" : "Where to watch →");
    visit.href = r.url;
    const button = node("button", "btn"); button.type = "button";
    button.textContent = isSaved(r.id) ? "Remove from saved" : "Save for later";
    button.setAttribute("aria-label", `${button.textContent}: ${r.title}`);
    button.addEventListener("click", () => {
      saved = isSaved(r.id) ? saved.filter((t) => t.id !== r.id) : [...saved, r];
      persist(); draw(); drawSaved();
    });
    actions.append(visit, button); e.append(actions);
    return e;
  }
  function drawSaved() {
    const rows = saved.map((r) => all.find((t) => t.id === r.id) || r).filter(validNow);
    $("[data-tonight-saved]").hidden = !rows.length;
    $("[data-tonight-saved-list]").replaceChildren(...rows.map(card));
    $("[data-tonight-save-note]").textContent = storageOK ? "Saved in this browser only. Ended deals are hidden."
      : "Browser storage is unavailable. Saves last while this page is open.";
  }
  function draw() {
    const shown = matches.slice(cursor, cursor + 3);
    $("[data-tonight-results]").replaceChildren(...shown.map(card));
    $("[data-tonight-status]").textContent = !matches.length
      ? "No matches with those filters. Try another genre, service or budget."
      : `${matches.length} ${matches.length === 1 ? "match" : "matches"}. Showing ${cursor + 1}–${cursor + shown.length}.`;
    $("[data-tonight-another]").hidden = matches.length <= 3;
  }
  function search() {
    const get = (n) => control(n).value;
    matches = all.filter((r) => {
      if (r.mode !== mode() || !validNow(r) || (get("genre") && !r.genres.includes(get("genre")))) return false;
      if (mode() === "watch") return (!get("service") || r.services.includes(get("service"))) && (!get("kind") || r.kind === get("kind"));
      if (get("currency") && r.currency !== get("currency")) return false;
      return get("budget") === "" || (r.price !== null && r.price <= Number(get("budget")));
    });
    // Shuffle once per filter change; another batch walks the whole pool before cycling.
    for (let i = matches.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [matches[i], matches[j]] = [matches[j], matches[i]];
    }
    cursor = 0; draw();
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); search(); });
  form.addEventListener("change", (e) => { if (e.target.name === "mode") setup(); else search(); });
  $("[data-tonight-another]").addEventListener("click", () => {
    cursor = cursor + 3 < matches.length ? cursor + 3 : 0; draw();
  });
  form.hidden = false; setup(); drawSaved();
})();
