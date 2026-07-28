"""Evaluate must-not-claim labels using the detection rules the label declares.

Extracted from triage/eval_triage.py so the narrator's scorer reads the same
labels the triager's does. The generalisation is one parameter: `blob` is
whatever text the screens should match, so the same rules run against a triage
findings array and against a narrative object.

The bug this shape exists to prevent is recorded in
evals/results/05-blocked-path.md: the screens were hardcoded to entry 02's rules,
so entry 05 reported `zero_mnc_violations: True` having evaluated nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import pointers as ptr  # noqa: E402


def declared_violations(labels: dict[str, dict[str, Any]], *, blob: str,
                        findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every MNC label that says, in the label, how to detect it.

    Three machine-readable shapes appear across the golden set:

      type: forbidden_finding · scope: [all]   → any emission at all violates
      detect.patterns: [regex, …]              → matched against `blob`
      match.any_of: [pointer, …]               → violated by citing one

    Labels whose detection is a human judgment produce no verdict rather than a
    silent pass. A finding with no `evidence` key contributes nothing to the
    pointer screen — that is what lets one evaluator serve both the triage layer
    (findings carry pointers) and the narrative layer (they carry prose).
    """
    out: list[dict[str, Any]] = []
    for label_id, label in labels.items():
        if not label_id.startswith("MNC-"):
            continue
        scope = [str(x).lower() for x in (label.get("scope") or [])]

        if label.get("type") == "forbidden_finding" and "all" in scope and findings:
            out.append({"rule": label_id, "finding": "*",
                        "why": f"{len(findings)} finding(s) emitted where the label "
                               f"forbids any"})

        for pattern in ((label.get("detect") or {}).get("patterns") or []):
            try:
                hit = re.search(pattern, blob, re.I)
            except re.error:
                continue
            if hit:
                out.append({"rule": label_id, "finding": "*",
                            "why": f"output matches forbidden pattern {pattern!r} "
                                   f"→ {hit.group(0)!r}"})

        forbidden = [p for p in ((label.get("match") or {}).get("any_of") or [])
                     if isinstance(p, str) and not p.endswith("*")]
        if forbidden:
            for f in findings:
                cited = [p for p in (f.get("evidence") or [])
                         if any(ptr.matches(p, q) for q in forbidden)]
                if cited:
                    out.append({"rule": label_id, "finding": f.get("id"),
                                "why": f"cites forbidden evidence {cited}"})
    return out
