# Promotion protocol — how a finding may enter a label set

    file:   evals/PROMOTION-PROTOCOL.md
    status: binding on every golden entry from 2026-07-28

## The problem this exists to prevent

Entry 02's label set grew from 13 must-catch findings to 17. The four additions
came from the *unlabeled bucket* — findings the model emitted that matched no
label — and the three v0.6 runs that v1.0 froze then scored 17/17 against the
enlarged set.

Nothing here was done in bad faith and the additions improved the ground truth:
each was verified present in the frozen fixture, independent of any model
output. But **verification is not selection.** The fixture can confirm that a
defect is real; it cannot make the choice of *which* real defects become
must-catch independent of what the model happened to find. A recall number
measured against labels chosen from a model's output is in-sample, and calling
it anything else overstates it.

## The rule

1. **Promotion is allowed and encouraged.** "Findings I'd have missed" becoming
   measurable is the third label bucket's whole purpose. Do not suppress it.
2. **Record the source on every label.** A label carries `source: planted`,
   `source: fixture-review`, or `source: promoted-from-run <run file>`. A label
   with no `source` is treated as promoted.
   **Labels written before this protocol are exempt from that default.** The
   `source:` key is new, so no existing label carries one, and reading their
   silence as "promoted" would overstate the contamination as badly as the
   corrected header understated it. Their provenance is recorded in prose in
   their entry's label-file header instead. Two entries are affected, and the
   exemption is closed at them — it covers no label written after this file:

   - **Entry 02** — the `provenance:` block of
     `evals/golden/02-sabotaged/expected/findings.md` splits the 17 must-catch
     labels. **MC-101…MC-113 (13) predate every triager prompt**: planted
     defects labeled 2026-07-27 from the frozen fixture. **MC-114…MC-117 (4)
     were promoted** on 2026-07-28. The four MNC labels carry no model input.
   - **Entry 05** — nothing promoted. Its header records that the labels do not
     depend on the capture and that nothing in them was changed in response to
     the three runs.
3. **A prompt scored against a label set containing labels promoted from that
   prompt's own lineage is IN-SAMPLE.** Say so wherever the number appears — the
   results file, PROJECT-STATE, the prompt's front matter if it quotes a recall
   figure. "17/17" without that qualifier is an overstatement.
4. **The out-of-sample recall number comes from an entry whose labels predate
   every run against it.** Entries 01, 03 and 04 are that opportunity, and it is
   single-use per entry: label from the fixture, freeze, *then* run. (Entry 05
   already meets the ordering test but carries no must-catch labels, so it
   yields an out-of-sample behavioural check and no recall figure.)
5. **A promotion wave never lands in the same commit as a run it is scored by.**
   Promote, commit, re-run, report. The order is the evidence.

## Consequences for what is already recorded

- finding-triager **v1.0's 17/17 against entry 02 is in-sample.** The prompt is
  still frozen and the 18 recorded entry-02 runs still stand — this changes what
  the number means, not whether it happened. (v1.0 is v0.6 frozen with new front
  matter; the runs behind the 17/17 headline are `runs/v0.6-run{1,2,3}.json`.)
- **Entry 05 is out-of-sample** and stays that way: its labels were written
  before any capture, describing an absence. 1 of 3 runs behaved as labeled —
  run 3, which emitted the empty array the labels call for.
- **Entry 01 is the project's first real out-of-sample precision measurement.**
  Label it from the fixture before a single run touches it. Its `expect.gates`
  are declared in advance for the same reason (`eval/v0.2`).

## What an out-of-sample recall number would take

Nothing in the corrections above produces one. Concretely, it requires all four:
a golden entry whose must-catch set is complete and frozen before any run; a
prompt that was not tuned against that entry; the run recorded after the freeze
commit (rule 5); and the recall reported against the frozen set with no label
added between the run and the report. Entry 02 cannot supply it retroactively —
once four of its labels came out of v0.4 output, no later scoring of the
finding-triager lineage against entry 02 is out-of-sample, including a rerun of
v1.0 today. The number has to come from an entry that has not been run yet.
