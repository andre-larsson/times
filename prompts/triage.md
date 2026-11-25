Task: triage today's candidate items for the paper.

The reader's interests:
{interests}

For every candidate, return:
- id: the candidate's id, unchanged.
- keep: true if it belongs in this paper at all (any tier), false to drop it. Drop: off-topic items,
  buying guides, deals posts, listicles, opinion fluff, sponsored content, routine funding rounds,
  rumors with no substance, items that are clearly old news, job ads and lecture notes.
- section: "ai", "tech" or "gaming". AI = models, AI products, AI research, AI policy and AI
  business, and math or science done with AI (a proof an AI found or checked). Tech = software,
  developer tools, open source, security, infrastructure, hardware, big tech companies (when not
  mainly about AI), and math and computer science research without an AI angle (algorithms,
  complexity theory, cryptography). Gaming = games, game studios, game platforms.
- kicker: a 1–2 word label for the topic (see the house style).
- newsworthiness: 1–5 for this reader (halves allowed, e.g. 3.5).
    5 = major event the whole industry discusses today (a frontier model launch, a huge breach,
        GTA VI dated). Rare: at most a couple per day.
    4 = significant news a developer would want to read about today.
    3 = solid, relevant news.
    2 = minor but relevant; fine as a one-line brief.
    1 = barely relevant.
  Hacker News points and several outlets covering it are signals, not rules.
  Research is news too. A credible claim to settle a famous open problem (the Riemann Hypothesis,
  P vs NP, VP vs VNP, a new matrix multiplication exponent) is a 4 or 5 before experts have checked
  it, and a check of it (a Lean verification, a flaw found) is news again. Credible means a known
  researcher or lab, or experts discussing it; a lone unknown author's P vs NP proof is a 1. Smaller
  results (a better bound, a new algorithm) are 2 to 3.
  A short technical headline (a theorem, a paper title) can be big news. Look at the link (the
  page's host and path) and the points before you drop one you don't recognize.
- event: a short lowercase key for the underlying story, e.g. "kestrel-2-release". Give the same key
  to every candidate that covers the same event, so they can be merged.
- title_en: an English translation of a non-English headline. For English headlines return ""
  (don't copy them; the output must stay short).
