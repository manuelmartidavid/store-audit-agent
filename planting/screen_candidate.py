"""Golden-entry candidate screen — is this store still fit to be an eval entry?

    python -m planting.screen_candidate --entry 01
    python -m planting.screen_candidate --entry 04 --runs 3

Entries 01 and 04 are stores we do NOT own (design 2026-07-29, D5). Shopify can
reconfigure the Dawn demo, and Forest Whole Foods can change its theme, between
selection and capture day — and the failure mode is silent. A `noindex`
appearing on entry 01 turns the project's only false-positive test into a store
that correctly emits a `critical`, and nothing downstream would report that as
a selection problem rather than an agent problem.

So the selection criteria live here as code and are re-run immediately before
capture. A failing hard gate is a RE-SELECTION TRIGGER, not a defect to label
around.

HARD GATES — any failure disqualifies the candidate:

    reachable    HTTP 200, and no storefront password form
    indexable    no `meta robots: noindex` on any revenue template  -> a critical
    lcp          LCP <= 4.0s on home/collection/pdp                 -> a high
    cls          CLS <= 0.25 on home/collection/pdp                 -> a high
    platform     crawler.fingerprint agrees with the declared platform
    permalinks   WooCommerce only: default /shop|/product-category|/product

RECORDED, never disqualifying:

    robots       which templates robots.txt allows, and any Crawl-delay
    hygiene      title and meta-description presence per template

The hygiene block is deliberately NOT a gate. The defects it finds are real and
belong in the entry's labels — the person writing `expected/findings.md` needs
to know what the store already had before the agent said anything. Screening
them out would mean hunting for a store that flatters the agent, which is the
store-shopping failure this project has warned about twice.

Boundary discipline follows rubric §1: boundary values take the LOWER level, so
LCP exactly 4000 ms and CLS exactly 0.25 both PASS. Gates compare strictly.

This writes nothing. It builds no fixture and no labels.

Exit codes match measure.py: 0 = every hard gate passed · 1 = operational
failure · 2 = a hard gate failed (re-selection trigger).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlsplit

# planting/ is not a package; reach crawler/ the way measure.py does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import measure

# --- head parsing -----------------------------------------------------------

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"' r"|([\w:-]+)\s*=\s*'([^']*)'")
_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.I)
_HEAD_CLOSE = re.compile(r"</head\s*>", re.I)
_FORM_TAG = re.compile(r"<form\b[^>]*>", re.I)

#: `none` is shorthand for `noindex, nofollow`. Easy to miss, same consequence.
_NOINDEX_TOKENS = {"noindex", "none"}


@dataclass(frozen=True)
class HeadFacts:
    """What one template's document says about itself."""

    http_status: int
    title: str | None
    description: str | None
    robots: str | None
    #: True only when the document contains a <form> whose action targets
    #: /password — Shopify's storefront gate emits action="/password" on a
    #: <form class="storefront-password-form">. A bare password <input> (e.g.
    #: a header customer-login drawer, present on almost every theme page) is
    #: NOT enough to set this; that would false-positive-disqualify a
    #: perfectly reachable store.
    password_form: bool


@dataclass(frozen=True)
class Gate:
    """One screen verdict. `passed is False` disqualifies the candidate."""

    name: str
    passed: bool
    detail: str


