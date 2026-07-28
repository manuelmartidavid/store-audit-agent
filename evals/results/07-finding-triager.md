# Step 7 result — `finding-triager` against entry 02

    date:     2026-07-28
    entry:    evals/golden/02-sabotaged
    fixture:  manifest b219afac6f8234ff98ce6c4eaf004bdb4063aaf1155de78b0fe19c6512946d20
    rubric:   rubric.md v0.3 — the pin these runs were measured under.
              v0.4 (2026-07-28) changed §4 rule 3 presentation only; §1–§3 are
              byte-identical, so every number below stands unrecomputed.
    prompts:  finding-triager v0.1 → v1.0, 3 runs each, nothing else varied within a version
    status:   **v1.0 FROZEN 2026-07-28** — 3 of 3 runs clear every bar at 17/17 recall
    packs:    pack/v0.1 for v0.1–v0.4 · pack/v0.2 for v0.5–v1.0
    labels:   13 must-catch for v0.1–v0.4 · 17 for v0.5–v1.0 (four promoted 2026-07-28)

## Result

| run | findings | crit/high recall | med/low | overall | severity exact | effort exact | score | unlabeled | dead pointers | MNC | |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v0.1-1 | 16 | 0.83 | 0.50 | 0.69 | 1.00 | 0.50 | 24 | 7 | 1 | 0 | FAIL |
| v0.1-2 | 14 | 0.83 | 0.33 | 0.61 | 1.00 | 0.43 | 30 | 6 | 0 | 0 | FAIL |
| v0.1-3 | 16 | 0.83 | 0.50 | 0.69 | 1.00 | 0.50 | 25 | 7 | 3 | 0 | FAIL |
| v0.2-1 | 19 | **1.00** | 0.83 | 0.92 | 1.00 | 0.64 | 26 | 7 | 2 | 0 | FAIL |
| v0.2-2 | 18 | 1.00 | 0.83 | 0.92 | 1.00 | 0.64 | 26 | 6 | 3 | 0 | FAIL |
| v0.2-3 | 20 | 1.00 | 0.83 | 0.92 | 1.00 | 0.73 | 26 | 8 | 5 | 1 | FAIL |
| v0.3-1 | 18 | 1.00 | 0.67 | 0.85 | 1.00 | 0.30 | 24 | 7 | **0** | 0 | FAIL |
| v0.3-2 | 18 | 1.00 | 0.83 | 0.92 | 1.00 | 0.46 | 26 | 6 | 0 | 0 | **PASS** |
| v0.3-3 | 17 | 1.00 | 0.83 | 0.92 | 1.00 | 0.73 | 28 | 5 | 0 | 0 | **PASS** |
| v0.4-1 | 17 | 1.00 | **1.00** | **1.00** | 1.00 | 0.67 | 27 | 4 | 0 | 0 | **PASS** |
| v0.4-2 | 18 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 26 | 5 | 0 | 0 | **PASS** |
| v0.4-3 | 20 | 1.00 | 0.83 | 0.92 | 1.00 | 0.73 | 24 | 8 | 1 | 0 | FAIL |

*The twelve runs above were measured against the 13-label ground truth and
`pack/v0.1`. Bars at the time: 100% recall on the six `critical`/`high`, ≥ 75% on
the six `medium`/`low`, MC-113 both halves, zero MNC violations, ceilings ≤ 8 per
template and ≤ 25 total, schema valid, no automatic fail.*

**Two of three v0.4 runs detect all thirteen must-catch findings.** Severity
agreement is exact on every matched label in every one of these twelve runs — the
rubric's severity clauses are unambiguous enough that the model does not
disagree with them once, including the two traps built to make it: MC-102 is
`critical` **and** `trivial`, and MC-107 at 3915 ms takes `medium` from the
boundary-lower rule with 85 ms to spare.

Effort agreement is the weak metric: 0.30–0.73 exact, ≥ 0.91 within one level.
Effort does not enter the score (rubric §4 rule 4) and drives roadmap order only,
so this costs ordering accuracy, not the number.

