"""Writes manifest.yaml, the provenance record for one capture (spec §8).

Written by hand rather than with a YAML library because the exact byte layout
is part of what gets hashed.

Invariant: an eval run only counts if it pins this manifest's hash along with
the prompt and rubric versions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import SCHEMA_MANIFEST, __version__
from .config import TEMPLATES, THROTTLING_PROFILE

_PENDING = "PENDING"


@dataclass
class Manifest:
    captured_at: str
    origin: str
    gate: str
    templates: dict[str, dict[str, str]] = field(default_factory=dict)
    crawler_version: str = __version__
    lighthouse_version: str | None = None
    axe_core_version: str | None = None
    chrome_version: str | None = None
    throttling: str = THROTTLING_PROFILE

    def to_yaml(self) -> str:
        """Render the manifest as YAML text."""
        lines = [
            f"schema: {SCHEMA_MANIFEST}",
            f"captured_at: {self.captured_at}",
            f"origin: {self.origin}",
            f"gate: {self.gate}",
            f"crawler_version: {self.crawler_version}",
            f"lighthouse_version: {self.lighthouse_version or _PENDING}",
            f"axe_core_version: {self.axe_core_version or _PENDING}",
            f"chrome_version: {self.chrome_version or _PENDING}",
            f"throttling: {self.throttling}",
            "templates:",
        ]
        for template in TEMPLATES:
            entry = self.templates.get(template, {})
            crawl = entry.get("crawl", "error")
            lighthouse = entry.get("lighthouse", "skipped")
            axe = entry.get("axe", "skipped")
            # Quoted because a bare `404:` parses as an integer key in YAML.
            lines.append(
                f'  "{template}": {{ crawl: {crawl}, lighthouse: {lighthouse}, axe: {axe} }}'
            )
        return "\n".join(lines) + "\n"

    def write(self, path: Path) -> str:
        """Write the manifest to `path` and return its sha256."""
        body = self.to_yaml()
        path.write_text(body, encoding="utf-8", newline="\n")
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
