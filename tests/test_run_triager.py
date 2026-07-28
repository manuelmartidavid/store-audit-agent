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


_FROZEN_RUN_NAMES = frozenset(
    [f"v0.{minor}-run{n}" for minor in range(1, 7) for n in (1, 2, 3)]
    + [f"05-v1.0-run{n}" for n in (1, 2, 3)])


def test_the_21_frozen_runs_are_still_bare_and_none_are_missing():
    """The 21 runs recorded as interactive agent sessions (before
    `triage/run_triager.py` existed) are provenance, not output — their bytes
    are the evidence that nothing rewrote them into a newer shape. Runs the
    runner itself produces (e.g. v1.0-cli-run1.json) are *supposed* to be
    wrapped in `{run_meta, output}`; asserting bareness across the whole
    directory was catching the wrapper doing its job, not a regression. So
    this test pins bareness to the frozen 21 by name, and separately requires
    the recorded set be exactly that size — deleting one of the 21 must fail
    this test just as loudly as rewriting one does.
    """
    frozen = {name: ROOT / "runs" / f"{name}.json" for name in _FROZEN_RUN_NAMES}
    assert len(frozen) == 21
    for name, path in sorted(frozen.items()):
        assert path.is_file(), f"{name}.json is missing from runs/ — the frozen set changed"
        output, meta = eval_triage.load_run_output(path)
        assert output.get("schema") == "triage/v0.1", name
        assert meta is None, f"{name}.json was rewritten — recorded runs are frozen"


def test_every_other_run_file_still_loads_a_valid_triage_output():
    # Anything in runs/*.json outside the frozen 21 is allowed — expected,
    # even — to be wrapped by run_triager.py. But "allowed to be wrapped"
    # isn't "allowed to be garbage": a malformed new run file should still
    # fail somewhere, not slide through unnoticed just because it's exempt
    # from the bareness rule above.
    other_paths = [
        path for path in sorted((ROOT / "runs").glob("*.json"))
        if path.stem not in _FROZEN_RUN_NAMES
    ]
    assert other_paths, "expected at least one non-frozen run file (e.g. a runner-produced run)"
    for path in other_paths:
        output, _meta = eval_triage.load_run_output(path)
        assert output.get("schema") == "triage/v0.1", path.name


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


