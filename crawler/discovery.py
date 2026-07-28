"""Template discovery — spec §3.

Fixed target set, discovered in order, first match wins. The selection rules are
pure functions over hrefs so they can be tested without a network: the browser's
only job is to hand over the links in document order.

Bounded by construction: a 40,000-product catalog costs the same as a 40-product
one. Adversarial case 4 is satisfied structurally, not by a timeout.
"""

from __future__ import annotations

import random
import re
import secrets
from urllib.parse import urljoin, urlparse

# Nav-first ordering: the spec says "from home nav", and a theme that repeats the
# same collection links in a footer mega-menu should not change which one wins.
NAV_SELECTOR = (
    "header a[href], nav a[href], [role='navigation'] a[href], "
    ".header a[href], #shopify-section-header a[href]"
)
ALL_LINKS_SELECTOR = "a[href]"
PRODUCT_LINK_SELECTOR = "a[href*='/products/']"

_COLLECTION_RE = re.compile(r"^/collections/([^/?#]+)/?$")
_PRODUCT_RE = re.compile(r"^(?:/collections/[^/?#]+)?/products/([^/?#]+)/?$")


def same_origin(url: str, origin: str) -> bool:
    a, b = urlparse(url), urlparse(origin)
    return (a.scheme, a.netloc.lower()) == (b.scheme, b.netloc.lower())


def _path(url: str) -> str:
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
    """Strip query and fragment: the same product reached two ways is one page."""
    parsed = urlparse(href)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def pinned_target(pinned: dict | None, template: str, origin: str) -> str | None:
    """A golden entry may pin a template's URL instead of discovering it.

    Discovery reads the live store: which product is "first" in a collection is
    a merchandising decision, and on a cached storefront it can even differ
    between two requests seconds apart. For a fixture that must reproduce, that
    is a bug — so an eval entry can pin `collection`/`pdp` to exact URLs
    (context.yaml `eval.fixtures.targets`, or CLI `--pin`). Pins are eval-only,
    never rendered, and never reach a prompt. Returns the canonical URL, or None
    when nothing is pinned for `template`. A cross-origin pin is a config error,
    not a silent miss — raise.
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
    """`/{random-40-hex}` — a path no store has a template for.

    Seedable so a capture can be reproduced exactly; unseeded it uses
    :mod:`secrets`, because a predictable path is one a store could special-case.
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