## v0.5 → v1.0, and the ground-truth change underneath them

Between v0.4 and v0.5 two things moved at once, so the run tables either side are
not directly comparable and the header records which pack and which label set
each version was measured against.

**pack/v0.2 — every distilled node carries its own `@` pointer.** Rationale and
costs are in `specs/triager-io.md §4`. Effect, measured: unresolvable pointers
went 2–5 per run to **zero in all six runs** of v0.5 and v1.0, and MC-112 —
which the model had been finding since v0.3 but could only name at template level
— matched exactly every time. This was the single highest-leverage change in the
whole loop.

**Four findings promoted out of the unlabeled bucket** (MC-114 no `<h1>` on home ·
MC-115 meta descriptions absent on four templates · MC-116 no `main` landmark ·
MC-117 sixteen home CTAs and category cards linking to `#`), all verified against
the fixture independent of any model output. Composite recomputed 35 → 24, band
"Critical". A fifth promotion, MC-118, was folded back into MC-108 after three
v0.5 runs emitted both as one finding — correctly; a form control leaning on
placeholder text for its accessible name is one defect class, and splitting it was
an artefact of how MC-118 got promoted rather than a distinction the rubric draws.

> **Correction to this document's earlier promotion table.** It listed "No main
> landmark — seen in 3/3" against the v0.4 runs. That was wrong: the landmark
> finding came from v0.2 and v0.3 runs; **no v0.4 run reported it.** MC-116 was
> promoted on the strength of the fixture — axe fires `landmark-one-main` and
> `region` on all six templates — which is why the promotion still stands, but
> the frequency claim was not.

**v0.5 → v0.6.** Three labels missed in every v0.5 run, two of them promoted ones:

- *MC-117, sixteen dead links.* Nothing in the prompt asked whether links
  resolve; scanner-blind item 4 was about link *text*. Extended it to `href="#"`,
  empty and `javascript:void(0)` — a link that renders as navigation and does
  nothing.
- *MC-116, no `main` landmark.* axe fires it on all six templates and the model
  read the violations and chose not to report them. Added the rule that closes
  it: **every axe violation becomes a finding** unless it duplicates one already
  emitted. axe does not fire speculatively; deciding a violation is too minor to
  mention is a severity judgment, and §1 already makes that judgment.
- *MC-118* needed no prompt change — it was the labels that were wrong.

Result: **17/17 recall in all three v0.6 runs.** v1.0 is v0.6, frozen.

## Final run table — v0.5 and v1.0-lineage

| run | findings | crit/high | med/low | overall | sev exact | eff exact | score | unlabeled | dead ptrs | MNC | |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v0.5-1 | 19 | 1.00 | 0.88 | 0.94 | 0.93 | 0.80 | 24 | 3 | 0 | 0 | PASS |
| v0.5-2 | 18 | 0.88 | 0.88 | 0.88 | 1.00 | 0.71 | 26 | 3 | 0 | 0 | FAIL |
| v0.5-3 | 18 | 0.88 | 0.88 | 0.88 | 1.00 | 0.71 | 26 | 3 | 0 | 0 | FAIL |
| v0.6-1 | 20 | **1.00** | **1.00** | **1.00** | 0.94 | 0.56 | 14 | 3 | 0 | 0 | **PASS** |
| v0.6-2 | 20 | **1.00** | **1.00** | **1.00** | 0.94 | 0.81 | 22 | 3 | 0 | 0 | **PASS** |
| v0.6-3 | 19 | **1.00** | **1.00** | **1.00** | 1.00 | 0.69 | 20 | 2 | 0 | 0 | **PASS** |

Zero unresolvable pointers and zero MNC violations across all six. Severity
agreement is exact or within one level everywhere; the two 0.94s are both
MC-116 read as `low` where the label says `medium` — see the open items.

## The fourth harness judgment call: the per-template ceiling

