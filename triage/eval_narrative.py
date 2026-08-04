"""Scores an impact-narrator run against everything checkable by machine.

There's no ground-truth prose to compare against, so checks come in three tiers:

  * hard gates      — schema, word caps, coverage, the numeral ban, the blocked
                      path, and the must-not-claim screens the labels declare
  * advisory        — spelled-out quantities and template containment. Both are
                      partial, both report, neither fails a run
  * the human read  — is the consequence true, is the change a real fix

Invariant: keep this separate from eval_triage.py. The triage harness pin is
derived from that file's bytes, so a narrative change must not move a triage
pin.

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

#: Phrases that state a quantity without using a digit. Checked on every
#: narrative whatever labels are loaded, and only ever reported, never failed.
QUANTITY_WORDS = ("percent", "per cent", "a third", "a quarter", "a half",
                  "twice as", "three times", "double the", "half of", "most of")

#: Invariant: the numeral ban only covers digit characters, so "roughly a third
#: of shoppers" slips past it. That's why these phrases are gated separately.
#:
#: Invariant: "most of" stays out of the hard gate. Unlike the others it names
#: no proportion at all, just a qualitative majority, which rubric §6 rule 1
#: allows as directional language. That is not only an argument: it is the one
#: phrase here that appears in three recorded, passing entry-02 runs
#: (runs/narrator-v0.1-run{1,2,3}.json — "most of your traffic", "most of these
#: are small changes"), and the human read in
#: evals/results/09-impact-narrator.md already licensed every instance. Gating
#: it would fail three recorded runs to close a hole this evidence says is not
#: open. It stays in the advisory list so a human can still eyeball it.
_QUANTITY_GATE_EXCLUDE = ("most of",)
QUANTITY_GATE_WORDS = tuple(w for w in QUANTITY_WORDS if w not in _QUANTITY_GATE_EXCLUDE)


def quantity_word_patterns() -> tuple[str, ...]:
    """The gate words as word-bounded regexes.

    A label file copies these into its own `detect.patterns`. Kept as a function
    so a test can recompute them and fail if the two copies drift apart.
    """
    return tuple(rf"\b{re.escape(w)}\b" for w in QUANTITY_GATE_WORDS)


#: Words that count as naming the gate on a blocked store.
#: Invariant: match these on word boundaries, not as substrings — "gate" lives
#: inside navigate and mitigate, and "could not navigate to any page" once
#: satisfied this check without naming a gate at all. "gated" is listed
#: separately because a word-bounded "gate" does not match inside it.
_GATE_WORDS = ("gate", "gated", "password", "unreachable", "could not be reached",
               "not reachable", "blocked")
_GATE_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _GATE_WORDS) + r")\b", re.I)


def brief_ids(brief: dict[str, Any]) -> set[str]:
    """Every id the narrative must cover — all three buckets, not just the roadmap."""
    return {str(f.get("id")) for bucket in ("roadmap", "needs_verification", "noted")
            for f in (brief.get(bucket) or [])}


def _values(narrative: dict[str, Any]) -> list[tuple[str, str]]:
    """Every (field name, text) pair in a narrative."""
    out = [("summary", str(narrative.get("summary") or ""))]
    for fid, body in (narrative.get("findings") or {}).items():
        for field in FIELDS:
            out.append((f"{fid}.{field}", str((body or {}).get(field) or "")))
    return out


def validate(narrative: dict[str, Any], brief: dict[str, Any]) -> list[str]:
    """Check a narrative's shape, word caps, and coverage of the brief."""
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

    # Word caps apply on every path, including the blocked one where the summary
    # is the whole deliverable, so they run before the early return below.
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
    """Find any digit in the narrative's prose — numbers are not allowed.

    Only field values are scanned. Ids like `F-01` are keys, not prose.
    """
    out = []
    for name, value in _values(narrative):
        hit = _DIGIT_RE.search(value)
        if hit:
            out.append(f"{name} contains a digit ({value[max(0, hit.start() - 20):hit.end() + 20]!r})")
    return out


def quantity_word_notes(narrative: dict[str, Any]) -> list[str]:
    """Note any spelled-out quantity, for a human to read. Never fails a run.

    This overlaps the hard gate where a label declares one, which is fine — an
    entry with no such label would otherwise have no signal at all, and this
    also catches "most of", which the hard gate leaves alone.
    """
    out = []
    for name, value in _values(narrative):
        for word in QUANTITY_WORDS:
            if word in value.lower():
                out.append(f"{name} contains the quantity phrase {word!r} — read it")
    return out


