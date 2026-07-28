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
