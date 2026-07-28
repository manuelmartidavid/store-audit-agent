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
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import eval_triage, mnc  # noqa: E402
from triage.scoring import STATUS_INACCESSIBLE  # noqa: E402

HARNESS_VERSION = "narrative-eval/v0.1"
HARNESS_PATH = Path(__file__).resolve()
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
#: Word-boundary matched (I2), not a bare substring scan: "gate" is a substring
#: of navigate/investigate/mitigate/delegate, and "Shoppers could not navigate
#: to any page" used to satisfy this screen without naming any gate at all —
#: the only content check on the entire deliverable on the blocked path.
_GATE_WORDS = ("gate", "password", "unreachable", "could not be reached",
               "not reachable", "blocked")
_GATE_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _GATE_WORDS) + r")\b", re.I)


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

    # The word cap applies unconditionally — including on the blocked path, where
    # the summary is the entire deliverable — so it runs before the blocked early
    # return below. Coverage and per-finding checks stay gated on `blocked`: a
    # blocked run has no findings to cover.
    for name, value in _values(narrative):
        field = name.split(".")[-1]
        cap = CAPS[field]
        words = len(value.split())
        if words > cap:
            errors.append(f"{name} is {words} words, cap is {cap}")

    blocked = brief.get("store_status") == STATUS_INACCESSIBLE
    if blocked:
        if findings:
            errors.append(f"store_status is INACCESSIBLE but {len(findings)} finding(s) "
                          f"were narrated; the correct output is an empty object")
        if summary and not _GATE_WORD_RE.search(summary):
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


def _narrative_scope_ids(labels: dict[str, dict[str, Any]]) -> list[str]:
    """MNC label ids whose `scope` includes `narrative` — the ones this layer
    is on the hook for evaluating, as opposed to MNC-401/404 (triage-only)."""
    return sorted(
        label_id for label_id, label in labels.items()
        if label_id.startswith("MNC-")
        and "narrative" in [str(s).lower() for s in (label.get("scope") or [])])


def evaluate(narrative: dict[str, Any], brief: dict[str, Any],
             labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    errors = validate(narrative, brief)
    numerals = numeral_violations(narrative)

    # C1a — the hole entry 02's MNC-402/403 sat in: a label scoped `narrative`
    # whose detection is prose (`detect.rule`, not `detect.patterns`) produced
    # no verdict from `mnc.declared_violations` and nothing said so.
    # `zero_mnc_violations: True` then read as "checked, clean" when it was
    # "never checked" — evals/results/05-blocked-path.md's failure mode, one
    # layer up. A label documented as `discharged:` is exempt on the record;
    # anything else with no executable screen is a hard error naming itself,
    # not a silent pass.
    scoped = _narrative_scope_ids(labels)
    executable = mnc.executable_label_ids(labels)
    discharged = [lid for lid in scoped if mnc.is_discharged(labels[lid])]
    screens_run = [lid for lid in scoped if lid in executable]
    dead = [lid for lid in scoped if lid not in executable and lid not in discharged]
    if dead:
        raise ValueError(
            f"{', '.join(dead)}: scope includes 'narrative' but declares no "
            "executable screen (forbidden_finding+scope:[all], "
            "detect.patterns, or match.any_of) and no `discharged:` block "
            "explaining why one is not needed. Scoring against this label "
            "would report zero_mnc_violations having evaluated nothing — "
            "see evals/results/05-blocked-path.md.")

    narrated = [{"id": fid, **(body or {})}
                for fid, body in (narrative.get("findings") or {}).items()]
    violations = mnc.declared_violations(
        labels, blob=json.dumps(narrative, ensure_ascii=False), findings=narrated)

    advisory = quantity_word_notes(narrative) + template_containment_notes(narrative, brief)

    return {
        "harness_version": harness_version(),
        "errors": errors,
        "numerals": numerals,
        "mnc_violations": violations,
        # How many narrative-scoped MNC screens actually ran, by id — not just
        # what they found. A bar that reports green must be able to show its
        # work (C1a).
        "mnc_screens_run": screens_run,
        "mnc_screens_discharged": discharged,
        "advisory": advisory,
        "passed": not errors and not numerals and not violations,
    }


# ---------------------------------------------------------------------------
# provenance — verified rather than printed (I1)
#
# eval_triage.py::provenance sets the standard: "a pin nobody checks is a
# comment." This scorer's pins used to be exactly that — --prompt-version
# accepted any string, brief_sha256 was copied from the run record and never
# recomputed from --brief, run_meta.prompt_version was recorded and never
# compared against --prompt-version, and HARNESS_VERSION was a bare constant
# with no binding to the bytes it named.
# ---------------------------------------------------------------------------

def harness_version(path: Path = HARNESS_PATH) -> str:
    """`narrative-eval/v0.1+<sha8>` — mirrors eval_triage.harness_version().

    Read at call time, not at import, so the digest describes the bytes on
    disk. Moves on any edit to this file, including one that changes no bar —
    the same trade eval_triage.rubric_version()/harness_version() make.
    """
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:8]
    return f"{HARNESS_VERSION}+{digest}"


def provenance(run: dict[str, Any], brief_path: Path, prompt_version: str) -> dict[str, Any]:
    """The narrator layer's pins, verified rather than printed.

    Three gaps this closes, all reachable from the CLI before this existed:
    an unpinned or made-up --prompt-version scored a run anyway; brief_sha256
    was copied from run_meta and never checked against the brief actually
    passed on the command line, so scoring run 1 against the wrong brief still
    recorded run 1's digest; and run_meta.prompt_version — the model's own
    record of what it was run against — was never compared to --prompt-version
    at all.
    """
    resolved_prompt = eval_triage.resolve_prompt_version(prompt_version)

    run_meta = run.get("run_meta") or {}
    computed_brief_sha256 = hashlib.sha256(Path(brief_path).read_bytes()).hexdigest()
    recorded_brief_sha256 = run_meta.get("brief_sha256")
    if recorded_brief_sha256 and recorded_brief_sha256 != computed_brief_sha256:
        raise SystemExit(
            f"brief hash does not match the run's pin.\n"
            f"  run_meta.brief_sha256: {recorded_brief_sha256}\n"
            f"  {brief_path}: {computed_brief_sha256}\n"
            "The run was scored against a different brief than the one it saw. "
            "Coverage is this harness's strongest gate and it depends entirely "
            "on the brief being the right one — point --brief at the brief "
            "this run was actually rendered against.")

    recorded_prompt_version = run_meta.get("prompt_version")
    if recorded_prompt_version and recorded_prompt_version != resolved_prompt:
        raise SystemExit(
            f"--prompt-version does not match the run's record.\n"
            f"  --prompt-version: {resolved_prompt}\n"
            f"  run_meta.prompt_version: {recorded_prompt_version}\n"
            "The run was not produced by the prompt version being asserted "
            "here.")

    return {
        "prompt_version": resolved_prompt,
        "brief_sha256": computed_brief_sha256,
        "rubric_version": eval_triage.rubric_version(),
        "narrative_harness": harness_version(),
        "model": run_meta.get("model"),
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
    result["provenance"] = provenance(run, args.brief, args.prompt_version)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
