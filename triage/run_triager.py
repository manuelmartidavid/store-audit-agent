"""Run a rendered finding-triager prompt through the API and record the run.

Why this exists: the first 21 recorded runs were executed as agent sessions.
Their JSON carries `schema` and `findings` and nothing else — no model, no
parameters, no timestamp — so "3 of 3 clear every bar" cannot be re-run and
N=3 with an unrecorded sampler is not a rate.

The run record wraps the model's output rather than merging into it. The
model's JSON is evidence and stays byte-exact; the harness's metadata sits
beside it. `eval_triage.load_run_output` reads both this shape and the bare
shape the 21 recorded runs use.

`run_meta` deliberately does not carry a pack version or a fixture manifest
hash: `eval_triage.provenance()` already computes and verifies both of those
(the pack version against the pack file's own claim, the fixture hash against
the label's pin), and records how — `pack_pin: "matched"` vs `"asserted"`. A
second, independently-sourced copy here, with nothing reconciling the two,
would reopen the exact defect that provenance-verification work closed: a pin
nobody checks is a comment. `pack_sha256` stays — it is a digest of the actual
bytes fed to the model, which is new information, not a duplicate claim.

Model notes, because they are load-bearing for reproducibility:
  * `claude-opus-5` **rejects** temperature / top_p / top_k (HTTP 400). There is
    no sampler knob to pin; what varies run to run is effort and thinking, and
    both are recorded.
  * Thinking is ON by default on this model, and `max_tokens` caps thinking plus
    response together — hence the generous default.
  * The rendered prompt is ~145k tokens, so the request streams. A non-streaming
    call at this size risks an HTTP timeout.

Usage:
    python triage/run_triager.py runs/v1.0.rendered.md \\
        --pack packs/02-sabotaged.pack.json \\
        --prompt-version finding-triager/v1.0 -o runs/v1.0-run4.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import dotenv  # noqa: E402

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
    # 32k characters, and the rendered triager prompt is ~145k tokens.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rendered", type=Path, help="a rendered prompt from render_prompt.py")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-tokens", type=int, default=None,
                         help="--via api only: caps thinking plus response together "
                              f"(default {MAX_TOKENS}). Rejected with --via claude-cli, "
                              "where max_tokens is not a controllable knob (see "
                              "run_meta.comparability) — accepting it there would let a "
                              "parameter that does nothing look like it did something.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--via", default="api", choices=["api", "claude-cli"],
                         help="api (default): anthropic SDK, billed to the Console API key. "
                              "claude-cli: shell out to the Claude Code CLI on the operator's "
                              "own subscription — for testing the pipeline without spending "
                              "Console credits. Not comparable to an api run (see run_meta).")
    parser.add_argument("--system-prompt", default=CLI_SYSTEM_PROMPT,
                         help="--via claude-cli only: the CLI's --system-prompt. The rendered "
                              "prompt carries all real instruction; this must stay neutral.")
    args = parser.parse_args(argv)

    loaded = dotenv.load(args.env_file)
    if loaded:
        print(f"· loaded {len(loaded)} var(s) from {args.env_file}: {', '.join(loaded)}")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    prompt = args.rendered.read_text(encoding="utf-8")

    if args.via == "claude-cli":
        if args.max_tokens is not None:
            raise SystemExit(
                "--max-tokens has no effect with --via claude-cli — thinking and "
                "max_tokens are not controllable knobs on that path (see "
                "run_meta.comparability). Drop --max-tokens, or use --via api if you "
                "need to control it.")
        # Must happen before anything spawns a child — including cli_version()'s
        # own `claude --version` below — or an absent CLI surfaces as a raw
        # FileNotFoundError traceback instead of this actionable exit.
        _require_cli_on_path()
        meta = run_meta(model=args.model, effort=args.effort,
                        rendered_path=args.rendered, pack_path=args.pack,
                        prompt_version=args.prompt_version, started_at=started_at,
                        via="claude-code-cli", system_prompt=args.system_prompt,
                        cli_version=cli_version())
        print(f"· claude-cli {args.model} effort={args.effort} · prompt {len(prompt) / 1024:.0f} KB "
              "· NOT comparable to an api run (see run_meta.comparability)")
        text, usage = call_model_via_cli(prompt, model=args.model, effort=args.effort,
                                         system_prompt=args.system_prompt)
        meta["resolved_model"] = usage.pop("resolved_model")
        meta["total_cost_usd"] = usage.pop("total_cost_usd")
        meta["session_id"] = usage.pop("session_id")
        meta["num_turns"] = usage.pop("num_turns")
        meta["usage"] = usage
    else:
        max_tokens = args.max_tokens if args.max_tokens is not None else MAX_TOKENS
        meta = run_meta(model=args.model, effort=args.effort, max_tokens=max_tokens,
                        rendered_path=args.rendered, pack_path=args.pack,
                        prompt_version=args.prompt_version, started_at=started_at)
        print(f"· {args.model} effort={args.effort} thinking={THINKING} "
              f"max_tokens={max_tokens} · prompt {len(prompt) / 1024:.0f} KB")
        text, usage = call_model(prompt, model=args.model, effort=args.effort,
                                 max_tokens=max_tokens)
        meta["usage"] = usage

    record = {"run_meta": meta, "output": extract_json(text)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    findings = len(record["output"].get("findings") or [])
    print(f"✓ {args.out} · {findings} findings · "
          f"{usage['input_tokens']} in / {usage['output_tokens']} out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
