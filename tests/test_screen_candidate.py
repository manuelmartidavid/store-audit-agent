"""The candidate screen's pure layer — no network, no browser.

Entries 01 and 04 are stores we do not own, so the criteria that selected them
have to be re-runnable before capture (design 2026-07-29 D5). These pin the
parsing and the verdicts; the network and browser paths are exercised by
running the tool, the same split tests/test_measure.py uses.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planting"))

import screen_candidate as sc  # noqa: E402
import measure  # noqa: E402  (same sys.path bootstrap as screen_candidate)


class _StubSample:
    """measure.Sample carries fields the perf gates never read.

    A stub keeps these tests independent of that dataclass's full shape, while
    the SampleRun wrapper around it stays the real type — so a field rename in
    SampleRun breaks these tests, which is the point.
    """

    def __init__(self, lcp: float | None, cls: float | None):
        self.lcp = lcp
        self.cls = cls


# --- parse_head -------------------------------------------------------------

HEAD = """<!doctype html><html><head>
<title>  Bags &ndash; theme-dawn-demo </title>
<meta name="description" content="Organic almonds and cashews">
<meta name="robots" content="noindex, nofollow">
<meta property="og:title" content="ignored">
</head><body></body></html>"""


def test_parse_head_reads_title_description_and_robots():
    facts = sc.parse_head(HEAD, 200)
    assert facts.title == "Bags &ndash; theme-dawn-demo"
    assert facts.description == "Organic almonds and cashews"
    assert facts.robots == "noindex, nofollow"
    assert facts.http_status == 200


def test_parse_head_reports_absent_fields_as_none_not_empty_string():
    facts = sc.parse_head("<html><head><title>x</title></head></html>", 200)
    assert facts.description is None
    assert facts.robots is None


def test_parse_head_treats_an_empty_description_as_absent():
    # broadcast-theme-main serves content="" — an empty description is a missing
    # one, and letting "" through would report hygiene the store does not have.
    facts = sc.parse_head('<head><meta name="description" content=""></head>', 200)
    assert facts.description is None


def test_parse_head_accepts_single_quoted_attributes():
    facts = sc.parse_head("<head><meta name='robots' content='noindex'></head>", 200)
    assert facts.robots == "noindex"


def test_parse_head_is_not_overridden_by_a_body_meta_robots():
    # Regression: parse_head used to scan the WHOLE document, and the
    # meta-robots loop kept the LAST match anywhere — so a body
    # "index, follow" (some themes duplicate robots meta outside <head>)
    # silently overrode a real head noindex. That is a false negative on the
    # gate that eliminated 4 of 9 candidate stores during selection.
    html = (
        "<html><head><meta name=\"robots\" content=\"noindex\"></head>"
        "<body><meta name=\"robots\" content=\"index, follow\"></body></html>"
    )
    facts = sc.parse_head(html, 200)
    assert sc.is_noindex(facts.robots) is True


def test_parse_head_reads_title_from_head_even_with_a_body_title():
    # Some themes emit a second <title> inside an inline SVG in the body.
    # _TITLE.search keeps the FIRST match, so an unscoped scan happens to
    # get this one right today — but only by the accident of document order;
    # scoping to <head> makes it correct by construction.
    html = (
        "<html><head><title>Real Title</title></head>"
        "<body><svg><title>icon</title></svg></body></html>"
    )
    facts = sc.parse_head(html, 200)
    assert facts.title == "Real Title"


def test_parse_head_falls_back_to_whole_document_when_there_is_no_head():
    facts = sc.parse_head("<html><body><title>x</title></body></html>", 200)
    assert facts.title == "x"


def test_parse_head_detects_a_storefront_password_form():
    html = '<head></head><body><form action="/password"><input type="password" name="p"></form></body>'
    assert sc.parse_head(html, 200).password_form is True


SHOPIFY_GATE_HTML = """<!doctype html><html><head><title>Password &middot; torontosportscard</title></head>
<body>
<form method="post" action="/password" id="login_form" accept-charset="UTF-8" class="storefront-password-form">
<input type="password" name="password" id="password" autofocus>
</form>
</body></html>"""


def test_parse_head_detects_the_real_shopify_storefront_gate():
    # Ground truth fetched from this project's own gated store:
    # final URL https://torontosportscard.myshopify.com/password
    assert sc.parse_head(SHOPIFY_GATE_HTML, 200).password_form is True


def test_parse_head_does_not_flag_a_customer_login_drawer_as_gated():
    # Many themes render a password <input> for the customer-login drawer in
    # the header of every page. That input alone must not disqualify a
    # perfectly reachable store — only a <form> whose action targets
    # /password (the actual storefront gate) may.
    html = (
        '<head><title>Shop</title></head><body>'
        '<form action="/account/login" method="post">'
        '<input type="password" name="customer[password]">'
        '</form></body>'
    )
    assert sc.parse_head(html, 200).password_form is False


# --- is_noindex -------------------------------------------------------------

@pytest.mark.parametrize("value", ["noindex", "NOINDEX", "noindex, nofollow",
                                   "  none  ", "index, noindex"])
def test_is_noindex_true(value):
    assert sc.is_noindex(value) is True


@pytest.mark.parametrize("value", [None, "", "index, follow",
                                   "index, follow, max-image-preview:large"])
def test_is_noindex_false(value):
    assert sc.is_noindex(value) is False


def test_is_noindex_treats_none_directive_as_noindex():
    # `none` is shorthand for `noindex, nofollow` and is easy to miss.
    assert sc.is_noindex("none") is True


# --- indexable_gate ---------------------------------------------------------

def test_indexable_gate_fails_on_noindex_and_says_it_is_a_critical():
    facts = sc.parse_head('<head><meta name="robots" content="noindex"></head>', 200)
    gate = sc.indexable_gate("home", facts)
    assert gate.passed is False
    assert gate.name == "indexable:home"
    assert "critical" in gate.detail.lower()


def test_indexable_gate_passes_when_no_robots_meta_present():
    gate = sc.indexable_gate("home", sc.parse_head("<head></head>", 200))
    assert gate.passed is True


# --- _REVENUE_TEMPLATES ------------------------------------------------------

def test_revenue_templates_is_exactly_home_collection_pdp():
    # Regression: this constant used to be named _PERF_TEMPLATES and only
    # governed the perf gates. It now also scopes indexable_gate — cart and
    # search must stay OUT of it, or a noindex on cart/search (normal SEO
    # hygiene) starts producing a false re-selection trigger again.
    assert set(sc._REVENUE_TEMPLATES) == {"home", "collection", "pdp"}
    assert "cart" not in sc._REVENUE_TEMPLATES
    assert "search" not in sc._REVENUE_TEMPLATES


# --- assemble_head_gates -----------------------------------------------------

NOINDEX_HEAD = '<head><meta name="robots" content="noindex, follow"></head>'


def test_assemble_head_gates_does_not_fail_indexable_on_a_noindex_search_page():
    # https://www.forestwholefoods.co.uk/?s=a serves noindex, follow — correct
    # SEO practice for a search-results page (Yoast/WooCommerce default), not
    # a defect. Gating on it is a false re-selection trigger.
    gates, _hygiene = sc.assemble_head_gates("search", 200, NOINDEX_HEAD, "https://x.test/?s=a")
    assert not any(g.name.startswith("indexable") for g in gates)
    assert all(g.passed for g in gates)


def test_assemble_head_gates_still_fails_indexable_on_a_noindex_home_page():
    gates, _hygiene = sc.assemble_head_gates("home", 200, NOINDEX_HEAD, "https://x.test/")
    indexable = next(g for g in gates if g.name.startswith("indexable"))
    assert indexable.passed is False


def test_assemble_head_gates_still_checks_reachable_on_cart_and_search():
    # Only indexable (and perf) narrow to revenue templates — reachable keeps
    # probing every template, cart and search included.
    gates, _hygiene = sc.assemble_head_gates("cart", 404, "", "https://x.test/cart/")
    reachable = next(g for g in gates if g.name.startswith("reachable"))
    assert reachable.passed is False
    assert "404" in reachable.detail


def test_assemble_head_gates_returns_no_hygiene_line_on_fetch_failure():
    gates, hygiene_line = sc.assemble_head_gates("home", 404, "", "https://x.test/")
    assert hygiene_line is None
    assert len(gates) == 1  # reachable only — no facts to build indexable from


# --- assemble_head_gates: the gate-redirect check (Finding 1) --------------
#
# `redirected_to_gate = measure._is_gate_url(final_url)` had ZERO test
# coverage before this: a reviewer replaced it with `redirected_to_gate =
# False` and all existing tests still passed. This is the FALSE-PASS mode —
# a gated Shopify store 302s to /password and serves its form THERE, and this
# is the half of gate detection that catches that when no <form> is served
# at the originally-requested URL (e.g. a JS-rendered gate page, or a probe
# that only fetched the head). No prior test ever drove `assemble_head_gates`
# with a /password final URL. These do, across the three shapes
# `measure._is_gate_url` is documented to handle: bare, trailing slash, and
# a query string (urlparse separates the query from the path, so the query
# variant exercises that `_is_gate_url` reads `.path`, not the raw string).

@pytest.mark.parametrize("final_url", [
    "https://x.test/password",
    "https://x.test/password/",
    "https://x.test/password?x=1",
])
def test_assemble_head_gates_fails_reachable_when_redirected_to_the_password_gate(final_url):
    # No <form action="/password"> in this HTML — the ONLY signal that this
    # landed on the gate is the redirect target itself.
    gates, _hygiene = sc.assemble_head_gates("home", 200, "<head></head>", final_url)
    reachable = next(g for g in gates if g.name.startswith("reachable"))
    assert reachable.passed is False
    assert "password" in reachable.detail.lower()


def test_assemble_head_gates_passes_reachable_when_not_redirected_to_the_gate():
    # Sanity check on the other side of the same branch: a normal 200 with no
    # password form and no gate redirect must still pass.
    gates, _hygiene = sc.assemble_head_gates("home", 200, "<head></head>", "https://x.test/")
    reachable = next(g for g in gates if g.name.startswith("reachable"))
    assert reachable.passed is True


# --- assemble_head_gates: network failures (Finding 3) ----------------------

def test_assemble_head_gates_reports_a_readable_detail_on_a_network_failure():
    # `_fetch`'s sentinel for a below-HTTP failure: status == 0, with the
    # human-readable reason smuggled through the final_url slot (see
    # `_fetch`'s docstring). `assemble_head_gates` must surface that reason,
    # not print a meaningless "HTTP 0".
    gates, hygiene_line = sc.assemble_head_gates(
        "home", 0, "",
        "https://www.forestwholefoods.co.uk/ — fetch failed: "
        "[Errno 11001] getaddrinfo failed")
    assert hygiene_line is None
    reachable = gates[0]
    assert reachable.name == "reachable:home"
    assert reachable.passed is False
    assert "getaddrinfo failed" in reachable.detail
    assert reachable.detail != "HTTP 0"


# --- permalink_gate ---------------------------------------------------------

WOO_DEFAULT = """<body>
<a href="/shop/">Shop</a>
<a href="https://ex.test/product-category/bakery/">Bakery</a>
<a href="https://ex.test/product/organic-almonds/">Almonds</a>
<a href="/cart/">Cart</a>
</body>"""

WOO_CUSTOM = """<body>
<a href="/store/">Store</a>
<a href="/store/bakery/">Bakery</a>
<a href="/store/bakery/organic-almonds/">Almonds</a>
</body>"""


def test_permalink_gate_passes_on_default_woocommerce_urls():
    gate = sc.permalink_gate(WOO_DEFAULT, "ex.test", "woocommerce")
    assert gate.passed is True


def test_permalink_gate_fails_on_customised_permalinks():
    gate = sc.permalink_gate(WOO_CUSTOM, "ex.test", "woocommerce")
    assert gate.passed is False
    assert "discovery" in gate.detail.lower()


def test_permalink_gate_accepts_product_category_without_a_shop_root():
    # offermanwoodshop.com exposes /product-category/ but no /shop/ — discovery
    # needs ONE default collection URL, not both.
    html = '<a href="/product-category/hearth/">Hearth</a>'
    assert sc.permalink_gate(html, "ex.test", "woocommerce").passed is True


def test_permalink_gate_does_not_require_product_links_on_home():
    # Discovery finds the PDP from the COLLECTION page, not from home
    # (specs/crawler.md §3). The first screening pass got this wrong and
    # disqualified offermanwoodshop for it.
    html = '<a href="/shop/">Shop</a>'
    assert sc.permalink_gate(html, "ex.test", "woocommerce").passed is True


def test_permalink_gate_is_not_applicable_to_shopify():
    gate = sc.permalink_gate("<body></body>", "ex.test", "shopify")
    assert gate.passed is True
    assert "n/a" in gate.detail.lower()


# --- perf_gates -------------------------------------------------------------

def _run(*pairs):
    samples = [_StubSample(lcp=lcp, cls=cls) for lcp, cls in pairs]
    return measure.SampleRun(samples=samples, failed=0, gate_leak=False, blocked=None)


def test_perf_gates_pass_below_the_thresholds():
    gates = sc.perf_gates("home", _run((2420.0, 0.0), (2430.0, 0.0)))
    assert all(g.passed for g in gates)


def test_perf_gates_fail_when_any_run_exceeds_lcp_4s():
    # EVERY run must hold. A median under the line with one run over it is the
    # "aim has not landed" case measure.py already refuses to call a pass.
    gates = sc.perf_gates("home", _run((3900.0, 0.0), (4950.0, 0.0)))
    lcp = next(g for g in gates if g.name.startswith("lcp"))
    assert lcp.passed is False
    assert "high" in lcp.detail.lower()


def test_perf_gates_pass_at_exactly_the_boundary():
    # rubric §1: boundary values take the LOWER level. 4000ms is medium.
    gates = sc.perf_gates("home", _run((4000.0, 0.25)))
    assert all(g.passed for g in gates)


def test_perf_gates_fail_on_cls_above_the_threshold():
    gates = sc.perf_gates("pdp", _run((2000.0, 0.31)))
    cls = next(g for g in gates if g.name.startswith("cls"))
    assert cls.passed is False


def test_perf_gates_fail_when_nothing_was_measured():
    # An empty sample list is an operational failure, not a silent pass — the
    # exact shape eval_triage's vacuous-gate bug took.
    gates = sc.perf_gates("home", measure.SampleRun(samples=[], failed=3,
                                                    gate_leak=False, blocked=None))
    assert all(g.passed is False for g in gates)


# --- ENTRIES: entry 04's cart slug (Finding 1) -------------------------------

def test_entry_04_cart_slug_is_basket_not_cart():
    # /cart/ genuinely 404s on forestwholefoods.co.uk (verified directly);
    # /basket/ is the real slug, a UK-store WooCommerce rename. There is a
    # comment next to the ENTRIES entry asking people not to "correct" this
    # back to /cart/ — a comment requests, this test enforces.
    assert sc.ENTRIES["04"]["templates"]["cart"] == "/basket/"


# --- effective_delay (Finding 2) --------------------------------------------

def test_effective_delay_uses_a_declared_crawl_delay_above_the_floor():
    assert sc.effective_delay("User-agent: *\nCrawl-delay: 10\n") == 10.0


def test_effective_delay_floors_a_declared_crawl_delay_below_1_5s():
    # The floor wins — a store declaring a SMALLER Crawl-delay does not make
    # this tool less polite than its own default.
    assert sc.effective_delay("User-agent: *\nCrawl-delay: 0.5\n") == 1.5


def test_effective_delay_defaults_to_1_5s_with_no_directive():
    assert sc.effective_delay("User-agent: *\nDisallow: /admin\n") == 1.5


def test_effective_delay_defaults_to_1_5s_when_unfetchable():
    assert sc.effective_delay(None) == 1.5


def test_effective_delay_defaults_to_1_5s_on_an_empty_body():
    assert sc.effective_delay("") == 1.5


def test_effective_delay_does_not_raise_on_a_malformed_crawl_delay():
    # A non-numeric Crawl-delay value must fall back to the floor, not raise.
    assert sc.effective_delay("User-agent: *\nCrawl-delay: abc\n") == 1.5


# --- _fetch: network failures below the HTTP layer (Finding 3) --------------

def test_fetch_returns_a_sentinel_instead_of_raising_on_a_urlerror(monkeypatch):
    # DNS failure, connection timeout, TLS errors: all surface as URLError
    # (sometimes wrapping a bare OSError as .reason), not HTTPError. This
    # path is LIVE — this machine currently cannot reach one of the two entry
    # stores. Uncaught, this used to abort the whole run as a bare traceback
    # before any gate report printed.
    def _boom(*_args, **_kwargs):
        raise urllib.error.URLError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(sc.urllib.request, "urlopen", _boom)
    status, html, final_url = sc._fetch("https://nonexistent.example.test/")
    assert status == 0
    assert html == ""
    assert "getaddrinfo failed" in final_url


def test_fetch_still_reports_http_errors_via_the_existing_path(monkeypatch):
    # Regression guard: the new except clause must not swallow HTTPError
    # (a URLError subclass) into the generic branch — status/url must still
    # come from the HTTPError itself.
    import io

    def _boom(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://x.test/", 404, "Not Found", {}, io.BytesIO(b""))

    monkeypatch.setattr(sc.urllib.request, "urlopen", _boom)
    status, html, final_url = sc._fetch("https://x.test/")
    assert status == 404
    assert html == ""
    assert final_url == "https://x.test/"
