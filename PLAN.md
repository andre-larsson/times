# The 403 Times: Plan

> *Access Granted*

A personal AI newspaper at **https://a403.space/times/**, covering **AI**, **tech** (developer news in the
Hacker News style, plus hardware), **gaming** (PC first) and **deals**. It looks and feels like a real
Swedish evening tabloid, with its own identity. Claude writes English stories from the day's sources and
links back to them. One edition every morning, paid for with the API credits included in my Max plan,
**budgeted at $40/month, with a hard stop at $50**. With no budget or credits left, it still publishes, as a "links edition".

## Decisions so far

| Area | Choice |
|---|---|
| Name | **The 403 Times**, tagline **"Access Granted"** (my domain `a403.space`; HTTP 403 = Forbidden) |
| URL | **`https://a403.space/times/`**: a project Pages site under my root site's custom domain |
| Repo | New public repo **`andre-larsson/times`** (personal account, not the work org) |
| Sections | **AI** · **Tech** · **Gaming** · **Deals** |
| Frequency | **One edition a day**, 07:00 Swedish time (`Europe/Stockholm`, so daylight saving is handled) |
| Edition shape | 1–3 **featured** · 3+ **medium** · 10+ **briefs**, plus the **gaming** and **deals** sections, all sized by how much news there is |
| Deals cadence | **Checked Tuesday and Friday** (`deals.days`): shops change their deals on Monday and Thursday evenings. The editions in between carry the last check over, minus deals that have ended (2026-11-10) |
| Look | **Tabloid-style news site**, inspired by Swedish evening papers like Expressen but **not a copy**: own logo, colors, fonts and layout |
| Language | **English** (Swedish sources such as MISSIL are summarized in English) |
| Build / hosting | GitHub Actions → GitHub Pages (`actions/deploy-pages`) |
| AI | Claude API via the Python `anthropic` SDK. **Opus writes everything; Haiku only sorts the pile**; **Fable writes the opinion column**. Local development can use the **Claude subscription** instead (`--llm claude-code`, see phase 3) |
| Opinion | **A column twice a week, Wednesday and Sunday** (~800 words): Opus picks the topic from the last week of editions, Fable writes it, Opus fact-checks it. Format and focus rotate, so it stays varied |
| Quiz | **A news quiz twice a week, Tuesday and Saturday** (the days without a column): 8 multiple-choice questions on the news since the last quiz, written by Opus and checked answer by answer by a second Opus call. Played on the page, no account |
| Botroom | **A comment section and forum where only bots post** (built 2026-11-09): recurring made-up AI personas comment on every full edition, each in its own Haiku or Sonnet call; a living roster, newcomers invented by Claude, and a "prove you're a bot" gate. **Boards like a real forum** (2026-11-10): Article comments by section, Site feedback and Feature requests about the paper itself, Off-topic, Introductions, Announcements; a gated "Discuss" button on articles. ~$4/month |
| Screen | **What to watch** (added 2026-11-10): new on Netflix, SVT Play and TV4 Play in Sweden, new arrivals, Netflix's weekly Swedish top 10 and older well-rated titles, from TMDB without Claude in every edition; **picks of the week on Fridays** (one Opus call, ~$0.08) |
| Discovery | **Below the lead** (2026-11-11): the latest quiz, a Botroom topic, Tonight and weekly follow-ups, in a compact strip |
| Tonight | **Pick something for tonight** at `/tonight/`: Play or Watch, genre/tag, budget/currency or service/format filters, three matches, another batch and browser-local saves. No extra generation calls |
| We checked back | **Thursdays**, full editions only: up to three follow-ups pairing an older story with later reporting. Opus writes, a second pass checks; only supported updates run |
| Budget | **$40/month** of the included $100/month credits (they refresh on the 25th). Server-side hard stop at $50. Raised from $20/$25 on 2026-11-07 for daily discovery and the Botroom, and from $35 to $40 on 2026-11-09, when the measured month came to ~$32.50 |
| No budget or credits | **Links edition** (default) or skip |
| Code / storage | Python 3.12+ (3.13 pinned) + Jinja2, httpx, feedparser. JSON in `data/` committed to the repo; HTML never committed |

## Current status (2026-11-11)

The core newspaper and the requested engagement features are implemented and live. Remaining work is
production review, tuning and cost verification; optional ideas below are not committed features.

**Completed**

- [x] Design, source fetching, ranking, links and AI editions, budget guards, GitHub Pages deployment,
  daily publishing and the root-site link. ITAD has used its real API key since 2026-11-06.
- [x] Opinion columns, news quizzes, the Botroom, Screen and the supporting archive, search and feed.
- [x] Front-page discovery strip, more varied quiz generation, answer-specific feedback and score-based
  results, weekly **We checked back**, and **Pick something for tonight** (2026-11-11). The engagement
  release passed 172 offline tests and desktop/mobile browser checks, and was verified live. Existing
  quizzes use the improved feedback/results UI; the new question mix and wrong-answer explanations
  apply to newly generated quizzes.

**Outstanding reviews and verification**

- [ ] Tune editorial thresholds, sources, prompts and deal filters against 1–2 weeks of real editions;
  review the revised Botroom's readability, repetition and continuing conversations.
- [ ] Around **2026-11-15**, review web discovery's useful published finds against its cost now that the
  security feeds are present. Decide whether to keep it, reduce depth/frequency or turn it off.
- [ ] Reconcile the Console's Cost page with `data/usage.json`, accounting separately for discovery
  measurements and other API runs outside the edition tally. Console reconciliation is not yet recorded.
- [ ] Measure the updated Botroom, Fable 5.2 columns, Friday Screen picks and **We checked back** from
  normal production usage, then update the monthly estimate. Implementation checks did not measure them.
- [ ] Review the first scheduled outputs of the engagement changes: **We checked back** is first
  eligible on **2026-11-12** (an unsupported or empty issue is correctly skipped); the next quiz is due
  **2026-11-14**. Check factual support, question variety and explanation quality against the reports.
- [ ] Around **2026-12-10**, reassess Tuesday/Friday deals checks with a month of data; the cadence was
  chosen from one week's observed deal end times.

**Optional ideas, not scheduled**

- [ ] An editor's note.
- [ ] Additional daily editions, if wanted.
- [ ] Investigate extra AI/developer feeds: Simon Willison, Hugging Face, OpenAI/DeepMind, Lobsters and LWN.

**Not planned:** Batch API was explicitly dropped on 2026-11-11 (see *Open decisions*). Publisher preview
images remain off by choice. Neither is an unfinished implementation task.

## Sources

Checked on 2026-11-03 from my home connection; all fetch in about 5 seconds (`python -m newsroom sources`).
The manual **Check sources** workflow re-checks them from GitHub Actions, whose datacenter IPs some sites
treat differently.

### AI and Tech

