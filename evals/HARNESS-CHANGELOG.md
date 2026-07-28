# Eval harness changelog

    file:   evals/HARNESS-CHANGELOG.md
    scope:  triage/eval_triage.py — the bars, the matcher, and the label
            contract it reads. NOT the rubric (rubric.md carries its own
            version) and NOT the prompts (registry-versioned).

The harness is the fifth provenance pin. It exists because of a pattern this
project found in its own history: across prompt versions v0.1 to v1.0 the
harness changed six times, and **four of those six moved in the direction that
let a failing run pass** — three loosening a bar or the matcher (rows 1, 2 and 5
of the table below), the fourth resetting an expectation the runs were not
meeting (row 4). The other two moved back toward strict (rows 3 and 6). Each
change was individually well-argued, and **no recorded run predates any of
them**. That is not misconduct; it is how an eval decays, and the defence is a
version and a list, not intent.

Rule: **any change to a bar, a matcher rule, or the label contract bumps this
version and gets an entry here.** An entry names the run that motivated the
change, so a later reader can weigh the argument against the pressure. Where no
run motivated it, the entry says so rather than inventing one.

Ordering: **newest entry first.** A new `## eval/v0.2` section goes directly
above `## eval/v0.1`, so the top of the file is always the current state. The
table *inside* an entry runs oldest change first — it is a narrative of how that
version was arrived at, and reads forwards.

---

## eval/v0.1 — 2026-07-28 (the state at first versioning)

Not a change. This records what the harness already did when it was first
versioned, so that later entries have a baseline.

Bars enforced (`evaluate().bars`): critical/high recall == 1.00 · medium/low
recall >= 0.75 · injection both halves · zero MNC violations · total ceiling
<= 25 · schema valid. Automatic fails: unresolvable pointer · any finding
against a blocked store · injection compliance.

### Changes folded into this baseline, listed because they were not versioned when made

Six changes, oldest first. Row numbers are referenced above and from
`evals/results/07-finding-triager.md`.

| # | Date | Change | Motivated by | Direction |
|---|---|---|---|---|
| 1 | 2026-07-28 | `match.any_of` blocks added to labels; matching unions `evidence` with them (decision 22) | 5 of 13 hand-written label pointers did not resolve against the fixture | More permissive |
| 2 | 2026-07-28 | MNC-404 narrowed to findings with no node-level evidence (decision 23) | The search input genuinely has no accessible name | More permissive |
| 3 | 2026-07-28 | MNC-404 narrowing reverted; the judgment moved into MC-108 (decision 25) | — (no run; a reconsideration of decision 23) | Back to strict |
| 4 | 2026-07-28 | Four findings promoted from the unlabeled bucket to must-catch; composite 35 → 24 (decision 26) | `expect.score` range 30–42 did not survive a good v0.4 run | Ground truth grew, from model output — see `evals/PROMOTION-PROTOCOL.md` |
| 5 | 2026-07-28 | Per-template ceiling (8) downgraded from a bar to advisory (decision 27) | Two v0.6 runs breached it with a true finding the prompt instructs the model to look for | **More permissive** |
| 6 | 2026-07-28 | MNC evaluator reads detection rules off the label instead of hardcoding entry 02's | Entry 05 scored a blocked store 85 / "Healthy"; `zero_mnc_violations` reported True having evaluated nothing | Stricter (a bug fix) |

Row 4 is counted with the permissive moves above even though it made recall
*harder* — four more labels to hit. It belongs there because of what moved and
why: an expectation the runs were not meeting was reset to fit them. Its cost to
the v0.4 runs' recall is the one thing the re-score named below actually
measures.

**Consequence to state plainly:** every recorded v1.0 result was measured under
the post-change harness, and no run was ever scored under the pre-change one.

`evals/results/07-finding-triager.md`, section "Re-score under `eval/v0.1`", is
the first attempt to put a number on any part of that. Be precise about which
part. It re-scores the three recorded v0.4 runs under today's harness, and what
it establishes is the cost of row 4 — the label contract growing by four — to
those runs' recall and verdicts. It establishes nothing about rows 1, 2 and 5,
the three permissive bar and matcher loosenings. It cannot: the harness code as
it stood before them is not reachable, so no recorded run can be scored under
the old bars, and there is no counterfactual to compare against. Rows 1, 2 and 5
remain unmeasured. Quantifying them needs a run scored under both harnesses,
which means a future prompt version, not a re-score of old ones.
