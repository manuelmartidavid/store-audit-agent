"""One calibrated character→token estimate, and the context windows it is checked against.

Why this is its own module: three call sites print or act on a token figure —
the packer's `--stats`, the renderer's one-line summary, and the runner's
preflight. A figure that carries its basis has to carry the *same* basis in all
three, and a constant copied three times is three places for the number to
drift away from the thing that justifies it.

THE BASIS — one measurement, not a rule of thumb:

    runs/v1.0.rendered.md        582,452 characters, as the runner reads it
                                 (text mode, LF — that is the string sent)
    runs/v1.0-cli-run1.json      315,094 prompt tokens, the model's own count
                                 (`run_meta.usage.raw.cache_creation_input_tokens`;
                                  `input_tokens` was 2 and `cache_read_input_tokens`
                                  0, so essentially the entire prompt was one cold
                                  cache write and that field *is* the prompt)
                             →   1.8485 characters per token

`CHARS_PER_TOKEN` below is derived from those two integers rather than typed in,
so the ratio cannot drift away from the evidence it came from.

WHAT THIS REPLACES, AND WHY IT WAS WRONG. Both call sites assumed 4 characters
per token, which printed "~145k tokens est." for a prompt that measured 315k —
wrong by 2.16x. The reason is not mysterious and is worth writing down so nobody
re-derives it: 4 chars/token is a rule of thumb *for prose*. The pack is dense
JSON — quotes, braces, sha256 digests, URLs, CSS selectors, `@` pointers — and
dense JSON tokenizes far worse than prose does.

WHAT THIS DOES NOT CLAIM. This is one datapoint, from entry 02's pack rendered
through finding-triager/v1.0 at `--indent 0`. A different fixture, a different
template, or the default minified render will tokenize at a different density,
and nothing here measures that. Three ways the number is soft — all small, all
named so a later reader does not have to rediscover them:

  * 315,094 is the whole *request*, so it includes roughly 1.7k tokens of Claude
    Code harness context (`run_meta.comparability` on that run). The prompt on
    its own is marginally cheaper than 1.8485 c/t implies, so this estimator errs
    high by about half a percent. Erring high is the safe direction for a guard.
  * It was measured on an `--indent 0` render — one newline per JSON element. The
    default minified render of the same pack is ~4.5% fewer characters.
  * The pack is 96% of the rendered prompt's characters (561,754 of 582,452), so
    this ratio is dominated by pack density. That is why the packer reuses it,
    with the same caveats, rather than keeping a second constant.

Everything derived here is an ESTIMATE and every caller prints it as one. The
only measurement in this file is the pair of integers below.
"""

from __future__ import annotations

# The two measured integers. Do not "simplify" these into a single float — the
# point of keeping both is that the ratio is checkable against its source.
CALIBRATION_CHARS = 582_452
CALIBRATION_TOKENS = 315_094
CALIBRATION_SOURCE = (
    "runs/v1.0.rendered.md (582,452 chars) vs runs/v1.0-cli-run1.json "
    "(315,094 tokens) — entry 02, finding-triager/v1.0, claude-opus-5"
)

#: ~1.85. Calibrated on entry 02's pack; see the module docstring before reusing it.
CHARS_PER_TOKEN = CALIBRATION_CHARS / CALIBRATION_TOKENS

# Context windows, from the `claude-api` skill (Current Models table, cached
# 2026-06-24; `shared/models.md`). Recorded here rather than looked up at call
# time because the preflight must work with no network and no API key.
#
# For every model in this table the window is the model's default *and* its
# maximum — there is no separate 1M model id and no beta header to send. The
# skill is explicit for the model this repo targets: "1M context window (default
# and maximum), 128K max output" (`shared/models.md`) and "1M context (default,
# no beta header)" (`shared/model-migration.md` → Migrating to Claude Opus 5).
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

# How close to the window the estimate is allowed to get before it stops being
# able to answer the question. This is a judgement, not a measurement: the ratio
# above rests on one fixture, so a different pack's density could plausibly move
# an estimate by this much, and nothing measured says the error is exactly 10%.
# Below the band, send. Inside it, warn and send — refusing on an estimate that
# cannot tell which side of the line it is on would be the same overreach this
# module exists to stop. Above it, refuse: no plausible calibration error
# rescues a prompt that far over.
GREY_ZONE = 0.10


def _chars(text_or_chars: str | int) -> int:
    return len(text_or_chars) if isinstance(text_or_chars, str) else int(text_or_chars)


def estimate_tokens(text_or_chars: str | int) -> int:
    """Characters → an estimated token count. An estimate; see the module docstring.

    Integer arithmetic on the two calibration constants, so the returned figure
    is exactly `chars × 315094 / 582452` and nothing is hidden in a rounded
    float constant.
    """
    return round(_chars(text_or_chars) * CALIBRATION_TOKENS / CALIBRATION_CHARS)


def thousands(tokens: int) -> str:
    """`315094` → `315k`. Below 1000 the rounding would read as zero, so don't."""
    return f"{tokens / 1000:.0f}k" if tokens >= 1000 else str(tokens)


def describe(text_or_chars: str | int) -> str:
    """`582,452 chars · ~315k tokens est.`

    The character count travels with the estimate on purpose: it is the one
    number here that was counted rather than inferred, and it lets a reader
    recompute the estimate without trusting this module.
    """
    chars = _chars(text_or_chars)
    return f"{chars:,} chars · ~{thousands(estimate_tokens(chars))} tokens est."


def context_preflight(text_or_chars: str | int, *, model: str) -> tuple[str, str | None]:
    """Would this prompt fit `model`'s context window? Returns (verdict, message).

    Verdicts: `"ok"` (send, no message), `"warn"` (send, but say so), `"refuse"`
    (clearly over), `"unknown"` (no window recorded for this model — say so and
    send; inventing a window would be worse than admitting there isn't one).

    The caller decides what a `"refuse"` costs. This function spends nothing and
    knows nothing about backends — it compares two numbers and says which.
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

    # Stated as facts, not as a verdict sentence: the caller decides whether
    # this becomes "refusing to send" or "sending anyway", and a message that
    # hard-codes one of those reads as a lie under the other.
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
