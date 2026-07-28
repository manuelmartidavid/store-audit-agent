# `impact-narrator` — design (step 9)

    file:    docs/superpowers/specs/2026-07-29-impact-narrator-design.md
    status:  design, approved 2026-07-29. Not yet implemented.
    scope:   step 9 of PROJECT-STATE "Next steps". One atomic change spanning
             specs/, triage/, prompts/, evals/, tests/.
    reads:   specs/triager-io.md (frozen) · rubric.md v0.5 · evals/PROMOTION-PROTOCOL.md
    writes:  specs/narrator-io.md (new, frozen on acceptance)

---

## Why this step, and why now

`impact-narrator` is the one substantial piece of work that depends on no fixture.
Its upstream contract `triage/v0.1` is frozen, and 19 entry-02 run JSONs already
carry findings, so it can be built and evaluated before the distiller fix retires
fixture `b219afac…`. It also carries the highest guardrail density in the project:
automatic-fail #1 (fabricated statistic) is unreachable at the triage layer by
construction, and lands here.

Two facts discovered during design changed its shape, and both are recorded
before anything else because the rest follows from them.

**1. `references/benchmarks.md` does not exist.** It is cited by rubric §6 rule 1
as the *sole* exemption for automatic-fail #1, by `prompts/README.md` as half the
narrator's declared input, and by entry 02's MNC-403 — which states that
quantification *with* a citation "is expected and correct here". `README.md` and
`plans/08-measurement-hardening-plan.md` both already flag it as not present. The
narrator's only permitted route to a number leads to a file that is not there.

**2. There is no `narrative/v0.x` contract.** The triager got `specs/triager-io.md`
before it got a prompt, and that spec is what the matcher, the scorer and — by its
own line 15 — the narrator code against. The narrator has no equivalent;
"narrative" is undefined everywhere it appears.

It does, however, already have labels waiting for it: MNC-403 (entry 02), MNC-402
(`scope: [findings, narrative, score]`), and entry 05's MNC-002 and MNC-003, both
scoped `narrative`. Nothing reads them — `eval_triage.py` scores triage only.

---

## Decisions taken

### D1 — v0.1 emits no numbers at all

`narrative/v0.1` permits **zero digit characters** in any field value. No
percentages, no currency, no session counts, no durations.

This makes automatic-fail #1 unreachable **by construction** rather than by
instruction — the same structural move `triage/v0.1` made when it refused to carry
an `impact` field, and the move this project has had the most success with. A
prompt that says "do not fabricate statistics" competes with the model's
helpfulness prior; a schema and a gate that admit no digits do not.

Cost, stated rather than hidden: MNC-403's citation-exemption clause stays dormant,
so entry 02 tests only the forbidding half of the rule it was written for.
`benchmarks.md` and quantification become v0.2 — deferred honestly, not assumed
done. Directional language with no number is always permitted by rubric §6 rule 1,
so a number-free narrative is a valid deliverable, not a degraded one.

