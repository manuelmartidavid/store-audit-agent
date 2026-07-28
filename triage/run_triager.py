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
  * The rendered prompt for entry 02 is **315,094 tokens**. That is measured, not
    estimated: it is the model's own count for the one recorded run
    (`runs/v1.0-cli-run1.json`, `run_meta.usage.raw.cache_creation_input_tokens`).
    This docstring used to say ~145k, which came from a 4-chars-per-token prose
    rule that is 2.16x wrong for a dense-JSON pack. The estimator now carries a
    ratio calibrated on that measurement — `triage/token_estimate.py`.
  * **It fits, and the reason is the model, not the backend.** `claude-opus-5`
    has a 1M-token context window, and 1M is both its default and its maximum:
    there is no separate 1M model id and no beta header to send (claude-api
    skill — `shared/models.md`: "1M context window (default and maximum)";
    `shared/model-migration.md` → Migrating to Claude Opus 5: "1M context
    (default, no beta header)"). The CLI reporting `contextWindow: 1000000` on
    the live run was this same model stating this same fact. So both `--via api`
    and `--via claude-cli` are pointed at a 1M model here, and a 315k prompt is
    at 31% of the window on either path.
  * The request streams because of the clock, not the window. The SDK's default
    request timeout is 10 minutes and it refuses a non-streaming call it expects
    to exceed that. Nothing else about the documented call changes at this size:
    the skill establishes no long-context price tier, header, or parameter that
    engages above 200k input on this model. What it does not settle is left
    unsaid here rather than guessed at, because a confident wrong sentence in
    this docstring is paid for in Console credits.
  * `main()` therefore preflights before it spends anything: it compares the
    estimated prompt size against the target model's recorded window and exits
    if the prompt is clearly over. The estimate is an estimate, so the guard
    warns rather than refuses near the line, and `--ignore-context-window`
    overrides it outright — an operator who knows better than the estimator
    should not be held up by it.

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

# Re-exported: tests/test_run_triager.py imports these from here, and this
# module's own docstring/CLI cite them by these names. `_RUNNER` is
# deliberately NOT re-exported as a bare name below — see the note next to
# the import block.
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

# `_RUNNER` is deliberately NOT re-exported as a bare name here. It is looked
# up, by name, inside `model_runner.cli_version` and
# `model_runner.call_model_via_cli` — both now live in triage/model_runner.py,
# so that lookup resolves in *that* module's globals, not this one's. Binding
# a copy of the name here (`from triage.model_runner import _RUNNER`) would
# give a caller something that looks patchable but silently isn't: patching
# this module's copy would no longer reach either call site. A test (or an
# operator) that needs the real seam patches `model_runner._RUNNER` —
# reachable off this module as `run_triager.model_runner._RUNNER` — which is
# where it actually lives now.


def main(argv: list[str] | None = None) -> int:
    # A Windows console defaults to cp1252, which cannot encode the `✓` in the
    # success line — so a run that had already called the model, written its
    # record and cost real money died on the print and exited non-zero. The
    # expensive work was done and the file was on disk; only the report failed.
    # `errors="replace"` rather than a plain reconfigure: a console that cannot
    # render a character should degrade, never abort.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass                                # not a reconfigurable stream

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

    # Before anything is spent. Both backends send this same string to the same
    # model, so both fail the same way if it does not fit — the api path costs
    # Console credits to find that out and the cli path costs subscription
    # quota. The check is on the requested model; on the cli path the CLI may
    # resolve something else, which is exactly why call_model_via_cli reads the
    # resolved model back out of the response rather than trusting this name.
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
        # Must happen before anything spawns a child — including cli_version()'s
        # own `claude --version` below — or an absent CLI surfaces as a raw
        # FileNotFoundError traceback instead of this actionable exit.
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
