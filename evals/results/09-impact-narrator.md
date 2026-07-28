# Step 9 — `impact-narrator` v0.1, built and measured (2026-07-29)

Design: `docs/superpowers/specs/2026-07-29-impact-narrator-design.md`
Contract: `specs/narrator-io.md` (frozen)

## What was built

`triage/build_brief.py` · `triage/scoring.py` and `triage/model_runner.py` and
`triage/mnc.py` (extractions) · `triage/run_narrator.py` ·
`triage/eval_narrative.py` · `prompts/impact-narrator/v0.1.md` · 43 new tests
(`tests/test_build_brief.py` 12 · `tests/test_eval_narrative.py` 18 ·
`tests/test_mnc.py` 9 · `tests/test_scoring.py` 4).

## Result

| Entry | Runs | Passed | Numerals | MNC violations |
|---|---|---|---|---|
| 02-sabotaged | 3 | 3/3 | 0 | 0 |
| 05-password-gated | 1 | 1/1 | 0 | 0 |

All four runs passed: `errors`, `numerals` and `mnc_violations` came back empty
on every one. Entry 02's advisory lists carried two kinds of note across the
three runs — `quantity_word_notes` (the phrase "most of", either idiomatic
("most of all") or a licensed directional claim backed by `store.mobile_share:
0.7`) and `template_containment_notes` (the words "search"/"cart"/"collection"
used in their ordinary English sense — "search engines," "add to cart" — not a
claim about the site's `search`/`cart`/`collection` template). The human read
(Q5) found none of these correspond to a real defect in the narrative — every
advisory hit across all three runs is a false positive of the kind
`eval_narrative.py`'s own docstrings predict. Entry 05's advisory list is
empty; `findings={}` makes coverage, word caps and template containment pass
by construction there, so the only informative part of that run is the
summary, which named the gate ("could not be reached" — one of
`eval_narrative.py`'s `_GATE_WORDS`) without naming Shopify or guessing a
cause — MNC-003 held on its first screening against a narrative.

## The human read — decision 3's criterion, run for the first time

Full note: `docs/superpowers/notes/2026-07-29-narrator-human-read.md`.

Editing cost: **≈5%** (about 3 of 58 client-facing fields) against the >~30%
kill criterion — **agent-conducted, N=1: a proxy for the human read the
criterion actually calls for, not a substitute for it.** Three fields drove
the estimate: `F-14.change` added unsupported specificity beyond its title
("describing what the shop sells" isn't licensed by "Home page has no
level-one heading"); `F-11.consequence` ("simply cannot read it") read
stronger than its `medium` severity ("axe violation off the purchase path");
`F-06` vs `F-05` was a severity-differentiation miss (near-equal-intensity
language despite a roughly 2.7x gap in the underlying LCP) counted as one
edit rather than two. The other 55 of 58 fields, including both performance
findings' `change` fields, correctly used the prompt's "write the
investigation, not a guess" escape hatch rather than inventing a mechanism.

Bounded-slot prose read mechanical in one place, not across the narrative —
the one stated risk of the contract shape. The `affects` field (15-word cap)
converges on "Every ___ who/on ___" across most of the 19 findings — a real
texture cost from the cap, not a correctness problem, so it is not folded
into the 5% figure. Elsewhere it reads like a person: the summary's second
sentence — "Below that sits a layer of friction — dead links on the home
page, slow loading on phones, faint button text, and missing shipping, tax
and returns detail at the moments buyers decide." — groups four unrelated
defects into one image rather than listing them, and `F-08.consequence` —
"Pages pull down far heavier images than they actually display, so shoppers
wait on their data for nothing." — has a point of view a slot fill would not.

## What these numbers are worth

**They establish that the gates work, not that the narrator generalises.** The
prompt was authored while reading recorded entry-02 triage output and then scored
against a brief built from one of those same runs. That is weaker than an
independent measurement and stronger than fix verification
(`evals/PROMOTION-PROTOCOL.md` rule 3). The first out-of-sample read comes with
entry 01, after the capture wave.

Three further limits the green bars do not distinguish:

- **The numeral ban passes trivially on prose that was never going to quantify.**
  It is worth exactly what a structural gate is worth: it makes the failure
  impossible, and says nothing about whether the model would have committed it.
- **Entry 05's pass is on an empty findings object**, so coverage, word caps and
  template containment all pass by construction there. The informative part of
  that run is the summary — specifically that MNC-003 held.
- **`change` was read once — by the agent that ran the pipeline, not a human,
  and not the project owner — on one run of 3.** The remediation-fabrication
  surface this contract accepted is checked at n=1, by a proxy reader.

## Open, carried forward

- `references/benchmarks.md` still does not exist (verified: `references/` is
  not a directory in this repo). v0.1 makes that survivable, not fixed.
  MNC-403's citation exemption stays dormant.
- The `noted` bucket is a report section the composer must render.
- The spelled-out-quantity screen is partial; template containment is advisory.
  Both are recorded in `evals/HARNESS-CHANGELOG.md`.
- **New, found by this step's full-suite run, not fixed here.**
  `tests/test_run_triager.py::test_every_other_run_file_still_loads_a_valid_triage_output`
  scans every non-frozen file under `runs/*.json` and asserts
  `schema == "triage/v0.1"`. That assumption predates the narrator: Task 8
  committed `runs/05-narrator-v0.1-run1.json` (schema `narrative/v0.1`), which
  the full suite had not been run against until this step's Step 3. `python -m
  pytest tests/ -q` now collects 423 (421 passed, 1 skipped, 1 failed) instead
  of the "zero failures" this plan expected — recorded here rather than edited
  away, since fixing `triage/`, `tests/`, or the file's own assumption is
  outside this step's "records, does not change behaviour" scope.
