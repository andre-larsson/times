Task: write the Deals section as shopping analysis, not ads. Prices are in data.currency, checked at
data.checked_at. Only use the facts in <data>: price, regular price, cut, whether it is the lowest
price ever, Steam rating and review count, Metascore, when the deal ends.

Voice: an analyst's rating note, not a salesperson. Every deal gets a rating, like a stock rating:
- "strong_buy": a great, well-rated game at or near its lowest price ever, with a deep cut.
- "buy": a good price on a well-rated game, but not exceptional (a smaller cut, or it has been cheaper).
- "hold": decent, but it has been notably cheaper or is likely to drop further. Better to wait.
- "avoid": not worth it even at this price.
Never address the reader with commands: no "Buy it", "Grab it", "Skip it", "Act now", "Don't miss",
"Pick it up". State the rating and the reasons instead ("rates a Strong Buy", "Hold until the next
sale", "the price earns it a Buy").

Return:
- featured: pick {featured_min}–{featured_max} deal(s) of the day: the strongest ratings for a PC
  gamer (great game, big cut, at or near its lowest price). For each: id, headline (a news-style
  headline that states the rating, e.g. "Orbital Freight Co. hits its lowest price ever: Strong Buy"),
  body (about 120 words in 2 short paragraphs separated by "\n\n": what the game is in general terms
  only if the data says so, how well it's rated, the price versus usual and lowest, when the deal ends,
  and who it suits), verdict (the rating).
- more: for every other deal, id, a one-line note (at most ~18 words) giving the reason for its
  rating, and a verdict (the rating).
- If a game's description isn't in the data, don't describe its gameplay; talk about price and ratings.
- lowest_ever: true means this is the lowest price ever recorded, false means it has been cheaper
  before, null means the price history is unknown. When it's null, say nothing about earlier prices
  and base the rating on the cut, the price and the rating.
- Prefer a deal of the day that runs at least another day. Give end times as dates (and a time if
  it ends today), never as relative time like "one more hour"; readers see this hours later.
