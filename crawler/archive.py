"""Archive a captured fixture directory, and verify it by manifest hash.

`fixtures/` is not in git, so a lost capture is a lost golden entry — this packs
one into a single file you can store somewhere durable.

Invariant: check the archive against `manifest.yaml`'s sha256, never the
tarball's own — gzip embeds an mtime, so the tarball hash changes between runs.

`-o` refuses to write over an existing archive unless `--force` is passed —
writing a bare `02-sabotaged.tar.gz` a second time is what destroyed the only
copy of the retired `b219afac…` fixture on 2026-07-31. Stamp the name with the
crawler version and the manifest's short hash anyway: the refusal stops the
loss, the stamp is what tells you which capture a tarball holds.

Usage:
    python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged-0.3.0-4bfd303fc9b1.tar.gz
    python -m crawler.archive --check archives/02-sabotaged-0.3.0-4bfd303fc9b1.tar.gz \
        --expect 4bfd303fc9b134ab425bc50ca2ede27646b5657b0696d8ab77de938471f50a6e
"""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

MANIFEST = "manifest.yaml"


def archive(fixture_dir: Path, out_path: Path, force: bool = False) -> str:
    """Tar+gzip every file under `fixture_dir`. Returns its manifest sha256."""
    fixture_dir = Path(fixture_dir)
    manifest = fixture_dir / MANIFEST
    if not manifest.exists():
        raise SystemExit(f"{fixture_dir} has no {MANIFEST} — that is not a capture, refusing to archive it")

    out_path = Path(out_path)
    if out_path.exists() and not force:
        raise SystemExit(
            f"{out_path} already exists — refusing to overwrite a frozen archive. "
            f"Stamp the name with the manifest's short hash, or pass --force to replace it."
        )
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
    """True if the archive's manifest hash matches `expected`."""
    return manifest_sha256_in(archive_path) == expected


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: write an archive, or check an existing one."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("fixture_dir", nargs="?", type=Path)
    parser.add_argument("-o", "--out", type=Path)
    parser.add_argument("--check", type=Path, help="verify an existing archive instead of writing one")
    parser.add_argument("--expect", help="the manifest sha256 the labels pin")
    parser.add_argument("--force", action="store_true", help="replace an existing archive at -o")
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
    digest = archive(args.fixture_dir, args.out, force=args.force)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"{args.out}  {size_mb:.1f} MB  manifest sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
