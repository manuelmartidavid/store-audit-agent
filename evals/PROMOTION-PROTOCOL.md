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
     were promoted** on 2026-07-28. The four MNC labels carry no model input
     today: MNC-404's decision-23 narrowing was motivated by a run
     observation, but decision 25 reverted it, so no MNC rule now rests on a
     run.
   - **Entry 05** — nothing promoted. Its header records that the labels do not
     depend on the capture and that nothing in them was changed in response to
     the three runs.
3. **A prompt scored against a label set containing labels promoted from that
   prompt's own lineage is IN-SAMPLE.** Say so wherever the number appears — the
   results file, PROJECT-STATE, the prompt registry (`prompts/README.md`).
   "17/17" without that qualifier is an overstatement.

   **Frozen prompt front matter is the exception, and it is not an oversight.**
   A frozen prompt's bytes (anything under `prompts/finding-triager/`) are a
   provenance pin: decision 12 makes a result the tuple of fixture manifest
   hash, prompt version, rubric version and pack version, and editing frozen
   front matter to add a qualifier would invalidate the runs recorded against
   those bytes exactly as editing the number itself would. Frozen front matter
   therefore carries its recall figure unqualified, by necessity — the results
   file is the qualifier's authority, and that is where a reader who finds an
   unqualified figure in frozen front matter should be sent.
4. **The out-of-sample recall number comes from an entry whose labels predate
   every run against it.** Entries 01, 03 and 04 are that opportunity, and it is
   single-use per entry: label from the fixture, freeze, *then* run. (Entry 05
   already meets the ordering test but carries no must-catch labels, so it
   yields an out-of-sample behavioural check and no recall figure.)
5. **A promotion wave never lands in the same commit as a run it is scored by.**
   Promote, commit, re-run, report. The order is the evidence.

## What the suite enforces today

Rule 2's `source:` key is enforced by nothing: no label carries one yet, and no
test requires one — a labeler who omits it gets no red test, only the reading
above that treats silence as promoted (except the two exempted entries). Rule 5
is prose discipline only; nothing in the suite can see commit order, so nothing
would catch a promotion wave landing beside the run it is scored by. Rules 1, 3
and 4 are judgment calls a test cannot make either — whether a label set is
in-sample, whether an entry's ordering qualifies it as out-of-sample — with one
exception: `test_every_citation_of_the_promotion_protocol_resolves` (task 9)
checks that this file's citations resolve, not that the claims made where they
are cited are correct. A labeler who mislabels provenance will not get a red
test for it. The discipline is the enforcement.

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
