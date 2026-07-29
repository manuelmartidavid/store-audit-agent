"""Runs axe-core accessibility checks on a page during the capture visit (spec §7).

Returns standard axe results JSON with violations only.

Invariant: don't add severity mapping here — the triager does that. This layer
stays raw evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CANDIDATE_PATHS = (
    Path("node_modules/axe-core/axe.min.js"),
    Path("node_modules/axe-core/axe.js"),
)


def locate(root: Path) -> Path | None:
    """Find the installed axe-core script, or None if it isn't there."""
    for candidate in _CANDIDATE_PATHS:
        path = root / candidate
        if path.is_file():
            return path
    return None


def version(root: Path) -> str | None:
    """The installed axe-core version, or None if it can't be read."""
    package = root / "node_modules/axe-core/package.json"
    if not package.is_file():
        return None
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version")
    except (ValueError, OSError):
        return None


class Axe:
    """Holds the axe-core source so every template shares one disk read."""

    def __init__(self, root: Path) -> None:
        self.path = locate(root)
        self.version = version(root)
        self._source: str | None = None

    @property
    def available(self) -> bool:
        """True if axe-core was found on disk."""
        return self.path is not None

    def _load(self) -> str:
        """Read the axe-core source, caching it after the first call."""
        if self._source is None:
            assert self.path is not None
            self._source = self.path.read_text(encoding="utf-8")
        return self._source

    def run(self, page: Any) -> dict[str, Any] | None:
        """Run axe against the page as currently loaded. None on failure."""
        if not self.available:
            return None
        try:
            page.add_script_tag(content=self._load())
            # resultTypes:['violations'] is axe's own "violations only" switch:
            # standard result shape, smaller payload.
            return page.evaluate(
                """() => axe.run(document, {
                    resultTypes: ['violations'],
                    elementRef: false,
                    ancestry: true,
                })"""
            )
        except Exception:
            return None
