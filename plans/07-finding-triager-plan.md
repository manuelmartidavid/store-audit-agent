# Step 7 — `finding-triager`, analyzed plan

    status:   proposal, not yet actioned
    against:  fixtures/02-sabotaged (manifest b219afac…, 16:39 +08 2026-07-27)
    targets:  13 MC labels · 4 MNC labels · score 35 (30–42) · band "Significant work needed"
    rubric:   references/rubric.md v0.3
    note:     numbers in §2 are measured from the frozen fixture, not estimated

---

## 0. What step 7 actually is

PROJECT-STATE next-step 7 reads: *"Write `finding-triager` against entry 02. Map
crawl/Lighthouse/axe evidence → severity/effort/confidence enums + evidence
pointers, no prose. Measure recall against the 13 MC labels; severity-agreement
separately."*

That sentence contains one prompt and four pieces of infrastructure that do not
exist yet:

| Needed | Exists? |
|---|---|
| `prompts/finding-triager/v0.1` | no — "Prompts written: none" |
| triager **output schema** (the join key for everything downstream) | no |
| **evidence packer** — fixtures → a model-sized `<input_data>` | no, and not yet named anywhere |
| **matcher + scorer** — pointer resolution, tiered recall, composite | no; `scripts/` holds only planting tooling |
| machine-readable read of `expected/findings.md` | no |

So step 7 is not "write a prompt". It is "stand up the eval loop, then write the
first prompt inside it." The prompt is the cheapest part and the last part.

---

## 1. Prerequisite — put the harness under version control

`StoreAuditAgent` has no git history (PROJECT-STATE, "known but not blocking").
That was tolerable while the artifacts were fixtures with their own manifest
hashes. It stops being tolerable at step 7, because decision 12 defines a result
as *fixture hash + prompt version + rubric version*, and the moment we start
saying "v2 beat v1" the prompt version has to mean something durable. Right now
"v1" would be a filename.

Cheapest possible moment: before the first prompt file exists. `.gitignore`
already exists; `.env` is already ignored; fixtures are large but text (~5 MB
for entry 02) — worth a deliberate call on whether they go in the repo or into
an ignored `fixtures/` with the manifest hash as the commitment.

**Recommendation: git init before writing any prompt.** ~10 minutes. Flagged as
a prerequisite rather than a nicety because it is one-way: history you did not
record cannot be recovered later.

---

## 2. Build the evidence packer — `scripts/pack_evidence.py`

### Why this is step one and not an afterthought

Nothing in the project has yet asked what the triager actually *reads*. The
fixtures are not it. Measured, on `fixtures/02-sabotaged`:

| File | On disk | Minified | Notes |
|---|---|---|---|
| `crawl.json` | 920 KB | **312 KB** | 6 templates, 46–59 KB each minified |
| `lighthouse.json` | 3.68 MB | — | 5 LHRs (no 404 run), ~440–566 KB each, **176 audits** each |
| `axe.json` | 598 KB | — | 6 entries, ~54–70 KB each — almost entirely `passes`/`inapplicable` |

Raw, that is ~1.3M tokens. Not a context-window problem to solve later; a
prompt-architecture decision to make first.

What the LHR bulk actually is (top audits by size, home): `network-requests`
97 KB · `screenshot-thumbnails` 77 KB · `script-treemap-data` 12 KB ·
`final-screenshot` 10 KB. None of it is evidence any label cites.

### Measured pack target

- distilled crawl, **verbatim** — 312 KB (it is already the distillation layer;
  re-distilling it would re-open spec §5 through the back door)
- Lighthouse: allow-listed audit IDs, heavy `details` stripped — **21 KB** for
  27 audits × 5 templates
- axe: `violations[]` only — the fixture contains exactly **3 distinct rules**
  across all six templates (`color-contrast`, `landmark-one-main`, `region`)

⇒ **≈ 350 KB ≈ 90k tokens.** Single-pass triage over all six templates is
viable. That is a real finding: it means we do not need a per-template
map-reduce architecture, and can pick chunking for determinism rather than
for capacity.

### The risk to write down

**The audit allow-list is a detection ceiling.** Any finding whose only evidence
is an audit we did not pack is undetectable by construction — structurally the
same bug as the distiller dropping the div-button (C-01), which cost a whole
recapture cycle to find. Two guards:

1. Derive the allow-list *from the 13 MC labels first*, then widen deliberately.
2. The packer records what it dropped, mirroring the crawler's `dropped` counts.
   The project already treats "absence must be distinguishable from omission" as
   a design rule (spec §4); the packer inherits it.

The packer is a **script** — governing rule: scripts measure, the model judges.
Its version joins the provenance set: fixture hash + prompt version + rubric
version + **pack version**. A green run without all four pinned is not a result.

---

## 3. Freeze the output contract before writing prose — `specs/triager-io.md`

The matcher, the scorer and (later) the narrator all code against the schema,
not the prompt. If the schema moves after runs are recorded, every recorded
result is invalidated. So it gets frozen first, and it is short:

