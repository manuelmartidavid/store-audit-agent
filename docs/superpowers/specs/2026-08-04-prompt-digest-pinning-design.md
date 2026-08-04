# Prompt digest pinning — design

**Date:** 2026-08-04
**Status:** approved
**Closes:** the "prompt versions are pinned by name, with no digest" open item
(HANDOFF-2026-07-31 §8; the `b219afac` shape of failure with a different noun).

## Problem

`resolve_prompt_version` (`triage/eval_triage.py:144`) checks only that
`prompts/{name}.md` exists, and `provenance()` records `prompt_pin: "exists"`.
Of the five provenance pins, the prompt is the only one that can be edited in
place without anything noticing: the next person to "just fix a typo" in a
frozen prompt silently changes what every run recorded against it was measured
with. `rubric_version()` and `harness_version()` already bind their pins to
bytes; the prompt pin must do the same — and can do better, because run records
already carry `run_meta.rendered_sha256`, the hash of what the model actually
saw.

## Decisions taken during brainstorming

- **Strictness:** a detected mismatch fails the scoring run (`SystemExit`),
  consistent with the fixture-pin precedent — exits rather than scoring blind
  (decision 12). It does not merely record.
- **Scope:** both callers of `resolve_prompt_version` — `eval_triage` and
  `eval_narrative`. Leaving the narrator at `"exists"` would recreate the same
  hole one module over.
- **Approach:** digest-in-the-value plus recompute-and-compare through
  `rendered_sha256` (approach B). A frozen-pins registry was rejected as a
  machine-readable sidecar (the `parse_labels` invariant: two copies of ground
  truth drift apart); git already pins the bytes — the gap is that *runs*
  record a name instead of bytes.

## Design

### 1. The pin value

`resolve_prompt_version("finding-triager/v1.3")` returns
`finding-triager/v1.3+<sha256[:8]>` of the template file's bytes — the
`rubric_version()` pattern exactly. It also verifies the template's front
matter (`prompt:`/`version:`) agrees with the filename, catching a `v1.2.md`
copied to `v1.3.md` without its header edited. Implementation verifies the
live prompts pass this check before it lands (the
`test_the_live_prompts_and_the_live_rubric_resolve` pattern).

### 2. The `matched` check in `eval_triage.provenance()`

`provenance()` gains a `run_meta` parameter — already loaded in `main()`
(`eval_triage.py:1071`), just never passed. When the run carries
`run_meta.rendered_sha256` **and** `--pack` was given, re-render
`prompts/{name}.md` with the pack via the existing `render_prompt.render()`
and compare hashes:

- equal → `prompt_pin: "matched"` — the template on disk is byte-identical to
  what the model saw. This also catches a hand-edited *rendered* file: the pin
  binds to what was sent, not what the template claims.
- unequal → `SystemExit`. `run_meta.pack_sha256` disambiguates the message:
  if the pack on disk doesn't hash to what the run recorded, the pack is wrong
  (point `--pack` at the right one); otherwise the template was edited in
  place after the run.
- no `run_meta` (old bare-JSON runs) or no `--pack` → `prompt_pin: "exists"`,
  as today. Old runs stay scoreable. The four-word pin vocabulary is
  unchanged.

The runbook's §3.1 eval command already passes `--pack`, so real results get
the strong check with zero workflow change.

**Newline subtlety the recompute must own:** `rendered_sha256` hashes *file
bytes*, and `write_text` translates newlines per-platform — a
Windows-rendered file is CRLF while `render()` returns LF text. The recompute
hashes the re-rendered text under both newline conventions and accepts
either.

**Indent subtlety:** the runbook never passes `--indent`, so the recompute
uses the default rendering. `eval_triage` gains an optional `--render-indent`
escape hatch, and the mismatch message mentions it.

### 3. `eval_triage.main()` cross-checks the asserted name

`eval_narrative` already refuses to score when `run_meta.prompt_version`
disagrees with the asserted `--prompt-version`; `eval_triage` gains the same
comparison, on the bare name (`run_meta` records no digest). Even a pack-less
eval then catches "asserted the wrong version".

### 4. `eval_narrative` gets the same treatment

- The equality check at `eval_narrative.py:321` must compare the *name part*
  of the resolved value — it would otherwise break the moment resolve returns
  `+sha8`.
- The narrator provenance gains the same re-render `matched` check, using the
  `{{BRIEF}}` placeholder and `--brief`, and records `prompt_pin` alongside
  `prompt_version` for symmetry.

## Error handling

All failures are `SystemExit` with the project's diagnostic style: what was
compared, both values, and what the operator should do. The three distinct
messages: wrong pack (pack bytes ≠ `pack_sha256`), template edited in place
(pack matches, render doesn't — mentions `--render-indent` as the escape
hatch for a non-default render), front matter disagrees with filename.

## Testing

New tests in `tests/test_provenance.py`, tmp-dir fixtures in the existing
helper style:

- digest changes when the template bytes change (rubric-style pair test)
- `matched` on a faithful re-render (tmp prompt + pack + run_meta)
- `SystemExit` reproducing the "typo fix after the run" failure directly —
  the way `test_archive.py` reproduces the b219afac loss
- old run without `run_meta` degrades to `exists` and still scores
- no `--pack` → `exists`
- a CRLF-rendered run still reads `matched`
- front-matter/filename disagreement refuses
- narrator: bare-name comparison survives the `+sha8` suffix; narrator
  `matched` check works through `{{BRIEF}}`
- live repo: every live prompt resolves with a digest and agreeing front
  matter

`test_the_prompt_pin_says_existence_and_not_more` is rewritten — its
docstring's premise ("the run files carry no prompt identity") is exactly
what this change makes false. Its replacement documents when `exists` is
still the honest ceiling (no run_meta, or no pack).

## Out of scope

- `run_triager` / `run_meta` record nothing new — `rendered_sha256` already
  carries the needed identity.
- Runbook commands are unchanged; prompt files are unchanged.
- After implementation, `PROJECT-STATE.md` gains a decision recording that
  the fifth pin is now bound to bytes.
