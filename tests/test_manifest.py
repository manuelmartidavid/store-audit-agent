"""manifest.yaml — spec §8."""

from __future__ import annotations

from crawler.config import TEMPLATES
from crawler.manifest import Manifest


def _manifest(**overrides) -> Manifest:
    base = dict(
        captured_at="2026-07-24T14:00:00+08:00",
        origin="https://shop.test",
        gate="password_supplied",
        templates={t: {"crawl": "captured", "lighthouse": "ok", "axe": "ok"} for t in TEMPLATES},
        lighthouse_version="12.8.2",
        axe_core_version="4.12.1",
        chrome_version="140.0.0.0",
    )
    base.update(overrides)
    return Manifest(**base)


def test_the_manifest_carries_every_field_the_spec_names(tmp_path):
    body = _manifest().to_yaml()
    for key in (
        "schema: manifest/v0.1",
        "captured_at: 2026-07-24T14:00:00+08:00",
        "origin: https://shop.test",
        "gate: password_supplied",
        "crawler_version:",
        "lighthouse_version: 12.8.2",
        "axe_core_version: 4.12.1",
        "chrome_version: 140.0.0.0",
        "throttling: mobile-4g-slow",
        "fetch_interval_s:",
        "crawl_delay_declared:",
    ):
        assert key in body


def test_all_six_templates_are_listed_in_canonical_order():
    lines = [l.strip() for l in _manifest().to_yaml().splitlines() if l.startswith("  ")]
    assert [l.split(":")[0].strip('"') for l in lines] == list(TEMPLATES)


def test_template_keys_survive_a_yaml_round_trip_as_strings():
    """Bare `404:` parses as an integer key; consumers index by string."""
    yaml = __import__("importlib").import_module("yaml")
    parsed = yaml.safe_load(_manifest().to_yaml())
    assert set(parsed["templates"]) == set(TEMPLATES)
    assert parsed["templates"]["404"]["crawl"] == "captured"


def test_an_undetected_tool_version_reads_pending_not_a_guess():
    body = _manifest(lighthouse_version=None, chrome_version=None).to_yaml()
    assert "lighthouse_version: PENDING" in body
    assert "chrome_version: PENDING" in body


def test_a_lighthouse_failure_on_one_template_is_recorded_and_the_rest_stand():
    """Spec §7: partial evidence is recorded as partial, never interpolated."""
    templates = {t: {"crawl": "captured", "lighthouse": "ok", "axe": "ok"} for t in TEMPLATES}
    templates["pdp"]["lighthouse"] = "failed"
    body = _manifest(templates=templates).to_yaml()
    assert '"pdp": { crawl: captured, lighthouse: failed, axe: ok }' in body
    assert '"home": { crawl: captured, lighthouse: ok, axe: ok }' in body


def test_the_manifest_hash_is_stable_and_is_the_hash_of_the_written_bytes(tmp_path):
    import hashlib

    path = tmp_path / "manifest.yaml"
    digest = _manifest().write(path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _manifest().write(tmp_path / "again.yaml")


def test_the_manifest_parses_as_yaml():
    yaml = __import__("importlib").import_module("yaml")
    parsed = yaml.safe_load(_manifest().to_yaml())
    assert parsed["schema"] == "manifest/v0.1"
    assert parsed["templates"]["pdp"] == {"crawl": "captured", "lighthouse": "ok", "axe": "ok"}


def test_the_manifest_records_the_delay_declared_and_the_interval_honoured():
    """A slow capture must be explicable from the fixture alone (design D6)."""
    body = _manifest(crawl_delay_declared=10, fetch_interval_s=10).to_yaml()
    assert "crawl_delay_declared: 10" in body
    assert "fetch_interval_s: 10" in body


def test_a_store_declaring_no_delay_records_null_not_a_number():
    yaml = __import__("importlib").import_module("yaml")
    parsed = yaml.safe_load(_manifest().to_yaml())
    assert parsed["crawl_delay_declared"] is None
    assert parsed["fetch_interval_s"] == 1


def test_a_store_declaring_zero_delay_records_zero_not_null():
    """A declared 0 is not an absence — conflating them is the evidence layer
    interpreting rather than recording."""
    yaml = __import__("importlib").import_module("yaml")
    parsed = yaml.safe_load(_manifest(crawl_delay_declared=0.0).to_yaml())
    assert parsed["crawl_delay_declared"] == 0
