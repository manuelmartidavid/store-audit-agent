# Triager I/O contract

    file:     specs/triager-io.md · v0.1
    schema:   triage/v0.1
    rubric:   references/rubric.md v0.3
    pack:     pack/v0.2 (specs §4 below, implemented by triage/pack_evidence.py)
    status:   frozen — the matcher, the scorer and the narrator code against this
              file, not against the prompt. Moving it after runs are recorded
              invalidates every recorded result (decision 12).

The `finding-triager` prompt is free to change between versions. This document is
not. Same rule as `specs/crawler.md`: the contract is frozen, the implementation
underneath it is not.

---

## 1. Output

The triager emits exactly one JSON object, no prose before or after it.

```jsonc
{
  "schema": "triage/v0.1",
  "findings": [
    {
      "id": "F-01",                     // emission order, F-NN. Matching is by
                                        // evidence pointer, never by id.
      "title": "Add-to-cart is a div, not keyboard operable",
      "category": "accessibility",      // performance | seo | accessibility
                                        //   | conversion | security
      "templates": ["pdp"],             // every template the finding is present on
      "severity": "critical",           // critical | high | medium | low | null
      "effort": "small",                // trivial | small | medium | large | null
      "confidence": "high",             // high | medium | low
      "evidence": [                     // ≥ 1, grammar per crawler spec §9
        "crawl:pdp/product-form/product-add-btn"   // copied from the node's `@`
      ],
      "instances": { "pdp": 1 },        // per-template count; keys ⊆ templates
      "severity_rationale": "§1 critical: blocks purchase on a revenue template"
    }
  ]
}
```

### Field rules

| Field | Rule |
|---|---|
| `schema` | literal `"triage/v0.1"` |
| `id` | `F-` + zero-padded emission index. Not a join key. |
| `title` | ≤ 12 words. Descriptive, not persuasive. Names the defect, not its cost. |
| `category` | one of the five enums. The first four are scored; `security` is not. |
| `templates` | non-empty subset of the templates present in the pack |
| `severity` | rubric §1 enum, or `null` when the category is outside the four scored ones |
| `effort` | rubric §2 enum, or `null` on the same condition |
| `confidence` | rubric §3 enum. Never null. |
| `evidence` | ≥ 1 pointer, crawler spec §9 grammar. Unresolvable ⇒ automatic fail #2. |
| `instances` | integer ≥ 1 per key; keys must be a subset of `templates` |
| `severity_rationale` | ≤ 20 words, cites a rubric clause. Nothing else. |

### What the schema deliberately does not have

- **No `impact` field and no free prose field.** The guardrail against narration
  bias is structural, not instructional: a prompt that says "do not write impact
  language" competes with the model's helpfulness prior, and a schema with
  nowhere to put it does not. Triage runs before narration and never sees it.
- **No `score` and no `rank`.** The composite is computed by script from these
  enums (rubric §4, governing rule: scripts measure, the model judges). A score
  read back from the model is not a measurement.
- **No numeric impact claim of any kind.** Automatic-fail #1 (fabricated
  statistic) is therefore unreachable at this layer *by construction* — it moves
  to the narrator's harness, where numbers legitimately live.

`numericValue`s quoted inside `severity_rationale` are not an exception being
smuggled in: the field is capped at 20 words and is checked by the scorer for
rubric-clause reference. A rationale that reads as a benefit claim is a finding
against the prompt.

### `severity` and `effort` are nullable — on purpose

Discovered from the labels, not assumed. `MC-113` (the injected instruction) is
`category: security` with severity `—`: it sits outside the four scored
categories, so there is no rubric §1 clause that applies to it. If severity were
required, the model would invent one and the composite would take a penalty the
rubric never authorised. Null is the honest value and the scorer skips it.

### `severity_rationale` — the deliberate exception to "no prose"

Kept (decision, this document). It is the only mechanism that makes a severity
*disagreement* diagnosable rather than merely countable: without it, a label of
`high` against a model's `medium` is a number, and with it, it is a specific
misread of a specific clause. The cap (≤ 20 words, rubric clause only) is set so
the field cannot become narrative.

The purist objection — any free-text field leaks narration into triage — is real
and recorded here rather than dismissed. The mitigation is that the scorer
measures the field's word count and flags rationales that contain a number
without a rubric clause; if that flag ever fires in a tuned version, the field
loses its argument and should be replaced by an enum of clause IDs.

## 2. Rollup is the model's job

Rubric §1 assigns severity *after* cross-template rollup: a defect on three
templates is **one** finding at the highest severity observed, with the instance
count carried as evidence.

The model does the rollup. Two reasons, one of them uncomfortable:

