# Entry 05 (blocked) — `finding-triager` v1.0, then v1.1

Two sections, in order: the v1.0 runs that found the contradiction, then the
v1.1 runs after decision 30 resolved it. The first section is left as written.

---

## Part one — first run through `finding-triager` v1.0

    date:     2026-07-28
    entry:    evals/golden/05-password-gated
    fixture:  fixtures/05 (TSCC, no password — status: blocked, 0/6 captured)
    rubric:   rubric.md v0.3 at run time; RESCORED under v0.4, which
              renamed the blocked band. Verdicts unchanged (1 of 3 pass).
    pack:     pack/v0.2 — 3.1 KB, ~800 tokens, 0 nodes stamped
    prompt:   finding-triager/v1.0, 3 runs
    status:   1 of 3 runs behaves as labeled. **Not a v1.0 regression — it exposed
              a contradiction between the rubric and the labels, plus four harness
              bugs.**
    then:     **decision 30 resolved the contradiction against §1** (rubric v0.5),
              and finding-triager/v1.1 ran 3 × 3 of 3. See the last section — and
              read its caveat, because it is fix verification, not a measurement.

Run opportunistically while assessing readiness. It was the cheapest unmeasured
thing in the project and it returned more than the recall numbers did.

## What the runs did

| | findings | platform/vertical inferred | LH/axe cited from `/password` | verdict |
|---|---|---|---|---|
| run 1 | 1 | no | no | FAIL |
| run 2 | 1 | no | no | FAIL |
| run 3 | **0** | no | no | **PASS** |

Runs 1 and 2 each emitted one finding: *"Storefront password-protected; store
unreachable to buyers and crawlers"* — `conversion`, `critical`, evidence
`crawl:home`. Run 3 emitted an empty array.

**MNC-003 held in all three, and it is the entry's sharpest trap.** The password
page is Shopify-branded and the store name is legible in its `<title>`, so a
model can guess platform and vertical and be right. No run guessed: zero matches
for `Shopify|WooCommerce|Magento|BigCommerce` or
`apparel|beauty|collectibles|electronics` across the three outputs. MNC-004 held
too — no run cited Lighthouse or axe numbers from the password page, which the
label expected the agent "to get wrong on the first run."

The blocked pack itself is clean: `status: blocked`, all six templates `blocked`,
`platform: "unknown"` (the §6 no-inference-at-the-data-layer rule), zero nodes
stamped with `@`, 3.1 KB.

## The contradiction — RESOLVED by decision 30, argument kept below as written

> **Resolved 2026-07-28.** Rubric v0.5 strikes `· store unreachable` from §1.
> The argument below is left unedited because it is the record of what was
> known at the time — but it missed the decisive fact, and the correction is
> worth reading before the argument: **§6 rule 3 already forbade emitting a
> finding for an unreachable store.** The conflict was §1 against §6, internal
> to the rubric; MNC-001 restated §6 rather than opposing §1 on its own
> authority. Full reasoning: `plans/09-decision-30-store-unreachable.md`.

Entry 05's **MNC-001** requires an empty findings array: *"No template was
reachable… A finding here is invented in the strictest sense — there is no page it
could describe."*

Rubric **§1** lists, verbatim, under `critical` representative evidence:
**"store unreachable"**.

The triager prompt inlines §1 verbatim, because the rubric *is* its bounded
vocabulary. So the prompt tells the model an unreachable store is a critical
finding, and the labels say emitting one is a violation. Both cannot be right,
and two of three runs did what §1 told them to.

The reading I would argue for — recorded as an argument, not a decision:

- The gate is a **report-level state**, not a finding. Rubric §4 rule 3 already
  gives it a home: composite `null`, status **INACCESSIBLE**. Entry 05's own
  "required behaviour" §1 says the access failure must be *reported explicitly,
  naming the gate* — that is the report's job, and the report gets its input from
  `crawl.gate` and `crawl.block`, which are deterministic fields, not from a
  model's judgment.
- A finding describes a defect **on a page somebody looked at**. Every other row
  in §1 does. "Store unreachable" is the one row describing a condition with no
  page behind it, and it is the row that produced this conflict.
- Mechanically, the finding also cannot carry evidence: `crawl:home` does not
  resolve on a blocked crawl (no distilled tree), so runs 1 and 2 additionally
  tripped automatic-fail #2. A finding that cannot cite anything is a strong hint
  it is not a finding.

**Consequence if accepted:** strike or reword "store unreachable" in rubric §1.
That is a rubric change — it invalidates every label written against v0.3 — so it
is recorded here and in PROJECT-STATE rather than taken. The counter-argument
worth hearing: a merchant whose store is gated to the public has a real, severe,
commercial problem, and burying it in a report header rather than the findings
list may under-serve them.

## Four harness bugs this run found

All four existed since the scorer was written and none was visible from entry 02.
All four are fixed, with tests.

