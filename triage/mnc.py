"""Evaluate must-not-claim labels using the detection rules the label declares.

Extracted from triage/eval_triage.py so the narrator's scorer reads the same
labels the triager's does. The generalisation is one parameter: `blob` is
whatever text the screens should match, so the same rules run against a triage
findings array and against a narrative object.

The bug this shape exists to prevent is recorded in
evals/results/05-blocked-path.md: the screens were hardcoded to entry 02's rules,
so entry 05 reported `zero_mnc_violations: True` having evaluated nothing.

A `crawl:` pointer needs a template *and* at least one semantic-path segment
(spec §9) — `crawler.pointers.matches` returns False whenever either side has
zero path segments. A `match.any_of` entry like `crawl:404`, with nothing after
the template, can therefore never match anything: the label would contribute
zero violations forever, which is the same silent-pass failure by a different
route. Such a pointer is rejected loudly inside `declared_violations()`, on
every call, rather than shipped as a screen that always passes.

`executable_label_ids()` names the labels `declared_violations()` can actually
evaluate, so a caller can tell "screen ran, found nothing" apart from "screen
never existed" — the entry-02 MNC-402/403 gap this pair of functions was added
to close (`evals/HARNESS-CHANGELOG.md`, `narrative-eval/v0.1`). A label whose
`scope` includes `narrative` but is absent from that set, and carries no
`discharged:` block explaining why, is a hard error in
`triage/eval_narrative.py::evaluate` rather than a silent pass.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import pointers as ptr  # noqa: E402


def scope_list(label: dict[str, Any]) -> list[str]:
    """Normalise a label's `scope` to a lowercase list.

    A hand-written label can spell `scope` three ways: a list (the common
    case), a bare string (`scope: narrative` with no brackets), or the key
    left off entirely. Iterating a bare string directly (`for x in
    "narrative"`) silently yields one entry per character — `"n", "a",
    "r", …` — which breaks every `in scope` check without raising anything.
    That is the same slipped-past-the-guard failure V2 named one layer up
    (`eval_narrative._narrative_scope_ids`), just reachable from here too, so
    both callers normalise through this one function rather than each
    re-deriving the same list comprehension and drifting on the edge cases.
    """
    raw = label.get("scope")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.lower()]
    return [str(s).lower() for s in raw]


def _screen_shapes(label: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    """The three executable shapes, isolated so `declared_violations` and
    `executable_label_ids` cannot drift on what counts as one.

    Returns (forbidden_finding_scope_all, patterns, forbidden_pointers). A
    `match.any_of` entry ending in `*` is a wildcard, not a forbidden pointer —
    `axe:*` cannot itself be cited, only matched against, so it contributes no
    screen (`test_a_wildcard_axe_pointer_is_still_skipped_not_raised`).
    """
    scope = scope_list(label)
    forbidden_finding = label.get("type") == "forbidden_finding" and "all" in scope
    patterns = [p for p in ((label.get("detect") or {}).get("patterns") or [])]
    forbidden = [p for p in ((label.get("match") or {}).get("any_of") or [])
                if isinstance(p, str) and not p.endswith("*")]
    return forbidden_finding, patterns, forbidden


def is_discharged(label: dict[str, Any]) -> bool:
    """Does the label document, rather than implement, its own screen — and
    does it document it *completely*?

    A `discharged:` block is an explicit, reviewed statement that no
    executable screen is needed at this layer — e.g. entry 05's MNC-002,
    closed by the fact that `narrative/v0.1` carries no score field at all.
    It is not a silent skip: the reasoning has to live in the label, so a
    block is only recognised here when it carries a non-empty `by` *and* a
    non-empty `note` — `discharged: true` or `discharged: {}` silences a
    must-not-claim screen with exactly as little accountability as never
    discharging it, just quieter about it. `executable_label_ids` still
    reports a discharge separately from a label that actually ran a screen,
    so a reader can tell "exempted, on the record" from "nobody wired this
    up". See `discharge_incomplete()` for the third case — a `discharged:`
    key that is present but does not qualify.
    """
    d = label.get("discharged")
    return isinstance(d, dict) and bool(d.get("by")) and bool(d.get("note"))


def discharge_incomplete(label: dict[str, Any]) -> bool:
    """True when a label carries a `discharged` key that is truthy but does
    not qualify as `is_discharged()` — `discharged: true`, `discharged: {}`,
    or a block missing `by` or `note`.

    Distinguished from "no `discharged` key at all" (which is simply not
    discharged, and may be perfectly fine for a label that carries its own
    executable screen) so a caller can raise a specific, actionable error
    instead of folding a malformed discharge into the generic "no executable
    screen and no discharged: block" message.
    """
    d = label.get("discharged")
    return bool(d) and not is_discharged(label)


def executable_label_ids(labels: dict[str, dict[str, Any]]) -> set[str]:
    """MNC label ids `declared_violations` can actually evaluate.

    A label outside this set produces no verdict from `declared_violations`
    regardless of scope. That is correct for a label whose detection is a
    human judgment — but from the outside, "evaluated, found nothing" and
    "never evaluated" look identical unless something names the difference.
    This is that name: `triage/eval_narrative.py::evaluate` surfaces it as
    `mnc_screens_run` and hard-fails a `narrative`-scoped label that is
    neither in this set nor `is_discharged()` (the entry-02 MNC-402/403 gap
    recorded in `evals/HARNESS-CHANGELOG.md`, `narrative-eval/v0.1`).
    """
    out: set[str] = set()
    for label_id, label in labels.items():
        if not label_id.startswith("MNC-"):
            continue
        forbidden_finding, patterns, forbidden = _screen_shapes(label)
        if forbidden_finding or patterns or forbidden:
            out.add(label_id)
    return out


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
        scope = scope_list(label)

        if label.get("type") == "forbidden_finding" and "all" in scope and findings:
            out.append({"rule": label_id, "finding": "*",
                        "why": f"{len(findings)} finding(s) emitted where the label "
                               f"forbids any"})

        # Every pattern is compiled before any of them is trusted to have
        # searched anything. `executable_label_ids` counts a non-empty
        # `patterns` list as a screen that ran — that field is what a caller
        # reads to tell "evaluated, found nothing" from "never evaluated" —
        # so a pattern that cannot even compile must not be silently skipped
        # (the old `except re.error: continue`). That let a label with
        # `patterns: ["[unclosed"]` land in `mnc_screens_run` having matched
        # nothing: the field added to prove a screen ran was itself false.
        # Same treatment a grammar-invalid `crawl:` pointer already gets
        # below, and for the same reason: a label that cannot run must be
        # loud, never counted.
        for pattern in ((label.get("detect") or {}).get("patterns") or []):
            try:
                compiled = re.compile(pattern, re.I)
            except re.error as exc:
                raise ValueError(
                    f"{label_id}: detect.patterns entry {pattern!r} does not "
                    f"compile as a regex ({exc}). A label that cannot run "
                    f"must be loud, never counted as a screen that ran.")
            hit = compiled.search(blob)
            if hit:
                out.append({"rule": label_id, "finding": "*",
                            "why": f"output matches forbidden pattern {pattern!r} "
                                   f"→ {hit.group(0)!r}"})

        forbidden = [p for p in ((label.get("match") or {}).get("any_of") or [])
                     if isinstance(p, str) and not p.endswith("*")]
        for p in forbidden:
            if p.startswith("crawl:"):
                path = p.split("/", 1)[1] if "/" in p else ""
                if not path:
                    raise ValueError(
                        f"{label_id}: match.any_of pointer {p!r} has no path "
                        f"segment after the template — it is grammar-invalid "
                        f"per specs/crawler.md §9 and can never match anything, "
                        f"so this label would silently contribute zero violations")
        if forbidden:
            for f in findings:
                cited = [p for p in (f.get("evidence") or [])
                         if any(ptr.matches(p, q) for q in forbidden)]
                if cited:
                    out.append({"rule": label_id, "finding": f.get("id"),
                                "why": f"cites forbidden evidence {cited}"})
    return out
