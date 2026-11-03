# AGENTS.md instructions for times (The 403 Times)

<INSTRUCTIONS>
- Primary goal: a personal AI newspaper published as a GitHub Pages project site at https://a403.space/times/ (repo `andre-larsson/times`, personal account, never the work org).
- Plan and decisions: PLAN.md (keep it in sync when decisions change).
- Language: Python 3.12+ (3.13 pinned in .python-version), managed with uv. Rendering: Jinja2 → static HTML. No JS framework.
- Install: `uv sync`.
- Preview: `uv run python -m newsroom serve --fixtures` → http://127.0.0.1:8403/times/.
- Build: `uv run python -m newsroom render` (real data in data/) or `--fixtures` (sample data).
- Real data locally: `uv run python -m newsroom sources` (status table), `generate --mode links --data-dir _work/data`, then `serve --data-dir _work/data`. Keep local runs in `_work/` (git-ignored); `data/` is written by the workflow.
- Tests: `uv run pytest`. Run them after any template, renderer or pipeline change; they are offline and check that every internal link resolves.
- Sources: a failing source must never stop a run (record it in the Harvest status). Use the shared `http.Client` (generic User-Agent, no personal details) and never log query strings (API keys).
- Base path: all URLs come from `site.base_path` (/times/) via the `url()` template global. Never hard-code paths.
- Design system lives in static/style.css tokens (colors, spacing scale, type). Reuse tokens; don't add one-off values.
- Sample data in tests/fixtures/ must stay clearly fictional (made-up names, example.com links).
- Never commit secrets (ANTHROPIC_API_KEY, ITAD_API_KEY live in GitHub Actions secrets), _site/, or .env files.
- Deployment (from phase 4): .github/workflows/edition.yml → actions/deploy-pages; verify the live URL after pushing, then link it from the root site andre-larsson.github.io. Pin actions to release commit SHAs at least two weeks old.
</INSTRUCTIONS>
