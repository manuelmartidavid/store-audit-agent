"""Estimates how many tokens a prompt costs, and checks it against context windows.

The ratio comes from one real measurement: a 582,452-character rendered prompt
that the model counted as 315,094 tokens, or about 1.85 characters per token.
Three call sites share it — the packer's `--stats`, the renderer's summary, and
the runner's preflight.

Invariant: the ratio is one datapoint, from entry 02's pack at `--indent 0`.
Another fixture or template will tokenize differently, so treat every figure
here as an estimate and print it as one.

Invariant: don't go back to the 4-chars-per-token rule of thumb. That's a
figure for prose; the packs are dense JSON and it was wrong by more than 2x.
"""

from __future__ import annotations

# Invariant: keep these as two integers rather than one float, so the ratio
# stays checkable against the measurement it came from.
CALIBRATION_CHARS = 582_452
CALIBRATION_TOKENS = 315_094
CALIBRATION_SOURCE = (
    "runs/v1.0.rendered.md (582,452 chars) vs runs/v1.0-cli-run1.json "
    "(315,094 tokens) — entry 02, finding-triager/v1.0, claude-opus-5"
)

#: ~1.85, calibrated on entry 02's pack.
CHARS_PER_TOKEN = CALIBRATION_CHARS / CALIBRATION_TOKENS

# Context windows, listed here rather than looked up so the preflight works with
# no network and no API key. For every model below this is both the default and
# the maximum — no separate model id, no beta header.
CONTEXT_WINDOWS = {
    "claude-opus-5": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-fable-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-4-5": 200_000,
}

# How close to the window an estimate can get before it stops being able to
# answer the question. Below the band, send. Inside it, warn and send. Above it,
# refuse. The 10% is a judgement call, not a measurement.
GREY_ZONE = 0.10


def _chars(text_or_chars: str | int) -> int:
    """Accept either a string or a character count and return the count."""
    return len(text_or_chars) if isinstance(text_or_chars, str) else int(text_or_chars)


def estimate_tokens(text_or_chars: str | int) -> int:
    """Estimate how many tokens some text costs."""
    return round(_chars(text_or_chars) * CALIBRATION_TOKENS / CALIBRATION_CHARS)


def thousands(tokens: int) -> str:
    """`315094` → `315k`. Left alone below 1000, where rounding would read as zero."""
    return f"{tokens / 1000:.0f}k" if tokens >= 1000 else str(tokens)


def describe(text_or_chars: str | int) -> str:
    """A one-line summary: `582,452 chars · ~315k tokens est.`

    The character count travels with the estimate because it's the only figure
    here that was counted rather than inferred.
    """
    chars = _chars(text_or_chars)
    return f"{chars:,} chars · ~{thousands(estimate_tokens(chars))} tokens est."


def context_preflight(text_or_chars: str | int, *, model: str) -> tuple[str, str | None]:
    """Would this prompt fit `model`'s context window? Returns (verdict, message).

    Verdicts: `ok` (send), `warn` (send, but say so), `refuse` (clearly over),
    `unknown` (no window on file for this model). The caller decides what to do
    with each; this just compares two numbers.
    """
    chars = _chars(text_or_chars)
    estimate = estimate_tokens(chars)
    window = CONTEXT_WINDOWS.get(model)
    basis = (f"{chars:,} characters at {CHARS_PER_TOKEN:.2f} chars/token, "
             f"calibrated on entry 02 — see triage/token_estimate.py")

    if window is None:
        known = ", ".join(sorted(CONTEXT_WINDOWS))
        return "unknown", (
            f"no context window is recorded here for {model!r}, so the prompt "
            f"cannot be checked against one. Estimated {estimate:,} tokens "
            f"({basis}). Sending unchecked. Windows on file: {known}.")

    # Worded as facts, not decisions — the caller chooses whether this becomes
    # "refusing to send" or "sending anyway".
    if estimate > window * (1 + GREY_ZONE):
        return "refuse", (
            f"the prompt is an estimated {estimate:,} tokens "
            f"({basis}) and {model} has a {window:,}-token context window — "
            f"over by {estimate / window - 1:.0%}. This figure is an estimate, "
            f"not a token count; it rests on one measured fixture and could be "
            f"wrong for this one. Send a smaller pack, or target a model with a "
            f"larger window, or pass --ignore-context-window if you have reason "
            f"to believe the estimate rather than the window is what is wrong.")

    if estimate > window * (1 - GREY_ZONE):
        return "warn", (
            f"within {GREY_ZONE:.0%} of the limit: an estimated {estimate:,} "
            f"tokens ({basis}) against {model}'s {window:,}-token window. At "
            f"this range the estimate cannot tell you which side of the line "
            f"you are on, so this is a warning and not a refusal. Sending.")

    return "ok", None
