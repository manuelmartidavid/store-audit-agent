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
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import eval_triage  # noqa: E402
from triage.scoring import (  # noqa: E402
    MAX_PER_TEMPLATE,
    MAX_TOTAL,
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

    eligible, needs, noted = split_buckets(findings)
    by_id = {f.get("id"): f for f in eligible}
    ranked = [by_id[i] for i in roadmap(eligible) if i in by_id]
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

    brief = build_brief(
        output, pack,
        triage_run_name=args.run.name,
        triage_prompt_version=(run.get("run_meta") or {}).get("prompt_version", ""),
        pack_sha256=hashlib.sha256(args.pack.read_bytes()).hexdigest(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{args.out}  status={brief['store_status']}  "
          f"roadmap={len(brief['roadmap'])}  needs_verification="
          f"{len(brief['needs_verification'])}  noted={len(brief['noted'])}  "
          f"overflow={brief['overflow_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
