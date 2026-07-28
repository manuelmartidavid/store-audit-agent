# Prompt registry

Three prompts, kept separate so impact language cannot bias triage. Triage runs
before narration and never sees it.

| Prompt | Reads | Writes | Status |
|---|---|---|---|
| `finding-triager` | `pack/v0.1` | `triage/v0.1` | **v0.1** — baseline, entry 02 |
| `impact-narrator` | `triage/v0.1` + `references/benchmarks.md` | narrative | not written |
| `report-composer` | narrative + score | HTML report | not written |

## Versioning

A version is a **file**, and a file is only a version once it is committed.
Decision 12 makes a result the tuple

    fixture manifest hash · prompt version · rubric version · pack version

so `finding-triager/v0.1` has to name something durable. `scripts/eval_triage.py`
records all four in every run record; a green run missing any of them is not a
result.

**Only the prompt changes between prompt versions.** Changing the rubric is a
separate and much louder decision — the rubric is also the labeling guide, so
changing it invalidates `expected/findings.md` and every label written from it.

## Running one

```sh
python scripts/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml \
    -o packs/02-sabotaged.pack.json

python scripts/render_prompt.py prompts/finding-triager/v0.1.md \
    --pack packs/02-sabotaged.pack.json -o runs/v0.1.rendered.md

# … obtain a triage/v0.1 JSON from the model, then:

python scripts/eval_triage.py runs/v0.1-run1.json \
    --entry evals/golden/02-sabotaged --fixtures fixtures/02-sabotaged \
    --prompt-version finding-triager/v0.1
```

`{{PACK}}` inside the `<input_data>` block is the only substitution. It is the
last thing in the prompt on purpose: the instructions are read before the data,
and the data cannot appear to be continuing them.
