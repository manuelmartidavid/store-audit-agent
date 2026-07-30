"""Session conduct — spec §3. No browser: these are the pure parts."""

from __future__ import annotations

from crawler.config import MIN_FETCH_INTERVAL_S
from crawler.session import Session

ORIGIN = "https://shop.test"


def test_a_declared_crawl_delay_raises_the_fetch_interval():
    session = Session(ORIGIN)
    assert session.honour_crawl_delay(10) == 10.0
    assert session.min_interval_s == 10.0


def test_a_delay_below_our_floor_never_lowers_it():
    """Invariant: brief §5 conduct is a floor. A store asking for less gets more."""
    session = Session(ORIGIN)
    assert session.honour_crawl_delay(0.2) == MIN_FETCH_INTERVAL_S
    assert session.min_interval_s == MIN_FETCH_INTERVAL_S


def test_no_declaration_leaves_the_floor_in_place():
    session = Session(ORIGIN)
    assert session.honour_crawl_delay(None) == MIN_FETCH_INTERVAL_S
    assert session.honour_crawl_delay(0) == MIN_FETCH_INTERVAL_S
