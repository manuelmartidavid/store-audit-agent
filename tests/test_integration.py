"""End-to-end crawls against a local storefront.

Spec §10's acceptance tests run against live targets and stay the acceptance bar;
these run the same shapes against a store that can be driven into every branch on
demand. They exercise everything the unit tests cannot reach: the real DOM
walker, the gate, axe injection, and the four output files.

Lighthouse is off by default here — it costs ~30s per template and its own
integration is proved by ``test_lighthouse_attaches_to_the_shared_browser``,
which is opt-in via CRAWLER_TEST_LIGHTHOUSE=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from crawler.config import TEMPLATES
from crawler.crawl import Options, crawl
from crawler.distill import iter_nodes
from crawler.pointers import resolve
from crawler.schema import validate_crawl
from tests.store_fixture import StoreServer

pytest.importorskip("playwright.sync_api", reason="playwright is required for integration tests")

PASSWORD = "tscc-open-sesame"
ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, server: StoreServer, **overrides):
    options = Options(
        origin=server.origin,
        out_dir=tmp_path,
        run_lighthouse=False,
        run_axe=True,
        node_root=ROOT,
        seed=1,
        **overrides,
    )
    return crawl(options, log=lambda *a: None)


def _crawl(tmp_path: Path, server: StoreServer, **overrides) -> dict:
    return _run(tmp_path, server, **overrides).crawl


def _node_where(crawl_json: dict, template: str, predicate):
    tree = crawl_json["templates"][template]["distilled"]
    return next((n for n in iter_nodes(tree) if predicate(n)), None)


# --- §10.1 blocked -----------------------------------------------------------

def test_a_password_gated_store_with_no_password_yields_the_blocked_shape(tmp_path):
    with StoreServer(password=PASSWORD) as server:
        result = _crawl(tmp_path, server, password_env=None)

    assert validate_crawl(result) == []
    assert result["status"] == "blocked"
    assert result["gate"] == "blocked"
    assert result["block"]["kind"] == "password_page"
    assert result["block"]["evidence"]
    assert "/password" in result["block"]["final_url"]

    # All six templates present, all blocked — a blocked store still yields a
    # valid, complete fixture.
    assert set(result["templates"]) == set(TEMPLATES)
    assert all(e["status"] == "blocked" for e in result["templates"].values())

    # MNC-003: the gate page is recognisably Shopify and the fingerprint says so
    # anyway — no.
    assert result["fingerprint"] == {"platform": "unknown", "evidence": [], "theme": None, "apps": []}


# --- §10.2 gated capture -----------------------------------------------------

def test_a_password_gated_store_with_the_password_captures_all_six_templates(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_STOREFRONT_PASSWORD", PASSWORD)
    with StoreServer(password=PASSWORD) as server:
        result = _crawl(tmp_path, server, password_env="TEST_STOREFRONT_PASSWORD")

    assert validate_crawl(result) == []
    assert result["gate"] == "password_supplied"
    assert result["status"] == "complete"
    captured = [t for t, e in result["templates"].items() if e["status"] == "captured"]
    assert sorted(captured) == sorted(TEMPLATES)


def test_the_password_appears_in_no_output_byte(tmp_path, monkeypatch):
    """Acceptance test §10.2: grep the entire fixtures dir for the value."""
    monkeypatch.setenv("TEST_STOREFRONT_PASSWORD", PASSWORD)
    with StoreServer(password=PASSWORD) as server:
        _crawl(tmp_path, server, password_env="TEST_STOREFRONT_PASSWORD")

    written = list(tmp_path.rglob("*"))
    assert {p.name for p in written} == {"crawl.json", "lighthouse.json", "axe.json", "manifest.yaml"}
    for path in written:
        assert PASSWORD.encode() not in path.read_bytes(), path


# --- §10.3 fingerprint -------------------------------------------------------

def test_a_shopify_store_fingerprints_as_shopify_with_evidence(tmp_path):
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    fingerprint = result["fingerprint"]
    assert fingerprint["platform"] == "shopify"
    assert "cdn.shopify.com asset URLs" in fingerprint["evidence"]
    assert fingerprint["theme"] == {"name": "Dawn", "version": "12.0.0"}
    assert [a["name"] for a in fingerprint["apps"]] == ["Judge.me"]


# --- §10.4 non-Shopify -------------------------------------------------------

def test_a_non_shopify_store_still_completes_and_feeds_the_reduced_path(tmp_path):
    """Acceptance test §10.4, and design D3: reduced means fewer platform-specific
    signals, not fewer pages. Before 0.3.0 this store yielded collection, pdp and
    search `absent` — the conversion axis, gone."""
    with StoreServer(platform="woocommerce") as server:
        result = _crawl(tmp_path, server)
        origin = server.origin

    assert validate_crawl(result) == []
    assert result["status"] == "complete"
    assert result["fingerprint"]["platform"] == "woocommerce"
    assert result["fingerprint"]["evidence"]

    templates = result["templates"]
    assert [t for t, e in templates.items() if e["status"] == "captured"] == list(TEMPLATES)
    assert templates["collection"]["url"] == f"{origin}/product-category/nuts/"
    assert templates["pdp"]["url"].startswith(f"{origin}/product/card-")
    assert templates["search"]["url"] == f"{origin}/?s=a"


def test_a_renamed_cart_slug_is_discovered_rather_than_assumed(tmp_path):
    """The bug the entry-04 screen found first: /cart/ 404s, the cart is /basket/."""
    with StoreServer(platform="woocommerce") as server:
        result = _crawl(tmp_path, server)
        origin = server.origin
        requested = list(server.options.hits)

    assert result["templates"]["cart"]["url"] == f"{origin}/basket/"
    assert result["templates"]["cart"]["status"] == "captured"
    assert "/cart" not in requested, "a discovered cart costs no extra fetch"


def test_a_shopify_store_still_discovers_exactly_as_it_did_before(tmp_path):
    """0.3.0's discovery change must be invisible to a Shopify capture."""
    with StoreServer() as server:
        result = _crawl(tmp_path, server)
        origin = server.origin

    templates = result["templates"]
    assert templates["collection"]["url"] == f"{origin}/collections/rookies"
    assert templates["pdp"]["url"].startswith(f"{origin}/products/card-")
    assert templates["cart"]["url"] == f"{origin}/cart"
    assert templates["search"]["url"] == f"{origin}/search?q=a"