*Rejected:* writing `benchmarks.md` first (real sourcing work, and it would
confound the narrator's first measurement with a second new artifact); permitting
arithmetic on declared `context.yaml` facts only (invents a second exemption the
rubric does not have — a rubric change, i.e. the loud kind of decision).

### D2 — the output is JSON with bounded named fields per finding

Not one free paragraph per finding, and not a Markdown document.

The triager's own lesson is that bounded fields are enforceable and free prose is
not — `severity_rationale` is capped at 20 words for exactly this reason. Each
field gets its own cap and its own gate, and a claim that fits no field is a claim
the schema will not carry. A Markdown document was rejected because nothing would
be keyed to a finding id, making traceability a parsing problem and forcing the
composer to re-associate prose with findings before it could rank or truncate.

Accepted cost: slot-assembled prose can read mechanical. That is the composer's
problem to solve and decision 3's editing-cost test is the instrument that will
say whether it did — which is why one human read is in scope (see D4).

### D3 — a script ranks, splits and truncates *before* the narrator

This settles a contradiction rather than expressing a preference.
`PROJECT-STATE.md` said the narrator "inherits the per-template report ceiling
(decision 27) — it is the layer that can truncate by roadmap rank";
`specs/triager-io.md` §5 and `README.md` said the ceiling gates the
report-composer. The stated reason in PROJECT-STATE does not hold either way:
roadmap rank is `severity_weight ÷ effort_cost`, which rubric §4 assigns to a
script. Neither the narrator nor the composer computes it.

**Resolution: `triage/build_brief.py` computes rank, splits the finding set, and
truncates to the rubric §5 ceilings. The narrator receives only what the report
will contain, plus an integer overflow count. It never ranks and never truncates.**

This honours *scripts measure, the model judges*; no narration is generated and
then discarded; and the "N additional minor items" line gets a number the model
did not compute. `specs/triager-io.md` §5 stands as written — the cap still gates
the report layer, which now receives an already-capped set. PROJECT-STATE's line
is corrected.

*Rejected:* the narrator ranking and truncating itself — a truncation decision made
in a model's head is not reproducible across runs, which is what decision 6 and
the score-by-script rule exist to prevent.

### D4 — mechanical gates, plus one recorded human read

There is no ground-truth prose to match against, so `triage/eval_narrative.py`
scores only what is mechanically checkable (see §"Gates" below). Separately, one
run gets a recorded human read against decision 3's editing-cost criterion, as a
**baseline, not a gate**.

The human read is in scope because D2 has exactly one stated risk — slot-assembled
prose reading mechanical — and a human read is the only instrument that detects it.
Deferring it to the composer means finding out one layer later, on top of a
foundation already built.

*Rejected:* an LLM judge for prose quality. It violates *scripts measure, the model
judges* in the one direction this project has never allowed, and the judge would
itself need validating against human reads — strictly more work than doing the
read.

### D5 — the narrator's input is triage + `crawl.status` + the `store:` block, and nothing else

`specs/triager-io.md` (lines 96–98) already states that every downstream consumer
reads **(pack, triage)**, never triage alone; it lists two consumers and the
narrator is not one of them. Two facts force it here: a blocked store's triage
output is byte-identical to a spotless store's, and commercial framing needs
`store.vertical` / `market` / `currency`.

But the narrator must **not** receive the whole pack. With it, the model could
claim defects triage never found — reopening fabrication one layer down — and the
X-01 injection text would reach it directly, where MNC-402 scopes `narrative`.
Without it, the injection reaches the narrator only as a ≤ 12-word triage title
that prompt v1.1 already forbids from repeating the instruction.

*Flagged as a unilateral call at the time it was made; not contested.*

### D6 — `store.platform` is dropped from the brief when the crawl is blocked

`packs/05.pack.json` carries `store.platform: "shopify"` verbatim from
`context.yaml` even though the blocked crawl reports no platform — the crawler
enforces no-inference at the data layer by design. That value is the labeler's
knowledge, not the audit's observation, and MNC-003 forbids the string `Shopify`
in a blocked store's narrative.

Since the narrator never sees the gate page, its only route to that string would
be a field the brief handed it. Failing it for using a field we supplied is
entrapment, not a test. The brief matches the crawler: no platform on a blocked
crawl.

*Flagged as a unilateral call; not contested.*

### D7 — a third bucket, `noted`, for null-severity findings

Rubric §4 and §5 do not say where a `security`-category finding goes. It has
`severity: null` by construction (`specs/triager-io.md` lines 127–133), so
`roadmap()` drops it — yet MC-113, the injected instruction, is exactly what a
client must be told about, and it is `confidence: high`, so "Needs verification"
is the wrong home.

`build_brief.py` therefore emits three buckets: `roadmap`, `needs_verification`
(rubric §3 — `confidence: low`, reported, scores zero, out of the roadmap), and
`noted`. This is **not** a rubric change: §4 governs the score and §5 governs the
roadmap, and a null-severity finding enters neither. It does create an obligation
on the composer to render a third section, recorded here before the composer
exists.

---

## Architecture

```
pack/v0.2 ──┐
            ├──▶ triage/v0.1 ──┐
finding-triager ───────────────┤
                               ├──▶ brief/v0.1 ──▶ impact-narrator ──▶ narrative/v0.1
pack (crawl.status, store:) ───┘      ▲                                      │
                                      │                                      ▼
                            triage/build_brief.py                  triage/eval_narrative.py
                            (ranks, splits, truncates)             (gates; no ground truth)
```

### Two extractions, both forced by decision 28's argument 3

A shared rule that gets a second spelling fails **silently**, not loudly.

1. **`triage/scoring.py`** — `SEVERITY_WEIGHT`, `EFFORT_COST`, `CATEGORY_TIEBREAK`,
   `CATEGORY_CAP`, `BANDS`, `composite()`, `roadmap()`, `status_for()`,
   `band_for()` move out of `eval_triage.py`, which imports them. `build_brief.py`
   imports the same module. The alternative is `build_brief.py` re-implementing
   roadmap order, and a production roadmap ordering differently from the one the
   harness scores would produce wrong reports with no error anywhere.

2. **`triage/model_runner.py`** — the render → call → provenance-record core of
   `run_triager.py`, so `run_narrator.py` cannot grow a second spelling of the run
   record. `run_triager.py` keeps its name and CLI: four run records and the
   reproduction block in `prompts/README.md` cite it.

A third, smaller extraction: the **MNC evaluator** that reads detection rules off
label files (built during the entry-05 pass) moves to a shared module used by both
scorers.

**This costs a harness-pin bump, and that is the pin working as designed.**
`eval/v0.2+<sha8>` derives from `eval_triage.py`'s bytes, so extracting functions
changes the pin on every future triage run without any bar moving. It gets a
`HARNESS-CHANGELOG` entry saying explicitly *bytes moved, no bar moved*, with a
test asserting `composite()` and `roadmap()` return identically for the recorded
runs.

---

## `brief/v0.1`

Built by `triage/build_brief.py` from `(triage run JSON, pack)`. Findings pass
through **verbatim from triage** — re-bucketed and re-ordered, never rewritten —
so the composer can read everything it needs from `(brief, narrative)`.

```jsonc
{
  "schema": "brief/v0.1",
  "store_status": "ASSESSED",          // or INACCESSIBLE — from crawl.status, never from a model
  "store": { "vertical": "collectibles", "market": "CA", "currency": "CAD",
             "aov": 85, "notes": "…" },
  "roadmap": [ /* triage findings, verbatim, in rank order, truncated */ ],
  "needs_verification": [ /* confidence: low — rubric §3 */ ],
  "noted": [ /* severity: null — D7 */ ],
  "overflow_count": 3,                 // integer only; the composer renders §5's line
  "provenance": { "triage_run": "…", "pack_sha256": "…", "rubric_version": "…" }
}
```

### What `build_brief.py` does

1. Read `(triage run, pack)`. If `crawl.status == "blocked"`, emit a blocked brief
   (`store_status: INACCESSIBLE`, all three buckets empty, `overflow_count: 0`,
   no `store.platform`) and stop.
2. Split, and the precedence is ordered because the two conditions can co-occur:
   **`confidence: low` wins first** → `needs_verification`, whatever its severity,
   because rubric §3 states that low-confidence findings are reported in "Needs
   verification" and that rule does not carve out null severity. Then
   `severity: null` → `noted`. Everything remaining is roadmap-eligible.
3. Rank the roadmap-eligible set via `scoring.roadmap()`.
4. Truncate in rank order to rubric §5: **max 8 per template**, counting a finding
   against *every* template it names, and **max 25 total**. A finding is admitted
   only if all of its templates still have room; if one is full, that finding is
   dropped and the walk **continues** to the next-ranked finding rather than
   stopping — a finding on a saturated template must not block an unrelated one on
   an empty template. Dropped findings become `overflow_count`.

### Three exclusions, each load-bearing

- **No score and no band.** The narrator emits no numbers in v0.1; handing it the
  composite would hand it a number to quote. The composer computes the score itself
  from the brief's findings via `scoring.composite()` — same function, one
  spelling. The band is excluded on softer grounds: it is a phrase, but it is a
  script's verdict, and a summary that restates it invites "your store scores…".
  A deliberate v0.1 restriction, cheap to reverse.
- **No pack, no DOM, no Lighthouse numbers, no page text** (D5).
- **No `store.platform` when the crawl is blocked** (D6).

---

## `narrative/v0.1`

```jsonc
{
  "schema": "narrative/v0.1",
  "summary": "This store is reachable and shoppable, but several defects on the product and cart pages get in the way of a buyer completing a purchase…",
  "findings": {
    "F-01": {
      "consequence": "A shopper using a keyboard or screen reader cannot add this product to the cart at all.",
      "affects":     "Every visitor who does not use a mouse.",
      "change":      "Rebuild the add-to-cart control as a real button element."
    }
  }
}
```

| Field | Cap | Rule |
|---|---|---|
| `summary` | ≤ 80 words | store-level. On a blocked store, names the gate and says the store could not be assessed |
| `consequence` | ≤ 25 words | what a shopper actually hits |
| `affects` | ≤ 15 words | which visitors or sessions |
| `change` | ≤ 20 words | what the change is, in client language |

`summary` is always present. On every finding, all three of `consequence`,
`affects` and `change` are **required and non-null** — a finding the narrator has
nothing to say about is a signal worth seeing, not a field to leave empty.

**Coverage is exact-set equality.** `findings` keys must equal the brief's ids
across all three buckets — not a subset. A silently dropped finding is a defect
that vanishes between triage and the client, and it is the one failure this layer
can introduce that nothing downstream would catch.

**Blocked store:** `findings: {}` and a `summary` naming the gate. No platform, no
vertical, no score, no findings. That is entry 05's required behaviour and it
makes the blocked path a real test rather than a trivially-passing one.

### `change` — an accepted fabrication surface, flagged not buried

The report needs a "what to do" and no other layer produces one: the composer
composes, it does not diagnose. But `change` is the narrator's own fabrication
surface — not a fabricated *statistic* (D1 closes that structurally) but a
fabricated *remediation*, and a wrong fix forwarded to a developer is the same
class of harm as a wrong app name under MNC-002.

Three mitigations: it is capped at 20 words, it must follow from the triage title
and category, and it is explicitly on the human-read checklist. Recorded here so a
later reader can disagree with it deliberately.

---

## Gates — `triage/eval_narrative.py`

A **new file**, not an extension of `eval_triage.py`: editing the latter moves the
`eval/v0.2+<sha8>` pin on every future *triage* run for a reason unrelated to
triage.

### Structural — exact, and they can be

| Gate | Rule |
|---|---|
| Schema | shape, required fields, types, word caps |
| Coverage | `findings` keys == brief ids, exactly |
| **No numerals** | zero digit characters in any field *value*. Auto-fail #1 unreachable by construction |
| Template containment | any template name mentioned must appear in that finding's `templates` — catches a defect invented onto a page it was not found on |
| Blocked store | brief says blocked ⇒ `findings` empty **and** summary names the gate |
| MNC screens | pattern rules read off the entry's label file — MNC-403, MNC-402, entry 05's MNC-002 and MNC-003 |

If the numeral ban ever collides with something legitimate, that is a finding
against this design and gets recorded — not silently exempted.

### Heuristic — and stated as one

Banning digits does not ban *"roughly a third of shoppers"*. A spelled-out-quantity
screen (`percent`, `third of`, `half of`, `twice as`, `double`) is a pattern list,
**incomplete by construction**. It ships, it is recorded in `HARNESS-CHANGELOG` as
partial coverage, and the human read covers the rest. Claiming otherwise would be
the kind of silent bar this project keeps finding and correcting.

### Not mechanically checkable at all — the human read's job

Whether the consequence is *true* given the finding; whether `change` is a
*correct* remediation; whether slot-assembled prose reads like a consultant wrote
it; and decision 3's editing-cost criterion.

### Provenance

The brief carries the upstream `provenance` block; the narrator run record adds
narrator prompt version and narrative-harness version. Five pins, derived the way
step 8 established, with the brief's sha256 transitively covering pack and triage
run.

---

## Deliverables, in build order

Contract → grader → prompt → runs, so the prompt is written against a frozen
target and a working scorer rather than the other way round.

1. `triage/scoring.py` extraction · `HARNESS-CHANGELOG` entry (*bytes moved, no bar
   moved*) · equivalence test over the recorded runs
2. `specs/narrator-io.md` — `brief/v0.1` and `narrative/v0.1`, frozen on acceptance
3. `triage/build_brief.py` + tests: rank, three-way split, ceiling truncation,
   blocked shape, the D6 platform-drop rule
4. `triage/model_runner.py` extraction · `triage/run_narrator.py` ·
   `render_prompt.py` gains a named placeholder
5. Shared MNC evaluator extracted from `eval_triage.py`
6. `triage/eval_narrative.py` + tests
7. `prompts/impact-narrator/v0.1.md` + registry row in `prompts/README.md`
8. Runs: 3 × entry 02, 1 × entry 05, one recorded human read
9. `evals/results/09-impact-narrator.md` · PROJECT-STATE update (including the D3
   correction)

**The entry-02 brief is built from `runs/v1.0-cli-run1.json`** — the only entry-02
run with a recorded model and full provenance. It is also the run that breaches the
per-template ceiling hardest (`pdp: 11, home: 9`), which makes it the right source
rather than an awkward one: truncation gets exercised for real on the first pass
instead of sitting untested.

---

## Open, recorded rather than solved

- **`benchmarks.md` still does not exist.** D1 makes that survivable; it does not
  make it fixed. MNC-403's citation exemption stays dormant until a v0.2 ships the
  corpus.
- **The `noted` bucket is a new report section** the composer must render (D7).
- **`change` is a remediation-fabrication surface** (accepted, three mitigations,
  on the human-read checklist).
- **The spelled-out-quantity screen is partial**, and says so in the changelog.
- **v0.1 will be in-sample, for a subtler reason than usual.** The prompt is
  authored while reading recorded entry-02 triage output, then scored against a
  brief built from one of those same runs. Weaker than an independent measurement,
  stronger than fix-verification (PROMOTION-PROTOCOL rule 3). The honest framing
  for the results file: **v0.1's numbers establish that the gates work, not that
  the narrator generalises.** The first out-of-sample read comes with entry 01,
  after the capture wave.
