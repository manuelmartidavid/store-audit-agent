"""triage/pack_evidence.py — the pack is the triager's whole world.

The tests that matter here are the ones about what the packer *removes*. A
packer that silently drops the audit a finding needs makes that finding
undetectable by construction — the same shape of bug as distillation dropping
the div-button (C-01), which cost a recapture cycle to find.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "02-sabotaged"
ENTRY = ROOT / "evals" / "golden" / "02-sabotaged"

_spec = importlib.util.spec_from_file_location("pack_evidence", ROOT / "triage" / "pack_evidence.py")
pack_evidence = importlib.util.module_from_spec(_spec)
sys.modules["pack_evidence"] = pack_evidence
_spec.loader.exec_module(pack_evidence)

# Reached through the packer rather than imported separately, so this test sees
# the same module object the packer estimates with.
token_estimate = pack_evidence.token_estimate

pytestmark = pytest.mark.skipif(not FIXTURE.exists(),
                                reason="fixtures/ is gitignored; run where the capture lives")


@pytest.fixture(scope="module")
def pack():
    return pack_evidence.build_pack(FIXTURE, ENTRY / "context.yaml")


def test_pack_fits_a_single_pass(pack):
    """Capacity is not what decides granularity — but it has to be true first.

    pack/v0.2 buys per-node pointers with tokens, and the headroom left over the
    target model's context window is what this guards: if a future entry pushes
    past it, the granularity decision (one pass vs per-template) reopens on
    capacity grounds rather than determinism grounds.

    Both of this test's numbers were corrected 2026-07-28; what it guards did not
    change. The window is 1M, not the 200k this docstring used to name —
    `claude-opus-5` is a 1M-context model by default (claude-api skill,
    `shared/models.md`). And the bound is now derived rather than typed: the old
    `< 150_000` came from a 4-chars-per-token prose rule that measured 2.16x low
    on this pack, so it was nominally guarding a ceiling the pack had in fact
    already crossed. Half the window, not all of it, because the rendered prompt
    is the pack plus a template and the model's reply has to fit as well.
    """
    stats = pack_evidence.pack_stats(pack)
    window = token_estimate.CONTEXT_WINDOWS["claude-opus-5"]
    assert stats["approx_tokens"] < window // 2, stats
    # The estimate is inferred from a counted number; keep both, so a reader who
    # distrusts the ratio can redo the division rather than take it on faith.
    assert stats["total_chars"] == pytest.approx(stats["total_kb"] * 1024, rel=0.001)


def test_eval_block_never_reaches_the_prompt(pack):
    """context.yaml has a hard store:/eval: split. eval: holds the answer key."""
    encoded = json.dumps(pack)
    context = yaml.safe_load((ENTRY / "context.yaml").read_text(encoding="utf-8"))
    assert "eval" not in pack["store"]
    assert str(context["eval"]["expect"]["score"]) not in json.dumps(pack["store"])
    assert "manifest_sha256" not in encoded or pack["provenance"]["manifest_sha256"]
    # the pinned PDP url is legitimately present (it is the crawled url); the
    # expectation block is not
    assert "score_min" not in encoded
    assert "portfolio_safe" not in encoded


def test_context_without_store_block_is_a_config_error(tmp_path):
    path = tmp_path / "context.yaml"
    path.write_text("eval:\n  id: '99'\n", encoding="utf-8")
    with pytest.raises(pack_evidence.PackError):
        pack_evidence.load_store_context(path)


def test_distilled_crawl_passes_through_verbatim_except_the_pointer_key(pack):
    """Re-distilling inside the packer would re-open crawler spec §5 silently.

    pack/v0.2 adds exactly one key per node and changes nothing else. The test
    strips `@` back out and demands byte-equality with the fixture, so a packer
    that quietly started editing the tree would fail here rather than in a run.
    """
    raw = json.loads((FIXTURE / "crawl.json").read_text(encoding="utf-8"))

    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k != pack_evidence.POINTER_KEY}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    assert strip(pack["crawl"]) == raw


def test_every_node_carries_the_pointer_that_names_it(pack):
    """The model copies `@`; the harness resolves it. One string, no drift."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from crawler import pointers as ptr

    for template, entry in pack["crawl"]["templates"].items():
        if not entry.get("distilled"):
            continue
        for pointer, node in ptr.iter_paths(template, entry["distilled"]):
            assert node.get(pack_evidence.POINTER_KEY) == pointer