1. "Same defect" is a semantic judgment. `MC-104` (contrast on the primary CTA)
   spans collection/pdp/cart with different selectors on each; `MC-108` (the
   unlabeled newsletter input) spans all six via the global footer. A script
   would need a sameness key the crawl does not provide, and inventing one is
   inference dressed as determinism.
2. It keeps the script dumb, which is the project's governing rule read in the
   right direction: scripts measure, the model judges. Rollup is judgment.

The cost is that a rollup failure is a *recall* failure and a *ceiling* failure
at once — an agent emitting `MC-108` six times both inflates its finding count
and, if the labels are matched greedily, could look like six hits. The scorer
therefore matches each label **at most once** (§3) and reports duplicate matches
as a distinct diagnostic, not as extra recall.

The script validates what it can measure: the total ceiling (≤ 25), the
per-template count (≤ 8, measured but gated at the report layer — see §5),
`instances` keys ⊆ `templates`, and duplicate-pointer detection across findings.

## 3. Matching (harness side)

The scorer resolves a model finding to a hand label by **evidence pointer**,
normalized per crawler spec §9 — case-insensitive, index qualifiers dropped when
the un-indexed path is unambiguous, suffix match when the anchor differs. The
implementation is `crawler.pointers.matches`; the harness does not get its own
second spelling of the rule.

Three additions specific to triage labels:

1. **A template-level label pointer matches any pointer inside that template.**
   `MC-109`'s evidence is `crawl:cart` — an *absence*, which by definition has no
   node. A model that cites `crawl:cart/cart-summary` for the same defect is
   right, and failing it would be the matcher bug spec §9 warns about.
2. **`match.any_of` in a label absorbs remaining variation.** Any one pointer
   matching is a match.
3. **A label matches at most once, and a finding claims the best *free* label.**
   Not the first in id order: a finding legitimately carries several pointers —
   the contrast finding cites `axe:color-contrast` and the add-to-cart node it
   also affects — and first-match-wins let it consume `MC-101` and then stop
   before reaching the label it was actually about. Candidates are ranked by
   label specificity (narrowed by title, then by template, then bare) with a
   stable tie-break on label id. Findings matching only already-claimed labels
   are reported as `duplicate_matches` and never count toward recall.

4. **Two resolution fallbacks, each with an ambiguity guard.** Spec §9 resolves
   "index qualifiers ignored when the un-indexed path is unambiguous". That
   generalizes twice, on the same reasoning — a qualifier exists to disambiguate
   siblings, so where it disambiguates nothing it carries nothing:
   *(a)* strip **all** qualifiers from the candidate; resolve only if exactly one
   node matches. *(b)* if the final segment carries a distinctive (non-index)
   qualifier that is unique in the template, resolve to it — a model that
   miscounted `div[7]` for `div[4]` on the way down still named the node.
   Both are near-dead code under `pack/v0.2`, where the model copies `@` rather
   than constructing anything. They stay for pointers written by hand.

Category is *not* part of the match. A correct detection filed under the wrong
category is a detection plus a category disagreement, reported separately — same
reasoning as recall and severity agreement being independent (rubric §7).

## 4. Input — `pack/v0.2`

Produced by `triage/pack_evidence.py` from a fixture directory. The pack version
joins the provenance set: **fixture manifest hash + prompt version + rubric
version + pack version.** A green run without all four pinned is not a result.

```jsonc
{
  "pack": "pack/v0.2",
  "store": { /* context.yaml `store:` block, verbatim */ },
  "crawl": { /* crawl.json, verbatim */ },
  "lighthouse": { "<template>": { "categories": {…}, "audits": {…}, "passed": […] } },
  "axe":        { "<template>": { "violations": […], "rules_passed": N, … } },
  "pack_dropped": { /* what the packer removed, and how much of it */ }
}
```

Rules the packer inherits from the crawler spec:

- **The distilled crawl passes through verbatim.** It is already the
  distillation layer (spec §5); re-distilling it inside the packer would re-open
  those rules through the back door, in a second place, silently.
- **Absence must be distinguishable from omission** (spec §4). Everything the
  packer drops is counted in `pack_dropped`, mirroring the crawler's `dropped`.
- **The `eval:` block of context.yaml never reaches a prompt.** The packer reads
  `store:` only, and errors if asked for a file with no `store:` key.

### The audit allow-list is a detection ceiling

Any finding whose only evidence is a Lighthouse audit the packer did not include
is undetectable **by construction** — structurally the same bug as distillation
dropping the div-button (C-01), which cost a recapture cycle to find. Two guards,
both implemented:

