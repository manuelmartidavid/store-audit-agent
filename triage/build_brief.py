"""Turns a triage run into the narrator's brief.

Takes a triage run plus its pack and produces a brief: the same findings,
verbatim, split into three buckets, ranked and truncated.

Invariant: this file only does arithmetic and set logic. Ranking comes from
triage.scoring so the two roadmaps can't disagree, and judgement calls belong
to the narrator downstream.

Usage:
    python triage/build_brief.py runs/v1.0-cli-run1.json \
        --pack packs/02-sabotaged.pack.json -o briefs/02-sabotaged.brief.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import eval_triage  # noqa: E402
from triage.scoring import (  # noqa: E402
    MAX_PER_TEMPLATE,
    MAX_TOTAL,
    SEVERITY_WEIGHT,
    STATUS_ASSESSED,
    STATUS_INACCESSIBLE,
    roadmap,
)

SCHEMA = "brief/v0.1"

#: An allow-list, not a copy: `password_env` names a secret, and `platform` is
#: only added when the crawl actually succeeded.
STORE_FIELDS = ("vertical", "market", "currency", "aov", "monthly_sessions",
                "mobile_share", "catalog_size", "notes")


def split_buckets(findings: list[dict[str, Any]]
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split findings into (roadmap, needs_verification, noted).

    Low confidence is checked first, then a null severity — a finding can be both.
    """
    road: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    noted: list[dict[str, Any]] = []
    for f in findings:
        if f.get("confidence") == "low":
            needs.append(f)
        elif f.get("severity") is None:
            noted.append(f)
        else:
            road.append(f)
    return road, needs, noted


def truncate(findings: list[dict[str, Any]], *,
             max_per_template: int = MAX_PER_TEMPLATE,
             max_total: int = MAX_TOTAL) -> tuple[list[dict[str, Any]], int]:
    """Cap an already-ranked list per template and overall.

    A finding takes a slot on every template it names.

    Invariant: when a template is full, drop that finding and carry on down the
    list. Stopping would let one saturated page swallow every finding below it.
    """
    used: dict[str, int] = {}
    admitted: list[dict[str, Any]] = []
    dropped = 0
    for f in findings:
        templates = list(f.get("templates") or [])
        if len(admitted) >= max_total:
            dropped += 1
            continue
        if any(used.get(t, 0) >= max_per_template for t in templates):
            dropped += 1
            continue
        for t in templates:
            used[t] = used.get(t, 0) + 1
        admitted.append(f)
    return admitted, dropped


def rank_eligible(eligible: list[dict[str, Any]]
                  ) -> tuple[list[dict[str, Any]], list[str]]:
    """Put findings back in the order `scoring.roadmap()` gives their ids.

    Returns `(ranked, lost)`, where `lost` holds any eligible finding roadmap()
    never returned — usually one with an off-enum severity.

    Invariant: use one queue per id rather than an id-keyed dict. Two findings
    sharing an id would collapse into one and the second would silently vanish.
    """
    queues: dict[str, deque] = defaultdict(deque)
    for f in eligible:
        queues[str(f.get("id"))].append(f)

    ranked: list[dict[str, Any]] = []
    for label_id in roadmap(eligible):
        queue = queues.get(label_id)
        if queue:
            ranked.append(queue.popleft())

    lost = sorted(str(f.get("id")) for queue in queues.values() for f in queue)
    return ranked, lost


def duplicate_or_missing_ids(findings: list[dict[str, Any]]) -> list[str]:
    """Ids shared by two findings, or missing from more than one.

    Invariant: everything downstream of the brief is keyed by id, so a
    collision here makes one finding unaddressable even though it's still in a
    list. Checked across all findings, not just roadmap-eligible ones.
    """
    seen: dict[str, int] = {}
    for f in findings:
        fid = f.get("id")
        key = str(fid) if fid not in (None, "") else "<missing id>"
        seen[key] = seen.get(key, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


def store_block(pack_store: dict[str, Any], blocked: bool) -> dict[str, Any]:
    """The store fields the narrator is allowed to see.

    Invariant: `platform` is left out on a blocked crawl. The narrator is
    forbidden from naming it there, so handing it over and then failing the
    model for using it would be entrapment.
    """
    block = {k: pack_store.get(k) for k in STORE_FIELDS}
    if not blocked:
        block["platform"] = pack_store.get("platform")
    return block


def build_brief(triage_output: dict[str, Any], pack: dict[str, Any], *,
                triage_run_name: str = "", triage_prompt_version: str = "",
                pack_sha256: str = "") -> dict[str, Any]:
    """Build the whole brief from a triage output and its pack."""
    blocked = (pack.get("crawl") or {}).get("status") == "blocked"
    findings = list(triage_output.get("findings") or [])

    provenance = {
        "triage_run": triage_run_name,
        "triage_prompt_version": triage_prompt_version,
        "pack_sha256": pack_sha256,
        "pack_manifest_sha256": (pack.get("provenance") or {}).get("manifest_sha256"),
        "rubric_version": eval_triage.rubric_version(),
    }

    if blocked:
        return {"schema": SCHEMA, "store_status": STATUS_INACCESSIBLE,
                "store": store_block(pack.get("store") or {}, blocked=True),
                "roadmap": [], "needs_verification": [], "noted": [],
                "overflow_count": 0, "provenance": provenance}

    duplicates = duplicate_or_missing_ids(findings)
    if duplicates:
        raise ValueError(
            f"build_brief: {duplicates} — an id shared by more than one "
            f"finding (or missing from more than one). Everything downstream "
            f"of the brief is keyed by id; a collision here makes one "
            f"finding silently unaddressable even though it is present in a "
            f"list. Fix the triage run's finding ids.")

    eligible, needs, noted = split_buckets(findings)
    ranked, lost = rank_eligible(eligible)
    if lost:
        # Invariant: the split has to be total — every finding must end up in
        # roadmap, needs_verification, noted, or overflow_count. Anything in
        # `lost` is in none of them.
        raise ValueError(
            f"build_brief: {lost} would land in no bucket and are not "
            f"counted in overflow_count. triage.scoring.roadmap() silently "
            f"drops a finding whose severity is not one of "
            f"{sorted(SEVERITY_WEIGHT)} — check for a typo or an id that "
            f"collides with another finding's.")
    admitted, overflow = truncate(ranked)

    return {"schema": SCHEMA, "store_status": STATUS_ASSESSED,
            "store": store_block(pack.get("store") or {}, blocked=False),
            "roadmap": admitted, "needs_verification": needs, "noted": noted,
            "overflow_count": overflow, "provenance": provenance}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: build one brief and write it to a file."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", type=Path, help="a triage run JSON")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args(argv)

    run = json.loads(args.run.read_text(encoding="utf-8"))
    output = run.get("output", run)
    pack = json.loads(args.pack.read_text(encoding="utf-8"))

    # build_brief() raises when a finding would be lost. Turn that into a plain
    # message rather than a traceback.
    try:
        brief = build_brief(
            output, pack,
            triage_run_name=args.run.name,
            triage_prompt_version=(run.get("run_meta") or {}).get("prompt_version", ""),
            pack_sha256=hashlib.sha256(args.pack.read_bytes()).hexdigest(),
        )
    except ValueError as e:
        raise SystemExit(str(e))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{args.out}  status={brief['store_status']}  "
          f"roadmap={len(brief['roadmap'])}  needs_verification="
          f"{len(brief['needs_verification'])}  noted={len(brief['noted'])}  "
          f"overflow={brief['overflow_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
