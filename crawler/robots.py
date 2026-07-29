"""Reads robots.txt and answers whether a URL may be fetched (spec §3).

A missing, empty, or failed robots.txt all mean "nothing is disallowed".
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib import robotparser

from .config import ROBOTS_UA


@dataclass
class Robots:
    """A parsed robots.txt, or a permissive stand-in when none was served."""

    status: str  # fetched | absent | error
    http_status: int | None = None
    _parser: robotparser.RobotFileParser | None = None

    @classmethod
    def parse(cls, body: str, http_status: int | None = 200) -> "Robots":
        """Build a Robots from robots.txt text."""
        parser = robotparser.RobotFileParser()
        parser.parse(body.splitlines())
        return cls(status="fetched", http_status=http_status, _parser=parser)

    @classmethod
    def permissive(cls, status: str = "absent", http_status: int | None = None) -> "Robots":
        """Build a Robots that allows everything."""
        return cls(status=status, http_status=http_status, _parser=None)

    def allows(self, url: str) -> bool:
        """True if the URL may be fetched."""
        if self._parser is None:
            return True
        # Our own UA first, then the wildcard group, so a rule naming us wins.
        return bool(self._parser.can_fetch(ROBOTS_UA, url)) and bool(
            self._parser.can_fetch("*", url)
        )
