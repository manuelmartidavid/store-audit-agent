"""Turns findings into a score, a band, and a roadmap order (rubric §4).

Pure arithmetic over the severity and effort values the model already picked.

Invariant: this is the only place these rules live. A second copy wouldn't
error — it would just rank differently and quietly produce a wrong report.
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

#: Emitted for every store, not just blocked ones — a field that only shows up on
#: failure is one a renderer forgets to handle.
STATUS_ASSESSED = "ASSESSED"
STATUS_INACCESSIBLE = "INACCESSIBLE"
BAND_INACCESSIBLE = "Inaccessible"

MAX_PER_TEMPLATE = 8
MAX_TOTAL = 25


def band_for(score: int | None) -> str:
    """The band name a score falls in."""
    if score is None:
        return BAND_INACCESSIBLE
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "Critical"


def status_for(score: int | None) -> str:
    """`INACCESSIBLE` when there is no score, `ASSESSED` when there is.

    Derived from the score so the two can never disagree.
    """
    return STATUS_INACCESSIBLE if score is None else STATUS_ASSESSED


def composite(findings: list[dict[str, Any]], blocked: bool = False) -> dict[str, Any]:
    """Work out the composite score and its breakdown (rubric §4).

    Invariant: a store that couldn't be assessed gets no score, never zero.
    Zero renders as "Critical", which is a judgement about a store nobody saw.
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
            continue                                  # security isn't scored
        if f.get("confidence") == "low":
            continue                                  # low confidence counts for 0
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
    """Order finding ids by severity ÷ effort, breaking ties by category then id."""
    scored = [f for f in findings
              if f.get("severity") in SEVERITY_WEIGHT and f.get("confidence") != "low"]

    def key(f: dict[str, Any]):
        weight = SEVERITY_WEIGHT[f["severity"]]
        cost = EFFORT_COST.get(f.get("effort"), EFFORT_COST["medium"])
        return (-(weight / cost), CATEGORY_TIEBREAK.get(f.get("category"), 9), str(f.get("id")))

    return [str(f.get("id")) for f in sorted(scored, key=key)]
