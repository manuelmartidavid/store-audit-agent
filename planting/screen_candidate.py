"""Golden-entry candidate screen — is this store still fit to be an eval entry?

    python -m planting.screen_candidate --entry 01
    python -m planting.screen_candidate --entry 04 --runs 3

Entries 01 and 04 are stores we don't own, and they can change between
selection and capture day without warning. A `noindex` appearing on entry 01
would turn the project's only false-positive test into a store that correctly
emits a `critical`, and nothing downstream would call that a selection problem
rather than an agent problem.

Invariant: a failing hard gate is a re-selection trigger, not a defect to label
around. That's why the criteria live here as code and get re-run right before
each capture.

HARD GATES — any failure disqualifies the candidate:

    reachable      HTTP 200, and no storefront password form
    indexable      no `meta robots: noindex` on any revenue template -> a critical
    platform       crawler.fingerprint's platform verdict, from raw home HTML,
                   agrees with the declared platform (`unknown` counts as FAIL)
    robots_allows  robots.txt allows fetching every template this screen probes
    lcp            LCP <= 4.0s on home/collection/pdp                -> a high
    cls            CLS <= 0.25 on home/collection/pdp                -> a high
    permalinks     WooCommerce only: default /shop|/product-category|/product

`lcp` and `cls` are HARD for entry 01 and RECORDED-ONLY for entry 04, per that
entry's `soft_gates`. Entry 01 is the false-positive test and was selected
against the perf bar; entry 04 was selected on permalinks, robots.txt and ICP
match, to exercise the reduced path and the null-AOV trap. Neither of those needs
a fast store, and the brief targets low-traffic SMB stores. A soft gate is still
measured and still printed — in its own block, never dropped — because its
numbers become labels.

`platform` builds a `crawler.fingerprint.Signals` from the home page's raw HTML
— asset URLs, the `generator` meta tag, the `<body>` class list — which is
everything the branch deciding "shopify" or "woocommerce" actually reads. A
live `crawler.Session` would add more evidence but wouldn't change the verdict
for these entries, so a plain `urllib` probe is enough.

RECORDED, never disqualifying:

    robots       any declared Crawl-delay (spaces fetches, never gates), plus a
                 note restating the disallow list `robots_allows` gates on
    hygiene      title and meta-description presence per template

Invariant: hygiene stays a note, not a gate. Its defects are real and belong in
the entry's labels — whoever writes `expected/findings.md` needs to know what
the store already had. Screening them out means hunting for a store that
flatters the agent.

Boundary values take the lower level (rubric §1), so LCP of exactly 4000 ms and
CLS of exactly 0.25 both PASS. Gates compare strictly.

Writes nothing — no fixture, no labels.

Exit codes: 0 = every hard gate passed, and every hard gate was evaluated ·
1 = operational failure · 2 = a hard gate failed (re-selection trigger,
outranks 3 even under --skip-perf) · 3 = screen incomplete — no hard gate
failed, but lcp/cls were never evaluated (--skip-perf), so 0 would misreport
what this run actually checked.
"""

from __future__ import annotations

import argparse
import gzip
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from html import unescape as _html_unescape
from pathlib import Path
from urllib.parse import urlparse, urlsplit

# planting/ is not a package, so reach crawler/ the way measure.py does. Both
# inserts are needed: the project root for `crawler.*`, and this file's own
# directory for the bare `import measure` below — under `python -m` the
# script's directory is not added to sys.path, only cwd, so without the second
# insert `import measure` fails on the documented entrypoint.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import measure
from crawler.config import ROBOTS_UA
from crawler.fingerprint import Signals, build
from crawler.robots import Robots

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
    #: True only when a <form> targets /password, which is what Shopify's
    #: storefront gate emits.
    #: Invariant: a bare password <input> must not set this. Almost every theme
    #: has one in its customer-login drawer, and counting it would disqualify a
    #: perfectly reachable store.
    password_form: bool


