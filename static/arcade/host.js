// Host page bridge for sandboxed 403 Arcade iframes: mounts srcdoc, tracks help dismissal and best score, resizes height.
(() => {
  "use strict";
  const docEl = document.getElementById("arcade-doc");
  const frame = document.getElementById("arcade-frame");
  if (!docEl || !frame) return;

  let data;
  try {
    data = JSON.parse(docEl.textContent);
  } catch {
    return;
  }

  const baseH = data.layout === "pointer" ? 548 : data.layout === "typing" ? 730 : 640;
  frame.style.height = `${baseH}px`;

  const helpKey = `times:arcade:help:${data.id}`;
  const bestKey = `times:arcade:best:${data.id}`;
  let seen = false;
  let best = 0;
  try {
    seen = localStorage.getItem(helpKey) === "1";
    best = Math.max(0, Math.round(Number(localStorage.getItem(bestKey)) || 0));
  } catch {
    /* private mode */
  }

  window.addEventListener("message", (e) => {
    if (e.source !== frame.contentWindow || !e.data || e.data.id !== data.id) return;
    if (e.data.type === "arcade:helpSeen") {
      try { localStorage.setItem(helpKey, "1"); } catch { /* private mode */ }
    } else if (e.data.type === "arcade:best" && typeof e.data.best === "number") {
      const next = Math.max(0, Math.round(e.data.best));
      if (next > best) {
        best = next;
        try { localStorage.setItem(bestKey, String(best)); } catch { /* private mode */ }
      }
    } else if (e.data.type === "arcade:height" && typeof e.data.height === "number") {
      const h = Math.max(baseH, Math.min(980, Math.ceil(e.data.height) + 4));
      frame.style.height = `${h}px`;
    }
  });

  frame.srcdoc = data.srcdoc
    .replace("__ARCADE_HELP_SEEN__", seen ? "true" : "false")
    .replace("__ARCADE_BEST__", String(best));
})();
