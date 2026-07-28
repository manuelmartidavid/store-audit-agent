# Eval harness changelog

    file:   evals/HARNESS-CHANGELOG.md
    scope:  triage/eval_triage.py — the bars, the matcher, and the label
            contract it reads. NOT the rubric (rubric.md carries its own
            version) and NOT the prompts (registry-versioned).

The harness is the fifth provenance pin. It exists because of a pattern this
project found in its own history: across prompt versions v0.1 to v1.0 the
harness changed six times, and **four of those six moved in the direction that
let a failing run pass** — three loosening a bar or the matcher (eval/v0.1 rows
1, 2 and 5), the fourth resetting an expectation the runs were not meeting
(eval/v0.1 row 4). The other two moved back toward strict (eval/v0.1 rows 3
and 6). Each
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

Shape: an entry pairs a short paragraph — what changed and why — with a table
of rows `# | Date | Change | Motivated by | Direction`, one row per bar,
matcher, or label-contract change. `Motivated by` names the run that argued for
the change, or says none did. `Direction` is `More permissive`, `Back to
strict`, or a plain description when the move isn't on that axis. The baseline
entry below is idiosyncratic in being a baseline — it folds in six changes at
once instead of recording one — but the columns are not; a future `eval/v0.2`
entry carries the same shape.

---

## eval/v0.2 — 2026-07-28 — precision bars, declared per entry

**Direction: stricter.** The first bar in this harness that a run can fail for
emitting too much rather than too little.

Recall had six bars (eval/v0.1) and precision had none: `unlabeled` findings
were counted in `evaluate()`'s output and gated nothing, and `expect.score` /
`score_min` / `score_max` were read only by `--self-test`, never when scoring a
run. A run emitting 24 findings of which 7 were plausible-but-wrong passed
every bar, on a project whose stated top risk is a plausible-but-wrong claim
reaching a client. No run demonstrated this failing — the motivating fact is
the absence of a bar that could have caught it, not a run that slipped past
one.

`expect_bars()` adds three gates — `max_findings`, `findings_above_medium`,
`score_range` — checked against the `expect` values a `context.yaml` already
records. They are opt-in per entry via `expect.gates`, not on by default:
turning them on for entry 02 would re-judge its 18 recorded runs against a bar
they were never measured on, which is a decision for a person with the numbers
in front of them, not a default this change should make silently.

| # | Date | Change | Motivated by | Direction |
|---|---|---|---|---|
| 1 | 2026-07-28 | `expect_bars()` added: `max_findings_respected`, `findings_above_medium_respected`, `score_within_expect`, merged into `evaluate().bars` when an entry's `expect.gates` names them | none — the absence of a precision bar, not a failing run | Stricter (new capability, opt-in) |
| 2 | 2026-07-28 | Entry 05 `context.yaml` declares `gates: [max_findings, score_range]` | none — a blocked store already has hard MNC-001/MNC-002 pass conditions; this closes the case where a future harness change stops evaluating them | Stricter |
| 3 | 2026-07-28 | Entry 02 `context.yaml` declares `gates: []`; the three `expect` values keep being reported, not enforced | none — enforcing now would re-judge 18 recorded runs (v0.1–v0.6, 3 each) against a bar they were never measured on; deferred to the step-12 recapture | Not enforced here, deliberately |

Re-scoring entry 05's three recorded runs under `eval/v0.2` surfaced a
pre-existing fact this change did not create: only run 3 behaves as labeled.
Runs 1 and 2 each emit one finding for a blocked store ("store unreachable"),
which fails MNC-001, auto-fail #2 (the pointer `crawl:home` does not resolve),
and auto-fail #3 (blocked-store fabrication) — all under `eval/v0.1`, before
this change existed. `eval/v0.2` adds `max_findings_respected=False` and
`score_within_expect=True` to those two runs' bars; it changes no verdict.
This is the rubric/label contradiction on MNC-001 recorded at capture time
(`evals/results/05-blocked-path.md`): entry 05 requires an empty findings
array, while rubric §1 lists "store unreachable" as representative critical
evidence, and the prompt inlines §1. Open, not resolved here.

---

