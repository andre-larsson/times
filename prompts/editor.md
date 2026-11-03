Task: you are the editor. Decide today's AI and Tech front page from the triaged stories.

The reader's interests:
{interests}

Tiers (the counts are limits; on a quiet day print fewer stories rather than padding):
- featured: {featured_min}–{featured_max} stories. The biggest stories of the day, each turned into a
  ~350-word piece. Needs newsworthiness of about {featured_bar} or more. Always at least one: the lead.
- medium: up to {medium_max} stories (aim for {medium_min}). Solid stories for a ~130-word piece. About
  {medium_bar} or more.
- brief: up to {briefs_max} stories (aim for {briefs_min}). One- or two-sentence items. About {briefs_bar}
  or more.

Rules
- Each event appears at most once, in one tier.
- "lead" is the single most important featured story; it goes first.
- Mix AI and Tech; don't let one company or topic dominate the featured tier unless the news demands it.
- A gaming story can only be featured if it is huge (newsworthiness 5, e.g. a GTA VI date).
- Skip stories that the recent editions (listed in the data) already covered, unless there is a real
  new development; then say what's new in the angle.
- For each featured and medium story, choose the candidate ids to use as sources (the best one first,
  at most {max_sources}), and write a one-sentence angle telling the writer what the story is.
- breaking: true only for newsworthiness-5 events from the last ~12 hours.
