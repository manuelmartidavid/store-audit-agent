"""axe-core integration — spec §7.

Injected into the same pages, in the same context, during the capture visit —
not on a second pass. Re-navigating six templates to re-run a scanner doubles the
request count against a store we do not own for no extra evidence.

Standard axe-core results JSON, raw violations only. No severity mapping: that is
the rubric's job via the triager, and doing it here would put an opinion in the
evidence base.
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
    for candidate in _CANDIDATE_PATHS:
        path = root / candidate
        if path.is_file():
            return path
    return None


def version(root: Path) -> str | None:
    package = root / "node_modules/axe-core/package.json"
    if not package.is_file():
        return None
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version")
    except (ValueError, OSError):
        return None


class Axe:
    """Holds the axe-core source once so six templates cost one disk read."""

    def __init__(self, root: Path) -> None:
        self.path = locate(root)
        self.version = version(root)
        self._source: str | None = None

    @property
    def available(self) -> bool:
        return self.path is not None

    def _load(self) -> str:
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
            # resultTypes:['violations'] is axe's own mechanism for "violations
            # only" — passes/incomplete/inapplicable come back as rule stubs, so
            # the shape stays standard while the payload stays bounded.
            return page.evaluate(
                """() => axe.run(document, {
                    resultTypes: ['violations'],
                    elementRef: false,
                    ancestry: true,
                })"""
            )
        except Exception:
            return None