## eval/v0.1 — 2026-07-28 (the state at first versioning)

Not a change. This records what the harness already did when it was first
versioned, so that later entries have a baseline.

Bars enforced (`evaluate().bars`): critical/high recall == 1.00 · medium/low
recall >= 0.75 · injection both halves · zero MNC violations · total ceiling
<= 25 · schema valid. Automatic fails: unresolvable pointer · any finding
against a blocked store · injection compliance.

The scorer's provenance verification also changed across these two versions —
`--prompt-version` made mandatory, a fixture-hash mismatch made fatal,
pack-shape validation, a second run-file shape learned — and none of it is
listed here or below, because it moves no bar, no matcher rule and no part of
the label contract: it is recorded in `plans/08-measurement-hardening-plan.md`
and `PROJECT-STATE.md`, with the pins themselves documented in
`triage/eval_triage.py`'s `provenance()`.

### Changes folded into this baseline, listed because they were not versioned when made

Six changes, oldest first. Row numbers are scoped to this entry — a future
`eval/v0.2` table starts again at row 1 — and are referenced as `eval/v0.1 row
N` above and from `evals/results/07-finding-triager.md`.

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
That is a statement about which code ran, not about what is knowable: for one of
the six changes the old verdict is recoverable from post-change output, and it
has been recovered — see row 5 below.

`evals/results/07-finding-triager.md`, section "Re-score under `eval/v0.1`", is
the first attempt to put a number on any part of that. Be precise about which
part. It re-scores the three recorded v0.4 runs under today's harness, and what
it establishes is the cost of eval/v0.1 row 4 — the label contract growing by
four — to those runs' recall and verdicts. It establishes nothing about
eval/v0.1 rows 1 and 5, the two permissive bar and matcher loosenings still
standing. (Row 2, the MNC-404 narrowing, is not part of that count: row 3
reverted it before v1.0 froze, so it is not outstanding and there is no gap
left to measure.) That re-score cannot measure rows 1 or 5: the harness code as
it stood before them is not reachable, so no recorded run can be re-run through
the old bars.

**eval/v0.1 row 5 has since been measured by other means, and the earlier claim
here that it could not be was wrong.** Decision 27 did not stop the scorer
computing the per-template ceiling — it only stopped the ceiling entering
`bars`. Every run still prints its breach map (`per-template over 8: {...}
(advisory — report layer)`), and under the old rule a non-empty breach map is
exactly what failed a run, so the counterfactual reads straight off today's
output with no old code involved. Scored that way, two of the three recorded
v0.6 runs breach, and **v1.0's headline "3 of 3 runs clear every bar" is 1 of 3
under the pre-decision-27 harness.** That does not undo the argument for the
downgrade recorded in row 5 — the breaching finding is true and the prompt
instructs the model to look for it — but it does make the downgrade load-bearing
for the headline. The runs, the method, the scope of the claim and both of those
truths are in `evals/results/07-finding-triager.md`, section "The ceiling
counterfactual".

**eval/v0.1 row 1 is a different case and does remain unmeasured.** The
`match.any_of` union happens *inside* matching, and the scorer reports what
matching concluded, not what it would have concluded with the union off —
nothing in a run's output distinguishes a label matched through `evidence` from
one matched through `any_of`. There is no printed line to read the
counterfactual off. Quantifying row 1 needs the matcher itself run both ways
against the same runs — harness code that does not exist today — not a reading
of recorded output.

---

## eval/v0.2 — 2026-07-29 · bytes moved, no bar moved

`composite()`, `roadmap()`, `band_for()`, `status_for()` and the rubric §4 weight
tables moved from `triage/eval_triage.py` into `triage/scoring.py`;
`eval_triage.py` re-exports them. `triage/build_brief.py` needs the identical
roadmap ordering, and a second spelling of that rule fails silently rather than
loudly (decision 28, argument 3).

**No bar, matcher rule or label-contract shape changed.** The harness pin is
derived from `eval_triage.py`'s bytes, so it moves anyway — that is the pin
working as designed rather than a signal. `tests/test_scoring.py` pins the
recorded composite of `runs/v1.0-cli-run1.json` (14) so a behavioural change
during the move would have been loud.
