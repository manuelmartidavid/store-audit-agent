"""Picks which URL to crawl for each template (spec §3).

Fixed target set, checked in order, first match wins. The selection rules are
plain functions over hrefs, so they test without a network — the browser just
hands over the links in document order.
"""

from __future__ import annotations

import random
import re
import secrets
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

NAV_SELECTOR = (
    "header a[href], nav a[href], [role='navigation'] a[href], "
    ".header a[href], #shopify-section-header a[href]"
)
ALL_LINKS_SELECTOR = "a[href]"


@dataclass(frozen=True)
class Profile:
    """The URL shapes one platform uses for the templates discovery has to find.

    Invariant: platform-specific knowledge lives here and nowhere else. A new
    platform is a new entry in `PROFILES`, not a branch in `crawl.py`.
    """

    name: str
    collection_re: "re.Pattern[str]"
    collection_exclude: frozenset[str]
    collection_fallback: str
    product_re: "re.Pattern[str]"
    product_link_selector: str
    sitewide_product_page: str
    cart_path: str
    search_path: str
    discover_cart: bool


SHOPIFY = Profile(
    name="shopify",
    collection_re=re.compile(r"^/collections/([^/?#]+)/?$"),
    # /collections/all is every store's catch-all, so it says nothing about how
    # this store merchandises. It stays the fallback, never the discovery.
    collection_exclude=frozenset({"all"}),
    collection_fallback="/collections/all",
    product_re=re.compile(r"^(?:/collections/[^/?#]+)?/products/([^/?#]+)/?$"),
    product_link_selector="a[href*='/products/']",
    sitewide_product_page="/collections/all",
    cart_path="/cart",
    search_path="/search?q=a",
    discover_cart=False,
)

WOOCOMMERCE = Profile(
    name="woocommerce",
    collection_re=re.compile(r"^/product-category/([^/?#]+(?:/[^/?#]+)*)/?$"),
    collection_exclude=frozenset(),
    collection_fallback="/shop/",
    product_re=re.compile(r"^/product/([^/?#]+)/?$"),
    # `/product/` is not a substring of `/products/`, so the two selectors do
    # not answer for each other.
    product_link_selector="a[href*='/product/']",
    sitewide_product_page="/shop/",
    # A starting point only: WooCommerce lets a store rename the cart slug, so
    # `discover_cart` reads the store's own cart link first (entry 04 serves
    # its cart at /basket/ and 404s on /cart/).
    cart_path="/cart",
    search_path="/?s=a",
    discover_cart=True,
)

PROFILES: dict[str, Profile] = {p.name: p for p in (SHOPIFY, WOOCOMMERCE)}

#: Kept for callers that want Shopify's selector by name.
PRODUCT_LINK_SELECTOR = SHOPIFY.product_link_selector

# A store's own cart link is the only thing that knows its cart slug. The
# selector is deliberately two-armed — a class hook (themes name the widget
# "cart" even when the slug is /basket/) and a slug suffix — because either
# alone misses a real store.
CART_LINK_SELECTOR = (
    "a.cart-contents[href], a[class*='cart'][href], a[class*='basket'][href], "
    "[class*='mini-cart'] a[href], [class*='cart'] > a[href], "
    "a[href$='/cart'], a[href$='/cart/'], a[href$='/basket'], a[href$='/basket/']"
)

# The same selector matches WooCommerce's add-to-cart button, whose class is
# literally `add_to_cart_button`. Adding to a cart is not the cart.
_NOT_THE_CART_RE = re.compile(r"add[-_]to[-_]cart|/cart/add|/checkout", re.I)


def profile_for(platform: str | None) -> Profile:
    """The discovery profile for a fingerprinted platform.

    Invariant: anything unrecognised gets SHOPIFY. That is precisely what every
    capture before 0.3.0 did, so an unrecognised store cannot regress relative
    to the fixtures already frozen against it.
    """
    return PROFILES.get((platform or "").strip().lower(), SHOPIFY)


def same_origin(url: str, origin: str) -> bool:
    """True if `url` has the same scheme and host as `origin`."""
    a, b = urlparse(url), urlparse(origin)
    return (a.scheme, a.netloc.lower()) == (b.scheme, b.netloc.lower())


def _path(url: str) -> str:
    """The path part of a URL, defaulting to "/"."""
    return urlparse(url).path or "/"


def pick_collection(hrefs: list[str], origin: str, profile: Profile = SHOPIFY) -> str | None:
    """First collection link matching `profile`'s URL shape."""
    for href in hrefs:
        if not same_origin(href, origin):
            continue
        match = profile.collection_re.match(_path(href))
        if match and match.group(1).lower() not in profile.collection_exclude:
            return _canonical(href)
    return None


def pick_product(hrefs: list[str], origin: str, profile: Profile = SHOPIFY) -> str | None:
    """First product link matching `profile`'s URL shape."""
    for href in hrefs:
        if not same_origin(href, origin):
            continue
        if profile.product_re.match(_path(href)):
            return _canonical(href)
    return None


def pick_cart(hrefs: list[str], origin: str) -> str | None:
    """First same-origin link that points at the store's own cart page.

    Invariant: reject add-to-cart hrefs before canonicalising. `?add-to-cart=99`
    lives in the query, which `_canonical` strips — so a check made afterwards
    would see `/shop/` and call it the cart.
    """
    for href in hrefs:
        if not same_origin(href, origin):
            continue
        if _NOT_THE_CART_RE.search(href):
            continue
        if _path(href).strip("/") == "":
            continue
        return _canonical(href)
    return None


def _canonical(href: str) -> str:
    """Drop the query and fragment so one page has one URL."""
    parsed = urlparse(href)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def pinned_target(pinned: dict | None, template: str, origin: str) -> str | None:
    """The URL an eval entry pinned for `template`, or None if it pinned none.

    Pinning keeps a fixture reproducible when the live store would otherwise
    return a different "first" product. Raises if the pinned URL is cross-origin.
    """
    url = (pinned or {}).get(template)
    if not url:
        return None
    if not same_origin(url, origin):
        raise ValueError(
            f"pinned {template} URL {url!r} is not same-origin as {origin!r}"
        )
    return _canonical(url)


def random_404_path(rng: random.Random | None = None) -> str:
    """A random `/{40-hex}` path that no store has a page for.

    Pass an `rng` to reproduce a capture exactly; without one it uses
    :mod:`secrets` so the path can't be predicted.
    """
    if rng is None:
        return "/" + secrets.token_hex(20)
    return "/" + "".join(rng.choice("0123456789abcdef") for _ in range(40))


def static_targets(origin: str, profile: Profile = SHOPIFY) -> dict[str, str]:
    """Templates whose URL is fixed by `profile`'s table."""
    return {
        "home": urljoin(origin + "/", "/"),
        "cart": urljoin(origin + "/", profile.cart_path),
        "search": urljoin(origin + "/", profile.search_path),
    }