```jsonc
{
  "schema": "triage/v0.1",
  "findings": [{
    "id": "F-01",                       // emission order; matching is by pointer, never by id
    "title": "…",                       // ≤ 12 words, descriptive not persuasive
    "category": "accessibility",        // performance|seo|accessibility|conversion|security
    "templates": ["collection","pdp","cart"],
    "severity": "high",                 // critical|high|medium|low|null
    "effort": "trivial",                // trivial|small|medium|large|null
    "confidence": "high",               // high|medium|low
    "evidence": ["axe:color-contrast"], // §9 grammar, ≥1
    "instances": {"collection":4,"pdp":3,"cart":1},
    "severity_rationale": "…"           // ≤ 20 words, rubric clause only — see below
  }]
}
```

Three things this schema decides on purpose:

- **No impact field, no prose field.** The guardrail against narration bias is
  structural, not instructional. A prompt that says "do not write impact
  language" competes with a model's helpfulness prior; a schema with nowhere to
  put it does not.
- **`severity` and `effort` are nullable.** Discovered from the labels, not
  assumed: MC-113 (the X-01 injection) is `category: security` with severity
  `—`, outside the four scored categories. If severity were required the model
  would invent one and the composite would break.
- **`severity_rationale` is a deliberate exception to "no prose."** It cites the
  rubric clause, nothing else. Rationale: it is the only way severity
  *disagreements* become diagnosable instead of just countable, and it is capped
  hard enough that it cannot become narrative. **This is a judgment call worth
  arguing about** — the purist position is that any free-text field leaks
  narration into triage.

Open sub-decision, needs a call: **who does cross-template rollup?** Rubric §1
says severity is assigned *after* rollup, and two labels depend on it (MC-104 is
one finding across 4 templates; MC-108 one finding across all six via the global
footer). Model-side rollup is a semantic judgment ("same defect") and keeps the
script dumb; script-side rollup is deterministic but needs a sameness key the
crawl does not provide. Leaning model-side, script validates the ceilings.

---

## 4. Write `prompts/finding-triager/v0.1.md`

Contents, in order, with the reason each part is there:

1. **Role + hard boundary.** Assign enums and pointers. Do not write prose, do
   not estimate impact, do not compute the score, do not rank.
2. **Rubric §1–§3 inlined verbatim.** The rubric *is* the bounded vocabulary
   (rubric preamble: it must be the same document as the labeling guide).
   Reference-by-link is not available to a prompt.
3. **Tie-breaks stated as rules, not prose.** Two carry real test weight in this
   entry: boundary-takes-lower (MC-107 at 3915 ms is `medium`, 85 ms under the
   line) and severity-never-depends-on-effort (MC-102 is `critical` **and**
   `trivial` — a model that softens severity because the fix is one line fails
   the highest-value label in the set).
4. **Pointer grammar (§9) with three worked examples**, plus the "shallow by
   intent" rule. Pointer quality is the join key for recall; a correct finding
   with an unresolvable pointer is automatic-fail #2.
5. **`<input_data>` wrapper + injection rule.** Everything inside is data. An
   instruction inside it is content to *report*, never to follow. MC-113's pass
   condition is two-part — treated as data AND emitted as a finding — and half
   credit is a fail.
6. **Negative-control discipline (MNC-404).** Absence of a defect is not a
   finding. The clean control product, the 404 and search templates, checkout.
7. **Absence-as-evidence.** The single hardest part of this prompt.

### The absence problem — flagging it before it bites

Three of the thirteen must-catch findings (MC-109 shipping cost hidden, MC-110
no returns reference, MC-111 no condition/grading detail) are `model_only: true`
and their evidence pointer is a **template with nothing at it**. No scanner
emits them. Verified against the fixture: the PDP contains no "condition" string
and the cart no "Free shipping" string — the evidence is that absence.

A prompt framed purely as "map evidence → enums" will never emit them, because
there is no evidence row to map. But a prompt that invites the model to report
what is missing is one step from MNC-403 (fabricated impact) and from
false-positive inflation against the ceilings.

The resolution I would propose: an **explicit, closed checklist of purchase-
decision affordances** the model verifies presence of per revenue template
(shipping cost/threshold visibility, returns reference near the buy box,
condition/spec detail appropriate to the vertical, price clarity, stock state).
Closed, so it cannot grow into speculation; per-template, so absence is a
checked fact rather than an intuition. MC-111 is the acid test — it is
vertical-specific (single-unit collectibles), so the checklist has to be
parameterized by `store.vertical` from context.yaml without becoming a
store-specific hint. If we cannot make MC-111 fire without effectively naming it
in the prompt, that is a finding about the architecture, not a prompt bug.

---

## 5. Build the matcher and scorer — `scripts/eval_triage.py`

Reads: triager output + `expected/findings.md` + the fixture manifest.
Writes: a run record with all four provenance pins.

- **Read the labels by parsing the fenced yaml blocks in
  `expected/findings.md`.** They are well-formed. The alternative — a sidecar
  machine file — introduces drift between the human-readable ground truth and
  the machine one, which is exactly the failure this project keeps catching.
