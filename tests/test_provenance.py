"""Decision 12's four pins, actually enforced.

The scorer printed all four and checked none. The one it computes — the fixture
manifest hash — was never compared to the pin the labels carry, so scoring a run
against a re-captured fixture printed a different hash and passed. That is the
failure mode this project exists to prevent, sitting inside the tool built to
catch it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)


def _entry(tmp_path: Path, pin: str | None) -> Path:
    entry = tmp_path / "entry"
    (entry / "expected").mkdir(parents=True)
    fixtures_line = f'    manifest_sha256: "{pin}"\n' if pin else ""
    (entry / "context.yaml").write_text(
        "store:\n  origin: https://example.test/\n"
        "eval:\n  fixtures:\n" + (fixtures_line or "    captured_at: null\n"),
        encoding="utf-8")
    (entry / "expected" / "findings.md").write_text("# labels\n", encoding="utf-8")
    return entry


def _fixtures(tmp_path: Path, body: str) -> Path:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "manifest.yaml").write_text(body, encoding="utf-8")
    return fixtures


def test_a_matching_fixture_hash_is_recorded(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    assert record["fixture_manifest_sha256"] == digest
    assert record["fixture_pin"] == "matched"


def test_a_mismatched_fixture_hash_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.3.0\n")   # recaptured
    entry = _entry(tmp_path, "0" * 64)                            # labels pin the old one
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    assert "does not match" in str(caught.value)


def test_an_absent_pin_is_fatal_unless_allowed(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    entry = _entry(tmp_path, None)
    with pytest.raises(SystemExit):
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0",
                                    "pack/v0.2", allow_unpinned=True)
    assert record["fixture_pin"] == "absent"


def test_an_unknown_prompt_version_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "x: 1\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v9.9", "pack/v0.2")
    assert "names no prompt file" in str(caught.value)
    with pytest.raises(SystemExit):
        eval_triage.provenance(entry, fixtures, "unpinned", "pack/v0.2")


def test_the_rubric_version_is_read_from_the_file_not_hardcoded(tmp_path):
    real = eval_triage.rubric_version()
    assert real.startswith("rubric.md v")
    copy = tmp_path / "rubric.md"
    copy.write_text("# Scoring rubric\n\n`rubric.md` · v9.9 draft\n\n---\n", encoding="utf-8")
    assert eval_triage.rubric_version(copy).startswith("rubric.md v9.9+")
    assert eval_triage.rubric_version(copy) != real


def test_the_live_prompts_and_the_live_rubric_resolve():
    # The real repo, not a fixture: v1.0 must exist and rubric.md must parse.
    assert eval_triage.resolve_prompt_version("finding-triager/v1.0", ROOT / "prompts")
    assert "unknown" not in eval_triage.rubric_version()


def test_pack_version_is_asserted_without_a_pack_file(tmp_path):
    # packs/ is gitignored and ordinarily absent, so this is the ordinary path —
    # which is exactly why it must read as a claim, not a verified pin.
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.1")
    assert record["pack_version"] == "pack/v0.1"
    assert record["pack_pin"] == "asserted"


def test_pack_version_is_matched_against_an_agreeing_pack_file(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    pack = tmp_path / "pack.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2",
                                    pack_path=pack)
    assert record["pack_pin"] == "matched"


def test_pack_version_disagreeing_with_the_pack_file_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    pack = tmp_path / "pack.json"
    pack.write_text('{"pack": "pack/v0.1"}', encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2",
                               pack_path=pack)
    assert "does not match" in str(caught.value)


def test_a_malformed_pack_version_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    with pytest.raises(SystemExit):
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "v0.2")


def test_allow_unpinned_excuses_a_missing_pin_not_a_mismatched_one(tmp_path):
    # allow_unpinned=True must only excuse an *absent* fixture pin. If a future
    # refactor moved the mismatch check below this guard, the flag would become
    # a total bypass — this test is what would go red if that happened.
    fixtures = _fixtures(tmp_path, "crawler_version: 0.3.0\n")   # recaptured
    entry = _entry(tmp_path, "0" * 64)                            # labels pin the old one
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2",
                               allow_unpinned=True)
    assert "does not match" in str(caught.value)


def test_the_manifest_pin_falls_back_to_the_label_files_header(tmp_path):
    # context.yaml carries no pin at all; the fallback must find the `manifest:`
    # header in expected/findings.md, matching the shape at
    # evals/golden/02-sabotaged/expected/findings.md:5.
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = tmp_path / "fallback-entry"
    (entry / "expected").mkdir(parents=True)
    (entry / "expected" / "findings.md").write_text(
        "# Expected findings\n\n"
        "    schema:      findings/v0.1\n"
        f"    manifest:    {digest}\n"
        "    captured_at: 2026-07-27T16:39:27+08:00\n",
        encoding="utf-8")
    assert eval_triage.expected_manifest_sha256(entry) == digest