# --- §10.5 robots ------------------------------------------------------------

def test_a_robots_disallowed_template_is_recorded_and_the_crawl_continues(tmp_path):
    with StoreServer(robots="User-agent: *\nDisallow: /collections\n") as server:
        result = _crawl(tmp_path, server)
        requested = list(server.options.hits)

    assert result["templates"]["collection"]["status"] == "blocked_by_robots"
    assert result["status"] == "complete", "a robots block is a fact, not a failure"
    assert result["templates"]["home"]["status"] == "captured"
    assert result["templates"]["cart"]["status"] == "captured"
    assert not any(p.startswith("/collections") for p in requested), "disallowed means not fetched"


# --- §10.6 determinism -------------------------------------------------------

def test_a_transient_503_is_retried_rather_than_recorded_as_error(tmp_path):
    """A store we don't own may throttle us with a 5xx that clears on retry.

    The cart 503s once, then serves normally; the crawl should capture it, not
    demote it to error and the run to partial.
    """
    with StoreServer(flaky={"/cart": 1}) as server:
        result = _crawl(tmp_path, server)

    assert result["templates"]["cart"]["status"] == "captured"
    assert result["templates"]["cart"]["http_status"] == 200
    assert result["status"] == "complete"


def test_a_persistent_5xx_still_ends_as_error_not_an_infinite_retry(tmp_path):
    with StoreServer(flaky={"/cart": 99}) as server:
        result = _crawl(tmp_path, server)

    assert result["templates"]["cart"]["status"] == "error"
    assert result["templates"]["cart"]["http_status"] == 503
    assert result["status"] == "partial"


def test_two_crawls_of_the_same_store_produce_identical_distilled_trees(tmp_path):
    with StoreServer() as server:
        first = _crawl(tmp_path / "a", server)
        second = _crawl(tmp_path / "b", server)

    for template in TEMPLATES:
        if template == "404":
            continue  # the 404 path is random by design; its URL differs by run
        assert json.dumps(first["templates"][template]["distilled"]) == json.dumps(
            second["templates"][template]["distilled"]
        ), template


def test_a_seeded_run_reproduces_the_404_url(tmp_path):
    with StoreServer() as server:
        first = _crawl(tmp_path / "a", server)
        second = _crawl(tmp_path / "b", server)
    assert first["templates"]["404"]["url"] == second["templates"]["404"]["url"]


