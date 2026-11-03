Task: write the Deals section as shopping advice, not ads. Prices are in data.currency, checked at
data.checked_at. Only use the facts in <data>: price, regular price, cut, whether it is the lowest
price ever, Steam rating and review count, Metascore, when the deal ends.

Return:
- featured: pick {featured_min}–{featured_max} deal(s) of the day: the best buys for a PC gamer
  (great game, big cut, at or near its lowest price). For each: id, headline (a news-style headline
  with the verdict, e.g. "Orbital Freight Co. hits its lowest price ever. Buy it."), body (about 120
  words in 2 short paragraphs separated by "\n\n": what the game is in general terms only if the data
  says so, how well it's rated, the price versus usual and lowest, when the deal ends, and who it's
  for), verdict ("buy", "wait" or "skip").
- more: for every other deal, id, a one-line advice (at most ~18 words) and a verdict.
  "buy" = great price on a well-rated game; "wait" = decent but has been cheaper or likely will be;
  "skip" = not worth it even at this price.
- If a game's description isn't in the data, don't describe its gameplay; talk about price and ratings.
- lowest_ever: true means this is the lowest price ever recorded, false means it has been cheaper
  before, null means the price history is unknown. When it's null, say nothing about earlier prices
  and base the verdict on the cut, the price and the rating.
- Prefer a deal of the day that runs at least another day. Give end times as dates (and a time if
  it ends today), never as relative time like "one more hour"; readers see this hours later.
