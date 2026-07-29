"""Turns a captured fixture into a model-sized evidence pack.

Reads the crawl, Lighthouse, and axe files plus the store context, and produces
one pack of roughly 220k tokens for a six-template Shopify capture.

Invariant: scripts measure, the model judges. Nothing here decides what counts
as a finding — the job is to drop bytes no finding could cite, and to count
what was dropped so absence stays distinguishable from omission.

Invariant: drop audits by structural rule, never by an allow-list of audit ids.
An allow-list is a detection ceiling: a finding whose only evidence is an audit
nobody listed can't be found at all. Audits go only when they're payload
carriers or Lighthouse called them notApplicable, and passing audits collapse
to an id rather than disappearing.

Usage:
    python triage/pack_evidence.py fixtures/02-sabotaged \
        --context evals/golden/02-sabotaged/context.yaml \
        -o packs/02-sabotaged.pack.json
    python triage/pack_evidence.py fixtures/02-sabotaged --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import token_estimate  # noqa: E402

try:  # pyyaml is a requirement, but --stats should still work without it
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler import pointers as ptr  # noqa: E402

PACK_VERSION = "pack/v0.2"

#: Key holding each node's own evidence pointer. Short on purpose — it appears
#: about 2,200 times in a six-template capture.
POINTER_KEY = "@"

# ---------------------------------------------------------------------------
# Lighthouse reduction rules
# ---------------------------------------------------------------------------

#: Audits that carry a payload rather than a conclusion — logs, screenshots,
#: dumps. Dropping them is about 85% of the Lighthouse result by weight and
#: costs no evidence.
#: Invariant: re-check this list against the labels whenever a golden entry is
#: added.
PAYLOAD_ONLY = frozenset({
    "network-requests",
    "screenshot-thumbnails",
    "script-treemap-data",
    "final-screenshot",
    "full-page-screenshot",
    "valid-source-maps",
    "user-timings",
    "main-thread-tasks",
    "metrics",              # just a re-bundle of the individual metric audits
    "network-rtt",
    "network-server-latency",
    "diagnostics",
    "resource-summary",
})

#: Metrics whose number is evidence however Lighthouse scored it. The rubric's
#: thresholds are numeric, so a passing CLS of 0 is as much a fact as a failing
#: one of 0.268.
ALWAYS_NUMERIC = frozenset({
    "first-contentful-paint",
    "largest-contentful-paint",
    "cumulative-layout-shift",
    "total-blocking-time",
    "speed-index",
    "interactive",
    "max-potential-fid",
    "server-response-time",
    "total-byte-weight",
})

_AUDIT_SCALARS = (
    "score", "scoreDisplayMode", "numericValue", "numericUnit",
    "displayValue", "explanation", "errorMessage",
)

MAX_DETAIL_ITEMS = 5
MAX_DETAIL_ITEM_CHARS = 1500
MAX_AXE_NODES = 5
MAX_AXE_HTML_CHARS = 200
MAX_AXE_SUMMARY_CHARS = 220


class PackError(RuntimeError):
    """Something is wrong with the fixture or its config. Raised, never ignored."""


# ---------------------------------------------------------------------------
# Lighthouse
# ---------------------------------------------------------------------------

def slim_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Strip one Lighthouse audit to its conclusion plus a sample of its evidence.

    `title` is kept because Lighthouse phrases it as the verdict. `description`
    is dropped — it's boilerplate that's identical for every run of every store.
    """
    out: dict[str, Any] = {"title": audit.get("title")}
    for key in _AUDIT_SCALARS:
        value = audit.get(key)
        if value not in (None, ""):
            out[key] = value
    if audit.get("warnings"):
        out["warnings"] = audit["warnings"]

    items = (audit.get("details") or {}).get("items")
    if isinstance(items, list) and items:
        kept: list[Any] = []
        for item in items[:MAX_DETAIL_ITEMS]:
            encoded = json.dumps(item, separators=(",", ":"), default=str)
            if len(encoded) > MAX_DETAIL_ITEM_CHARS and isinstance(item, dict):
                item = {k: v for k, v in item.items()
                        if isinstance(v, (str, int, float, bool))}
                item["_truncated"] = True
            kept.append(item)
        out["details_items"] = kept
        if len(items) > MAX_DETAIL_ITEMS:
            out["details_items_omitted"] = len(items) - MAX_DETAIL_ITEMS
    return out


