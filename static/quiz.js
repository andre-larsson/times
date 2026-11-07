// The quiz page: locks each question once it's answered, keeps the score, and remembers the answers in
// this browser. Right and wrong are shown by CSS (:has(input:checked)), so the quiz works without this.
(() => {
  "use strict";
  const quiz = document.querySelector("[data-quiz]");
  const box = document.querySelector(".quiz-score");
  if (!quiz || !box) return;
  const key = `quiz:${quiz.dataset.quiz}`;
  const items = [...quiz.querySelectorAll(".quiz-q")];
  const line = box.querySelector(".quiz-score-line");

  const load = () => { try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch { return {}; } };
  const save = (answers) => { try { localStorage.setItem(key, JSON.stringify(answers)); } catch { /* private mode */ } };
  const forget = () => { try { localStorage.removeItem(key); } catch { /* private mode */ } };
  const fields = (item) => item.querySelector("fieldset");

  function verdict(right, total) {
    if (right === total) return "A perfect score.";
    if (right >= total * 0.75) return "Sharp.";
    if (right >= total * 0.5) return "Not bad.";
    return "The archive has every story.";
  }

  function score() {
    let answered = 0, right = 0;
    for (const item of items) {
      const chosen = item.querySelector("input:checked");
      if (!chosen) continue;
      answered += 1;
      if (chosen.closest(".quiz-opt--right")) right += 1;
    }
    const total = items.length;
    box.hidden = answered === 0;
    line.textContent = answered < total
      ? `${right} of ${answered} right so far, ${total - answered} to go.`
      : `You got ${right} of ${total}. ${verdict(right, total)}`;
  }

  quiz.addEventListener("change", (event) => {
    const item = event.target.closest(".quiz-q");
    if (!item) return;
    fields(item).disabled = true;                  // one try per question
    const answers = load();
    answers[event.target.name] = event.target.value;
    save(answers);
    score();
  });

  box.querySelector("[data-quiz-reset]").addEventListener("click", () => {
    forget();
    for (const item of items) {
      fields(item).disabled = false;
      for (const input of item.querySelectorAll("input")) input.checked = false;
    }
    score();
    items[0]?.querySelector("input")?.focus();
  });

  const saved = load();
  for (const item of items) {
    for (const input of item.querySelectorAll("input")) {
      if (saved[input.name] === input.value) {
        input.checked = true;
        fields(item).disabled = true;
      }
    }
  }
  score();
})();
