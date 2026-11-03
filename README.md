# The 403 Times

*Access Granted.* A personal AI newspaper about AI, tech, PC gaming and deals, published at
<https://a403.space/times/>. A scheduled pipeline gathers the day's stories, Claude writes them up in
English with links to the sources, and the result is rendered as a static, tabloid-style site on
GitHub Pages.

See [PLAN.md](PLAN.md) for the full design: sources, budget, run modes, phases.

## Status

- **Phase 1 (design with sample data): done.** Templates, styles, the renderer and tests work against
  the sample editions in `tests/fixtures/`.
- Next: phase 2 (real sources and the no-AI "links edition"), then phase 3 (Claude).

## Run it locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                        # install dependencies
uv run python -m newsroom serve --fixtures     # render the sample editions and preview at http://127.0.0.1:8403/times/
uv run python -m newsroom render --fixtures    # render only, into _site/
uv run python -m newsroom serve --fixtures --front 2026-11-02   # preview the no-AI "links edition"
uv run pytest                                  # smoke tests: pages exist, internal links resolve, feed is valid
```

Without `--fixtures`, the commands read real editions from `data/editions/` (written by the pipeline
from phase 2 on).

## Layout

```
config.yaml          every tuning knob: schedule, story counts, sources, models, budget
newsroom/            Python package: `python -m newsroom <command>`
  render.py          edition JSON → static HTML in _site/
  serve.py           local preview server under the /times/ base path
templates/           Jinja2 templates (front, section, gaming, deals, article, archive, 404, feed)
static/              style.css, favicon, self-hosted fonts (SIL Open Font License)
tests/fixtures/      sample editions (made-up companies, games and outlets; links go to example.com)
data/                real editions, committed by the pipeline (from phase 2)
```

## Design notes

- Tabloid conventions (heavy condensed headlines, colored kickers, a dense mixed grid, a "Latest"
  column) with its own identity: black masthead, the amber "403" badge, Barlow Condensed headlines and
  Source Serif 4 for body text.
- News stories have no photos; the lead gets a typographic cover showing the story's key figure.
  Games and videos will use Steam and YouTube images.
- Light and dark mode follow the system setting. Every page is `noindex`.
