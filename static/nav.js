// The nav. The destinations scroll sideways when they don't fit: bring the current page's link
// into view, and fade whichever edge has more. The Menu is a <details> disclosure, so it opens
// and closes without JS. This adds the expected ways out: Escape, a click or tab outside it,
// and coming back to the page from the back/forward cache.
(() => {
  "use strict";
  const bar = document.querySelector(".nav-sections");
  const current = bar && bar.querySelector(".is-active");
  function reveal() {
    const b = bar.getBoundingClientRect(), r = current.getBoundingClientRect();
    if (r.right > b.right - 40 || r.left < b.left + 40) {
      bar.scrollLeft += r.left - b.left - (b.width - r.width) / 2;   // 40px: the fade
    }
  }
  function edges() {
    bar.classList.toggle("can-left", bar.scrollLeft > 1);
    bar.classList.toggle("can-right", bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 1);
  }
  function overflow() {
    bar.classList.remove("is-overflowing");
    const overflows = bar.scrollWidth > bar.clientWidth + 1;
    bar.classList.toggle("is-overflowing", overflows);
    if (overflows) edges();
    else bar.classList.remove("can-left", "can-right");
  }
  if (bar) {
    overflow();
    bar.addEventListener("scroll", edges, { passive: true });
    window.addEventListener("resize", overflow);
  }
  if (current) reveal();
  if (bar && document.fonts) document.fonts.ready.then(() => { overflow(); if (current) reveal(); });

  const menu = document.querySelector("[data-nav-menu]");
  if (!menu) return;
  const summary = menu.querySelector("summary");
  const panel = menu.querySelector(".nav-panel");

  function fitPanel() {
    const bottom = summary.getBoundingClientRect().bottom;
    panel.style.maxHeight = Math.max(0, window.innerHeight - bottom) + "px";
  }

  function close(focus) {
    if (!menu.open) return;
    menu.open = false;
    if (focus) summary.focus();
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu.open) close(menu.contains(document.activeElement));
  });
  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target)) close(false);
  });
  menu.addEventListener("focusout", (e) => {
    if (e.relatedTarget && !menu.contains(e.relatedTarget)) close(false);
  });
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) close(false);
  });
  menu.addEventListener("toggle", () => { if (menu.open) fitPanel(); });
  window.addEventListener("resize", () => { if (menu.open) fitPanel(); });
  window.addEventListener("scroll", () => { if (menu.open) fitPanel(); }, { passive: true });
})();
