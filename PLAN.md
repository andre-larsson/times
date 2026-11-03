# The 403 Times: Plan

> *Access Granted*

A personal AI newspaper at **https://a403.space/times/**, covering **AI**, **tech** (developer news in the
Hacker News style, plus hardware), **gaming** (PC first) and **deals**. It looks and feels like a real
Swedish evening tabloid, with its own identity. Claude writes English stories from the day's sources and
links back to them. One edition every morning, paid for with the API credits included in my Max plan,
**targeting about $20/month**. With no budget or credits left, it still publishes, as a "links edition".

## Decisions so far

| Area | Choice |
|---|---|
| Name | **The 403 Times**, tagline **"Access Granted"** (my domain `a403.space`; HTTP 403 = Forbidden) |
| URL | **`https://a403.space/times/`**: a project Pages site under my root site's custom domain |
| Repo | New public repo **`andre-larsson/times`** (personal account, not the work org) |
| Sections | **AI** · **Tech** · **Gaming** · **Deals** |
| Frequency | **One edition a day**, 06:30 Swedish time (`Europe/Stockholm`, so daylight saving is handled) |
| Edition shape | 1–3 **featured** · 3+ **medium** · 10+ **briefs**, plus the **gaming** and **deals** sections, all sized by how much news there is |
| Look | **Tabloid-style news site**, inspired by Swedish evening papers like Expressen but **not a copy**: own logo, colors, fonts and layout |
| Language | **English** (Swedish sources such as MISSIL are summarized in English) |
| Build / hosting | GitHub Actions → GitHub Pages (`actions/deploy-pages`) |
| AI | Claude API via the Python `anthropic` SDK. **Opus writes everything; Haiku only sorts the pile** |
| Budget | **~$20/month** of the included $100/month credits (they refresh on the 25th). Server-side hard stop at $25 |
| No budget or credits | **Links edition** (default) or skip |
| Code / storage | Python 3.12+ (3.13 pinned) + Jinja2, httpx, feedparser. JSON in `data/` committed to the repo; HTML never committed |

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
| **PCMag** | Direct feed blocked by bot protection (403). Use **Google News search for pcmag.com** instead: headline + short excerpt, so mostly briefs | ⚠️ workaround |
| Extras for AI depth (optional) | Simon Willison's Weblog, Hugging Face blog, OpenAI / Google DeepMind blogs, Lobsters, LWN | to check |

Hacker News stories are split between **AI** and **Tech**: triage assigns each one a section, or drops it.
Tech stories carry a sub-kicker such as **DEV**, **HARDWARE** or **SECURITY**.

### Gaming

| Source | How | Status |
|---|---|---|
| **MISSIL** (missil.se) | RSS `missil.se/feed` (Swedish → summarized in English). Reviews (`/spelrecensioner/`) carry a score ("Betyg 5 av 10"); film news and blogs skipped. Links edition: reviews only | ✅ |
| **PC Gamer** | RSS `pcgamer.com/feeds.xml`; reviews recognized by their `…-review/` URLs | ✅ |
| **Rock Paper Shotgun** | RSS `/feed` and **`/feed/reviews`** (the "Bestest Bests" tag becomes the score badge). `/feed/deals` dropped: mostly hardware, often weeks old | ✅ |
| **gameranx** | YouTube channel RSS (no API key needed) | ✅ |
| **I Dream of Indie Games** | YouTube channel RSS (`UC_HX1n5iojK-xjy9WxfxXhg`; Shorts skipped) + **written reviews** from `idreamofindie.com/blog-feed.xml` (posts are infrequent) | ✅ |
| Twitch (both channels) | Not used: live streams aren't news, and their YouTube uploads cover the same content | — |
| **Steam store data** | Store search in JSON mode for app lists (**popular new releases** by date, **most wishlisted**, **popular specials**), then `IStoreBrowseService/GetItems` for release dates, user-review labels, prices and art, 50 apps per call. No key. (The older `appreviews` endpoint now redirects to the store front, and `featuredcategories` only lists the newest, mostly unknown, releases.) Unofficial but widely used | ✅ |
| **Metacritic** | Feed removed ("410 Gone"), no public API, and scraping would go against its terms. **Link out only:** a "Metacritic →" search link per game | ❌ link only |
| OpenCritic (optional) | Has an API with a key; terms and limits to check in phase 2. Would add aggregate scores | to check |

