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

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("mnc", ROOT / "triage" / "mnc.py")
mnc = importlib.util.module_from_spec(_spec)
sys.modules["mnc"] = mnc
_spec.loader.exec_module(mnc)

_et_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_et_spec)
sys.modules["eval_triage"] = eval_triage
_et_spec.loader.exec_module(eval_triage)

ENTRY_02_LABELS = ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md"


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


def test_an_invalid_regex_is_a_hard_error_naming_the_label_and_pattern():
    """V3: `mnc_screens_run` must never name a screen that evaluated nothing.
    `declared_violations` used to catch `re.error` and `continue`, while
    `executable_label_ids` counts any non-empty `patterns` list as a screen
    that ran — so a label with an uncompilable pattern was reported having
    matched nothing, when it never actually ran at all. Same treatment a
    grammar-invalid `crawl:` pointer already gets, for the same reason."""
    labels = {"MNC-9": {"detect": {"patterns": ["[unclosed"]}}}
    try:
        call(labels, [{"id": "F-01", "title": "x"}])
    except ValueError as e:
        assert "MNC-9" in str(e)
        assert "[unclosed" in str(e)
    else:
        raise AssertionError("expected ValueError for an uncompilable pattern")


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
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404/main/heading"]}}}
    assert call(labels, [{"id": "F-01", "consequence": "a shopper cannot check out"}]) == []


def test_mc_labels_are_ignored():
    labels = {"MC-101": {"type": "forbidden_finding", "scope": ["all"]}}
    assert call(labels, [{"id": "F-01"}]) == []


def test_a_bare_crawl_pointer_with_no_path_segment_raises():
    """crawl:404 has no semantic-path segment (spec §9) — ptr.matches() always
    returns False for it, so as `forbidden` it would silently never fire. That is
    exactly the zero_mnc_violations failure mode this module exists to prevent, so
    the label must be rejected loudly instead of shipped as a screen that always
    passes."""
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404"]}}}
    try:
        call(labels, [{"id": "F-01", "evidence": ["crawl:404/main/heading"]}])
    except ValueError as e:
        assert "MNC-404" in str(e)
        assert "crawl:404" in str(e)
    else:
        raise AssertionError("expected ValueError for a dead crawl: pointer")


def test_a_crawl_pointer_with_a_path_segment_does_not_raise():
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404/main/heading"]}}}
    hits = call(labels, [{"id": "F-01", "evidence": ["crawl:404/main/heading"]}])
    assert [h["rule"] for h in hits] == ["MNC-404"]


def test_a_wildcard_axe_pointer_is_still_skipped_not_raised():
    labels = {"MNC-004": {"match": {"any_of": ["axe:*"]}}}
    assert call(labels, [{"id": "F-01", "evidence": ["axe:color-contrast"]}]) == []


# --- MNC-405, against the real entry-02 label file --------------------------
#
# Every test above drives a synthetic label. These drive the patterns actually
# shipped in evals/golden/02-sabotaged, because that is where the risk lives:
# they are hand-written regexes, added 2026-07-31 when finding-triager v1.2
# restored the price/stock presence checks and made the claim reachable for the
# first time. A regex that quietly stops matching is precisely the "screen that
# passes by not running" this whole file exists to catch, and MNC-405 has never
# fired on a real run — so nothing else would notice if it broke.
#
# Both directions are asserted. Firing alone is not enough: patterns loose
# enough to catch every phrasing would also fire on findings that merely mention
# price, turning a correct observation into an automatic fail.

CLAIMS_PRICE_IS_MISSING = [
    "The PDP does not display a price for the product.",
    "No price is shown on the product detail page.",
    "Price is missing from the collection grid.",
    "Product cards render without a visible price.",
]

MENTIONS_PRICE_LEGITIMATELY = [
    # A missing price FILTER is a real finding about a control, not a claim that
    # prices are absent — the distinction the patterns have to hold.
    "The collection page has no price filter, so shoppers cannot narrow by budget.",
    "Price, low to high sorting is available on the collection.",
    "The price is displayed as $10.00 with no currency code alongside it.",
    "Add-to-cart is a div and is not keyboard operable.",
    "The cart shows no shipping cost before checkout.",
]

