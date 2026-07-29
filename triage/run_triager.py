"""Runs a rendered finding-triager prompt and saves the output with its run details.

The record wraps the model's output rather than merging into it, so the model's
JSON stays byte-exact and the harness metadata sits beside it.

Worth knowing about the model:
  * claude-opus-5 rejects temperature / top_p / top_k, so there's no sampler to
    pin. Effort and thinking are what vary, and both are recorded.
  * Thinking is on by default and `max_tokens` covers thinking plus response
    together, hence the generous default.
  * A rendered entry-02 prompt is about 315k tokens against a 1M context window,
    so it fits with room to spare.
  * The request streams because the SDK refuses a non-streaming call it expects
    to run past its 10-minute timeout.

Invariant: main() preflights the prompt size before spending anything. Keep it
a warning near the line rather than a refusal — the size is only an estimate,
and `--ignore-context-window` is the override.

Usage:
    python triage/run_triager.py runs/v1.0.rendered.md \\
        --pack packs/02-sabotaged.pack.json \\
        --prompt-version finding-triager/v1.0 -o runs/v1.0-run4.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import dotenv  # noqa: E402
from triage import token_estimate  # noqa: E402
from triage import model_runner  # noqa: E402

# Re-exported because tests and this module's CLI refer to them by these names.
from triage.model_runner import (  # noqa: E402,F401
    CLI_SYSTEM_PROMPT,
    EFFORT,
    MAX_TOKENS,
    MODEL,
    THINKING,
    _sha256,
    call_model,
    call_model_via_cli,
    cli_version,
    extract_json,
    run_meta,
)

# Invariant: don't re-export `_RUNNER` here. It's looked up inside
# model_runner, so a copy in this module would look patchable but never reach
# either call site. Patch `model_runner._RUNNER` instead.


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: run one triager prompt and write the record."""
    # Invariant: keep errors="replace". A Windows console can't encode the `✓`
    # in the success line, and a run that already called the model and wrote
    # its file used to die on that print after spending real money.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass                                # not a stream we can reconfigure

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
                              "where it has no effect.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--via", default="api", choices=["api", "claude-cli"],
                         help="api (default): anthropic SDK, billed to the Console API key. "
                              "claude-cli: shell out to the Claude Code CLI on the operator's "
                              "own subscription — for testing the pipeline without spending "
                              "Console credits. Not comparable to an api run (see run_meta).")
    parser.add_argument("--system-prompt", default=CLI_SYSTEM_PROMPT,
                         help="--via claude-cli only: the CLI's --system-prompt. The rendered "
                              "prompt carries all real instruction; this must stay neutral.")
    parser.add_argument("--ignore-context-window", action="store_true",
                         help="send even when the preflight estimates the prompt will not fit "
                              "--model's context window. The preflight works off an estimate "
                              "calibrated on one fixture (triage/token_estimate.py); this is "
                              "the escape hatch for when you know better than it does.")
    args = parser.parse_args(argv)

    loaded = dotenv.load(args.env_file)
    if loaded:
        print(f"· loaded {len(loaded)} var(s) from {args.env_file}: {', '.join(loaded)}")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    prompt = args.rendered.read_text(encoding="utf-8")

    # Check the size before spending anything. Both backends send the same
    # string, so both fail the same way if it doesn't fit.
    verdict, message = token_estimate.context_preflight(prompt, model=args.model)
    if verdict == "refuse":
        if not args.ignore_context_window:
            raise SystemExit(f"refusing to send: {message}")
        print(f"· sending anyway, preflight overridden — {message}")
    elif message:
        print(f"· {message}")

    if args.via == "claude-cli":
        if args.max_tokens is not None:
            raise SystemExit(
                "--max-tokens has no effect with --via claude-cli — thinking and "
                "max_tokens are not controllable knobs on that path (see "
                "run_meta.comparability). Drop --max-tokens, or use --via api if you "
                "need to control it.")
        # Must run before anything spawns a child, including cli_version() below.
        model_runner._require_cli_on_path()
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
