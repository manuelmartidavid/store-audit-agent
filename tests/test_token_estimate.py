"""triage/token_estimate.py — the one place a printed token figure gets its basis.

What is worth testing here is not the arithmetic (it is one multiply) but the
two things that made the old estimator misleading: that the ratio still matches
the measurement it claims to come from, and that the guard built on it refuses
only when it can actually tell.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from triage import token_estimate  # noqa: E402

RENDERED = ROOT / "runs" / "v1.0.rendered.md"

# The measurement this module is calibrated against, restated here rather than
# imported, so the test fails if someone edits the constants to fit a number
# instead of editing them because a new measurement was taken.
MEASURED_CHARS = 582_452
MEASURED_TOKENS = 315_094


def test_the_calibration_constants_are_still_the_measured_pair():
    assert token_estimate.CALIBRATION_CHARS == MEASURED_CHARS
    assert token_estimate.CALIBRATION_TOKENS == MEASURED_TOKENS
    assert token_estimate.CHARS_PER_TOKEN == pytest.approx(1.8485, abs=0.0005)
    # The provenance travels with the number or the number is just a number.
    assert "v1.0-cli-run1.json" in token_estimate.CALIBRATION_SOURCE


def test_the_estimator_reproduces_its_own_measurement():
    """Round-trip: the datapoint it is calibrated on must come back out exactly."""
    assert token_estimate.estimate_tokens(MEASURED_CHARS) == MEASURED_TOKENS


@pytest.mark.skipif(not RENDERED.exists(),
                    reason="runs/v1.0.rendered.md is gitignored; run where the render lives")
def test_the_estimate_lands_on_the_real_rendered_prompt():
    """The end-to-end check, against the artefact the model actually read.

    Read in text mode on purpose — that is how run_triager reads it, so that is
    the string the model saw. (On Windows the file is CRLF on disk; counting
    bytes would inflate the character count by ~27k and quietly recalibrate the
    ratio against something nobody ever sent.)
    """
    text = RENDERED.read_text(encoding="utf-8")
    assert len(text) == MEASURED_CHARS
    assert token_estimate.estimate_tokens(text) == pytest.approx(MEASURED_TOKENS, rel=0.01)


@pytest.mark.skipif(not RENDERED.exists(),
                    reason="runs/v1.0.rendered.md is gitignored; run where the render lives")
def test_the_estimate_is_no_longer_the_four_chars_per_token_rule():
    """The specific defect this replaced: 4 chars/token printed 145k for a 315k
    prompt. Guard the correction directly, so reverting the constant fails here
    rather than only showing up as a number nobody recomputes."""
    text = RENDERED.read_text(encoding="utf-8")
    old_rule = len(text) // 4
    assert old_rule == pytest.approx(145_613, abs=1)
    assert token_estimate.estimate_tokens(text) > 2 * old_rule


def test_thousands_does_not_round_small_counts_to_zero():
    assert token_estimate.thousands(315_094) == "315k"
    assert token_estimate.thousands(999) == "999"


def test_describe_prints_the_counted_number_beside_the_inferred_one():
    described = token_estimate.describe(MEASURED_CHARS)
    assert "582,452 chars" in described      # counted
    assert "~315k tokens est." in described  # inferred, and marked as such


# --- the recorded context windows ------------------------------------------

def test_the_target_model_is_recorded_as_a_one_million_token_window():
    """claude-api skill, `shared/models.md`: "1M context window (default and
    maximum)"; `shared/model-migration.md` → Migrating to Claude Opus 5: "1M
    context (default, no beta header)". No separate model id, no beta header —
    which is why this is a plain lookup and not a flag the runner has to send."""
    assert token_estimate.CONTEXT_WINDOWS["claude-opus-5"] == 1_000_000


def test_haiku_is_recorded_as_the_one_small_window_model():
    """A single 200k entry keeps the table honest: the guard is comparing against
    a per-model fact, not against a constant that happens to be 1M everywhere."""
    assert token_estimate.CONTEXT_WINDOWS["claude-haiku-4-5"] == 200_000


# --- the preflight's three outcomes, plus the honest fourth -----------------
#
# Sized in characters against claude-haiku-4-5's 200k window so the arithmetic
# stays readable; the guard does not know or care which model it was handed.

def test_preflight_refuses_a_prompt_clearly_over_the_window():
    verdict, message = token_estimate.context_preflight(500_000, model="claude-haiku-4-5")
    assert verdict == "refuse"
    # The message states facts and leaves the verb to the caller — main() reads
    # it as "refusing to send: …" and, under --ignore-context-window, as
    # "sending anyway …". A message carrying its own verdict would be wrong
    # under one of the two.
    assert "refusing" not in message
    assert "over by 35%" in message
    assert "200,000-token context window" in message
    assert "claude-haiku-4-5" in message
    # A refusal has to say the figure is estimated and on what basis, or the
    # operator cannot tell whether to believe it.
    assert "estimate" in message
    assert "triage/token_estimate.py" in message
    assert "--ignore-context-window" in message


def test_preflight_only_warns_inside_the_grey_zone():
    """370k chars ≈ 200k tokens est. — right on the line. The estimate cannot
    tell which side it is on, so it must not pretend to."""
    verdict, message = token_estimate.context_preflight(370_000, model="claude-haiku-4-5")
    assert verdict == "warn"
    assert "refusing" not in message
    assert "warning and not a refusal" in message


def test_preflight_is_silent_when_the_prompt_plainly_fits():
    verdict, message = token_estimate.context_preflight(582_452, model="claude-opus-5")
    assert verdict == "ok"
    assert message is None


def test_preflight_says_so_rather_than_guessing_an_unknown_model():
    verdict, message = token_estimate.context_preflight(
        582_452, model="claude-something-not-yet-released")
    assert verdict == "unknown"
    assert "no context window is recorded" in message
    assert "unchecked" in message


def test_the_grey_zone_boundaries_are_where_the_constant_says():
    window = token_estimate.CONTEXT_WINDOWS["claude-haiku-4-5"]
    band = token_estimate.GREY_ZONE
    just_under = int(window * (1 - band) * token_estimate.CHARS_PER_TOKEN) - 1_000
    just_over = int(window * (1 + band) * token_estimate.CHARS_PER_TOKEN) + 1_000
    assert token_estimate.context_preflight(just_under, model="claude-haiku-4-5")[0] == "ok"
    assert token_estimate.context_preflight(just_over, model="claude-haiku-4-5")[0] == "refuse"
