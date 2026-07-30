"""robots.txt handling — spec §3 and acceptance test §10.5."""

from __future__ import annotations

from crawler.robots import Robots

ORIGIN = "https://shop.test"


def test_a_disallowed_template_is_not_allowed():
    robots = Robots.parse("User-agent: *\nDisallow: /collections\n")
    assert not robots.allows(f"{ORIGIN}/collections/rookies")
    assert robots.allows(f"{ORIGIN}/products/card")
    assert robots.allows(f"{ORIGIN}/")


def test_a_rule_naming_the_crawler_specifically_is_honoured():
    robots = Robots.parse("User-agent: StoreAuditAgent\nDisallow: /cart\n")
    assert not robots.allows(f"{ORIGIN}/cart")
    assert robots.allows(f"{ORIGIN}/search?q=a")


def test_shopifys_default_disallows_are_honoured():
    robots = Robots.parse(
        "User-agent: *\nDisallow: /admin\nDisallow: /cart\nDisallow: /checkout\nAllow: /\n"
    )
    assert not robots.allows(f"{ORIGIN}/cart")
    assert robots.allows(f"{ORIGIN}/collections/all")


def test_a_missing_or_broken_robots_txt_is_permissive():
    for robots in (Robots.permissive("absent", 404), Robots.permissive("error")):
        assert robots.allows(f"{ORIGIN}/cart")


def test_an_empty_robots_txt_disallows_nothing():
    assert Robots.parse("").allows(f"{ORIGIN}/anything")


# --- Crawl-delay (design D6) -------------------------------------------------

def test_a_declared_crawl_delay_is_read():
    """Forest Whole Foods and Nalgene both declare 10 — normal for WordPress
    behind a caching plugin."""
    assert Robots.parse("User-agent: *\nCrawl-delay: 10\nAllow: /\n").crawl_delay_s == 10.0


def test_a_group_naming_the_crawler_wins_over_the_wildcard_group():
    body = (
        "User-agent: *\nCrawl-delay: 10\n\n"
        "User-agent: StoreAuditAgent\nCrawl-delay: 2\n"
    )
    assert Robots.parse(body).crawl_delay_s == 2.0


def test_the_wildcard_delay_applies_when_our_group_declares_none():
    body = (
        "User-agent: *\nCrawl-delay: 7\n\n"
        "User-agent: StoreAuditAgent\nDisallow: /admin\n"
    )
    assert Robots.parse(body).crawl_delay_s == 7.0


def test_a_delay_declared_for_some_other_bot_is_not_ours_to_honour():
    body = "User-agent: AhrefsBot\nCrawl-delay: 30\n"
    assert Robots.parse(body).crawl_delay_s is None


def test_no_declaration_and_no_robots_txt_both_read_as_none():
    assert Robots.parse("User-agent: *\nAllow: /\n").crawl_delay_s is None
    assert Robots.parse("").crawl_delay_s is None
    assert Robots.permissive("absent", 404).crawl_delay_s is None
    assert Robots.permissive("error").crawl_delay_s is None


def test_a_fractional_delay_reads_as_none_and_that_is_recorded_not_hidden():
    """`urllib.robotparser` accepts integers only (`line[1].strip().isdigit()`).

    Below our 1s floor it changes nothing, because the caller takes
    `max(min_interval_s, delay)`. Above it, a fractional value is silently lost —
    which is why this is a test rather than a comment.
    """
    assert Robots.parse("User-agent: *\nCrawl-delay: 0.5\n").crawl_delay_s is None
    assert Robots.parse("User-agent: *\nCrawl-delay: 1.5\n").crawl_delay_s is None
