"""Runs Lighthouse audits through the Node sidecar (spec §7).

The actual audit work is in ``node/lighthouse_runner.mjs``. This module finds
Node, reads the version for the manifest, and records a sidecar crash as failed
templates instead of failing the whole run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RUNNER = Path(__file__).parent / "node" / "lighthouse_runner.mjs"


@dataclass
class LighthouseResult:
    lhrs: list[dict[str, Any]]          # standard LHR objects, in template order
    status: dict[str, str]              # template -> ok | failed | skipped
    version: str | None = None
    errors: dict[str, str] | None = None


def version(root: Path) -> str | None:
    """The installed Lighthouse version, or None if it can't be read."""
    package = root / "node_modules/lighthouse/package.json"
    if not package.is_file():
        return None
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version")
    except (ValueError, OSError):
        return None


def available(root: Path) -> bool:
    """True if both Node and Lighthouse are installed."""
    return bool(shutil.which("node")) and (root / "node_modules/lighthouse").is_dir()


def run(
    root: Path,
    port: int,
    targets: list[tuple[str, str]],
    *,
    timeout_s: int = 900,
) -> LighthouseResult:
    """Audit each (template, url) against the browser listening on `port`.

    Invariant: Lighthouse opens tabs in the browser's default context, which
    has its own cookie jar. The caller must mirror the crawl's cookies there
    first with :meth:`crawler.session.Session.mirror_session_to_default`, or a
    gated store will audit the password page.
    """
    if not targets:
        return LighthouseResult(lhrs=[], status={}, version=version(root))

    if not available(root):
        return LighthouseResult(
            lhrs=[],
            status={template: "skipped" for template, _ in targets},
            version=None,
            errors={"*": "node or node_modules/lighthouse not present"},
        )

    payload = [{"template": t, "url": u} for t, u in targets]
    with tempfile.TemporaryDirectory() as tmp:
        targets_path = Path(tmp) / "targets.json"
        out_path = Path(tmp) / "out.json"
        targets_path.write_text(json.dumps(payload), encoding="utf-8")

        try:
            subprocess.run(
                ["node", str(_RUNNER), str(port), str(targets_path), str(out_path)],
                cwd=str(root),
                check=True,
                timeout=timeout_s,
                capture_output=True,
                env={**os.environ, "NODE_NO_WARNINGS": "1"},
            )
            raw = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:
            # The sidecar died, so every template is failed. No partial credit.
            return LighthouseResult(
                lhrs=[],
                status={template: "failed" for template, _ in targets},
                version=version(root),
                errors={"*": _short(exc)},
            )

    return assemble(raw, version(root))


def assemble(raw: list[dict[str, Any]], detected_version: str | None) -> LighthouseResult:
    """Turn the sidecar's per-template results into a LighthouseResult.

    Only successful audits contribute an LHR; anything else is marked failed and
    kept out of lighthouse.json (spec §7).
    """
    lhrs: list[dict[str, Any]] = []
    status: dict[str, str] = {}
    errors: dict[str, str] = {}
    for entry in raw:
        template = entry.get("template", "")
        if entry.get("ok") and entry.get("lhr"):
            lhrs.append(entry["lhr"])
            status[template] = "ok"
        else:
            status[template] = "failed"
            errors[template] = entry.get("error", "unknown lighthouse failure")

    if lhrs and not detected_version:
        detected_version = lhrs[0].get("lighthouseVersion")
    return LighthouseResult(lhrs=lhrs, status=status, version=detected_version, errors=errors or None)


def _short(exc: Exception) -> str:
    """A one-line, length-capped summary of an exception."""
    if isinstance(exc, subprocess.CalledProcessError):
        tail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return (tail[-1] if tail else f"node exited {exc.returncode}")[:300]
    return str(exc).strip().splitlines()[0][:300] if str(exc).strip() else exc.__class__.__name__
