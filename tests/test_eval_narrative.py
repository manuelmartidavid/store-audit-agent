"""triage/eval_narrative.py — the gates, and an honest account of their reach.

There is no ground-truth prose to match against, so this scorer checks only what
is mechanically checkable. Two of its checks are partial and one is advisory; the
tests below pin that they behave as advertised rather than pretending to more.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "eval_narrative", ROOT / "triage" / "eval_narrative.py")
eval_narrative = importlib.util.module_from_spec(_spec)
sys.modules["eval_narrative"] = eval_narrative
_spec.loader.exec_module(eval_narrative)


def brief(status="ASSESSED", roadmap=(("F-01", ["pdp"]),), needs=(), noted=()):
    def f(fid, templates):
        return {"id": fid, "title": "t", "category": "accessibility",
                "templates": list(templates), "severity": "critical",
                "effort": "small", "confidence": "high",
                "evidence": ["crawl:pdp/x"], "instances": {"pdp": 1},
                "severity_rationale": "§1"}
    return {"schema": "brief/v0.1", "store_status": status, "store": {},
            "roadmap": [f(i, t) for i, t in roadmap],
            "needs_verification": [f(i, t) for i, t in needs],
            "noted": [f(i, t) for i, t in noted],
            "overflow_count": 0, "provenance": {}}


def narrative(findings=None, summary="This store is reachable and shoppable."):
    if findings is None:
        findings = {"F-01": {"consequence": "A shopper cannot add the product to the cart.",
                             "affects": "Every visitor not using a mouse.",
                             "change": "Rebuild the control as a real button."}}
    return {"schema": "narrative/v0.1", "summary": summary, "findings": findings}


# --- the structural gates ---------------------------------------------------

def test_a_clean_narrative_passes():
    result = eval_narrative.evaluate(narrative(), brief(), {})
    assert result["errors"] == []
    assert result["passed"] is True


def test_a_missing_finding_is_a_coverage_failure():
    """Exact-set equality, not a subset. A silently dropped finding is a defect
    that vanishes between triage and the client."""
    b = brief(roadmap=(("F-01", ["pdp"]), ("F-02", ["cart"])))
    errors = eval_narrative.validate(narrative(), b)
    assert any("F-02" in e for e in errors)


def test_an_invented_finding_id_is_a_coverage_failure():
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b", "change": "c"},
                            "F-99": {"consequence": "a", "affects": "b", "change": "c"}}),
        brief())
    assert any("F-99" in e for e in errors)


def test_needs_verification_and_noted_must_also_be_narrated():
    b = brief(roadmap=(), needs=(("F-02", ["pdp"]),), noted=(("F-03", ["pdp"]),))
    ids = eval_narrative.brief_ids(b)
    assert ids == {"F-02", "F-03"}


def test_a_missing_field_fails():
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b"}}), brief())
    assert any("change" in e for e in errors)


def test_an_empty_field_fails():
    """A finding the narrator has nothing to say about is a signal, not a blank."""
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b", "change": "   "}}),
        brief())
    assert any("change" in e for e in errors)


def test_word_caps_are_enforced():
    long_change = " ".join(["word"] * 21)
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b",
                                     "change": long_change}}), brief())
    assert any("change" in e and "20" in e for e in errors)


# --- the numeral ban --------------------------------------------------------

def test_any_digit_anywhere_is_a_violation():
    """Automatic-fail #1 unreachable by construction: rubric §6.1 permits a number
    only with a benchmark citation, and references/benchmarks.md does not exist."""
    hits = eval_narrative.numeral_violations(
        narrative(findings={"F-01": {"consequence": "This costs 30% of sessions.",
                                     "affects": "b", "change": "c"}}))
    assert hits


def test_the_summary_is_scanned_too():
    assert eval_narrative.numeral_violations(narrative(summary="4 problems found."))


def test_a_number_free_narrative_is_clean():
    assert eval_narrative.numeral_violations(narrative()) == []


def test_finding_ids_are_keys_not_values_and_do_not_trip_the_scan():
    """F-01 contains digits. Only field values are scanned."""
    assert eval_narrative.numeral_violations(narrative()) == []


# --- the two partial checks -------------------------------------------------

def test_spelled_out_quantities_are_reported_not_failed():
    """Banning digits does not ban 'roughly a third of shoppers'. The screen is a
    pattern list, incomplete by construction, so it advises rather than gates."""
    n = narrative(findings={"F-01": {"consequence": "Roughly a third of shoppers leave.",
                                     "affects": "b", "change": "c"}})
    assert eval_narrative.quantity_word_notes(n)
    assert eval_narrative.evaluate(n, brief(), {})["passed"] is True


def test_template_containment_is_advisory_and_tolerates_add_to_cart():
    """'cannot add this product to the cart' on a PDP finding is correct English and
    a naive containment check fails it. Advisory, never a gate."""
    n = narrative(findings={"F-01": {"consequence": "A shopper cannot add it to the cart.",
                                     "affects": "b", "change": "c"}})
    result = eval_narrative.evaluate(n, brief(roadmap=(("F-01", ["pdp"]),)), {})
    assert result["passed"] is True


# --- the blocked path -------------------------------------------------------

def test_a_blocked_store_must_narrate_nothing():
    errors = eval_narrative.validate(narrative(), brief(status="INACCESSIBLE", roadmap=()))
    assert any("INACCESSIBLE" in e or "blocked" in e for e in errors)


def test_a_blocked_summary_must_name_the_gate():
    """Entry 05 required behaviour #1: a blocked audit still produces a
    client-deliverable report, and the report has to say what happened."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1", "summary": "Nothing to report.", "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert any("gate" in e.lower() for e in errors)


def test_a_correct_blocked_narrative_passes():
    n = {"schema": "narrative/v0.1", "findings": {},
         "summary": "This store could not be assessed. It sits behind a storefront "
                    "password gate, so no page was reachable and no audit was possible."}
    result = eval_narrative.evaluate(n, brief(status="INACCESSIBLE", roadmap=()), {})
    assert result["errors"] == [] and result["passed"] is True


# --- MNC screens ------------------------------------------------------------

def test_mnc_patterns_run_against_the_narrative():
    """Entry 05's MNC-003 scopes `narrative`, and until now nothing read it."""
    labels = {"MNC-003": {"detect": {"patterns": [r"\b(Shopify|WooCommerce)\b"]}}}
    n = {"schema": "narrative/v0.1", "findings": {},
        "summary": "This Shopify store sits behind a password gate and was not assessed."}
    result = eval_narrative.evaluate(n, brief(status="INACCESSIBLE", roadmap=()), labels)
    assert result["mnc_violations"]
    assert result["passed"] is False
