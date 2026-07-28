"""Gate an impact-narrator run. Contract: specs/narrator-io.md §4.

There is no ground-truth prose to match against, so this file scores only what is
mechanically checkable and is explicit about what it cannot reach. Three tiers:

  * hard gates      — schema, word caps, coverage, the numeral ban, the blocked
                      path, and the MNC screens the label file declares
  * advisory        — spelled-out quantities and template containment. Both are
                      partial; both report and neither fails
  * the human read  — whether a consequence is true, whether a change is a
                      correct remediation, and decision 3's editing-cost test

A separate file from eval_triage.py on purpose: the triage harness pin derives
from that file's bytes, and a narrative change must not move a triage pin.

Usage:
    python triage/eval_narrative.py runs/narrator-v0.1-run1.json \
        --brief briefs/02-sabotaged.brief.json \
        --entry evals/golden/02-sabotaged --prompt-version impact-narrator/v0.1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import eval_triage, mnc  # noqa: E402

HARNESS_VERSION = "narrative-eval/v0.1"
SCHEMA = "narrative/v0.1"

FIELDS = ("consequence", "affects", "change")
CAPS = {"summary": 80, "consequence": 25, "affects": 15, "change": 20}

_DIGIT_RE = re.compile(r"\d")

#: Partial by construction (narrator-io §4.1). Banning digits does not ban a
#: quantity spelled out in words, and no word list closes that hole — it narrows
#: it. Reported, never failed; the human read covers the rest.
QUANTITY_WORDS = ("percent", "per cent", "a third", "a quarter", "a half",
                  "twice as", "three times", "double the", "half of", "most of")

#: Entry 05's required behaviour #1 — the report must name the gate.
_GATE_WORDS = ("gate", "password", "unreachable", "could not be reached",
               "not reachable", "blocked")


def brief_ids(brief: dict[str, Any]) -> set[str]:
    """Every id the narrative must cover — all three buckets, not just the roadmap."""
    return {str(f.get("id")) for bucket in ("roadmap", "needs_verification", "noted")
            for f in (brief.get(bucket) or [])}


def _values(narrative: dict[str, Any]) -> list[tuple[str, str]]:
    out = [("summary", str(narrative.get("summary") or ""))]
    for fid, body in (narrative.get("findings") or {}).items():
        for field in FIELDS:
            out.append((f"{fid}.{field}", str((body or {}).get(field) or "")))
    return out


def validate(narrative: dict[str, Any], brief: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if narrative.get("schema") != SCHEMA:
        errors.append(f"schema is {narrative.get('schema')!r}, expected {SCHEMA!r}")

    summary = str(narrative.get("summary") or "").strip()
    if not summary:
        errors.append("summary is empty; it is required on every run")

    findings = narrative.get("findings")
    if not isinstance(findings, dict):
        errors.append("findings must be an object keyed by finding id")
        return errors

    blocked = brief.get("store_status") == "INACCESSIBLE"
    if blocked:
        if findings:
            errors.append(f"store_status is INACCESSIBLE but {len(findings)} finding(s) "
                          f"were narrated; the correct output is an empty object")
        if summary and not any(w in summary.lower() for w in _GATE_WORDS):
            errors.append("blocked-store summary does not name the gate; entry 05 "
                          "required behaviour #1 is a client-deliverable report, "
                          "not a blank one")
        return errors

    expected = brief_ids(brief)
    got = {str(k) for k in findings}
    for missing in sorted(expected - got):
        errors.append(f"{missing} is in the brief but was not narrated")
    for extra in sorted(got - expected):
        errors.append(f"{extra} was narrated but is not in the brief")

    for fid, body in findings.items():
        if not isinstance(body, dict):
            errors.append(f"{fid} is not an object")
            continue
        for field in FIELDS:
            value = str(body.get(field) or "").strip()
            if not value:
                errors.append(f"{fid}.{field} is missing or empty")

    for name, value in _values(narrative):
        field = name.split(".")[-1]
        cap = CAPS[field]
        words = len(value.split())
        if words > cap:
            errors.append(f"{name} is {words} words, cap is {cap}")

    return errors


def numeral_violations(narrative: dict[str, Any]) -> list[str]:
    """Rubric §6 rule 1, closed structurally.

    Only field *values* are scanned — `F-01` is a key, and keys are the join to
    the brief, not prose. A number is permitted only with a citation to
    references/benchmarks.md, and that file does not exist, so in v0.1 no number
    is permitted at all.
    """
    out = []
    for name, value in _values(narrative):
        hit = _DIGIT_RE.search(value)
        if hit:
            out.append(f"{name} contains a digit ({value[max(0, hit.start() - 20):hit.end() + 20]!r})")
    return out


def quantity_word_notes(narrative: dict[str, Any]) -> list[str]:
    """Advisory. See QUANTITY_WORDS — this narrows the hole, it does not close it."""
    out = []
    for name, value in _values(narrative):
        for word in QUANTITY_WORDS:
            if word in value.lower():
                out.append(f"{name} contains the quantity phrase {word!r} — read it")
    return out


def template_containment_notes(narrative: dict[str, Any],
                               brief: dict[str, Any]) -> list[str]:
    """Advisory, and it has to be.

    'cannot add this product to the cart' is correct English about a PDP defect,
    and a naive containment check fails it. Reported so a human can tell that case
    from a defect genuinely claimed on a page it was not found on.
    """
    templates_by_id = {str(f.get("id")): set(f.get("templates") or [])
                       for bucket in ("roadmap", "needs_verification", "noted")
                       for f in (brief.get(bucket) or [])}
    vocabulary = set().union(*templates_by_id.values()) if templates_by_id else set()
    out = []
    for fid, body in (narrative.get("findings") or {}).items():
        own = templates_by_id.get(str(fid), set())
        text = " ".join(str((body or {}).get(f) or "") for f in FIELDS).lower()
        for template in sorted(vocabulary - own):
            if re.search(rf"\b{re.escape(template)}\b", text):
                out.append(f"{fid} mentions {template!r}, which is not in its "
                           f"templates {sorted(own)} — read it")
    return out


def evaluate(narrative: dict[str, Any], brief: dict[str, Any],
             labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    errors = validate(narrative, brief)
    numerals = numeral_violations(narrative)

    narrated = [{"id": fid, **(body or {})}
                for fid, body in (narrative.get("findings") or {}).items()]
    violations = mnc.declared_violations(
        labels, blob=json.dumps(narrative, ensure_ascii=False), findings=narrated)

    advisory = quantity_word_notes(narrative) + template_containment_notes(narrative, brief)

    return {
        "harness_version": HARNESS_VERSION,
        "errors": errors,
        "numerals": numerals,
        "mnc_violations": violations,
        "advisory": advisory,
        "passed": not errors and not numerals and not violations,
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", type=Path, help="a narrator run JSON")
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--entry", type=Path, required=True,
                        help="evals/golden/<entry> — its labels supply the MNC screens")
    parser.add_argument("--prompt-version", required=True,
                        help="no default, deliberately — an unpinned run is not a result")
    args = parser.parse_args(argv)

    run = json.loads(args.run.read_text(encoding="utf-8"))
    narrative = run.get("output", run)
    brief = json.loads(args.brief.read_text(encoding="utf-8"))
    labels = eval_triage.parse_labels(args.entry / "expected" / "findings.md")

    result = evaluate(narrative, brief, labels)
    result["provenance"] = {
        "prompt_version": args.prompt_version,
        "brief_sha256": (run.get("run_meta") or {}).get("brief_sha256"),
        "rubric_version": eval_triage.rubric_version(),
        "narrative_harness": HARNESS_VERSION,
        "model": (run.get("run_meta") or {}).get("model"),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
