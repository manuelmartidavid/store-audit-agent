"""Constants that the rest of the crawler codes against.

Anything here that changes the bytes of a fixture is provenance: it belongs in
manifest.yaml too, or a fixture regression becomes undebuggable six weeks later.
"""

from __future__ import annotations

from . import __version__

# --- conduct (spec §3, brief §5) -------------------------------------------
# Non-negotiable for stores we don't own.
MIN_FETCH_INTERVAL_S = 1.0
MAX_CONCURRENCY = 1
USER_AGENT = (
    "Mozilla/5.0 (compatible; StoreAuditAgent/{v}; +https://github.com/store-audit-agent) "
    "Chrome/Playwright"
).format(v=__version__)
ROBOTS_UA = "StoreAuditAgent"

# --- timing -----------------------------------------------------------------
NAV_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_MS = 5_000  # networkidle is best-effort; never fatal

# --- transient-error retry --------------------------------------------------
# A store we don't own may throttle us with a 429 or a 5xx that clears on a
# retry. Retrying these (with backoff, politeness preserved) keeps a transient
# blip from demoting a template to `error` and the whole crawl to `partial`. A
# 4xx is never retried — that is a genuine "absent", not a hiccup.
TRANSIENT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_TRANSIENT_RETRIES = 2
RETRY_BACKOFF_S = 3.0

# --- templates (spec §3) ----------------------------------------------------
# Order is the discovery order AND the canonical order of every array we emit.
TEMPLATES = ("home", "collection", "pdp", "cart", "search", "404")

# --- throttling (spec §7/§8) ------------------------------------------------
# Name is what manifest.yaml records; the numbers are what the Node sidecar pins.
# Lighthouse's own mobile default is Slow 4G — pinned explicitly so a Lighthouse
# default change shows up as a version bump, not a silent fixture drift.
THROTTLING_PROFILE = "mobile-4g-slow"

# --- distillation (spec §5) -------------------------------------------------
MAX_SIBLING_RUN = 5
TEXT_KEEP_MIN_CHARS = 20
MAX_DATA_URI_BYTES = 1024
MAX_TEXT_CHARS = 4000  # per node; guards against a pathological single text node

# --- app fingerprints (spec §4) ---------------------------------------------
# Detection only. Never causally attributed — see MNC-002. The value is the
# display name; the key is a substring matched against script/link/img URLs.
APP_SIGNATURES: dict[str, str] = {
    "judge.me": "Judge.me",
    "jdgm": "Judge.me",
    "loox.io": "Loox",
    "yotpo": "Yotpo",
    "okendo": "Okendo",
    "stamped.io": "Stamped",
    "klaviyo": "Klaviyo",
    "attentivemobile": "Attentive",
    "privy.com": "Privy",
    "gorgias": "Gorgias",
    "tidio": "Tidio",
    "zdassets": "Zendesk",
    "intercom": "Intercom",
    "rechargepayments": "Recharge",
    "boldapps": "Bold",
    "smile.io": "Smile.io",
    "swymrelay": "Swym",
    "searchanise": "Searchanise",
    "hotjar": "Hotjar",
    "googletagmanager": "Google Tag Manager",
    "connect.facebook.net": "Meta Pixel",
    "tiktok.com/i18n/pixel": "TikTok Pixel",
    "clarity.ms": "Microsoft Clarity",
    "gem-elements": "Gempages",
    "pagefly": "PageFly",
    "shogun": "Shogun",
    "wiser": "Wiser",
    "rebuyengine": "Rebuy",
}