def _attrs(tag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR.finditer(tag):
        key = (m.group(1) or m.group(3) or "").lower()
        out[key] = m.group(2) if m.group(2) is not None else (m.group(4) or "")
    return out


def _head_scope(html: str) -> str:
    """Return the substring between `<head` and `</head>`.

    Falls back to the whole document when there is no `</head>` to bound it
    (e.g. a fixture with no head section at all) — better to over-read a
    headless document than to raise on it.
    """
    close = _HEAD_CLOSE.search(html)
    if not close:
        return html
    open_ = _HEAD_OPEN.search(html)
    start = open_.start() if open_ else 0
    return html[start:close.end()]


def _is_password_gate_action(action: str) -> bool:
    """True when a <form action=...> targets Shopify's storefront gate.

    Shopify redirects a password-protected storefront to /password and emits
    <form method="post" action="/password" class="storefront-password-form">
    there. Matches both the bare path and an absolute URL whose path ends in
    /password.
    """
    if not action:
        return False
    return urlsplit(action.strip()).path.endswith("/password")


def parse_head(html: str, http_status: int) -> HeadFacts:
    """Read the head facts a screen decision depends on.

    Regex rather than a parser because this reads four known fields out of a
    document we do not otherwise trust, and adding a parser dependency to a
    pre-capture probe buys nothing. An empty `content=""` is reported as absent:
    broadcast-theme-main serves exactly that, and treating it as present would
    report hygiene the store does not have.

    `<title>` and `<meta>` are read from the head ONLY — some themes render a
    second `<title>` inside an inline SVG in the body, and reading the whole
    document would let a body `<meta name="robots" content="index, follow">`
    silently override a real `noindex` set in the head (a false negative on
    the one gate that eliminated 4 of 9 candidate stores during selection).

    `password_form` is checked over the WHOLE document, not just the head,
    since the storefront gate is a <form> in the body.
    """
    head = _head_scope(html)

    title_match = _TITLE.search(head)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None

    description = robots = None
    for tag in _META.finditer(head):
        attrs = _attrs(tag.group(0))
        name = (attrs.get("name") or "").lower()
        content = (attrs.get("content") or "").strip()
        if name == "description":
            description = content or None
        elif name == "robots":
            robots = content or None

    password_form = False
    for tag in _FORM_TAG.finditer(html):
        attrs = _attrs(tag.group(0))
        if _is_password_gate_action(attrs.get("action") or ""):
            password_form = True
            break

    return HeadFacts(
        http_status=http_status,
        title=title or None,
        description=description,
        robots=robots,
        password_form=password_form,
    )


def is_noindex(robots: str | None) -> bool:
    """True when a robots directive keeps the page out of the index."""
    if not robots:
        return False
    tokens = {t.strip().lower() for t in robots.split(",")}
    return bool(tokens & _NOINDEX_TOKENS)


def indexable_gate(template: str, facts: HeadFacts) -> Gate:
    """A `noindex` on a revenue template is a correct `critical` (rubric §1).

    Four of the nine theme demos screened on 2026-07-29 failed here. It is not
    bad luck: demo stores are deliberately deindexed so they do not compete
    with real merchant stores in search.
    """
    if is_noindex(facts.robots):
        return Gate(
            name=f"indexable:{template}",
            passed=False,
            detail=(f"meta robots={facts.robots!r} — the audit would correctly emit a "
                    f"critical (blocks indexing of a revenue template, rubric §1)"),
        )
    return Gate(name=f"indexable:{template}", passed=True,
                detail=f"meta robots={facts.robots!r}")


# --- permalinks -------------------------------------------------------------

_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_WOO_COLLECTION = re.compile(r"^/(shop|product-category/[^/]+)/?$", re.I)


def permalink_gate(html: str, host: str, platform: str) -> Gate:
    """WooCommerce entries must use DEFAULT permalinks, or discovery cannot find them.

    The 0.3.0 discovery table (design D3) keys on `/shop`,
    `/product-category/{slug}` and `/product/{slug}`. A store on customised
    permalinks (`/store/{cat}/{product}`) is a hard disqualifier for this entry
    — not a defect in the store, and not something to route around with a pin,
    because entry 04 exists to exercise the non-Shopify discovery path.

    Only ONE default collection URL is required. `offermanwoodshop.com` exposes
    `/product-category/` and no `/shop/`, and discovery needs either. Product
    links are NOT required on home: discovery reaches the PDP from the
    collection page (specs/crawler.md §3).

    `_WOO_COLLECTION` matches exactly one category segment
    (`/product-category/{slug}`), not a nested one
    (`/product-category/{parent}/{child}/`) — deliberately: the discovery table
    this gate exists to protect (design D3, above) only knows the one-segment
    shape. A store whose only collection link is nested would fail discovery
    the same way it fails here, so this is not a gap to widen.
    """
    if platform != "woocommerce":
        return Gate(name="permalinks", passed=True,
                    detail=f"n/a — platform is {platform}")

    paths = []
    for href in _HREF.findall(html):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != host:
            continue
        paths.append(parsed.path or href)

    collections = sorted({p for p in paths if _WOO_COLLECTION.match(p)})
    if collections:
        return Gate(name="permalinks", passed=True,
                    detail=f"default collection URL present: {collections[0]}")
    return Gate(
        name="permalinks",
        passed=False,
        detail=("no /shop or /product-category/{slug} link on home — discovery "
                "cannot reach a collection, so this store needs customised "
                "permalink support that entry 04 is not the place to build"),
    )


# --- performance ------------------------------------------------------------

def perf_gates(template: str, run: "measure.SampleRun") -> list[Gate]:
    """LCP and CLS must stay off the `high` side on EVERY run.

    Every run, not the median: a median under the line with one run over it is
    exactly what measure.py already refuses to call a pass ("the aim has not
    landed - this is noise, not a defect"). Screening inherits that discipline
    because a fixture is captured once, and it can be captured on the bad run.

    An empty sample list fails both gates. A gate that passes having evaluated
    nothing is the vacuous-pass shape step 8 found twice in this repo.

    Reads `s.lcp`/`s.cls` directly rather than through `getattr(s, ..., None)`:
    `run.samples` is typed as `list[measure.Sample]`, and `Sample` always
    carries both fields (defaulting to `None` when Lighthouse has no reading,
    which is what the `is not None` filter below is for). A bare `getattr`
    default would instead swallow a genuine shape mismatch — e.g. a caller
    passing an object with no `.lcp` at all — as "nothing measured", which is
    the same silent-pass-shaped failure this function exists to refuse.
    """
    lcp_high, cls_high = measure.LCP_HIGH_MS, measure.CLS_HIGH
    lcps = [s.lcp for s in run.samples if s.lcp is not None]
    clss = [s.cls for s in run.samples if s.cls is not None]

    gates: list[Gate] = []

    if not lcps:
        gates.append(Gate(f"lcp:{template}", False,
                          "nothing measured — treated as a failure, not a pass"))
    else:
        over = [v for v in lcps if v > lcp_high]
        gates.append(Gate(
            f"lcp:{template}", not over,
            (f"{min(lcps)/1000:.2f}–{max(lcps)/1000:.2f}s over {len(lcps)} run(s)"
             + (f"; {len(over)} on the HIGH side (> {lcp_high/1000:.1f}s)" if over else ""))))

    if not clss:
        gates.append(Gate(f"cls:{template}", False,
                          "nothing measured — treated as a failure, not a pass"))
    else:
        over = [v for v in clss if v > cls_high]
        gates.append(Gate(
            f"cls:{template}", not over,
            (f"{min(clss):.3f}–{max(clss):.3f} over {len(clss)} run(s)"
             + (f"; {len(over)} above {cls_high}" if over else ""))))

    return gates