def template_containment_notes(narrative: dict[str, Any],
                               brief: dict[str, Any]) -> list[str]:
    """Note where a finding mentions a template that isn't one of its own.

    Advisory only: "cannot add this product to the cart" is correct English
    about a PDP defect, and a strict check would fail it. A human decides.
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
    """The label ids that reach the narrative layer and must be screened here.

    Counts `scope: [narrative]`, `scope: [all]`, a bare string scope, and a
    label with no scope key at all.

    Invariant: a missing scope must mean "reaches every layer", not "reaches
    none" — otherwise an unscoped label silently escapes every screen.
    """
    out = []
    for label_id, label in labels.items():
        if not label_id.startswith("MNC-"):
            continue
        if label.get("scope") is None:
            out.append(label_id)
            continue
        scope = mnc.scope_list(label)
        if "narrative" in scope or "all" in scope:
            out.append(label_id)
    return sorted(out)


def evaluate(narrative: dict[str, Any], brief: dict[str, Any],
             labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Run every check over one narrative and return the full result."""
    errors = validate(narrative, brief)
    numerals = numeral_violations(narrative)

    # Checked across every label, not just narrative-scoped ones — a malformed
    # discharge is a bug in the label whichever layer it would have exempted.
    malformed_discharge = sorted(
        lid for lid, label in labels.items()
        if lid.startswith("MNC-") and mnc.discharge_incomplete(label))
    if malformed_discharge:
        raise ValueError(
            f"{', '.join(malformed_discharge)}: carries a `discharged:` key "
            "that is not a complete discharge — both `by` and `note` must be "
            "non-empty. `discharged: true` (or a block missing either field) "
            "silences a must-not-claim screen with no reasoning on record, "
            "which is the same accountability gap as never discharging it, "
            "just quieter about it.")

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
        # Which screens actually ran, by id — a green result has to show its work.
        "mnc_screens_run": screens_run,
        "mnc_screens_discharged": discharged,
        "advisory": advisory,
        "passed": not errors and not numerals and not violations,
    }


# ---------------------------------------------------------------------------
# provenance
#
# Invariant: every pin below is recomputed and compared, never just printed. A
# pin nobody checks is a comment.
# ---------------------------------------------------------------------------

def harness_version(path: Path = HARNESS_PATH) -> str:
    """This harness's version plus a hash of its own bytes.

    Read at call time so the hash describes the file on disk. It moves on any
    edit to this file, even one that changes no check.
    """
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:8]
    return f"{HARNESS_VERSION}+{digest}"


def provenance(run: dict[str, Any], brief_path: Path, prompt_version: str, *,
               render_indent: int | None = None,
               prompts_dir: Path = eval_triage.PROMPTS_DIR) -> dict[str, Any]:
    """Verify the run's pins and return them.

    Recomputes the brief's hash from the file passed on the command line,
    checks the prompt version against what the run recorded, and — when the
    run carries rendered_sha256 — requires the template on disk to re-render
    to exactly what the model saw. Exits on any mismatch.
    """
    resolved_prompt = eval_triage.resolve_prompt_version(prompt_version, prompts_dir)
    prompt_name = resolved_prompt.split("+", 1)[0]

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
    if recorded_prompt_version and recorded_prompt_version != prompt_name:
        raise SystemExit(
            f"--prompt-version does not match the run's record.\n"
            f"  --prompt-version: {resolved_prompt}\n"
            f"  run_meta.prompt_version: {recorded_prompt_version}\n"
            "The run was not produced by the prompt version being asserted "
            "here.")

    # The strong check. The brief was already verified against the run's own
    # brief_sha256 above, so a mismatch here can only be the template.
    prompt_pin = "exists"
    recorded_rendered = run_meta.get("rendered_sha256")
    if recorded_rendered:
        template = prompts_dir / f"{prompt_name}.md"
        if recorded_rendered in eval_triage._rendered_digests(
                template, brief_path, "BRIEF", render_indent):
            prompt_pin = "matched"
        else:
            raise SystemExit(
                f"the prompt on disk does not reproduce what this run saw.\n"
                f"  run_meta.rendered_sha256: {recorded_rendered}\n"
                f"  re-render of {template}: no match\n"
                "The template was edited in place after the run, or the rendered "
                "file was edited before it. If the run was rendered with a "
                "non-default --indent, pass the same value as --render-indent.")

    return {
        "prompt_version": resolved_prompt,
        "prompt_pin": prompt_pin,
        "brief_sha256": computed_brief_sha256,
        "rubric_version": eval_triage.rubric_version(),
        "narrative_harness": harness_version(),
        "model": run_meta.get("model"),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: score one narrator run and print the result."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", type=Path, help="a narrator run JSON")
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--entry", type=Path, required=True,
                        help="evals/golden/<entry> — its labels supply the screens")
    parser.add_argument("--prompt-version", required=True,
                        help="required on purpose — an unpinned run is not a result")
    parser.add_argument("--render-indent", type=int, default=None,
                        help="the --indent the run's prompt was rendered with, if any "
                             "(needed to re-derive rendered_sha256 for the prompt pin)")
    args = parser.parse_args(argv)

    run = json.loads(args.run.read_text(encoding="utf-8"))
    narrative = run.get("output", run)
    brief = json.loads(args.brief.read_text(encoding="utf-8"))
    labels = eval_triage.parse_labels(args.entry / "expected" / "findings.md")

    result = evaluate(narrative, brief, labels)
    result["provenance"] = provenance(run, args.brief, args.prompt_version,
                                      render_indent=args.render_indent)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
