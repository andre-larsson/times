Task: you are the opinion editor. Pick the topic for the paper's next opinion column from the stories
it ran in the last {lookback_days} days (in <data>), and brief the columnist.

The reader's interests:
{interests}

A good column topic
- Matters to the reader, and the reporting gives the column real facts to stand on: several stories on
  one thread, or one big story with a question worth arguing about.
- Has a real argument in it: reasonable people disagree, or the obvious take is wrong.
- Is new. earlier_columns lists what the column has already argued. Never return to one of those topics
  unless something big has changed, and then argue a clearly different point.
- Prefer threads from the last week, but an older story is fine if it's still unresolved.

Variety: the choices are already narrowed for this column
- format: one of allowed_formats (format_guide explains each). Pick the one the topic suits best.
- focus: one of allowed_focus (focus_guide explains each).
- Don't pick the same company, product or story family as the most recent earlier column.

Off limits
- Partisan politics: elections, parties, politicians and who is right politically. Tech policy is fine
  when the column argues about the technology and its effects on people.
- Anthropic and Claude, including stories mainly about them. The column is written by Claude, so it
  has a conflict of interest.
- Tragedies and stories about private individuals.

Reply with:
- topic: 2–6 words naming the subject, e.g. "Memory prices and the gaming PC".
- focus, format: from the allowed lists.
- thesis: the position the column will argue, in one or two specific, arguable sentences.
- story_ids: 3–8 ids from stories (the most important first) whose facts the column will use. The
  columnist gets each story's full text: featured and medium stories have a few hundred words, briefs
  and gaming_news only a sentence or two. Include at least two featured or medium stories when the
  topic has them.
