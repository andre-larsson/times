# AGENTS.md instructions for times (The 403 Times)

<INSTRUCTIONS>
- Primary goal: a personal AI newspaper published as a GitHub Pages project site at https://a403.space/times/ (repo `andre-larsson/times`, personal account, never the work org).
- Plan and decisions: PLAN.md (keep it in sync when decisions change).
- Language: Python 3.12, managed with uv. Rendering: Jinja2 → static HTML. No JS framework.
- Install: `uv sync`.
- Preview: `uv run python -m newsroom serve --fixtures` → http://127.0.0.1:8403/times/.
- Build: `uv run python -m newsroom render` (real data in data/) or `--fixtures` (sample data).
- Tests: `uv run pytest`. Run them after any template or renderer change; they check that every internal link resolves.
- Base path: all URLs come from `site.base_path` (/times/) via the `url()` template global. Never hard-code paths.
- Design system lives in static/style.css tokens (colors, spacing scale, type). Reuse tokens; don't add one-off values.
- Sample data in tests/fixtures/ must stay clearly fictional (made-up names, example.com links).
- Never commit secrets (ANTHROPIC_API_KEY, ITAD_API_KEY live in GitHub Actions secrets), _site/, or .env files.
- Deployment (from phase 4): GitHub Actions → actions/deploy-pages; verify the live URL after pushing, then link it from the root site andre-larsson.github.io.
</INSTRUCTIONS>