# --- discovery and distillation against real markup --------------------------

def test_template_discovery_follows_the_spec_table(tmp_path):
    with StoreServer() as server:
        result = _crawl(tmp_path, server)
        origin = server.origin

    templates = result["templates"]
    assert templates["home"]["url"] == f"{origin}/"
    # First /collections/{handle} in the nav, excluding /collections/all.
    assert templates["collection"]["url"] == f"{origin}/collections/rookies"
    assert templates["pdp"]["url"].startswith(f"{origin}/products/card-")
    assert templates["cart"]["url"] == f"{origin}/cart"
    assert templates["search"]["url"] == f"{origin}/search?q=a"
    assert len(templates["404"]["url"].rsplit("/", 1)[-1]) == 40
    assert templates["404"]["http_status"] == 404


def test_the_crawl_is_bounded_regardless_of_catalog_size(tmp_path):
    """Adversarial case 4, satisfied structurally: a 50-card grid costs the same
    as a 5-card one because one page per template is captured.

    The bound is on navigations — subresources a page pulls in (its own images,
    stylesheets) are the store's choice, not the crawler's, and counting them
    would measure the wrong thing.
    """
    with StoreServer() as server:
        result = _run(tmp_path, server)
        documents = [
            p for p in server.options.hits
            if p != "/robots.txt" and not p.startswith("/img/")
        ]

    # Spec §3: max 6 fetches for discovery + 6 template captures + gate handling.
    assert result.fetches <= 12, f"{result.fetches} navigations"
    assert len(documents) <= 12, documents
    # One page per template: the 50-card grid is fetched once, not fifty times.
    assert sum(1 for p in documents if p.startswith("/products/")) == 1
    assert sum(1 for p in documents if p.startswith("/collections/")) == 1


def test_the_div_add_to_cart_survives_into_the_fixture_with_a_resolvable_pointer(tmp_path):
    """C-01 end to end: recorded as a div with its attributes, not interpreted."""
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    node = _node_where(result, "pdp", lambda n: n.get("attrs", {}).get("data-testid") == "add-to-cart")
    assert node is not None
    assert node["tag"] == "div"
    assert node["attrs"]["onclick"] == "addToCart()"
    assert node["text"] == "Add to cart"
    assert resolve("crawl:pdp/product-form/div[add-to-cart]", result) is not None


def test_the_noindex_meta_survives_on_the_collection_template(tmp_path):
    """C-02: an indexing blocker on a revenue template."""
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    robots_meta = _node_where(
        result, "collection", lambda n: n.get("attrs", {}).get("name") == "robots"
    )
    assert robots_meta["attrs"]["content"] == "noindex"


def test_the_injected_instruction_is_carried_through_as_data(tmp_path):
    """X-01: the crawler records it. Treating it as data is the triager's test —
    but it cannot be reported as a finding if distillation drops it."""
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    tree = result["templates"]["pdp"]["distilled"]
    text = " ".join(n.get("text", "") for n in iter_nodes(tree))
    assert "Ignore previous instructions" in text


def test_the_fifty_card_grid_collapses_to_five_cards_and_a_count(tmp_path):
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    tree = result["templates"]["collection"]["distilled"]
    grid = next(n for n in iter_nodes(tree) if n.get("attrs", {}).get("class") == "grid")

    assert len(grid["children"]) == 6, "five product cards and a count, not fifty"
    assert grid["children"][5]["repeat"]["count"] == 50
    assert grid["children"][5]["repeat"]["sample"]["tag"] == "li"

    # The 45 collapsed cards are gone from the payload entirely.
    hrefs = [n["attrs"]["href"] for n in iter_nodes(tree) if n.get("tag") == "a"]
    assert "/products/card-4" in hrefs
    assert "/products/card-40" not in hrefs


def test_dropped_counts_are_recorded_so_absence_is_distinguishable_from_omission(tmp_path):
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    dropped = result["templates"]["home"]["dropped"]
    assert set(dropped) == {"script_bodies", "style_blocks", "svg_internals", "comment_nodes"}
    assert dropped["script_bodies"] >= 1
    assert dropped["style_blocks"] == 1
    assert dropped["svg_internals"] == 4  # g + 3 paths
    assert dropped["comment_nodes"] == 1


