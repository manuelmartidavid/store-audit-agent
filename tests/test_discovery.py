"""Template discovery — spec §3."""

from __future__ import annotations

import random
import re

from crawler.discovery import (
    CART_LINK_SELECTOR,
    SHOPIFY,
    WOOCOMMERCE,
    pick_cart,
    pick_collection,
    pick_product,
    pinned_target,
    profile_for,
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


# --- platform profiles (design D3) ------------------------------------------

def test_an_unrecognised_platform_gets_the_shopify_profile():
    """0.3.0 must not regress a store 0.2.0 crawled — and 0.2.0 was Shopify-only."""
    for platform in ("custom", "unknown", "", None, "Magento"):
        assert profile_for(platform) is SHOPIFY


def test_the_platform_name_is_matched_case_insensitively():
    assert profile_for("WooCommerce") is WOOCOMMERCE
    assert profile_for("shopify") is SHOPIFY


def test_woocommerce_collection_discovery_reads_product_category_urls():
    hrefs = [
        f"{ORIGIN}/about/",
        f"{ORIGIN}/product-category/nuts/",
        f"{ORIGIN}/product-category/seeds/",
    ]
    assert pick_collection(hrefs, ORIGIN, WOOCOMMERCE) == f"{ORIGIN}/product-category/nuts/"


def test_woocommerce_collection_discovery_accepts_a_nested_category():
    hrefs = [f"{ORIGIN}/product-category/nuts/almonds/"]
    assert pick_collection(hrefs, ORIGIN, WOOCOMMERCE) == f"{ORIGIN}/product-category/nuts/almonds/"


def test_woocommerce_product_discovery_reads_singular_product_urls():
    hrefs = [f"{ORIGIN}/product-category/nuts/", f"{ORIGIN}/product/organic-almonds/"]
    assert pick_product(hrefs, ORIGIN, WOOCOMMERCE) == f"{ORIGIN}/product/organic-almonds/"


def test_the_two_profiles_do_not_answer_for_each_other():
    """`/products/x` and `/product/x` differ by one character and mean different stores."""
    assert pick_product([f"{ORIGIN}/products/card-1"], ORIGIN, WOOCOMMERCE) is None
    assert pick_product([f"{ORIGIN}/product/almonds/"], ORIGIN, SHOPIFY) is None
    assert pick_collection([f"{ORIGIN}/collections/rookies"], ORIGIN, WOOCOMMERCE) is None
    assert pick_collection([f"{ORIGIN}/product-category/nuts/"], ORIGIN, SHOPIFY) is None


def test_woocommerce_static_targets_use_the_woocommerce_search_form():
    targets = static_targets(ORIGIN, WOOCOMMERCE)
    assert targets["home"] == f"{ORIGIN}/"
    assert targets["search"] == f"{ORIGIN}/?s=a"
    assert targets["cart"] == f"{ORIGIN}/cart", "a starting point; discovery overrides it"


def test_each_profile_carries_a_fallback_for_both_link_based_templates():
    assert SHOPIFY.collection_fallback == "/collections/all"
    assert SHOPIFY.sitewide_product_page == "/collections/all"
    assert WOOCOMMERCE.collection_fallback == "/shop/"
    assert WOOCOMMERCE.sitewide_product_page == "/shop/"


# --- cart discovery (a WooCommerce store may rename the slug) ----------------

def test_the_cart_link_is_read_from_the_store_rather_than_assumed():
    """Entry 04 serves its cart at /basket/ and 404s on /cart/."""
    assert pick_cart([f"{ORIGIN}/basket/"], ORIGIN) == f"{ORIGIN}/basket/"


def test_an_add_to_cart_link_is_never_mistaken_for_the_cart_page():
    """WooCommerce product cards carry class `add_to_cart_button` and an
    `?add-to-cart=` href — the selector matches them, so the picker must not."""
    hrefs = [
        f"{ORIGIN}/shop/?add-to-cart=99",
        f"{ORIGIN}/?add_to_cart=99",
        f"{ORIGIN}/cart/add",
        f"{ORIGIN}/checkout/",
        f"{ORIGIN}/basket/",
    ]
    assert pick_cart(hrefs, ORIGIN) == f"{ORIGIN}/basket/"


def test_a_mini_cart_that_links_to_the_homepage_tells_us_nothing():
    assert pick_cart([f"{ORIGIN}/", ORIGIN], ORIGIN) is None


def test_cart_discovery_ignores_off_origin_links():
    assert pick_cart(["https://elsewhere.test/basket/"], ORIGIN) is None


def test_the_selector_is_the_filter_so_the_picker_takes_what_it_is_handed():
    """CART_LINK_SELECTOR decides which links `pick_cart` ever sees; the picker
    rejects the href shapes that selector is known to over-match (an
    add-to-cart flag, `/cart/add`, `/checkout`) and, per `profile`, any href
    that is itself a product page — the loop button WooCommerce renders for
    variable, grouped and external products carries the cart-matching class
    but links to the product permalink. `/about/` matches neither rejection on
    either profile, so it still passes straight through."""
    assert pick_cart([f"{ORIGIN}/about/"], ORIGIN) == f"{ORIGIN}/about/"


def test_no_links_at_all_returns_none_so_the_caller_falls_back_to_the_profile():
    assert pick_cart([], ORIGIN) is None


def test_the_cart_selector_names_both_a_class_hook_and_a_slug_suffix():
    assert "cart" in CART_LINK_SELECTOR and "basket" in CART_LINK_SELECTOR


def test_a_variable_product_loop_button_is_never_mistaken_for_the_cart():
    """WooCommerce's loop button for variable, grouped and external products
    carries class `add_to_cart_button` (so CART_LINK_SELECTOR matches it) but
    links to the product permalink rather than an add-to-cart href — the one
    shape `_NOT_THE_CART_RE` cannot catch, and the reason `pick_cart` takes a
    profile."""
    hrefs = [f"{ORIGIN}/product/organic-almonds/", f"{ORIGIN}/basket/"]
    assert pick_cart(hrefs, ORIGIN, WOOCOMMERCE) == f"{ORIGIN}/basket/"

    hrefs = [f"{ORIGIN}/products/rookie-card", f"{ORIGIN}/cart"]
    assert pick_cart(hrefs, ORIGIN, SHOPIFY) == f"{ORIGIN}/cart"
