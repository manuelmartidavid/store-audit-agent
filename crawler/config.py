"""Constants the rest of the crawler reads."""

from __future__ import annotations

from . import __version__

# Invariant: any value here that changes the bytes of a fixture must also be
# recorded in manifest.yaml, or fixture regressions become impossible to trace.

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
# Retried with backoff so a temporary blip doesn't mark a template as an error.
# 4xx is never retried — that means the page really is missing.
TRANSIENT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_TRANSIENT_RETRIES = 2
RETRY_BACKOFF_S = 3.0

# --- templates (spec §3) ----------------------------------------------------
# Discovery order, and the order of every array we emit.
TEMPLATES = ("home", "collection", "pdp", "cart", "search", "404")

# --- throttling (spec §7/§8) ------------------------------------------------
# The name manifest.yaml records; the Node sidecar pins the actual numbers.
# Invariant: pinned on purpose — if Lighthouse changes its mobile default, this
# must show up as a version bump rather than silent fixture drift.
THROTTLING_PROFILE = "mobile-4g-slow"

#: Roughly what one capture costs in navigations: robots + gate + six templates
#: + discovery fallbacks. Used only to project how long a declared Crawl-delay
#: will make a capture take, so a slow run reads as arithmetic rather than a hang.
EXPECTED_FETCHES_PER_CAPTURE = 14

# --- distillation (spec §5) -------------------------------------------------
MAX_SIBLING_RUN = 5
TEXT_KEEP_MIN_CHARS = 20
MAX_DATA_URI_BYTES = 1024
MAX_TEXT_CHARS = 4000  # per node; guards against a pathological single text node

# --- app fingerprints (spec §4) ---------------------------------------------
# Key is a substring matched against script/link/img URLs; value is the display
# name.
# Invariant: detection only — never claim one of these apps caused a problem
# (MNC-002).
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
