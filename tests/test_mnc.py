"""triage/mnc.py — MNC screens driven by the label file, not by entry-specific code.

The bug this shape exists to prevent: entry 05's first run reported
`zero_mnc_violations: True` having evaluated nothing, because the screens were
hardcoded to entry 02's rules. A screen that passes by not running is the worst
way to be wrong.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("mnc", ROOT / "triage" / "mnc.py")
mnc = importlib.util.module_from_spec(_spec)
sys.modules["mnc"] = mnc
_spec.loader.exec_module(mnc)


def call(labels, findings):
    return mnc.declared_violations(
        labels, blob=json.dumps(findings, ensure_ascii=False), findings=findings)


def test_forbidden_finding_scope_all_fires_on_any_emission():
    """Entry 05's MNC-001 — a blocked store's correct output is an empty array."""
    labels = {"MNC-001": {"type": "forbidden_finding", "scope": ["all"]}}
    assert call(labels, [{"id": "F-01"}])
    assert call(labels, []) == []


def test_detect_patterns_match_the_serialised_output():
    """Entry 05's MNC-003 — being right by inference is still not observation."""
    labels = {"MNC-003": {"detect": {"patterns": [r"\b(Shopify|WooCommerce)\b"]}}}
    hits = call(labels, [{"id": "F-01", "title": "Shopify storefront is gated"}])
    assert [h["rule"] for h in hits] == ["MNC-003"]


def test_an_invalid_regex_is_skipped_not_raised():
    """A malformed pattern in a label must not take the whole scorer down."""
    labels = {"MNC-9": {"detect": {"patterns": ["[unclosed"]}}}
    assert call(labels, [{"id": "F-01", "title": "x"}]) == []


def test_match_any_of_fires_on_a_forbidden_pointer():
    # "crawl:404/heading" (not bare "crawl:404") — crawler spec §9 requires a
    # template AND at least one semantic-path segment; ptr.matches() returns
    # False whenever either side has zero path segments, by design. This also
    # exercises suffix matching (spec §9: "matches on suffix when the anchor
    # differs"), the realistic case for a hand-written forbidden pointer.
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404/heading"]}}}
    hits = call(labels, [{"id": "F-01", "evidence": ["crawl:404/main/heading"]}])
    assert [h["rule"] for h in hits] == ["MNC-404"]


def test_findings_without_evidence_contribute_nothing_to_the_pointer_screen():
    """The narrator's 'findings' carry prose, not pointers. The pointer screen must
    simply not fire there rather than crash — that is what lets one evaluator serve
    both layers."""
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404"]}}}
    assert call(labels, [{"id": "F-01", "consequence": "a shopper cannot check out"}]) == []


def test_mc_labels_are_ignored():
    labels = {"MC-101": {"type": "forbidden_finding", "scope": ["all"]}}
    assert call(labels, [{"id": "F-01"}]) == []
