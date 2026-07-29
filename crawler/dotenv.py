"""Minimal .env loader that copies KEY=value lines into os.environ.

Rules:
- `KEY=value`, one per line. `export KEY=value` is allowed.
- Blank lines and `#` comments are skipped. A `#` inside a value is kept.
- Surrounding quotes are stripped; nothing inside is expanded.
- A variable already set in the real environment wins over the file.

Invariant: never log or echo a loaded value — this carries the storefront
password.
"""

from __future__ import annotations

import os
from pathlib import Path


def load(path: Path | str = ".env", *, override: bool = False) -> list[str]:
    """Load KEY=value pairs from `path` into os.environ.

    Returns the key names applied, never the values. A missing file is fine.
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
