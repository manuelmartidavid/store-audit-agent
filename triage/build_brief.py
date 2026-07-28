"""Turn a triage run into the narrator's brief. Contract: specs/narrator-io.md §2.

    triage run JSON (triage/v0.1)  +  pack/v0.2
            ↓
    brief/v0.1 — findings verbatim, split three ways, ranked and truncated

Everything this file does is arithmetic and set logic. Rank comes from
triage.scoring (rubric §4), so the production roadmap and the harness's roadmap
cannot disagree. The narrator downstream makes judgments; this file must not.

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

#: An allow-list, not a copy (narrator-io §2.4). `password_env` names a secret and
#: has no narrative use; `platform` is appended only when the crawl succeeded.
STORE_FIELDS = ("vertical", "market", "currency", "aov", "monthly_sessions",
                "mobile_share", "catalog_size", "notes")


def split_buckets(findings: list[dict[str, Any]]
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Three buckets, and the precedence is fixed because the conditions co-occur.

    `confidence: low` wins first (rubric §3 puts low-confidence findings in "Needs
    verification" and does not carve out null severity), then `severity: null`.
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
    """Rubric §5, applied to an already-ranked list.

    A finding occupies a slot on **every** template it names, because rollup means
    one finding really is present on all of them. When one of its templates is
    full the finding is dropped and the walk *continues* — stopping would let a
    saturated page swallow every finding ranked below it, on pages with room.
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
    """Pair `scoring.roadmap()`'s id order back to finding objects — by
    identity, not by a plain id-keyed dict.

    A dict keyed `str(f.get("id"))` collapses two findings that share an id
    (or both have none) into one entry, so the second silently disappears
    instead of reaching the roadmap. A queue per id preserves both: each
    occurrence of an id in `roadmap()`'s output consumes exactly one queued
    finding, so two same-id findings are both represented if `roadmap()`
    names the id twice, and neither is lost to the other.

    Returns `(ranked, lost)`. `lost` is every eligible finding's id that
    `roadmap()` never returned at all — I3's target: `roadmap()` re-filters
    on `severity in SEVERITY_WEIGHT`, so a finding that is eligible for the
    roadmap (non-null severity, not low-confidence) but carries an off-enum
    severity (a typo, a future rubric level, anything not in `{critical,
    high, medium, low}`) is silently dropped there, before `truncate()` ever
    runs — it lands in no bucket and is not counted in `overflow_count`
    either. This is the one failure that can lose a finding between triage
    and the client with nothing downstream to catch it, since every later
    layer measures against the brief.
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
    """I3's other route to the same loss: an id two findings share, or that
    neither carries at all.

    `brief.roadmap` / `needs_verification` / `noted` are plain lists, but
    everything downstream — `eval_narrative.brief_ids()`, `narrative.findings`
    — is keyed by id. Two findings sharing an id (including two both missing
    one) collapse to the same key one layer down, and one becomes silently
    unaddressable even though it never went missing from any *list* here.
    Checked across the whole input, not just the roadmap-eligible slice: the
    collision is just as real if one instance lands in `noted` and the other
    in `roadmap`.
    """
    seen: dict[str, int] = {}
    for f in findings:
        fid = f.get("id")
        key = str(fid) if fid not in (None, "") else "<missing id>"
        seen[key] = seen.get(key, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


def store_block(pack_store: dict[str, Any], blocked: bool) -> dict[str, Any]:
    """narrator-io §2.4 — an allow-list with one conditional field.

    `platform` is dropped on a blocked crawl. The pack copies it verbatim from
    context.yaml, but the crawler reports no platform there by design, and entry
    05's MNC-003 forbids the string in a blocked narrative. Supplying the field
    and then failing the model for using it would be entrapment, not a test.
    """
    block = {k: pack_store.get(k) for k in STORE_FIELDS}
    if not blocked:
        block["platform"] = pack_store.get("platform")
    return block


def build_brief(triage_output: dict[str, Any], pack: dict[str, Any], *,
                triage_run_name: str = "", triage_prompt_version: str = "",
                pack_sha256: str = "") -> dict[str, Any]:
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
        # I3 — the split must be total: every input finding lands in roadmap,
        # needs_verification, noted, or overflow_count. `lost` reaching here
        # means `scoring.roadmap()` silently dropped a finding — off-enum
        # severity, or an id colliding with another finding's — before
        # `truncate()` ever ran, so it is in none of the three buckets and not
        # counted in overflow_count either.
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run", type=Path, help="a triage run JSON")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args(argv)

    run = json.loads(args.run.read_text(encoding="utf-8"))
    output = run.get("output", run)
    pack = json.loads(args.pack.read_text(encoding="utf-8"))

    # `build_brief()` raises ValueError for the two ways a finding set can
    # lose a finding between triage and the client (I3: colliding/missing
    # ids, or `scoring.roadmap()` silently dropping an off-enum severity).
    # Left uncaught, that is a Python traceback instead of a report — the
    # same fatal-reporting convention `eval_narrative.py::provenance()`
    # already uses (`raise SystemExit(message)`, no traceback) applies here.
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
