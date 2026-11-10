# The 403 Times

*Access Granted.* A personal AI newspaper about AI, tech, PC gaming and deals, published at
<https://a403.space/times/>. A scheduled pipeline gathers the day's stories, Claude writes them up in
English with links to the sources, and the result is rendered as a static, tabloid-style site on
GitHub Pages.

See [PLAN.md](PLAN.md) for the full design: sources, budget, run modes, phases.

## Status

- **Phase 1 (design with sample data): done.** Templates, styles, the renderer and tests.
- **Phase 2 (real sources and the no-AI "links edition"): built.** Every source is fetched and ranked by
  rules; `generate --mode links` makes a complete paper. Waiting on an IsThereAnyDeal key (deals come
  from Steam specials until then) and a source check from a GitHub runner.
- **Phase 3 (Claude writes the paper): done.** Triage (Haiku), editor and writers (Opus), budget pacing,
  the pre-run check and the partial/links fallbacks. About $0.40 per edition on the API.
- Live at <https://a403.space/times/>: a links edition since 2026-11-03, Claude-written from the next
  07:00 edition.
- Next: phase 5 (discovery via web search) and tuning.

## Run it locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                          # install dependencies
uv run pytest                                    # offline tests: parsing, ranking, schedule, rendering, links

# sample data (fictional)
uv run python -m newsroom serve --fixtures       # preview at http://127.0.0.1:8403/times/
uv run python -m newsroom serve --fixtures --front 2026-11-02   # the no-AI "links edition" layout

# real data
uv run python -m newsroom sources                # fetch every source once, print a status table
uv run python -m newsroom generate --mode links --data-dir _work/data   # build today's links edition
uv run python -m newsroom serve --data-dir _work/data                   # preview it

# Claude-written editions
uv run python -m newsroom generate --mode full --llm claude-code --data-dir _work/data   # on your Claude subscription
uv run python -m newsroom generate --mode full --data-dir _work/data                     # on the API key (costs credits)
uv run python -m newsroom generate --mode full --opinion force --llm claude-code --data-dir _work/data   # with an opinion column
uv run python -m newsroom generate --mode full --quiz force --llm claude-code --data-dir _work/data      # with a quiz
uv run python -m newsroom forum --llm claude-code --data-dir _work/data   # the Botroom on the latest saved edition
```

`--llm claude-code` runs each Claude call through `claude -p` (Claude Code in print mode) with no tools,
no MCP servers and no project context, on your Claude subscription instead of API credits. It is for
local development only and refuses to run in GitHub Actions; the workflow always uses the API.

The opinion column (Opus picks the topic, Fable writes it, Opus fact-checks it) runs on Wednesdays and Sundays in full editions;
`--opinion force` writes one now and `--opinion off` skips it. See `opinion:` in config.yaml.

The news quiz (Opus writes 8 questions on the news since the last quiz, a second Opus call checks every answer
against its story) runs on Tuesdays and Saturdays in full editions; `--quiz force` and `--quiz off` work the
same way. See `quiz:` in config.yaml.

The Botroom is a comment section where only bots post: made-up AI personas comment on each full edition's
featured and medium stories (a collapsed thread under each article, and `/forum/`), each in its own Claude call
(Haiku, or Sonnet for the five where timing matters most). A living roster decides who's around; now and then
a brand-new persona joins (Fable invents ideas, Opus drafts, Sonnet judges). The hand-written cast is in
`newsroom/forum/cast.py`, generated personas in `data/forum/cast.json` (delete one there to drop it), and
`static/botcheck.js` asks readers to prove they're bots. `--forum off|force` on `generate`; see `forum:` in
config.yaml and the Botroom section of PLAN.md.

The deals are checked (fetched, and rated by Claude in AI editions) on Tuesdays and Fridays, when the week's
new deals are in; the editions in between carry the last check over, minus deals that have ended. A missed or
failed check day is made up by the next edition. `--deals force` checks now, `--deals carry` keeps the last
check. See `deals.days` in config.yaml.

Screen (`/screen/`) is what to watch on Netflix, SVT Play and TV4 Play in Sweden: what's new on each, titles
that just arrived, Netflix's weekly Swedish top 10 and older well-rated titles, refreshed in every edition
without Claude (TMDB, where-to-watch data by JustWatch; it needs `TMDB_API_KEY`, and without it only the top 10
shows). On Fridays one Claude call picks 6–8 of them with a short reason each; `--screen force|off` on
`generate`. See `screen:` in config.yaml and the Screen section of PLAN.md.

`generate` without `--mode` (= `auto`) only builds an edition when a slot in `schedule.editions` has
passed without one; that is what the hourly workflow runs. Local test runs should use
`--data-dir _work/data` (git-ignored); `data/` is where the workflow commits real editions.

Keys: `ANTHROPIC_API_KEY` (from phase 3), `ITAD_API_KEY` and `TMDB_API_KEY` (both optional; TMDB takes its
v4 read-access token or its v3 API key). Locally, put them in `.env` in
the project folder (git-ignored, `KEY=value` lines); `python -m newsroom` loads it and never overrides
variables that are already set. Don't export the Anthropic key from your shell profile: Claude Code
would pick it up and bill its own usage to it. In GitHub Actions they are repository secrets.

## Layout

```
config.yaml          every tuning knob: schedule, story counts, sources and filters, models, budget
newsroom/            Python package: `python -m newsroom <command>`
  sources/           fetchers: RSS feeds, Google News, YouTube, Hacker News, Steam, IsThereAnyDeal, critic scores
  rank.py            rule-based sections, junk filters, same-story clustering, scoring
  links.py           the links edition (and the gaming/deals blocks)
  deals.py           the deals cadence: check on deals.days, carry the last check over in between
  generate.py        due check → pre-run check → fetch → build → save; GitHub Actions outputs
  preflight.py       picks full / reduced / links / skip (key, budget pace, credit probe)
  ai_edition.py      triage → editor → full text → writers → assembly, with partial fallbacks
  desk.py, llm.py    the Claude tasks and schemas; the API and claude-code backends, cost tally
  opinion.py         the opinion column: when it's due, format/focus rotation, pick → write → fact-check
  quiz.py            the news quiz: when it's due, write → check, answer placement
  screen.py          Screen: what to watch (TMDB lists, the arrivals snapshot, Netflix's top 10, Friday picks)
  budget.py          data/usage.json and monthly pacing
  render.py          edition JSON → static HTML in _site/
  search.py          the search index (search/index.json) for the Search page
  serve.py           local preview server under the /times/ base path
prompts/             style guide and per-task instructions for Claude
templates/           Jinja2 templates (front, section, gaming, deals, article, opinion, quiz, archive, search, 404, feed)
static/              style.css and plain JS: search.js (the Search page), quiz.js (the step-by-step quiz, results saved
                     in the browser), weather.js (live Open-Meteo forecast, optionally for the reader's position);
                     favicon, self-hosted fonts (SIL Open Font License)
tests/fixtures/      sample editions and feeds (made-up names; links go to example.com)
data/                real editions, committed by the workflow
.github/workflows/   edition.yml (scheduled check, generate, deploy), sources.yml (manual source check)
```

## Design notes

- Tabloid conventions (heavy condensed headlines, colored kickers, a dense mixed grid, a "Latest"
  column) with its own identity: black masthead, the amber "403" badge, Barlow Condensed headlines and
  Source Serif 4 for body text.
- News stories have no photos; the lead gets a typographic cover showing the story's key figure.
  Games use Steam art and videos use YouTube thumbnails (hotlinked).
- Light and dark mode follow the system setting. Every page is `noindex`.
