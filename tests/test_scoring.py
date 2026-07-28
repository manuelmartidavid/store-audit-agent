"""triage/scoring.py — rubric §4 arithmetic, extracted so exactly one spelling exists.

The point of this file is that the extraction changed nothing. Two of these tests
pin numbers recorded in evals/results/. If one fails, the extraction moved
behaviour — STOP and report. Do not edit the number.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("scoring", ROOT / "triage" / "scoring.py")
scoring = importlib.util.module_from_spec(_spec)
sys.modules["scoring"] = scoring
_spec.loader.exec_module(scoring)


def finding(**kw):
    base = {"id": "F-01", "title": "t", "category": "performance", "templates": ["home"],
            "severity": "high", "effort": "small", "confidence": "high",
            "evidence": ["lighthouse:audits/largest-contentful-paint"],
            "instances": {"home": 1}, "severity_rationale": "rubric §1"}
    base.update(kw)
    return base


def test_composite_is_100_minus_penalties():
    out = scoring.composite([finding(severity="critical"), finding(severity="low")])
    assert out["penalties"] == 16
    assert out["score"] == 84
    assert out["band"] == "Minor drag"


def test_blocked_store_has_no_score():
    """Rubric §4 rule 3 / decision 29. Never 0 — zero renders as 'Critical'."""
    out = scoring.composite([], blocked=True)
    assert out["score"] is None
    assert out["status"] == "INACCESSIBLE"
    assert out["band"] == "Inaccessible"


def test_roadmap_puts_the_best_ratio_first():
    """severity_weight ÷ effort_cost: critical/trivial (15) beats high/small (3)."""
    order = scoring.roadmap([
        finding(id="F-01", severity="high", effort="small"),
        finding(id="F-02", severity="critical", effort="trivial"),
    ])
    assert order[0] == "F-02"


def test_recorded_entry_02_run_still_scores_14():
    """Characterisation. runs/v1.0-cli-run1.json is recorded at composite 14 in
    evals/results/07-finding-triager.md. If this fails, the extraction changed
    behaviour — STOP and report rather than editing the expected value."""
    run = json.loads((ROOT / "runs" / "v1.0-cli-run1.json").read_text(encoding="utf-8"))
    out = scoring.composite(run["output"]["findings"])
    assert out["score"] == 14
    assert out["status"] == "ASSESSED"


def test_recorded_entry_02_run_still_ranks_the_same_roadmap_order():
    """Characterisation for roadmap(), the other half of the claim
    docs/superpowers/specs/2026-07-29-impact-narrator-design.md makes about this
    extraction ("a test asserting composite() and roadmap() return identically
    for recorded runs") — only composite() was actually pinned until this test.
    roadmap() is the function `triage/build_brief.py` depends on for production
    ordering, so it is the one whose silent drift would matter most. Pinned
    against the same recorded run as the composite test above; if this fails,
    the extraction moved behaviour — STOP and report rather than editing the
    expected order."""
    run = json.loads((ROOT / "runs" / "v1.0-cli-run1.json").read_text(encoding="utf-8"))
    order = scoring.roadmap(run["output"]["findings"])
    assert order == ["F-02", "F-01", "F-07", "F-04", "F-09", "F-14", "F-03",
                     "F-05", "F-08", "F-16", "F-17", "F-18", "F-19", "F-10",
                     "F-11", "F-12", "F-13", "F-15", "F-06", "F-20"]
