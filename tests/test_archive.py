"""crawler/archive.py — the golden fixture's only backup.

The archive's own sha256 is NOT the commitment: gzip embeds an mtime, so two
archives of identical bytes differ. The commitment is what it already was —
the sha256 of manifest.yaml (decision 12) — so verification reads that member
out of the tar and hashes it. An archive that round-trips but reports a
different manifest hash is a corrupted backup, and that is the case worth
catching.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("crawler_archive", ROOT / "crawler" / "archive.py")
archive_mod = importlib.util.module_from_spec(_spec)
sys.modules["crawler_archive"] = archive_mod
_spec.loader.exec_module(archive_mod)


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "02-sabotaged"
    (fixture / "nested").mkdir(parents=True)
    (fixture / "manifest.yaml").write_text("crawler_version: 0.2.0\n", encoding="utf-8")
    (fixture / "crawl.json").write_text('{"schema": "crawl/v0.1"}', encoding="utf-8")
    (fixture / "nested" / "extra.json").write_text("{}", encoding="utf-8")
    return fixture


def test_archive_contains_every_file_under_the_fixture(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "02-sabotaged.tar.gz"
    archive_mod.archive(fixture, out)
    with tarfile.open(out, "r:gz") as tar:
        names = sorted(tar.getnames())
    assert names == [
        "02-sabotaged/crawl.json",
        "02-sabotaged/manifest.yaml",
        "02-sabotaged/nested/extra.json",
    ]


def test_archive_returns_the_manifest_hash_not_the_tarball_hash(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "a.tar.gz"
    returned = archive_mod.archive(fixture, out)
    expected = hashlib.sha256((fixture / "manifest.yaml").read_bytes()).hexdigest()
    assert returned == expected
    assert returned != hashlib.sha256(out.read_bytes()).hexdigest()


def test_verify_reads_the_manifest_back_out_of_the_tar(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "a.tar.gz"
    digest = archive_mod.archive(fixture, out)
    assert archive_mod.manifest_sha256_in(out) == digest
    assert archive_mod.verify(out, digest) is True
    assert archive_mod.verify(out, "0" * 64) is False


def test_an_existing_archive_is_never_silently_overwritten(tmp_path):
    """This is the b219afac loss, reproduced.

    On 2026-07-31 a re-freeze wrote `archives/02-sabotaged.tar.gz` over the
    tarball holding the only copy of the retired fixture, printed a success
    line and exited 0. Eighteen scored runs lost the bytes behind them.
    Version-stamped names make the collision unlikely; refusing the write is
    what makes it impossible.
    """
    fixture = _fixture(tmp_path)
    out = tmp_path / "02-sabotaged.tar.gz"
    first = archive_mod.archive(fixture, out)

    (fixture / "manifest.yaml").write_text("crawler_version: 0.3.0\n", encoding="utf-8")
    try:
        archive_mod.archive(fixture, out)
    except SystemExit as exit_:
        assert "--force" in str(exit_)
    else:
        raise AssertionError("archiving over an existing archive must fail loudly")

    # The point of the refusal: the predecessor is still intact.
    assert archive_mod.manifest_sha256_in(out) == first


def test_force_overwrites_an_existing_archive(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "02-sabotaged.tar.gz"
    first = archive_mod.archive(fixture, out)

    (fixture / "manifest.yaml").write_text("crawler_version: 0.3.0\n", encoding="utf-8")
    second = archive_mod.archive(fixture, out, force=True)

    assert second != first
    assert archive_mod.manifest_sha256_in(out) == second


def test_the_cli_refuses_to_clobber_unless_forced(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "02-sabotaged.tar.gz"
    assert archive_mod.main([str(fixture), "-o", str(out)]) == 0

    try:
        archive_mod.main([str(fixture), "-o", str(out)])
    except SystemExit as exit_:
        assert "--force" in str(exit_)
    else:
        raise AssertionError("the CLI must refuse to overwrite without --force")

    assert archive_mod.main([str(fixture), "-o", str(out), "--force"]) == 0


def test_a_fixture_with_no_manifest_is_refused(tmp_path):
    fixture = tmp_path / "empty"
    fixture.mkdir()
    (fixture / "crawl.json").write_text("{}", encoding="utf-8")
    try:
        archive_mod.archive(fixture, tmp_path / "a.tar.gz")
    except SystemExit as exit_:
        assert "manifest.yaml" in str(exit_)
    else:
        raise AssertionError("archiving a fixture with no manifest must fail loudly")