Two v0.6 runs put nine findings on the PDP against a cap of eight. Diagnosing it
rather than assuming a model defect turned up the real cause: **the 17-label
ground truth itself puts eight must-catch findings on the PDP**, exactly the cap.
A run with perfect recall has zero headroom, and both breaches were presence-
checklist item 5 — a defect this prompt instructs the model to look for.

Rubric §5 caps findings per template *"in the ranked roadmap"* and truncates
overflow by roadmap rank. That is a report behaviour, and the triager cannot
perform it: it does not compute roadmap rank (script work, rubric §4) and does not
know what the report will hold. So the per-template ceiling now **gates the
report-composer**; the scorer measures and reports it but does not fail on it.
The **total** ceiling stays hard at triage — a triager emitting forty findings is
a precision failure no truncation repairs.

This is the same reasoning that put automatic-fail #1 in the narrator's harness:
a bar belongs to the layer that can act on it. It is also, unavoidably, a bar
being relaxed by the person whose runs it was failing — so it is flagged here as
the fourth judgment call, alongside the three below, and
`test_the_ground_truth_itself_sits_at_the_pdp_ceiling` now guards the labels so a
future promotion past eight is a decision rather than a discovery.

## What each version changed, and why

Only the prompt changed between versions. The rubric did not — it is also the
labeling guide, and changing it would invalidate `expected/findings.md`.

**v0.1 → v0.2.** Three misses were consistent across all three baseline runs,
and none was a matcher artefact:

- *MC-103, generic collection title.* Nothing in v0.1 told the model that a
  `<title>` describing the template rather than the page is a defect. The
  severity table said "missing or duplicated", and the model sees one page per
  template, so duplication is not observable — genericity is its observable form.
  Added the template-metadata check.
- *MC-107, home LCP 3.92s.* Two of three runs rolled home and PDP LCP into one
  `high` finding, which destroys the only thing that distinguished them; the
  third omitted the amber metric entirely. Added: a metric crossing a severity
  boundary between templates is two findings, and a `medium`-band metric on a
  revenue template is reportable.
- *MC-108 (unlabeled newsletter input) and MC-112 (noise alt text).* Neither is
  emitted by axe. Added the scanner-blind checklist: form controls without an
  accessible name, alt describing the medium, non-native controls, link text
  naming no destination.

Result: critical/high recall 0.83 → 1.00, medium/low 0.33–0.50 → 0.83.

**v0.2 → v0.3 — pointer construction.** Every run in v0.1 and v0.2 emitted at
least one `crawl:` pointer that resolves to nothing, which is automatic-fail #2
and kills a run outright regardless of recall. Three causes, all addressable:
the model anchored on a **CSS class** (not in the §9 grammar), picked a
qualifier from the most descriptive attribute rather than the first one the
grammar specifies, and invented ancestors (`main` on a page with no `<main>`).
v0.3 states the qualifier attribute order verbatim, says a class is not a name,
and adds *trace it or drop it* — fall back to the template-level pointer rather
than guess. Dead pointers went 2–5 per run → 0, 0, 0.

**v0.3 → v0.4 — rollup does not run backwards.** v0.3-run1 merged "no returns
reference" and "no condition detail" into one PDP finding, losing MC-111. The
rollup rule read in only one direction. Added: each failed presence-checklist
item is its own finding.

## Harness changes made during the loop, and their justification

Three, all in the matcher, none in the rubric or the labels' verdicts. Each is
the "a near-miss pointer is a matcher bug, not a model miss" rule being applied —
which is also the rule that makes a matcher change suspicious, so each is stated
with the guard that keeps it from being a licence.

1. **Qualifier-insensitive resolution, unambiguous only.** `crawl:collection/html/head/title`
   is the model's spelling; the fixture's builder produces
   `…/title[collections-toronto-sports-cards]`. Spec §9 already ignores *index*
   qualifiers when the un-indexed path is unambiguous; this generalizes `index`
   to `any qualifier`, on the same reasoning (a qualifier disambiguates
   siblings — if the stripped path names one node, there was nothing to
   disambiguate). **Guard:** a stripped path naming more than one node resolves
   to none.
