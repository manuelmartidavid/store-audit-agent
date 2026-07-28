"""robots.txt handling — spec §3.

Fetched first and respected. A disallowed template is recorded as
``blocked_by_robots``: a fact for the report, not a gap to route around.

Wraps :mod:`urllib.robotparser` so the crawler never has to care whether the file
was missing, empty, or served as a 500 — all three mean "nothing is disallowed",
and each is a different provenance note.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib import robotparser

from .config import ROBOTS_UA


@dataclass
class Robots:
    """A parsed robots.txt, or a permissive stand-in for one that wasn't served."""

    status: str  # fetched | absent | error
    http_status: int | None = None
    _parser: robotparser.RobotFileParser | None = None

    @classmethod
    def parse(cls, body: str, http_status: int | None = 200) -> "Robots":
        parser = robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        return cls(status="fetched", http_status=http_status, _parser=parser)

    @classmethod
    def permissive(cls, status: str = "absent", http_status: int | None = None) -> "Robots":
        return cls(status=status, http_status=http_status, _parser=None)

    def allows(self, url: str) -> bool:
        if self._parser is None:
            return True
        # Checked under our identifying UA first, then the wildcard group, so a
        # site that names us specifically wins over a generic rule.
        return bool(self._parser.can_fetch(ROBOTS_UA, url)) and bool(
            self._parser.can_fetch("*", url)
        )
