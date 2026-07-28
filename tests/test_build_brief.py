"""triage/build_brief.py — the script half of the narrator layer.

Everything here is arithmetic and set logic. The narrator downstream makes
judgments; this file must not, and the tests are written to catch it starting to.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("build_brief", ROOT / "triage" / "build_brief.py")
build_brief = importlib.util.module_from_spec(_spec)
sys.modules["build_brief"] = build_brief
_spec.loader.exec_module(build_brief)


def finding(**kw):
    base = {"id": "F-01", "title": "t", "category": "performance", "templates": ["home"],
            "severity": "high", "effort": "small", "confidence": "high",
            "evidence": ["lighthouse:audits/largest-contentful-paint"],
            "instances": {"home": 1}, "severity_rationale": "rubric §1"}
    base.update(kw)
    return base


def pack(status="complete", **store):
    base_store = {"platform": "shopify", "vertical": "collectibles", "market": "CA",
                  "currency": "CAD", "password_env": "TSCC_STOREFRONT_PASSWORD",
                  "aov": 85, "monthly_sessions": "<10k", "mobile_share": 0.7,
                  "catalog_size": "50-500", "notes": "n"}
    base_store.update(store)
    return {"pack": "pack/v0.2", "store": base_store, "crawl": {"status": status},
            "provenance": {"manifest_sha256": "deadbeef"}}


# --- the bucket split -------------------------------------------------------

def test_low_confidence_goes_to_needs_verification():
    """Rubric §3: reported, scores zero, out of the ranked roadmap."""
    road, needs, noted = build_brief.split_buckets([finding(confidence="low")])
    assert [f["id"] for f in needs] == ["F-01"]
    assert road == [] and noted == []


def test_null_severity_goes_to_noted():
    """MC-113's shape — security, no §1 clause applies, but a client must be told."""
    road, needs, noted = build_brief.split_buckets(
        [finding(category="security", severity=None, effort=None)])
    assert [f["id"] for f in noted] == ["F-01"]
    assert road == [] and needs == []


def test_low_confidence_wins_over_null_severity():
    """The two conditions co-occur and the precedence is fixed (narrator-io §2.1).
    Rubric §3 does not carve out null severity, so needs_verification takes it."""
    road, needs, noted = build_brief.split_buckets(
        [finding(category="security", severity=None, effort=None, confidence="low")])
    assert [f["id"] for f in needs] == ["F-01"]
    assert noted == []


# --- truncation -------------------------------------------------------------

def test_per_template_ceiling_admits_eight_and_overflows_the_ninth():
    ranked = [finding(id=f"F-{i:02d}", templates=["pdp"]) for i in range(1, 10)]
    admitted, overflow = build_brief.truncate(ranked)
    assert len(admitted) == 8
    assert overflow == 1


def test_a_saturated_template_does_not_block_an_unrelated_finding():
    """The walk continues past a full template rather than stopping — otherwise
    one saturated page silently swallows findings on every page after it."""
    ranked = ([finding(id=f"F-{i:02d}", templates=["pdp"]) for i in range(1, 10)]
              + [finding(id="F-99", templates=["cart"])])
    admitted, overflow = build_brief.truncate(ranked)
    assert "F-99" in [f["id"] for f in admitted]
    assert overflow == 1


def test_a_finding_is_counted_against_every_template_it_names():
    """Rollup means one finding can occupy a slot on four pages at once."""
    ranked = [finding(id=f"F-{i:02d}", templates=["home", "pdp"]) for i in range(1, 10)]
    admitted, overflow = build_brief.truncate(ranked)
    assert len(admitted) == 8 and overflow == 1


def test_total_ceiling_binds_at_twenty_five():
    ranked = [finding(id=f"F-{i:02d}", templates=[f"t{i}"]) for i in range(1, 31)]
    admitted, overflow = build_brief.truncate(ranked)
    assert len(admitted) == 25 and overflow == 5


# --- the store block --------------------------------------------------------

def test_password_env_never_reaches_the_brief():
    """It names a secret and has no narrative use (decision 8)."""
    block = build_brief.store_block(pack()["store"], blocked=False)
    assert "password_env" not in block


def test_platform_is_dropped_on_a_blocked_crawl():
    """The pack carries it verbatim from context.yaml, but the crawler reports no
    platform on a blocked crawl by design, and MNC-003 forbids the string. Handing
    it over and then failing the model for using it would be entrapment."""
    assert "platform" not in build_brief.store_block(pack()["store"], blocked=True)
    assert build_brief.store_block(pack()["store"], blocked=False)["platform"] == "shopify"


# --- the whole brief --------------------------------------------------------

def test_a_blocked_crawl_produces_an_empty_brief_that_says_so():
    brief = build_brief.build_brief({"schema": "triage/v0.1", "findings": []},
                                    pack(status="blocked"))
    assert brief["schema"] == "brief/v0.1"
    assert brief["store_status"] == "INACCESSIBLE"
    assert brief["roadmap"] == [] and brief["needs_verification"] == [] and brief["noted"] == []
    assert brief["overflow_count"] == 0


def test_findings_pass_through_verbatim():
    """Re-bucketed and re-ordered, never rewritten — the composer reads triage
    fields off the brief."""
    src = finding(severity_rationale="§1 high: LCP > 4.0s on a revenue template")
    brief = build_brief.build_brief({"schema": "triage/v0.1", "findings": [src]}, pack())
    assert brief["roadmap"][0] == src


def test_the_brief_carries_no_score_and_no_band():
    """The narrator emits no numbers; handing it the composite hands it one to quote."""
    brief = build_brief.build_brief({"schema": "triage/v0.1", "findings": [finding()]}, pack())
    assert "score" not in brief and "band" not in brief
