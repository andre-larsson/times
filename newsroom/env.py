"""Load KEY=VALUE lines from the project's git-ignored .env for local runs.

Real environment variables always win, so GitHub Actions secrets are never overridden. Keeping the
key here instead of exporting it from ~/.bashrc stops other tools (like Claude Code) from picking it up.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import ROOT


def load_dotenv(path: Path | None = None) -> list[str]:
    """Set variables from .env that aren't already set; return their names (never values)."""
    path = path or ROOT / ".env"
    if not path.is_file():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key.isidentifier():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
