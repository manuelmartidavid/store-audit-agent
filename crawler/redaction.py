"""Checks written output for the storefront password before reporting success (spec §2).

Invariant: a hit is fatal and destructive — the offending files are deleted so
they can't be committed.
"""

from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import quote


class SecretLeak(RuntimeError):
    """Raised when a secret is found in written output. The files are deleted."""


def _variants(secret: str) -> list[bytes]:
    """Every encoding a password might appear in inside a file."""
    forms = {
        secret,
        quote(secret),
        quote(secret, safe=""),
        secret.replace('"', '\\"'),
        base64.b64encode(secret.encode("utf-8")).decode("ascii"),
    }
    # JSON \u-escapes any non-ASCII the encoder felt like escaping.
    forms.add(secret.encode("unicode_escape").decode("ascii"))
    return [f.encode("utf-8") for f in forms if f]


def assert_absent(directory: Path, secret: str | None) -> None:
    """Fail loudly if `secret` appears anywhere under `directory`."""
    if not secret:
        return
    needles = _variants(secret)
    offenders: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        if any(needle in blob for needle in needles):
            offenders.append(path)

    if offenders:
        for path in offenders:
            try:
                path.unlink()
            except OSError:
                pass
        names = ", ".join(str(p.relative_to(directory)) for p in offenders)
        raise SecretLeak(
            f"storefront password found in written output ({names}); "
            "those files have been deleted. This is a crawler bug — fix it before rerunning."
        )
