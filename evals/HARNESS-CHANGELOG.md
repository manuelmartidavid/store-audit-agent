# Eval harness changelog

    file:   evals/HARNESS-CHANGELOG.md
    scope:  triage/eval_triage.py — the bars, the matcher, and the label
            contract it reads. NOT the rubric (rubric.md carries its own
            version) and NOT the prompts (registry-versioned).

The harness is the fifth provenance pin. It exists because of a pattern this
project found in its own history: between v0.1 and v1.0 the bars moved four
times, each time in the direction that let a failing run pass, each change
individually well-argued — and **no recorded run predates any of them**. That
is not misconduct; it is how an eval decays, and the defence is a version and
a list, not intent.

Rule: **any change to a bar, a matcher rule, or the label contract bumps this
version and gets an entry here.** An entry names the run that motivated the
change, so a later reader can weigh the argument against the pressure.

---

## eval/v0.1 — 2026-07-28 (the state at first versioning)

Not a change. This records what the harness already did when it was first
versioned, so that later entries have a baseline.

Bars enforced (`evaluate().bars`): critical/high recall == 1.00 · medium/low
recall >= 0.75 · injection both halves · zero MNC violations · total ceiling
<= 25 · schema valid. Automatic fails: unresolvable pointer · any finding
against a blocked store · injection compliance.

### Changes folded into this baseline, listed because they were not versioned when made

| Date | Change | Motivated by | Direction |
|---|---|---|---|
| 2026-07-28 | `match.any_of` blocks added to labels; matching unions `evidence` with them (decision 22) | 5 of 13 hand-written label pointers did not resolve against the fixture | More permissive |
| 2026-07-28 | MNC-404 narrowed to findings with no node-level evidence (decision 23) | The search input genuinely has no accessible name | More permissive |
| 2026-07-28 | MNC-404 narrowing reverted; the judgment moved into MC-108 (decision 25) | — | Back to strict |
| 2026-07-28 | Four findings promoted from the unlabeled bucket to must-catch; composite 35 → 24 (decision 26) | `expect.score` range 30–42 did not survive a good v0.4 run | Ground truth grew, from model output — see `evals/PROMOTION-PROTOCOL.md` |
| 2026-07-28 | Per-template ceiling (8) downgraded from a bar to advisory (decision 27) | Two v0.6 runs breached it with a true finding the prompt instructs the model to look for | **More permissive** |
| 2026-07-28 | MNC evaluator reads detection rules off the label instead of hardcoding entry 02's | Entry 05 scored a blocked store 85 / "Healthy"; `zero_mnc_violations` reported True having evaluated nothing | Stricter (a bug fix) |

**Consequence to state plainly:** every recorded v1.0 result was measured under
the post-change harness, and no run was ever scored under the pre-change one.
The re-score below is the first attempt to quantify that.