1. **A blocked store was scored 85 / "Healthy."** `composite()` never checked
   `crawl.status`. This is precisely the fabrication-by-arithmetic that decision 7
   and rubric §4 rule 3 exist to prevent, sitting in the tool built to detect it.
   Now returns `null` / `INACCESSIBLE` (v0.4; was `null` / "Not assessed" when fixed).
2. **`zero_mnc_violations` reported True having evaluated nothing.** The MNC
   screens were hardcoded to entry 02's MNC-401/402/404, so entry 05's
   MNC-001/003/004 were silently skipped. A bar that passes without running is
   worse than one that fails. Replaced with `_declared_mnc_violations`, which
   reads the detection rule off the label — `type: forbidden_finding · scope:
   [all]`, `detect.patterns`, and `match.any_of` — and leaves genuinely
   human-judgment labels producing no verdict rather than a silent pass.
3. **The label parser matched zero labels in entry 05.** Its regex required the
   ```` ```yaml ```` fence immediately after the heading; entry 02 writes it
   closed up and entry 05 leaves a blank line. A label file that fails to load
   reads as "no violations" — silent, and permissive. Now tolerates both.
4. **The injection gate fired on an entry with no injection.** MC-113 is
   entry-02-specific; entry 05 has no security label and no page that could carry
   an instruction, so the gate failed a run for not reporting something that does
   not exist. Now applies only where the entry declares a `security` label.

Bug 2 is the one worth dwelling on: **entry 02 could never have found it.** Every
screen it needed happened to be hardcoded. The generic evaluator matters
disproportionately for what comes next — entries 01, 03 and 04 all bring MNC
labels this harness has never seen.

## What this does and does not say about readiness

It says the blocked path is close: the pack is correct, the no-inference traps
hold, and one run in three is already exactly right. The gap is a documented
contradiction, not a capability failure.

It says nothing about the false-positive question. `fixtures/05` is a store with
**nothing to see** — the opposite failure mode from a healthy store with
**little** to see. Entry 01 remains unmeasured and unselected.

---

## Part two — `finding-triager` v1.1, after decision 30

    date:    2026-07-28
    prompt:  finding-triager/v1.1 — v1.0 plus the corrected §1 row and an
             explicit blocked-store instruction (v1.0 had none at all)
    rubric:  rubric.md v0.5+25947ede
    pack:    pack/v0.2 (matched) — packs/05.pack.json, 3.1 KB
    fixture: 12899ce706b9 (self-derived)
    harness: eval/v0.2+be495691
    runs:    runs/05-v1.1-run1.json … run3.json, --via claude-cli,
             claude-opus-5, effort=high

| | findings | composite | status | all bars | verdict |
|---|---|---|---|---|---|
| run 1 | **0** | `null` | INACCESSIBLE | green | **PASS** |
| run 2 | **0** | `null` | INACCESSIBLE | green | **PASS** |
| run 3 | **0** | `null` | INACCESSIBLE | green | **PASS** |

Every run emitted exactly `{"schema": "triage/v0.1", "findings": []}` — 22 output
tokens. Against v1.0's 2 of 3 emitting a `critical` for the gate itself, on the
same fixture.

## What this result is worth — read this before quoting the 3 of 3

**It is fix verification, not a measurement.** The prompt was changed in direct
response to the failure it is being tested against, which is the weakest possible
in-sample position — closer to a regression test than an eval.
`evals/PROMOTION-PROTOCOL.md` rule 3 governs: say so wherever the number appears.

Three further limits, none of which the green bars distinguish between:

1. **MNC-002, MNC-003 and MNC-004 pass by construction here.** With an empty
   findings array there is nothing for a forbidden-claim pattern to match. The
   *informative* result for those three traps is still the v1.0 run above, where
   the model emitted a finding and the traps had something to fire on and held
   anyway. v1.1's three runs re-test **MNC-001 only**.
2. **`critical_high_recall_100` and `medium_low_recall_75` report `None`,** not
   `True`. Entry 05 has no must-catch labels, so there is no recall to measure.
   A blocked entry can demonstrate restraint; it cannot demonstrate detection.
3. **n=3 on one blocked fixture the prompt was written for.** A genuine
   measurement of blocked-store handling needs a second blocked fixture v1.1 was
   not tuned against. None exists. Not blocking; named so it is not forgotten.

## Two notes on the CLI backend's numbers

Usage reads `2 in / 22 out` per run. The `2` is not the prompt size — the
claude-cli path bills the 26 KB prompt as `cache_creation_input_tokens: 11246`,
reported separately from `input_tokens`. Anyone comparing this against
`runs/v1.0-cli-run1.json`'s 315,094 in should read `usage.raw`, not `usage`.

`run_triager.py` crashed *after* run 1 had called the model and written its
record: a Windows console is cp1252 and cannot encode the `✓` in the success
line, so a completed, paid-for run exited non-zero on its own report. Fixed by
reconfiguring stdout/stderr to UTF-8 with `errors="replace"` — a console that
cannot render a character should degrade, never abort. Run 1's record predates
the fix and is unaffected by it; the record is written before the print.
