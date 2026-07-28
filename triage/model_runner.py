"""Call a model and record what produced the answer. Backend-neutral.

Extracted from triage/run_triager.py so `run_narrator.py` cannot grow a second
spelling of the provenance record. `run_triager.py` keeps its name and CLI: four
run records and the reproduction block in prompts/README.md cite it by path.

Nothing here knows what a triage finding is, or what a narrative is. It renders
nothing and validates nothing — it calls a model, extracts one JSON object, and
writes down enough to run it again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MODEL = "claude-opus-5"
EFFORT = "high"
THINKING = "adaptive"
MAX_TOKENS = 32000

# The rendered triager prompt carries the entire task. The CLI backend's
# system prompt exists only to tell the model it is being evaluated — it must
# add no task guidance of its own, or a measurement taken through this path
# would be testing the harness's prompt, not the triager's.
CLI_SYSTEM_PROMPT = (
    "You are being evaluated. Follow the user message exactly. Do not add "
    "instructions, context, or behavior beyond what it specifies."
)

# Non-greedy: the contract is one JSON object and no prose, so tolerate a
# single fence and nothing more. A greedy `.*` here would splice a reply that
# accidentally contains a second fenced block into one invalid document —
# spanning from the first `{` to the *last* `}` before the final fence.
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_meta(*, model: str, effort: str, rendered_path: Path, pack_path: Path,
             prompt_version: str, started_at: str, max_tokens: int | None = None,
             via: str = "anthropic-sdk", system_prompt: str | None = None,
             cli_version: str | None = None) -> dict[str, Any]:
    """Everything needed to run this again — and to tell, from the file alone,
    which backend produced it.

    The two backends are not interchangeable and their records say so. The
    `anthropic-sdk` path pins `max_tokens`/`thinking`/`sampling` because those
    are real, controllable knobs on that path. The `claude-code-cli` path
    doesn't get those fields — recording them would imply a control that
    doesn't exist there — and instead carries `comparability`, an explicit,
    recorded statement (not a comment) of what a CLI run can and cannot be
    compared against.
    """
    core: dict[str, Any] = {
        "model": model,
        "effort": effort,
        "prompt_version": prompt_version,
        "rendered_sha256": _sha256(rendered_path),
        "pack_sha256": _sha256(pack_path),
        "started_at": started_at,
        "via": via,
    }

    if via == "claude-code-cli":
        core["cli_version"] = cli_version
        core["system_prompt"] = system_prompt
        core["comparability"] = (
            "NOT COMPARABLE to an anthropic-sdk run: max_tokens and thinking are "
            "not controllable through the claude-code-cli path, and roughly 1.7k "
            "tokens of Claude Code harness context (system prompt scaffolding, "
            "even with --tools \"\" --strict-mcp-config) precede the prompt on "
            "every request. effort and the resolved model ARE pinned on this "
            "path, the same as on anthropic-sdk, so those two fields — and only "
            "those two — can be compared across the two backends."
        )
        return core

    # anthropic-sdk (the default, unchanged, path)
    try:
        import anthropic
        sdk_version = getattr(anthropic, "__version__", "unknown")
    except ImportError:  # the metadata builder stays importable without the SDK
        sdk_version = "not installed"
    core.update({
        "thinking": THINKING,
        "max_tokens": max_tokens,
        "sampling": "not applicable (claude-opus-5 rejects temperature/top_p/top_k)",
        "sdk_version": sdk_version,
    })
    return core


def extract_json(text: str) -> dict[str, Any]:
    """The contract says one JSON object and no prose. Tolerate a fence, only."""
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"the model's reply is not one JSON object ({error}). "
            f"First 200 chars: {text[:200]!r}")


def call_model(prompt: str, *, model: str, effort: str, max_tokens: int) -> tuple[str, dict]:
    """One streamed request. Returns (text, usage)."""
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        output_config={"effort": effort},
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise SystemExit(f"the request was declined: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise SystemExit(
            f"output hit max_tokens ({max_tokens}) — thinking and response share the "
            "budget on this model; re-run with a larger --max-tokens")

    text = "".join(block.text for block in message.content if block.type == "text")
    usage = {"input_tokens": message.usage.input_tokens,
             "output_tokens": message.usage.output_tokens,
             "stop_reason": message.stop_reason}
    return text, usage


def _stderr_tail(stderr: str, chars: int = 2000) -> str:
    return (stderr or "")[-chars:]


# `runner=subprocess.run` as a default *parameter* value gets resolved once,
# at function-definition time, and baked into the function object — so
# `monkeypatch.setattr(run_triager.subprocess, "run", fake)` never reaches a
# call made through that default; it already captured the original object.
# `_RUNNER` is looked up by name inside each function body instead, which
# Python resolves fresh on every call — so patching this module attribute
# (`run_triager._RUNNER`) actually intercepts the next call. This indirection
# is the only thing standing between a forgotten test double and a real
# subprocess spawn that spends the subscription.
_RUNNER = subprocess.run

# Env vars that route or bill a child `claude` process somewhere other than
# the operator's own Claude subscription — the entire reason this backend
# exists. Every child this module spawns must have all of these stripped:
#   ANTHROPIC_API_KEY       - bills the Console API directly.
#   ANTHROPIC_AUTH_TOKEN    - an alternate credential for the same Console billing.
#   ANTHROPIC_BASE_URL      - repoints the CLI at a different (possibly billed) endpoint.
#   CLAUDE_CODE_USE_BEDROCK - routes the request, and its billing, through AWS Bedrock.
#   CLAUDE_CODE_USE_VERTEX  - routes the request, and its billing, through GCP Vertex.
_BILLING_ROUTING_ENV_VARS = frozenset({
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
})


def _child_env() -> dict[str, str]:
    """`os.environ` with every billing/routing var stripped, for any child
    this module spawns under --via claude-cli.

    One of those vars may be present even though the user never set it
    directly — `dotenv.load()` in main() can put ANTHROPIC_API_KEY there from
    `.env`. Built as a fresh dict rather than a mutation of `os.environ` so
    the parent process's own environment is untouched.
    """
    return {key: value for key, value in os.environ.items()
            if key not in _BILLING_ROUTING_ENV_VARS}


def _require_cli_on_path() -> None:
    """Guard every child this module spawns under --via claude-cli.

    Must run before *any* subprocess reaches a shell — including
    cli_version()'s own `claude --version` — or an absent CLI surfaces as a
    raw `FileNotFoundError` traceback instead of this actionable exit.
    """
    if shutil.which("claude") is None:
        raise SystemExit(
            "the `claude` CLI is not on PATH — install Claude Code and confirm "
            "`claude --version` works before using --via claude-cli.")


def cli_version(runner=None) -> str:
    """`claude --version`, captured for the run record — not asserted, run."""
    runner = runner if runner is not None else _RUNNER
    proc = runner(["claude", "--version"], capture_output=True, text=True,
                   encoding="utf-8", env=_child_env())
    return (proc.stdout or proc.stderr).strip()


def call_model_via_cli(prompt: str, *, model: str, effort: str, system_prompt: str,
                        runner=None) -> tuple[str, dict]:
    """One `claude -p` invocation via the Claude Code CLI. Returns (text, usage).

    Exists to test the pipeline without spending Console credits — it runs on
    the operator's personal Claude subscription instead of the `anthropic`
    SDK's Console-billed API key. Every failure mode below is one that would
    otherwise either silently bill the Console API or hand back a run that
    looks clean but isn't a single completion.
    """
    runner = runner if runner is not None else _RUNNER
    _require_cli_on_path()

    argv = [
        "claude", "-p",
        "--model", model,
        "--effort", effort,
        "--tools", "",
        "--system-prompt", system_prompt,
        "--strict-mcp-config",
        "--output-format", "json",
    ]
    # The prompt goes on stdin, never argv — Windows caps a command line near
    # 32k characters, and the rendered triager prompt is ~582k *characters*
    # (measured on runs/v1.0.rendered.md). Characters are the unit the cap is
    # denominated in; this comment used to argue the point in tokens, which is
    # the wrong unit for it as well as the wrong number.
    #
    # encoding="utf-8" is not cosmetic: without it, text=True falls back to
    # locale.getpreferredencoding(), which is cp1252 on this machine. Every
    # rendered triager prompt contains U+2264 ('≤'), unencodable in cp1252 —
    # stdin would raise UnicodeEncodeError before the CLI is ever reached.
    # The same fallback would also mangle UTF-8 stdout on decode, silently
    # corrupting a measured artifact rather than raising at all.
    proc = runner(argv, input=prompt, capture_output=True, text=True,
                   encoding="utf-8", env=_child_env())

    if proc.returncode != 0:
        raise SystemExit(
            f"claude CLI exited {proc.returncode}. stderr tail:\n{_stderr_tail(proc.stderr)}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"claude CLI stdout is not JSON ({error}). "
            f"First 200 chars of stdout: {proc.stdout[:200]!r}. "
            f"stderr tail:\n{_stderr_tail(proc.stderr)}")

    if data.get("is_error"):
        raise SystemExit(
            f"claude CLI reported is_error=true (subtype={data.get('subtype')!r}). "
            f"stderr tail:\n{_stderr_tail(proc.stderr)}")

    if "result" not in data:
        raise SystemExit(
            f"claude CLI response has no 'result' field. Keys present: "
            f"{sorted(data.keys())}. stderr tail:\n{_stderr_tail(proc.stderr)}")

    num_turns = data.get("num_turns")
    if num_turns is not None and num_turns > 1:
        raise SystemExit(
            f"claude CLI used {num_turns} turns, not 1. Tools are off, so a "
            "multi-turn response means the harness did something other than "
            "answer — this is not a clean single completion and cannot be recorded "
            "as one.")

    # The resolved model id must be read back out of what actually ran, not
    # merely echo the one requested — that is the entire point of this
    # field: catching a silent model substitution. modelUsage absent, empty,
    # or holding more than one key all mean the same thing: there is no
    # single unambiguous read-back available. Falling back to the requested
    # model in any of those cases would fabricate a read-back that never
    # happened, and silently picking an arbitrary key on a tie would be just
    # as unaccountable. Fail instead of recording a plausible-looking guess.
    model_usage = data.get("modelUsage") or {}
    if len(model_usage) != 1:
        raise SystemExit(
            f"claude CLI response's modelUsage has {len(model_usage)} key(s) "
            f"({sorted(model_usage.keys())!r}), not exactly 1 — the model actually "
            "run cannot be read back unambiguously, and recording the requested "
            f"model ({model!r}) in its place would fabricate a read-back that never "
            f"happened. stderr tail:\n{_stderr_tail(proc.stderr)}")
    resolved_model = next(iter(model_usage))

    # The full usage block, kept wholesale — cache_creation sub-objects,
    # server_tool_use, service_tier, and anything a future CLI version adds
    # are evidence too, and this module's whole posture is that the record
    # keeps what actually happened rather than a hand-picked projection of it.
    raw_usage = data.get("usage") or {}
    usage = {
        # Flattened for convenience (main()'s summary print reads these) —
        # "raw" below is the actual, un-trimmed record.
        "input_tokens": raw_usage.get("input_tokens"),
        "output_tokens": raw_usage.get("output_tokens"),
        "raw": raw_usage,
        "resolved_model": resolved_model,
        "total_cost_usd": data.get("total_cost_usd"),
        "session_id": data.get("session_id"),
        "num_turns": num_turns,
        "stop_reason": data.get("stop_reason"),
    }
    return data["result"], usage
