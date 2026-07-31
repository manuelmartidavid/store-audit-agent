"""The candidate screen's pure layer — no network, no browser.

Entries 01 and 04 are stores we do not own, so the criteria that selected them
have to be re-runnable before capture (design 2026-07-29 D5). These pin the
parsing and the verdicts; the network and browser paths are exercised by
running the tool, the same split tests/test_measure.py uses.
"""

from __future__ import annotations

import socket
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


# --- platform_gate -----------------------------------------------------------
#
# `crawler.fingerprint.build` was wrongly claimed (final review wave 1) to need
# a live Session — real HTTP headers, browser cookies, `page.evaluate` output —
# to run at all. Verified false by execution: `Signals` defaults every field to
# empty, and the Shopify/WooCommerce marker blocks `build` actually uses read
# only `signals.urls`, `signals.meta["generator"]` and `signals.body_classes`,
# all three derivable from raw HTML. These pin `platform_gate`, which builds
# exactly that reduced `Signals` from a home-page HTML string.

SHOPIFY_HOME_HTML = """<!doctype html><html><head></head><body>
<script src="https://cdn.shopify.com/s/files/1/0001/theme.js"></script>
<link rel="stylesheet" href="/cdn/shop/t/1/assets/base.css">
</body></html>"""

WOO_HOME_HTML = """<!doctype html><html>
<head><meta name="generator" content="WooCommerce 8.1"></head>
<body class="woocommerce woocommerce-page">
<script src="/wp-content/plugins/woocommerce/assets/js/frontend/woocommerce.min.js"></script>
</body></html>"""

NO_MARKERS_HOME_HTML = "<!doctype html><html><head></head><body></body></html>"


def test_platform_gate_passes_when_declared_shopify_matches_shopify_shaped_html():
    gate = sc.platform_gate(SHOPIFY_HOME_HTML, "shopify")
    assert gate.passed is True
    assert gate.name == "platform"


def test_platform_gate_passes_when_declared_woocommerce_matches_woo_shaped_html():
    gate = sc.platform_gate(WOO_HOME_HTML, "woocommerce")
    assert gate.passed is True


def test_platform_gate_fails_and_names_both_platforms_on_a_mismatch():
    # declared shopify, but the HTML is unambiguously WooCommerce-shaped.
    gate = sc.platform_gate(WOO_HOME_HTML, "shopify")
    assert gate.passed is False
    assert "shopify" in gate.detail.lower()
    assert "woocommerce" in gate.detail.lower()


def test_platform_gate_fails_with_a_distinct_detail_when_detection_is_inconclusive():
    # No platform markers anywhere -> crawler.fingerprint.build returns
    # "unknown". Treated as FAIL (a screen that shrugs is a vacuous pass), but
    # with wording that says detection failed, not that it found a mismatch.
    gate = sc.platform_gate(NO_MARKERS_HOME_HTML, "shopify")
    assert gate.passed is False
    assert "inconclusive" in gate.detail.lower()


def test_platform_gate_evidence_list_is_present_in_the_detail():
    gate = sc.platform_gate(SHOPIFY_HOME_HTML, "shopify")
    assert "cdn.shopify.com" in gate.detail.lower()


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


def test_permalink_gate_refuses_a_nested_category_path():
    # `_WOO_COLLECTION` matches exactly ONE category segment
    # (`/product-category/{slug}`), not a nested one
    # (`/product-category/{parent}/{child}/`) — the discovery table this gate
    # protects (design D3) only knows the one-segment shape, so a store whose
    # only collection link is nested must fail here, the same way it would
    # fail discovery.
    html = '<a href="/product-category/food/bakery/">Bakery</a>'
    gate = sc.permalink_gate(html, "ex.test", "woocommerce")
    assert gate.passed is False


def test_permalink_gate_reports_home_not_fetched_instead_of_a_permalink_diagnosis():
    # Regression: when home_html is "" (home was robots-disallowed or its
    # fetch failed), the old code fell into the same "no /shop or
    # /product-category/{slug} link on home" branch a real permalink defect
    # takes — describing a problem that was never observed. Must still FAIL
    # (an unassessed gate must not pass), but say what actually happened.
    gate = sc.permalink_gate("", "ex.test", "woocommerce")
    assert gate.passed is False
    assert "not fetched" in gate.detail.lower()
    assert "discovery" not in gate.detail.lower()


def test_permalink_gate_excludes_a_cross_host_link():
    # A link to a different host must not satisfy the gate — `parsed.netloc`
    # is compared against `host`, and a mismatch is skipped rather than
    # treated as a same-site collection URL.
    html = '<a href="https://other.example.com/shop">Shop</a>'
    gate = sc.permalink_gate(html, "ex.test", "woocommerce")
    assert gate.passed is False


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


