"""crawl.json shape and status classification — spec §4 and §6."""

from __future__ import annotations

import copy

import pytest

from crawler import SCHEMA_CRAWL
from crawler.config import TEMPLATES
from crawler.crawl import _blank_template, _overall_status, _template_status
from crawler.distill import distill
from crawler.fingerprint import empty as empty_fingerprint
from crawler.schema import validate_crawl
from tests.rawtree import build

ORIGIN = "https://shop.test"


def _captured(url: str = f"{ORIGIN}/x") -> dict:
    raw, dropped = build("<html><body><main><h1>Hi there everyone</h1></main></body></html>")
    return {
        "url": url,
        "status": "captured",
        "http_status": 200,
        "distilled": distill(raw),
        "dropped": dropped,
    }


def _complete_crawl() -> dict:
    return {
        "schema": SCHEMA_CRAWL,
        "origin": ORIGIN,
        "status": "complete",
        "gate": "none",
        "fingerprint": {"platform": "shopify", "evidence": ["cdn.shopify.com asset URLs"], "theme": None, "apps": []},
        "templates": {t: _captured() for t in TEMPLATES},
    }


def _blocked_crawl() -> dict:
    return {
        "schema": SCHEMA_CRAWL,
        "origin": ORIGIN,
        "status": "blocked",
        "gate": "blocked",
        "block": {
            "kind": "password_page",
            "evidence": "302 → /password; form[action='/password']",
            "final_url": f"{ORIGIN}/password",
        },
        "fingerprint": empty_fingerprint(),
        "templates": {t: _blank_template(status="blocked") for t in TEMPLATES},
    }


# --- template status classification -----------------------------------------

@pytest.mark.parametrize(
    "template,http_status,final_url,expected",
    [
        ("pdp", 200, f"{ORIGIN}/products/x", "captured"),
        ("cart", 404, f"{ORIGIN}/cart", "absent"),
        ("collection", 410, f"{ORIGIN}/collections/x", "absent"),
        ("search", 500, f"{ORIGIN}/search", "error"),
        ("home", None, f"{ORIGIN}/", "error"),
        ("cart", 200, "https://checkout.test/cart", "absent"),
        # Whatever the store serves for an unknown path *is* the 404 template.
        # A 200 here is a soft-404 and interpreting it is the triager's job.
        ("404", 404, f"{ORIGIN}/abc", "captured"),
        ("404", 200, f"{ORIGIN}/abc", "captured"),
        # A 5xx on the 404 probe is the platform's error page, not the store's
        # 404 template — observed live as Shopify's throttle interstitial.
        ("404", 503, f"{ORIGIN}/abc", "error"),
        ("404", None, f"{ORIGIN}/abc", "error"),
    ],
)
def test_template_status_classification(template, http_status, final_url, expected):
    assert _template_status(template, http_status, final_url, ORIGIN) == expected


# --- overall status ---------------------------------------------------------

def test_zero_captured_templates_is_blocked():
    assert _overall_status({t: _blank_template(status="blocked") for t in TEMPLATES}) == "blocked"


def test_captured_plus_errored_is_partial():
    templates = {t: _captured() for t in TEMPLATES}
    templates["search"] = _blank_template(status="error")
    assert _overall_status(templates) == "partial"


def test_absent_and_robots_blocked_templates_do_not_make_a_run_partial():
    """A template that legitimately does not exist is not a failure."""
    templates = {t: _captured() for t in TEMPLATES}
    templates["collection"] = _blank_template(status="blocked_by_robots")
    templates["cart"] = _blank_template(status="absent")
    assert _overall_status(templates) == "complete"


# --- shape conformance ------------------------------------------------------

def test_a_complete_crawl_conforms():
    assert validate_crawl(_complete_crawl()) == []


def test_a_blocked_crawl_still_yields_a_valid_complete_fixture():
    """Spec §6: a blocked store still yields a valid, complete fixture."""
    crawl = _blocked_crawl()
    assert validate_crawl(crawl) == []
    assert set(crawl["templates"]) == set(TEMPLATES)
    assert all(e["status"] == "blocked" for e in crawl["templates"].values())


def test_every_template_entry_carries_all_five_keys_even_when_absent():
    """Absence must be distinguishable from omission."""
    entry = _blank_template(status="absent")
    assert set(entry) == {"url", "status", "http_status", "distilled", "dropped"}


def test_a_blocked_crawl_reporting_a_platform_is_rejected():
    """MNC-003: the password page is recognisably Shopify; the store was not
    observed, so the fingerprint says unknown."""
    crawl = _blocked_crawl()
    crawl["fingerprint"] = {
        "platform": "shopify",
        "evidence": ["cdn.shopify.com asset URLs"],
        "theme": None,
        "apps": [],
    }
    problems = validate_crawl(crawl)
    assert any("unknown" in p for p in problems)


def test_a_blocked_crawl_without_a_block_object_is_rejected():
    crawl = _blocked_crawl()
    del crawl["block"]
    assert any("block object" in p for p in validate_crawl(crawl))


@pytest.mark.parametrize("kind", ["password_page", "bot_challenge", "http_error", "dns"])
def test_every_block_kind_in_the_spec_is_accepted(kind):
    crawl = _blocked_crawl()
    crawl["block"]["kind"] = kind
    assert validate_crawl(crawl) == []


def test_an_invented_block_kind_is_rejected():
    crawl = _blocked_crawl()
    crawl["block"]["kind"] = "vibes"
    assert any("block.kind" in p for p in validate_crawl(crawl))


def test_a_missing_template_key_is_rejected():
    crawl = _complete_crawl()
    del crawl["templates"]["search"]
    assert any("missing" in p for p in validate_crawl(crawl))


def test_a_captured_template_without_a_distilled_tree_is_rejected():
    crawl = _complete_crawl()
    crawl["templates"]["pdp"]["distilled"] = None
    assert any("no distilled tree" in p for p in validate_crawl(crawl))


def test_dropped_must_carry_exactly_the_four_counters():
    crawl = _complete_crawl()
    crawl["templates"]["pdp"]["dropped"] = {"script_bodies": 1}
    assert any("dropped" in p for p in validate_crawl(crawl))


def test_partial_requires_both_a_capture_and_an_error():
    crawl = _complete_crawl()
    crawl["status"] = "partial"
    assert any("partial" in p for p in validate_crawl(crawl))


def test_a_repeat_marker_is_a_valid_node():
    crawl = _complete_crawl()
    sample = copy.deepcopy(crawl["templates"]["home"]["distilled"])
    crawl["templates"]["home"]["distilled"]["children"] = [{"repeat": {"count": 47, "sample": sample}}]
    assert validate_crawl(crawl) == []