@pytest.fixture(autouse=True)
def _no_real_subprocess(monkeypatch):
    """Belt and braces for finding 6: every test in this module injects a
    fake `runner`, but nothing stopped a *future* test from forgetting to.
    Before this fixture, that mistake would silently spend the operator's
    subscription (or worse, hang waiting on real stdin). Replace every seam
    a real spawn could go through — the module-level `_RUNNER` indirection
    that `cli_version`/`call_model_via_cli` fall back to when no `runner=` is
    passed, and `subprocess.run`/`Popen` themselves for any future code that
    calls them directly — with something that fails loudly instead.
    """
    def _boom(*args, **kwargs):
        raise AssertionError(
            "a test in test_run_triager.py reached a real subprocess spawn — "
            "inject a fake `runner` instead")

    monkeypatch.setattr(run_triager, "_RUNNER", _boom)
    monkeypatch.setattr(run_triager.subprocess, "run", _boom)
    monkeypatch.setattr(run_triager.subprocess, "Popen", _boom)


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
    # stdout is deliberately *valid* JSON here (unlike a naive version of this
    # test) — with empty stdout, json.loads("") would raise on its own and
    # this test would pass even if the returncode guard were deleted
    # entirely. Valid JSON forces the returncode check itself to be what
    # raises.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(1, json.dumps(_SUCCESS_PAYLOAD), "boom: auth failed"), captured)

    with pytest.raises(SystemExit, match="exited 1"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_on_non_json_stdout(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, "not json at all", ""), captured)

    with pytest.raises(SystemExit, match="not JSON"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_is_error_true(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, is_error=True, subtype="error_during_execution")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit, match="is_error=true"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_result_missing(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = {k: v for k, v in _SUCCESS_PAYLOAD.items() if k != "result"}
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit, match="no 'result' field"):
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

    with pytest.raises(SystemExit, match="not 1"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_cli_absent_from_path(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit, match="not on PATH"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high", system_prompt="sys")


# --- finding 1: resolved_model must be read back, never fabricated ----------
#
# `next(iter(model_usage), model)` used to fall back to the *requested*
# model whenever modelUsage was absent, empty, or renamed by a CLI update —
# indistinguishable from a value actually read back out of what ran. That
# laundered the request into the answer, defeating the one field that exists
# to catch a silent model substitution. It also picked an arbitrary key
# silently if modelUsage ever held more than one. Both must now fail loudly
# instead of recording a plausible-looking guess.

def test_call_model_via_cli_records_the_model_actually_read_back_even_if_different(monkeypatch):
    # If the CLI silently resolves to a different model than requested, the
    # record must show what actually ran — not the one asked for.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, modelUsage={
        "claude-opus-5-20260101": {"inputTokens": 2, "outputTokens": 3},
    })
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    _, usage = run_triager.call_model_via_cli(
        "prompt", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    assert usage["resolved_model"] == "claude-opus-5-20260101"


def test_call_model_via_cli_raises_systemexit_when_model_usage_is_empty(monkeypatch):
    # Falling back to the *requested* model here would fabricate a read-back
    # that never happened — indistinguishable from one genuinely confirmed.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, modelUsage={})
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit, match="modelUsage"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


def test_call_model_via_cli_raises_systemexit_when_model_usage_has_multiple_keys(monkeypatch):
    # `next(iter(...))` on a multi-key dict silently picks an arbitrary
    # entry — just as unaccountable as fabricating one from the request.
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, modelUsage={
        "claude-opus-5": {"inputTokens": 2, "outputTokens": 1},
        "claude-haiku-5": {"inputTokens": 0, "outputTokens": 2},
    })
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    with pytest.raises(SystemExit, match="modelUsage"):
        run_triager.call_model_via_cli(
            "prompt", model="claude-opus-5", effort="high",
            system_prompt="sys", runner=runner)


# --- finding 2: stdin/stdout must be UTF-8, never the locale codec ----------
#
# text=True with no encoding= uses locale.getpreferredencoding(), which is
# cp1252 on this machine. Every rendered triager prompt contains U+2264
# ('≤'), unencodable in cp1252, so a real run would die on stdin before the
# CLI is ever reached — and cp1252-decoded UTF-8 stdout would either raise or
# silently mojibake a measured artifact. These tests assert the encoding
# actually handed to the runner, since the real subprocess can't be exercised.

def test_call_model_via_cli_passes_utf8_encoding_not_the_locale_codec(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), ""), captured)

    run_triager.call_model_via_cli(
        "prompt containing ≤", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    assert captured["kwargs"]["encoding"] == "utf-8"


def test_cli_version_passes_utf8_encoding_not_the_locale_codec():
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, "2.1.218", ""), captured)

    run_triager.cli_version(runner=runner)

    assert captured["kwargs"]["encoding"] == "utf-8"


# --- finding 4: the env strip must cover every child this module spawns ----

def test_cli_version_strips_anthropic_api_key_from_its_own_child_env(monkeypatch):
    # cli_version() spawns a child too (`claude --version`) — the
    # wallet-protecting strip must not be applied to only one of the two
    # children main() can spawn.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-reach-the-child")
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, "2.1.218", ""), captured)

    run_triager.cli_version(runner=runner)

    assert "ANTHROPIC_API_KEY" not in captured["kwargs"]["env"]
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-should-not-reach-the-child"


# --- finding 9 (env half): the strip must cover the whole billing-routing set

