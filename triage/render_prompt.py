"""Fill a prompt template's one placeholder with its input JSON.

`{{PACK}}` in a triager template takes the pack; `{{BRIEF}}` in a narrator
template takes the brief. Pass exactly one of `--pack` or `--brief`.

Invariant: don't add a template engine. A prompt version has to mean one file,
and anything more than this single substitution gives the prompt a second place
to change.

Usage:
    python triage/render_prompt.py prompts/finding-triager/v0.1.md \
        --pack packs/02-sabotaged.pack.json -o runs/v0.1.rendered.md

    python triage/render_prompt.py prompts/impact-narrator/v0.1.md \
        --brief briefs/02-sabotaged.brief.json -o runs/narrator-v0.1.rendered.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from triage import token_estimate  # noqa: E402

PLACEHOLDER = "{{PACK}}"   # kept because the triager's templates and docs name it
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def prompt_version(template_text: str) -> str:
    """The `prompt/version` pair from a template's front matter."""
    match = _FRONTMATTER.match(template_text)
    if not match:
        return "unpinned"
    fields = dict(
        line.split(":", 1) for line in match.group(1).split("\n") if ":" in line
    )
    name = fields.get("prompt", "").strip()
    version = fields.get("version", "").strip()
    return f"{name}/{version}" if name and version else "unpinned"


def render(template_path: Path, data_path: Path, indent: int | None = None,
           placeholder: str = "PACK") -> tuple[str, str]:
    """Substitute one placeholder and return the text plus the prompt version.

    `placeholder` is the token's name, so `PACK` and `BRIEF` share one renderer.
    """
    token = "{{" + placeholder + "}}"
    text = template_path.read_text(encoding="utf-8")
    if token not in text:
        raise SystemExit(f"{template_path} has no {token} placeholder")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    separators = None if indent else (",", ":")
    body = json.dumps(data, indent=indent, separators=separators, default=str)
    return text.replace(token, body), prompt_version(text)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: render one template to a file."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("template", type=Path)
    parser.add_argument("--pack", type=Path, help="evidence pack (the triager's input)")
    parser.add_argument("--brief", type=Path, help="narrator brief (the narrator's input)")
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--indent", type=int, default=None)
    args = parser.parse_args(argv)

    if bool(args.pack) == bool(args.brief):
        raise SystemExit("give exactly one of --pack or --brief")
    data, placeholder = (args.pack, "PACK") if args.pack else (args.brief, "BRIEF")

    text, version = render(args.template, data, args.indent, placeholder)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    # Character count sits next to the token estimate on purpose: characters are
    # counted, tokens are only inferred, so `est.` stays in the output.
    print(f"{args.out}  {len(text) / 1024:.0f} KB  {token_estimate.describe(text)}  "
          f"prompt_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