### Deals

| Source | How | Status |
|---|---|---|
| **IsThereAnyDeal** | Official API (`/deals/v2` with a JSON filter: cut ≥ 50%, within 10% of the historical low, games only, Steam ≥ 80% with ≥ 500 reviews; then `/games/info/v2` for Steam rating and Metascore). Free key by registering an app at isthereanydeal.com; personal and public use allowed; 1000 requests per 5 minutes. Store links: Steam's own page for Steam deals, otherwise the ITAD game page (no affiliate redirects). Credited on the page. **Coded from the API spec; not yet run with a real key** | ⏳ key needed |
| Steam specials | Popular games on sale. **Fallback** when there's no ITAD key: same cut and rating filters, but no lowest-ever data | ✅ |

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
- On quiet days it prints fewer stories rather than padding. There's always at least one featured lead.
- A GTA VI-size gaming story can take the front-page lead.

### Gaming section

| Block | Count | Content |
|---|---|---|
| **New on PC** | 3–10 | PC games released on Steam in the last ~7 days: art, date, Steam user rating, one-line blurb, links to reviews, "Steam →" and "Metacritic →" |
| **Reviews** | 3–10 | Reviews from PC Gamer, RPS, MISSIL… in the last ~3 days, grouped per game: outlet, score as stated (or the RPS "Recommended" badge), one-line verdict, link |
| **Console spotlight** | 0–3, often empty | Only console-first releases above a high notability bar (GTA VI, an Ocarina of Time remake): announcements, release dates, launch week, review round-ups |
| **Coming soon** | ≤ 8 | Notable upcoming releases with dates. PC games from Steam's upcoming list; big console games added when the news states a date. Kept in `data/games_watchlist.json` |
| **Watch** | 2–4 | New videos from gameranx and I Dream of Indie Games: thumbnail, title, one-line blurb based on the video's title and description (no transcripts) |
| **Gaming news** | ≤ 6 | Briefs from MISSIL, PC Gamer, RPS |

### Deals section (written as shopping news, not ads)

| Block | Count | Content |
|---|---|---|
| **Deal of the day** | 1–2 | A short article (~150 words): what the game is, how good reviewers and Steam users say it is, the price versus its lowest ever, when the deal ends, and a clear **Buy / Wait / Skip** verdict with who it's for |
| **More deals** | 5–10 | One-line advice per deal, with a price tag showing the regular price struck through, the sale price, the discount and a "Lowest ever" badge |

- **Picking deals:** IsThereAnyDeal deals for Sweden (prices in the local currency), filtered to
  at or near the lowest price ever, a minimum discount, and well-reviewed games (Steam rating, review scores).
- **Links:** plain store links, no affiliate links.
- **Labels:** "Price checked 06:30. Prices change." Each deal is credited to IsThereAnyDeal.
- **Cost:** written in one Opus call for the whole section.

## Look and feel: a real tabloid news site

Inspired by the conventions of Swedish evening papers (Expressen, Aftonbladet). **Nothing is copied:** the
logo, color palette, fonts, icons and exact layout are all our own.

**Brand**
- **Masthead:** a solid black bar with the **"The 403 Times"** logotype in heavy condensed type.
- **"403" badge:** the number is set as an amber, status-code-style badge.
- **Tagline:** *Access Granted* in small caps.
- **Above the masthead:** a thin utility bar with the date, "Morning edition" and "Updated 06:31".

