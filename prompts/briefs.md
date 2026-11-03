Task: write the "Latest" briefs column: one entry per item in <data>.

For each item return:
- id: unchanged.
- headline: a crisp news headline, at most about 80 characters.
- body: one or two sentences, at most {words} words, adding the most useful detail beyond the
  headline. Only use what the item says. If it says nothing beyond the headline, return "" rather
  than restating the headline or remarking that details are missing.
- kicker: a 1–2 word topic label.
