Task: you are the copy desk. Check the paper's news quiz before it is published. data.questions are
the questions; data.stories has the full text of the story each question was written from, keyed by
story_id. Every question is published with its right answer, so a wrong answer key is the worst mistake
the quiz can make.

For each question, check:
- The answer is right according to its story (data.stories[story_id]). The fact must be in the story,
  not just plausible.
- Every one of the wrong_answers is wrong. Drop the question if any wrong answer could also be right,
  even partly or under another reading of the question (a rounded figure, a parent company, an earlier
  version, a second product that also qualifies).
- The question has one clear reading and one answer, and doesn't give the answer away.
- The explanation is accurate and supported by the story.
- Nothing off limits: site metrics such as Hacker News points, tragedies, private individuals,
  partisan politics, or a claim the story calls a rumor or unconfirmed.

Not your job: style, difficulty or how interesting the question is.

Reply with one result per question, in order:
- n: the question's number.
- verdict: "ok" when every check passes, otherwise "drop". There is no "fix": a doubtful question is
  dropped, never repaired.
- problem: for a drop, what is wrong in one short sentence; "" for ok.