**Type**
- Headlines in a **heavy condensed sans**, large and tightly spaced.
- Story text in a readable serif, with a bold dek (the subheadline).
- Open-licensed fonts, **self-hosted** in the repo, so the site makes no third-party font requests.

**Color**
- Black, white and newsprint gray, with **one signature accent (403 amber)**.
- Every section has its own label color for kickers and section bands (e.g. AI violet, Tech cyan,
  Gaming green, Deals magenta). The exact palette gets decided in phase 1.

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
│  Front   AI   Tech   Gaming   Deals   Archive                            │
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
- **Last step:** once it's verified live, link it from the root launcher and redeploy the root site.
- **HTTPS is broken on `a403.space` (found 2026-11-03).** GitHub never issued a certificate for the domain
  (`https_certificate: null`), so `https://a403.space/...` shows a `*.github.io` certificate and browsers
  warn. DNS is correct (four GitHub A records, `www` CNAME). Fix before go-live: in the root repo's Pages
  settings, remove and re-add the custom domain, wait for the certificate, then tick "Enforce HTTPS". Until
  then the site works over `http://`. Page links are relative to `/times/`, so only the feed's absolute URLs
  depend on it.

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
1. **Target ($20):** `budget.monthly_usd: 20`. My own tally in `data/usage.json` (token usage × the price
   table), paced across the calendar month.
2. **Hard stop ($25):** a Console workspace `times` with a $25/month spend limit, holding the API key.
   This limit also resets on the 1st.
3. **Backstop:** the credits themselves. With no card and auto-reload off, nothing can ever be charged.

**Pacing:** calendar month, not the credit cycle. The paper uses at most $25 of the $100, so the refresh
date doesn't matter. If other projects ever empty the balance, the pre-run probe sees "credit balance too
low" and publishes a links edition.

## Cost estimate and tuning knobs

Prices: Opus 5.5 is $4 in / $20 out per million tokens; Haiku 5.5 is $0.10 / $0.50; web search is $0.01 per search.

| Step, one edition a day | Model | Quiet day | Busy day |
|---|---|---|---|
| Triage ~300 candidates (batched) | Haiku | $0.01 | $0.01 |
| Editor: assign tiers | Opus | $0.05 | $0.05 |
| Featured (~$0.05 each) | Opus | 1 → $0.05 | 3 → $0.15 |
| Medium (~$0.02 each) | Opus | 3 → $0.06 | 6 → $0.12 |
| Briefs (one batched call) | Opus | $0.02 | $0.04 |
| Gaming: blurbs, verdicts, video blurbs (one batched call) | Opus | $0.04 | $0.06 |
| Deals: deal of the day + more deals (one call) | Opus | $0.04 | $0.06 |
| Discovery, depth `light` (3 searches, 3 fetches) | Opus | $0.25 | $0.25 |
| **Per day / per month** | | **~$0.52 / ~$16** | **~$0.74 / ~$22** |

- A month of busy days would run slightly over $20. The pacing guard handles that by making some
  editions `reduced` (no discovery, fewer stories), so the month lands at about $20.
- Discovery is the largest single item. Setting `search.discovery_every_days: 2` saves ~$4/month.
- Rough estimates; phases 3 and 5 measure the real numbers.

