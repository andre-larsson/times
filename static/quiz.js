// The quiz, step by step: a start screen, one question at a time (one try each, answer and story shown
// right away), then the result. Answers, time and result are saved in this browser (localStorage), so a
// quiz can be resumed, and quiz cards elsewhere are marked "Completed". Without this script every
// question shows at once and CSS reveals the answers (:has(input:checked)).
(() => {
  "use strict";
  const PER_QUESTION_MS = 3 * 60 * 1000;          // the timer counts at most this per question (an idle tab)

  const keyFor = (id) => `quiz:${id}`;
  function load(id) {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(keyFor(id)) || "{}") || {}; } catch { /* blocked or bad JSON */ }
    // The first version saved only the answers ({q1: "2", …})
    return saved.answers ? saved : { answers: saved };
  }
  const save = (id, state) => { try { localStorage.setItem(keyFor(id), JSON.stringify(state)); } catch { /* private mode */ } };
  const forget = (id) => { try { localStorage.removeItem(keyFor(id)); } catch { /* private mode */ } };

  function markCards() {
    for (const card of document.querySelectorAll("[data-quiz-card]")) {
      const state = load(card.dataset.quizCard);
      const badge = card.querySelector("[data-quiz-done]");
      if (!badge) continue;
      const done = state.done && Number.isInteger(state.right) && Number.isInteger(state.total);
      badge.hidden = !done;
      card.classList.toggle("is-done", Boolean(done));
      if (done) badge.querySelector("[data-quiz-done-score]").textContent = `${state.right}/${state.total}`;
    }
  }

  function verdict(right, total) {
    if (right === total) return "A perfect score.";
    if (right >= total * 0.75) return "Sharp.";
    if (right >= total * 0.5) return "Not bad.";
    return "The archive has every story.";
  }

  function clock(ms) {
    const s = Math.max(1, Math.round(ms / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  function play(app) {
    const id = app.dataset.quiz;
    const items = [...app.querySelectorAll(".quiz-q")];
    const total = items.length;
    const $ = (sel) => app.querySelector(sel);
    const start = $(".quiz-start"), nav = $(".quiz-nav"), end = $(".quiz-end");
    const prev = $("[data-quiz-prev]"), next = $("[data-quiz-next]");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let state = load(id);
    let current = -1;
    let shownAt = 0;                              // when the current unanswered question appeared

    const chosen = (i) => items[i].querySelector("input:checked");
    const answered = (i) => Boolean(chosen(i));
    const right = (i) => Boolean(chosen(i)?.closest(".quiz-opt--right"));
    const fields = (i) => items[i].querySelector("fieldset");
    const open = () => items.map((_, i) => i).filter((i) => !answered(i));
    const score = () => items.filter((_, i) => right(i)).length;

    function show(view) {
      start.hidden = view !== "start";
      nav.hidden = view !== "question";
      end.hidden = view !== "end";
      if (view !== "question") items.forEach((item) => item.classList.remove("is-current"));
    }

    // Bring the top of the quiz into view when a step starts above the screen, then focus it
    function arrive(target, anchor) {
      if (anchor.getBoundingClientRect().top < 0) anchor.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
      target.focus({ preventScroll: true });
    }

    function label(i) {
      const left = open();
      const button = items[i].querySelector("[data-quiz-advance]");
      button.textContent = left.length ? "Next question" : "See result";
      next.disabled = !answered(i) || i === total - 1;
    }

    function go(i, focus = true) {
      current = i;
      items.forEach((item, j) => item.classList.toggle("is-current", j === i));
      show("question");
      $("[data-quiz-at]").textContent = String(i + 1);
      prev.disabled = i === 0;
      label(i);
      shownAt = answered(i) ? 0 : Date.now();
      if (focus) arrive(items[i], nav);
    }

    function finish(focus = true) {
      show("end");
      current = -1;
      $("[data-quiz-score]").textContent = String(state.right);
      $("[data-quiz-verdict]").textContent = verdict(state.right, total);
      const time = $("[data-quiz-time]");
      time.hidden = !state.time;
      time.textContent = state.time ? `Finished in ${clock(state.time)}.` : "";
      end.querySelectorAll("[data-quiz-goto]").forEach((row, i) => {
        const ok = right(i);
        row.classList.toggle("is-right", ok);
        row.classList.toggle("is-wrong", !ok);
        row.querySelector("[data-quiz-sym]").textContent = ok ? "✓" : "✗";
        row.querySelector("[data-quiz-word]").textContent = ok ? "Right: " : "Wrong: ";
      });
      if (focus) arrive(end, end);
    }

    function welcome() {
      const done = total - open().length;
      $("[data-quiz-progress]").textContent = done ? `${done} of ${total} answered` : `${total} questions`;
      $("[data-quiz-start]").textContent = done ? "Continue" : "Start the quiz";
      show("start");
    }

    function complete() {
      Object.assign(state, { done: true, right: score(), total, finished: state.finished || new Date().toISOString() });
      save(id, state);
      markCards();
    }

    app.addEventListener("change", (event) => {
      const i = items.indexOf(event.target.closest(".quiz-q"));
      if (i < 0) return;
      fields(i).disabled = true;                  // one try per question
      state.answers[event.target.name] = event.target.value;
      if (shownAt) state.time = (state.time || 0) + Math.min(Date.now() - shownAt, PER_QUESTION_MS);
      shownAt = 0;
      if (open().length) save(id, state);
      else complete();
      label(i);
      items[i].querySelector(".quiz-reveal").focus({ preventScroll: true });   // read out the verdict
    });

    // Arrow keys would pick an option (and with one try, commit to it): here they only move the focus,
    // and Space or Enter picks
    app.addEventListener("keydown", (event) => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.type !== "radio" || input.disabled) return;
      if (event.key === "Enter") { event.preventDefault(); input.click(); return; }
      const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const group = [...input.closest(".quiz-options").querySelectorAll("input")];
      group[(group.indexOf(input) + step + group.length) % group.length].focus();
    });

    app.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      if (button.matches("[data-quiz-start]")) {
        go(open()[0] ?? 0);
      } else if (button.matches("[data-quiz-advance]")) {
        const left = open();
        if (!left.length) finish();
        else go(left.find((j) => j > current) ?? left[0]);
      } else if (button.matches("[data-quiz-prev]")) {
        go(current - 1);
      } else if (button.matches("[data-quiz-next]")) {
        go(current + 1);
      } else if (button.matches("[data-quiz-goto]")) {
        go(Number(button.dataset.quizGoto));
      } else if (button.matches("[data-quiz-reset]")) {
        forget(id);
        state = { answers: {} };
        items.forEach((item, i) => {
          fields(i).disabled = false;
          item.querySelectorAll("input").forEach((input) => { input.checked = false; });
        });
        markCards();
        go(0);
      }
    });

    // Put back the saved answers, then open where the reader left off
    items.forEach((item, i) => {
      for (const input of item.querySelectorAll("input")) {
        if (state.answers[input.name] === input.value) {
          input.checked = true;
          fields(i).disabled = true;
        }
      }
    });
    app.classList.add("quiz-app--live");
    if (open().length) welcome();
    else {
      if (!state.done || state.right !== score() || state.total !== total) complete();
      finish(false);
    }
  }

  const app = document.querySelector("[data-quiz]");
  if (app) play(app);
  markCards();
})();
