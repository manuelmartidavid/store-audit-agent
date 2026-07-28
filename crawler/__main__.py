"""CLI: ``python -m crawler``.

    python -m crawler --origin https://example.myshopify.com --out fixtures/
    python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/

The ``--context`` form reads ``store.password_env`` and ``eval.fixtures.source``
straight out of a golden entry, so capturing entry 02 and entry 05 differs by one
flag (``--no-password``) rather than by two hand-typed invocations — which is the
whole design of that pair.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .crawl import Options, crawl
from .dotenv import load as load_dotenv
from .redaction import SecretLeak

_SIMPLE_KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*?)\s*$")


def _read_context(path: Path) -> tuple[str | None, str | None, dict]:
    """Pull (origin, password_env) out of a golden context.yaml.

    Uses PyYAML when it is installed and falls back to a two-key line scan when
    it is not: the crawler should not need a YAML dependency to read two strings,
    and the `eval:` block is never rendered anywhere, only read here.
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        store = data.get("store") or {}
        fixtures = ((data.get("eval") or {}).get("fixtures") or {})
        targets = fixtures.get("targets") or {}
        if not isinstance(targets, dict):
            targets = {}
        return fixtures.get("source"), store.get("password_env"), targets
    except ImportError:
        pass

    origin = password_env = None
    for line in text.splitlines():
        match = _SIMPLE_KEY.match(line)
        if not match:
            continue
        _, key, value = match.groups()
        value = value.strip().strip('"').strip("'")
        if key == "password_env" and value and value != "null" and password_env is None:
            password_env = value
        elif key == "source" and value and value != "null" and origin is None:
            origin = value
    return origin, password_env, {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crawler",
        description="Capture the deterministic evidence base for one store (specs/crawler.md v0.1).",
    )
    parser.add_argument("--origin", help="Store origin, e.g. https://example.myshopify.com")
    parser.add_argument("--context", type=Path, help="Golden-entry context.yaml to read origin/password_env from")
    parser.add_argument("--out", type=Path, default=Path("fixtures"), help="Output directory (default: fixtures/)")
    parser.add_argument("--password-env", help="Env var holding the storefront password")
    parser.add_argument("--no-password", action="store_true", help="Ignore the password even if one is configured (entry 05)")
    parser.add_argument("--no-lighthouse", action="store_true")
    parser.add_argument("--no-axe", action="store_true")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed (debugging)")
    parser.add_argument("--debug-port", type=int, default=9222, help="CDP port Lighthouse attaches to")
    parser.add_argument("--seed", type=int, help="Seed the 404 path for a reproducible capture")
    parser.add_argument("--pin", action="append", default=[], metavar="TEMPLATE=URL",
                        help="Pin a template to an exact URL (repeatable), e.g. --pin pdp=https://…/products/x. Overrides discovery; also settable via context eval.fixtures.targets.")
    parser.add_argument("--node-root", type=Path, default=Path.cwd(), help="Directory holding node_modules/")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="dotenv file to load the password from (default: .env)")
    parser.add_argument("--no-env-file", action="store_true", help="Do not load any .env file; use the process environment only")
    parser.add_argument("--no-verify-idempotence", action="store_true", help="Skip the inline distillation determinism check")
    parser.add_argument("--version", action="version", version=f"crawler {__version__}")
    return parser


def _force_utf8_output() -> None:
    """Never let a console codepage abort a crawl.

    The progress log uses arrows and check marks; a legacy Windows console
    (cp1252) raises UnicodeEncodeError on the first one and takes the whole run
    down with it. Reconfigure to UTF-8 with a safe fallback where supported.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)

    if not args.no_env_file:
        # Real environment always wins; the file only fills gaps. Names are safe
        # to print, values never are.
        loaded = load_dotenv(args.env_file)
        if loaded:
            print(f"· loaded {len(loaded)} var(s) from {args.env_file}: {', '.join(loaded)}")

    origin, password_env = args.origin, args.password_env
    pinned: dict[str, str] = {}
    if args.context:
        ctx_origin, ctx_password_env, ctx_targets = _read_context(args.context)
        origin = origin or ctx_origin
        password_env = password_env or ctx_password_env
        pinned.update(ctx_targets)
    for item in args.pin:
        if "=" not in item:
            print(f"error: --pin expects TEMPLATE=URL, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        pinned[k.strip()] = v.strip()
    if not origin:
        print("error: --origin or --context is required", file=sys.stderr)
        return 2
    if args.no_password:
        password_env = None

    options = Options(
        origin=origin,
        out_dir=args.out,
        password_env=password_env,
        run_lighthouse=not args.no_lighthouse,
        run_axe=not args.no_axe,
        headless=not args.headed,
        debug_port=args.debug_port,
        seed=args.seed,
        node_root=args.node_root,
        verify_idempotence=not args.no_verify_idempotence,
        pinned=pinned,
    )

    print(f"→ {origin}  (gate env: {password_env or 'none'})")
    if pinned:
        print("· pinned targets: " + ", ".join(f"{k}={v}" for k, v in pinned.items()))
    try:
        result = crawl(options)
    except SecretLeak as leak:
        print(f"FATAL: {leak}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 — a crawl failure is an operator message
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    crawl_json = result.crawl
    captured = [t for t, e in crawl_json["templates"].items() if e["status"] == "captured"]
    print(
        f"  status={crawl_json['status']} gate={crawl_json['gate']} "
        f"platform={crawl_json['fingerprint']['platform']} "
        f"captured={len(captured)}/6 lighthouse={result.lighthouse_count} "
        f"axe={result.axe_count} fetches={result.fetches}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