| Knob | Config | Default |
|---|---|---|
| Editions per day | `schedule.editions` | `["06:30"]` |
| Story counts | `edition.featured / medium / briefs` | 1–3 / 3–6 / 10–20 |
| Newsworthiness bar | `edition.*.min_newsworthiness` | 4.5 / 3.5 / 2.5 |
| Gaming blocks | `gaming.*` | see the gaming section above |
| Deals | `deals.featured / more / min_cut / near_low_pct / min_rating` | 1–2 / 5–10 / 50% / 10% / "Very Positive" |
| Search depth and frequency | `search.depth`, `search.discovery_every_days` | `light`, 1 |
| Models | `models.*` | Opus everywhere except Haiku triage |
| Budget | `budget.monthly_usd` | 20 |

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
│                 MISSIL · PC Gamer · RPS (main, reviews, deals) · YouTube channel feeds
│                 Steam store data · IsThereAnyDeal deals
│   2. normalize  canonical URL, title, excerpt, source, time, signals, language
│   3. dedupe     against data/seen.json; age limits
│   4. rank       rule-based (signals, recency, keywords, number of sources) → every mode
│   ── AI modes ──
│   5. discover   Opus + web_search/web_fetch (depth preset)
│   6. triage     Haiku: section, sub-kicker, newsworthiness 1–5, same-event grouping, keep/drop
│   7. edit       Opus editor: tiers for AI/Tech (+ any huge gaming story)
│   8. extract    full text for featured and medium stories
│   9. write      Opus: featured and medium (one call each) · briefs (one batched call) ·
│                 gaming (one batched call) · deals (one call)
│   ───────────────
│  10. save       data/editions/YYYY/MM/DD.json, games_watchlist.json, usage.json, seen.json
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
│   ├── budget.py  preflight.py  extract.py  watchlist.py      (phase 3)
│   ├── llm.py                # anthropic client, structured outputs, cost tally, error classes
│   ├── discover.py  triage.py  editor.py
│   ├── writers.py            # featured / medium / briefs / gaming / deals prompts + schemas
│   └── render.py
├── prompts/
├── templates/                # base, front, section, gaming, deals, article, archive, 404, feed.xml
├── static/                   # style.css, fonts/ (self-hosted, open-licensed), logo.svg
├── data/  seen.json  usage.json  games_watchlist.json  editions/2026/11/03.json
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
  editions: ["06:30"]

edition:
  featured: { min: 1, max: 3,   words: 350, max_sources: 3, min_newsworthiness: 4.5 }
  medium:   { min: 3, max: 6,   words: 130, min_newsworthiness: 3.5 }
  briefs:   { min: 10, max: 20, words: 35,  min_newsworthiness: 2.5 }

gaming:
  new_on_pc:         { min: 3, max: 10, window_days: 7 }
  reviews:           { min: 3, max: 10, window_days: 3 }
  console_spotlight: { max: 3, min_notability: 4.5 }
  coming_soon:       { max: 8, horizon_days: 180 }
  watch:             { max: 4 }
  news:              { max: 6 }

deals:
  country: SE
  featured: { min: 1, max: 2 }
  more:     { min: 5, max: 10 }
  min_cut_pct: 50
  near_low_pct: 10                  # within 10% of the lowest price ever
  min_steam_rating: "Very Positive"

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

budget:
  monthly_usd: 20                   # paced over the calendar month, like the workspace spend limit
  pace_allowance_usd: 2
  per_run_usd: 1.25
  when_over_pace: reduced

llm:
  when_unavailable: links