@dataclass(frozen=True)
class Gate:
    """One screen verdict. A failing HARD gate disqualifies the candidate.

    Invariant: `hard` defaults to True. A gate that forgets to say what it is
    must keep disqualifying — the failure mode of the other default is a
    criterion that silently stops being one, which is the vacuous pass this
    file already refuses twice elsewhere.
    """

    name: str
    passed: bool
    detail: str
    hard: bool = True


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

    Regex rather than a parser: this reads four known fields, and a parser
    dependency in a pre-capture probe buys nothing. An empty `content=""`
    counts as absent — some themes serve exactly that, and calling it present
    would report hygiene the store doesn't have.

    Invariant: read `<title>` and `<meta>` from the head only. Some themes
    render a second `<title>` inside an inline SVG, and scanning the whole
    document would let a body-level `robots: index, follow` override a real
    `noindex` in the head — a false negative on the gate that eliminated most
    candidates.

    `password_form` is checked across the whole document, since the storefront
    gate is a <form> in the body.
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

    Most theme demos fail here, and not by bad luck — demo stores are
    deliberately deindexed so they don't compete with real merchants in search.

    Invariant: this does not scope itself to revenue templates; the caller
    does. `assemble_head_gates` only invokes it for `_REVENUE_TEMPLATES`, and
    any other caller must do the same or trip a false re-selection trigger.
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


def assemble_head_gates(
    template: str, status: int, html: str, final_url: str
) -> tuple[list[Gate], str | None]:
    """Turn one template's raw head-probe fetch into gates plus a hygiene line.

    Network-free so the indexable-gate scoping is directly testable. A
    `noindex` on cart or search is normal SEO hygiene, not a defect, so gating
    on it would be a false re-selection trigger. `reachable` still runs on
    every template; only `indexable` and perf narrow to revenue templates.

    Returns `([Gate(...)], None)` when the fetch itself failed — there are no
    head facts to build hygiene or indexable from, only the unreachability.
    """
    if status != 200 or not html:
        # status == 0 is `_fetch`'s sentinel for a network failure (DNS,
        # connection timeout, TLS, ...) rather than an HTTP response at all —
        # `final_url` carries the readable reason in that case, not a URL.
        # See `_fetch`'s docstring.
        detail = f"HTTP {status}" if status else final_url
        return [Gate(f"reachable:{template}", False, detail)], None

    facts = parse_head(html, status)
    # A gate shows up two ways: a <form action="/password"> in the page, or a
    # redirect that already landed on /password before any form is parsed.
    # Either disqualifies. `measure._is_gate_url` is reused rather than
    # respelled here.
    redirected_to_gate = measure._is_gate_url(final_url)
    gated = facts.password_form or redirected_to_gate
    detail = f"HTTP {status}"
    if facts.password_form:
        detail += " — storefront password form present"
    elif redirected_to_gate:
        detail += f" — redirected to {final_url} (storefront password gate)"

    gates = [Gate(f"reachable:{template}", not gated, detail)]
    if template in _REVENUE_TEMPLATES:
        gates.append(indexable_gate(template, facts))

    # `facts.title` is raw HTML text content — entities and all (e.g. "Bags
    # &ndash; theme-dawn-demo"). This line is explicitly a label, so it is
    # unescaped before printing rather than shown as markup.
    title = _html_unescape(facts.title) if facts.title else facts.title
    hygiene_line = (f"  {template:<11} title={title!r}"
                    f"  description={'present' if facts.description else 'ABSENT'}")
    return gates, hygiene_line


# --- platform ----------------------------------------------------------------

_ASSET_TAG = re.compile(r"<(?:script|link|img)\b[^>]*>", re.I)
_BODY_TAG = re.compile(r"<body\b[^>]*>", re.I)


def _asset_urls(html: str) -> list[str]:
    """Every `<script src>`, `<link href>` and `<img src>` URL in the document.

    These three tag shapes are what `crawler.fingerprint`'s platform markers
    key on, and all of them appear in raw HTML — no rendered DOM or JS needed.
    """
    urls: list[str] = []
    for tag in _ASSET_TAG.finditer(html):
        attrs = _attrs(tag.group(0))
        url = attrs.get("src") or attrs.get("href")
        if url:
            urls.append(url)
    return urls


def _generator_meta(html: str) -> str | None:
    """The `<meta name="generator" content="...">` value, head-scoped.

    Head-scoped for the same reason as `parse_head`: WooCommerce's generator
    meta lives in `<head>`, and scoping there stops a body element with the
    same `name` from overriding it.
    """
    for tag in _META.finditer(_head_scope(html)):
        attrs = _attrs(tag.group(0))
        if (attrs.get("name") or "").lower() == "generator":
            return attrs.get("content") or None
    return None


def _body_classes(html: str) -> list[str]:
    """The `<body class="...">` token list, or `[]` if there is no body tag."""
    match = _BODY_TAG.search(html)
    if not match:
        return []
    attrs = _attrs(match.group(0))
    return (attrs.get("class") or "").split()


