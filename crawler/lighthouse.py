"""Lighthouse driver — spec §7.

Thin wrapper around the Node sidecar. Everything interesting is in
``node/lighthouse_runner.mjs``; what lives here is locating Node, pinning
versions for the manifest, and turning a sidecar crash into recorded partial
evidence rather than a failed run.
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
    package = root / "node_modules/lighthouse/package.json"
    if not package.is_file():
        return None
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version")
    except (ValueError, OSError):
        return None


def available(root: Path) -> bool:
    return bool(shutil.which("node")) and (root / "node_modules/lighthouse").is_dir()


def run(
    root: Path,
    port: int,
    targets: list[tuple[str, str]],
    *,
    timeout_s: int = 900,
) -> LighthouseResult:
    """Audit each (template, url) against the browser listening on `port`.

    The crawl runs in its own isolated Playwright context, but Lighthouse opens
    its tabs in the browser's *default* context — a separate cookie jar. The gate
    session reaches Lighthouse only because the caller mirrors the crawl's
    cookies into that default context first, via
    :meth:`crawler.session.Session.mirror_session_to_default`. (A persistent
    context that fused the two would share the jar directly but deadlocks
    Lighthouse's second run, so it is deliberately not used — see session.py.)
    This is the spec §7 shared authenticated session.
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
            # The whole sidecar died. Every template is failed, and that is what
            # the manifest will say — no interpolation, no partial credit.
            return LighthouseResult(
                lhrs=[],
                status={template: "failed" for template, _ in targets},
                version=version(root),
                errors={"*": _short(exc)},
            )

    return assemble(raw, version(root))


def assemble(raw: list[dict[str, Any]], detected_version: str | None) -> LighthouseResult:
    """Turn the sidecar's per-template results into a LighthouseResult.

    Pure and browser-free so the failure-classification path — the one that
    quietly recorded four errored audits as ``ok`` — is unit-testable. Only
    genuinely successful runs contribute an LHR; an ``ok: false`` entry (a load
    error the sidecar surfaced) is a failed template, recorded in the manifest
    and kept out of lighthouse.json rather than interpolated (spec §7).
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
    if isinstance(exc, subprocess.CalledProcessError):
        tail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return (tail[-1] if tail else f"node exited {exc.returncode}")[:300]
    return str(exc).strip().splitlines()[0][:300] if str(exc).strip() else exc.__class__.__name__