sources:
  hackernews: { front_page: true, min_points: 100 }
  feeds:
    - { name: Ars Technica,       url: "https://feeds.arstechnica.com/arstechnica/index", sections: [ai, tech] }
    - { name: TechRadar,          url: "https://www.techradar.com/feeds.xml",             sections: [ai, tech] }
    - { name: Tom's Hardware,     url: "https://www.tomshardware.com/feeds.xml",          sections: [tech] }
    - { name: MISSIL,             url: "https://www.missil.se/feed/", sections: [gaming], language: sv }
    - { name: PC Gamer,           url: "https://www.pcgamer.com/feeds.xml",               sections: [gaming, tech] }
    - { name: Rock Paper Shotgun, url: "https://www.rockpapershotgun.com/feed",           sections: [gaming] }
    - { name: RPS Reviews,        url: "https://www.rockpapershotgun.com/feed/reviews",   sections: [gaming], kind: reviews }
    - { name: RPS Deals,          url: "https://www.rockpapershotgun.com/feed/deals",     sections: [deals] }
  google_news:
    - { name: PCMag, query: "pcmag.com when:2d", sections: [tech, ai] }
  youtube:
    - { name: gameranx,               channel_id: "UCNvzD7Z-g64bPXxGzaQaa4g" }
    - { name: I Dream of Indie Games, channel_id: "TBD" }
  steam: { cc: se, lists: [new_releases, top_sellers, coming_soon, specials] }
  itad:  { enabled: true }          # needs the ITAD_API_KEY secret

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
                     "image": "steam capsule url", "blurb": "…", "review_ids": ["r1"], "metacritic_search": "…" } ],
    "reviews": [ { "id": "r1", "game": "…", "outlet": "PC Gamer", "score": "82", "verdict": "…", "url": "…" } ],
    "console_spotlight": [ { "game": "…", "platforms": ["ps5"], "headline": "…", "summary": "…", "sources": [] } ],
    "coming_soon": [ { "game": "…", "platforms": ["pc"], "date": "2026-11-14", "date_precision": "day", "url": "…" } ],
    "watch": [ { "channel": "gameranx", "title": "…", "url": "…", "thumbnail": "…", "blurb": "…" } ],
    "news": [ { "headline": "…", "summary": "…", "url": "…" } ]
  },
  "deals": {
    "featured": [ { "game": "…", "shop": "Steam", "price": 9.99, "regular": 39.99, "currency": "EUR", "cut": 75,
                    "lowest_ever": true, "expires": "…", "verdict": "buy", "headline": "…", "body": "…", "url": "…" } ],
    "more": [ { "game": "…", "price": 4.99, "regular": 19.99, "cut": 75, "lowest_ever": false, "advice": "…", "url": "…" } ],
    "checked_at": "2026-11-03T05:30:00Z"
  },
  "links": [ { "section": "tech", "title": "…", "url": "…", "source": "…", "excerpt": "…", "rank": 0.8 } ]
}
```

**seen.json rules:** items dropped by triage are marked seen right away; items written up are marked
seen once written; link-only items stay unseen, so a later full edition can still use them.

## Pages

| Page | Content |
|---|---|
| `/times/` | Today's front page (layout above) |
| `/times/ai/`, `/times/tech/` | Section front: colored band, recent featured and medium stories, briefs |
| `/times/gaming/` | All gaming blocks, ~2 weeks of history, the full "Coming soon" list |
| `/times/deals/` | Today's deals plus recent ones still active |
| `/times/YYYY/MM/DD/<slug>/` | Article page (see *Look and feel*) |
| `/times/archive/` | Past editions by date, mode labeled |
| `/times/feed.xml` | Atom feed |

- `noindex` on every page.
- Footer: "Written by Claude from the linked sources; may contain errors. Deals data: IsThereAnyDeal."
- 404 page: "403: you're allowed in, but this page doesn't exist."

## Workflow: `.github/workflows/edition.yml`

The real file is in the repo; this is its shape.

| Trigger | What runs |
|---|---|
| `schedule: "35 * * * *"` (hourly) | `generate` checks whether a slot in `schedule.editions` (Stockholm time) has passed without an edition. Usually not, and the run ends in seconds. At :35 the 06:30 slot is caught at 06:35, plus GitHub's usual cron delay |
| `workflow_dispatch` with `mode` | `auto` behaves like the schedule; `full`, `reduced`, `links` or `skip` force a run now and replace today's edition |
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

2. **Sources, ranking and the links edition** (local, $0). ✅ **Built 2026-11-03**, two checks left.
   - Fetchers for every source: HN, eight feeds, PCMag via Google News, both YouTube channels, Steam
     (three lists) and IsThereAnyDeal. A failing source is reported and skipped, never fatal.
   - Rule-based ranking (`rank.py`): section assignment (AI keywords, categories and URL paths), junk and
     shopping filters, gadget-review penalty, same-story clustering, recency + HN points + source weight.
   - `generate --mode links` builds a complete paper; `generate` does the due check and writes
     `GITHUB_OUTPUT` and a source-status table to the Actions step summary.
   - Both workflows written. 18 offline tests.
   - **Left:** run IsThereAnyDeal with a real key (until then deals come from Steam specials), and the
     "Check sources" run from an Actions runner, which needs the GitHub repo.

   *Done when* `generate --mode links` produces a real, useful paper with no AI. (It does: a real links
   edition rendered and reviewed on desktop and phone on 2026-11-03.)

3. **Claude: triage, editor, writers, deals advice, budget, preflight and fallback** (local, cents)
   *Done when*:
   - a real full edition has a sensible tier split;
   - `usage.json` matches the Console's Cost page;
   - forced failures produce correct `reduced`, `partial` and `links` editions.

4. **Go live**
   - Fix HTTPS for `a403.space` (see *Hosting*).
   - Create the Console workspace ($25 limit) and its key. Register an IsThereAnyDeal app for its key.
   - `gh repo create andre-larsson/times --public --source . --push`.
   - Enable Pages (`build_type=workflow`) and add the `ANTHROPIC_API_KEY` and `ITAD_API_KEY` secrets.
   - Run "Check sources", then trigger Edition with `mode=links`, then `mode=full`.
   - Verify `https://a403.space/times/`, then link it from the root launcher.

   *Done when* the next 06:30 edition publishes by itself.

