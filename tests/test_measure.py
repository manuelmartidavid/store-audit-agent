"""Pure helpers in planting/measure.py — browser-free and deterministic.

measure.py is a planting aid, not part of the shipped crawler, but its
threshold-side classification and LHR parsing decide when the aim loop stops, so
the deterministic parts are worth pinning — in the same spirit as
``lighthouse.assemble``. The browser-driving path is exercised by hand against
the live store (it is the only thing that can reach it); these cover the rest.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# planting/ is not a package; put it on the path the way measure.py expects.
# (Was `scripts/` until decision 28 split that grab-bag by concern.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planting"))

import measure  # noqa: E402


# --- _parse_band ------------------------------------------------------------

def test_parse_band_both_ends():
    assert measure._parse_band("3000..3800") == (3000.0, 3800.0)


def test_parse_band_open_upper_and_lower():
    assert measure._parse_band("5000..") == (5000.0, None)
    assert measure._parse_band("..3800") == (None, 3800.0)


@pytest.mark.parametrize("spec", ["3000", "abc..def", "..", "3800..3000"])
def test_parse_band_rejects_malformed(spec):
    with pytest.raises(Exception):  # argparse.ArgumentTypeError
        measure._parse_band(spec)


# --- _is_gate_url -----------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://shop.test/password",
    "https://shop.test/password/",
    "http://shop.test/password?foo=1",
])
def test_gate_urls_are_detected(url):
    assert measure._is_gate_url(url) is True


@pytest.mark.parametrize("url", [
    "https://shop.test/",
    "https://shop.test/products/a-card",
    "https://shop.test/collections/passwords",  # substring, not the gate path
    "",
])
def test_non_gate_urls_are_not(url):
    assert measure._is_gate_url(url) is False


# --- _side (rubric v0.2: boundary values take the LOWER level) --------------

def test_lcp_sides():
    assert measure._side(None, "lcp") == "no value"
    assert measure._side(4500, "lcp").startswith("HIGH")
    assert measure._side(4000, "lcp").startswith("MEDIUM"), "== 4.0s is medium, not high"
    assert measure._side(3000, "lcp").startswith("MEDIUM")
    assert measure._side(2500, "lcp").startswith("below"), "== 2.5s is below medium"


def test_cls_sides():
    assert measure._side(0.30, "cls").startswith("HIGH")
    assert measure._side(0.25, "cls").startswith("at/below"), "== 0.25 is not > 0.25"
    assert measure._side(0.05, "cls").startswith("at/below")


# --- _lcp_selector (handles both LHR detail shapes) -------------------------

def _audits(details):
    return {"largest-contentful-paint-element": {"details": details}}


def test_lcp_selector_newer_nested_shape():
    audits = _audits({"items": [{"items": [{"node": {"selector": ".hero-img"}}]}]})
    assert measure._lcp_selector(audits) == ".hero-img"


def test_lcp_selector_older_flat_shape():
    audits = _audits({"items": [{"node": {"selector": "img.product__media"}}]})
    assert measure._lcp_selector(audits) == "img.product__media"


def test_lcp_selector_falls_back_to_snippet():
    audits = _audits({"items": [{"node": {"snippet": "<img src=hero.png>"}}]})
    assert measure._lcp_selector(audits) == "<img src=hero.png>"


def test_lcp_selector_absent_returns_none():
    assert measure._lcp_selector({}) is None
    assert measure._lcp_selector(_audits({})) is None
