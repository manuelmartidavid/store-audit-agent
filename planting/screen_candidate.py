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
    permalinks   WooCommerce only: default /shop|/product-category|/product

There is deliberately NO platform gate. `crawler.fingerprint.build` needs real
HTTP response headers, live browser cookies, and `page.evaluate` results
(`window.Shopify`, via crawler/js/signals.js) — none of which this screen's
plain `urllib` head-probe fetch produces, so a live `crawler.Session` would be
required to check it here.

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

import argparse
import gzip
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape as _html_unescape
from pathlib import Path
from urllib.parse import urlparse, urlsplit

# planting/ is not a package; reach crawler/ the way measure.py does. Both
# entries are needed: parents[1] (project root) for `crawler.*`, and this
# file's own directory for the bare `import measure` below — the docstring
# above documents `python -m planting.screen_candidate` as the entrypoint,
# and under `-m` the script's own directory is NOT auto-added to sys.path
# (only cwd is), unlike `python planting/screen_candidate.py`. Without this
# second insert, `import measure` only resolves under the invocation the
# module does not document.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import measure
from crawler.config import ROBOTS_UA
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

    This function does NOT scope itself to revenue templates — it will happily
    build an indexable gate for `cart` or `search` if asked to. The scoping
    happens at the call site, `assemble_head_gates`, which only invokes this
    for templates in `_REVENUE_TEMPLATES`. A future direct caller must apply
    that same scoping itself, or risk the exact false re-selection trigger
    `assemble_head_gates`'s docstring records for `/?s=a`.
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

    Pure and network-free so the indexable-gate SCOPING is directly testable:
    `indexable_gate` is only appended for templates in `_REVENUE_TEMPLATES`.
    A `noindex` on cart or search (e.g. forestwholefoods.co.uk's `/?s=a`,
    which correctly serves `noindex, follow`) is normal SEO hygiene, not a
    defect — gating on it is a false re-selection trigger, not a real one.
    `reachable` still runs on EVERY template, including cart and search;
    only `indexable` (and, separately, perf) narrow to revenue templates.

    Returns `([Gate(...)], None)` when the fetch itself failed (non-200 or
    empty body) — there are no head facts to build hygiene or indexable from
    in that case, only the fact that the template was unreachable.
    """
    if status != 200 or not html:
        # status == 0 is `_fetch`'s sentinel for a network failure (DNS,
        # connection timeout, TLS, ...) rather than an HTTP response at all —
        # `final_url` carries the readable reason in that case, not a URL.
        # See `_fetch`'s docstring.
        detail = f"HTTP {status}" if status else final_url
        return [Gate(f"reachable:{template}", False, detail)], None

    facts = parse_head(html, status)
    # A gate can show up two ways: a <form action="/password"> served
    # in-page, OR a redirect that already landed on /password before any
    # form is even parsed (measure._is_gate_url — reused rather than
    # respelled here, see MNC-004 in measure.py). Either one disqualifies.
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


# --- the selected entries ---------------------------------------------------

#: The stores selected on 2026-07-29 (design D1, D2). Keyed by eval id so the
#: screen can be re-run as `--entry 01` without anyone retyping a URL, and so
#: the URLs live in exactly one place alongside the gates that chose them.
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
        "templates": {
            "home": "/",
            "collection": "/shop/",
            "pdp": "/product/organic-almonds/",
            # WooCommerce lets a store rename the cart page slug; this is a
            # UK store and uses the British term. Verified directly: /cart/
            # 404s here, /basket/ serves 200. Do not "correct" this back to
            # /cart/ — that guess is what was wrong the first time.
            "cart": "/basket/",
            "search": "/?s=a",
        },
    },
}

#: The templates rubric §1 calls "revenue" templates — the ones a shopper must
#: pass through to buy something. Governs TWO gates: perf (LCP/CLS) and
#: indexable. cart and search are deliberately excluded from both:
#:   - perf: cart sits behind an empty-cart redirect on many stores, and its
#:     LCP says more about that redirect than about the theme.
#:   - indexable: a `noindex` on cart or search is normal SEO hygiene
#:     (WooCommerce/Yoast set it by default so these pages don't compete with
#:     revenue templates in search) — NOT a defect. Gating on it produces a
#:     false re-selection trigger, exactly what happened to entry 04's
#:     `/?s=a` on 2026-07-29. reachable is still checked on every template,
#:     including cart and search — only indexable and perf narrow to revenue.
_REVENUE_TEMPLATES = ("home", "collection", "pdp")


def _fetch(url: str, timeout: int = 30) -> tuple[int, str, str]:
    """One polite GET. Identifying UA, matching specs/crawler.md §3 conduct.

    Returns `(status, html, final_url)`. `final_url` is `resp.url` — the URL
    after any redirects urllib followed — because a gated Shopify storefront
    does not serve its password form at the requested URL, it 302s to
    `/password` and serves the form THERE
    (`torontosportscard.myshopify.com/` -> `.../password`). A caller reading
    only the body of the originally-requested URL would never see that
    redirect happened.

    A network failure below the HTTP layer — DNS failure, connection timeout,
    a TLS error — raises `URLError` (or a bare `OSError` for some of those,
    e.g. a `socket.timeout`), not `HTTPError`; there is no HTTP response to
    read a status from. This path is LIVE, not theoretical: this project has
    a machine with a broken route to one of the two entry stores. Left
    uncaught it aborts the whole run as a bare traceback before any gate
    report prints — the same shape `build_brief.py::main()` was fixed for in
    d8e5bfb. So it is caught here too and turned into the sentinel
    `status == 0`, with `final_url` repurposed to carry a human-readable
    reason instead of a URL. `assemble_head_gates` treats any non-200 status
    as a `reachable` failure already; it special-cases `0` only to source the
    detail text from `final_url` instead of formatting `"HTTP 0"`, which
    would name nothing. The failure is never swallowed — `reachable` still
    FAILS, with the real reason attached.
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