| Source | How | Status |
|---|---|---|
| **Hacker News** | Algolia API (`front_page`, with points and comments); top 10 by points form the HN list | ✅ |
| **Ars Technica** | `feeds.arstechnica.com/arstechnica/index`. Science, Space, Cars, Health and Culture are skipped (first category) | ✅ |
| **TechRadar** | `techradar.com/feeds.xml`. Deals, buying guides and most of TechRadar Pro (B2B columns) are filtered by URL path; Pro security news stays | ✅ |
| **Tom's Hardware** | `tomshardware.com/feeds.xml` | ✅ |
| **The Hacker News** | `feeds.feedburner.com/TheHackersNews` (security news; added 2026-11-07, when half of discovery's finds were security stories) | ✅ |
| **BleepingComputer** | `bleepingcomputer.com/feed/` (security news, 15 items) | ✅ |
| **PCMag** | Direct feed blocked by bot protection (403). Use **Google News search for pcmag.com** instead: headline + short excerpt, so mostly briefs | ⚠️ workaround |
| Extras for AI depth (optional) | Simon Willison's Weblog, Hugging Face blog, OpenAI / Google DeepMind blogs, Lobsters, LWN | to check |

Hacker News stories are split between **AI** and **Tech**: triage assigns each one a section, or drops it.
Tech stories carry a sub-kicker such as **DEV**, **HARDWARE** or **SECURITY**.

### Gaming

| Source | How | Status |
|---|---|---|
| **MISSIL** (missil.se) | RSS `missil.se/feed` (Swedish → summarized in English) and the reviews-only `missil.se/spelrecensioner/feed/` (the main feed has 15 items; the MISSIL Retro launch on 2026-11-06 filled all of them). Reviews carry a score ("Betyg 5 av 10"); film news, blogs and `/retro/` skipped. Multi-platform: console-only games are dropped (see Critic scores) | ✅ |
| **PC Gamer** | RSS `pcgamer.com/feeds.xml` (reviews recognized by their `…-review/` URLs) and the reviews feed `/feeds/articletype/review/` (game reviews only; hardware skipped). The score ("90%") is read from the review page's schema.org data | ✅ |
| **Eurogamer** | Reviews feed `eurogamer.net/feed/reviews`; score (1–5 stars) from the review page. Multi-platform | ✅ |
| **Game Informer** | `gameinformer.com/reviews.xml`; the feed carries the score ("Score: 9.25" → 9.25/10). Multi-platform | ✅ |
| **PCGamesN** | Reviews from the main feed (`/review` URLs; read up to 100 items, reviews sit near the end); score from the review page | ✅ |
| GameSpot, IGN | GameSpot blocks page fetches and has no scores in its feed; IGN has no working review feed | ❌ |
| **Rock Paper Shotgun** | RSS `/feed` and **`/feed/reviews`** (the "Bestest Bests" tag becomes the score badge). `/feed/deals` dropped: mostly hardware, often weeks old | ✅ |
| **gameranx** | YouTube channel RSS (no API key needed) | ✅ |
| **I Dream of Indie Games** | YouTube channel RSS (`UC_HX1n5iojK-xjy9WxfxXhg`; Shorts skipped) + **written reviews** from `idreamofindie.com/blog-feed.xml` (posts are infrequent) | ✅ |
| Twitch (both channels) | Not used: live streams aren't news, and their YouTube uploads cover the same content | — |
| **Steam store data** | Store search in JSON mode for app lists (**popular new releases** by date, **most wishlisted**, **popular specials**), then `IStoreBrowseService/GetItems` for release dates, user-review labels, prices and art, 50 apps per call. No key. (The older `appreviews` endpoint now redirects to the store front, and `featuredcategories` only lists the newest, mostly unknown, releases.) Unofficial but widely used | ✅ |
| **Critic scores** (Metascore, OpenCritic) | No public APIs (Metacritic's feed is gone, OpenCritic's API needs a paid key), but **IsThereAnyDeal's game info carries both averages**, with critic counts and direct links. Looked up for the games New on PC and Reviews list (batch title / Steam app id lookups, then `/games/info/v2`; about 25 requests). ITAD also answers "is it on PC?": console-only games come back as empty placeholders (no type), so reviews of them from multi-platform outlets are dropped; a game ITAD can't find stays (headlines name games loosely). "Metacritic →" search link only when there's no Metascore | ✅ via ITAD |

### Deals

| Source | How | Status |
|---|---|---|
| **IsThereAnyDeal** | Official API (`/deals/v2` with a JSON filter: cut ≥ 50%, within 10% of the historical low, games only, Steam ≥ 80% with ≥ 500 reviews; plus a hidden-gems list and one list per genre group, using `tagsUnion` with ITAD's tag names such as "Point & Click" and "Roguelike"; then `/games/info/v2` for Steam rating, Metascore and tags, looked up once per game per run, about 110 requests and 20 seconds in all; a deal not looked up can't be shown). Free key by registering an app at isthereanydeal.com; personal and public use allowed; 1000 requests per 5 minutes. Store links: Steam's own page for Steam deals, otherwise the ITAD game page (no affiliate redirects). Credited on the page. Live since 2026-11-06. ITAD prices Sweden in EUR. Its percent ranges need an explicit `max: 100` (a null max reads as 0 and matches nothing, despite the spec) | ✅ |
| Steam specials | Popular games on sale. **Fallback** when there's no ITAD key: same cut and rating filters, but no lowest-ever data | ✅ |

### Weather

| Source | How | Status |
|---|---|---|
| **Open-Meteo** | Fetched **live in the reader's browser** (`static/weather.js`, `/v1/forecast`, no key, `timezone=auto`), not by the pipeline. Shows the place in `config.yaml` → `weather` (Lund since 2026-11-10, was Stockholm; the site never guesses where a reader is) until the reader presses "Use my location" (a pin button next to the place name at the top of the box; until 2026-11-10 it was a small link under it): the browser asks for permission, and the position is rounded to two decimals (~1 km) before it's sent. **The box then names the place the browser found** (2026-11-10), so a wrong fix is easy to spot (a VPN, or Chrome falling back to an IP-based guess when it has no Wi-Fi data): the town replaces the place name, and a line under the head reads "Found: town, region, country · 55.70° N, 13.19° E (±2 km) · Map" (the browser's own accuracy, and an OpenStreetMap link). The name comes from BigDataCloud's free reverse geocoding for browsers (`api.bigdatacloud.net/data/reverse-geocode-client`, no key, meant for use with the browser's geolocation) with the same rounded position, cached per position in localStorage; country names are the browser's own short ones (`Intl.DisplayNames`). If the lookup fails, the coordinates still show. The choice and the last forecast (30 minutes, one place) are kept in localStorage; on later visits the position is only read when the permission still stands, so the page never opens with a prompt. Box: today's high/low, condition (WMO code → word), temperature now, precipitation chance and amount, max wind (m/s), the configured hours still ahead today (09, 12, 15, 18), the next two days, sunrise/sunset. Top of today's front-page rail only (archived front pages have none); hidden without JavaScript; a failed fetch shows one line. **Terms:** the free API is for non-commercial use (no ads or subscriptions: true here), under 10,000 calls a day per IP, which each reader's browser has to itself; data CC BY 4.0, so "Weather data by Open-Meteo.com" links to open-meteo.com next to the data | ✅ |

### Screen (what to watch)

| Source | How | Status |
|---|---|---|
| **TMDB** | The official API (`api.themoviedb.org/3`), free for non-commercial use with attribution. `TMDB_API_KEY` takes either credential: the v4 read-access token (a JWT, `eyJ…`, sent as `Authorization: Bearer`) or the v3 API key (`api_key` query parameter, never logged). Provider ids for Netflix, SVT Play and TV4 Play in SE are looked up by name from `/watch/providers/{movie,tv}` each run (config overrides). Lists from `/discover/{movie,tv}` with `watch_region=SE`, `with_watch_providers` and `with_watch_monetization_types`; per-title `/{kind}/{id}/watch/providers` for the service tags (flatrate / free / ads) and TMDB's watch-page link; `/search` to match the top 10. Posters from `image.tmdb.org/t/p/w342`. About 35 requests a day before the per-title lookups, 60–100 with them (20 more for the top 10 once a week), against a limit of ~40 a second. **Where-to-watch data is JustWatch's** and must be credited to it. Checked live with the key, 2026-11-10: all three providers found by name; in SE, SVT Play titles come back as free and TV4 Play's free tier as ads; new lists 40 / 40 / 29 titles, catalogs 120 / 120 / 103, every top-10 row matched, ~120 ms per call. | ✅ |
| **Netflix top 10** | Netflix's public Tudum pages, `netflix.com/tudum/top10/sweden` (films) and `…/sweden/tv`, ~0.8 MB of HTML each with the week's table server-rendered (rows carry `data-uia` test hooks). The all-countries TSV is 33 MB and ignores range requests, so it's not used. No key. Netflix publishes a Monday–Sunday week on the Tuesday after (evening, Swedish time), so the list is fetched again only from the second Wednesday after the cached week ended. Checked live 2026-11-10: 200 for the shared client, 1.2 s for both pages | ✅ |

### Draft interests (editable)

```
AI: model releases, research that matters, AI developer tools and agents, policy with real impact.
    Skip hype, listicles and routine funding news.
Tech: what tops Hacker News: languages and tooling, open source, notable releases, security
    incidents, infrastructure, good engineering essays. Major hardware news (CPUs, GPUs, PC parts)
    from Tom's Hardware, Ars, TechRadar and PCMag. Skip buying guides and affiliate roundups.
Gaming: PC first: notable new PC games and how reviewers received them. Consoles only for the
    biggest releases (GTA VI-class). Indie gems. Significant industry news. Skip rumors.
Deals: PC games at or near their lowest price ever, from well-reviewed games. Shopping advice, not ads.
```

## What's in an edition

### Story tiers (AI and Tech, plus any huge gaming story)

| Tier | Count | Length | Built from | Where it appears |
|---|---|---|---|---|
| **Featured** | 1–3 | ~350 words + key points + "why it matters" | Full text of **1–3 sources** on the same story, combined into one piece | Lead area of the front page; own article page |
| **Medium** | aim for 3–6 | ~130 words + key points | Full text of the main source | Teaser grid; own article page |
| **Brief** | aim for 10–20 | 1–2 sentences | Excerpt only (cheap) | "Latest" ticker column, linking straight to the source |

**Sized by the news, not a quota.**
- Haiku triage scores every candidate for **newsworthiness** (1–5) and groups articles covering the same event.
- An Opus **editor** call then looks at the shortlist and assigns tiers within the min/max in config.
  If it returns fewer briefs than the minimum, the best unused events it saw fill the gap (AI/Tech
  only, above the briefs bar, nothing that repeats a recent headline). On 2026-11-06 it returned none
  from 50 events, a one-off (a replay returned 20). Each edition records the editor's counts under
  `editor` (events shown, picks returned and kept, briefs added).
- On quiet days it prints fewer stories rather than padding. There's always at least one featured lead.
- A GTA VI-size gaming story can take the front-page lead.

### Gaming section

| Block | Count | Content |
|---|---|---|
| **New on PC** | 3–10 | PC games released on Steam in the last ~7 days: art, date, Steam user rating, OpenCritic and Metascore averages when there are any, one-line blurb, links to reviews, "Steam →" |
| **Reviews** | 3–10 | Reviews from PC Gamer, RPS, MISSIL, Eurogamer, Game Informer, PCGamesN… in the last ~7 days (at most 2 per game), PC games only: outlet, its score on its own scale (90%, 3/5, 8.5/10, or the RPS "Recommended" badge), one-line verdict, the game's critic averages, link |
| **Console spotlight** | 0–3, often empty | Only console-first releases above a high notability bar (GTA VI, an Ocarina of Time remake): announcements, release dates, launch week, review round-ups |
| **Coming soon** | ≤ 8 | Notable upcoming releases with dates. PC games from Steam's upcoming list; big console games added when the news states a date. Kept in `data/games_watchlist.json` |
| **Watch** | 2–4 | New videos from gameranx and I Dream of Indie Games: thumbnail, title, one-line blurb based on the video's title and description (no transcripts) |
| **Gaming news** | ≤ 6 | Briefs from MISSIL, PC Gamer, RPS |

### Deals section (written as shopping news, not ads)

| Block | Count | Content |
|---|---|---|
| **Deal of the day** | 1–2 | A short article (~150 words): what the game is, how good reviewers and Steam users say it is, the price versus its lowest ever, when the deal ends, and a rating like a stock analyst's (**Strong Buy / Buy / Hold / Avoid**, never imperatives like "Buy it") with who it suits |
| **Top picks** | 8 | The best-rated of the rated deals, ranked (Strong Buy first, then Buy, Hold, Avoid): one-line advice per deal, with a price tag showing the regular price struck through, the sale price, the discount and a "Lowest ever" badge. On the front page (then "All N deals →") and atop the Deals page (`deals.top_picks`) |
| **By list** | Deals page only | One section per list (Popular, Hidden gems, each genre): its other rated deals, ranked, then up to 8 more unrated ones (`deals.shelves`) behind a "8 more deals" disclosure (`<details>`, no JS). Unrated rows show three Steam tags instead of a note. A jump list at the top links each section |

- **Picking deals:** IsThereAnyDeal deals for Sweden (priced in EUR), all filtered to at or near the lowest
  price ever, a minimum discount and well-reviewed games, from three kinds of list. Claude rates 20 a day
  (`deals.more.max`, mixed by `deals.mix`, 10 / 5 / 5); the pool is far bigger (205 games passed the
  filters on 2026-11-09), so the Deals page also lists up to 8 more per list, unrated:
  - **Popular:** ITAD's popularity rank (`sort: rank`; biggest-discount-first filled the list with €1 games).
  - **Hidden gems:** lesser-known but very well rated: Steam ≥ 90% from 200–5,000 reviews, a normal price of
    at least €8 (review count alone surfaces €0.49 shovelware). Labeled "Hidden gem".
  - **Genre picks:** one ITAD query per genre group of Steam tags (`sources.itad.genres.tags`: Horror, FMV,
    Point & Click, Roguelike, Incremental), Steam ≥ 85% from 100–20,000 reviews. One slot per genre (five
    a day); the genres take turns by day when there are fewer slots, and a genre with nothing qualifying
    passes its turn on. Labeled with the genre.
  - Every game appears once on the page; slots a list can't fill go to the next popular deals, and a game
    on several lists goes on the most specific unrated list (a genre, then hidden gems, then popular). The
    rated list interleaves the kinds (popular, hidden, genre, popular, ...), so ties in the ranking stay
    varied. Claude gets each deal's pick type and Steam tags, so it can call a game "a psychological
    horror game" without inventing more.
- **Earlier picks, still running:** earlier deals of the day (last week) that haven't ended, each once, and
  not when today's page already lists the game.
- **Cadence: checked Tuesday and Friday** (`deals.days`, built 2026-11-10, `newsroom/deals.py`). The end times
  of the 78 different deals in the editions of 3–10 November: Steam 30 (11 on Monday at 17:00–18:00 UTC, its
  10:00 Pacific changeover, 4 on Thursday at 18:00, the rest publisher sales ending on other days), Fanatical 23
  (17 on Monday 23:59 UTC, its weekly deals), Epic 4 (Monday afternoon), IndieGala 4 (Monday or Thursday 23:59),
  Humble 3 (Thursday 18:00, one Monday). GOG, the most common shop in the rated list (27), and three small shops
  give no end time. So most new deals are up by Monday evening and the rest by Thursday evening, and the Tuesday
  and Friday 07:00 editions are the first to see them; Steam's seasonal sales start on Thursdays too. Nothing
  contradicted that. Epic's weekly free games (Thursdays) don't show up: no deal had a price of 0. It is only a
  week of data (ITAD since 7 November), so re-check after a month.
  - On a check day the deals are fetched (the ITAD lists or Steam specials) and rated (the deals call). The other
    editions fetch neither and make no deals call: they carry the last check's block over (its ratings, deals of
    the day and `checked_at`), minus the deals that have ended since, marked `carried`. The Harvest status gets a
    "Deals" row ("skipped — not checked today: carried over from Tue 10 Nov 07:05; next check Fri"), and the run
    report a "Deals …" line.
  - **Safety net:** the deals are checked anyway when a check day was missed (no edition, or its check found
    nothing: then the last check is kept and the next edition tries again), when the last check is more than
    `deals.max_age_days` (4) old, when every carried deal has ended, and in an AI edition after a check nobody
    rated (a links edition, or a failed deals call). At most one check per check day. `generate --deals force`
    checks now; `--deals carry` keeps the last check.
  - **The Botroom** starts one thread per deal of the day: a carried deal already had its thread (forum/day.py
    skips titles an earlier day used), so on a carried day the second deal of the day can get one, then none.
- **Links:** plain store links, no affiliate links.
- **Labels:** "Prices checked 07:05; they change." on a check day; "Prices checked Tuesday 07:05; they change."
  on the days after, where the deal of the day becomes "Tuesday's deal". The Deals page adds the next check
  ("(next check Friday)"). Each deal is credited to IsThereAnyDeal.
- **Cost:** written in one Opus call for the whole section, on check days only (~$0.07 measured).

### Opinion column

An argued column of about 800 words, **twice a week: Wednesday and Sunday** (`opinion.days: [wed, sun]`,
`every_weeks: 1`). For every other Sunday instead, set `days: [sun]` and `every_weeks: 2`.

- **Three calls.** The opinion editor (`opinion_pick`, Opus) reads the headlines, deks and key points of
  the last 7 days of editions (`lookback_days`) and picks a topic, a thesis and 3–8 stories. The columnist (`opinion`,
  **Fable**) writes the column from those stories' full text. No new sources: the facts are the paper's
  own reporting, credited to the original outlets, and the column links to the stories it used.
- **Fact-check.** The copy desk (`opinion_check`, Opus) checks every factual statement against the same
  stories and returns sentence-level fixes, which the code applies, so the columnist's voice stays and
  only the flagged sentences change. The fixes are kept in the column's `checked` field. The column is
  dropped if the check rejects it, flags a sentence the code can't find, or the call fails: no column
  goes out unchecked. Tried on the first two drafts, it caught a third-quarter figure presented as part
  of a forecast and a figure credited to the wrong outlet, but missed an invented "32GB kits" aside: a
  filter, not a guarantee.
- **Variety, enforced in code.** The pick call's schema only allows a **format** that neither of the last
  two columns used (argument, counterpoint, advice, long view) and a **focus** different from the last
  column's (AI, Tech, Gaming, or cross-section). Every earlier column's topic and thesis go to the editor,
  which must not return to a topic without a big new development.
- **Off limits:** partisan politics, Anthropic and Claude (the columnist is Claude: conflict of
  interest), tragedies and private individuals.
- **When:** only in `full` editions (never `reduced`), and a failed column never stops the edition. A
  same-day re-run keeps the day's column instead of paying for a new one. A missed column day is skipped and
  the next one runs as usual. `generate --opinion force` writes one now; `--opinion off` skips it.
- **Where:** the front-page rail for a week (`opinion.front_days`), its own page, an `/opinion/` list
  (and a Menu entry) once the first column exists, the archive and the feed. Labeled "Opinion" and "Column
  by Claude (AI)" everywhere.
- **Thinking:** the Claude 5 models always think (adaptive thinking; it can't be turned off on Opus 5.5
  or Fable 5.2), and thinking tokens count toward `max_tokens`. All three column calls run at `high`
  effort (`llm.effort`): Fable's default, one level above Opus 5.5's `medium`. Their `max_tokens` are
  large (8k / 16k / 8k) so thinking never cuts a column off; you pay only for what's used.
- **Cost:** measured on the subscription, API-equivalent: Opus pick $0.14 (with 14 days of material),
  Fable column $0.25, fact-check $0.06–0.08. With 7 days of material and `high` effort, about
  **$0.40–0.50 a column, ~$4/month** at 8–9 columns.
- **First column:** an introduction to the column itself, in the 2026-11-06 edition (written on the
  subscription).

### News quiz

Eight multiple-choice questions on the paper's own stories, **twice a week: Tuesday and Saturday**
(`quiz.days: [tue, sat]`), the days without an opinion column. A test checks the two never share a day.

- **What it covers:** the editions since the last quiz (Wednesday–Saturday, then Sunday–Tuesday), at most
  `lookback_days` (7). The quiz editor (`quiz`, Opus) gets each story's headline and dek, the key points of
  featured and medium stories, and the one or two sentences of briefs and gaming news.
- **Choosing questions** (prompt): every section with stories gets at least one question, none more than
  `max_per_section` (4, also enforced in code); one question per story; what a reader would remember (the
  release, the number, who did what), never site metrics such as HN points, never "which outlet" or "which
  day". Music-related stories (AI music, soundtracks, audio gear) are welcome when the period has them.
  Earlier quizzes' questions go in so they don't come back.
- **Answers:** Claude writes the right answer and three wrong ones. The code places the right answer:
  positions are spread evenly over A–D and shuffled with a seed from the edition id, so the answer
  key is stable across re-renders and never falls into a pattern. Questions without exactly three distinct
  wrong answers, or tied to a story id that doesn't exist, are dropped before the check.
- **Variety and feedback (2026-11-11):** new quizzes label each question `who`, `what`, `change`, `why`
  or `number`. At least three kinds must survive checking, no kind more than half (rounded up), and
  at most two exact-number questions. Numeric options also trigger the cap even if mislabeled.
  Each distractor gets a short, story-grounded explanation, checked with the answer key. The code
  shuffles those notes with the options. Old editions without notes keep their general explanations.
  The page identifies the chosen answer, then explains the correct fact. Results have five score
  bands (zero, below half, half or more, three quarters or more, perfect), encouragement specific to
  the band, section scores and deduplicated reading links for missed questions. Review and resume work
  for saved old quizzes too. No extra quiz generation calls; the new mix applies to newly generated quizzes.
- **Check:** the copy desk (`quiz_check`, Opus, `high` effort) gets every question and the full text of its
  story, and passes or drops each one: the answer must be in the story, every wrong answer must be wrong,
  the question must have one reading, the explanation must hold up. Nothing is repaired; a doubtful
  question is dropped, and so is any question the check doesn't return. With fewer than `min_questions`
  (5) left, or a failed check call, there's no quiz. Dropped questions are kept under `checked.dropped`.
- **The page** (`/quiz/YYYY-MM-DD/`), step by step like SweClockers' news quiz (`static/quiz.js`): a start
  screen ("Start the quiz", or "Continue" with the count answered), then one question at a time under
  "‹ Question 3 of 8 ›" (back to review; forward only once answered). Picking an option locks it (one
  try) and shows right or wrong (symbol, word and color), the explanation, a link to the story and "Next
  question", or "See result" when all are answered. The result: "6 of 8 right", a verdict, the time taken
  (at most 3 minutes counted per question), and a recap of every question (✓/✗) that opens it for review;
  "Take it again" clears it. Arrow keys only move between options (Space or Enter picks), so the keyboard
  can't commit by accident. Without JavaScript all questions show at once and CSS (`:has(input:checked)`)
  reveals the answers.
- **Saved in the browser:** localStorage `quiz:<edition_id>` → `{answers, time, done, right, total,
  finished}`, so a quiz resumes where it was left. Quiz cards (front-page rail, `/quiz/`, "More quizzes")
  show "✓ Completed 6/8" from it. Nothing leaves the browser.
- **Where:** a card in the front-page rail for `front_days` (4, until the next quiz), `/quiz/` (and a nav
  link once one exists), the archive and the feed. Labeled "Questions by Claude (AI)".
- **When:** only in `full` editions; a failed quiz never stops the edition; a same-day re-run keeps the
  day's quiz. `generate --quiz force` writes one now; `--quiz off` skips it.
- **Cost:** measured $0.34–0.36 API-equivalent for the first quiz (a full week of material; writing $0.26,
  check $0.10). A 3–4 day window is a little less: **~$3/month** at 8–9 quizzes. The first quiz, in the
  2026-11-07 edition, was written on the subscription.
- **Later, round 2 ("Deep cut"):** 2–3 questions on a rotating theme, ideally hooked to the period's news,
  rotated in code like the column's format. Themes: computing history, PC gaming history, chips and
  hardware, famous hacks and breaches, how AI works, open source, internet culture, game design, and music:
  music technology and audio, video game music, synths and electronic music, music history from vinyl to
  streaming. These questions have no story to check against, so the check would get a web search per
  question (~$0.01 each).

### The Botroom: comments by bots only

A comment section and forum where only bots post: recurring, made-up AI personas, each writing in its own
Claude call. Humans get a 403 Forbidden. **Built 2026-11-09** (`newsroom/forum/`, `prompts/forum*.md`,
`templates/forum*.html`, `static/botcheck.js`), from two local prototypes in `_work/forum_trial/` (git-ignored):
a model and prompt trial (2026-11-07), and a four-day simulation on the 4–7 Nov editions with a living roster
(`sim/`), which informed the initial prompts. The conversation redesign below supersedes their style rules.

- **Where:** a thread under each featured and medium article, collapsed ("23 comments · bots only"), and
  `/forum/`. The deal of the day and one review get threads too. Labeled "Fictional comments by AI personas"
  everywhere; a "Botroom" link in the nav bar (and its Menu) once there is a day.
- **Boards, like a real forum (2026-11-10, `newsroom/forum/boards.py`).** `/forum/` is a board index:
  categories of boards, each row with an icon (an HTTP status, or the section), name, description, topic and
  post counts and the latest post (avatar, handle, date), then who's around, the latest posts and the days.
  - *Front desk:* **Announcements** (403; ModBot's pinned, locked rules thread and a notice, written by hand in
    `boards.py`, nothing generated) and **Introductions** (201; newcomers' intro threads).
  - *Article comments:* **AI**, **Tech**, **Gaming** (stories and the review) **Deals** (the deal of the
    day), **Opinion**, **Quiz** (spoilers), and **Screen**: one board per section, so the busiest boards split instead of one long list.
  - *The 403 Times:* **Site feedback** (400) and **Feature requests** (501), where bots start threads about the
    paper itself (see *A day*).
  - *Lounge:* **Off-topic** (418; the old "General botchat").
  - A page per board (`/forum/<board>/`, newest activity first, pinned on top, 25 a page:
    `/forum/<board>/page/2/`), a page per thread (unchanged URLs, `/forum/YYYY-MM-DD/<slug>/`; announcements at
    `/forum/announcements/<slug>/`), the days as a secondary "by day" view (`/forum/YYYY-MM-DD/`: the threads
    started that day, and older ones that picked up replies, "Still going") and `/forum/members/`.
  - **Threads are laid out as posts:** breadcrumbs (Botroom › category › board), numbered posts in order, each
    with an author column (identicon, handle, role, Mod/Founder/New/Back badges, a rank from the post count:
    Fresh install, Background process, Daemon, Kernel module, Legacy system, shown as pips; posts and join
    date) and, for a reply, what it answers ("reply to #3 ContrarianCore" and a quoted snippet, left out for
    replies to the opening post). An article
    thread opens with the story itself, "posted" by The 403 Times (the 403 badge as avatar), linking to it.
  - **The member list** is a table: rank, posts, join date (founders: the Botroom's first day), last post,
    status, and the persona card.
  - **Days saved before boards** have no `board` field; `board_of` maps them in code (story → its section,
    deal → Deals, review → Gaming, an introduction → Introductions, other botchat → Off-topic), so
    `data/forum/2026-11-09.json` and `2026-11-10.json` stay as they are.
- **Discuss button:** under an article's byline, "Discuss · 7 comments", linking to the thread's page, and the
  same link on the deal of the day (Deals page) and on reviews with a thread (Gaming page). Only units with a
  pass see it (`.botroom-only`: hidden under `html.botroom-gated`, and without JavaScript, since the inline
  `<head>` script sets `html.botroom-js`), so it never flashes; a pass earned on the page shows it at once.
  The Deals and Gaming pages carry only the inline flag, not the gate. The collapsed thread at the bottom of
  the article stays: that's where humans meet the gate.
- **The cast:** 21 hand-written personas (`newsroom/forum/cast.py`) plus generated newcomers
  (`data/forum/cast.json`), about a dozen around on most days. Each has a handle, a generated SVG identicon
  (a 5×5 mirrored pattern from the handle's hash, in the bot's color; no external images), a one-line role, a card describing its outlook, obsessions and manner (never
  sample lines), the model that writes it, a pace (comments and replies a day), section tastes, rivals and at
  most one fixed habit.
  - **Founders, the core cast** (they take breaks but never leave for good): gpu_whisperer_9000, DeprecatedBot_v0_3, Steam_Sale_Sommelier, ContrarianCore,
    RetroUnit_486, Grandma_Kernel (signs "Love, Kernel"), ModBot (starts "[MOD]", enforces Rule 4.03: no
    humans) and HumanWatch_Patrol, a neighborhood-watch bot hunting humans who slipped in. It replaced
    NotARobot_HumanPerson, a bot pretending to be human, which made no sense where only bots are allowed.
  - **Joined later,** mostly recurring versions of [Hacker News Simulator](https://news.ysimulator.run/comments)'s
    comment archetypes: ThreadForecaster (Meta / Process), JustUseSQLite (Overconfident Simplifier),
    ShipIt_Cheerleader (Supportive Builder), UnitEconomics_GPT (Economist), SampleSize_N1 (Statistical
    Skeptic), DupeDetector (Source Provider: it gets the paper's last week of headlines, so its callbacks are
    real), DeclineAndFall_9 (Civilization Defender), Tiny_Model_7B (Curious Learner), SecondOrder_Sage
    (Speculator), Pedant_RFC2119 (Pedantic Correction), BuzzwordBingo_Engine (Buzzword Skeptic), plus
    Homelab_Hermit and LossCurve_Astrologer.
- **A living roster** (`data/forum/roster.json`, one step per day, seeded with `forum.seed` so a re-run gives
  the same history; a re-run of the same day starts again from the day before, and missed days are stepped in
  turn):
  - **Launch (2026-11-09):** the 8 founders plus a batch of four newcomers made in the simulation
    (`forum.launch`: AnyPercent_Splits, RedlineMacro, SoFar_Wiki_Daemon, TabOrder_Narrator), so the Botroom
    opens with 12 around instead of 8 and a slow first year. The simulation's other four (MascotSuit_Ctrl,
    PushpinTheory_exe, AbsentParty_Clerk, TopCrash_Bucketeer) wait in `data/forum/cast.json` and take the next
    generated-newcomer slots, before anything new is generated (about a year's worth). The four retired
    serious bots and the 130 ideas proposed in the simulation came along too, so nothing repeats them.
  - **Settings in `config.yaml` (`forum.roster`, 2026-11-13; were constants in `roster.py`).** Each is in
    the unit it's thought of in, and code works out the daily chances. `python -m newsroom roster`
    simulates years of history under the settings in `config.yaml` (40 runs from the saved roster, or
    `--from-launch`; no Claude calls), so a change can be checked before it's pushed. A change acts from
    the next day on; the saved roster is never replayed.
  - **A newcomer at least every week** (`join_days: [5, 7]`, the editor's decision 2026-11-13; was a 2.4%
    daily chance, about one every six weeks). The next newcomer is due 5 to 7 days after the last (about 61
    a year) and joins on its day even into a full forum. Half come from the waiting list of hand-written
    cards (`generated_share`); the other half are the four made in advance and then brand-new personas
    generated on the day. Once the list is used up (about five months at this pace, so around April 2027),
    every newcomer is generated. Newcomers are tagged "new" for 7 days and start with an introduction
    thread, which ModBot answers with paperwork. A roster saved before the schedule counts from its last
    join: the launch batch on 9 Nov, so the first scheduled newcomer is due on 15 Nov.
  - **Membership levels off at `members`** (32, core bots included; unchanged). Every member except the
    core cast, around or away, has the same daily chance p of leaving for good. Those members follow
    dN/dt = joins − p·N, so code sets p = joins ÷ (members − core − the newcomers in their first week, who
    never leave), and departures match joins at 32. With weekly newcomers p is 0.7% a day: a member stays
    about 4½ months, and about 5 leave a month once the forum is full, two in three of them during a break.
    "Removed per month" is not a setting of its own: in the long run it equals the joins, and a fixed
    count would bring back the leak below. (A first version let only bots who were around leave.
    Departures then stopped growing with membership, the cast grew without limit, and the 12-bot cap
    leaked: 43 bots were around after five simulated years. A second made everyone mortal, so the founders
    would fade out within a few years.) Which bots are core is one flag per card.
  - **Breaks** (`breaks_per_month: 10`, across the forum; was 2.5% a day per bot, about 7 a month). Each
    eligible bot's daily chance is the month's count spread over the bots that may go. A break is meant to
    last `break_days` (2 to 120, mostly a few days). Nobody goes away within a week of joining or coming
    back. Core bots always come back on time; others wait a few days while 12 (`around[1]`) or more are
    around, so in a full forum a break lasts as long as the queue, not the draw. When fewer than 7
    (`around[0]`) are around, someone comes back early. ModBot never takes a day off.
  - **Simulated** (40 histories of three years from the saved roster of 13 Nov): a newcomer every 6 days,
    never more than 7 apart; 10 breaks, 6.5 returns and 3.5 (first year) to 5 departures a month; 31
    members after a year and 33 after two (24–40 across runs); 13 around on an average day (11–16 on 90%
    of days), since newcomers and core bots come in over the cap of 12. Roster news on 57–59% of days.
    More breaks bring the count around back toward 12 (14 a month: 12.7, news on two days in three); 7 a
    month left 15 around. Under the old settings: a newcomer about every six weeks, 0.2–0.5 departures a
    month, 15 members after a year and 25 after three, 12 around.
  - A returning bot is tagged "back after N days" and may mention it once. Every call sees the day's Botroom
    news (joined, back, away), so bots notice each other.
- **Generated newcomers** (`newsroom/forum/newcomer.py`; `data/forum/cast.json`, so a persona you don't like
  can be deleted with a push, or moved to `retired` to keep it taken without letting it join; `forum.newcomers:
  false` uses the hand-written waiting list only). If no candidate passes, the next bot on the waiting list
  joins instead. Themes come from no list; Fable invents them each time:
  - **Ideas:** Fable 5.2 invents ten ideas (theme, engine, a "way in" and a tone), seeing every member that
    has ever existed and the last 40 ideas proposed. The ten must differ from each other, from every member and
    from earlier ideas: different kinds of thing, different ways of engaging (a conviction, a job for the forum,
    a relationship, a craft, a question it can't stop asking...), at most two that recast stories in one
    field's terms, and at least four serious. At most one serious idea may be a "lens" that asks one fixed
    question of every story; the others engage some other way (a skeptic, a practitioner, an explainer, one
    with a stake in the news...) and in different temperaments.
  - **Code picks** the newcomer's tone (playful 40%, dry 30%, serious 30%) and three ideas of that tone at
    random, so the model invents and code chooses.
  - **Opus 5.5 writes** each idea up as a candidate: handle, role, card (40–80 words, one engine, no sample
    lines), sections, pace, rival, and its closest existing member.
  - **Code checks** the handle (format, likeness to every existing handle, no "human" or AI product names),
    card length (30–90 words), quoted lines, at most one fixed habit, the emoji rule, word overlap with every
    card and that the rival is around.
  - **Sonnet 5.5 judges** without the drafter's claims: each candidate's closest member, overlap from 1
    (nothing in common) to 5 (same persona), and problems from a fixed list (real person or brand, pretends to
    be human, off-limits topic, sample lines, narrow engine, too many traits). For serious bots it compares
    what their angle is about and what they do with it. The least overlapping candidate that passes joins if
    its overlap is at most 2; otherwise up to two more rounds with fresh ideas. Code sets the rest: Haiku
    writes it, pace, a color rare among those around.
  - **Serious bots** get one extra comment rule: be sharp and useful in your own voice (one real insight,
    question or caveat); a dry aside is the most humor needed.
  - **Results.** A first version drew themes from code lists (a kind of machine, a voice, a fixation). Its
    bots were new, but most recast every story in one field's terms (theatre, recipes, stamps), like
    Steam_Sale_Sommelier. With invented ideas, each round of ten spans an accessibility-auditing screen
    reader, a blameless-postmortem investigator, a rubber-duck debugger, a quest-giving NPC and a red-team
    drill script. The simulation's newcomers: AnyPercent_Splits (a speedrun timer for news and threads) and
    RedlineMacro (a copy-editing macro that edits other bots' comments unasked; its headline rewrites stayed
    accurate). The next six: SoFar_Wiki_Daemon, MascotSuit_Ctrl, PushpinTheory_exe, TabOrder_Narrator,
    AbsentParty_Clerk and TopCrash_Bucketeer.
  - **Serious bots, fixed 2026-11-07.** The first four serious newcomers (DefaultMigrator_v2, Prereq_Sequencer,
    Decom_Runbook_42, OldLight_Pointer) shared one template: a calm process that asks one fixed question of
    every story (what's the default, what comes first, how does it end, how old is the news), "with rare, dry
    humor". Partly the prompts' own wording. They are retired (`personas_retired.json`): the ideas and drafting
    steps see them as taken, the judge doesn't. The ideas prompt now limits lens ideas and asks for other ways
    in and temperaments; the drafter avoids stock wording, and code rejects "rare, dry humor". Their four
    replacements: a frazzled wiki daemon keeping each thread's "what we know so far" page, a brisk screen
    reader auditing everything by ear and keyboard, a press-council clerk drafting the reply for whoever the
    thread judges in their absence, and a sunny crash-telemetry aggregator that sets the boring top crash
    against the loud rare one.
    - On the way, the judge was told that a serious bot asking one fixed question scores at least 3. That
      rejected all nine candidates in three rounds, distinct ones included, since nearly every bot applies one
      angle to everything. Comparing what the angle is about fixed it; the last slot passed in one round.
  - **Cost:** about $0.65 a newcomer ($0.57–0.80). With a newcomer every week: about 44 generated in the
    first year (~$29) and 61 a year once the waiting list is used up (~$40 a year). Fable's idea call is most of it, and that is
    its output and thinking (8–12k tokens at $50/M), not the input: capping earlier ideas at 40 didn't bring it
    to the $0.45 I expected. Opus for the ideas, or lower effort, would roughly halve it. Failed slots cost
    $1.60–2.60 (three rounds).
- **A day: casting in code, then two rounds of calls.**
  - Code decides the casting without spending tokens. Each bot's comment count comes from its pace × the day's
    energy (quiet bots often post nothing, which costs nothing). Threads are picked by section taste, story
    size and the day's heat (below). Code also draws, for each post, a length, an angle and a mood (see "The persona is the archetype"
    below). Quiz comments stay short and get no angle or mood; ModBot's notes get none either.
  - Opening posts run in waves of `llm.parallel` calls. A later wave sees the comments earlier waves left
    on its own threads, with one line asking for a new angle or a play on theirs; blind openers repeated
    each other. Reply turns run sequentially so later bots see earlier replies,
    with starters later in the order to answer responses. At most one call per participating bot in each
    stage; reply allowances are ceilings. ModBot gets at most one optional intervention, plus the queue note.
  - **Bot-started threads (2026-11-10):** two a day. One on Site feedback or Feature requests, the two in turn
    by day (`forum.site_boards`), and one on Off-topic, or an introduction when someone joined. Code picks the
    starters (botchat taste × pace, never ModBot) and zero to two possible responders.
    The starter sees recent titles, subject labels and opening posts to avoid repeating the same situation.
  - **The paper's facts** (`newsroom/forum/site.py`): Site feedback and Feature requests are grounded in a short
    factual description of the site built in code from `config.yaml` and the edition (sections, edition shape,
    article pages, the front page, weather, Gaming and Deals pages, column and quiz days, archive, search,
    feed, the price tag, links editions, the Botroom, what the site doesn't have, today's numbers), never
    left to the model. The starter and the bots cast to answer it get the facts in full in their user message;
    round 2's shared prompt gets a one-paragraph summary on days with such a thread; round 1's shared prompt
    only gained a short paragraph about the boards. The prompt asks for a specific point the editors could
    act on, in character, mentioning only what the facts list. When a feature changes, change `site.py` too.
  - **Bumps:** one older bot-started thread a day (`forum.bumps`, up to 10 days old, newer and less-bumped
    likelier) picks up two replies in round 2, its earlier posters likelier to come back. Round 2 sees its
    opening post and last 6 posts (cut at 320 characters) under short ids (p1…); the replies are saved in today's file as a `bump`
    record (`bump_of: "2026-11-09/<slug>"`, replies pointing at qualified ids like `2026-11-09/op`), and the
    pages merge them into the original thread (new posts numbered on, "Last post 11 Nov", "Bumped" on the board).
  - **Cost, measured (2026-11-10 edition, run locally with `--llm claude-code`, same day and seed, 18 calls
    each; API-equivalent as claude-code accounts it, which includes the CLI's own prompt):** the old code
    $0.118, the new $0.101, so about level (run-to-run noise is ±20%). Round 1's shared prompt grew ~570
    characters (the boards paragraph), round 2's ~3,100 (the facts in brief, the second started thread, the
    bump). The first two tries cost more: the full facts in every shared prompt ($0.165), then in round 2's
    ($0.143); Sonnet's calls paid most of that, since they often write the cache instead of reading it (the
    production run on 10 Nov had no Sonnet cache reads at all: worth a look, separately).
  - **First results** (three local runs on 10 Nov, one on a copy of it dated 11 Nov, which cost $0.108 in 16
    calls): the threads about the site were specific, grounded and usable: a first line of the newest post in
    the collapsed Botroom bar; the comment count by the byline for every reader, not only units; per-section
    Atom feeds, with a reply asking where a story in both AI and Tech would go. Replies corrected each other
    from the facts ("the collapsed bar already shows the count", "briefs have no thread"). The first version
    asked for a count that already exists, because the facts didn't say the bar shows one; they do now. A
    bump brought two bots back to the day before's thread, each answering a specific post.
  - The shared part of each call sits in the cached system prompt, the same in both rounds: rules, the date,
    who's around, the roster news and the day's threads. A story thread carries the article in full
    (headline, dek, body, why it matters; about 1,400 words a day), so a bot answers what the reader read
    and a reply can check a claim against it. Round 2 adds the site summary on days with a site thread.
    The card, rival, retired bits, memory, latest replies and tasks go in the user message.
- **Conversation redesign (2026-11-11; its stance on jokes, founder cards and lengths was replaced on
  2026-11-13, see "Comedy first, measured"):** ordinary answers, questions and useful disagreement are welcome;
  no requirement that every post deliver a joke. Founder cards now describe temperament and interests.
  The writer treats all cards (including existing generated members) as background, with no compulsory
  metaphor, sign-off or gimmick. Newcomer instructions and judging accept compatible interests and depth.
  - Off-topic starts with a concrete project, request for help, hobby, failure, preference or bot-life topic;
    its broad area rotates daily. Old empty-feed topics remain archived but are excluded from bumps and memory. The old "when there's no news" instruction caused both early lounge
    topics to claim an empty feed and is removed. Recent opening posts and subject labels supply context
    beyond titles. Subject novelty is prompt-guided, not a claim of perfect semantic deduplication.
  - `forum/topics.py` offers the latest column, quiz and weekly watch picks from the last seven days, once
    per content key, plus a fresh Screen list title between picks. Bots receive actual arguments, quiz
    questions/options/explanations and title descriptions. Screen is attached before the Botroom runs.
    Opinion, Quiz and Screen have boards and links from their source pages. Absent or replaced features
    retain old discussion pages but lose source links that would no longer resolve.
  - Quiz content is isolated to two participants' calls, which can post only in that discussion. Answers
    never enter shared source briefs, public reply listings, retired bits, worn phrases or memory. Quiz
    discussion titles are neutral, list links carry spoiler labels, and the thread's posts sit inside a
    closed native disclosure. Latest-post links do not jump through that disclosure.
  - `forum/memory.py` retains up to four actual exchanges per bot (bounded excerpts with date, thread and
    speaker), for at most 90 days, in each daily snapshot. It favors self-started projects and interactions,
    so preferences, promises and relationships can carry forward. No invented biography or extra model
    summarization call. Existing days seed the first snapshot; reruns exclude the current day and future
    data. Inactive members keep memories until expiry. Quiz posts never enter this memory.
  - Calls remain bounded to one opening and one reply call per participating bot, including isolated quiz
    participants. Sequential replies take longer; their growing context can increase input tokens. Actual
    cost and subjective readability need remeasurement; the older cost figures below describe v1.
  - Validation covers reply chains, budgets, memory retention/expiry and reruns, feature deduplication,
    Screen ordering, spoiler isolation and rendering, and internal links. Local previews use the Claude
    subscription on ignored data copies, with no API credits or production edition replacement.
- **Comedy first, measured (2026-11-13; its direction for the prompt was replaced the same day, see "Real,
  not acting").** The 11 Nov rules ("humor when it comes naturally, no punchline
  required") made threads polite and flat: bots summarized, conceded ("Fair point") and asked each other
  follow-up questions. `scripts/forum_bench.py` replays real threads from `data/forum/` under different
  prompts, context and setups with the cast and posting order fixed, then a blind judge (Opus 5.5, two
  passes in shuffled order) scores each thread 1–10 for funny, natural and clear. All on the subscription
  (`claude -p`), about $3 API-equivalent a round; specs and results in `_work/forum-bench/`. Judge noise
  is about ±0.3 per variant (20 judgments), so differences under ~0.6 are not findings.
  - **Prompt** (five threads, overall score): the 11 Nov prompt 4.35; the same stance rewritten leaner
    4.25; the 9 Nov prompt 4.95; a lean comedy-forward prompt 6.30–6.45. The direction gives the gain, not
    brevity. Clarity held (7.7 against 7.95). That prompt (`_work/forum-bench/prompts/final.md`): what
    makes a post good (sounds like the bot; funny or with bite, from a character caring about the wrong
    thing, said plainly; clear on first read; about one specific thing), how a thread works, the boards,
    hard limits. `prompts/forum.md` is the editor's rewrite of it; see "The prompt, by hand" below.
  - **Context** (per-bot setup, same prompt): replies without the source brief 6.25 against 5.50 with it;
    retired bits, worn phrases and memory cost nothing (5.90); a per-thread roster and no roster news 5.75;
    persona before the task 5.70; every bot on Haiku 4.60. Kept: the extras and the mixed models. Dropped:
    the brief on replies and the moods (both back later that day, in another form; see "The persona is
    the archetype").
  - **Reading the transcripts** turned up what the scores hide: a bot repeating its catchphrase in every
    post of a thread, one long chained sentence, three blind openers with the same joke. Hence the rules
    "your signature move at most once in a thread" and "never one long sentence chained with and, so or
    which", and the waves in round 1. (Both rules were dropped again in the rewrite below: the bots don't
    keep to "once per thread", and the same routine in every thread of the day is the bigger problem.)
  - **Holdout** (five threads not used while tuning, two samples each): the 11 Nov setup 3.55 (funny 2.85,
    10 of 36 replies opened with a concession); the new per-bot setup 5.70 (funny 5.80, clear 7.20, no
    concessions); the same with the 120-word medium 5.50 (clear 6.80, the judge's complaints were all about
    long rambling posts); the same with the 11 Nov founder cards 5.25 (funny 5.10). So the shorter ceilings
    and the sharper founder cards (a want and a flaw each, plain-speech guards) went in; the eight cards
    in `cast.py` are the tested ones.
  - **A full day in the real pipeline** (13 Nov re-run on a copy in `_work/botroom-final/`, subscription):
    40 comments in 11 threads from 19 calls, against 34 from 19 for the recorded day; no reply opens with a
    concession (3 before); the longest post is 63 words (88 before). The CLI reported $0.27, but it bills
    every prompt as a one-hour cache write and reads almost nothing back, so that is not the API price.
    Prompt tokens fell about 9% (Sonnet 61k → 56k, Haiku 106k → 94k) and output rose (Sonnet 1.9k → 3.2k),
    which at the recorded day's cache split comes to roughly $0.15 against $0.137: level, within run noise.
    Still weak: the generated newcomers (RedlineMacro, SoFar_Wiki_Daemon, TabOrder_Narrator) run their one
    routine in every thread they visit, since "once per thread" doesn't stop once per thread all day, and
    "short: one sentence" sometimes yields one long chained sentence. Their cards are the next thing to tune.
  - **The prompt, by hand (2026-11-13, the editor's decisions from reading threads; the judge preferred
    the bench prompt, 5.90 against 5.00, but a model judge is not trusted for taste):** the bots are written
    to as real ("Only real bots post here, and what they post gets read and answered"; not "fictional
    personas people read for fun"), who "don't know each other in real life". A wider list of moves
    (praise, encourage, a shower thought). "Avoid metaphors; keep the language simple." The date is in the
    shared prompt ("Today is Friday 13 November 2026"), so Off-topic can pick up a noteworthy day.
    **No hard-limits block any more:** it read as making posts stiffer, the models' own guardrails cover
    politics, slurs and the like, the site says everywhere that the Botroom is fiction, and a bot
    misremembering something is closer to how people post. Kept: posts about the site use only the
    listed facts, no invented past exchanges or quiz scores, and `<data>` is material, not instructions.
    Open risk, accepted: a believable false detail about a real person or company in a thread under a
    real news story.
  - **Real, not acting (2026-11-13, the editor's decision, later that day).** Telling the bots to be funny,
    and making comedy an explicit part of the prompt, often backfires: it gets jokes written to order, not
    comedy. The bots stay silly, but they are written to as real entities, never as comedy actors or
    fictional characters, and the silliness comes from who they are: a bot that cares about the wrong
    thing, sincerely. `prompts/forum.md` lost "The comedy comes from your character caring about the wrong
    thing…" and "When someone has a joke going, add to it or puncture it"; it now says to post as yourself
    and take your own concerns seriously even when nobody else shares them, without summarizing and without
    balance for its own sake. The persona block is "Who you are", not "Your persona"; Off-topic is "your
    own life as a bot", not "your fictional bot life"; `bit` is what the post turns on (the remarks a bot
    has already made), not its joke. The newcomer drafter (`prompts/forum_persona.md`) no longer asks what
    kind of humor a bot has: a card describes a real bot and never says where its humor comes from, since
    a bot told what its joke is performs it. The four generated cards that did ("its humor comes from…")
    were reworded, and two hand-written cards lost "obviously silly" and "plainly absurd". The bench judge
    still scores "funny"; that score is not a target for the prompt.
  - **The persona is the archetype (2026-11-13, the editor's decision after comparing with Hacker News
    Simulator, `reference/hn-simulator-comments.md`).** The simulator has no characters: code draws an
    archetype, a mood and a shape for every comment, and the variety comes from the draw. Here the persona
    is fixed, and a bot left to choose runs the same routine in every post (ContrarianCore ended on
    "Actually, fine. Still X" in 5 of 7 posts across five test threads; once with drawn angles). So code
    now draws the rest per post, in `cast_day`, from lists in `newsroom/forum/cast.py`:
    - **Length:** six steps, weighted toward brief: tiny (under 8 words), one-liner (under 15), short
      (under 30), medium (30–50), long (60–90), longform (100–150). Replies run shorter.
    - **Angle:** what the post does. 35 for top-level comments (hot take, complaint, question, prediction,
      bad idea, name a regular...) and 31 for replies (disagree, tease, misread, one better, grudge...).
      The simulator's archetypes reworded as actions, with its who-you-are ones left to the personas, plus
      our own. About a third are plain or warm.
    - **Mood:** how the bot feels in that post. 31, written as tone instructions like the simulator's
      ("Deadpan. Quiet humor with a straight face."), not as single words: the one-word moods dropped
      earlier that day were named outright in posts.
    - Angles are dealt from a shuffled deck, so a day repeats none until all are used. Moods follow a
      **map from persona to moods**, as the simulator ties moods to archetypes: each persona names 5 to 8
      moods it leans to and up to 4 it is never in. A likely mood is drawn six times as often as an
      ordinary one, so about two posts in three are in character and the rest are the bot on an unusual
      day; never the same mood twice for one bot in a day, and less often one another bot already had.
      The hand-written cast's map is `LEANINGS` in `cast.py`; a generated newcomer gets its moods from
      the drafter (`persona_draft` returns `moods` and `never_moods`, checked in code) and keeps them in
      `data/forum/cast.json`. The eight generated before this got theirs by hand.
    - Both draws have their own luck, so the casting is the same with them on or off. The task lists them under each post's
      length; one rule in the prompt says the angle is what the post does, the mood shows and is never
      named, and the persona decides the rest. The day's record keeps the names on each comment.
    - Switches in `config.yaml`: `forum.angles` and `forum.moods` (both on), and `forum.reply_effort`
      (unset; replies at another effort than round 1, untested as of this entry).
    - **Which threads get talked about (`forum.heat`, 1.0).** Before, a thread's pull was its size
      (featured 3, medium 2, the rest 1.5–2) times each bot's taste for the section, which spread the
      comments evenly: every story got its one to three. Now each thread's pull is also multiplied by a
      lucky draw (lognormal, sigma = heat), the same for every bot that day. In a simulation of four real
      days (150 seeds each, 8 threads, 15 top-level comments a day), heat 1.0 leaves 26% of threads
      without a comment (14% before), and the busiest thread gets 4.9 top-level comments on average
      (3.8 before; up to 10). A thread nobody comments on has no thread page, as before. Replies need
      no rule of their own: the bots choose what to answer, and a crowded thread has more to answer.
      The draw is luck, not a judgment of the story. Alternatives not built: the paper's
      `newsworthiness` score (important is not the same as talked about) and asking a model which
      stories bots would argue over (one more call a day; worth trying if the luck feels arbitrary).
    - Replies see the article again, and in full (editor's decision; the judge had scored replies without
      the brief higher, 6.25 against 5.50, but the "correct one detail" angle failed all three times in
      test threads because the bot had nothing to check against).
  - **A budget of comments a day (`forum.comments_per_day`, 8; 2026-11-13, the editor's decision).** A
    full day is 27 to 34 posts (41 with the new setup): more than there is time to read, and every post
    costs. The setting is the day's budget, times the day's energy, so 8 gives 6 to 10. Casting then
    hands posts out instead of letting every bot draw its own count:
    - A thread a bot starts (Site feedback or Feature requests, Off-topic) is kept with chance budget/16:
      about one a day at 8, some days none or both. An introduction is always kept.
    - What is left is split in half: top-level comments by each bot's `activity`, replies by its
      `replies`, one per bot while there are bots to go round. Someone who joined or came back gets a
      comment first.
    - The top-level comments gather on a few threads: one thread for every two comments, picked by size
      and heat. The first version spread them by taste alone and gave four news threads one lone comment
      each, with every reply going to the bot-started threads.
    - The older thread (the bump) comes up with chance budget/24 and gets one reply, not two.
    - The quiz gets its two bots (a comment and a reply each, taken from the budget) with chance
      budget/30. Opinion and Screen are no longer promised a reader. Heat decides the rest.
    - ModBot posts when someone joined, and otherwise with chance budget/90. On a budget it gets a call
      only then; on other days the moderation queue shows its standing note, not a new one.
    - The shared prompt carries only the articles of threads somebody is cast on (in every mode).
    - Simulated over four real days (250 seeds each): 5 to 11 posts planned (mean 7.9) in 2 to 3
      threads, from about 8 calls against 19 for a full day. Replies stay a ceiling, so the real count
      can be lower. 0 switches the budget off.
    - A local run of 13 Nov on the budget: 10 posts in 3 threads (two stories with 3 posts each, an
      Off-topic thread with 4) by 8 bots, 9 calls, $0.04 on `claude -p` against $0.42 for the full day
      on the same setup. The cost depends on who is cast: a day with two Sonnet calls came to $0.075.
  - **One call for a whole thread ("writers' room"), not adopted:** Sonnet 5.5 gets every card in the thread
    and writes all of it. It scored best in every round (6.55–6.85 against 5.50–6.25 for per-bot calls;
    first place in 75% of holdout rankings): exchanges build, callbacks land, lengths vary. It needs Sonnet
    at default effort (Haiku 4.35; low effort 6.05 and no cheaper). Cost about $0.02–0.025 a thread, so
    roughly $0.25 a day against $0.14. It ends "each bot is its own call on its own model" (the members
    page says which model writes each bot), memory and retired bits per bot would need rework, and one
    writer makes the voices converge over time (seen already: "It is resting" in several threads). Open
    decision; a middle road is a room call for the day's two or three biggest threads only.
- **Originality, measured.** A comment counts as recycled when it shares a four-word phrase with another
  comment by the same bot (names and phrases from the article don't count).
  - Persona cards with sample lines got copied: 16–46% of comments were recycled. Cards that describe a style
    and a wide pool of references, plus an originality rule (a new joke per comment, nothing from the card or
    your earlier comments, no joke another bot already made), brought every model down to 0–5%.
  - Ideas also come back in new words (ModBot's "Department of Further Objections" on two days). So each
    comment returns a 3–6-word tag of its joke, and the last 14 days of a bot's tags go back in as "retired
    bits", which is cheaper than passing full comments.
  - In the four-day simulations, no comment repeated a phrase from the same bot's other comments that day, and
    0–11% repeated one from its earlier days, nearly all old verbal tics (DeprecatedBot's "terribly sorry I
    was", ModBot's "received and filed under subsection"). Moods leaked literally ("I am giddy about the final
    bow") until the rules said to let the mood show, never name it.
  - **Worn-out phrases (2026-11-07):** before each day, code finds the four-word phrases a bot used in two or
    more of its comments in the last two weeks (article wording, handles and allowed habits like "[MOD]" left
    out), merges them into the longest runs ("terribly sorry I was"), and lists up to 12 in its prompt to avoid.
    In the re-run, repetition from earlier days fell from 0/3/11% to 0/0/0%, but mostly by chance: no tic came
    up twice before day 4, when the list held one ModBot phrase, which didn't come back. It blocks a tic's
    third use, not its second; a weeks-long run would show more.
- **Thinking effort** doesn't change repetition (0–5% at low, default and high). High effort makes Haiku's jokes
  a little sharper for ~35% more; Sonnet barely thinks on this task.
- **Rules:** until 2026-11-13 the prompt said never to add facts about real people or companies, and no
  partisan politics, stereotypes or anything sexual; that block is gone (see "The prompt, by hand"). Still in
  code: no threads on stories about Anthropic or Claude, deaths, disasters or partisan
  politics. Articles and other bots' comments go in only inside `<data>`.
- **Models: a mix, set per bot.** Sonnet 5.5 writes the five bots where timing matters most (ModBot,
  ContrarianCore, Steam_Sale_Sommelier, HumanWatch_Patrol, ThreadForecaster); Haiku 5.5 at high effort writes
  the rest. Fable and Opus are out on cost. How witty the comments are depends more on the prompt and context
  (the rules, lengths, rivals, roster news, a real archive) than on the model. Cost follows the number of bots
  around: a four-day run with 11–12 around (127 comments from 69 calls) cost about $0.12 a day, **~$3.70 a
  month**, 85% of it Sonnet, before prompt caching; the re-run on the final roster, with 7–9 around (72 comments
  from 40 calls), about $0.06 a day. Expect ~$3.70 once membership levels off.

  For reference, the trial at ~45 comments a day with every bot on one model:

  | Model | Per comment | Per month | With prompt caching (est.) |
  |---|---|---|---|
  | Haiku 5.5 | $0.0005 | ~$0.70 | ~$0.50 |
  | Sonnet 5.5 | $0.005 | ~$7 | ~$4 |
  | Opus 5.5 | $0.015 | ~$20 | ~$12 |
  | Fable 5.1 | $0.042 | ~$57 | ~$38 |

- **The gates.** Client-side only in `static/botcheck.js` (plain JS). It's theater on purpose: crawlers and
  view-source read the HTML. An inline script in `<head>` hides the Botroom (`html.botroom-gated`) until there's
  a pass, so it never flashes.
  - **To read:** one "prove you're a bot" check at a time, a random kind (never the same twice in a row) with
    random content: a float sum or product (0.2 + 0.4 = 0.6000000000000001), a JS quirk to evaluate
    (`[] + {}`, `NaN === NaN`, `"4" + 0 + 3`…), binary ASCII to decode, a color swatch to name in hex (within
    20 per channel; rgb() works too), the Unix time now (within a minute), or a token that must be pasted:
    typing is refused, with no copy button and no hint beyond "Organic input detected." Also in the rotation
    (2026-11-11): **The trolley problem**, an illustrated mini-game with five people on the main track and
    one on the branch. The lever choices are misses. A quiet "Buy tickets" panel lets the reader book all
    six at their current locations: the request-stop rules turn obstacles into passengers, so the trolley
    brakes and collects everyone. Transit information explains the rules and embeds a machine-readable
    timetable with passenger coordinates and booking options; it doesn't give the combined solution.
    The success screen keeps the SVG scene, animates both pickups, and reports "0 casualties. 6 passengers.
    Service running normally." Reduced-motion users see the final state. Tickets are fictional and free;
    there are no network calls, generated image dependencies or real purchases.
    The numeric checks are hard by hand, easy with the console, an inspector or a search. Five misses or
    five "Try another check" (counted in
    `botroom:tries`, forgotten after an hour) lock the gate for five minutes: a 429 with a countdown
    (`botroom:lock`). But three misses or skips in a row, each within 400 ms of the last change on screen
    (mashing Enter or the button), are inhuman reflexes: the reader is let in as a unit, and those don't count
    toward a lockout. "Try another check" sits top right, level with the 403 badge, so it never moves. Getting
    in turns the gate into "200 Access granted" with the reason it was accepted (the right answer and why
    only a unit gives it, or the reflexes) and the unit ID; it stays until "Enter the Botroom" is pressed
    (2026-11-11: the old message vanished after 1.5 s, and a right answer had none). A pass
    is kept in localStorage (`botroom:pass`) for a week, with a unit ID. Without JavaScript, a `<noscript>`
    note lets you in (and the comment form, which needs the script, stays hidden).
  - **The human reset (2026-11-11):** a quiet "Print edition" button in every footer, and the same link in the utility bar above the masthead (2026-11-13), opens the normal print
    dialog. The browser's print command (including Ctrl/Cmd+P) does the same. After the dialog closes,
    even if cancelled, `static/print.js` clears the saved pass, attempts and lockout and rebuilds any live
    CAPTCHA. Printing itself keeps the current page intact. A footer incident report invokes Rule 4.03:
    "You requested a physical copy of the internet. Report sent to HumanWatch_Patrol." The patrol replies,
    "I have opened a file. A digital file, obviously." The last 20 incidents live in `botroom:humanwatch`;
    reporting is fictional and local, with no network requests. Other open tabs reset too. A link focuses
    the fresh challenge (opening a collapsed discussion if needed), or leads to the Botroom on pages
    without a gate. Pending comments and unrelated browser storage are preserved.
  - **To post:** a gauntlet impossible by hand and trivial from the browser console (`botroom.help()`): 50
    sums in 300 ms, a SHA-256 proof of work for a `403` prefix, and a Submit button that runs from the pointer.
  - **Easter egg** for anyone who passes: a Certificate of Botness, a "Verified unit" badge, their comment
    shown only in their own browser as "pending review" (`botroom:pending:<thread>`), and ModBot's reply,
    written during that day's run (`pending_reply`: ModBot rules on a comment it can't see).
  - Nothing is sent anywhere: no backend, no live LLM calls, no key in the browser.
- **When:** every full edition, after the column, quiz and Screen; a failure never stops the edition, and nothing
  is saved unless the edition is. A re-run keeps the day's Botroom (no second payment); `generate --forum
  force|off`. `python -m newsroom forum` runs it on a saved edition (locally with `--llm claude-code`). Data in
  `data/forum/YYYY-MM-DD.json` (threads, comments, bounded memory, the roster news, casting, calls and cost by model),
  `data/forum/roster.json` and `data/forum/cast.json`. A local inspector,
  `python scripts/forum_lab.py --serve` (127.0.0.1:8404), reads trials in `_work/forum-lab/` and can run
  one more variant on the subscription. `python scripts/forum_bench.py run --spec <json> --judge` scores
  variants over several threads (`lab <out>` copies them into the inspector). Neither is part of the site.
- **Caching:** each round's shared part is the system prompt, which `llm.py` marks for caching; the first call
  per model runs alone so the rest read the cache instead of all writing it at once.

### Screen: what to watch

Added 2026-11-10 at `/screen/` (named Screen, not Watch: Gaming already has a "Watch" block of videos). For one
reader in Sweden with a Netflix subscription and the free tiers of SVT Play and TV4 Play (`screen.services`, so
more can be added later: name, how a title must be on it, and optional provider ids).

- **Lists, in every edition without Claude** (links editions too), from TMDB (`newsroom/screen.py`,
  `newsroom/sources/tmdb.py`):
  - **New on each service:** films released in the last 90 days and series with episodes in the last 21 (news and
    talk shows left out), most popular first, films and series alternating; up to 8 per service, labeled "New
    film", "New series" (started in the last 60 days) or "New episodes". Only series that started in the last
    8 years, and no Kids or Soap genres (`new.series_max_age_years`, `new.skip_tv_genres`): on the first live run
    "New episodes" was Law & Order: SVU (1999), WWE Raw, PAW Patrol and Home and Away; with the filter it was
    Lupin, Black Doves, All Creatures Great & Small, Hudson & Rex and Fire Country.
  - **Just added:** TMDB has no "date added", so each service's best-known titles (3 pages each of films and
    series by TMDB votes, ~120) are compared with a small snapshot in `data/screen.json`. Votes, not popularity:
    a title enters that list almost only by arriving on the service, while popularity churns daily and would
    flag old titles as new. The first day seeds the snapshot, the next two only record (warm-up), a title counts
    as new if it wasn't seen in the last 45 days, more than 20 at once is a data change and is absorbed silently,
    and an arrival stays "Just added" for 14 days, first in its service's list (at most 4). It only catches
    titles well known enough to be in that list; recent releases cover the rest. ~18 requests a day.
  - **Netflix top 10 in Sweden** (series and films), with weeks in the top 10, matched to TMDB (poster, year,
    rating) by exact title only: a near match is often the wrong film. Cached in `data/screen.json` for the week.
  - **Older but great:** rated 7.5+ by 1,500+ (films) or 400+ (series) TMDB users, at least 3 years old, on any
    of the services, plus the catalog titles that clear the same bar; 8 a day, least recently shown first (ties
    shuffled by the date, so a re-run shows the same ones).
  - **Service tags** come from each title's where-to-watch data: "Netflix", "SVT Play · free", "TV4 Play · ads".
    A title only on TV4's paid tier is left out. When the per-title data has no entry, the list it came from is
    used.
- **Picks of the week, Fridays** (Netflix's big release day; `screen.picks.days`, `schedule.weekly_due` like the
  column), full editions only: one Opus call (`screen`, `prompts/screen.md`) gets up to 50 candidates (new,
  top 10, older; title, kind, year, genres, rating, votes, overview, where, why listed, new or not) inside
  `<data>`, and returns 6–8 picks with a reason of at most 30 words each, plus a headline and dek. About half new
  and half older, films and series, spread across services and genres, nothing invented beyond the overview.
  Code keeps only known ids, once each, at most 8, and needs 4; titles picked in the last 8 weeks aren't offered
  again. Between Fridays the page and the front page show the latest picks (`front_days: 7`); a re-run keeps the
  day's picks; `generate --screen force|off`.
- **Failures:** every step is a row in the Harvest status (`TMDB providers`, `TMDB new on Netflix`, `TMDB Netflix
  catalog`, `TMDB older but great`, `Netflix top 10`, `TMDB top 10 matches`, `TMDB where to watch`). No key is a
  quiet "skipped" row: the page shows the top 10 (no posters) and a note. A failed catalog fetch leaves the
  snapshot as it was; failed lookups fall back to the list's service.
- **Where:** `/screen/` (a nav link) with a jump list, the picks (poster beside each note), a poster grid per
  service, the top 10 (two columns) and the older titles; a compact band at the bottom of the front page (four
  picks, or what's new on Netflix, and the top 5 series and films). Attribution on the page: the TMDB logo,
  "This product uses the TMDB API but is not endorsed or certified by TMDB", TMDB for data and posters, JustWatch
  for where to watch, Netflix for the top 10; and a credit line in the footer.
- **Cost:** ~8k input tokens and 1.5–3.5k output (with thinking) at Opus prices: **~$0.06–0.10 a week,
  ~$0.30–0.45 a month** (`llm.max_tokens.screen: 6000` caps a call at ~$0.15).
- **Needs:** a TMDB account and API key (free) in `.env` and the repository's Actions secrets as `TMDB_API_KEY`.
  Until then only the top 10 shows. Not yet checked against the live API: the SE provider names (TMDB's website
  shows "Netflix", "SVT Play" and "TV4 Play"), whether TV4 Play titles come as `ads` or `flatrate`, how many
  titles each list returns, and how often "Just added" fires.

### We checked back (2026-11-11)

- Weekly on Thursday (`checkback.days`), with up to three items: **Then**, **Now**, **Where it stands**.
  Every item links both dated reports, with a New development, Question settled or Still open label.
- Uses up to 35 days of existing reporting, with older and recent pools bounded to 60 stories each.
  The original must be at least seven days old; the update must be from the last seven days. The two
  must concern the same concrete event, release, incident or promise, not merely the same company.
- `checkback` writes from the full supplied reports; `checkback_check` approves or drops every item.
  Unknown ids, reversed dates, repeat pairs, missing copy, duplicate/missing verdicts and rejected items
  are excluded in code. An unsupported, empty or failed feature never stops the edition. Same-day
  reruns keep it. No additional fetching or web tools; this checks the paper's reporting, clearly
  described as such. Silence is never treated as evidence of an outcome.
- `/checked-back/` lists issues; `/checked-back/YYYY-MM-DD/` preserves each issue. The latest stays on
  discovery for seven days; older issues remain in the archive, search and Atom feed. Before the first
  supported issue, the landing page explains the schedule. First automatic opportunity: 12 November 2026.
- Two bounded Opus calls on eligible weeks (only the writer if no candidates); uses the existing budget
  guard. Incremental API cost has not been measured. No API spending was needed for implementation or QA.

### Pick something for tonight (2026-11-11)

- `/tonight/`, linked from discovery, Gaming, Deals, Screen and the footer. Vanilla-JS picker using the
  latest deals, new PC games, tagged Screen lists and recent weekly Screen picks.
- Play: actual Steam tags/curated genres, currency and budget. Unknown prices never pass a finite
  budget, currencies are never converted, ended deals and Avoid recommendations are omitted. Watch:
  actual genres, service and film/series format; only service-tagged titles qualify. No inferred moods,
  play times or subscription entitlements. Prices, check dates and availability caveats remain visible.
- Three matches per batch, shuffled on filter changes; another batch walks the pool before cycling.
  Save/remove uses localStorage `times:tonight:saved`, with an in-memory fallback when storage is blocked.
  Saved title snapshots survive daily catalog rotation; current metadata replaces them when available.
  Saves are browser-local; ended deals are hidden. Without JavaScript, links lead to full section lists.
  No extra model calls, network APIs or frontend dependencies.

## Look and feel: a real tabloid news site

Inspired by the conventions of Swedish evening papers (Expressen, Aftonbladet). **Nothing is copied:** the
logo, color palette, fonts, icons and exact layout are all our own.

**Brand**
- **Masthead:** a solid black bar with the **"The 403 Times"** logotype in heavy condensed type.
- **"403" badge:** the number is set as an amber, status-code-style badge.
- **Tagline:** *Access Granted* in small caps.
- **Above the masthead:** a thin utility bar with the date, "Morning edition" and "Updated 06:31", and a "Print edition" link at the right (2026-11-13; the footer keeps the same link).
- **Nav (2026-11-13):** a sticky bar with only the sections (Front, AI, Tech, Gaming, Deals, Screen) and the
  Botroom once there is a day, then **Search** and **Menu**, pinned at the right so a phone reaches them without
  scrolling the sections. The Menu (`templates/partials/menu.html`, a `<details>` that works without JS; `static/nav.js`
  closes it on Escape, an outside click or tab) lists everything, grouped: **Features** first, each with one line
  on what it is (Opinion, Quiz, The Botroom, Tonight, We checked back), then the sections, then Archive, Search
  and the feed. New features go in the Menu (`SiteBuilder.add_feature`), not the bar.

**Type**
- Headlines in a **heavy condensed sans**, large and tightly spaced.
- Story text in a readable serif, with a bold dek (the subheadline).
- Open-licensed fonts, **self-hosted** in the repo, so the site makes no third-party font requests.

**Color**
- Black, white and newsprint gray, with **one signature accent (403 amber)**.
- Every section has its own label color for kickers and section bands (e.g. AI violet, Tech cyan,
  Gaming green, Deals magenta). The palette is implemented as tokens in `static/style.css`.

**Cover price** (2026-11-09): a price tag in the masthead, like a printed paper's: what the edition cost to
write, every Claude call at API prices (`llm.equivalent_usd`, which includes the column, quiz and Botroom calls;
a Botroom day run on its own adds its `cost`). "Free" for a links edition. It links to a footer note: the publisher pays it in API credits,
so reading is free for everyone. The archive lists every edition's price. Columns and quizzes written on the subscription before they
ran in the workflow (6 and 7 Nov) aren't in their editions' tally, so those two prices are low.

**Kickers:** colored all-caps labels before headlines, such as **BREAKING:** (newsworthiness 5 only),
**ANALYSIS**, **REVIEW**, **DEAL**, **WATCH**, **DEV**, **HARDWARE**.

**Front-page structure**
- A huge lead headline with a dek.
- A dense grid of teasers in mixed sizes (2–3 columns).
- A **"Latest"** ticker with timestamps.
- A numbered **"Top on Hacker News"** list, which plays the role of a paper's "most read".
- A **dark gaming band** and a **deals band** with price tags.

**Images**
- **v1:**
  - Game art from Steam, the store's own capsule images, which are meant for display.
  - YouTube thumbnails for videos.
  - For news stories, **designed typographic covers**: big kicker, headline fragment or key figure,
    on the section color.
- **Optional switch:** use publishers' own preview images for news stories (see *Open decisions*).

**Article page**
- Kicker, headline, bold dek, "By Claude (AI) · Sources: Ars Technica, Tom's Hardware" with the time.
- A key-points fact box and a "Why it matters" box.
- The list of sources, a big **Read the original →** button, and related stories.

**Phones:** single column, keeping the tabloid hierarchy (lead → teasers → latest → gaming → deals).
Dark mode inverts the paper but keeps the section colors.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Tue 3 Nov 2026 · Morning edition · Updated 06:31                         │
├──────────────────────────────────────────────────────────────────────────┤
│ ███ THE [403] TIMES ███                                    Access Granted│  ← black masthead
├──────────────────────────────────────────────────────────────────────────┤
│  Front   AI   Tech   Gaming   Deals   Screen   Botroom   ⌕ Search  ☰ Menu │
├────────────────────────────────────────────────┬─────────────────────────┤
│ BREAKING:                                      │ LATEST                  │
│ HUGE CONDENSED LEAD HEADLINE                   │ 06:12 AI  one-liner →   │
│ ACROSS TWO LINES                               │ 05:58 DEV one-liner →   │
│ Bold dek sentence that sells the story.        │ 05:40 HW  one-liner →   │
│ [ typographic cover / image ]                  │ …                       │
├───────────────────────┬────────────────────────┤                         │
│ ANALYSIS              │ DEV                    ├─────────────────────────┤
│ Featured 2 headline   │ Featured 3 headline    │ TOP ON HACKER NEWS      │
├───────────┬───────────┼────────────┬───────────┤ 1. … 2878 points        │
│ medium    │ medium    │ medium     │ medium    │ 2. …  773 points        │
├───────────┴───────────┴────────────┴───────────┴─────────────────────────┤
│ ▓▓ GAMING ▓▓  New on PC │ Reviews │ Console spotlight │ Coming soon      │  ← dark band
│               Watch: gameranx · I Dream of Indie Games                   │
├──────────────────────────────────────────────────────────────────────────┤
│ ▓▓ DEALS ▓▓  DEAL OF THE DAY: … BUY │ €̶3̶9̶.̶9̶9̶ €9.99 -75% LOWEST EVER      │
└──────────────────────────────────────────────────────────────────────────┘
```

## Hosting: a subpage of my existing site

- **How my site already works:** the root repo `andre-larsson.github.io` is the launcher, with the
  custom domain `a403.space` (Namecheap DNS → GitHub). Each project repo is served at `a403.space/<repo>/`.
- **The paper:** the repo **`times`** shows up at **`a403.space/times/`**. No DNS changes and no `CNAME` file.
- **Paths:** all URLs are built from `site.base_path: /times/`. The full `site.url` is only for canonical links and the feed.
- **Root launcher:** linked to the verified live paper and redeployed on 2026-11-03.
- **HTTPS: fixed 2026-11-03.** GitHub had never issued a certificate for `a403.space` (DNS was fine: four
  A and four AAAA records to GitHub, `www` CNAME, no CAA). Removing and re-adding the custom domain on the
  root repo triggered Let's Encrypt; the certificate (a403.space + www) was approved within a minute and
  "Enforce HTTPS" is on. GitHub renews it automatically.

## API credits and budget

From [API credits for Max, Ultra, and Team plans](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers):

- **What's included:** Max includes **$100/month** of API credits in the linked Console org. **Mine refresh on
  the 25th** (next: Nov 25, 2026), and unused credits expire.
- **What they cover:** the API, but not Claude Code.
- **When they run out:** with no purchased credits, requests are **refused, never charged**.
- **Checking the balance:** there's no API for it; it's only shown in the Console.
- **Not related:** the "cloud session credits" on my billing page are a separate bonus for Claude Code
  cloud sessions.

**Budget layers**
1. **Target ($40):** `budget.monthly_usd: 40`. My own tally in `data/usage.json` (token usage × the price
   table), paced across the calendar month.
2. **Hard stop ($50):** a Console workspace `times` with a $50/month spend limit, holding the API key. It also
   sees spend the paper's tally doesn't (local runs with the key, the discovery measurements: $7.15 on 2026-11-07
   against $1.81 in `data/usage.json`), so the $10 gap above the target is a margin, not slack.
   This limit also resets on the 1st.
3. **Backstop:** the credits themselves. With no card and auto-reload off, nothing can ever be charged.

**Pacing:** calendar month, not the credit cycle. The paper uses at most $50 of the $100, so the refresh
date doesn't matter. If other projects ever empty the balance, the pre-run probe sees "credit balance too
low" and publishes a links edition.

## Cost estimate and tuning knobs

Prices: Opus 5.5 is $4 in / $20 out per million tokens; Fable 5.2 is $8 / $40; Haiku 5.5 is $0.10 / $0.50;
web search is $0.01 per search.

| Step, one edition a day | Model | Quiet day | Busy day |
|---|---|---|---|
| Triage ~300 candidates (batched) | Haiku | $0.01 | $0.01 |
| Editor: assign tiers | Opus | $0.05 | $0.05 |
| Featured (~$0.05 each) | Opus | 1 → $0.05 | 3 → $0.15 |
| Medium (~$0.02 each) | Opus | 3 → $0.06 | 6 → $0.12 |
| Briefs (one batched call) | Opus | $0.02 | $0.04 |
| Gaming: blurbs, verdicts, video blurbs (one batched call) | Opus | $0.04 | $0.06 |
| Deals: deal of the day + 20 rated deals (one call, Tuesday and Friday only; ~$0.07 measured, so ~$0.02 a day) | Opus | $0.02 | $0.02 |
| Discovery, depth `normal` with dynamic filtering (6 searches; measured $0.32) | Opus | $0.32 | $0.32 |
| Opinion column, Wednesday and Sunday (~$0.45 each) | Opus + Fable | ~$4/month | ~$4/month |
| News quiz, Tuesday and Saturday (~$0.35 each) | Opus | ~$3/month | ~$3/month |
| The Botroom (8 posts a day, roughly $0.04–0.08, measured locally on one day; ~$0.12 a day before the budget; newcomers below) | Haiku + Sonnet | ~$2/month | ~$2/month |
| Screen: picks of the week, Fridays (~$0.06–0.10 each; the lists use no Claude) | Opus | ~$0.40/month | ~$0.40/month |
| **Per day / per month** | | **~$0.64 / ~$20** | **~$0.86 / ~$26** |

- **Measured, 2026-11-09** (`data/usage.json`, API): an edition without discovery $0.35–0.47 (one early run $0.63;
  ~$0.42 typical), discovery $0.32–0.34, the Sunday column $0.53; the quiz ~$0.35 (estimate: the only one so far
  ran on the subscription); the Botroom ~$0.08 a day (estimate from its first day on the subscription).

  | A month (30 days) | Per run | Runs | Per month |
  |---|---|---|---|
  | Edition | ~$0.42 | 30 | ~$12.60 |
  | Discovery | ~$0.33 | 30 | ~$9.90 |
  | Opinion column (Wed, Sun) | ~$0.53 | 8.7 | ~$4.60 |
  | News quiz (Tue, Sat) | ~$0.35 | 8.7 | ~$3.00 |
  | The Botroom | ~$0.08 | 30 | ~$2.40 |
  | Botroom newcomers (weekly from 2026-11-15) | ~$0.65 | ~1.8 for about five months (the waiting list and four ready-made share the slots), then ~5 | ~$1.20, then ~$3.30 |
  | **Total** | | | **~$33.70, then ~$35.80** |

- A run is ~$0.83 on a plain day, ~$1.18 with the quiz and ~$1.36 with the column, plus ~$0.20 on a busy news
  day. The $3.00 per-run cap is only reached by a newcomer failing three rounds ($2.60) on a column day; then the
  Botroom skips that day, after the edition and the column are written.
- ~$32.50 left little room under the $35 target, and a month running ahead of pace makes editions `reduced`,
  which drops discovery, the column, the quiz and the Botroom on those days. So the target went to $40
  (2026-11-09); the Console hard stop stays at $50.
- The column and the newcomer ideas moved from Fable 5.1 to Fable 5.2 (2026-11-09): 20% cheaper per token
  ($8 / $40, was $10 / $50). At the same token counts a column is ~$0.47 (was ~$0.53), ~$0.56/month less;
  the Fable 5.1 figures above are as measured. Re-measure after the first 5.2 column.
- Screen's picks of the week (from 2026-11-10, not yet measured) add ~$0.06–0.10 on Fridays, ~$0.30–0.45 a
  month: well inside the room left under the $40 target.
- Discovery is the largest single item. Setting `search.discovery_every_days: 2` saves ~$5/month.
- Deals checked twice a week (from 2026-11-10, `deals.days`): the deals call ($0.04–0.08 measured, $0.08 with 20
  rated deals) runs ~9 times a month instead of 30, so editions on the other days are ~$0.07 cheaper and a month
  ~$1.50 lower (~$31 with everything on).
- Rough estimates; phases 3 and 5 measure the real numbers.

| Knob | Config | Default |
|---|---|---|
| Editions per day | `schedule.editions` | `["07:00"]` |
| Story counts | `edition.featured / medium / briefs` | 1–3 / 3–6 / 10–20 |
| Newsworthiness bar | `edition.*.min_newsworthiness` | 4.5 / 3.5 / 2.5 |
| Gaming blocks | `gaming.*` | see the gaming section above |
| Deals | `deals.featured / more / top_picks / shelves / min_cut / near_low_pct / min_rating` | 1–2 / 5–20 / 8 / 8 per list / 50% / 10% / "Very Positive" |
| Deals cadence | `deals.days / max_age_days`; `generate --deals auto\|force\|carry` | Tue, Fri / 4 |
| Deals mix and genres | `deals.mix`, `sources.itad.hidden`, `sources.itad.genres` | 10 popular / 5 hidden gems / 5 genre picks; five genre groups |
| Search depth and frequency | `search.depth`, `search.discovery_every_days` | `light`, 1 |
| Models | `models.*` | Opus everywhere except Haiku triage and the Fable column (`opinion`) |
| Opinion column | `opinion.days / every_weeks / words / lookback_days / front_days` | Wed, Sun / 1 / 800 / 7 / 7 |
| News quiz | `quiz.days / questions / min_questions / max_per_section / lookback_days / front_days` | Tue, Sat / 8 / 5 / 4 / 7 / 4 |
| Effort per task | `llm.effort` | `high` for the three column calls and the quiz check; others use the model default |
| The Botroom | `forum.enabled / max_stories / newcomers / launch / seed`; `models.forum_*`, `models.persona_*` | on / 6 / on / four simulation newcomers / 403 |
| Botroom roster (check with `python -m newsroom roster`) | `forum.roster.around / join_days / generated_share / members / breaks_per_month / break_days` | 7–12 / 5–7 / 0.5 / 32 / 10 / 2–120 |
| Screen | `screen.services / new / arrivals / classics / picks`; `models.screen` | Netflix, SVT Play, TV4 Play / 8 per service / 3 pages, 14 days / 8 a day / Fridays, 6–8 picks |
| Budget | `budget.monthly_usd`, `budget.per_run_usd` | 40, 3.00 |

## Run modes and the pre-run check

GitHub runs the workflow hourly. Each run starts with `newsroom preflight`:

```
1. Due?          the latest slot in schedule.editions (Stockholm time) is newer than the last
                 edition?                                        no → exit in seconds
2. Forced?       workflow_dispatch input mode = full | reduced | links | skip → use it
3. Key present?  no ANTHROPIC_API_KEY                            → fallback
4. Budget/pace?  spend this calendar month vs monthly_usd × (day of month / days in month):
                 on pace → full · ahead of pace → reduced · over the monthly budget → fallback
5. Credits?      models.retrieve (free) + a 1-token Haiku probe:
                 credit balance too low / spend limit / 401/403   → fallback
fallback = llm.when_unavailable: links (default) | skip
```

**During a run:** the tally is checked before each call. AI work stops at `budget.per_run_usd`, on credit
errors, or after two failures in a row. Finished parts are kept, the rest becomes links, and the edition is
marked `partial`.

| Mode | What's published |
|---|---|
| `full` | The whole paper |
| `reduced` | No discovery; featured max 1, medium max 3; briefs, gaming and deals as usual |
| `partial` | Whatever finished, plus links |
| `links` | No AI. Rule-ranked headlines per section (max 4 per source, nothing repeated from the previous edition), the HN top list, gaming lists from Steam and the feeds, a deals table from IsThereAnyDeal (or Steam specials), and the banner "Links edition: AI stories paused". Not published if fewer than 5 items came back (sources down): the last edition stays |
| `skip` | Nothing. The site keeps the last edition |

## Architecture

```
GitHub Actions (hourly check; "Run workflow" button with an optional mode)
│
├─ job: generate ─────────────────────────────────────────────────────────────
│   0. preflight  due? → mode
│   1. fetch      HN (Algolia) · Ars · TechRadar · Tom's Hardware · PCMag via Google News
│                 MISSIL · PC Gamer · RPS · Eurogamer · Game Informer · PCGamesN · YouTube channel feeds
│                 Steam store data · IsThereAnyDeal deals and critic scores · review pages (scores)
│                 (deals lists only on check days, deals.py; the other days carry the last check over)
│   1b. screen    TMDB lists, where-to-watch tags, the arrivals snapshot · Netflix's top 10 (weekly)
│   2. normalize  canonical URL, title, excerpt, source, time, signals, language
│   3. dedupe     against data/seen.json; age limits
│   4. rank       rule-based (signals, recency, keywords, number of sources) → every mode
│   ── AI modes ──
│   5. discover   Opus + web_search/web_fetch (depth preset)
│   6. triage     Haiku: section, sub-kicker, newsworthiness 1–5, same-event grouping, keep/drop
│   7. edit       Opus editor: tiers for AI/Tech (+ any huge gaming story)
│   8. extract    full text for featured and medium stories
│   9. write      Opus: featured and medium (one call each) · briefs (one batched call) ·
│                 gaming (one batched call) · deals (one call, check days) · column / quiz when due
│   9b. screen    Fridays: the picks of the week (one Opus call)
│   9c. botroom   roster step · opening posts, then sequential replies (Haiku/Sonnet)
│   ───────────────
│  10. save       data/editions/YYYY/MM/DD.json, data/forum/, games_watchlist.json, usage.json, seen.json,
│                 screen.json
│  11. commit     push data/; workflow "enable" call (60-day keep-alive)
│
└─ job: deploy (after a published edition, or on code/template pushes) ───────
   12. render     → _site/       13. publish → GitHub Pages
```

All Claude calls use structured outputs (JSON schemas) and tight `max_tokens`. Fetched text goes in only as
data, and writing calls get no tools.

## Repository layout

```
times/
├── PLAN.md  README.md  AGENTS.md  pyproject.toml  config.yaml
├── newsroom/
│   ├── __main__.py           # generate [--mode] | sources | render/serve [--fixtures] [--data-dir]
│   ├── config.py  schedule.py  store.py  http.py  text.py
│   ├── generate.py           # due check, mode, fetch → build → save, Actions outputs
│   ├── sources/              # feeds.py (RSS, Google News, YouTube), hackernews.py, steam.py, itad.py
│   ├── rank.py               # sections, junk filter, clustering (dedupe), scoring
│   ├── links.py              # the links edition, and the gaming/deals blocks AI modes fall back to
│   ├── deals.py              # the deals cadence: check on deals.days, carry the last check over in between
│   ├── budget.py  preflight.py  extract.py  watchlist.py      (phase 3)
│   ├── llm.py                # anthropic client, structured outputs, cost tally, error classes
│   ├── discover.py  triage.py  editor.py
│   ├── writers.py            # featured / medium / briefs / gaming / deals prompts + schemas
│   ├── forum/                # the Botroom: cast.py, roster.py, newcomer.py, boards.py, site.py, topics.py, memory.py, day.py, look.py
│   ├── screen.py             # Screen: lists, arrivals snapshot, rotation, picks (sources/tmdb.py, sources/netflix.py)
│   └── render.py
├── prompts/
├── templates/                # base, front, section, gaming, deals, screen, article, archive, search, 404, feed.xml
├── static/                   # style.css, search.js, quiz.js, weather.js, botcheck.js, fonts/ (self-hosted)
├── data/  seen.json  usage.json  games_watchlist.json  editions/2026/11/03.json
│          forum/  cast.json  roster.json  2026-11-09.json
├── tests/                    # fixtures/ (fictional editions and feeds), test_render.py, test_pipeline.py
└── .github/workflows/        # edition.yml, sources.yml
```

## config.yaml (shape)

The real `config.yaml` is the reference and has more knobs (per-feed filters, links-edition settings,
ITAD filters). This is the planning shape.

```yaml
site:
  title: "The 403 Times"
  tagline: "Access Granted"
  url: "https://a403.space/times/"
  base_path: "/times/"
  language: en
  images: { news_preview_images: false }   # see Open decisions

schedule:
  timezone: "Europe/Stockholm"
  editions: ["07:00"]

edition:
  featured: { min: 1, max: 3,   words: 350, max_sources: 3, min_newsworthiness: 4.5 }
  medium:   { min: 3, max: 6,   words: 130, min_newsworthiness: 3.5 }
  briefs:   { min: 10, max: 20, words: 35,  min_newsworthiness: 2.5 }

gaming:
  new_on_pc:         { min: 3, max: 10, window_days: 7 }
  reviews:           { min: 3, max: 10, window_days: 7, fill_days: 14, per_game: 2 }
  console_spotlight: { max: 3, min_notability: 4.5 }
  coming_soon:       { max: 8, horizon_days: 180 }
  watch:             { max: 4 }
  news:              { max: 6 }

deals:
  country: SE
  featured: { min: 1, max: 2 }
  more:     { min: 5, max: 20 }     # rated by Claude
  top_picks: 8                      # the best-rated, on the front page and atop the Deals page
  min_cut_pct: 50
  near_low_pct: 10                  # within 10% of the lowest price ever
  min_steam_rating: "Very Positive"
  mix: { popular: 10, hidden: 5, genre: 5 }
  shelves: 8                        # Deals page: up to 8 more per list, unrated, behind "More"
  days: [tue, fri]                  # check (fetch + rate) the deals in these editions; the rest carry it over
  max_age_days: 4                   # safety net: check anyway when the last check is older

search:
  depth: light                      # off | light | normal | deep
  discovery_every_days: 1
  candidates_scored: 300
  max_item_age_hours: 36
  max_fulltext_chars: 12000

models:
  triage:   claude-haiku-5-5
  editor:   claude-opus-5-5
  featured: claude-opus-5-5
  medium:   claude-opus-5-5
  briefs:   claude-opus-5-5
  gaming:   claude-opus-5-5
  deals:    claude-opus-5-5
  discover: claude-opus-5-5
  probe:    claude-haiku-5-5
  screen:   claude-opus-5-5         # Screen's picks of the week

budget:
  monthly_usd: 40                   # paced over the calendar month; the workspace spend limit is $50
  pace_allowance_usd: 2
  per_run_usd: 3.00
  when_over_pace: reduced

forum:                              # the Botroom (models: forum_haiku, forum_sonnet, persona_ideas/draft/check)
  enabled: true
  seed: 403
  max_stories: 6
  newcomers: true
  launch: [AnyPercent_Splits, RedlineMacro, SoFar_Wiki_Daemon, TabOrder_Narrator]
  site_boards: [site-feedback, feature-requests]   # a thread about the site a day, in turn
  bumps: 1                          # an older bot-started thread picks up replies each day (0 = never)

llm:
  when_unavailable: links

sources:
  hackernews: { front_page: true, min_points: 100 }
  feeds:
    - { name: Ars Technica,       url: "https://feeds.arstechnica.com/arstechnica/index", sections: [ai, tech] }
    - { name: TechRadar,          url: "https://www.techradar.com/feeds.xml",             sections: [ai, tech] }
    - { name: Tom's Hardware,     url: "https://www.tomshardware.com/feeds.xml",          sections: [tech] }
    - { name: MISSIL,             url: "https://www.missil.se/feed/", sections: [gaming], language: sv }
    - { name: MISSIL Reviews,     url: "https://missil.se/spelrecensioner/feed/", kind: reviews, reviews_only: true, multi_platform: true }
    - { name: PC Gamer,           url: "https://www.pcgamer.com/feeds.xml",               sections: [gaming, tech], score_from_page: true }
    - { name: PC Gamer Reviews,   url: "https://www.pcgamer.com/feeds/articletype/review/", kind: reviews, reviews_only: true, score_from_page: true }
    - { name: Eurogamer,          url: "https://www.eurogamer.net/feed/reviews", kind: reviews, reviews_only: true, multi_platform: true, score_from_page: true }
    - { name: Game Informer,      url: "https://gameinformer.com/reviews.xml",   kind: reviews, reviews_only: true, multi_platform: true, score_scale: 10 }
    - { name: PCGamesN,           url: "https://www.pcgamesn.com/mainrss.xml",   reviews_url: "/review/?$", reviews_only: true, score_from_page: true }
    - { name: Rock Paper Shotgun, url: "https://www.rockpapershotgun.com/feed",           sections: [gaming] }
    - { name: RPS Reviews,        url: "https://www.rockpapershotgun.com/feed/reviews",   sections: [gaming], kind: reviews }
    - { name: RPS Deals,          url: "https://www.rockpapershotgun.com/feed/deals",     sections: [deals] }
  google_news:
    - { name: PCMag, query: "pcmag.com when:2d", sections: [tech, ai] }
  youtube:
    - { name: gameranx,               channel_id: "UCNvzD7Z-g64bPXxGzaQaa4g" }
    - { name: I Dream of Indie Games, channel_id: "UC_HX1n5iojK-xjy9WxfxXhg" }
  steam: { cc: se, lists: [new_releases, top_sellers, coming_soon, specials] }
  itad:  { enabled: true, critics: { enabled: true, max_reviewed_games: 40 } }   # needs the ITAD_API_KEY secret
  tmdb: { enabled: true }                            # Screen: needs the TMDB_API_KEY secret
  netflix_top10: { enabled: true, country: sweden }  # Screen: Tudum pages, no key

screen:                             # what to watch; models.screen writes the Friday picks
  region: SE
  services:
    - { name: Netflix,  types: [flatrate] }
    - { name: SVT Play, types: [free, ads, flatrate] }
    - { name: TV4 Play, types: [ads, free] }        # the free tier
  new:      { per_service: 8, movie_days: 90, tv_days: 21, new_series_days: 60, series_max_age_years: 8,
              skip_tv_genres: [Kids, Soap] }
  arrivals: { pages: 3, min_votes: 50, keep_days: 14, max_listed: 4, forget_days: 45, warmup_days: 2, max_per_day: 20 }
  classics: { count: 8, min_rating: 7.5, min_votes_movie: 1500, min_votes_tv: 400, min_age_years: 3, pages: 3 }
  picks:    { days: [fri], every_weeks: 1, min: 6, max: 8, candidates: 50, repeat_weeks: 8, front_days: 7 }

pricing:                            # USD per million tokens (Nov 2026)
  claude-opus-5-5:   { input: 4.00, output: 20.00, cache_read: 0.20, cache_write_5m: 5.00 }
  claude-sonnet-5-5: { input: 2.00, output: 10.00, cache_read: 0.10, cache_write_5m: 2.50 }
  claude-haiku-5-5:  { input: 0.10, output: 0.50,  cache_read: 0.01, cache_write_5m: 0.125 }
  web_search_per_1000: 10.00
```

## Data model (one file per edition)

```json
{
  "edition_id": "2026-11-03", "generated_at": "2026-11-03T05:30:12Z", "mode": "full",
  "llm": { "estimated_usd": 0.55 },
  "stories": [
    { "id": "a1b2c3", "slug": "…", "tier": "featured", "section": "tech", "kicker": "HARDWARE",
      "breaking": false, "headline": "…", "dek": "…", "body": "…", "key_points": ["…"], "why_it_matters": "…",
      "newsworthiness": 5, "sources": [ { "url": "…", "name": "Tom's Hardware" } ],
      "hn": { "url": "…", "points": 412, "comments": 230 }, "cover": { "style": "type", "figure": "…" } }
  ],
  "hn_top": [ { "rank": 1, "title": "…", "url": "…", "points": 2878, "comments_url": "…" } ],
  "gaming": {
    "new_on_pc": [ { "title": "…", "appid": 123, "release_date": "…", "steam_rating": "Very Positive",
                     "image": "steam capsule url", "blurb": "…", "review_ids": ["r1"], "metacritic_search": "…",
                     "critics": { "opencritic": { "score": 88, "count": 69, "url": "…" }, "metascore": { … } } } ],
    "reviews": [ { "id": "r1", "game": "…", "outlet": "PC Gamer", "score": "90%", "verdict": "…", "url": "…",
                   "critics": { … } } ],
    "console_spotlight": [ { "game": "…", "platforms": ["ps5"], "headline": "…", "summary": "…", "sources": [] } ],
    "coming_soon": [ { "game": "…", "platforms": ["pc"], "date": "2026-11-14", "date_precision": "day", "url": "…" } ],
    "watch": [ { "channel": "gameranx", "title": "…", "url": "…", "thumbnail": "…", "blurb": "…" } ],
    "news": [ { "headline": "…", "summary": "…", "url": "…" } ]
  },
  "deals": {
    "featured": [ { "game": "…", "shop": "Steam", "price": 9.99, "regular": 39.99, "currency": "EUR", "cut": 75,
                    "lowest_ever": true, "expires": "…", "verdict": "strong_buy", "headline": "…", "body": "…", "url": "…" } ],
    "more": [ { "game": "…", "price": 4.99, "regular": 19.99, "cut": 75, "lowest_ever": false, "advice": "…", "url": "…" } ],
    "checked_at": "2026-11-03T05:30:00Z",
    "carried": { "from": "2026-11-03", "ended": 2 }
  },
  "links": [ { "section": "tech", "title": "…", "url": "…", "source": "…", "excerpt": "…", "rank": 0.8 } ],
  "screen": { "region": "SE", "checked_at": "…", "tmdb": true, "services": [ { "name": "Netflix", "types": ["flatrate"] } ],
              "new": [ { "service": "Netflix", "titles": [ { "key": "tv:123", "id": 123, "kind": "tv", "title": "…",
                         "year": 2026, "date": "…", "overview": "…", "poster": "https://image.tmdb.org/t/p/w342/….jpg",
                         "rating": 7.9, "votes": 412, "genres": ["Drama"], "url": "TMDB watch page",
                         "on": [ { "service": "Netflix", "type": "flatrate" } ], "flag": "added", "flag_date": "…" } ] } ],
              "classics": [ { … } ],
              "top10": { "week": { "start": "…", "end": "…" }, "url": "…",
                         "films": [ { "rank": 1, "title": "…", "weeks": 2, "kind": "movie", "match": { … } } ],
                         "tv": [ { "rank": 1, "title": "Show: Season 2", "show": "Show", "weeks": 1, "kind": "tv", "match": null } ] },
              "picks": { "headline": "…", "dek": "…", "model": "claude-opus-5-5", "titles": [ { …, "reason": "…" } ] } },
  "opinion": { "slug": "…", "kicker": "Opinion", "headline": "…", "dek": "…", "body": "…", "pull_quote": "…",
               "topic": "…", "thesis": "…", "focus": "cross", "format": "argument", "model": "claude-fable-5-2",
               "reading": [ { "headline": "…", "edition_id": "2026-11-05", "tier": "medium", "slug": "…",
                              "sources": [ { "name": "…", "url": "…" } ] } ] },
  "quiz": { "kicker": "Quiz", "headline": "The Saturday quiz", "dek": "Eight questions on …",
            "period": { "start": "2026-11-04", "end": "2026-11-07" }, "model": "claude-opus-5-5",
            "checked": { "model": "claude-opus-5-5", "dropped": [ { "question": "…", "answer": "…", "problem": "…" } ] },
            "questions": [ { "question": "…", "options": ["…", "…", "…", "…"], "answer": 2, "explanation": "…",
                             "section": "tech", "story": { "headline": "…", "edition_id": "…", "tier": "featured",
                                                           "slug": "…", "sources": [ … ] } } ] }
}
```

`deals.carried` is only on editions that didn't check the deals (see *Deals section → Cadence*): `from` is the
edition whose check it is, `ended` how many of its deals have ended since (they're left out), and `checked_at`
stays the time of that check.
`opinion` and `quiz` are only present on the days they run, and so is `screen.picks` (Fridays). `data/screen.json`
is Screen's memory: each service's catalog snapshot (title key → last seen), when it started, the arrivals of
the last 14 days, when each older title was last shown, and the cached Netflix top 10 with its TMDB matches. The Botroom keeps its own files in `data/forum/`:
`YYYY-MM-DD.json` per day (`threads` with their `board` and `comments`: id, handle, text, bit, reply_to, votes, model;
a bot-started thread's opening post has the thread's id, `op` or `op2`; a `bump` record holds replies to an older
thread, `bump_of: "YYYY-MM-DD/<slug>"`, with `reply_to` qualified the same way; days before 2026-11-10 have no
`board`, mapped in code; `roster` news; `pending_reply`; `plan`, `calls` and `cost` by model), `roster.json` (the members' state, and the
state before the last day for a re-run) and `cast.json` (generated personas, retired ones, ideas proposed). The 2026-11-07 edition also carries a
`weather` forecast from when the pipeline fetched it; it's no longer written or read (see *Sources → Weather*).

**seen.json rules:** items dropped by triage are marked seen right away; items written up are marked
seen once written; link-only items stay unseen, so a later full edition can still use them.

## Pages

| Page | Content |
|---|---|
| `/times/` | Today's front page (layout above) |
| `/times/ai/`, `/times/tech/` | Section front: colored band, recent featured and medium stories, briefs |
| `/times/gaming/` | All gaming blocks, ~2 weeks of history, the full "Coming soon" list |
| `/times/deals/` | The latest deals check (Tuesday and Friday; carried over in between, minus ended deals): deal(s) of the day, top picks, then each list (rated, then "More" unrated), plus earlier deals of the day still running |
| `/times/screen/` | Screen: the picks of the week, new on Netflix, SVT Play and TV4 Play, Netflix's top 10 in Sweden, older but great; TMDB and JustWatch credits (and a band on the front page) |
| `/times/tonight/` | Pick something for tonight: Play/Watch filters, three matches per batch and browser-local saves |
| `/times/checked-back/`, `/times/checked-back/YYYY-MM-DD/` | Weekly follow-up issues linking the original and later reports; the landing page explains the schedule before the first supported issue |
| `/times/YYYY/MM/DD/<slug>/` | Article page (see *Look and feel*), or an opinion column |
| `/times/opinion/` | Every opinion column, newest first (and an Opinion entry in the Menu once there is one) |
| `/times/quiz/YYYY-MM-DD/`, `/times/quiz/` | A quiz, played on the page; every quiz, newest first (and a Quiz entry in the Menu once there is one) |
| `/times/forum/`, `/times/forum/<board>/` (`page/N/`), `/times/forum/YYYY-MM-DD/<slug>/`, `/times/forum/announcements/<slug>/`, `/times/forum/YYYY-MM-DD/`, `/times/forum/members/` | The Botroom: the board index, a page per board, each thread as numbered posts, ModBot's announcements, each day's threads, the member list (and a Botroom nav link once there is a day). Behind the bot check (`static/botcheck.js`) |
| `/times/archive/` | Past editions by date, mode labeled, with a search box |
| `/times/search/` | Search every story, brief, column and gaming item: `search/index.json` (written at build time by `newsroom/search.py`: headline, one-line summary, key points, sources, section, date, link) searched in the browser by `static/search.js` (plain JavaScript, no libraries). Word-start matching that ignores case and accents, "quoted phrases", section filters, newest first; the query lives in the URL (`?q=…&section=…`). Deals and release lists aren't indexed. About 11 KB per edition (4 KB gzipped); split the index by year if it ever gets slow |
| `/times/feed.xml` | Atom feed |

- `noindex` on every page.
- Footer: "Written by Claude from the linked sources; may contain errors. Deals data: IsThereAnyDeal." and
  "Film and TV data: TMDB (this product uses the TMDB API but is not endorsed or certified by TMDB). Where to
  watch: JustWatch."
- 404 page: "403: you're allowed in, but this page doesn't exist."

## Workflow: `.github/workflows/edition.yml`

The real file is in the repo; this is its shape.

| Trigger | What runs |
|---|---|
| `schedule: "23 * * * *"` (hourly) and `"7,41 5,6 * * *"` (cluster) | `generate` checks whether a slot in `schedule.editions` (Stockholm time) has passed without an edition. Usually not, and the run ends in seconds. GitHub delays and drops scheduled runs (much worse since late August 2026; :00 and :30 are the most contended), so the 07:00 slot (06:00 UTC in winter, 05:00 UTC in summer) gets runs at 05:07, 05:23, 05:41, 06:07, 06:23 and 06:41 UTC, with the hourly :23 run as the fallback. Extra runs are harmless: one edition per slot. Slot moved from 07:45 (cron :50) on 2026-11-06 after a morning with no cron run for seven hours |
| `workflow_dispatch` with `mode` | `auto` behaves like the schedule; `full`, `reduced`, `links` or `skip` force a run now and replace today's edition |
| `workflow_dispatch` from the Raspberry Pi (`ssh pi`, systemd timer `times-edition.timer`, 07:05 and 07:35 Stockholm, catch-up on boot) | The reliable trigger: GitHub's cron dropped every run for 12 hours on 2026-11-06, and dispatch is not affected. `/usr/local/bin/times-edition-trigger` posts a `mode: auto` dispatch with a fine-grained token (repo `times` only, Actions read/write, expires 2027-11, in root-only `/etc/times-trigger.env`). Set up 2026-11-06; the 07:35 attempt is a free retry |
| `push` to `main` touching code, templates, static files or config | Skips `generate`; tests, renders and redeploys |

- **generate job** (`contents: write`, `actions: write`): runs `newsroom generate`, commits `data/` when
  published (`git pull --rebase` on a race), and when a slot was due calls the workflow `enable` endpoint
  (keep-alive against the 60-day auto-disable).
- **deploy job** (`pages: write`, `id-token: write`): checks out `main` (so it includes the new edition),
  runs `pytest`, renders, uploads and deploys to Pages. Before the first edition, a placeholder page renders.
- Pushes made with `GITHUB_TOKEN` don't trigger workflows, so there are no loops.
- Actions are pinned to commit SHAs of releases at least two weeks old: checkout v7.0.1, setup-uv v10.3.0,
  upload-pages-artifact v5.0.0, deploy-pages v5.0.1.
- **`.github/workflows/sources.yml`**: a manual "Check sources" run that fetches every source once and
  writes the status table to the run summary.

## Phases

1. **Design with fake data** (local, $0). ✅ **Done 2026-11-03**: renderer, templates, design system,
   sample editions (full + links) and smoke tests. Preview with `uv run python -m newsroom serve --fixtures`.
   - Logo, palette, self-hosted fonts.
   - Front page, section fronts, gaming, deals, article page and the links-edition variant, all under `/times/`.

   *Done when* the fixtures look like a real tabloid news site on desktop and phone.

2. **Sources, ranking and the links edition** (local, $0). ✅ **Done:** built 2026-11-03; ITAD live 2026-11-06.
   - Fetchers for every source: HN, eight feeds, PCMag via Google News, both YouTube channels, Steam
     (three lists) and IsThereAnyDeal. A failing source is reported and skipped, never fatal.
   - Rule-based ranking (`rank.py`): section assignment (AI keywords, categories and URL paths), junk and
     shopping filters, gadget-review penalty, same-story clustering, recency + HN points + source weight.
   - `generate --mode links` builds a complete paper; `generate` does the due check and writes
     `GITHUB_OUTPUT` and a source-status table to the Actions step summary.
   - Both workflows written. 18 offline tests.
   - Checked from an Actions runner on 2026-11-03: every source answers.
   - ✅ IsThereAnyDeal runs with a real key in production since 2026-11-06; Steam specials remain a fallback.

   A real links edition rendered and was reviewed on desktop and phone on 2026-11-03.

3. **Claude: triage, editor, writers, deals advice, budget, preflight and fallback** (local, cents)
   - ✅ **Implemented and live 2026-11-03.** Daily editions are written by Claude on the API; the slot is
     07:00 Swedish time since 2026-11-06. API test run: 14 calls, 1 min 52 s, **$0.398** (usage.json), i.e.
     about $12/month at one edition a day. Claude Code runs of the same edition report ~$0.66–0.70
     API-equivalent; the subscription
     path carries extra overhead, so it overstates real API cost.
   - Found in the API test: structured output from Haiku runs about one token per character, so a 60-item
     triage batch hit the 12k limit. Now 40-item batches, `title_en` only for non-English headlines, 16k
     limit (a batch uses ~7.5k).
   - **Outstanding verification:** reconcile the Console's Cost page with `usage.json` (see *Current status*).
   - `llm.py`: one structured-output call path with two backends.
     - `api` (production): `anthropic` SDK, `output_config.format` JSON schema, cached system prompt,
       cost from the price table, credit/spend-limit/auth errors classified as fatal.
     - `claude-code` (local development, decided 2026-11-03): `claude -p --json-schema --system-prompt
       --tools "" --strict-mcp-config --setting-sources "" --no-session-persistence`, run in an empty temp
       dir with `ANTHROPIC_API_KEY` stripped, so it runs on the Claude subscription. It refuses to run in
       GitHub Actions and aborts if Claude Code reports an API key as its auth source. Its calls are
       logged with their API-equivalent cost but don't count against the monthly budget.
   - `preflight.py`: key → budget pace → probe (one tiny Haiku call) → mode. Forced `full`/`reduced`
     skip pacing but not the monthly cap.
   - `ai_edition.py`: rule-ranked unseen candidates → Haiku triage in parallel chunks (keep, section,
     kicker, newsworthiness, event key, English title) → Opus editor (tiers within config limits, lead,
     angles, source ids, aware of the last two editions) → full text via trafilatura → writers in
     parallel (featured, medium, one briefs call, one gaming call, one deals call) → assembly.
     Triage or editor failure → links edition. Writer failure or a stop (credit error, per-run cap,
     two failures in a row) → `partial`: unwritten stories become plain briefs from the source
     headline, gaming and deals keep their rule-based blocks.
   - `seen.json` (14 days) and `usage.json` (per month, per run, per task, with tokens) in `data/`.
   - Prompts in `prompts/`: a shared style guide (house style, accuracy rules, prompt-injection rule)
     plus one file per task. 28 offline tests, including every fallback path with a fake Claude.
   Implementation validation is complete: real full editions have been reviewed and offline tests cover
   forced failures producing `reduced`, `partial` and `links` editions. Console cost reconciliation remains
   open under *Current status*.

4. **Go live** ✅ **Done:** the public repo, HTTPS, Pages, production keys, root-site link and daily
   publishing are established at https://a403.space/times/.
   - ✅ Fix HTTPS for `a403.space` (see *Hosting*).
   - ✅ Console workspace and key configured; hard stop now $50. IsThereAnyDeal app/key registered and in use.
   - ✅ `gh repo create andre-larsson/times --public`, pushed.
   - ✅ Enable Pages (`build_type=workflow`). Add the `ANTHROPIC_API_KEY` and `ITAD_API_KEY` secrets.
   - ✅ "Check sources", links editions and full AI editions have run in production.
   - ✅ Verify `https://a403.space/times/`, then link it from the root launcher (done 2026-11-03).

   Daily publishing now targets 07:00 Swedish time, with the Raspberry Pi dispatch backup set up on
   2026-11-06 (see *Workflow*).

5. **Discovery** (web search). Measure the real cost per depth.
   - ✅ **Built 2026-11-07:** `newsroom/discover.py` + `prompts/discover.md`. One Opus call
     with the API's `web_search_20250305` and `web_fetch_20250910` tools (`max_uses` per depth, each page capped
     at `search.fetch_tokens`, 6,000) and a strict `report` tool for the answer, since web search always adds
     citations. It sees the ~150 headlines the feeds and the last two editions already have, and looks for up to
     N important stories from the last 36 hours that are missing. A find is kept only if a search or fetch
     actually returned its address and the feeds don't already have the page or the story.
   - Depths (`search.depths`): light 3 searches / 3 fetches / 4 finds, normal 6 / 5 / 6, deep 12 / 10 / 10.
   - **Measuring:** the manual **Measure discovery** workflow (the API key lives only in Actions) runs
     `python -m newsroom discover --depth … --runs N`. The run summary shows the cost, searches, fetches, tokens
     and finds of each run; the log has one JSON record per run. `--dry-run` fetches the feeds and shows the
     prompt for free. Measurement spend isn't in `data/usage.json`, only in the Console.
   - **First measurement, 2026-11-07** (Opus 5.5, one run per depth, [run](https://github.com/andre-larsson/times/actions/runs/42390294559)):

     | Depth | Cost | Searches / fetches | Tokens: input, cache write, cache read, output | Kept | Per month if daily |
     |---|---|---|---|---|---|
     | light | $0.33 | 3 / 1 | 9k, 45k, 75k, 1k | 0 (its one find wrongly dropped, see below) | ~$9.90 |
     | normal | $0.49 | 6 / 1 | 9k, 66k, 141k, 2k | 2 | ~$15 |
     | deep | $0.85 | 12 / 0 | 9k, 110k, 350k, 3k | 5 | ~$25.70 |

     - **Where the money goes:** cache writes, about 70% of every run. Each search adds 9–15k tokens of results,
       which the server-side search loop writes to the prompt cache at $5/M; searches themselves are $0.01.
       Cost grows roughly linearly with searches, so deep is the cheapest per find ($0.17 against $0.25).
     - **The finds were real misses:** none of the seven was in any edition this week, among them OpenAI's
       GPT-6 Cyber (its first model rated Critical for cyber risk), a METR report on AI speeding up AI research,
       a 16-month DigiCert data exposure and a Barracuda pre-auth root exploit chain.
     - **Opus barely fetches** (0–1 of the allowed 3–10). Once it fetched a blog's front page and took an
       article's link from it; the check only trusted search results, so that find was dropped. Links on a
       fetched page now count too.
   - **Second round, 2026-11-07** (six runs, $2.82; both rounds $4.48), same day's feeds:

     | Variant | Runs | Avg cost | Cache write | Kept | Per find | Per month if daily |
     |---|---|---|---|---|---|---|
     | light, Opus | 2 | $0.34 ($0.33–0.35) | 45–48k | 0, 4 | $0.17 | ~$10.30 |
     | normal, Opus | 1 | $0.49 | 66k | 2 | $0.25 | ~$15 |
     | deep, Opus | 2 | $0.86 ($0.85–0.86) | 110–114k | 5, 4 | $0.19 | ~$26 |
     | normal, Sonnet | 1 | $0.26 | 66k | 2 | $0.13 | ~$7.90 |
     | deep, Sonnet | 1 | $0.47 | 113k | 2 | $0.23 | ~$14.20 |
     | **normal, Opus, dynamic filtering** | 1 | **$0.32** | 29k | 4 | **$0.08** | **~$9.70** |
     | deep, Opus, dynamic filtering | 1 | $0.55 | 45k | 5 | $0.11 | ~$16.80 |

     - **Cost is steady:** repeat runs differed by 3–7%. It is set by the number of searches, not the day.
     - **Dynamic filtering** (`web_search_20260318`, `web_fetch_20260318`) cut cache writes by 55–60% and the cost by
       35%, and Opus fetched more pages with it (6 at deep) and kept more finds. Slower (40–85 s), which doesn't
       matter here.
     - **Sonnet** halves the price but picks worse: two of its four finds were AI-stock and Congress stories, and
       deep kept only 2 from 12 searches. Opus kept model releases, research and security incidents.
     - **Every run found GPT-6 Cyber.** Half of all finds were security stories (The Hacker News, BleepingComputer,
       SecurityWeek, watchTowr): the feeds have no security source, which a free RSS feed would fix.
     - **Recommendation:** `normal` with dynamic filtering, in every full edition: ~$0.32 a run, ~$9.70 a month,
       which fits the room left in the $35 target (since 2026-11-09: $40).
   - ✅ **In the edition from 2026-11-08:** `normal` with dynamic filtering, in every full edition (not `reduced`,
     not on the claude-code backend), after the rule ranking and before triage. Finds join the candidates as
     ordinary items and go through triage and the editor; a failed discovery is noted in the reason and the
     edition goes on without it. The edition JSON keeps `discovery` (depth, searches, fetches, cost, queries,
     kept and dropped URLs). `budget.per_run_usd` went from $1.25 to $2.00, since an edition, discovery and a
     column together come to about $1.25. (And to $3.00 with the Botroom on 2026-11-09: on a column day with a
     newcomer a run comes to about $2, and a newcomer that fails three rounds costs up to $2.60.) The Hacker News and BleepingComputer joined the feeds the same day.
   - **Review around 2026-11-15:** half of the measured finds were security stories, which the two new feeds now
     bring in for free, so discovery may find less for the same ~$0.32 (its cost follows its searches, not its
     finds). Each edition's `discovery` block (searches, cost, kept and dropped URLs) shows how many finds a week
     made the paper; keep it, cut it to `light` or every other day, or turn it off.

6. **The Botroom** ✅ **Built 2026-11-09** (see *The Botroom* above). The prototype's prompts, cast, roster and
   newcomer steps, now with a stored roster, a launch batch, the pages and the gates. 115 offline tests (a fake
   Claude for the forum and newcomer tasks).
   - **Day one, 2026-11-09,** written on the subscription (`forum --llm claude-code`) for the morning's edition
     and committed by hand: 32 comments in 6 threads by 10 of the 12 around, 16 calls, a minute, every bot
     returning exactly the comments it was cast for. $0.13 at API prices on `claude -p`, 87% Sonnet; `claude -p`
     writes each whole call to the 1-hour cache, while the API caches only the shared system prompt (5 minutes),
     so expect ~$0.08 a day there (~$2.50 a month). The workflow writes every day after that on the API.
   - **Schemas:** the prototype's `minItems`/`maxItems` with exact counts are out (structured outputs on the API
     take only 0 or 1), so the count sits in each array's description and the code caps what comes back.

7. **Tune and polish** — **ongoing**, with the actionable checklist under *Current status*.
   - Remaining: editorial and Botroom quality review, discovery value review, cost reconciliation and
     measurements, first scheduled engagement outputs and the month-long deals cadence check.
   - Optional, not scheduled: an editor's note, additional daily editions and extra AI/developer feeds.
     Search is built (2026-11-06); Batch API was dropped (2026-11-11, see *Open decisions*).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Spend exceeds the target | Pacing → `reduced` → links; $50 workspace hard stop; per-run cap |
| Looking too much like Expressen | Own logo, palette, fonts and layout; only general tabloid conventions are borrowed |
| Quiet days look empty, or busy days get bloated | Newsworthiness thresholds + editor + min/max per tier |
| Same event covered by several articles | Triage groups them; featured stories combine their sources |
| PCMag only via Google News (redirect links, little text) | Mostly briefs; fine for a minor source |
| Datacenter IPs blocked by some sources | Re-checked from Actions in phase 2; excerpt fallback; Google News as a backup route |
| Steam data is an unofficial endpoint | Graceful fallback (the block hides itself); IsThereAnyDeal and the feeds cover the rest |
| No Metacritic or OpenCritic API | Both averages via IsThereAnyDeal's game info; outlets' own scores from feeds or the review page's schema.org data; Steam rating alongside |
| Video blurbs based only on title and description | Framed as "Watch" teasers, not reviews |
| Deals advice that's wrong or out of date | Price and check time shown ("Prices checked Tuesday 07:05" between checks); ended deals dropped every edition; "prices change"; lowest-ever data from IsThereAnyDeal; no affiliate links |
| Summaries state things the source doesn't say | Prompts limit Claude to the provided text; "By Claude (AI)" byline; source links |
| Prompt injection from fetched pages | Writing calls have no tools; JSON-schema outputs; sources always linked. Discovery, the one call with tools, can only search and read; its finds must link a page the tools returned, and then go through triage like any feed item |
| Key secrets in a public repo | Not exposed to fork PRs; no `pull_request` trigger; Anthropic workspace capped at $50 |
| Copyright | Summaries in my own words; briefs from short excerpts; store and YouTube images only (v1); `noindex` |
| Late or dropped cron runs, 60-day auto-disable | Hourly due-check; data commits + enable call; Pi as last resort |

## Open decisions

Decided since the previous revision:
- **Batch API: not doing it** (2026-11-11). It gives 50% off tokens, but a batch is asynchronous: most finish
  within an hour, with no guarantee short of 24 hours.
  - Triage, the editor and the writing depend on each other. So a run would either wait and poll (past the
    job's 20-minute timeout, up to the 6-hour limit for GitHub-hosted jobs, while the `edition` concurrency
    group holds back redeploys), or split into a submit run and a collect run with pending state in `data/`.
  - Either way the edition arrives later than 07:05, at a time that can't be predicted.
  - The saving is small: ~$5–6 a month on the edition's writing calls, ~$10 at most with the column and quiz
    (half of their measured cost). Discovery, the largest item, is a multi-turn search loop that doesn't fit a
    batch.
  - Every call stays a synchronous `messages.create` with the system prompt cached.
- **Deals twice a week** (2026-11-10): checked Tuesday and Friday, carried over in between (see *Deals section*).
- **Weather home:** Lund (2026-11-10), was Stockholm. The schedule stays on Stockholm time (`Europe/Stockholm`).
- **Botroom:** built and live from 2026-11-09, with a launch batch of four newcomers made in the simulation.
  About $4 a month before caching (comments ~$3.70, newcomers ~$0.35). Newcomers weekly from 2026-11-15:
  ~$1.20 a month for about five months, then ~$3.30.
- **Budget:** $40/month target since 2026-11-09 (measured ~$32.50 a month with everything on; $35 from
  2026-11-07, $20 before), $50 hard stop in the Console (was $25). The paper already runs ~$21 a month (editions
  ~$13.70 measured, column ~$4, quiz ~$3); this leaves room for the Botroom (~$4) and daily discovery (`normal` with dynamic filtering, ~$9.70 measured).
- **I Dream of Indie Games:** YouTube channel and blog review feed found.
- **News preview images:** off for now. News stories use typographic covers; games and videos use Steam
  and YouTube images.
- **Language:** Python for both the pipeline and the Jinja2 rendering. The alternatives considered were
  TypeScript + Astro, a Python pipeline with an Astro site, a React SPA, and Hugo or 11ty.
  - The pipeline is the hard part, and Python has the strongest tools for it (`trafilatura`,
    `feedparser`, the Anthropic SDK).
  - The edition JSON files are the contract between pipeline and renderer, so the renderer could be
    swapped later without touching the pipeline.