2. **Distinctive-tail resolution.** `img[icon-shield-svg]` names one node in the
   template; a model that miscounted `div[7]` for `div[4]` on the way down still
   named it. **Guard:** the qualifier must not be a bare index, and must be
   unique within the template.
3. **A finding claims the best free label, not the first one in id order.** A
   contrast finding that also cites the add-to-cart node was consuming MC-101 and
   then breaking before it could reach MC-104. Candidates are now ranked by
   label specificity with a stable tie-break.

And one screen was narrowed, which is the judgment call in this document most
worth arguing about:

4. **MNC-404 now fires only on findings with no node-level evidence.** The
   original screen flagged any unlabeled finding confined to `search`/`404`. But
   the search input genuinely has no accessible name — that is a real defect on
   an unplanted template, and the label file's own third bucket says a finding
   matching neither MC nor MNC is *not* a failure. Reading every real defect on
   a control template as a violation contradicts that outright. The discriminator
   is now whether the claim is cited or asserted. **If you disagree, this is the
   line to change** — it is the one place the harness got more permissive.

## What the loop found that no prompt tuning would have

**Rendered prices and stock state do not survive distillation.** `$149.99` is
seven characters, below `TEXT_KEEP_MIN_CHARS` (20), and a price span is not an
interactive element — so it is dropped. Verified: zero `$` characters in the
distilled tree of any template, on a store whose collection page carries a price
filter with a max of 70. Every early run reported "no price on the PDP" and every
one of those was a false positive **caused by the evidence base**.

This is structurally the same bug as C-01 (the div-button invisible to both axe
and the distiller), found the same way, one layer further out. v0.4 works around
it by removing price and stock from the presence checklist and saying why, but
the workaround costs two real purchase-decision affordances. **The fix belongs in
the distiller** and it changes capture output, so it lands with the step-8
recapture.

## Still open

1. **Two category caps now bind** — `seo` by 4, `accessibility` by 1. Rubric §4
   rule 2 says a binding cap means the weights are wrong rather than the cap.
   This store is not ordinary (two `critical`s in two categories), so the caps
   binding here is arguably them working. The cheap check is entry 01: if a cap
   binds on the clean-theme false-positive test, §4's weights need revisiting.
   Changing them is a rubric change and invalidates every label written against
   v0.3, so it waits for that evidence.
2. **MC-116 severity: label says `medium`, two of three runs say `low`.** The
   label reasons that landmark navigation affects a subset of sessions (§1
   medium); the runs reason it is hygiene with no measurable session impact (§1
   low). Two independent runs agreeing against the label is worth one look before
   assuming the label is right.
3. **Effort agreement is still the weak metric** — 0.56–0.81 exact, ≥ 1.00 within
   one level in every v0.6 run. Effort does not enter the score (rubric §4 rule
   4) so it costs roadmap ordering, not the number. It is the obvious target if
   anyone wants a v1.1.
4. **The distiller's short-text gap is unfixed** and blocks two presence-checklist
   items. It changes capture output, so it belongs with the step-8 recapture —
   after which entry 02 needs re-freezing and re-labeling, and every number in
   this document needs re-measuring.
5. **The false-positive check still has not run.** Entry 01 has no store selected.
   `fixtures/02` (the pre-sabotage baseline) is crawler 0.1.0 and directional at
   best. **This is the largest remaining hole in the result:** every number here
   measures recall against a store built to be found out, and nothing yet measures
   what the triager says about a store that is basically fine.

## Resolved during the loop (kept for the record)