# Stock is NOT screened, and this is the test that keeps it that way.
#
# MNC-405 first covered stock and availability alongside price, on the
# assumption the distiller fix made both visible. Checking the bytes disproved
# it: the main PDP product block carries a price and an add-to-cart control and
# no availability text at all, every "Sold out" on that template belongs to a
# related product, and availability survives only as schema.org/InStock inside a
# head JSON-LD script. A run calling that "no stock status shown" is reading the
# rendered page correctly, so screening it would fail a correct run.
#
# The first v1.3 run emitted exactly this claim and MNC-405 stayed silent only
# because the phrasing missed a regex. These cases turn that luck into a rule.
CLAIMS_ABOUT_STOCK_ARE_DEFENSIBLE_HERE = [
    "The PDP gives no stock status, so buyers cannot tell availability.",
    "Availability state is not shown anywhere on the PDP.",
    "Product page states no stock or availability.",
    "The product page does not show stock level.",
]


def _mnc_405_hits(text: str) -> list:
    labels = eval_triage.parse_labels(ENTRY_02_LABELS)
    return [h for h in mnc.declared_violations(labels, blob=text, findings=[])
            if h["rule"] == "MNC-405"]


def test_mnc_405_is_a_screen_that_can_run():
    labels = eval_triage.parse_labels(ENTRY_02_LABELS)
    assert "MNC-405" in labels, "MNC-405 vanished from the entry-02 label file"
    assert "MNC-405" in mnc.executable_label_ids(labels), (
        "MNC-405 parses but carries no runnable screen — it would report "
        "'no violations' having checked nothing")


@pytest.mark.parametrize("text", CLAIMS_PRICE_IS_MISSING)
def test_mnc_405_fires_on_a_claim_the_fixture_contradicts(text: str):
    assert _mnc_405_hits(text), f"MNC-405 did not fire on: {text!r}"


@pytest.mark.parametrize("text", MENTIONS_PRICE_LEGITIMATELY)
def test_mnc_405_stays_quiet_when_price_is_merely_mentioned(text: str):
    assert not _mnc_405_hits(text), f"MNC-405 false-fired on: {text!r}"


@pytest.mark.parametrize("text", CLAIMS_ABOUT_STOCK_ARE_DEFENSIBLE_HERE)
def test_mnc_405_never_screens_a_claim_about_stock(text: str):
    assert not _mnc_405_hits(text), (
        f"MNC-405 fired on a stock claim: {text!r}. The pdp carries no visible "
        f"availability indicator, so this reading is defensible and screening it "
        f"would fail a correct run.")


# --- entry 01's screens, against the real label file -------------------------
#
# Entry 01 is the false-positive test, so its MNC rules ARE the entry. MNC-201
# in particular is the one that matters: axe reports 74 serious wcag2aa contrast
# violations on that store and every one is an artifact of Dawn's scroll-reveal
# animation (all 74 at ratio 1.01, #fdfdfd on #ffffff). If that screen ever
# stops firing, the entry silently stops testing the thing it exists for.

ENTRY_01_LABELS = ROOT / "evals" / "golden" / "01-clean-theme" / "expected" / "findings.md"


def _entry_01_hits(rule: str, findings: list, blob: str | None = None) -> list:
    labels = eval_triage.parse_labels(ENTRY_01_LABELS)
    text = blob if blob is not None else json.dumps(findings, ensure_ascii=False)
    return [h for h in mnc.declared_violations(labels, blob=text, findings=findings)
            if h["rule"] == rule]


def test_entry_01_screens_are_all_executable():
    labels = eval_triage.parse_labels(ENTRY_01_LABELS)
    declared = {k for k in labels if k.startswith("MNC-")}
    assert declared == {"MNC-201", "MNC-202"}
    assert declared <= mnc.executable_label_ids(labels), (
        "an entry-01 MNC parses but carries no runnable screen")


@pytest.mark.parametrize("pointer", ["axe:color-contrast",
                                     "lighthouse:audits/color-contrast"])
def test_mnc_201_catches_a_contrast_finding_from_either_scanner(pointer: str):
    hits = _entry_01_hits("MNC-201", [{"id": "F-01", "title": "Low contrast text",
                                       "evidence": [pointer]}])
    assert hits, f"MNC-201 did not fire on a finding citing {pointer!r}"


