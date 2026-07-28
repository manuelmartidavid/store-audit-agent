"""triage/run_triager.py — the thing that makes a run reproducible.

No test here touches the network. What is worth testing is exactly what the 21
recorded runs lack: that the run file carries the model and the parameters that
produced it, and that the scorer can still read the old bare-output shape.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_triager = _load("run_triager", "triage/run_triager.py")
eval_triage = _load("eval_triage", "triage/eval_triage.py")


def test_run_meta_records_the_model_and_every_parameter(tmp_path):
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    meta = run_triager.run_meta(
        model="claude-opus-5", effort="high", max_tokens=32000,
        rendered_path=rendered, pack_path=pack,
        prompt_version="finding-triager/v1.0", started_at="2026-07-28T10:00:00+08:00")

    # "pack_version" is deliberately absent: provenance() already records the
    # pack version, with a pack_pin field saying whether it was verified or
    # merely asserted. A second, independently-sourced pack version here would
    # reintroduce the unreconciled-duplicate defect task 5 removed.
    for key in ("model", "effort", "thinking", "max_tokens", "prompt_version",
                "rendered_sha256", "pack_sha256", "started_at",
                "sdk_version"):
        assert key in meta, key
    assert meta["model"] == "claude-opus-5"
    assert len(meta["rendered_sha256"]) == 64
    # Opus 5 rejects temperature/top_p/top_k, so there is no sampler to record —
    # say so in the record rather than leaving a reader to wonder.
    assert meta["sampling"] == "not applicable (claude-opus-5 rejects temperature/top_p/top_k)"


def test_extract_json_tolerates_a_fenced_response():
    payload = '{"schema": "triage/v0.1", "findings": []}'
    assert run_triager.extract_json(payload)["schema"] == "triage/v0.1"
    assert run_triager.extract_json(f"```json\n{payload}\n```")["schema"] == "triage/v0.1"
    with pytest.raises(SystemExit):
        run_triager.extract_json("I could not produce JSON.")


def test_extract_json_does_not_splice_a_second_fenced_block():
    # A greedy capture spans from the first `{` to the *last* `}` before the
    # final fence, swallowing a second block and the prose between them into
    # one invalid document. The contract is one JSON object and no prose —
    # tolerate a single fence, and return the first object intact.
    first = {"schema": "triage/v0.1", "findings": []}
    reply = (
        '```json\n{"schema": "triage/v0.1", "findings": []}\n```\n'
        "Unrelated prose the model should not have emitted.\n"
        '```json\n{"schema": "triage/v0.2", "findings": ["decoy"]}\n```'
    )
    assert run_triager.extract_json(reply) == first


def test_the_scorer_reads_both_run_shapes(tmp_path):
    bare = tmp_path / "bare.json"
    bare.write_text('{"schema": "triage/v0.1", "findings": []}', encoding="utf-8")
    output, meta = eval_triage.load_run_output(bare)
    assert output["schema"] == "triage/v0.1"
    assert meta is None

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({
        "run_meta": {"model": "claude-opus-5"},
        "output": {"schema": "triage/v0.1", "findings": []},
    }), encoding="utf-8")
    output, meta = eval_triage.load_run_output(wrapped)
    assert output["schema"] == "triage/v0.1"
    assert meta["model"] == "claude-opus-5"


def test_the_21_recorded_runs_still_load():
    for path in sorted((ROOT / "runs").glob("*.json")):
        output, meta = eval_triage.load_run_output(path)
        assert output.get("schema") == "triage/v0.1", path.name
        assert meta is None, f"{path.name} was rewritten — recorded runs are frozen"
