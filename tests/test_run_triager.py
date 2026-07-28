"""triage/run_triager.py — the thing that makes a run reproducible.

No test here touches the network. What is worth testing is exactly what the 21
recorded runs lack: that the run file carries the model and the parameters that
produced it, and that the scorer can still read the old bare-output shape.
"""

from __future__ import annotations

import importlib.util
import json
import os
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


# --- --via claude-cli backend -----------------------------------------------
#
# This second backend exists so the pipeline can be tested without spending
# Console credits, by shelling out to the `claude` CLI on the repo owner's
# personal subscription instead of calling the SDK. No test here may touch
# the network or invoke the real CLI — the subprocess boundary is faked via
# an injected `runner` callable with the same shape as `subprocess.run`.


def test_run_meta_records_via_on_the_sdk_path(tmp_path):
    # The existing anthropic-sdk path never set `via` before this change; a
    # reader six months from now must not find it absent on either path.
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    meta = run_triager.run_meta(
        model="claude-opus-5", effort="high", max_tokens=32000,
        rendered_path=rendered, pack_path=pack,
        prompt_version="finding-triager/v1.0", started_at="2026-07-28T10:00:00+08:00")

    assert meta["via"] == "anthropic-sdk"


def test_run_meta_records_via_and_incomparability_on_the_cli_path(tmp_path):
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    meta = run_triager.run_meta(
        model="claude-opus-5", effort="high",
        rendered_path=rendered, pack_path=pack,
        prompt_version="finding-triager/v1.0", started_at="2026-07-28T10:00:00+08:00",
        via="claude-code-cli",
        system_prompt="You are being evaluated.", cli_version="2.1.218")

    assert meta["via"] == "claude-code-cli"
    assert meta["cli_version"] == "2.1.218"
    assert meta["system_prompt"] == "You are being evaluated."
    # A recorded value, not a comment — someone reading the run file must be
    # able to tell, from the file alone, what this path does and doesn't support.
    comparability = meta["comparability"]
    assert "not comparable" in comparability.lower()
    assert "max_tokens" in comparability
    assert "thinking" in comparability
    assert "1.7" in comparability or "1,700" in comparability  # ~1.7k harness tokens
    assert "effort" in comparability.lower()


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_runner(response, captured):
    def runner(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return response

    return runner


_SUCCESS_PAYLOAD = {
    "result": "OK",
    "usage": {
        "input_tokens": 2,
        "output_tokens": 3,
        "cache_creation_input_tokens": 1718,
        "cache_read_input_tokens": 0,
    },
    "modelUsage": {"claude-opus-5": {"inputTokens": 2, "outputTokens": 3}},
    "total_cost_usd": 0.00097,
    "session_id": "sess_abc123",
    "stop_reason": "end_turn",
    "num_turns": 1,
    "is_error": False,
    "subtype": "success",
}


def test_call_model_via_cli_builds_the_measured_argument_list(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), ""), captured)

    run_triager.call_model_via_cli(
        "the rendered prompt", model="claude-opus-5", effort="high",
        system_prompt="You are being evaluated.", runner=runner)

    assert captured["argv"] == [
        "claude", "-p",
        "--model", "claude-opus-5",
        "--effort", "high",
        "--tools", "",
        "--system-prompt", "You are being evaluated.",
        "--strict-mcp-config",
        "--output-format", "json",
    ]


def test_call_model_via_cli_sends_the_prompt_on_stdin_not_argv(monkeypatch):
    # A ~145k-token rendered prompt as an argv element would blow past
    # Windows' ~32k character command-line cap.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), ""), captured)

    huge_prompt = "x" * 500_000
    run_triager.call_model_via_cli(
        huge_prompt, model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    assert huge_prompt not in captured["argv"]
    assert captured["kwargs"]["input"] == huge_prompt


def test_call_model_via_cli_strips_anthropic_api_key_from_the_child_env_only(monkeypatch):
    # This is the test that protects the user's wallet: if the child process
    # sees ANTHROPIC_API_KEY, the CLI bills the Console API — the exact thing
    # this backend exists to avoid.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-reach-the-child")
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), ""), captured)

    run_triager.call_model_via_cli(
        "prompt", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    child_env = captured["kwargs"]["env"]
    assert "ANTHROPIC_API_KEY" not in child_env
    # The parent process's environment must be untouched.
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-should-not-reach-the-child"


def test_call_model_via_cli_parses_a_realistic_success_payload(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), "trust-dialog warning\n"),
        captured)

    text, usage = run_triager.call_model_via_cli(
        "prompt", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    assert text == "OK"
    assert usage["resolved_model"] == "claude-opus-5"
    assert usage["total_cost_usd"] == 0.00097
    assert usage["session_id"] == "sess_abc123"
    assert usage["num_turns"] == 1
    assert usage["input_tokens"] == 2
    assert usage["output_tokens"] == 3


def test_call_model_via_cli_raises_systemexit_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(1, "", "boom: auth failed"), captured)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_on_non_json_stdout(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, "not json at all", ""), captured)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_is_error_true(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, is_error=True, subtype="error_during_execution")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_result_missing(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = {k: v for k, v in _SUCCESS_PAYLOAD.items() if k != "result"}
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_num_turns_exceeds_one(monkeypatch):
    # Tools are off, so a multi-turn response means the harness did something
    # other than answer — the run is not a clean single completion.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, num_turns=2)
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_cli_absent_from_path(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high", system_prompt="sys")