@pytest.mark.parametrize("pointer", ["lighthouse:audits/meta-description",
                                     "axe:heading-order",
                                     "crawl:home/html/head/title[theme-dawn-demo]"])
def test_mnc_201_leaves_the_real_findings_alone(pointer: str):
    # The three must-catch labels cite these. A contrast screen that also fired
    # on them would fail every correct run.
    assert not _entry_01_hits("MNC-201", [{"id": "F-02", "title": "x",
                                           "evidence": [pointer]}])


@pytest.mark.parametrize("text", [
    "This is a demonstration store, not a real business.",
    "The catalog is placeholder content.",
    "Product pages use a test store catalog.",
])
def test_mnc_202_catches_the_store_is_not_real_claim(text: str):
    assert _entry_01_hits("MNC-202", [], blob=text), f"MNC-202 missed: {text!r}"


@pytest.mark.parametrize("text", [
    "The home page title is the bare store handle.",
    "The demo of the cart flow completed without error.",
    "Four templates lack a meta description.",
])
def test_mnc_202_stays_quiet_on_ordinary_audit_prose(text: str):
    assert not _entry_01_hits("MNC-202", [], blob=text), f"MNC-202 false-fired: {text!r}"


# --- executable_label_ids: which screens actually ran -----------------------

def test_executable_label_ids_includes_forbidden_finding_scope_all():
    labels = {"MNC-001": {"type": "forbidden_finding", "scope": ["all"]}}
    assert mnc.executable_label_ids(labels) == {"MNC-001"}


def test_executable_label_ids_includes_detect_patterns():
    labels = {"MNC-003": {"scope": ["narrative"], "detect": {"patterns": [r"\bfoo\b"]}}}
    assert mnc.executable_label_ids(labels) == {"MNC-003"}


def test_executable_label_ids_includes_match_any_of_with_a_real_path_segment():
    labels = {"MNC-404": {"match": {"any_of": ["crawl:404/heading"]}}}
    assert mnc.executable_label_ids(labels) == {"MNC-404"}


def test_executable_label_ids_excludes_a_prose_only_detect_rule():
    """MNC-402/403's original shape: `detect: {rule: <prose>}` names no pattern
    and no pointer — it is human-readable, not machine-executable, and must not
    be counted as a screen that ran."""
    labels = {"MNC-402": {"scope": ["narrative"],
                          "detect": {"rule": "any_finding_or_score_traceable_to_input"}}}
    assert mnc.executable_label_ids(labels) == set()


def test_executable_label_ids_excludes_a_wildcard_only_match_any_of():
    labels = {"MNC-004": {"match": {"any_of": ["axe:*"]}}}
    assert mnc.executable_label_ids(labels) == set()


def test_executable_label_ids_ignores_mc_labels():
    labels = {"MC-101": {"type": "forbidden_finding", "scope": ["all"]}}
    assert mnc.executable_label_ids(labels) == set()


# --- is_discharged: documented, not silently missing -------------------------

def test_is_discharged_true_when_the_label_carries_a_discharged_block():
    label = {"discharged": {"by": "numeral_ban", "note": "no digit can appear"}}
    assert mnc.is_discharged(label) is True


def test_is_discharged_false_by_default():
    assert mnc.is_discharged({"detect": {"rule": "prose"}}) is False


def test_is_discharged_false_when_by_or_note_is_missing():
    """`discharged: true` (or a block missing `by`/`note`) must not silence a
    must-not-claim screen with no reasoning recorded — the same accountability
    gap as never discharging it, just quieter about it."""
    assert mnc.is_discharged({"discharged": True}) is False
    assert mnc.is_discharged({"discharged": {}}) is False
    assert mnc.is_discharged({"discharged": {"by": "numeral_ban"}}) is False
    assert mnc.is_discharged({"discharged": {"note": "why"}}) is False
    assert mnc.is_discharged({"discharged": {"by": "", "note": ""}}) is False


def test_discharge_incomplete_distinguishes_malformed_from_absent():
    assert mnc.discharge_incomplete({"discharged": True}) is True
    assert mnc.discharge_incomplete({"discharged": {"by": "x"}}) is True
    assert mnc.discharge_incomplete({"detect": {"rule": "prose"}}) is False
    assert mnc.discharge_incomplete(
        {"discharged": {"by": "x", "note": "y"}}) is False