def platform_gate(home_html: str, declared: str) -> Gate:
    """Does `crawler.fingerprint`'s platform verdict agree with the declared one?

    Builds a `Signals` from home's raw HTML and runs it through the real
    `crawler.fingerprint.build`, not a stub of it. The Shopify and WooCommerce
    marker blocks read only `signals.urls`, `signals.meta["generator"]` and
    `signals.body_classes`, all available without a live `Session` — `Signals`
    defaults every other field to empty and `build` runs on what it's given.

    Invariant: `unknown` fails, with its own detail separate from a mismatch. A
    store whose platform can't be determined was never verified to be what it
    was declared as, and letting that read as a pass is the vacuous pass this
    module refuses elsewhere.
    """
    signals = Signals(
        urls=_asset_urls(home_html),
        meta={"generator": g} if (g := _generator_meta(home_html)) else {},
        body_classes=_body_classes(home_html),
    )
    result = build(signals)
    detected, evidence = result["platform"], result["evidence"]

    if detected == "unknown":
        return Gate(
            name="platform",
            passed=False,
            detail=(f"declared={declared!r} but detection was inconclusive — no "
                     f"platform markers found in home's HTML; evidence={evidence}"),
        )
    if detected != declared:
        return Gate(
            name="platform",
            passed=False,
            detail=(f"declared={declared!r} but detected={detected!r}; "
                     f"evidence={evidence}"),
        )
    return Gate(
        name="platform",
        passed=True,
        detail=f"declared={declared!r} matches detected platform; evidence={evidence}",
    )


# --- permalinks -------------------------------------------------------------

_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_WOO_COLLECTION = re.compile(r"^/(shop|product-category/[^/]+)/?$", re.I)


def permalink_gate(html: str, host: str, platform: str) -> Gate:
    """WooCommerce entries must use DEFAULT permalinks, or discovery cannot find them.

    Discovery keys on `/shop`, `/product-category/{slug}` and
    `/product/{slug}`. A store on customised permalinks is a hard disqualifier
    — not a store defect, and not something to route around with a pin, since
    this entry exists to exercise the non-Shopify discovery path.

    Only one default collection URL is needed; discovery takes either `/shop`
    or `/product-category/`. Product links aren't required on home, because
    discovery reaches the PDP from the collection page.

    Invariant: `_WOO_COLLECTION` matches one category segment, not a nested
    one. That's deliberate — discovery only knows the one-segment shape, so a
    store whose only collection link is nested would fail there too. Not a gap
    to widen.
    """
    if platform != "woocommerce":
        return Gate(name="permalinks", passed=True,
                    detail=f"n/a — platform is {platform}")

    if not html:
        # `home_html` is "" when home was robots-disallowed or its fetch
        # failed, so there is no permalink to have found. Still a FAIL — an
        # unassessed gate must not pass — but say what happened rather than
        # giving the diagnosis below, which describes a problem nobody saw.
        return Gate(
            name="permalinks",
            passed=False,
            detail="home was not fetched — permalinks could not be assessed",
        )

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

def apply_soft_gates(gates: list[Gate], soft: frozenset[str]) -> list[Gate]:
    """Mark every gate whose FAMILY is in `soft` as recorded-not-gating.

    The family is the part before the colon, so `lcp` covers `lcp:home`,
    `lcp:collection` and `lcp:pdp` without enumerating templates — a per-entry
    list that had to name every template would drift the moment one was added.

    Invariant: this only ever downgrades. It cannot make a gate hard, so a
    typo'd family name loses a criterion loudly (the gate still gates) rather
    than gaining one silently.
    """
    return [g if g.name.split(":")[0] not in soft else replace(g, hard=False)
            for g in gates]


