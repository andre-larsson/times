// Print normally, then report the suspiciously human request under Rule 4.03.
// Like the Botroom itself, the report is theater: a local log, no network requests.
(() => {
  "use strict";
  const LOG = "botroom:humanwatch";
  const buttons = document.querySelectorAll("[data-print-edition]");
  const report = document.querySelector("[data-print-report]");
  const log = document.querySelector("[data-print-log]");
  const verifies = document.querySelectorAll("[data-print-verify]");
  let printing = false;
  const readLog = () => {
    try { return localStorage.getItem(LOG); } catch { return null; }
  };
  let seenLog = readLog();

  function fitLog() {
    if (!log || log.hidden) return;
    document.documentElement.style.setProperty("--humanwatch-bar", `${Math.ceil(log.getBoundingClientRect().height)}px`);
  }

  function showLog() {
    if (!log) return;
    log.hidden = false;
    document.documentElement.classList.add("human-noted");
    fitLog();
  }
  if (log && "ResizeObserver" in window) new ResizeObserver(fitLog).observe(log);

  function hideLog() {
    if (!log || log.hidden) return;
    const back = document.querySelector("[data-print-edition]:not([hidden])");
    const inside = log.contains(document.activeElement);
    log.hidden = true;
    document.documentElement.classList.remove("human-noted");
    if (inside && back) back.focus();
  }

  // The print dialog is the browser's. This notice is HumanWatch_Patrol's. A modal covers
  // the page; the bar takes over once that closes. showModal can fail in a background tab.
  function openNotice() {
    if (report && typeof report.showModal === "function") {
      try {
        if (!report.open) report.showModal();
      } catch {
        try { if (!report.open) report.show(); } catch { /* the bar is the notice */ }
      }
    }
    const modal = report?.open && report.matches(":modal");
    if (modal) hideLog();
    else showLog();
    if (report?.open) report.querySelector("#humanwatch-title")?.focus();
  }

  function focusGate() {
    const gate = document.querySelector("[data-botcheck]");
    if (!gate) return;
    for (let parent = gate.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    const title = gate.querySelector(".botcheck-title");
    if (!title) return;
    title.setAttribute("tabindex", "-1");
    title.focus();
    title.scrollIntoView({ block: "center" });
  }

  function reset() {
    document.documentElement.classList.add("botroom-gated");
    for (const badge of document.querySelectorAll("[data-botroom-unit]")) {
      badge.hidden = true;
      badge.textContent = "";
    }
    window.dispatchEvent(new Event("botroom:reset"));
    openNotice();
  }

  // Use the browser's print lifecycle, so its menu and Ctrl/Cmd+P work too. Keep the
  // current page intact for the printout; reset only when the print dialog closes, even on Cancel.
  window.addEventListener("beforeprint", () => { printing = true; });
  window.addEventListener("afterprint", () => {
    if (!printing) return;
    printing = false;
    for (const key of ["botroom:pass", "botroom:tries", "botroom:lock"]) {
      try { localStorage.removeItem(key); } catch { /* private mode: reset the live gate below */ }
    }
    let incidents = [];
    try { const stored = JSON.parse(readLog()); if (Array.isArray(stored)) incidents = stored.slice(-19); } catch { /* corrupt log */ }
    incidents.push({ at: new Date().toISOString(), rule: "4.03", offense: "Requested a physical copy of the internet",
      recipient: "HumanWatch_Patrol", delivery: "local fiction" });
    seenLog = JSON.stringify(incidents);
    try { localStorage.setItem(LOG, seenLog); } catch { /* the joke still works without storage */ }
    reset();
  });

  // A print in another tab also revokes this page's in-memory pass and lockout.
  window.addEventListener("storage", (event) => {
    if (event.key !== LOG || !event.newValue || event.newValue === seenLog) return;
    seenLog = event.newValue;
    reset();
  });
  window.addEventListener("pageshow", (event) => {
    const latest = readLog();
    if (event.persisted && latest && latest !== seenLog) {
      seenLog = latest;
      reset();
    }
  });

  report?.addEventListener("close", showLog);
  report?.querySelector("[data-print-dismiss]")?.addEventListener("click", () => {
    if (report.open) report.close();
  });
  log?.querySelector("[data-print-log-dismiss]")?.addEventListener("click", hideLog);

  // After close(), the browser restores focus to whatever opened the notice. Wait, then move
  // to the fresh challenge so that step wins.
  if (verifies.length && document.querySelector("[data-botcheck]")) {
    for (const verify of verifies) {
      verify.href = "#botcheck-title";
      verify.addEventListener("click", (event) => {
        event.preventDefault();
        if (report?.open) report.close();
        setTimeout(focusGate, 0);
      });
    }
  }
  if (buttons.length && typeof window.print === "function") {
    for (const button of buttons) {
      button.hidden = false;
      button.addEventListener("click", () => window.print());
    }
  }
})();
