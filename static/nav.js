// The nav. On a phone the sections scroll sideways: bring the current page's link into view.
// The Menu is a <details> disclosure, so it opens and closes without JS. This adds the expected
// ways out: Escape, a click or tab outside it, and coming back to the page from the back/forward cache.
(() => {
  "use strict";
  const bar = document.querySelector(".nav-sections");
  const current = bar && bar.querySelector(".is-active");
  function reveal() {
    const b = bar.getBoundingClientRect(), r = current.getBoundingClientRect();
    if (r.right > b.right - 40) bar.scrollLeft += r.left - b.left - (b.width - r.width) / 2;   // 40px: the fade
  }
  if (current) {
    reveal();
    if (document.fonts) document.fonts.ready.then(reveal);   // the headline font widens the links when it loads
  }

  const menu = document.querySelector("[data-nav-menu]");
  if (!menu) return;
  const summary = menu.querySelector("summary");

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
})();
