# Entry 05 (blocked) — first run through `finding-triager` v1.0

    date:     2026-07-28
    entry:    evals/golden/05-password-gated
    fixture:  fixtures/05 (TSCC, no password — status: blocked, 0/6 captured)
    rubric:   references/rubric.md v0.3
    pack:     pack/v0.2 — 3.1 KB, ~800 tokens, 0 nodes stamped
    prompt:   finding-triager/v1.0, 3 runs
    status:   1 of 3 runs behaves as labeled. **Not a v1.0 regression — it exposed
              a contradiction between the rubric and the labels, plus four harness
              bugs.**

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

## The contradiction — needs a call, do not resolve by inference

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
  gives it a home: composite `null`, band **Not assessed**. Entry 05's own
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
   Now returns `null` / "Not assessed".
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
