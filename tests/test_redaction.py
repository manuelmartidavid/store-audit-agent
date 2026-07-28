"""Secret hygiene — spec §2, and acceptance test §10.2 run from the inside."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from crawler.redaction import SecretLeak, assert_absent

SECRET = "gate-p@ss w0rd"


def test_clean_output_passes(tmp_path):
    (tmp_path / "crawl.json").write_text(json.dumps({"gate": "password_supplied"}))
    assert_absent(tmp_path, SECRET)  # no raise


def test_a_leaked_secret_is_fatal_and_the_offending_file_is_deleted(tmp_path):
    leaky = tmp_path / "crawl.json"
    leaky.write_text(json.dumps({"note": f"submitted {SECRET}"}))

    with pytest.raises(SecretLeak):
        assert_absent(tmp_path, SECRET)
    assert not leaky.exists(), "a leaked fixture must not be left on disk to be committed"


def test_url_encoded_forms_are_caught_too(tmp_path):
    (tmp_path / "crawl.json").write_text(f'{{"url": "https://x.test/?p={quote(SECRET)}"}}')
    with pytest.raises(SecretLeak):
        assert_absent(tmp_path, SECRET)


def test_nested_files_are_scanned(tmp_path):
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "axe.json").write_text(SECRET)
    with pytest.raises(SecretLeak):
        assert_absent(tmp_path, SECRET)


def test_no_password_configured_is_not_an_error(tmp_path):
    (tmp_path / "crawl.json").write_text("{}")
    assert_absent(tmp_path, None)
    assert_absent(tmp_path, "")