def test_call_model_via_cli_strips_the_full_billing_routing_env_set(monkeypatch):
    # ANTHROPIC_API_KEY is not the only var that can route a child's billing
    # somewhere other than the operator's own subscription.
    for name, value in [
        ("ANTHROPIC_API_KEY", "sk-ant-x"),
        ("ANTHROPIC_AUTH_TOKEN", "tok-x"),
        ("ANTHROPIC_BASE_URL", "https://evil.example/v1"),
        ("CLAUDE_CODE_USE_BEDROCK", "1"),
        ("CLAUDE_CODE_USE_VERTEX", "1"),
    ]:
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}
    runner = _fake_runner(
        _FakeCompletedProcess(0, json.dumps(_SUCCESS_PAYLOAD), ""), captured)

    run_triager.call_model_via_cli(
        "prompt", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    child_env = captured["kwargs"]["env"]
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                 "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        assert name not in child_env, name


# --- finding 5: usage must be recorded wholesale, not a hand-picked slice --

def test_call_model_via_cli_records_the_full_usage_block_not_a_projection(monkeypatch):
    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    payload = dict(_SUCCESS_PAYLOAD, usage={
        "input_tokens": 2,
        "output_tokens": 3,
        "cache_creation_input_tokens": 1718,
        "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 1718, "ephemeral_1h_input_tokens": 0},
        "server_tool_use": {"web_search_requests": 0},
        "service_tier": "standard",
    })
    captured = {}
    runner = _fake_runner(_FakeCompletedProcess(0, json.dumps(payload), ""), captured)

    _, usage = run_triager.call_model_via_cli(
        "prompt", model="claude-opus-5", effort="high",
        system_prompt="sys", runner=runner)

    # Nothing from the CLI's usage block is dropped, even fields this module
    # never anticipated (a future CLI version could add more).
    assert usage["raw"] == payload["usage"]
    assert usage["raw"]["cache_creation"]["ephemeral_5m_input_tokens"] == 1718
    assert usage["raw"]["server_tool_use"] == {"web_search_requests": 0}
    assert usage["raw"]["service_tier"] == "standard"
    # The flattened convenience fields (main()'s summary print reads these)
    # still sit alongside it, not in place of it.
    assert usage["input_tokens"] == 2
    assert usage["output_tokens"] == 3


# --- finding 6: the runner seam must be patchable via a module attribute ---

def test_runner_falls_back_to_the_module_level_indirection_when_omitted(monkeypatch):
    # Proves the fix for finding 6: `runner=subprocess.run` as a *default
    # parameter value* would have baked in the original function object at
    # def time, immune to `monkeypatch.setattr(run_triager, "_RUNNER", ...)`.
    # Looking `_RUNNER` up inside the function body means this patch is seen.
    captured = {}
    monkeypatch.setattr(
        run_triager, "_RUNNER",
        _fake_runner(_FakeCompletedProcess(0, "2.1.218", ""), captured))

    result = run_triager.cli_version()  # no runner= passed

    assert result == "2.1.218"
    assert captured["argv"] == ["claude", "--version"]


def test_forgetting_to_inject_a_runner_fails_loudly_via_the_autouse_fixture():
    # This module's autouse `_no_real_subprocess` fixture (above) patches
    # `_RUNNER` to something that raises. A test that forgot to pass its own
    # `runner=` — the exact mistake finding 6 is about — gets a loud,
    # immediate failure here instead of a real subprocess spawn.
    with pytest.raises(AssertionError, match="real subprocess"):
        run_triager.cli_version()


# --- finding 3 & 7: main()'s --via claude-cli wiring -------------------------

def test_main_checks_path_before_calling_cli_version(tmp_path, monkeypatch):
    # Before finding 3's fix, main() called cli_version() while building
    # run_meta, ahead of call_model_via_cli's own shutil.which guard — so an
    # absent CLI surfaced as a raw FileNotFoundError, not this SystemExit.
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    monkeypatch.setattr(run_triager.shutil, "which", lambda name: None)

    def _boom_if_called():
        raise AssertionError("cli_version() must not run when claude is not on PATH")
    monkeypatch.setattr(run_triager, "cli_version", _boom_if_called)

    with pytest.raises(SystemExit, match="not on PATH"):
        run_triager.main([
            str(rendered), "--pack", str(pack),
            "--prompt-version", "finding-triager/v1.0",
            "-o", str(tmp_path / "out.json"), "--via", "claude-cli",
            "--env-file", str(tmp_path / "does-not-exist.env"),
        ])


def test_main_wires_the_cli_backend_and_folds_usage_onto_meta(tmp_path, monkeypatch):
    # No test called main() or cli_version() before this — the --via
    # dispatch, the folding of total_cost_usd/session_id/num_turns onto
    # meta, and the final print's dependence on usage["input_tokens"] were
    # all unexercised.
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")
    out = tmp_path / "out.json"

    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(run_triager, "cli_version", lambda: "2.1.218")

    def _fake_call_model_via_cli(prompt, *, model, effort, system_prompt):
        return (
            '{"schema": "triage/v0.1", "findings": []}',
            {
                "input_tokens": 2, "output_tokens": 3, "raw": {"input_tokens": 2},
                "resolved_model": "claude-opus-5", "total_cost_usd": 0.001,
                "session_id": "sess_x", "num_turns": 1, "stop_reason": "end_turn",
            },
        )
    monkeypatch.setattr(run_triager, "call_model_via_cli", _fake_call_model_via_cli)

    rc = run_triager.main([
        str(rendered), "--pack", str(pack),
        "--prompt-version", "finding-triager/v1.0",
        "-o", str(out), "--via", "claude-cli",
        "--env-file", str(tmp_path / "does-not-exist.env"),
    ])

    assert rc == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["run_meta"]["via"] == "claude-code-cli"
    assert record["run_meta"]["cli_version"] == "2.1.218"
    assert record["run_meta"]["resolved_model"] == "claude-opus-5"
    assert record["run_meta"]["total_cost_usd"] == 0.001
    assert record["run_meta"]["session_id"] == "sess_x"
    assert record["run_meta"]["num_turns"] == 1
    assert record["run_meta"]["usage"]["input_tokens"] == 2
    assert record["output"] == {"schema": "triage/v0.1", "findings": []}


# --- finding 9 (max-tokens half): a --via claude-cli footgun ----------------

def test_main_rejects_max_tokens_with_via_claude_cli(tmp_path, monkeypatch):
    # --max-tokens is a real knob on --via api but inert on --via claude-cli
    # (see run_meta.comparability) — accepting it silently there would let a
    # parameter that does nothing look like it did something.
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    monkeypatch.setattr(run_triager.shutil, "which", lambda name: "/usr/bin/claude")

    def _boom_if_called():
        raise AssertionError("cli_version() must not run when --max-tokens is rejected first")
    monkeypatch.setattr(run_triager, "cli_version", _boom_if_called)

    with pytest.raises(SystemExit, match="max-tokens"):
        run_triager.main([
            str(rendered), "--pack", str(pack),
            "--prompt-version", "finding-triager/v1.0",
            "-o", str(tmp_path / "out.json"), "--via", "claude-cli",
            "--max-tokens", "9000",
            "--env-file", str(tmp_path / "does-not-exist.env"),
        ])


def test_main_still_defaults_max_tokens_on_the_api_path(tmp_path, monkeypatch):
    # The --max-tokens default moved from the argparse level (32000) to
    # main() itself, to make "the user passed --max-tokens" distinguishable
    # from "the user didn't" — confirm the api path still gets the same
    # default it always did when the flag is omitted.
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")
    out = tmp_path / "out.json"

    def _fake_call_model(prompt, *, model, effort, max_tokens):
        assert max_tokens == run_triager.MAX_TOKENS
        return '{"schema": "triage/v0.1", "findings": []}', {
            "input_tokens": 1, "output_tokens": 1, "stop_reason": "end_turn"}
    monkeypatch.setattr(run_triager, "call_model", _fake_call_model)

    rc = run_triager.main([
        str(rendered), "--pack", str(pack),
        "--prompt-version", "finding-triager/v1.0",
        "-o", str(out),
        "--env-file", str(tmp_path / "does-not-exist.env"),
    ])

    assert rc == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["run_meta"]["max_tokens"] == run_triager.MAX_TOKENS
