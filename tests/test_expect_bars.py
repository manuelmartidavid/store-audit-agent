"""Precision bars — the ones the harness never had.

Recall has six bars; precision has none. `unlabeled` findings are counted and
gate nothing, so a run emitting 24 findings of which 7 are plausible-but-wrong
passes everything. The project's stated top risk is a plausible-but-wrong claim
reaching a client.

The gates are declared per entry (`expect.gates`) rather than inferred, because
turning them on for entry 02 retroactively would re-judge 18 recorded runs on a
bar they were never measured against — a decision for a person, not for a
default.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)


def _findings(count: int, severity: str = "low") -> list[dict]:
    return [{"id": f"F-{n:02d}", "severity": severity, "category": "seo",
             "confidence": "high", "templates": ["home"]} for n in range(count)]


def test_no_gates_declared_means_no_precision_bars():
    bars = eval_triage.expect_bars(_findings(40), {"score": 10}, {"max_findings": 3})
    assert bars == {}


def test_max_findings_gate():
    expect = {"gates": ["max_findings"], "max_findings": 3}
    assert eval_triage.expect_bars(_findings(3), {"score": 95}, expect)["max_findings_respected"]
    assert not eval_triage.expect_bars(_findings(4), {"score": 95}, expect)["max_findings_respected"]


def test_findings_above_medium_gate():
    expect = {"gates": ["findings_above_medium"], "findings_above_medium": 0}
    clean = eval_triage.expect_bars(_findings(3, "medium"), {"score": 95}, expect)
    assert clean["findings_above_medium_respected"]
    noisy = eval_triage.expect_bars(_findings(1, "high"), {"score": 95}, expect)
    assert not noisy["findings_above_medium_respected"]


def test_score_range_gate_including_the_blocked_store():
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": 100}
    assert eval_triage.expect_bars([], {"score": 95}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 60}, expect)["score_within_expect"]

    blocked = {"gates": ["score_range"], "score_min": None, "score_max": None}
    assert eval_triage.expect_bars([], {"score": None}, blocked)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 0}, blocked)["score_within_expect"]


def test_entry_02_declares_no_gates_and_says_why():
    text = (ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["eval"]["expect"]["gates"] == []
    assert "18 recorded runs" in text


def test_entry_05_gates_max_findings():
    data = yaml.safe_load(
        (ROOT / "evals" / "golden" / "05-password-gated" / "context.yaml").read_text(encoding="utf-8"))
    assert "max_findings" in data["eval"]["expect"]["gates"]


# ---------------------------------------------------------------------------
# Finding 1 — a one-sided score range must not raise, on either side
# ---------------------------------------------------------------------------

def test_score_range_lower_bound_only():
    # score_max present and explicitly null: "no ceiling", not "unset". Entry
    # 01's own pass condition is exactly this shape (rubric §5: score >= 90).
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": None}
    assert eval_triage.expect_bars([], {"score": 90}, expect)["score_within_expect"]
    assert eval_triage.expect_bars([], {"score": 100}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 89}, expect)["score_within_expect"]


def test_score_range_upper_bound_only():
    # score_min present and explicitly null: "no floor", not "unset".
    expect = {"gates": ["score_range"], "score_min": None, "score_max": 90}
    assert eval_triage.expect_bars([], {"score": 90}, expect)["score_within_expect"]
    assert eval_triage.expect_bars([], {"score": 0}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 91}, expect)["score_within_expect"]


# ---------------------------------------------------------------------------
# Finding 2 — a declared gate with no value, or no known name, must not pass
# silently
# ---------------------------------------------------------------------------

def test_declared_gate_with_missing_value_raises():
    expect = {"gates": ["max_findings"]}  # max_findings never set
    with pytest.raises(SystemExit, match="max_findings"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)


def test_declared_findings_above_medium_with_missing_value_raises():
    expect = {"gates": ["findings_above_medium"]}
    with pytest.raises(SystemExit, match="findings_above_medium"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)


def test_declared_score_range_with_missing_bounds_raises():
    # gates declares score_range but never sets score_min/score_max at all —
    # distinct from entry 05's blocked-store case, which sets both to null
    # explicitly.
    expect = {"gates": ["score_range"]}
    with pytest.raises(SystemExit, match="score_range"):
        eval_triage.expect_bars([], {"score": 95}, expect)


def test_unknown_gate_name_raises():
    expect = {"gates": ["max_findigns"], "max_findigns": 3}  # typo'd gate name
    with pytest.raises(SystemExit, match="not a known gate"):
        eval_triage.expect_bars(_findings(1), {"score": 95}, expect)


# ---------------------------------------------------------------------------
# The wiring, which every test above this line went around
#
# `expect_bars()` was called directly nine times and never once through
# `evaluate()`. Two lines connect it to reality — `bars.update(expect_bars(...))`
# in `evaluate()` and the block in `main()` that reads `eval.expect` out of the
# entry's context.yaml — and both could be deleted with the whole suite green.
# A bar that passes without running is worse than a bar that fails; a bar whose
# wiring is untested is the same failure one level out.
#
# The capture below is built here rather than read from `fixtures/`, which is
# gitignored: a wiring test that skips on a fresh clone reports coverage it does
# not have.
# ---------------------------------------------------------------------------

PRECISION_BARS = {"max_findings_respected", "findings_above_medium_respected",
                  "score_within_expect"}


def _capture(tmp_path: Path) -> Path:
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "crawl.json").write_text(json.dumps({
        "status": "ok",
        "templates": {"home": {"url": "https://example.test/",
                               "distilled": {"tag": "html", "children": []}}},
    }), encoding="utf-8")
    (capture / "lighthouse.json").write_text("[]", encoding="utf-8")
    (capture / "axe.json").write_text("[]", encoding="utf-8")
    return capture


def _output(count: int, severity: str = "low") -> dict:
    """A schema-valid run whose every pointer resolves, so only the gates move."""
    return {"schema": "triage/v0.1", "findings": [
        {"id": f"F-{n:02d}", "title": "Home hero image is oversized",
         "category": "seo", "templates": ["home"], "severity": severity,
         "effort": "small", "confidence": "high", "evidence": ["crawl:home"],
         "instances": {"home": 1}, "severity_rationale": "rubric §1 as labeled"}
        for n in range(count)]}


def test_a_declared_gate_reaches_the_bars_through_evaluate(tmp_path):
    """Declared, and failing when it should — not merely present in the dict."""
    fixture = eval_triage.Fixture(_capture(tmp_path))
    expect = {"gates": ["max_findings"], "max_findings": 3}

    within = eval_triage.evaluate(_output(3), {}, fixture, expect=expect)
    assert within["bars"]["max_findings_respected"] is True
    assert within["passed"]

    over = eval_triage.evaluate(_output(4), {}, fixture, expect=expect)
    assert over["bars"]["max_findings_respected"] is False
    assert not over["passed"], "a failed precision bar must fail the run, not just report"


def test_the_score_gate_is_checked_against_evaluates_own_composite(tmp_path):
    """The bar reads the score `evaluate()` computed, not one handed to it."""
    fixture = eval_triage.Fixture(_capture(tmp_path))
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": 100}

    clean = eval_triage.evaluate(_output(2, "low"), {}, fixture, expect=expect)
    assert clean["composite"]["score"] == 98
    assert clean["bars"]["score_within_expect"] is True

    heavy = eval_triage.evaluate(_output(2, "critical"), {}, fixture, expect=expect)
    assert heavy["composite"]["score"] == 75          # 30 penalties, capped at 25
    assert heavy["bars"]["score_within_expect"] is False
    assert not heavy["passed"]


def test_no_precision_bar_appears_when_expect_is_omitted(tmp_path):
    """The default is silence, not a bar reported green having checked nothing."""
    fixture = eval_triage.Fixture(_capture(tmp_path))
    result = eval_triage.evaluate(_output(12), {}, fixture)
    assert not PRECISION_BARS & set(result["bars"])
    assert result["passed"]


def test_entry_02s_empty_gates_list_produces_no_precision_bar(tmp_path):
    """Entry 02 records `expect` values and gates none of them, deliberately.

    Its `max_findings` would fail the 12-finding run below if `gates: []` were
    read as "all of them" — which is exactly the accident that would re-judge 18
    recorded runs against a bar they were never measured on.
    """
    context = yaml.safe_load(
        (ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml").read_text(encoding="utf-8"))
    expect = context["eval"]["expect"]
    assert expect["gates"] == [] and expect.get("max_findings") is not None

    fixture = eval_triage.Fixture(_capture(tmp_path))
    result = eval_triage.evaluate(_output(12), {}, fixture, expect=expect)
    assert not PRECISION_BARS & set(result["bars"])


def test_main_carries_the_entrys_gates_from_context_yaml_into_the_bars(tmp_path, capsys):
    """The second untested line: `main()` reading `eval.expect` and passing it on.

    End to end through the CLI, because that is the only path a recorded score
    ever takes.
    """
    capture = _capture(tmp_path)
    (capture / "manifest.yaml").write_text("crawler_version: 0.2.0\n", encoding="utf-8")
    digest = hashlib.sha256((capture / "manifest.yaml").read_bytes()).hexdigest()

    entry = tmp_path / "entry"
    (entry / "expected").mkdir(parents=True)
    (entry / "expected" / "findings.md").write_text("# labels\n", encoding="utf-8")
    (entry / "context.yaml").write_text(
        "eval:\n"
        "  fixtures:\n"
        f'    manifest_sha256: "{digest}"\n'
        "  expect:\n"
        "    max_findings: 1\n"
        "    gates: [max_findings]\n", encoding="utf-8")

    run = tmp_path / "run.json"
    run.write_text(json.dumps(_output(2)), encoding="utf-8")

    code = eval_triage.main([str(run), "--entry", str(entry), "--fixtures", str(capture),
                             "--prompt-version", "finding-triager/v1.0",
                             "--pack-version", "pack/v0.2"])
    printed = capsys.readouterr().out
    assert "max_findings_respected=False" in printed
    assert code == 1

    # The header line's pin-status annotations (decision: "silence reads as
    # verification") — display-only, but a pin printed without its status
    # invites the reader to assume the strongest reading available. This is
    # what stops that header from silently reverting to its pre-fix, unstatused
    # format: `prompt_pin` is always "exists", `fixture_pin` is "matched" here
    # (the entry pins a manifest hash and does not derive it after labeling),
    # and both `pack_pin` and `harness_pin` are "asserted" — two independent
    # pins sharing one word, so a count catches either one going missing where
    # a plain substring check would not.
    assert "(exists)" in printed
    assert "(matched)" in printed
    assert printed.count("(asserted)") == 2

    # …and the same run under an entry that declares no gate is silent about it.
    (entry / "context.yaml").write_text(
        "eval:\n  fixtures:\n"
        f'    manifest_sha256: "{digest}"\n'
        "  expect:\n    max_findings: 1\n    gates: []\n", encoding="utf-8")
    code = eval_triage.main([str(run), "--entry", str(entry), "--fixtures", str(capture),
                             "--prompt-version", "finding-triager/v1.0",
                             "--pack-version", "pack/v0.2"])
    printed = capsys.readouterr().out
    assert "max_findings_respected" not in printed
    assert code == 0
