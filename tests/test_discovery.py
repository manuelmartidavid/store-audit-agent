"""Template discovery — spec §3."""

from __future__ import annotations

import random
import re

from crawler.discovery import (
    pick_collection,
    pick_product,
    pinned_target,
    random_404_path,
    same_origin,
    static_targets,
)

ORIGIN = "https://shop.test"


def test_first_collection_link_wins_and_collections_all_is_excluded():
    hrefs = [
        f"{ORIGIN}/",
        f"{ORIGIN}/collections/all",
        f"{ORIGIN}/collections/rookies",
        f"{ORIGIN}/collections/graded",
    ]
    assert pick_collection(hrefs, ORIGIN) == f"{ORIGIN}/collections/rookies"


def test_collection_discovery_ignores_off_origin_and_nested_collection_urls():
    hrefs = [
        "https://elsewhere.test/collections/rookies",
        f"{ORIGIN}/collections/rookies/products/card",
        f"{ORIGIN}/collections/graded",
    ]
    assert pick_collection(hrefs, ORIGIN) == f"{ORIGIN}/collections/graded"


def test_no_collection_link_returns_none_so_the_caller_can_fall_back():
    assert pick_collection([f"{ORIGIN}/pages/about"], ORIGIN) is None


def test_product_discovery_accepts_bare_and_collection_scoped_urls():
    assert pick_product([f"{ORIGIN}/products/card-1"], ORIGIN) == f"{ORIGIN}/products/card-1"
    assert (
        pick_product([f"{ORIGIN}/collections/rookies/products/card-2"], ORIGIN)
        == f"{ORIGIN}/collections/rookies/products/card-2"
    )


def test_query_strings_are_stripped_so_one_page_is_one_page():
    assert pick_product([f"{ORIGIN}/products/card?variant=42"], ORIGIN) == f"{ORIGIN}/products/card"


def test_the_404_path_is_forty_hex_characters():
    assert re.fullmatch(r"/[0-9a-f]{40}", random_404_path())


def test_seeding_makes_a_capture_reproducible():
    assert random_404_path(random.Random(7)) == random_404_path(random.Random(7))
    assert random_404_path(random.Random(7)) != random_404_path(random.Random(8))


def test_static_template_urls_match_the_spec_table():
    targets = static_targets(ORIGIN)
    assert targets["home"] == f"{ORIGIN}/"
    assert targets["cart"] == f"{ORIGIN}/cart"
    assert targets["search"] == f"{ORIGIN}/search?q=a"


def test_same_origin_compares_scheme_and_host_only():
    assert same_origin(f"{ORIGIN}/cart", ORIGIN)
    assert not same_origin("http://shop.test/cart", ORIGIN)
    assert not same_origin("https://checkout.test/cart", ORIGIN)


# --- pinned_target (golden entries override discovery) ----------------------

def test_a_pin_returns_the_canonical_url_and_bypasses_discovery():
    pinned = {"pdp": f"{ORIGIN}/products/upper-deck-box?variant=9"}
    assert pinned_target(pinned, "pdp", ORIGIN) == f"{ORIGIN}/products/upper-deck-box"


def test_no_pin_for_a_template_returns_none_so_discovery_runs():
    assert pinned_target({"pdp": f"{ORIGIN}/products/x"}, "collection", ORIGIN) is None
    assert pinned_target(None, "pdp", ORIGIN) is None
    assert pinned_target({}, "pdp", ORIGIN) is None


def test_a_cross_origin_pin_is_a_config_error_not_a_silent_miss():
    import pytest
    with pytest.raises(ValueError):
        pinned_target({"pdp": "https://elsewhere.test/products/x"}, "pdp", ORIGIN)