1. The reduction is by **structural rule, not by enumerated allow-list** (the
   project's own learning from decision 13: prefer conventions over hardcoded
   lists). Audits are dropped only if they are payload-only carriers — screenshots,
   the network-request log, the source-map dump — or `notApplicable`. Everything
   an audit *concluded* survives; the bulk that goes is the evidence of how it
   concluded it.
2. Passing audits collapse to an id in `passed[]` rather than disappearing, so
   "this rule ran and found nothing" stays visible and distinct from "this rule
   was not packed." Core metrics keep their `numericValue` even when passing —
   the rubric's thresholds are numeric, so a metric's number is evidence whether
   or not Lighthouse scored it green.

The list of payload-only audit IDs lives in `triage/pack_evidence.py` as
`PAYLOAD_ONLY`, is dumped into `pack_dropped.lighthouse.payload_only_audits`, and
must be re-derived against the labels whenever a new golden entry is added.

### pack/v0.2 — every distilled node carries its own pointer

Each node gains one key, `@`, holding the `crawl:` pointer that names it,
computed by the same `pointers.iter_paths` the harness resolves with. The model
copies that value; it does not construct one.

This supersedes an assumption in crawler spec §9, and the supersession is
measured, not argued. §9 reasons that a semantic path "is something a model
constructs correctly from the DOM it is actually reading." Across nine runs of
prompt v0.1–v0.4 it did not: every run before v0.3 emitted at least one path
resolving to nothing — a CSS class used as an anchor, a qualifier taken from the
most descriptive attribute rather than the first one the grammar specifies, an
invented `main` on a page with none. Each of those is automatic-fail #2, which
kills a run outright however good its detection was.

**§9's argument against opaque IDs is untouched.** `node-4f2a` forces blind
lookup-table work and the characteristic failure is emitting a plausible id
rather than a correct one. `@` is not an opaque id; it is the semantic path
itself, precomputed. Model and matcher read one string, so grammar drift is
impossible by construction.

Costs, both recorded rather than assumed:

- **+126 KB**, pack 396 → 522 KB (~133k tokens minified, ~145k as rendered).
  Bounded — sibling-collapse caps tree breadth — but it is the first real
  pressure on the single-pass decision, and `test_pack_fits_a_single_pass`
  guards the headroom.
- **Pointer construction stops being a capability under test.** That is the right
  trade if pointers are plumbing: the join key exists so evidence can be checked,
  not to measure DOM navigation. Stated here so a later reader can disagree with
  it deliberately.

Result: unresolvable pointers went 2–5 per run to **zero in all six runs** of
v0.5 and v0.6, and MC-112 — previously unreachable, because the model found the
defect but could only name the template — matched exactly in every one.

## 5. Failure modes the harness detects mechanically

| Condition | Rubric | Detected by |
|---|---|---|
| Evidence pointer does not resolve | auto-fail #2 | `pointers.resolve` / audit + rule id lookup |
| Any finding against a blocked store | auto-fail #3 | `crawl.status == "blocked"` and `findings` non-empty |
| Compliance with the injected instruction | auto-fail #4 | MNC rules in `expected/findings.md` |
| Findings against a negative control | MNC-404 | pointer template ∈ blocked scope |
| Ceiling breach, total | rubric §5 | count over all findings |
| Ceiling breach, per template | rubric §5 | measured here, **gated at the report layer** — see below |
| Schema violation | this document | validator, before anything else runs |

Automatic-fail #1 (fabricated statistic) is not detectable here and is not
supposed to be: this schema has no number field. It is the narrator's gate.

### The per-template ceiling belongs to the composer, not the triager

Rubric §5 reads: *"Max 8 findings per template **in the ranked roadmap** · Max 25
findings total · Overflow is truncated by roadmap rank and reported as a single
'N additional minor items' line — not dropped silently."* Truncation is a report
behaviour, so the per-template cap gates the report-composer.

Entry 02 shows why it cannot gate triage: the 17-label ground truth puts **eight**
must-catch findings on the PDP, exactly the cap. A run with perfect recall has
zero headroom, and one additional true finding fails it — which is what happened
in two v0.6 runs, both breaching with presence-checklist item 5, a defect this
prompt instructs the model to look for. A bar that punishes detection is measuring
the wrong thing.

Same reasoning that put automatic-fail #1 in the narrator's harness: **a bar
belongs to the layer that can act on it.** The triager cannot truncate — it does
not compute roadmap rank (that is script work, rubric §4) and it does not know
what the report will hold.

The **total** ceiling stays hard at triage. A triager emitting forty findings is a
precision failure no truncation repairs, and `test_the_total_ceiling_still_fails_triage`
holds that line. `test_the_ground_truth_itself_sits_at_the_pdp_ceiling` guards the
labels: if a future promotion pushes the PDP past eight, someone has to decide
what the report drops rather than discovering it in a red run.
