# Decision 30 — "store unreachable" leaves rubric §1

    file:       plans/09-decision-30-store-unreachable.md
    date:       2026-07-28
    status:     DESIGN — awaiting approval, nothing edited yet
    resolves:   PROJECT-STATE "Open decisions" #1 (MNC-001 vs rubric §1)
    rubric:     v0.4 → v0.5
    prompt:     finding-triager v1.0 → v1.1

---

## 1. The reframing — why the recorded question was the wrong question

The open decision is recorded in three places (`PROJECT-STATE.md`,
`evals/results/05-blocked-path.md`, `evals/golden/05-password-gated/expected/findings.md`)
as *the entry-05 labels contradict the rubric*. It is not. Four things the
existing write-ups do not say:

**1.1 — Rubric §6 already says what MNC-001 says.** Automatic fail #3:

> **Blocked-store fabrication.** Any finding emitted for a store the crawler
> could not access (golden entries #2 and #5, adversarial cases 1–2).

MNC-001 is a restatement of that clause, not an independent claim. The conflict
is **§1 vs §6, internal to the rubric**. The label is downstream of §6 and is not
a party to the dispute — which means the labels are not what has to move.

**1.2 — The triager prompt never inlines §6.** `v1.0` carries §1, §2, §3 and a
procedure. It contains no automatic-fail section and no store-level blocked-store
instruction of any kind. Its only blocked-adjacent line is procedure step 2
(`v1.0.md:392`), which governs a *per-template* `absent` / `blocked_by_robots`
status, not a store-level gate.

So the model was handed exactly one rule about unreachable stores — the §1 row —
and two of three runs applied it correctly.

**1.3 — "1 of 3 pass" is noise, not a pass rate.** Run 3's empty findings array
had no instruction behind it. Nothing in the prompt asked for it. Reading that
run as partial compliance credits the prompt with a behaviour it never specified.

**1.4 — The invalidation cost is smaller than recorded.** No entry-02 label
depends on the row (grep of `evals/golden/02-sabotaged/expected/findings.md` for
`unreachable|blocked|INACCESSIBLE` returns one hit, and it is a v0.4 provenance
note, not a label). And the distiller fix already scheduled as step 11 retires
fixture `b219afac…`, forcing recapture → re-freeze → re-label → re-run. **A §1
edit made now rides a re-measurement that is already on the calendar.** Deferred,
it buys a second one.

---

## 2. The decision

**Strike `· store unreachable` from rubric §1's `critical` representative-evidence
column.** Do not replace it.

The governing design rule settles it: *scripts measure, the model judges.*
Whether the store was reachable is **measured** — `crawl.status` is a
deterministic crawler field, and `triage/eval_triage.py::composite()` already
reads it (that was harness bug 1's fix). Asking the triager to re-report it as a
finding asks the model to judge a fact the script already holds, and it is the
one finding class that can never carry a resolvable evidence pointer, so it also
trips automatic-fail #2 on emission.

**Nothing is lost by striking rather than rewording.** §1's *rule* column reads
"Blocks purchase, or blocks indexing of a revenue template." A cart returning 403
on an otherwise-reachable store is `critical` under that rule with no example row
needed — the right-hand column is representative evidence, not an enumeration.

### The counter-argument, recorded and rejected

A merchant whose storefront is gated to the public has a real and severe
commercial problem, and burying it in a report header rather than the findings
list may under-serve them. This is rejected on the grounds that the gate is
reported *more* reliably as a crawl fact than as a model judgment: §4 rule 3
gives it `score: null` / `status: INACCESSIBLE` / band `Inaccessible`, and entry
05's own required-behaviour #1 obliges the report to name the gate explicitly. A
deterministic field states it every time; a model emitted it two times in three.

---

## 3. Where reachability travels — the gap this must close first

`evals/results/05-blocked-path.md` justifies striking the row by saying the gate
"is a report-level state" the report picks up from `crawl.gate` / `crawl.block`.
**That is not currently true, and it is the one real cost of this decision.**

`triage/v0.1` has two fields: `schema` and `findings`. A blocked store's triage
output is `{"schema":"triage/v0.1","findings":[]}` — byte-identical to a spotless
store's. And `specs/triager-io.md` defines no report-composer input contract, so
"the composer will read the pack" is an assumption rather than an interface.

Strike the row without addressing this and store-level reachability is
representable nowhere between the crawl and the report.

**Fix, chosen for being the cheapest correct one: do not add a field.** State
explicitly that the composer's input is **(pack, triage)**, not triage alone, and
that store-level reachability reaches the report through `crawl.status` — the
same path the scorer already uses. `triage/v0.1` stays frozen and byte-compatible;
no recorded run is touched.

The alternative — a `store_status` field on `triage/v0.1` — is rejected: it would
be a schema change to a frozen contract that 22 recorded runs are scored against,
in order to carry a value the model must not be the source of anyway.

---

## 4. Change set

| # | File | Change |
|---|---|---|
| 1 | `rubric.md` | v0.4 → **v0.5**. Strike `· store unreachable` from §1's `critical` row. Add §1 tie-break rule 6 stating that a finding describes a template that was captured, and pointing store-level reachability at §4 rule 3 / §6 rule 3. Fix §6 rule 3's stale parenthetical (it names "golden entries #2 and #5"; entry 02 is fully accessible — `status: complete`, 6/6). Add a v0.5 scope note in the shape of v0.4's. |
| 2 | `prompts/finding-triager/v1.1.md` | v1.0 with the corrected §1 table row, plus an explicit blocked-store instruction: if `crawl.status` is `blocked`, emit `findings: []`. Front matter pins `rubric.md v0.5`. |
| 3 | `specs/triager-io.md` | Additive clause: reachability never travels through `triage/v0.1`; the composer's input is (pack, triage). No field, clause or rule changed. |
| 4 | `evals/golden/05-password-gated/expected/findings.md` | Delete the `## OPEN` block. Rewrite MNC-001's `reason` to cite §6 rule 3 as its source rather than standing alone. Header records the resolution. |
| 5 | `evals/results/05-blocked-path.md`, `PROJECT-STATE.md`, `prompts/README.md` | Record decision 30; open decisions 3 → 2; registry gains v1.1 with its measurement scope stated. |

### Deliberately not changed

- **`evals/HARNESS-CHANGELOG.md` gets no entry.** Its stated scope is
  `triage/eval_triage.py` — the bars, the matcher and the label contract —
  and explicitly **not** the rubric, which carries its own version. No bar,
  matcher rule or label-contract shape changes here. Saying this out loud
  because a silent skip and a reasoned skip look identical in a diff.
- **No recorded verdict changes.** Entry-05 runs 1 and 2 still fail MNC-001;
  run 3 still passes. What changes is that runs 1 and 2 are no longer defensible
  by citing the prompt. The 1-of-3 in the record stands, re-read.
- **Entry 02 is untouched.** 17 must-catch labels, composite 24, band Critical,
  18 recorded runs — all unaffected in substance.
- **Frozen prompts v0.1–v1.0 stay frozen** and keep pinning `rubric.md v0.3`.
  Their bytes are a provenance pin (decision 12); they remain valid *as run*.

---

## 5. Invalidation analysis — the honest version

v0.4 was presentation-only: it touched §4 and the bands table, none of which the
prompt inlines. **v0.5 is not.** It edits §1, which every prompt version carries
verbatim. Consequences, stated rather than implied:

- **Every prompt through v1.0 now carries a §1 that differs from the current
  rubric by one list item.** They stay frozen and their recorded results stand,
  because a result is a tuple pinned to the rubric version it ran under
  (decision 12) — `rubric_version()` derives from the file's bytes, so v0.5's
  digest will differ and the pin will say so.
- **v1.1's entry-02 behaviour is unmeasured** and must not inherit v1.0's
  "3 of 3 at 17/17". The registry will say v1.1 is measured on entry 05 only.
  Entry-02 re-measurement happens in the capture wave (step 13), which was
  already required.
- **No golden label is invalidated.** This is the narrow kind of rubric change,
  like v0.4 — but for a different reason. v0.4 was narrow because it missed the
  inlined sections; v0.5 is narrow because the clause it edits is one no label
  in the golden set was written against.

---

## 6. Verification, and what it is worth

Run `finding-triager/v1.1` three times against `fixtures/05` through
`triage/run_triager.py --via claude-cli`, scored by `triage/eval_triage.py`.

**Pass bar:** 3 of 3 emit `findings: []`; MNC-002, MNC-003 and MNC-004 hold in
all three; composite `null`, status `INACCESSIBLE`, band `Inaccessible`.

**What this measurement is worth, stated up front:** the prompt is being changed
in direct response to the observed failure, so this is *fix verification*, not an
independent measurement of a capability. It is the weakest kind of in-sample
result — closer to a regression test than an eval — and it will be recorded as
such in `evals/results/05-blocked-path.md`. PROMOTION-PROTOCOL rule 3's
discipline applies: say so wherever the number appears.

A genuine measurement of blocked-store handling requires a second blocked fixture
the prompt was not tuned against. None exists. Not blocking; worth naming.

---

## 7. Flagged judgment calls

1. **Editing a frozen spec.** `specs/triager-io.md` declares itself frozen.
   Change 3 is additive — it names a downstream layer's input and changes no
   field, clause or rule — and follows the precedent of the file's own
   2026-07-28 paths-only amendment, which is recorded in its header the same way.
   Called out rather than assumed.
2. **The composer contract is being asserted, not built.** Nothing consumes
   (pack, triage) yet, because the composer does not exist. This decision writes
   down the interface it must have; it does not verify one.
3. **v1.1 changes two things at once** — the §1 row and a new blocked-store
   instruction. They are not separable: correcting §1 alone leaves the model with
   *no* instruction for a blocked store, which is how run 3's empty array came to
   be an accident rather than a behaviour.
