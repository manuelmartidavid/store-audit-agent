"""Rubric §4 arithmetic — the composite, the bands, and roadmap order.

Extracted from triage/eval_triage.py so that exactly one spelling of these rules
exists. Decision 28's third argument, applied one layer out: the harness scores
against this and triage/build_brief.py builds the production roadmap from it. A
second implementation would not raise — it would silently rank differently, and
the report would be wrong with no error anywhere.

Nothing here judges. It arithmetic-s the enums a model already chose.
"""

from __future__ import annotations

from typing import Any

SEVERITY_WEIGHT = {"critical": 15, "high": 6, "medium": 2, "low": 1}
SEVERITY_ORDER = ["low", "medium", "high", "critical"]
EFFORT_COST = {"trivial": 1, "small": 2, "medium": 5, "large": 10}
EFFORT_ORDER = ["trivial", "small", "medium", "large"]
SCORED_CATEGORIES = ("performance", "seo", "accessibility", "conversion")
CATEGORY_CAP = 25
CATEGORY_TIEBREAK = {"performance": 0, "conversion": 1, "seo": 2, "accessibility": 3}
BANDS = [(85, "Healthy"), (65, "Minor drag"), (45, "Material friction"),
         (25, "Significant work needed"), (0, "Critical")]

#: Rubric §4 rule 3 (v0.4). Emitted for every store, not only blocked ones — a
#: field that appears only on failure is a field a renderer forgets to handle.
STATUS_ASSESSED = "ASSESSED"
STATUS_INACCESSIBLE = "INACCESSIBLE"
BAND_INACCESSIBLE = "Inaccessible"

MAX_PER_TEMPLATE = 8
MAX_TOTAL = 25


def band_for(score: int | None) -> str:
    if score is None:
        return BAND_INACCESSIBLE
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "Critical"


def status_for(score: int | None) -> str:
    """`INACCESSIBLE` when there is no score, `ASSESSED` when there is.

    Derived from the score rather than passed in, so the two can never disagree:
    a status saying ASSESSED beside a null score would be worse than either
    field alone.
    """
    return STATUS_INACCESSIBLE if score is None else STATUS_ASSESSED


def composite(findings: list[dict[str, Any]], blocked: bool = False) -> dict[str, Any]:
    """Rubric §4, computed by script from the model's enums. Never read back.

    A store that could not be assessed has **no score** (rubric §4 rule 3,
    decision 7). Not zero: zero renders as "Critical" on the band table, which is
    a judgment about a store nobody saw — fabrication by arithmetic. The failure
    mode is a number rather than a sentence, which is exactly why it survives a
    read-through of the narrative and has to be caught here.
    """
    if blocked:
        return {"score": None, "status": STATUS_INACCESSIBLE, "band": band_for(None),
                "per_category": None, "per_category_capped": None, "penalties": None,
                "caps_binding": [],
                "note": "crawl was blocked — no score, per rubric §4 rule 3"}
    per_category = {c: 0 for c in SCORED_CATEGORIES}
    for f in findings:
        category = f.get("category")
        if category not in per_category:
            continue                                  # security is not scored
        if f.get("confidence") == "low":
            continue                                  # rule 1: weight 0
        per_category[category] += SEVERITY_WEIGHT.get(f.get("severity"), 0)
    capped = {c: min(v, CATEGORY_CAP) for c, v in per_category.items()}
    total = sum(capped.values())
    score = max(0, 100 - total)
    return {
        "score": score,
        "status": status_for(score),
        "band": band_for(score),
        "per_category": per_category,
        "per_category_capped": capped,
        "penalties": total,
        "caps_binding": [c for c in SCORED_CATEGORIES if per_category[c] > CATEGORY_CAP],
    }


def roadmap(findings: list[dict[str, Any]]) -> list[str]:
    """Rubric §4: severity_weight ÷ effort_cost, ties by category then id."""
    scored = [f for f in findings
              if f.get("severity") in SEVERITY_WEIGHT and f.get("confidence") != "low"]

    def key(f: dict[str, Any]):
        weight = SEVERITY_WEIGHT[f["severity"]]
        cost = EFFORT_COST.get(f.get("effort"), EFFORT_COST["medium"])
        return (-(weight / cost), CATEGORY_TIEBREAK.get(f.get("category"), 9), str(f.get("id")))

    return [str(f.get("id")) for f in sorted(scored, key=key)]
