"""Checks model output against the must-not-claim labels, using each label's own rules.

Shared by the triager's scorer and the narrator's: `blob` is whatever text the
screens should match, so the same rules run against both.

Invariant: the whole point here is that a screen which can't run must be loud,
never silently counted as passing. Two ways that has gone wrong before:
  * screens hardcoded to one entry's rules reported "no violations" having
    checked nothing;
  * a `crawl:` pointer with no path segment after the template can never match,
    so its label would contribute zero violations forever.
Both now raise instead.
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

    Invariant: always go through this. A hand-written label may spell `scope`
    as a list, a bare string, or leave it off; iterating a bare string yields
    one entry per character and breaks every `in scope` check without raising.
    """
    raw = label.get("scope")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.lower()]
    return [str(s).lower() for s in raw]


def _screen_shapes(label: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    """The three kinds of screen a label can carry.

    Returns (forbidden_finding, patterns, forbidden_pointers). A `match.any_of`
    entry ending in `*` is a wildcard and contributes no screen.
    """
    scope = scope_list(label)
    forbidden_finding = label.get("type") == "forbidden_finding" and "all" in scope
    patterns = [p for p in ((label.get("detect") or {}).get("patterns") or [])]
    forbidden = [p for p in ((label.get("match") or {}).get("any_of") or [])
                if isinstance(p, str) and not p.endswith("*")]
    return forbidden_finding, patterns, forbidden


def is_discharged(label: dict[str, Any]) -> bool:
    """True if the label explains in writing why it needs no executable screen.

    Only counts when the `discharged` block carries both a `by` and a `note`.

    Invariant: keep both required. A bare `discharged: true` silences a screen
    with no accountability at all.
    """
    d = label.get("discharged")
    return isinstance(d, dict) and bool(d.get("by")) and bool(d.get("note"))


def discharge_incomplete(label: dict[str, Any]) -> bool:
    """True when a label tried to discharge itself but did it incompletely.

    Kept separate from "no `discharged` key at all" so the caller can raise a
    specific error rather than a generic one.
    """
    d = label.get("discharged")
    return bool(d) and not is_discharged(label)


def executable_label_ids(labels: dict[str, dict[str, Any]]) -> set[str]:
    """The label ids `declared_violations` can actually check.

    This is what lets a caller tell "checked, found nothing" apart from "never
    checked" — labels outside this set produce no verdict at all.
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
    """Find every violation of a label that says how to detect itself.

    Labels come in three checkable shapes:

      type: forbidden_finding · scope: [all]   → any finding at all violates
      detect.patterns: [regex, …]              → matched against `blob`
      match.any_of: [pointer, …]               → violated by citing one
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

        # Invariant: never swallow a bad regex here. A pattern that doesn't
        # compile used to be skipped, which left the label counted as a screen
        # that ran while it had matched nothing.
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