def pack_lighthouse_run(lhr: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Pack one Lighthouse result, returning it and a count of what was dropped."""
    audits_out: dict[str, Any] = {}
    passed: list[str] = []
    dropped = {"payload_only": 0, "not_applicable": 0, "passed_collapsed": 0}

    for audit_id, audit in (lhr.get("audits") or {}).items():
        if audit_id in PAYLOAD_ONLY:
            dropped["payload_only"] += 1
            continue
        if audit.get("scoreDisplayMode") == "notApplicable":
            dropped["not_applicable"] += 1
            continue
        if audit.get("score") == 1 and audit_id not in ALWAYS_NUMERIC:
            passed.append(audit_id)
            dropped["passed_collapsed"] += 1
            continue
        audits_out[audit_id] = slim_audit(audit)

    packed = {
        "lighthouse_version": lhr.get("lighthouseVersion"),
        "url": lhr.get("finalDisplayedUrl") or lhr.get("requestedUrl"),
        "categories": {k: v.get("score") for k, v in (lhr.get("categories") or {}).items()},
        "audits": audits_out,
        "passed": sorted(passed),
    }
    if lhr.get("runWarnings"):
        packed["run_warnings"] = lhr["runWarnings"]
    return packed, dropped


# ---------------------------------------------------------------------------
# axe
# ---------------------------------------------------------------------------

def pack_axe_run(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Pack one axe result down to violations, keeping the pass counts.

    Invariant: keep `rules_passed`. It's the only thing separating "axe checked
    this template and found nothing" from "axe never ran here".
    """
    violations = []
    for violation in result.get("violations") or []:
        nodes = violation.get("nodes") or []
        violations.append({
            "id": violation.get("id"),
            "impact": violation.get("impact"),
            "help": violation.get("help"),
            "tags": [t for t in (violation.get("tags") or [])
                     if t.startswith("wcag") or t == "best-practice"],
            "node_count": len(nodes),
            "nodes": [{
                "target": n.get("target"),
                "html": (n.get("html") or "")[:MAX_AXE_HTML_CHARS],
                "failureSummary": " ".join((n.get("failureSummary") or "").split())
                                  [:MAX_AXE_SUMMARY_CHARS],
            } for n in nodes[:MAX_AXE_NODES]],
        })
        if len(nodes) > MAX_AXE_NODES:
            violations[-1]["nodes_omitted"] = len(nodes) - MAX_AXE_NODES

    packed = {
        "url": result.get("url"),
        "violations": violations,
        "rules_passed": len(result.get("passes") or []),
        "rules_incomplete": [i.get("id") for i in (result.get("incomplete") or [])],
        "rules_inapplicable": len(result.get("inapplicable") or []),
    }
    dropped = {
        "passes": len(result.get("passes") or []),
        "inapplicable": len(result.get("inapplicable") or []),
        "incomplete_node_detail": len(result.get("incomplete") or []),
    }
    return packed, dropped


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def annotate_pointers(crawl: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Stamp every distilled node with the evidence pointer that names it.

    Models built these paths themselves at first and got them wrong often enough
    to fail runs outright, so the pack precomputes them with the same function
    the harness resolves with. Model and matcher then read one identical string.

    The trade-off: building pointers is no longer something the model is tested
    on. That's fine — they're plumbing for checking evidence, not a skill under
    measurement.
    """
    stamped = 0
    for template, entry in (crawl.get("templates") or {}).items():
        root = entry.get("distilled")
        if not root:
            continue
        for pointer, node in ptr.iter_paths(template, root):
            if isinstance(node, dict):
                node[POINTER_KEY] = pointer
                stamped += 1
    return crawl, stamped


def _url_index(crawl: dict[str, Any]) -> dict[str, str]:
    """A url → template lookup. Lighthouse and axe key by URL, the pack by template."""
    index: dict[str, str] = {}
    for template, entry in (crawl.get("templates") or {}).items():
        url = entry.get("url")
        if url:
            index[url] = template
            index[url.rstrip("/")] = template
    return index


def _template_for(url: str | None, index: dict[str, str]) -> str | None:
    """The template a URL belongs to, or None if it isn't one of ours."""
    if not url:
        return None
    return index.get(url) or index.get(url.rstrip("/"))


def load_store_context(path: Path | None) -> dict[str, Any]:
    """Read the `store:` block out of a context.yaml, and only that block.

    Invariant: never let the `eval:` block through. It holds the expected score
    — the answer key — and trusting a prompt not to read half a file is not a
    control.
    """
    if path is None:
        return {}
    if yaml is None:  # pragma: no cover
        raise PackError("pyyaml is required to read context.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "store" not in data:
        raise PackError(f"{path} has no `store:` block — refusing to guess")
    return data["store"]


def build_pack(fixture_dir: Path, context_path: Path | None = None) -> dict[str, Any]:
    """Build the whole evidence pack from a fixture directory."""
    fixture_dir = Path(fixture_dir)
    crawl = json.loads((fixture_dir / "crawl.json").read_text(encoding="utf-8"))
    lighthouse_raw = json.loads((fixture_dir / "lighthouse.json").read_text(encoding="utf-8"))
    axe_raw = json.loads((fixture_dir / "axe.json").read_text(encoding="utf-8"))
    manifest_path = fixture_dir / "manifest.yaml"
    manifest_bytes = manifest_path.read_bytes() if manifest_path.exists() else b""

    index = _url_index(crawl)
    templates = list((crawl.get("templates") or {}).keys())
    crawl, pointers_stamped = annotate_pointers(crawl)

    lighthouse: dict[str, Any] = {}
    lh_dropped = {"payload_only": 0, "not_applicable": 0, "passed_collapsed": 0}
    lh_unmatched: list[str] = []
    for lhr in lighthouse_raw:
        template = _template_for(lhr.get("finalDisplayedUrl") or lhr.get("requestedUrl"), index)
        if template is None:
            lh_unmatched.append(lhr.get("requestedUrl") or "?")
            continue
        packed, dropped = pack_lighthouse_run(lhr)
        lighthouse[template] = packed
        for key, value in dropped.items():
            lh_dropped[key] += value

    axe: dict[str, Any] = {}
    axe_dropped = {"passes": 0, "inapplicable": 0, "incomplete_node_detail": 0}
    axe_unmatched: list[str] = []
    for result in axe_raw:
        template = _template_for(result.get("url"), index)
        if template is None:
            axe_unmatched.append(result.get("url") or "?")
            continue
        packed, dropped = pack_axe_run(result)
        axe[template] = packed
        for key, value in dropped.items():
            axe_dropped[key] += value

    # Say "not run" out loud rather than leaving the key missing, so the model
    # can tell absence from omission.
    for template in templates:
        if template not in lighthouse:
            lighthouse[template] = {"status": "not_run",
                                    "note": "no Lighthouse run for this template in the capture"}
        if template not in axe:
            axe[template] = {"status": "not_run",
                             "note": "no axe run for this template in the capture"}

    pack = {
        "pack": PACK_VERSION,
        "provenance": {
            "fixture_dir": fixture_dir.name,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes else None,
            "crawl_schema": crawl.get("schema"),
        },
        "store": load_store_context(context_path),
        "crawl": crawl,
        "lighthouse": lighthouse,
        "axe": axe,
        "pack_dropped": {
            "lighthouse": {
                **lh_dropped,
                "payload_only_audits": sorted(PAYLOAD_ONLY),
                "audit_detail_items_capped_at": MAX_DETAIL_ITEMS,
                "unmatched_runs": lh_unmatched,
            },
            "axe": {
                **axe_dropped,
                "violation_nodes_capped_at": MAX_AXE_NODES,
                "unmatched_runs": axe_unmatched,
            },
            "crawl": "nothing — the distilled tree passes through verbatim "
                     "(it is already the distillation layer, crawler spec §5). "
                     f"pack/v0.2 ADDS one key: every node carries `{POINTER_KEY}`, "
                     "its own evidence pointer, computed by the same function the "
                     "harness resolves with.",
            "pointers_stamped": pointers_stamped,
        },
    }
    return pack


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def pack_stats(pack: dict[str, Any]) -> dict[str, Any]:
    """Size figures for a pack, by section and in total."""
    def chars(obj: Any) -> int:
        return len(json.dumps(obj, separators=(",", ":"), default=str))

    total = chars(pack)
    return {
        "crawl_kb": round(chars(pack["crawl"]) / 1024, 1),
        "lighthouse_kb": round(chars(pack["lighthouse"]) / 1024, 1),
        "axe_kb": round(chars(pack["axe"]) / 1024, 1),
        "total_kb": round(total / 1024, 1),
        # `total_chars` is counted, `approx_tokens` is inferred from it. Both are
        # reported so a reader can recompute the second from the first.
        "total_chars": total,
        "approx_tokens": token_estimate.estimate_tokens(total),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: build a pack, print its stats, and optionally write it."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("--context", type=Path, default=None,
                        help="context.yaml — the store: block is read, eval: is not")
    parser.add_argument("-o", "--out", type=Path, default=None)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--indent", type=int, default=None,
                        help="pretty-print (costs ~25%% more tokens; default minified)")
    args = parser.parse_args(argv)

    try:
        pack = build_pack(args.fixture_dir, args.context)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stats = pack_stats(pack)
    if args.stats or not args.out:
        for key, value in stats.items():
            print(f"{key:16s} {value}")
        dropped = pack["pack_dropped"]
        print(f"{'lh dropped':16s} {dropped['lighthouse']['payload_only']} payload-only, "
              f"{dropped['lighthouse']['not_applicable']} notApplicable, "
              f"{dropped['lighthouse']['passed_collapsed']} passed→id")
        print(f"{'axe dropped':16s} {dropped['axe']['passes']} passes, "
              f"{dropped['axe']['inapplicable']} inapplicable")
        print(f"{'pointers':16s} {dropped['pointers_stamped']} nodes stamped with `{POINTER_KEY}`")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        separators = None if args.indent else (",", ":")
        args.out.write_text(
            json.dumps(pack, indent=args.indent, separators=separators, default=str),
            encoding="utf-8")
        print(f"wrote {args.out} ({stats['total_kb']} KB, {stats['total_chars']:,} chars, "
              f"~{token_estimate.thousands(stats['approx_tokens'])} tokens est.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
