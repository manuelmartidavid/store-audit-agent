"""Lighthouse result assembly — spec §7 partial-evidence handling.

The browser-driving parts are covered by the integration suite; what is pure and
worth pinning here is the classification that a load error is a *failure*, not a
success — the bug that recorded four ERRORED_DOCUMENT_REQUEST audits as `ok`.
"""

from __future__ import annotations

from crawler.lighthouse import assemble


def _lhr(version="12.8.2"):
    return {"lighthouseVersion": version, "categories": {"performance": {"score": 0.9}}}


def test_successful_runs_contribute_an_lhr_and_read_ok():
    result = assemble(
        [{"template": "home", "ok": True, "lhr": _lhr()}],
        detected_version="12.8.2",
    )
    assert result.status == {"home": "ok"}
    assert len(result.lhrs) == 1
    assert result.errors is None


def test_an_errored_run_is_failed_kept_out_of_the_lhr_array_and_carries_its_error():
    """A sidecar `ok: false` (a runtimeError load failure) is not evidence."""
    result = assemble(
        [
            {"template": "home", "ok": True, "lhr": _lhr()},
            {"template": "pdp", "ok": False, "error": "ERRORED_DOCUMENT_REQUEST: unable to load"},
        ],
        detected_version="12.8.2",
    )
    assert result.status == {"home": "ok", "pdp": "failed"}
    assert len(result.lhrs) == 1, "the errored template contributes no LHR"
    assert "pdp" in result.errors and "ERRORED_DOCUMENT_REQUEST" in result.errors["pdp"]


def test_a_failure_without_an_error_message_still_reads_failed():
    result = assemble([{"template": "cart", "ok": False}], detected_version="12.8.2")
    assert result.status == {"cart": "failed"}
    assert result.errors["cart"]


def test_the_version_falls_back_to_the_lhrs_own_field_when_undetected():
    result = assemble([{"template": "home", "ok": True, "lhr": _lhr("12.9.9")}], detected_version=None)
    assert result.version == "12.9.9"


def test_all_failed_yields_no_lhrs_and_no_version_guess():
    result = assemble([{"template": "home", "ok": False, "error": "x"}], detected_version=None)
    assert result.lhrs == []
    assert result.version is None
