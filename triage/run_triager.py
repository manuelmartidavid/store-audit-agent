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
import re
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

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_meta(*, model: str, effort: str, max_tokens: int, rendered_path: Path,
             pack_path: Path, prompt_version: str, started_at: str) -> dict[str, Any]:
    """Everything needed to run this again and get a comparable result."""
    try:
        import anthropic
        sdk_version = getattr(anthropic, "__version__", "unknown")
    except ImportError:  # the metadata builder stays importable without the SDK
        sdk_version = "not installed"
    return {
        "model": model,
        "effort": effort,
        "thinking": THINKING,
        "max_tokens": max_tokens,
        "sampling": "not applicable (claude-opus-5 rejects temperature/top_p/top_k)",
        "prompt_version": prompt_version,
        "rendered_sha256": _sha256(rendered_path),
        "pack_sha256": _sha256(pack_path),
        "started_at": started_at,
        "sdk_version": sdk_version,
    }


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rendered", type=Path, help="a rendered prompt from render_prompt.py")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    loaded = dotenv.load(args.env_file)
    if loaded:
        print(f"· loaded {len(loaded)} var(s) from {args.env_file}: {', '.join(loaded)}")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    meta = run_meta(model=args.model, effort=args.effort, max_tokens=args.max_tokens,
                    rendered_path=args.rendered, pack_path=args.pack,
                    prompt_version=args.prompt_version, started_at=started_at)

    prompt = args.rendered.read_text(encoding="utf-8")
    print(f"· {args.model} effort={args.effort} thinking={THINKING} "
          f"max_tokens={args.max_tokens} · prompt {len(prompt) / 1024:.0f} KB")
    text, usage = call_model(prompt, model=args.model, effort=args.effort,
                             max_tokens=args.max_tokens)
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