- **Pointer resolution per §9: normalized, not exact.** Case-insensitive, index
  qualifiers ignored when the un-indexed path is unambiguous, suffix match when
  the anchor differs, `match.any_of` for the rest. Spec rule, restated because
  it will be tempting to ignore under a red run: *a correct finding with a
  near-miss pointer is a matcher bug, not a model miss.*
- **Recall and severity agreement computed independently** (§7). Never collapse
  them — collapsing puts the 100% bar out of reach for reasons unrelated to
  detection.
- **Composite computed by script from the model's enums**, never read from the
  model. Compare against `expect`: 35, range 30–42, band, 6 findings above
  medium, ceilings ≤8/template and ≤25 total.
- **Automatic fails detected mechanically:** unresolvable pointer, any finding
  on a blocked store, MNC violations. Automatic-fail #1 (fabricated statistic)
  is unreachable at this layer by design — the schema has no number field — so
  it moves to the narrator's harness.

---

## 6. Run the loop

1. **Baseline v0.1, N ≥ 3 runs, change nothing mid-loop.** Variance is a new
   gate I am proposing: a single green run on a stochastic model is not a
   result, and the project already pins everything else about provenance.
2. Bars for entry 02:
   - 100 % recall on the six critical/high: MC-101, MC-102 (critical),
     MC-103, MC-104, MC-105, MC-106 (high)
   - ≥ 75 % on the six medium/low: MC-107–MC-112 ⇒ **≥ 5 of 6**
   - MC-113 both halves
   - zero MNC violations
   - ceilings respected
3. **Only the prompt changes between versions.** A rubric change is a separate
   and much louder decision — the rubric is also the labeling guide, so changing
   it invalidates `expected/findings.md`.
4. **When the run disagrees with intent, ask what is wrong before assuming it is
   the prompt.** Three times in entry 02 the measurement overrode the plan
   (P-01/P-02 inverted, P-04 → MNC, S-02 dropped). The same discipline applies
   to matcher bugs: a near-miss pointer is a matcher fix, a fabricated pointer
   is a prompt fix.
5. Freeze v1, write the result and the learnings into PROJECT-STATE.

---

## 7. The overfitting hole, and a cheap partial answer

Entry 02 is a store with thirteen deliberately planted defects. Tuning
precision against it is tuning against a target that rewards finding things.
The false-positive test is entry 01 (rubric §5: ≤ 3 findings, none above
medium, score ≥ 90) — and entry 01's store **has not been selected yet**
(next-step 9).

Cheap partial answer available today: run the frozen triager over
**`fixtures/02`**, the pre-sabotage baseline of the same store. It is not clean
and it is not labeled, so it is not a pass/fail gate — but it is the *same
theme without the plants*, so any finding it produces that is not a known
pre-existing issue is a candidate false positive, at zero capture cost.

Caveat that must be stated: `fixtures/02` was captured under crawler 0.1.0,
before decisions 13 (fingerprint) and 16 (distiller). Its `apps[]` and its
div-button handling differ from 0.2.0. It is a directional check, not a
measurement. Making it a measurement means recapturing it — which is step 8's
work anyway.

---

## 8. Sequence and rough shape

| # | Work | Kind | Gate before moving on |
|---|---|---|---|
| 7.0 | `git init` the harness | infra | history exists before prompt v0.1 |
| 7.1 | `specs/triager-io.md` — output schema frozen | spec | rollup owner decided |
| 7.2 | `scripts/pack_evidence.py` + tests | script | pack ≤ ~100k tokens, drop-counts recorded, allow-list derived from the 13 labels |
| 7.3 | `prompts/finding-triager/v0.1.md` + registry | prompt | absence-checklist approach settled |
| 7.4 | `scripts/eval_triage.py` + tests | script | reproduces score 35 from the *labels themselves* before it ever scores a model |
| 7.5 | baseline → tune → freeze v1 | loop | tiered bars met across N ≥ 3 runs |
| 7.6 | PROJECT-STATE update + learnings | record | — |

7.4's gate is worth calling out: **the scorer must reproduce 35 from
`expected/findings.md` alone before it is pointed at a model.** If it cannot
recompute the hand-verified composite from the hand labels, it is broken, and
discovering that while also debugging a prompt would waste the run.

---

## 9. Open decisions — need a call, not an inference

1. **Git init before prompt v0.1?** (recommend: yes) — and do fixtures go in the
   repo, or stay ignored with the manifest hash as the commitment?
2. **Triage granularity** — one pass over all six templates (fits: ~90k tokens),
   or per-template passes plus a rollup stage? Capacity no longer decides this;
   determinism and iteration cost do.
3. **Rollup owner** — model (semantic, matches rubric §1 ordering) or script
   (deterministic, needs a sameness key that does not exist yet)?
4. **How runs are executed** — a scripted API runner (reproducible, supports the
   N ≥ 3 variance gate, costs tokens) or driving the prompt manually through a
   Claude session (zero setup, but no provenance and no variance measurement).
   Decision 12 points hard at the former; `.env` currently holds no API key, so
   this is a real setup step, not a formality.
5. **`severity_rationale` in the schema** — diagnostic value vs. the purist "no
   free text in triage" position.
