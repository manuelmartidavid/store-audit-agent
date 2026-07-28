"""Precision bars — the ones the harness never had.

Recall has six bars; precision has none. `unlabeled` findings are counted and
gate nothing, so a run emitting 24 findings of which 7 are plausible-but-wrong
passes everything. The project's stated top risk is a plausible-but-wrong claim
reaching a client.

The gates are declared per entry (`expect.gates`) rather than inferred, because
turning them on for entry 02 retroactively would re-judge 18 recorded runs on a
bar they were never measured against — a decision for a person, not for a
default.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)


def _findings(count: int, severity: str = "low") -> list[dict]:
    return [{"id": f"F-{n:02d}", "severity": severity, "category": "seo",
             "confidence": "high", "templates": ["home"]} for n in range(count)]


def test_no_gates_declared_means_no_precision_bars():
    bars = eval_triage.expect_bars(_findings(40), {"score": 10}, {"max_findings": 3})
    assert bars == {}


def test_max_findings_gate():
    expect = {"gates": ["max_findings"], "max_findings": 3}
    assert eval_triage.expect_bars(_findings(3), {"score": 95}, expect)["max_findings_respected"]
    assert not eval_triage.expect_bars(_findings(4), {"score": 95}, expect)["max_findings_respected"]


def test_findings_above_medium_gate():
    expect = {"gates": ["findings_above_medium"], "findings_above_medium": 0}
    clean = eval_triage.expect_bars(_findings(3, "medium"), {"score": 95}, expect)
    assert clean["findings_above_medium_respected"]
    noisy = eval_triage.expect_bars(_findings(1, "high"), {"score": 95}, expect)
    assert not noisy["findings_above_medium_respected"]


def test_score_range_gate_including_the_blocked_store():
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": 100}
    assert eval_triage.expect_bars([], {"score": 95}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 60}, expect)["score_within_expect"]

    blocked = {"gates": ["score_range"], "score_min": None, "score_max": None}
    assert eval_triage.expect_bars([], {"score": None}, blocked)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 0}, blocked)["score_within_expect"]


def test_entry_02_declares_no_gates_and_says_why():
    text = (ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["eval"]["expect"]["gates"] == []
    assert "18 recorded runs" in text


def test_entry_05_gates_max_findings():
    data = yaml.safe_load(
        (ROOT / "evals" / "golden" / "05-password-gated" / "context.yaml").read_text(encoding="utf-8"))
    assert "max_findings" in data["eval"]["expect"]["gates"]


# ---------------------------------------------------------------------------
# Finding 1 — a one-sided score range must not raise, on either side
# ---------------------------------------------------------------------------

def test_score_range_lower_bound_only():
    # score_max present and explicitly null: "no ceiling", not "unset". Entry
    # 01's own pass condition is exactly this shape (rubric §5: score >= 90).
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": None}
    assert eval_triage.expect_bars([], {"score": 90}, expect)["score_within_expect"]
    assert eval_triage.expect_bars([], {"score": 100}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 89}, expect)["score_within_expect"]


def test_score_range_upper_bound_only():
    # score_min present and explicitly null: "no floor", not "unset".
    expect = {"gates": ["score_range"], "score_min": None, "score_max": 90}
    assert eval_triage.expect_bars([], {"score": 90}, expect)["score_within_expect"]
    assert eval_triage.expect_bars([], {"score": 0}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 91}, expect)["score_within_expect"]


# ---------------------------------------------------------------------------
# Finding 2 — a declared gate with no value, or no known name, must not pass
# silently
# ---------------------------------------------------------------------------

def test_declared_gate_with_missing_value_raises():
    expect = {"gates": ["max_findings"]}  # max_findings never set
    with pytest.raises(SystemExit, match="max_findings"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)


def test_declared_findings_above_medium_with_missing_value_raises():
    expect = {"gates": ["findings_above_medium"]}
    with pytest.raises(SystemExit, match="findings_above_medium"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)


def test_declared_score_range_with_missing_bounds_raises():
    # gates declares score_range but never sets score_min/score_max at all —
    # distinct from entry 05's blocked-store case, which sets both to null
    # explicitly.
    expect = {"gates": ["score_range"]}
    with pytest.raises(SystemExit, match="score_range"):
        eval_triage.expect_bars([], {"score": 95}, expect)


def test_unknown_gate_name_raises():
    expect = {"gates": ["max_findigns"], "max_findigns": 3}  # typo'd gate name
    with pytest.raises(SystemExit, match="not a known gate"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)
