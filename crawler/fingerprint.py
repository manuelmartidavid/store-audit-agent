"""Platform / theme / app fingerprinting — spec §4.

Pattern-matching only, per the boundary table. This module reports what was
*observed of the store*. It never infers, and it never causally attributes an app
to anything (MNC-002) — it records that a script was present, full stop.

Apps are recognised two ways: a vendor-domain substring (``APP_SIGNATURES``), and
the theme-app-extension asset path convention. The second exists because the
first can only ever name an app somebody already hardcoded, and most of a modern
Shopify store's third-party surface arrives as extensions.

The blocked case is enforced at the data layer rather than the prompt layer: a
store that was not observed yields ``platform: "unknown"`` with empty evidence,
even when the page that blocked us is recognisably Shopify (MNC-003). That is
what :func:`empty` is for.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import APP_SIGNATURES

Fingerprint = dict[str, Any]

_SHOPIFY_URL_MARKERS = (
    ("cdn.shopify.com", "cdn.shopify.com asset URLs"),
    ("/cdn/shop/", "/cdn/shop/ asset paths"),
    ("shopifycloud", "shopifycloud script host"),
    ("shopifycdn.net", "shopifycdn.net asset URLs"),
    ("/cdn/shopifycloud/", "shopifycloud runtime bundle"),
)
_WOO_URL_MARKERS = (
    ("/wp-content/plugins/woocommerce", "wp-content/plugins/woocommerce assets"),
    ("/wp-content/themes/", "wp-content theme assets"),
    ("woocommerce-blocks", "woocommerce-blocks bundle"),
)

_THEME_JSON_RE = re.compile(r"Shopify\.theme\s*=\s*(\{.*?\})\s*;", re.S)
_THEME_NAME_RE = re.compile(r"theme[_-]?name[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", re.I)
_THEME_VERSION_RE = re.compile(r"theme[_-]?version[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']", re.I)

# --- theme app extensions ---------------------------------------------------
# Extension assets are served from a fixed path shape:
#     /extensions/<uuid>/<handle>-<build>/assets/<file>
# The uuid segment is required to look like a uuid. The bare `/extensions/` path
# is cheap to collide with, and a wrong app name is worse than no app name — a
# named app that isn't installed is a fabricated finding waiting to happen. If
# Shopify changes the convention this matches nothing and reports nothing; it
# never guesses.
_EXTENSION_PATH_RE = re.compile(
    r"/extensions/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"(?P<segment>[^/?#]+)/",
    re.I,
)
# Only the *last* numeric segment is the build counter: `restockrocket-1-546`
# is handle `restockrocket-1`, build 546. Digits earlier in the segment belong
# to the handle the developer chose.
_EXTENSION_BUILD_RE = re.compile(r"-\d+$")

EVIDENCE_SCRIPT_SRC = "script src pattern"
EVIDENCE_EXTENSION = "theme app extension asset path"
EVIDENCE_BOTH = "script src pattern + theme app extension asset path"

# Below this length a normalized vendor name is too collision-prone to fold on.
_MIN_FOLD_CHARS = 4


@dataclass
class Signals:
    """Everything observed across the captured pages, accumulated."""

    urls: list[str] = field(default_factory=list)
    inline_scripts: list[str] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)
    shopify_global: bool = False
    shopify_theme: dict[str, Any] | None = None
    body_classes: list[str] = field(default_factory=list)

    def merge(self, other: "Signals") -> None:
        self.urls.extend(other.urls)
        self.inline_scripts.extend(other.inline_scripts)
        for k, v in other.meta.items():
            self.meta.setdefault(k, v)
        for k, v in other.headers.items():
            self.headers.setdefault(k.lower(), v)
        self.cookies.extend(c for c in other.cookies if c not in self.cookies)
        self.shopify_global = self.shopify_global or other.shopify_global
        if other.shopify_theme and not self.shopify_theme:
            self.shopify_theme = other.shopify_theme
        self.body_classes.extend(c for c in other.body_classes if c not in self.body_classes)


def empty() -> Fingerprint:
    """The fingerprint of a store that was not observed (spec §6)."""
    return {"platform": "unknown", "evidence": [], "theme": None, "apps": []}


def _detect_theme(signals: Signals) -> dict[str, Any] | None:
    theme = signals.shopify_theme
    if isinstance(theme, dict):
        name = theme.get("name") or theme.get("theme_name")
        version = theme.get("version") or theme.get("theme_version")
        if name:
            return {"name": str(name), "version": str(version) if version else None}

    blob = "\n".join(signals.inline_scripts)
    match = _THEME_JSON_RE.search(blob)
    if match:
        try:
            parsed = json.loads(match.group(1))
            name = parsed.get("name")
            if name:
                version = parsed.get("version") or parsed.get("theme_version")
                return {"name": str(name), "version": str(version) if version else None}
        except (ValueError, AttributeError):
            pass

    name_match = _THEME_NAME_RE.search(blob) or _THEME_NAME_RE.search(
        signals.meta.get("theme-name", "")
    )
    if name_match:
        version_match = _THEME_VERSION_RE.search(blob)
        return {
            "name": name_match.group(1),
            "version": version_match.group(1) if version_match else None,
        }
    return None


def _normalize(name: str) -> str:
    """Lowercase alphanumerics only — the key two observations of one app share."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def extension_handle(url: str) -> str | None:
    """The theme-app-extension handle in ``url``, or None if it isn't one.

    The handle is returned verbatim, build counter stripped. It is not
    title-cased or prettified: `al-bulk-discount-manager` is what the store
    actually serves, and turning it into "AL Bulk Discount Manager" would be a
    guess at a product name that nothing in the capture supports.
    """
    match = _EXTENSION_PATH_RE.search(url)
    if not match:
        return None
    handle = _EXTENSION_BUILD_RE.sub("", match.group("segment"))
    return handle or None


