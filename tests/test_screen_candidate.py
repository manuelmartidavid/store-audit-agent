"""The candidate screen's pure layer — no network, no browser.

Entries 01 and 04 are stores we do not own, so the criteria that selected them
have to be re-runnable before capture (design 2026-07-29 D5). These pin the
parsing and the verdicts; the network and browser paths are exercised by
running the tool, the same split tests/test_measure.py uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planting"))

import screen_candidate as sc  # noqa: E402


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


def test_parse_head_detects_a_storefront_password_form():
    html = '<head></head><body><form action="/password"><input type="password" name="p"></form></body>'
    assert sc.parse_head(html, 200).password_form is True


def test_parse_head_does_not_flag_an_ordinary_page_as_gated():
    assert sc.parse_head(HEAD, 200).password_form is False


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
