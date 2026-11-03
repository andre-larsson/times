Task: triage today's candidate items for the paper.

The reader's interests:
{interests}

For every candidate, return:
- id: the candidate's id, unchanged.
- keep: true if it belongs in this paper at all (any tier), false to drop it. Drop: off-topic items,
  buying guides, deals posts, listicles, opinion fluff, sponsored content, routine funding rounds,
  rumors with no substance, items that are clearly old news.
- section: "ai", "tech" or "gaming". AI = models, AI products, AI research, AI policy and AI
  business. Tech = software, developer tools, open source, security, infrastructure, hardware, big
  tech companies (when not mainly about AI). Gaming = games, game studios, game platforms.
- kicker: a 1–2 word label for the topic (see the house style).
- newsworthiness: 1–5 for this reader (halves allowed, e.g. 3.5).
    5 = major event the whole industry discusses today (a frontier model launch, a huge breach,
        GTA VI dated). Rare: at most a couple per day.
    4 = significant news a developer would want to read about today.
    3 = solid, relevant news.
    2 = minor but relevant; fine as a one-line brief.
    1 = barely relevant.
  Hacker News points and several outlets covering it are signals, not rules.
- event: a short lowercase key for the underlying story, e.g. "kestrel-2-release". Give the same key
  to every candidate that covers the same event, so they can be merged.
- title_en: the headline in English (translate non-English headlines; otherwise copy it).
