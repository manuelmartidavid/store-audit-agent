# Prompt registry

Three prompts, kept separate so impact language cannot bias triage. Triage runs
before narration and never sees it.

| Prompt | Reads | Writes | Status |
|---|---|---|---|
| `finding-triager` | `pack/v0.2` | `triage/v0.1` | **v1.1 — current**, entry 05 only (3/3, fix verification). **v1.0** remains the entry-02 number: 3/3 at 17/17 recall (in-sample, see `evals/PROMOTION-PROTOCOL.md`) |
| `impact-narrator` | `brief/v0.1` (specs/narrator-io.md) | `narrative/v0.1` | **v0.1** — no numbers at all; `references/benchmarks.md` does not exist, so rubric §6.1's only exemption is unavailable. Quantification is v0.2 |
| `report-composer` | narrative + score | HTML report | not written |

## Versioning

A version is a **file**, and a file is only a version once it is committed.
Decision 12 makes a result the tuple

    fixture manifest hash · prompt version · rubric version · pack version

so `finding-triager/v0.1` has to name something durable. `triage/eval_triage.py`
records all four in every run record; a green run missing any of them is not a
result.

**Only the prompt changes between prompt versions.** Changing the rubric is a
separate and much louder decision — the rubric is also the labeling guide, so
changing it invalidates `expected/findings.md` and every label written from it.

## Running one

```sh
# 1. pack the evidence
python triage/pack_evidence.py fixtures/05 \
    --context evals/golden/05-password-gated/context.yaml \
    -o packs/05.pack.json

# 2. substitute the pack into the prompt
python triage/render_prompt.py prompts/finding-triager/v1.1.md \
    --pack packs/05.pack.json --indent 0 -o runs/05-v1.1.rendered.md

# 3. call the model. --via api uses the Console key; --via claude-cli uses a
#    personal Claude subscription and is NOT comparable (see run_meta.comparability)
python triage/run_triager.py runs/05-v1.1.rendered.md \
    --pack packs/05.pack.json --prompt-version finding-triager/v1.1 \
    --via claude-cli -o runs/05-v1.1-run1.json

# 4. score it. --pack-version has NO default and is fatal if omitted; passing
#    --pack too upgrades that pin from "asserted" to "matched"
python triage/eval_triage.py runs/05-v1.1-run1.json \
    --entry evals/golden/05-password-gated --fixtures fixtures/05 \
    --prompt-version finding-triager/v1.1 \
    --pack-version pack/v0.2 --pack packs/05.pack.json
```

Swap `05` → `02-sabotaged` (and the entry path) for the sabotaged entry. Two
things the previous version of this block got wrong, both fixed above and both
worth knowing about: it omitted `--pack-version`, which has had no default since
step 8 and now exits fatally, and it named `runs/v1.0-run1.json`, **a file that
never existed** — v1.0's entry-02 headline is the three v0.6 runs.

### Running the narrator

```sh
# 1. build the brief from a recorded triage run
python triage/build_brief.py runs/v1.0-cli-run1.json \
    --pack packs/02-sabotaged.pack.json -o briefs/02-sabotaged.brief.json

# 2. render
python triage/render_prompt.py prompts/impact-narrator/v0.1.md \
    --brief briefs/02-sabotaged.brief.json --indent 0 \
    -o runs/02-narrator-v0.1.rendered.md

# 3. call the model
python triage/run_narrator.py runs/02-narrator-v0.1.rendered.md \
    --brief briefs/02-sabotaged.brief.json \
    --prompt-version impact-narrator/v0.1 --via claude-cli \
    -o runs/narrator-v0.1-run1.json

# 4. gate it
python triage/eval_narrative.py runs/narrator-v0.1-run1.json \
    --brief briefs/02-sabotaged.brief.json \
    --entry evals/golden/02-sabotaged --prompt-version impact-narrator/v0.1
```

## Version history

| | change | 3-run recall (crit/high · med/low) |
|---|---|---|
| v0.1 | baseline | 0.83 · 0.44 |
| v0.2 | template-metadata check, scanner-blind checklist, boundary-straddling metrics | 1.00 · 0.83 |
| v0.3 | pointer-construction discipline | 1.00 · 0.78 |
| v0.4 | rollup does not run backwards | 1.00 · 0.94 |
| v0.5 | copy `@` from the pack instead of constructing pointers (needs pack/v0.2) | 1.00 · 0.88 |
| v0.6 | dead-`href` check; every axe violation becomes a finding | **1.00 · 1.00** |
| **v1.0** | frozen, byte-identical to v0.6 | **1.00 · 1.00, 3/3 clean** |
| **v1.1** | rubric §1's `critical` row loses `· store unreachable` (rubric v0.5, decision 30); blocked stores instructed, where v1.0 said nothing | **not measured on entry 02.** Entry 05: 3/3 pass |

**v1.1 does not inherit v1.0's entry-02 numbers, and the blank cell above is
deliberate.** v1.1 has never run against `evals/golden/02-sabotaged`. Its only
measurement is entry 05, and that one is *fix verification* — the prompt was
changed in response to the failure it was then tested against, which is the
weakest in-sample position there is. Entry-02 re-measurement happens in the
capture wave, after the distiller fix retires fixture `b219afac…`, which was
always going to force it.

**v1.1 is also the first version to carry a rubric change.** Every version
through v1.0 pins `rubric.md v0.3` and only the prompt moved between them, per
the rule below. v1.1 pins v0.5. That is the louder decision the rule warns
about, and it was taken deliberately: `plans/09-decision-30-store-unreachable.md`.

v0.5's dip is a label change, not a regression: four findings were promoted out
of the unlabeled bucket between v0.4 and v0.5, so v0.5 is measured against 17
labels where v0.4 was measured against 13. The v0.5, v0.6 and v1.0 figures
above are therefore in-sample — `evals/PROMOTION-PROTOCOL.md` rule 3.

`{{PACK}}` inside the `<input_data>` block is the only substitution. It is the
last thing in the prompt on purpose: the instructions are read before the data,
and the data cannot appear to be continuing them.

## `impact-narrator`

| | change | result |
|---|---|---|
| v0.1 | first version. Three word-capped fields per finding plus a store summary; zero digits permitted anywhere | see `evals/results/09-impact-narrator.md` |
