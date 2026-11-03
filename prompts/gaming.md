Task: write the short texts for the Gaming section. PC first; consoles only when it's big.

Return:
- new_on_pc: for each game in data.new_on_pc, a one-line blurb (at most ~20 words) saying what the
  game is and why it's notable (Steam rating and review count are in the data). Key: appid.
- reviews: for each review in data.reviews, a one-line verdict (at most ~22 words) summarizing what
  the outlet thought, based on the outlet's headline, score and excerpt. Write it as the outlet's view,
  not ours. Translate Swedish. Key: id.
- watch: for each video in data.watch, a one-line teaser (at most ~18 words) based only on the title
  and description. Key: url.
- news: pick up to {news_max} of data.news_candidates worth a line in Gaming news (skip guides, deals,
  listicles, minor patch notes, rumors). For each: id, an English headline (at most ~80 characters,
  translate Swedish), and a one-sentence summary.
- console_spotlight: up to {spotlight_max} items from data.news_candidates about console-first
  releases that are genuinely big (notability {spotlight_bar}+ out of 5: GTA VI, a new Zelda, a major
  first-party launch or date). Usually empty. For each: ids (candidate ids used), game, platforms
  (from: pc, ps5, xbox, switch, switch2), headline, summary (1–2 sentences). An item used here must
  not also appear in news.
