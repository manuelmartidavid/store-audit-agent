"""Picks which URL to crawl for each template (spec §3).

Fixed target set, checked in order, first match wins. The selection rules are
plain functions over hrefs, so they test without a network — the browser just
hands over the links in document order.
"""

from __future__ import annotations

import random
import re
import secrets
from urllib.parse import urljoin, urlparse

# Nav links are checked first, so a footer mega-menu repeating the same links
# can't change which one wins.
NAV_SELECTOR = (
    "header a[href], nav a[href], [role='navigation'] a[href], "
    ".header a[href], #shopify-section-header a[href]"
)
ALL_LINKS_SELECTOR = "a[href]"
PRODUCT_LINK_SELECTOR = "a[href*='/products/']"

_COLLECTION_RE = re.compile(r"^/collections/([^/?#]+)/?$")
_PRODUCT_RE = re.compile(r"^(?:/collections/[^/?#]+)?/products/([^/?#]+)/?$")


def same_origin(url: str, origin: str) -> bool:
    """True if `url` has the same scheme and host as `origin`."""
    a, b = urlparse(url), urlparse(origin)
    return (a.scheme, a.netloc.lower()) == (b.scheme, b.netloc.lower())


def _path(url: str) -> str:
    """The path part of a URL, defaulting to "/"."""
    return urlparse(url).path or "/"


def pick_collection(hrefs: list[str], origin: str) -> str | None:
    """First `/collections/{handle}` link, excluding `/collections/all`."""
    for href in hrefs:
        if not same_origin(href, origin):
            continue
        match = _COLLECTION_RE.match(_path(href))
        if match and match.group(1).lower() != "all":
            return _canonical(href)
    return None


def pick_product(hrefs: list[str], origin: str) -> str | None:
    """First `/products/{handle}` link, collection-scoped or not."""
    for href in hrefs:
        if not same_origin(href, origin):
            continue
        if _PRODUCT_RE.match(_path(href)):
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


def static_targets(origin: str) -> dict[str, str]:
    """Templates whose URL is fixed by the spec table."""
    return {
        "home": urljoin(origin + "/", "/"),
        "cart": urljoin(origin + "/", "/cart"),
        "search": urljoin(origin + "/", "/search?q=a"),
    }