# --- IPv4 preference: a dead AAAA record must not cost 60s a fetch -----------
#
# Diagnosed 2026-07-30. This machine's router advertises a global IPv6 prefix
# with no upstream transit, so every AAAA connect attempt hangs until timeout.
# `urllib` has no Happy Eyeballs, so it blocks ~60s per fetch before falling
# back to IPv4 — measured 63.88s against entry 04's host, whose IPv4 path
# answers in 0.96s. That artefact is what produced entry 04's retracted
# "LCP 19-23s" figures. Chromium fails over in ~300ms, so `measure.py` is not
# affected and the capture path is not either; only these urllib probes are.


def test_ipv4_addresses_sort_before_ipv6():
    infos = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.26.9.137", 443)),
    ]
    assert [i[0] for i in sc._ipv4_first(infos)] == [socket.AF_INET, socket.AF_INET6]


def test_an_ipv6_only_host_keeps_its_addresses_rather_than_losing_them():
    """Invariant: reorder, never filter. Dropping AF_INET6 would make a genuinely
    IPv6-only host unreachable — trading a host quirk for a capability loss."""
    infos = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))]
    assert sc._ipv4_first(infos) == infos


def test_order_within_a_family_is_preserved():
    """Stable sort: DNS round-robin order carries real load-balancing intent."""
    a = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.26.9.137", 443))
    b = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.26.8.137", 443))
    v6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))
    assert sc._ipv4_first([v6, a, b]) == [a, b, v6]


def test_prefer_ipv4_makes_socket_return_ipv4_first(monkeypatch):
    """The installer is what `main` calls; it must reorder real getaddrinfo output."""
    v6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))
    v4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.26.9.137", 443))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [v6, v4])

    sc.prefer_ipv4()

    assert socket.getaddrinfo("shop.test", 443)[0][0] == socket.AF_INET


def test_prefer_ipv4_is_idempotent(monkeypatch):
    """`main` may run more than once in one process (the test suite does)."""
    v6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))
    v4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.26.9.137", 443))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [v6, v4])

    sc.prefer_ipv4()
    sc.prefer_ipv4()

    assert [i[0] for i in socket.getaddrinfo("shop.test", 443)] == [
        socket.AF_INET,
        socket.AF_INET6,
    ]


def test_main_installs_the_ipv4_preference_before_it_fetches_anything(monkeypatch):
    """Invariant: the preference must be in place before the first probe, not
    after. `main` fetches robots.txt as its very first network act, so a
    preference installed later would leave that fetch paying the full timeout —
    and robots.txt gates every template that follows it."""
    installed_before_first_fetch: list[bool] = []

    def _spy_fetch(url, timeout=30):
        installed_before_first_fetch.append(
            getattr(socket.getaddrinfo, "_prefers_ipv4", False)
        )
        raise SystemExit(99)  # stop main here; the ordering is all we assert

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    monkeypatch.setattr(sc, "_fetch", _spy_fetch)

    with pytest.raises(SystemExit) as exc:
        sc.main(["--entry", "04", "--skip-perf"])

    assert exc.value.code == 99, "the spy should have been reached"
    assert installed_before_first_fetch == [True]


