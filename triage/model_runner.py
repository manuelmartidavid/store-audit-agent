"""Calls a model and records what produced the answer.

Works for both the triager and the narrator: it calls a model, pulls out one
JSON object, and writes down enough to run it again. It knows nothing about what
a finding or a narrative is.
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

# Invariant: this system prompt must never add task guidance. The rendered
# prompt carries the whole task; anything extra here would mean the run
# measures this prompt instead of the one under test.
CLI_SYSTEM_PROMPT = (
    "You are being evaluated. Follow the user message exactly. Do not add "
    "instructions, context, or behavior beyond what it specifies."
)

# Invariant: keep this non-greedy. A greedy `.*` would splice a reply
# containing two fenced blocks into one invalid document.
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _sha256(path: Path) -> str:
    """The sha256 of a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_meta(*, model: str, effort: str, rendered_path: Path, pack_path: Path,
             prompt_version: str, started_at: str, max_tokens: int | None = None,
             via: str = "anthropic-sdk", system_prompt: str | None = None,
             cli_version: str | None = None) -> dict[str, Any]:
    """Everything needed to reproduce a run, including which backend made it.

    The SDK path records max_tokens, thinking, and sampling because those are
    real knobs there. The CLI path records a comparability note instead.
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

    # anthropic-sdk, the default path
    try:
        import anthropic
        sdk_version = getattr(anthropic, "__version__", "unknown")
    except ImportError:  # stay importable without the SDK installed
        sdk_version = "not installed"
    core.update({
        "thinking": THINKING,
        "max_tokens": max_tokens,
        "sampling": "not applicable (claude-opus-5 rejects temperature/top_p/top_k)",
        "sdk_version": sdk_version,
    })
    return core


def extract_json(text: str) -> dict[str, Any]:
    """Pull the one JSON object out of a model's reply, allowing a code fence."""
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
    """One streamed request through the Anthropic SDK. Returns (text, usage)."""
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
    """The last few thousand characters of a subprocess's stderr."""
    return (stderr or "")[-chars:]


# Invariant: keep calling subprocess through this module attribute, not a
# default argument. A default is bound once at import, so tests that patch it
# never take effect and a forgotten test double spawns a real, billable
# subprocess.
_RUNNER = subprocess.run

# Env vars that would bill or reroute a child `claude` process away from the
# operator's own subscription. All of them are stripped from every child:
#   ANTHROPIC_API_KEY       - bills the Console API directly.
#   ANTHROPIC_AUTH_TOKEN    - another credential for the same Console billing.
#   ANTHROPIC_BASE_URL      - points the CLI at a different endpoint.
#   CLAUDE_CODE_USE_BEDROCK - routes the request, and its billing, through AWS.
#   CLAUDE_CODE_USE_VERTEX  - routes the request, and its billing, through GCP.
_BILLING_ROUTING_ENV_VARS = frozenset({
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
})


def _child_env() -> dict[str, str]:
    """A copy of the environment with every billing and routing var removed.

    A fresh dict, so this never touches the parent process's own environment.
    """
    return {key: value for key, value in os.environ.items()
            if key not in _BILLING_ROUTING_ENV_VARS}


def _require_cli_on_path() -> None:
    """Exit with a clear message if the `claude` CLI isn't installed.

    Invariant: call this before any subprocess runs, including `claude
    --version`,  or a missing CLI shows up as a raw FileNotFoundError
    traceback.
    """
    if shutil.which("claude") is None:
        raise SystemExit(
            "the `claude` CLI is not on PATH — install Claude Code and confirm "
            "`claude --version` works before using --via claude-cli.")


def cli_version(runner=None) -> str:
    """The output of `claude --version`, for the run record."""
    runner = runner if runner is not None else _RUNNER
    proc = runner(["claude", "--version"], capture_output=True, text=True,
                   encoding="utf-8", env=_child_env())
    return (proc.stdout or proc.stderr).strip()


def call_model_via_cli(prompt: str, *, model: str, effort: str, system_prompt: str,
                        runner=None) -> tuple[str, dict]:
    """One `claude -p` call through the Claude Code CLI. Returns (text, usage).

    Runs on the operator's own Claude subscription instead of a billed API key.
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
    # Invariant: the prompt goes on stdin, never argv. Windows caps a command
    # line near 32k characters and a rendered prompt runs to ~582k.
    # Invariant: keep encoding="utf-8". Without it Python falls back to the
    # system codepage, which can't encode characters like '≤' — stdin raises
    # before the CLI is reached, and stdout comes back mangled.
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

    # Invariant: read the model id back out of what actually ran; never fall
    # back to the requested one. This field exists to catch a silent model
    # substitution, and a guess here would defeat it.
    model_usage = data.get("modelUsage") or {}
    if len(model_usage) != 1:
        raise SystemExit(
            f"claude CLI response's modelUsage has {len(model_usage)} key(s) "
            f"({sorted(model_usage.keys())!r}), not exactly 1 — the model actually "
            "run cannot be read back unambiguously, and recording the requested "
            f"model ({model!r}) in its place would fabricate a read-back that never "
            f"happened. stderr tail:\n{_stderr_tail(proc.stderr)}")
    resolved_model = next(iter(model_usage))

    # The whole usage block is kept, including anything a future CLI adds.
    raw_usage = data.get("usage") or {}
    usage = {
        # Flattened for the summary print; "raw" below is the full record.
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