def _detect_apps(signals: Signals) -> list[dict[str, str]]:
    # Evidence is the *shape* of the observation, never a claim about what the
    # app does to the store (MNC-002).
    known: dict[str, dict[str, str]] = {}
    extensions: dict[str, None] = {}

    for url in signals.urls:
        lowered = url.lower()
        for needle, display in APP_SIGNATURES.items():
            if needle in lowered and display not in known:
                known[display] = {"name": display, "evidence": EVIDENCE_SCRIPT_SRC}
        handle = extension_handle(url)
        if handle is not None:
            extensions.setdefault(handle, None)

    # One app can be observed twice — once on its vendor domain, once as its
    # theme app extension. Fold those into a single entry when the handle
    # contains the known name under normalization. That is near-miss
    # normalization of one observation (decision 9's rule applied to app names),
    # not an inference about a second app. Anything that doesn't fold stays
    # separate under its raw handle.
    for handle in list(extensions):
        for display, entry in known.items():
            normalized = _normalize(display)
            if len(normalized) >= _MIN_FOLD_CHARS and normalized in _normalize(handle):
                entry["evidence"] = EVIDENCE_BOTH
                del extensions[handle]
                break

    apps = list(known.values())
    apps.extend({"name": handle, "evidence": EVIDENCE_EXTENSION} for handle in extensions)
    # Stable order — apps[] is compared across runs.
    return sorted(apps, key=lambda app: app["name"])


def build(signals: Signals, observed: bool = True) -> Fingerprint:
    """Derive the §4 fingerprint block from accumulated signals."""
    if not observed:
        return empty()

    evidence: list[str] = []
    platform = "unknown"

    for needle, description in _SHOPIFY_URL_MARKERS:
        if any(needle in u.lower() for u in signals.urls):
            evidence.append(description)
    if signals.shopify_theme is not None:
        evidence.append("Shopify.theme JSON")
    if signals.shopify_global:
        evidence.append("Shopify global object")
    if any(c.startswith(("_shopify_", "cart_currency", "secure_customer_sig")) for c in signals.cookies):
        evidence.append("Shopify session cookies")
    for header in ("x-shopid", "x-shopify-stage", "x-sorting-hat-shopid"):
        if header in signals.headers:
            evidence.append(f"{header} response header")

    if evidence:
        platform = "shopify"
    else:
        for needle, description in _WOO_URL_MARKERS:
            if any(needle in u.lower() for u in signals.urls):
                evidence.append(description)
        generator = (signals.meta.get("generator") or "").lower()
        if "woocommerce" in generator:
            evidence.append("generator meta names WooCommerce")
        if any("woocommerce" in c for c in signals.body_classes):
            evidence.append("woocommerce body class")
        if evidence:
            platform = "woocommerce"
        elif signals.urls or signals.meta:
            # Pages were observed and matched nothing known. That is a fact about
            # the store, not an absence of observation.
            platform = "custom"
            if generator:
                evidence.append(f"generator meta: {signals.meta.get('generator')}")

    # Stable order, no duplicates — evidence lists are compared across runs.
    deduped = list(dict.fromkeys(evidence))
    return {
        "platform": platform,
        "evidence": deduped,
        "theme": _detect_theme(signals),
        "apps": _detect_apps(signals),
    }