_DEFAULT_DELAY = 1.5

_CRAWL_DELAY = re.compile(r"(?im)^\s*crawl-delay\s*:\s*([\d.]+)")


def effective_delay(robots_body: str | None) -> float:
    """The delay, in seconds, to hold between every polite fetch.

    `max(default floor, robots.txt's declared Crawl-delay)` — the HIGHER of
    the two always wins, never the lower. specs/crawler.md §3 says robots.txt
    is "fetched first and respected"; the project's brief §5 calls politeness
    non-negotiable for stores this project does not own, with no carve-out
    for the project's own tooling. So a declared Crawl-delay below our own
    1.5s floor does not shrink the gap, and an absent, unfetchable
    (`robots_body is None`), or malformed directive (e.g. `Crawl-delay: abc` —
    `_CRAWL_DELAY` simply fails to match it) falls back to the floor rather
    than raising or silently defaulting to 0.
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entry", choices=sorted(ENTRIES), required=True)
    parser.add_argument("--runs", type=int, default=2,
                        help="Lighthouse runs per revenue template (default 2)")
    parser.add_argument("--skip-perf", action="store_true",
                        help="Head and permalink gates only — no browser")
    parser.add_argument("--debug-port", type=int, default=9223)
    args = parser.parse_args(argv)

    entry = ENTRIES[args.entry]
    origin, platform = entry["origin"], entry["platform"]
    print(f"screening entry {args.entry}: {origin}  (declared platform: {platform})\n")

    gates: list[Gate] = []
    hygiene: list[str] = []
    home_html = ""

    # --- robots.txt, fetched FIRST and respected (specs/crawler.md §3) -----
    # Recorded AND gated — fetched and parsed before a single template is
    # touched, so `notes`, `disallowed` (below), and the delay every
    # subsequent fetch uses are ready before the probe loop starts. Reporting
    # which templates robots blocks AFTER already fetching them would be
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

    # This is the ONLY spot allowed to fall back to the 1.5s floor silently:
    # everywhere else in this function, that floor is `delay`, already
    # raised to match a real Crawl-delay if one was declared. Printed too, so
    # the run's own output evidences the conduct rather than merely asserting
    # it (the module used to print the Crawl-delay note while spacing its own
    # requests 1.5s apart regardless — asserting an obligation in the same
    # breath it failed to meet it).
    delay = effective_delay(robots_body)
    reason = "robots.txt Crawl-delay" if delay > _DEFAULT_DELAY else "default"
    notes.append(f"politeness: {delay:.1f}s between fetches ({reason})")

    # --- head probe, one polite GET per template ----------------------------
    # `delay` is held before EVERY fetch here, including before the first
    # template — i.e. between robots.txt and that first fetch too. There is
    # no exemption for "the first one": robots.txt already used its own slot
    # before this loop started.
    #
    # A template robots.txt disallows is NOT fetched — brief §5 calls conduct
    # non-negotiable for stores this project does not own, and design D2
    # rejected the alternative store (Nalgene) for exactly this condition on
    # a revenue template. So the same condition here is a FAILING gate, not a
    # skip: the `disallowed` check above is what makes D2's disqualifier a
    # real gate, and what makes the "respected" claim in this section's
    # header true rather than aspirational.
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

    gates.append(permalink_gate(home_html, urlparse(origin).netloc, platform))

    # --- performance --------------------------------------------------------
    if not args.skip_perf:
        for template in _REVENUE_TEMPLATES:
            path = entry["templates"].get(template)
            if not path:
                # A missing revenue template is a gap in ENTRIES, not
                # something to pass over quietly — the verdict below must not
                # be able to say "fit to capture" while a whole template's
                # perf was never even attempted.
                gates.append(Gate(
                    f"lcp:{template}", False,
                    f"no {template!r} path in ENTRIES['{args.entry}']['templates'] "
                    f"— performance cannot be screened for it",
                ))
                continue
            if template in disallowed:
                # Already recorded as a failing `robots_allows:{template}`
                # gate in the head probe above; conduct forbids fetching it
                # again here for a Lighthouse run.
                continue
            run = measure.sample_url(origin + path, runs=args.runs,
                                     password=None, debug_port=args.debug_port,
                                     echo=False)
            if run.blocked:
                print(f"blocked at the gate on {template}: {run.blocked}", file=sys.stderr)
                return 1
            gates.extend(perf_gates(template, run))

    # --- report -------------------------------------------------------------
    print("gates")
    for gate in gates:
        print(f"  [{'PASS' if gate.passed else 'FAIL'}] {gate.name:<20} {gate.detail}")
    print("\nseo hygiene (recorded, NOT a gate — these become labels)")
    for line in hygiene:
        print(line)
    print("\nnotes")
    for note in notes:
        print(f"  {note}")

    if args.skip_perf:
        print("\nPERF NOT SCREENED — lcp/cls gates were not evaluated")

    failed = [g for g in gates if not g.passed]
    if failed:
        print(f"\nRE-SELECTION TRIGGER — {len(failed)} hard gate(s) failed: "
              f"{', '.join(g.name for g in failed)}")
        return 2
    if args.skip_perf:
        print(f"\nall {len(gates)} head gates passed — perf NOT screened, "
              f"entry {args.entry} is NOT cleared to capture")
        return 0
    print(f"\nall {len(gates)} hard gates passed — entry {args.entry} is fit to capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
