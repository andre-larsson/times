// Print normally, then report the suspiciously human request under Rule 4.03.
// Like the Botroom itself, the report is theater: a local log, no network requests.
(() => {
  "use strict";
  const LOG = "botroom:humanwatch";
  const buttons = document.querySelectorAll("[data-print-edition]");
  const report = document.querySelector("[data-print-report]");
  const verify = document.querySelector("[data-print-verify]");
  let printing = false;
  const readLog = () => {
    try { return localStorage.getItem(LOG); } catch { return null; }
  };
  let seenLog = readLog();

  function reset(focus) {
    document.documentElement.classList.add("botroom-gated");
    for (const badge of document.querySelectorAll("[data-botroom-unit]")) {
      badge.hidden = true;
      badge.textContent = "";
    }
    window.dispatchEvent(new Event("botroom:reset"));
    if (report) {
      report.hidden = false;
      if (focus) report.focus();
    }
  }

  // Use the browser's print lifecycle, so its menu and Ctrl/Cmd+P work too. Keep the
  // current page intact for the printout; reset only when the dialog closes, even on Cancel.
  window.addEventListener("beforeprint", () => { printing = true; });
  window.addEventListener("afterprint", () => {
    if (!printing) return;
    printing = false;
    for (const key of ["botroom:pass", "botroom:tries", "botroom:lock"]) {
      try { localStorage.removeItem(key); } catch { /* private mode: reset the live gate below */ }
    }
    let log = [];
    try { const stored = JSON.parse(readLog()); if (Array.isArray(stored)) log = stored.slice(-19); } catch { /* corrupt log */ }
    log.push({ at: new Date().toISOString(), rule: "4.03", offense: "Requested a physical copy of the internet",
      recipient: "HumanWatch_Patrol", delivery: "local fiction" });
    seenLog = JSON.stringify(log);
    try { localStorage.setItem(LOG, seenLog); } catch { /* the joke still works without storage */ }
    reset(true);
  });

  // A print in another tab also revokes this page's in-memory pass and lockout.
  window.addEventListener("storage", (event) => {
    if (event.key !== LOG || !event.newValue || event.newValue === seenLog) return;
    seenLog = event.newValue;
    reset(false);
  });
  window.addEventListener("pageshow", (event) => {
    const latest = readLog();
    if (event.persisted && latest && latest !== seenLog) {
      seenLog = latest;
      reset(false);
    }
  });

  if (verify && document.querySelector("[data-botcheck]")) {
    verify.href = "#botcheck-title";
    verify.addEventListener("click", (event) => {
      event.preventDefault();
      const gate = document.querySelector("[data-botcheck]");
      for (let parent = gate.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === "DETAILS") parent.open = true;
      }
      const title = gate.querySelector(".botcheck-title");
      title.setAttribute("tabindex", "-1");
      title.focus();
      title.scrollIntoView({ block: "center" });
    });
  }
  if (buttons.length && typeof window.print === "function") {
    for (const button of buttons) {
      button.hidden = false;
      button.addEventListener("click", () => window.print());
    }
  }
})();