def test_the_report_evidences_the_resolver_preference_instead_of_asserting_it(capsys, monkeypatch):
    """`prefer_ipv4` reorders DNS results process-wide, which is invisible in the
    output of a tool whose figures were retracted once already for a DNS-shaped
    reason. Same reasoning as the `politeness:` note: evidence the conduct.
    """
    monkeypatch.setattr(sc.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(
        sc, "_fetch",
        lambda url, timeout=30: (200, "<head><title>t</title></head>", url),
    )

    sc.main(["--entry", "04", "--skip-perf"])

    notes = capsys.readouterr().out
    assert "resolver: IPv4 tried before IPv6" in notes


# --- soft gates: measured and reported, but not disqualifying ----------------
#
# Entry 04 failed lcp/cls on its 2026-07-31 screen (home LCP 19.2-19.9s, CLS
# 0.43, pdp LCP 20.5-23.5s). Those gates were entry 01's selection criteria --
# the design's perf screen is headed "Demo" and covers entry 01 candidates only.
# Entry 04 was selected on permalinks, robots.txt and ICP match, and exists to
# exercise the reduced path and the null-AOV trap; neither needs a fast store,
# and the brief targets low-traffic SMB stores. Same reasoning the docstring
# already applies to hygiene: screening these out means hunting for a store that
# flatters the agent.


def test_a_gate_is_hard_unless_it_says_otherwise():
    """Default must stay hard, or an unmarked gate silently stops disqualifying."""
    assert sc.Gate("reachable:home", True, "HTTP 200").hard is True


def test_soft_families_downgrade_every_gate_in_that_family():
    gates = [
        sc.Gate("lcp:home", False, "x"),
        sc.Gate("cls:pdp", False, "y"),
        sc.Gate("reachable:home", False, "z"),
    ]
    out = sc.apply_soft_gates(gates, frozenset({"lcp", "cls"}))
    assert [g.hard for g in out] == [False, False, True]


def test_nothing_is_downgraded_when_no_family_is_soft():
    """Entry 01's path: the perf bar it was selected against must not move."""
    gates = [sc.Gate("lcp:home", False, "x")]
    assert sc.apply_soft_gates(gates, frozenset())[0].hard is True


def test_soft_gates_are_named_by_family_not_by_full_gate_name():
    """`lcp` must cover lcp:home, lcp:collection and lcp:pdp without listing them."""
    gates = [sc.Gate(f"lcp:{t}", False, "x") for t in ("home", "collection", "pdp")]
    assert all(g.hard is False for g in sc.apply_soft_gates(gates, frozenset({"lcp"})))


def test_entry_04_records_perf_while_entry_01_still_gates_on_it():
    assert sc.ENTRIES["04"]["soft_gates"] == frozenset({"lcp", "cls"})
    assert sc.ENTRIES["01"].get("soft_gates", frozenset()) == frozenset()


# Stub documents that pass every HEAD gate for their platform, so a non-zero exit
# in the tests below can only come from lcp/cls. Without this the entry-04 test
# would "pass" on `platform` and `permalinks` failing instead — green for a reason
# that has nothing to do with soft gates.
_WOO_DOC = (
    '<head><title>Forest Whole Foods</title>'
    '<meta name="description" content="Organic wholefoods"></head>'
    '<body class="woocommerce">'
    '<script src="/wp-content/plugins/woocommerce/assets/js/frontend.js"></script>'
    '<a href="/product-category/bakery/">Bakery</a></body>'
)
_SHOPIFY_DOC = (
    '<head><title>Dawn demo</title>'
    '<meta name="description" content="A demo store"></head>'
    '<body><script src="https://cdn.shopify.com/s/files/1/assets/theme.js"></script>'
    '</body>'
)


def _stub_perf(monkeypatch, lcp_ms, cls_val, doc):
    """Drive main()'s perf loop without a browser."""
    class _Run:
        blocked = None
        samples = [_StubSample(lcp_ms, cls_val)]

    monkeypatch.setattr(sc.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(sc, "_fetch", lambda url, timeout=30: (200, doc, url))
    monkeypatch.setattr(sc.measure, "sample_url", lambda *a, **k: _Run())


def test_the_stubs_clear_every_hard_gate_on_their_own(monkeypatch, capsys):
    """Guards the two tests below: if the stub ever stops satisfying the head
    gates, they would go green on the wrong failure instead of on soft gates."""
    _stub_perf(monkeypatch, lcp_ms=1000, cls_val=0.0, doc=_WOO_DOC)
    assert sc.main(["--entry", "04"]) == 0
    _stub_perf(monkeypatch, lcp_ms=1000, cls_val=0.0, doc=_SHOPIFY_DOC)
    assert sc.main(["--entry", "01"]) == 0


def test_a_failing_soft_gate_does_not_trigger_re_selection(monkeypatch, capsys):
    """The whole point: entry 04's real numbers must not disqualify it."""
    _stub_perf(monkeypatch, lcp_ms=20000, cls_val=0.43, doc=_WOO_DOC)
    assert sc.main(["--entry", "04"]) == 0


def test_entry_01_is_still_disqualified_by_the_same_numbers(monkeypatch, capsys):
    """The bar entry 01 was selected against has not moved."""
    _stub_perf(monkeypatch, lcp_ms=20000, cls_val=0.43, doc=_SHOPIFY_DOC)
    assert sc.main(["--entry", "01"]) == 2


def test_a_failing_hard_gate_still_disqualifies_entry_04(monkeypatch, capsys):
    """Softening perf must not soften anything else."""
    _stub_perf(monkeypatch, lcp_ms=20000, cls_val=0.43, doc=_WOO_DOC)
    monkeypatch.setattr(sc, "_fetch", lambda url, timeout=30: (500, "", url))
    assert sc.main(["--entry", "04"]) == 2


def test_a_failing_soft_gate_is_reported_rather_than_hidden(monkeypatch, capsys):
    """A number that stops gating must not stop being visible — it becomes a label.

    Asserts on the perf section's own header, not on the substring "NOT a gate",
    which the seo-hygiene header already contains and would satisfy vacuously.
    """
    _stub_perf(monkeypatch, lcp_ms=20000, cls_val=0.43, doc=_WOO_DOC)
    sc.main(["--entry", "04"])
    out = capsys.readouterr().out
    assert "perf (recorded, NOT a gate for entry 04" in out
    assert "20.00" in out, "the measurement itself must still print"
    assert "lcp:home" in out, "and must still be attributed to its template"