1. ~~**The §9 semantic-path grammar is harder to emit than the spec assumed.**~~
   RESOLVED by `pack/v0.2`; the paragraph below is kept as the record of why.
   Spec §9 argues for semantic paths over opaque IDs because "a semantic path is
   something a model constructs correctly from the DOM it is actually reading."
   Measured across nine runs, it did not: every run before v0.3 emitted at least
   one unresolvable path, and v0.4-run3 still did. v0.3's *trace it or drop it*
   rule works by trading precision for resolvability, and MC-112 is the visible
   cost — the model finds the defect and points at `crawl:home`, which is not
   specific enough to match a node-level label.
   The structural fix is to **carry the crawler-derived pointer on each distilled
   node in the pack**, making construction a lookup. That is not the opaque-ID
   failure §9 warns about — it is the semantic path itself, precomputed. It is a
   `pack/v0.2` change and it touches a frozen spec's reasoning, so it is recorded
   here rather than taken.
2. ~~**`expect.score` range 30–42 does not survive a good run.**~~ RESOLVED —
   four findings promoted, composite recomputed to 24, range set to 18–34.
   Original reasoning below. v0.4 scores 24–27
   because the model finds 4–8 legitimate findings the labels do not carry, each
   adding penalties. The score is behaving correctly and the range was set from
   the must-catch set alone. Either the range widens downward or the strongest
   unlabeled findings get promoted to MC (see below).
3. ~~**v1 freeze.**~~ RESOLVED — v1.0 frozen 2026-07-28, 3 of 3 clean at 17/17.
4. **The false-positive check was not run.** Plan §7's cheap partial answer is to
   run the frozen prompt over `fixtures/02`, the pre-sabotage baseline. That
   fixture is crawler 0.1.0 — before the distiller and fingerprint changes — so
   it is directional at best, and making it a measurement means recapturing it,
   which is step 8's work anyway. Entry 01, the real false-positive test, has no
   store selected yet.

## Promotion candidates from the unlabeled bucket

Findings that appear in v0.4 runs, match no label, and look real on inspection.
This is "findings I'd have missed" becoming measurable rather than punished.

Superseded by the 2026-07-28 promotions; the four that were promoted are struck
through. See the correction note above about the landmark row's frequency claim.

| Seen in | Finding | Note |
|---|---|---|
| 3/3 | Home template has no `<h1>` | `axe:page-has-heading-one` fires. Real, and unplanted. |
| 3/3 | Meta description absent on home, cart, search | The S-02 gap that was dropped from the PDP exists elsewhere on the store |
| 3/3 | Cart indicates no tax, duty or handling | Presence-checklist item 2, genuinely absent |
| 3/3 | No `main` landmark; content outside landmark regions | `axe:landmark-one-main` + `axe:region` on all six templates |
| 2/3 | PDP states no delivery or shipping expectation | Presence-checklist item 5 |
| 2/3 | Carousel dots below minimum touch target | `lighthouse:audits/target-size` |
| 1/3 | Home hero and category links are `href="#"` placeholders | Verified in the fixture: `a.category-card[href="#"]` |
| 1/3 | Search form input has no accessible name | Real; the MNC-404 narrowing above turns on this one |

## Reproducing

```sh
python triage/eval_triage.py --self-test          # the composite, from the labels alone
python triage/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml -o packs/02-sabotaged.pack.json
python triage/render_prompt.py prompts/finding-triager/v1.0.md \
    --pack packs/02-sabotaged.pack.json --indent 0 -o runs/v1.0.rendered.md
# run the rendered prompt, capture the JSON, then:
python triage/eval_triage.py runs/v1.0-run1.json --prompt-version finding-triager/v1.0
```

> Paths corrected 2026-07-28: decision 28 split `scripts/` by concern.  <!-- STALE-OK -->
> The commands above are the ones that run today; the results in this file
> were produced by the same code under its former path.

Runs were executed as independent agent sessions against the rendered prompt,
each one told to read nothing else in the repository. There is no scripted API
runner yet (`.env` holds no API key); `triage/render_prompt.py` exists so that
adding one is a small job and the rendered artefact is identical either way.
