"""Render a prompt template against an evidence pack. One substitution, no engine.

`{{PACK}}` inside the template's `<input_data>` block is replaced with the pack
JSON. Nothing else is substituted — a template language here would be a second
place for the prompt to change, and prompt versions have to mean one file.

Usage:
    python triage/render_prompt.py prompts/finding-triager/v0.1.md \
        --pack packs/02-sabotaged.pack.json -o runs/v0.1.rendered.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLACEHOLDER = "{{PACK}}"
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def prompt_version(template_text: str) -> str:
    """`prompt: x` + `version: y` from the front matter — the provenance pin."""
    match = _FRONTMATTER.match(template_text)
    if not match:
        return "unpinned"
    fields = dict(
        line.split(":", 1) for line in match.group(1).split("\n") if ":" in line
    )
    name = fields.get("prompt", "").strip()
    version = fields.get("version", "").strip()
    return f"{name}/{version}" if name and version else "unpinned"


def render(template_path: Path, pack_path: Path, indent: int | None = None) -> tuple[str, str]:
    text = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        raise SystemExit(f"{template_path} has no {PLACEHOLDER} placeholder")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    separators = None if indent else (",", ":")
    body = json.dumps(pack, indent=indent, separators=separators, default=str)
    return text.replace(PLACEHOLDER, body), prompt_version(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("template", type=Path)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--indent", type=int, default=None)
    args = parser.parse_args(argv)

    text, version = render(args.template, args.pack, args.indent)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}  {len(text) / 1024:.0f} KB  ~{len(text) // 4000}k tokens est.  "
          f"prompt_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
