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
