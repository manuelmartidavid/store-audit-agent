"""Archive a captured fixture directory, and verify it by manifest hash.

Decision 19 keeps `fixtures/` out of git: the commitment is the manifest hash
recorded in `expected/findings.md` and `context.yaml`, not the capture bytes.
That is a sound commitment and a poor backup — the hash commits to bytes held on
one machine, produced from a live store that has since drifted. The store cannot
be rewound, so a lost fixture is a lost golden entry.

This writes the directory to one file you can put somewhere durable, and
verifies it against the pin the labels already carry. The tarball's own sha256
is deliberately NOT the check: gzip embeds an mtime, so it is not stable across
runs. `manifest.yaml`'s sha256 is, and it is the value decision 12 already pins.

Usage:
    python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
    python -m crawler.archive --check archives/02-sabotaged.tar.gz \
        --expect b219afac6f8234ff98ce6c4eaf004bdb4063aaf1155de78b0fe19c6512946d20
"""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

MANIFEST = "manifest.yaml"


def archive(fixture_dir: Path, out_path: Path) -> str:
    """Tar+gzip every file under `fixture_dir`. Returns its manifest sha256."""
    fixture_dir = Path(fixture_dir)
    manifest = fixture_dir / MANIFEST
    if not manifest.exists():
        raise SystemExit(f"{fixture_dir} has no {MANIFEST} — that is not a capture, refusing to archive it")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in fixture_dir.rglob("*") if p.is_file())
    with tarfile.open(out_path, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(fixture_dir.parent).as_posix()))
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def manifest_sha256_in(archive_path: Path) -> str | None:
    """The archived manifest's sha256, read back out of the tar."""
    with tarfile.open(Path(archive_path), "r:gz") as tar:
        member = next((m for m in tar.getmembers()
                       if Path(m.name).name == MANIFEST and m.isfile()), None)
        if member is None:
            return None
        handle = tar.extractfile(member)
        if handle is None:
            return None
        return hashlib.sha256(handle.read()).hexdigest()


def verify(archive_path: Path, expected: str) -> bool:
    return manifest_sha256_in(archive_path) == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("fixture_dir", nargs="?", type=Path)
    parser.add_argument("-o", "--out", type=Path)
    parser.add_argument("--check", type=Path, help="verify an existing archive instead of writing one")
    parser.add_argument("--expect", help="the manifest sha256 the labels pin")
    args = parser.parse_args(argv)

    if args.check:
        found = manifest_sha256_in(args.check)
        print(f"{args.check}  manifest sha256 {found}")
        if args.expect:
            ok = found == args.expect
            print("MATCHES the pin" if ok else f"DOES NOT MATCH — pin is {args.expect}")
            return 0 if ok else 1
        return 0

    if not args.fixture_dir or not args.out:
        parser.error("a fixture_dir and -o are required unless --check")
    digest = archive(args.fixture_dir, args.out)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"{args.out}  {size_mb:.1f} MB  manifest sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