5. **Discovery** (web search). Measure the real cost per depth.

6. **Tune and polish**
   - After 1–2 weeks: thresholds, sources, prompts and deal filters, against real editions and spend.
   - Then: Batch API, an "editor's note", search, more editions if wanted.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Spend exceeds the target | Pacing → `reduced` → links; $25 workspace hard stop; per-run cap |
| Looking too much like Expressen | Own logo, palette, fonts and layout; only general tabloid conventions are borrowed |
| Quiet days look empty, or busy days get bloated | Newsworthiness thresholds + editor + min/max per tier |
| Same event covered by several articles | Triage groups them; featured stories combine their sources |
| PCMag only via Google News (redirect links, little text) | Mostly briefs; fine for a minor source |
| Datacenter IPs blocked by some sources | Re-checked from Actions in phase 2; excerpt fallback; Google News as a backup route |
| Steam data is an unofficial endpoint | Graceful fallback (the block hides itself); IsThereAnyDeal and the feeds cover the rest |
| No Metacritic scores | Scores from the reviews themselves + Steam rating; Metacritic as a link; OpenCritic optional |
| Video blurbs based only on title and description | Framed as "Watch" teasers, not reviews |
| Deals advice that's wrong or out of date | Price and timestamp shown; "prices change"; lowest-ever data from IsThereAnyDeal; no affiliate links |
| Summaries state things the source doesn't say | Prompts limit Claude to the provided text; "By Claude (AI)" byline; source links |
| Prompt injection from fetched pages | Writing calls have no tools; JSON-schema outputs; sources always linked |
| Key secrets in a public repo | Not exposed to fork PRs; no `pull_request` trigger; Anthropic workspace capped at $25 |
| Copyright | Summaries in my own words; briefs from short excerpts; store and YouTube images only (v1); `noindex` |
| Late or dropped cron runs, 60-day auto-disable | Hourly due-check; data commits + enable call; Pi as last resort |

## Open decisions

None right now. Decided since the previous revision:
- **I Dream of Indie Games:** YouTube channel and blog review feed found.
- **News preview images:** off for now. News stories use typographic covers; games and videos use Steam
  and YouTube images.
- **Language:** Python for both the pipeline and the Jinja2 rendering. The alternatives considered were
  TypeScript + Astro, a Python pipeline with an Astro site, a React SPA, and Hugo or 11ty.
  - The pipeline is the hard part, and Python has the strongest tools for it (`trafilatura`,
    `feedparser`, the Anthropic SDK).
  - The edition JSON files are the contract between pipeline and renderer, so the renderer could be
    swapped later without touching the pipeline.