def test_a_pointer_read_off_the_pack_resolves_against_the_fixture(pack):
    """The whole point: the value a model copies is one the matcher accepts."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from crawler import pointers as ptr

    crawl = json.loads((FIXTURE / "crawl.json").read_text(encoding="utf-8"))
    checked = 0
    for template, entry in pack["crawl"]["templates"].items():
        if not entry.get("distilled"):
            continue
        for _, node in list(ptr.iter_paths(template, entry["distilled"]))[:40]:
            pointer = node.get(pack_evidence.POINTER_KEY)
            assert ptr.resolve(pointer, crawl) is not None, pointer
            checked += 1
    assert checked > 100


def test_every_captured_template_has_an_entry_even_without_a_run(pack):
    """Absence must be distinguishable from omission (crawler spec §4)."""
    templates = set(pack["crawl"]["templates"])
    assert set(pack["lighthouse"]) == templates
    assert set(pack["axe"]) == templates
    # the 404 probe served 503 during capture, so it has no LHR
    assert pack["lighthouse"]["404"]["status"] == "not_run"
    assert "audits" not in pack["lighthouse"]["404"]


def test_passing_audits_collapse_but_do_not_vanish(pack):
    home = pack["lighthouse"]["home"]
    assert "is-crawlable" in home["passed"]          # home is indexable
    assert home["passed"] == sorted(home["passed"])  # stable across runs


def test_a_failing_audit_keeps_its_number(pack):
    collection = pack["lighthouse"]["collection"]
    assert collection["audits"]["is-crawlable"]["score"] == 0
    cls = collection["audits"]["cumulative-layout-shift"]
    assert cls["numericValue"] > 0.25               # MC-106, the CLS plant


def test_core_metrics_keep_their_number_even_when_green(pack):
    """The rubric's thresholds are numeric, so a green metric is still evidence."""
    home = pack["lighthouse"]["home"]
    assert "cumulative-layout-shift" in home["audits"]
    assert home["audits"]["cumulative-layout-shift"]["score"] == 1
    assert home["audits"]["cumulative-layout-shift"]["numericValue"] == 0
    assert "cumulative-layout-shift" not in home["passed"]


def test_the_boundary_pair_survives_packing(pack):
    """MC-105/MC-107 straddle LCP 4.0s. Losing either number collapses the pair."""
    home = pack["lighthouse"]["home"]["audits"]["largest-contentful-paint"]["numericValue"]
    pdp = pack["lighthouse"]["pdp"]["audits"]["largest-contentful-paint"]["numericValue"]
    assert 2500 < home < 4000 < pdp


def test_axe_violations_survive_and_counts_are_recorded(pack):
    collection = pack["axe"]["collection"]
    rules = {v["id"] for v in collection["violations"]}
    assert "color-contrast" in rules                 # MC-104
    assert collection["rules_passed"] > 0            # 'axe ran here' ≠ 'axe was not packed'
    assert isinstance(collection["rules_incomplete"], list)


def test_axe_nodes_are_capped_but_the_count_is_not(pack):
    for template, entry in pack["axe"].items():
        for violation in entry.get("violations", []):
            assert len(violation["nodes"]) <= pack_evidence.MAX_AXE_NODES
            if violation["node_count"] > pack_evidence.MAX_AXE_NODES:
                assert violation["nodes_omitted"] == \
                    violation["node_count"] - pack_evidence.MAX_AXE_NODES


def test_dropped_accounting_is_present_and_names_what_it_dropped(pack):
    dropped = pack["pack_dropped"]["lighthouse"]
    assert dropped["payload_only"] > 0
    assert dropped["passed_collapsed"] > 0
    assert set(dropped["payload_only_audits"]) == set(pack_evidence.PAYLOAD_ONLY)
    assert not dropped["unmatched_runs"]
    assert not pack["pack_dropped"]["axe"]["unmatched_runs"]


def test_payload_only_audits_carry_no_conclusion():
    """The deny-list must never grow to include an audit a finding could cite."""
    citable = {"largest-contentful-paint", "cumulative-layout-shift", "is-crawlable",
               "color-contrast", "meta-description", "document-title", "image-alt",
               "label", "link-name", "button-name", "uses-responsive-images",
               "modern-image-formats", "total-byte-weight", "render-blocking-resources"}
    assert not (pack_evidence.PAYLOAD_ONLY & citable)


def test_packing_is_deterministic(pack):
    """Determinism is the whole point of fixtures (crawler spec §10.6)."""
    again = pack_evidence.build_pack(FIXTURE, ENTRY / "context.yaml")
    assert json.dumps(again, sort_keys=True, default=str) == \
        json.dumps(pack, sort_keys=True, default=str)


def test_slim_audit_drops_boilerplate_but_keeps_the_verdict():
    audit = {"id": "x", "title": "Document does not have a meta description",
             "description": "a paragraph of static boilerplate " * 20,
             "score": 0, "scoreDisplayMode": "binary"}
    out = pack_evidence.slim_audit(audit)
    assert out["title"] == audit["title"]
    assert out["score"] == 0
    assert "description" not in out


def test_slim_audit_caps_detail_items_and_says_how_many_it_dropped():
    audit = {"title": "t", "score": 0,
             "details": {"items": [{"n": i} for i in range(12)]}}
    out = pack_evidence.slim_audit(audit)
    assert len(out["details_items"]) == pack_evidence.MAX_DETAIL_ITEMS
    assert out["details_items_omitted"] == 12 - pack_evidence.MAX_DETAIL_ITEMS