def perf_gates(template: str, run: "measure.SampleRun") -> list[Gate]:
    """LCP and CLS must stay off the `high` side on EVERY run.

    Invariant: every run, not the median. A fixture is captured once and can be
    captured on the bad run, so a median under the line with one run over it
    isn't a pass — the same discipline measure.py already applies.

    Invariant: an empty sample list fails both gates. A gate that passes having
    evaluated nothing is the vacuous pass this repo has found twice.

    Reads `s.lcp`/`s.cls` directly rather than via `getattr(..., None)`, which
    would swallow a real shape mismatch as "nothing measured" — the same silent
    pass this function exists to refuse. `Sample` always carries both fields,
    set to None when Lighthouse has no reading.
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


# --- the selected entries ---------------------------------------------------

#: The selected stores, keyed by eval id so the screen re-runs as `--entry 01`
#: without anyone retyping a URL, and so the URLs live in one place beside the
#: gates that chose them.
ENTRIES: dict[str, dict] = {
    "01": {
        "origin": "https://theme-dawn-demo.myshopify.com",
        "platform": "shopify",
        "templates": {
            "home": "/",
            "collection": "/collections/bags",
            "pdp": "/products/small-convertible-flex-bag-cappuccino",
            "cart": "/cart",
            "search": "/search?q=a",
        },
    },
    "04": {
        "origin": "https://www.forestwholefoods.co.uk",
        "platform": "woocommerce",
        # Measured, printed, and NOT disqualifying — the same treatment hygiene
        # gets, for the same stated reason: screening these out means hunting
        # for a store that flatters the agent.
        #
        # The perf bar is entry 01's selection criterion. The design's perf
        # screen is headed "Demo" and covers entry-01 candidates only; entry 04
        # was selected on default permalinks, robots.txt blocking nothing we
        # need, and ICP match, and exists to exercise the reduced path and the
        # null-AOV trap. Neither needs a fast store, and the brief targets
        # low-traffic SMB stores — this one is the customer, not the exception.
        # Its 2026-07-31 screen read home LCP 19.2-19.9s, CLS 0.43, pdp LCP
        # 20.5-23.5s: real `high` findings, and exactly the must-catch labels
        # this entry currently lacks.
        "soft_gates": frozenset({"lcp", "cls"}),
        "templates": {
            "home": "/",
            "collection": "/shop/",
            "pdp": "/product/organic-almonds/",
            # Invariant: don't "correct" this to /cart/. WooCommerce lets a
            # store rename the cart slug, and this UK store uses the British
            # term — /cart/ 404s here, /basket/ serves 200. That guess was
            # wrong once already.
            "cart": "/basket/",
            "search": "/?s=a",
        },
    },
}

#: The templates a shopper must pass through to buy something (rubric §1).
#: Governs the perf and indexable gates. cart and search are left out of both:
#:   - perf: cart often sits behind an empty-cart redirect, so its LCP
#:     describes that redirect more than the theme.
#:   - indexable: a `noindex` there is normal SEO hygiene, not a defect, and
#:     gating on it produces a false re-selection trigger.
#: reachable is still checked on every template; only these two narrow.
_REVENUE_TEMPLATES = ("home", "collection", "pdp")


def _fetch(url: str, timeout: int = 30) -> tuple[int, str, str]:
    """One polite GET. Identifying UA, matching specs/crawler.md §3 conduct.

    Returns `(status, html, final_url)`. `final_url` is the URL after any
    redirects, because a gated Shopify storefront 302s to `/password` and
    serves the form there — a caller reading only the requested URL's body
    would never see the redirect happened.

    Invariant: keep catching network failures below the HTTP layer. DNS,
    connection timeouts and TLS errors raise URLError or OSError rather than
    HTTPError, so there's no status to read, and uncaught they abort the whole
    run as a traceback before any gate report prints. They become the sentinel
    `status == 0`, with `final_url` carrying a readable reason instead of a
    URL. Never swallowed — `reachable` still fails, with the real reason
    attached.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": ROBOTS_UA, "Accept-Encoding": "gzip",
                      "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return resp.status, raw.decode("utf-8", "replace"), resp.url
    except urllib.error.HTTPError as exc:
        return exc.code, "", exc.url or url
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return 0, "", f"{url} — fetch failed: {reason}"


# --- IPv4 preference --------------------------------------------------------
#
# `urllib` has no Happy Eyeballs: it walks `getaddrinfo`'s list in order and
# blocks on each address until the connect timeout. On a host whose IPv6 is
# advertised but has no upstream transit, every dual-stack fetch therefore pays
# a full ~60s connect timeout before falling back to IPv4 — measured 63.88s
# against entry 04's host, whose IPv4 path answers in 0.96s. That artefact is
# what produced entry 04's retracted "LCP 19-23s" figures, so this is a
# correctness fix for the screen's numbers, not only a speed one.
#
# Chromium does implement Happy Eyeballs and fails over in ~300ms, so
# `measure.py` and the capture path are unaffected and are deliberately left
# alone: forcing a family there would change capture conduct to work around a
# host quirk.
#: Marks our wrapper so `prefer_ipv4` can tell whether the `getaddrinfo`
#: currently installed is ours. A module-level "already done" flag would not:
#: it outlives the wrapping it claims to describe, so anything that replaces
#: `socket.getaddrinfo` afterwards (a test's monkeypatch, another library)
#: leaves the flag asserting a preference that is no longer installed.
_MARK = "_prefers_ipv4"