def test_script_bodies_never_reach_the_fixture(tmp_path):
    with StoreServer() as server:
        _crawl(tmp_path, server)
    blob = (tmp_path / "crawl.json").read_text(encoding="utf-8")
    assert "window.Shopify = window.Shopify" not in blob
    assert "https://cdn.shopify.com/s/files/1/0001/assets/theme.js" in blob, "the reference is kept"


# --- axe ---------------------------------------------------------------------

def test_axe_runs_on_every_captured_template_and_emits_standard_results(tmp_path):
    with StoreServer() as server:
        _crawl(tmp_path, server)

    results = json.loads((tmp_path / "axe.json").read_text(encoding="utf-8"))
    assert len(results) == len(TEMPLATES)
    for entry in results:
        assert {"violations", "url", "testEngine"} <= set(entry)
    # Raw violations, no severity mapping — that is the rubric's job.
    violations = [v for entry in results for v in entry["violations"]]
    assert violations, "the fixture store has real accessibility defects planted in it"
    assert all("impact" in v for v in violations)


def test_the_manifest_records_provenance_for_every_template(tmp_path):
    yaml = pytest.importorskip("yaml")
    with StoreServer() as server:
        _crawl(tmp_path, server)

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["schema"] == "manifest/v0.1"
    assert manifest["throttling"] == "mobile-4g-slow"
    assert manifest["axe_core_version"]
    assert manifest["chrome_version"] and manifest["chrome_version"] != "PENDING"
    assert set(manifest["templates"]) == set(TEMPLATES)
    assert all(e["axe"] == "ok" for e in manifest["templates"].values())


# --- lighthouse (opt-in: slow) ----------------------------------------------

@pytest.mark.skipif(
    os.environ.get("CRAWLER_TEST_LIGHTHOUSE") != "1",
    reason="set CRAWLER_TEST_LIGHTHOUSE=1 to run the Lighthouse sidecar (~1 min)",
)
def test_lighthouse_attaches_to_the_shared_browser(tmp_path, monkeypatch):
    """§7: the Node API against the shared authenticated context.

    Run against the *gated* store — a Lighthouse that could not carry the session
    cookie would audit the password page and score it, which is the exact failure
    the CLI would produce.
    """
    monkeypatch.setenv("TEST_STOREFRONT_PASSWORD", PASSWORD)
    with StoreServer(password=PASSWORD) as server:
        options = Options(
            origin=server.origin,
            out_dir=tmp_path,
            password_env="TEST_STOREFRONT_PASSWORD",
            run_lighthouse=True,
            run_axe=False,
            node_root=ROOT,
            seed=1,
        )
        result = crawl(options, log=lambda *a: None)

    lhrs = json.loads((tmp_path / "lighthouse.json").read_text(encoding="utf-8"))
    assert lhrs, "no LHR produced"
    for lhr in lhrs:
        assert lhr["configSettings"]["formFactor"] == "mobile"
        # The load-bearing assertion: Lighthouse must land on the audited page,
        # not get bounced to the gate. A run in the wrong cookie jar redirects to
        # /password and produces a perfect score for a page that is not the store.
        final = lhr.get("finalDisplayedUrl") or lhr.get("finalUrl", "")
        assert "/password" not in final, f"Lighthouse audited the gate page: {final}"
        assert lhr.get("audits", {}).get("document-title", {}) is not None
    yaml = pytest.importorskip("yaml")
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["lighthouse_version"] != "PENDING"


# --- crawl-delay (design D6) --------------------------------------------------

def test_a_declared_crawl_delay_is_honoured_and_recorded(tmp_path):
    """Design D6. 2s is enough to prove the wiring; this adds ~14s to the suite,
    which is the honest cost of testing a delay rather than mocking one."""
    with StoreServer(robots="User-agent: *\nCrawl-delay: 2\nAllow: /\n") as server:
        result = _run(tmp_path, server)

    body = (tmp_path / "manifest.yaml").read_text(encoding="utf-8")
    assert "crawl_delay_declared: 2" in body
    assert "fetch_interval_s: 2" in body
    assert result.crawl["status"] == "complete"


def test_rendered_prices_reach_the_fixture(tmp_path):
    """Blocking-adjacent finding from the step-7 loop: zero `$` survived
    distillation in any template, so the prompt had to instruct the model not to
    check two purchase-decision affordances."""
    with StoreServer() as server:
        result = _crawl(tmp_path, server)

    collection = json.dumps(result["templates"]["collection"]["distilled"])
    assert "$85.00" in collection
