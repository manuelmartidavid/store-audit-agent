"""Run the impact-narrator against a rendered prompt and record what produced it.

Same two backends and the same provenance record as run_triager.py, because both
call triage/model_runner.py. Tools are disabled on the CLI path for the same
reason as triage: with them on, the model could read the fixture directly and the
measurement would be void.

Usage:
    python triage/run_narrator.py runs/02-narrator-v0.1.rendered.md \
        --brief briefs/02-sabotaged.brief.json \
        --prompt-version impact-narrator/v0.1 --via claude-cli \
        -o runs/narrator-v0.1-run1.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import model_runner  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rendered", type=Path)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True,
                        help="no default, deliberately — an unpinned run is not a result")
    parser.add_argument("--via", choices=["api", "claude-cli"], default="api")
    parser.add_argument("--model", default=model_runner.MODEL)
    parser.add_argument("--effort", default=model_runner.EFFORT)
    parser.add_argument("--max-tokens", type=int, default=model_runner.MAX_TOKENS)
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args(argv)

    prompt = args.rendered.read_text(encoding="utf-8")
    started_at = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    if args.via == "claude-cli":
        text, usage = model_runner.call_model_via_cli(
            prompt, model=args.model, effort=args.effort,
            system_prompt=model_runner.CLI_SYSTEM_PROMPT)
        meta = model_runner.run_meta(
            model=args.model, effort=args.effort, rendered_path=args.rendered,
            pack_path=args.brief, prompt_version=args.prompt_version,
            started_at=started_at, via="claude-code-cli",
            system_prompt=model_runner.CLI_SYSTEM_PROMPT,
            cli_version=model_runner.cli_version())
    else:
        text, usage = model_runner.call_model(
            prompt, model=args.model, effort=args.effort, max_tokens=args.max_tokens)
        meta = model_runner.run_meta(
            model=args.model, effort=args.effort, rendered_path=args.rendered,
            pack_path=args.brief, prompt_version=args.prompt_version,
            started_at=started_at, max_tokens=args.max_tokens)

    meta["usage"] = usage
    # `pack_sha256` is what run_meta names the input digest; for this layer the
    # input is the brief. Aliased rather than renamed so one record shape serves
    # both backends and both layers.
    meta["brief_sha256"] = meta.get("pack_sha256")

    record = {"run_meta": meta, "output": model_runner.extract_json(text)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}  findings={len(record['output'].get('findings') or {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