def _ipv4_first(infos: list[tuple]) -> list[tuple]:
    """`getaddrinfo` results with the IPv4 addresses moved to the front.

    Invariant: reorder, never filter. Dropping AF_INET6 would make a genuinely
    IPv6-only host unreachable — trading a local host quirk for a capability
    loss. The sort is stable, so DNS round-robin order survives within a family.
    """
    return sorted(infos, key=lambda info: info[0] != socket.AF_INET)


def prefer_ipv4() -> None:
    """Make this process try IPv4 before IPv6 for every name it resolves.

    Idempotent: `main` may run more than once per process (the test suite does),
    and wrapping an already-wrapped `getaddrinfo` would nest pointlessly.
    """
    if getattr(socket.getaddrinfo, _MARK, False):
        return
    _inner = socket.getaddrinfo

    def _wrapped(*args, **kwargs):
        return _ipv4_first(_inner(*args, **kwargs))

    setattr(_wrapped, _MARK, True)
    socket.getaddrinfo = _wrapped


_DEFAULT_DELAY = 1.5

_CRAWL_DELAY = re.compile(r"(?im)^\s*crawl-delay\s*:\s*([\d.]+)")


def effective_delay(robots_body: str | None) -> float:
    """The delay, in seconds, to hold between every polite fetch.

    Invariant: the higher of our floor and robots.txt's Crawl-delay always
    wins, never the lower. Politeness is non-negotiable for stores this project
    doesn't own, with no carve-out for its own tooling — so a declared delay
    below the 1.5s floor doesn't shrink the gap, and an absent, unfetchable or
    malformed directive falls back to the floor rather than to 0.
    """
    if robots_body:
        match = _CRAWL_DELAY.search(robots_body)
        if match:
            try:
                return max(_DEFAULT_DELAY, float(match.group(1)))
            except ValueError:
                pass
    return _DEFAULT_DELAY


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: screen one candidate entry and report its gates."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entry", choices=sorted(ENTRIES), required=True)
    parser.add_argument("--runs", type=int, default=2,
                        help="Lighthouse runs per revenue template (default 2)")
    parser.add_argument("--skip-perf", action="store_true",
                        help="Head and permalink gates only — no browser")
    parser.add_argument("--debug-port", type=int, default=9223)
    args = parser.parse_args(argv)

    # Before the first probe, not after: robots.txt is this screen's very first
    # network act and it gates every template that follows, so a preference
    # installed later would leave that one fetch paying the full IPv6 timeout.
    prefer_ipv4()

    entry = ENTRIES[args.entry]
    origin, platform = entry["origin"], entry["platform"]
    print(f"screening entry {args.entry}: {origin}  (declared platform: {platform})\n")

    gates: list[Gate] = []
    hygiene: list[str] = []
    home_html = ""

    # --- robots.txt, fetched FIRST and respected (specs/crawler.md §3) -----
    # Recorded and gated. Parsed before any template is touched, so the notes,
    # the disallow set and the delay are all ready before the probe loop
    # starts — reporting what robots blocks after fetching it would be
    # backwards.
    status, robots_body_raw, robots_final_url = _fetch(origin + "/robots.txt")
    notes: list[str] = []
    robots_body = robots_body_raw if status == 200 and robots_body_raw else None
    disallowed: set[str] = set()
    if robots_body:
        robots = Robots.parse(robots_body)
        disallowed = {t for t, p in entry["templates"].items() if not robots.allows(origin + p)}
        notes.append(f"robots.txt blocks: {sorted(disallowed) or 'nothing probed'}")
        delay_match = _CRAWL_DELAY.search(robots_body)
        if delay_match:
            notes.append(f"robots.txt declares Crawl-delay: {delay_match.group(1)}"
                         f" — conduct requires honouring it (design D6)")
    else:
        # `status == 0` is `_fetch`'s sentinel for a below-HTTP failure, with
        # the readable reason smuggled through the final_url slot instead of
        # a URL — same convention `assemble_head_gates` already reads.
        detail = f"HTTP {status}" if status else robots_final_url
        notes.append(f"robots.txt: {detail}")

    # The only place allowed to fall back to the floor silently — everywhere
    # else uses `delay`, already raised to any declared Crawl-delay. Printed
    # so the run's output evidences the conduct instead of asserting it: this
    # once printed the Crawl-delay note while still spacing requests 1.5s
    # apart regardless.
    delay = effective_delay(robots_body)
    reason = "robots.txt Crawl-delay" if delay > _DEFAULT_DELAY else "default"
    notes.append(f"politeness: {delay:.1f}s between fetches ({reason})")

    # Same reasoning as the politeness note: `prefer_ipv4` reorders DNS results
    # for the whole process, and a screen whose figures were retracted once for
    # a DNS-shaped reason should evidence that in its own output rather than
    # leave it to whoever reads the source.
    notes.append("resolver: IPv4 tried before IPv6 (a dead AAAA route would "
                 "otherwise cost ~60s per fetch and has skewed this screen before)")

    # --- head probe, one polite GET per template ----------------------------
    # `delay` is held before every fetch, the first template included —
    # robots.txt already used its own slot before the loop started.
    #
    # Invariant: a template robots.txt disallows is never fetched, and that's a
    # failing gate rather than a skip. Conduct is non-negotiable for stores
    # this project doesn't own, and a candidate was already rejected for
    # exactly this on a revenue template.
    for template, path in entry["templates"].items():
        if template in disallowed:
            gates.append(Gate(
                f"robots_allows:{template}", False,
                "robots.txt disallows this template — not fetched (design D2)",
            ))
            continue
        time.sleep(delay)
        url = origin + path
        status, html, final_url = _fetch(url)
        if template == "home":
            home_html = html
        new_gates, hygiene_line = assemble_head_gates(template, status, html, final_url)
        gates.extend(new_gates)
        if hygiene_line:
            hygiene.append(hygiene_line)

    gates.append(platform_gate(home_html, platform))
    gates.append(permalink_gate(home_html, urlparse(origin).netloc, platform))

    # --- performance --------------------------------------------------------
    if not args.skip_perf:
        for template in _REVENUE_TEMPLATES:
            path = entry["templates"].get(template)
            if not path:
                # A missing revenue template is a gap in ENTRIES, not something
                # to pass over quietly — the verdict must not read "fit to
                # capture" while a whole template's perf was never attempted.
                gates.append(Gate(
                    f"lcp:{template}", False,
                    f"no {template!r} path in ENTRIES['{args.entry}']['templates'] "
                    f"— performance cannot be screened for it",
                ))
                continue
            if template in disallowed:
                # Already failed as `robots_allows:{template}` in the head
                # probe, and conduct forbids fetching it again for Lighthouse.
                continue
            run = measure.sample_url(origin + path, runs=args.runs,
                                     password=None, debug_port=args.debug_port,
                                     echo=False)
            if run.blocked:
                print(f"blocked at the gate on {template}: {run.blocked}", file=sys.stderr)
                return 1
            gates.extend(perf_gates(template, run))

    # --- report -------------------------------------------------------------
    gates = apply_soft_gates(gates, entry.get("soft_gates", frozenset()))
    hard = [g for g in gates if g.hard]
    soft = [g for g in gates if not g.hard]

    print("gates")
    for gate in hard:
        print(f"  [{'PASS' if gate.passed else 'FAIL'}] {gate.name:<20} {gate.detail}")

    # Printed in their own block rather than dropped. A number that stops
    # disqualifying must not stop being visible — these become labels, and a
    # reader must not mistake a green exit for a fast store.
    if soft:
        print(f"\nperf (recorded, NOT a gate for entry {args.entry} — these become labels)")
        for gate in soft:
            print(f"  [{'ok ' if gate.passed else 'OVER'}] {gate.name:<20} {gate.detail}")

    print("\nseo hygiene (recorded, NOT a gate — these become labels)")
    for line in hygiene:
        print(line)
    print("\nnotes")
    for note in notes:
        print(f"  {note}")

    if args.skip_perf:
        print("\nPERF NOT SCREENED — lcp/cls gates were not evaluated")

    failed = [g for g in hard if not g.passed]
    if failed:
        print(f"\nRE-SELECTION TRIGGER — {len(failed)} hard gate(s) failed: "
              f"{', '.join(g.name for g in failed)}")
        return 2
    over = [g for g in soft if not g.passed]
    if args.skip_perf:
        print(f"\nall {len(hard)} head gates passed — perf NOT screened, "
              f"entry {args.entry} is NOT cleared to capture")
        return 3
    print(f"\nall {len(hard)} hard gates passed — entry {args.entry} is fit to capture")
    if over:
        print(f"  ({len(over)} recorded perf measurement(s) over the rubric line: "
              f"{', '.join(g.name for g in over)} — label these, don't re-select)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
