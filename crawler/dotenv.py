"""Minimal .env loader.

The storefront password lives in a gitignored .env (sabotage-spec §gate), but the
crawler reads os.environ — so something has to bridge the two. A real dependency
(python-dotenv) is overkill for `KEY=value` lines, and the password must never be
logged, so a tiny in-house parser that never echoes a value is the safer choice.

Rules, deliberately boring:
- `KEY=value`, one per line. `export KEY=value` is tolerated.
- `#` comments and blank lines ignored. A `#` inside a value is kept.
- Surrounding single/double quotes are stripped; nothing inside is expanded.
- **A value already present in the real environment always wins** — an exported
  var or a `--password-env` pointing at a live var is never clobbered by the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load(path: Path | str = ".env", *, override: bool = False) -> list[str]:
    """Load KEY=value pairs from `path` into os.environ.

    Returns the names of the keys applied (never the values). Missing file is not
    an error — a public store has no .env and that is fine.
    """
    file = Path(path)
    if not file.is_file():
        return []

    applied: list[str] = []
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied
