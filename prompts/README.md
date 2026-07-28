# Prompt registry

Three prompts, kept separate so impact language cannot bias triage. Triage runs
before narration and never sees it.

| Prompt | Reads | Writes | Status |
|---|---|---|---|
| `finding-triager` | `pack/v0.2` | `triage/v0.1` | **v1.0 — frozen 2026-07-28**, 3/3 runs at 17/17 recall |
| `impact-narrator` | `triage/v0.1` + `references/benchmarks.md` | narrative | not written — next |
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
python triage/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml \
    -o packs/02-sabotaged.pack.json

python triage/render_prompt.py prompts/finding-triager/v1.0.md \
    --pack packs/02-sabotaged.pack.json --indent 0 -o runs/v1.0.rendered.md

# … obtain a triage/v0.1 JSON from the model, then:

python triage/eval_triage.py runs/v1.0-run1.json \
    --entry evals/golden/02-sabotaged --fixtures fixtures/02-sabotaged \
    --prompt-version finding-triager/v1.0
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

v0.5's dip is a label change, not a regression: four findings were promoted out
of the unlabeled bucket between v0.4 and v0.5, so v0.5 is measured against 17
labels where v0.4 was measured against 13.

`{{PACK}}` inside the `<input_data>` block is the only substitution. It is the
last thing in the prompt on purpose: the instructions are read before the data,
and the data cannot appear to be continuing them.
