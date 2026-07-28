# Step 8 — Measurement hardening, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

    status:   proposal, not yet actioned
    against:  the adversarial review of 2026-07-28 (findings P0-1…P2-16)
    rubric:   rubric.md v0.4 · fixture manifest b219afac… · pack/v0.2 · finding-triager v1.0
    note:     every number quoted below was measured against the repo on
              2026-07-28, not estimated. Where a claim is "verified", the
              command that verified it is in the step.

**Goal:** Make the project's own measurements trustworthy — pin, verify, back up
and reproduce every artifact a recorded result depends on — *before* the step-11
distiller fix regenerates the fixture, the labels and every number in the repo.

**Architecture:** Nine tasks, each independently testable and committed on its
own. Tasks 1–2 repair what is currently broken (the suite does not collect; the
documented reproduction commands name deleted paths). Tasks 3–5 make the
provenance real: the golden fixture gets an off-repo archive, the toolchain that
produced it gets pinned, and `eval_triage` starts *verifying* the four pins it
already prints. Task 6 replaces "runs were agent sessions" with a scripted
runner that records model and parameters. Tasks 7–9 close the methodology
findings: the harness gets a version and a bar changelog, precision gets a bar
for the first time, and the label file's provenance claim gets corrected.

**Tech stack:** Python 3.10 · pytest 9.1.1 · PyYAML 6.0.3 · Playwright 1.61.0 ·
Node (lighthouse 12.8.2, axe-core 4.12.1) · `anthropic` SDK (new, task 6 only).

## Global Constraints

Every task's requirements implicitly include these.

- **Python 3.10.** `from __future__ import annotations` at the top of every new
  module, matching the existing files.
- **Install with `python -m pip install --user`** and invoke tools as modules
  (`python -m pytest`). Global pip is broken on this machine.
- **Tests import modules by path**, not by package — the repo has no
  `pyproject.toml`, no `conftest.py` and `triage/` is not a package. Copy the
  `importlib.util.spec_from_file_location` idiom from
  [tests/test_eval_triage.py:24-28](tests/test_eval_triage.py#L24-L28).
- **`fixtures/` is gitignored.** Any test that needs `fixtures/02-sabotaged`
  must be guarded with the existing `needs_fixture` skipif pattern
  ([tests/test_eval_triage.py:30](tests/test_eval_triage.py#L30)) so the suite
  is green on a fresh clone.
- **Frozen artifacts are byte-frozen.** Do NOT edit `prompts/finding-triager/*.md`
  (v0.1–v1.0) or any file in `runs/`. Their bytes are provenance. Where a frozen
  file names a stale path, the fix goes in a note elsewhere, never in the file.
- **No new runtime dependency** except `anthropic` in task 6.
- **One commit per task**, message prefix `fix:`, `feat:`, `test:` or `docs:`.
- **Never** weaken or delete an existing test to make a new one pass. If an
  existing test now fails, that is a finding — record it and stop.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/test_measure.py` | *modify* — import `planting/`, not the deleted `scripts/` | 1 |
| `tests/test_repo_hygiene.py` | *new* — every test module imports; no stale path in a live doc | 1, 2 |
| `README.md`, `evals/results/07-finding-triager.md`, `specs/triager-io.md`, `evals/golden/02-sabotaged/context.yaml`, `rubric.md` | *modify* — path and count drift | 2 |
| `crawler/archive.py` | *new* — tar the golden fixture, verify it by manifest hash | 3 |
| `tests/test_archive.py` | *new* | 3 |
| `requirements.txt`, `package.json`, `README.md` | *modify* — exact pins, `npm ci` | 4 |
| `tests/test_toolchain_pins.py` | *new* — pins match entry 02's recorded provenance | 4 |
| `triage/eval_triage.py` | *modify* — verify the pins; harness version; expect bars | 5, 7, 8 |
| `tests/test_provenance.py` | *new* | 5 |
| `triage/run_triager.py` | *new* — scripted API runner, records model + params | 6 |
| `tests/test_run_triager.py` | *new* — offline; no network | 6 |
| `evals/HARNESS-CHANGELOG.md` | *new* — every bar change, dated, with the run that motivated it | 7 |
| `evals/golden/*/context.yaml` | *modify* — `expect.gates` | 8 |
| `evals/golden/02-sabotaged/expected/findings.md` | *modify* — split the provenance claim per amendment | 9 |
| `evals/PROMOTION-PROTOCOL.md` | *new* — how a finding may enter the label set | 9 |

---

## Task 1: Repair test collection

`python -m pytest tests/ -q` — the command in [README.md:173](README.md#L173) —
currently **aborts at collection**. `tests/test_measure.py` puts `scripts/` on
the path, and decision 28 deleted `scripts/`; `measure.py` now lives in
`planting/`. The whole suite stops, so the other 199 tests do not run either.

**Files:**
- Modify: `tests/test_measure.py:17-18`
- Create: `tests/test_repo_hygiene.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_repo_hygiene.py` — task 2 adds a second test to this
  same file.

- [ ] **Step 1: Reproduce the failure**

Run: `python -m pytest tests/ -q`

Expected: collection error, `ModuleNotFoundError: No module named 'measure'`,
`1 error in 0.5s`, and **zero tests run**.

- [ ] **Step 2: Write the guard test**

Create `tests/test_repo_hygiene.py`:

```python
"""The repo's own plumbing — the checks that fail silently when they rot.

A collection error is the worst kind of red: pytest reports one error and runs
nothing, so a suite that "has no failures" can be a suite that never ran. This
module imports every sibling test module by path, so a broken import is one
failed test among many rather than a stopped suite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

_MODULES = sorted(p for p in TESTS.glob("test_*.py") if p.name != Path(__file__).name)


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.stem)
def test_every_test_module_imports(path: Path):
    spec = importlib.util.spec_from_file_location(f"_hygiene_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
```

- [ ] **Step 3: Run it to see it fail**

Run: `python -m pytest tests/test_repo_hygiene.py -q`

Expected: FAIL on `test_every_test_module_imports[test_measure]` with
`ModuleNotFoundError: No module named 'measure'`. The other module ids pass.

- [ ] **Step 4: Fix the path**

In `tests/test_measure.py`, replace lines 17-18:

```python
# scripts/ is not a package; put it on the path the way measure.py expects.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
```

with:

```python
# planting/ is not a package; put it on the path the way measure.py expects.
# (Was `scripts/` until decision 28 split that grab-bag by concern.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planting"))
```

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS, no collection errors. Count is 199 + the measure module's tests
+ one parametrized hygiene test per module. Record the exact number in the
commit message — it is the baseline the later tasks add to.

- [ ] **Step 6: Commit**

```bash
git add tests/test_measure.py tests/test_repo_hygiene.py
git commit -m "fix: test_measure imports planting/, not the deleted scripts/

Decision 28 moved measure.py; the import was never updated, so
`python -m pytest tests/` aborted at collection and ran zero tests.
test_repo_hygiene now imports every test module by path, so the next
broken import is one red test rather than a stopped suite."
```

---

## Task 2: Kill the stale-path drift, and make it mechanical

Verified stale, all of them live documents:

- `references/rubric.md` **does not exist** — the file is [rubric.md](rubric.md)
  at the repo root. The nonexistent path is cited by the labels, the sabotage
  spec, the plan, the scorer constant, and the rubric's own header.
- `scripts/eval_triage.py`, `scripts/pack_evidence.py`, `scripts/render_prompt.py`
  in [evals/results/07-finding-triager.md:302-308](evals/results/07-finding-triager.md#L302-L308)
  (the "Reproducing" block — every command fails) and in
  [specs/triager-io.md:6](specs/triager-io.md#L6), :169 and :213 — and that spec
  is marked *frozen*.
- [README.md:189-196](README.md#L189-L196) says triager, matcher and eval harness
  are "not yet implemented". All three shipped in step 7.
- [context.yaml:61-70](evals/golden/02-sabotaged/context.yaml#L61-L70) says "18
  must-catch findings" and "MC-114…MC-118". The file has **17** MC labels and
  MC-118 was folded into MC-108 (decision 26).

**Files:**
- Modify: `evals/results/07-finding-triager.md`, `specs/triager-io.md`,
  `README.md`, `evals/golden/02-sabotaged/context.yaml`, `rubric.md`
- Modify: `tests/test_repo_hygiene.py` (add the lint)

**Interfaces:**
- Consumes: `tests/test_repo_hygiene.py` from task 1.
- Produces: `LIVE_DOCS` / `FROZEN` constants in that module — task 9 does not
  depend on them, but a later doc edit will trip the lint.

- [ ] **Step 1: Write the failing lint**

Append to `tests/test_repo_hygiene.py`:

```python
# --- stale-path lint ---------------------------------------------------------
#
# Two paths in this repo name things that do not exist. `scripts/` was split by
# concern (decision 28) and `references/rubric.md` never existed — the file is
# `rubric.md` at the root. Both are still cited, and a documented command that
# fails is worse than no documentation: it reads as reproducible and is not.
#
# Frozen artifacts are exempt BY DESIGN, not by oversight. A prompt version's
# bytes are one of decision 12's four provenance pins; editing v1.0's front
# matter to correct a path would invalidate the 21 recorded runs to fix a
# cosmetic error. The alias is recorded in rubric.md's header instead.
_STALE = {
    "scripts/": "split by concern into crawler/ triage/ planting/ (decision 28)",
    "references/rubric.md": "the file is rubric.md at the repo root",
}

_FROZEN = ("prompts/", "runs/", "_live-check/")


def _live_docs() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("node_modules/", ".git/")) or rel.startswith(_FROZEN):
            continue
        out.append(path)
    return sorted(out)


@pytest.mark.parametrize("path", _live_docs(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_live_doc_names_a_path_that_does_not_exist(path: Path):
    text = path.read_text(encoding="utf-8")
    hits = []
    for stale, why in _STALE.items():
        for number, line in enumerate(text.split("\n"), start=1):
            if stale in line and "STALE-OK" not in line:
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number} names {stale!r} — {why}")
    assert not hits, "\n".join(hits)
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_repo_hygiene.py -q`

Expected: FAIL on several ids, including `specs/triager-io.md`,
`evals/results/07-finding-triager.md`, `plans/07-finding-triager-plan.md`,
`PROJECT-STATE.md`, `rubric.md` and the label files.

- [ ] **Step 3: Fix the reproduction block**

In `evals/results/07-finding-triager.md`, replace the fenced block at lines
302-308 with the paths that exist:

```sh
python triage/eval_triage.py --self-test          # the composite, from the labels alone
python triage/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml -o packs/02-sabotaged.pack.json
python triage/render_prompt.py prompts/finding-triager/v1.0.md \
    --pack packs/02-sabotaged.pack.json --indent 0 -o runs/v1.0.rendered.md
# run the rendered prompt, capture the JSON, then:
python triage/eval_triage.py runs/v1.0-run1.json --prompt-version finding-triager/v1.0
```

Immediately below the block, add:

```markdown
> Paths corrected 2026-07-28: decision 28 split `scripts/` by concern. The
> commands above are the ones that run today; the results in this file were
> produced by the same code under its former path.
```

- [ ] **Step 4: Fix the frozen spec by amendment, not by rewrite**

`specs/triager-io.md` is frozen, and its three `scripts/` references are a
path rename, not a contract change — so amend the header rather than editing
the body. Replace lines 5-6:

```
    rubric:   references/rubric.md v0.4
    pack:     pack/v0.2 (specs §4 below, implemented by scripts/pack_evidence.py)
```

with:

```
    rubric:   rubric.md v0.4
    pack:     pack/v0.2 (specs §4 below, implemented by triage/pack_evidence.py)
    amended:  2026-07-28 — paths only. `scripts/` → `triage/` (decision 28) and
              `references/rubric.md` → `rubric.md`. No clause, field or rule
              changed; the contract this file freezes is untouched.
```

Then update the two body references — `scripts/pack_evidence.py` at §4 line 169
and §4's `PAYLOAD_ONLY` note at line 213 — to `triage/pack_evidence.py`.

- [ ] **Step 5: Record the rubric's canonical path**

The prompts pin `references/rubric.md` and must not be edited. Make the alias a
recorded fact instead. In `rubric.md`, replace line 3:

```
`references/rubric.md` · v0.4 draft · Phase 0 close
```

with:

```
`rubric.md` (canonical path) · v0.4 draft · Phase 0 close

> Cited as `references/rubric.md` in every `finding-triager` prompt front matter
> and in labels written before 2026-07-28. That spelling is an alias for this
> file and always was — there has never been a `references/` directory. Frozen
> artifacts keep the old spelling deliberately: their bytes are a provenance pin
> (decision 12), and correcting a path in them would invalidate 21 recorded runs
> to fix a typo.  <!-- STALE-OK -->
```

- [ ] **Step 6: Fix the README status table**

In `README.md`, replace the three stale rows of the Implementation status table
(lines 191-196) with:

```markdown
| Crawler (`crawler/`) | **Implemented and tested** — `specs/crawler.md` v0.1 |
| Scoring rubric (`rubric.md`) | v0.4; calibrated against entry 02, not yet frozen |
| Golden set (`evals/golden/`) | Entries 02 (17 MC / 4 MNC, frozen) & 05 (labeled); 01/03/04 not yet present |
| Triager (`prompts/finding-triager/`) | **v1.0 frozen** — 21 recorded runs, in-sample (see `evals/PROMOTION-PROTOCOL.md`) |
| Narrator / report composer | Specified; **not yet implemented** |
| `references/benchmarks.md` | Referenced by the rubric; **not yet present**  <!-- STALE-OK --> |
| Eval harness (`triage/eval_triage.py`) | **Implemented** — matcher, tiered recall, composite, MNC screens |
```

Also fix the Repository layout block (line 62 onward) by adding, after the
`evals/golden/` group:

```
triage/                   the eval loop — pack_evidence · render_prompt · eval_triage
planting/                 defect-planting tooling (measure · inspect_lcp · fit_image)
prompts/                  finding-triager v0.1 … v1.0, registry-versioned
```

- [ ] **Step 7: Fix the label count in context.yaml**

In `evals/golden/02-sabotaged/context.yaml`, replace the `expect:` comment at
lines 61-65 with:

```yaml
    # From fixtures/02-sabotaged, rubric v0.3. Composite = 24 from the 17
    # must-catch findings; band "Critical". Recomputed 2026-07-28 when four
    # findings were promoted out of the unlabeled bucket (MC-114…MC-117; a
    # fifth candidate, MC-118, was folded into MC-108 rather than added) — the
    # 13-label value was 35 / "Significant work needed", and the runs recorded
    # against it in evals/results/07-finding-triager.md are scored on that basis.
```

- [ ] **Step 8: Sweep the remainder**

Run: `python -m pytest tests/test_repo_hygiene.py -q`

For each remaining failure, apply the same rule: **live doc → fix the path;
historical record of what was true then → append ` <!-- STALE-OK -->` to that
line with a one-clause reason.** `PROJECT-STATE.md`'s decision-28 paragraph and
`plans/07-finding-triager-plan.md` are historical records (they describe the
layout *before* the split) and take the marker; the label files' `rubric:`
headers are live pins and take the path fix.

- [ ] **Step 9: Verify and commit**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS, count = task 1's baseline + one hygiene test per markdown file.

```bash
git add -A
git commit -m "docs: correct stale paths and label counts; lint them mechanically

scripts/ was split by decision 28 and references/rubric.md never existed, so
every documented reproduction command failed and the frozen I/O spec named a
deleted file. README claimed three shipped components were unimplemented;
context.yaml said 18 MC labels where the file has 17.

Frozen artifacts (prompts/, runs/) keep the old spelling — their bytes are a
provenance pin. The alias is recorded in rubric.md's header instead."
```

---

## Task 3: Archive the golden fixture

`fixtures/` is gitignored (decision 19) and the commitment is the manifest hash
`b219afac…`. But that hash commits to bytes that exist on exactly one machine,
produced from a **live third-party store that has already drifted** — a 4-hour
document-cache freeze, a collection-membership race, apps installed and
disabled, a theme on a sabotage branch in a separate repo. The store cannot be
rewound to 2026-07-27 16:39. Lose the directory and entry 02 is gone.

**Files:**
- Create: `crawler/archive.py`
- Create: `tests/test_archive.py`
- Modify: `README.md` (usage), `.gitignore` (ignore the archive output dir)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `crawler.archive.archive(fixture_dir: Path, out_path: Path) -> str` —
    writes a `.tar.gz`, returns the archived `manifest.yaml`'s sha256.
  - `crawler.archive.manifest_sha256_in(archive_path: Path) -> str | None`
  - `crawler.archive.verify(archive_path: Path, expected: str) -> bool`
  - CLI: `python -m crawler.archive <fixture_dir> -o <path>` / `--verify <sha>`

- [ ] **Step 1: Write the failing test**

Create `tests/test_archive.py`:

```python
"""crawler/archive.py — the golden fixture's only backup.

The archive's own sha256 is NOT the commitment: gzip embeds an mtime, so two
archives of identical bytes differ. The commitment is what it already was —
the sha256 of manifest.yaml (decision 12) — so verification reads that member
out of the tar and hashes it. An archive that round-trips but reports a
different manifest hash is a corrupted backup, and that is the case worth
catching.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("crawler_archive", ROOT / "crawler" / "archive.py")
archive_mod = importlib.util.module_from_spec(_spec)
sys.modules["crawler_archive"] = archive_mod
_spec.loader.exec_module(archive_mod)


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "02-sabotaged"
    (fixture / "nested").mkdir(parents=True)
    (fixture / "manifest.yaml").write_text("crawler_version: 0.2.0\n", encoding="utf-8")
    (fixture / "crawl.json").write_text('{"schema": "crawl/v0.1"}', encoding="utf-8")
    (fixture / "nested" / "extra.json").write_text("{}", encoding="utf-8")
    return fixture


def test_archive_contains_every_file_under_the_fixture(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "02-sabotaged.tar.gz"
    archive_mod.archive(fixture, out)
    with tarfile.open(out, "r:gz") as tar:
        names = sorted(tar.getnames())
    assert names == [
        "02-sabotaged/crawl.json",
        "02-sabotaged/manifest.yaml",
        "02-sabotaged/nested/extra.json",
    ]


def test_archive_returns_the_manifest_hash_not_the_tarball_hash(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "a.tar.gz"
    returned = archive_mod.archive(fixture, out)
    expected = hashlib.sha256((fixture / "manifest.yaml").read_bytes()).hexdigest()
    assert returned == expected
    assert returned != hashlib.sha256(out.read_bytes()).hexdigest()


def test_verify_reads_the_manifest_back_out_of_the_tar(tmp_path):
    fixture = _fixture(tmp_path)
    out = tmp_path / "a.tar.gz"
    digest = archive_mod.archive(fixture, out)
    assert archive_mod.manifest_sha256_in(out) == digest
    assert archive_mod.verify(out, digest) is True
    assert archive_mod.verify(out, "0" * 64) is False


def test_a_fixture_with_no_manifest_is_refused(tmp_path):
    fixture = tmp_path / "empty"
    fixture.mkdir()
    (fixture / "crawl.json").write_text("{}", encoding="utf-8")
    try:
        archive_mod.archive(fixture, tmp_path / "a.tar.gz")
    except SystemExit as exit_:
        assert "manifest.yaml" in str(exit_)
    else:
        raise AssertionError("archiving a fixture with no manifest must fail loudly")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_archive.py -q`

Expected: collection error — `FileNotFoundError: crawler/archive.py`.

- [ ] **Step 3: Write the implementation**

Create `crawler/archive.py`:

```python
"""Archive a captured fixture directory, and verify it by manifest hash.

Decision 19 keeps `fixtures/` out of git: the commitment is the manifest hash
recorded in `expected/findings.md` and `context.yaml`, not the capture bytes.
That is a sound commitment and a poor backup — the hash commits to bytes held on
one machine, produced from a live store that has since drifted. The store cannot
be rewound, so a lost fixture is a lost golden entry.

This writes the directory to one file you can put somewhere durable, and
verifies it against the pin the labels already carry. The tarball's own sha256
is deliberately NOT the check: gzip embeds an mtime, so it is not stable across
runs. `manifest.yaml`'s sha256 is, and it is the value decision 12 already pins.

Usage:
    python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
    python -m crawler.archive --check archives/02-sabotaged.tar.gz \\
        --expect b219afac6f8234ff98ce6c4eaf004bdb4063aaf1155de78b0fe19c6512946d20
"""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

MANIFEST = "manifest.yaml"


def archive(fixture_dir: Path, out_path: Path) -> str:
    """Tar+gzip every file under `fixture_dir`. Returns its manifest sha256."""
    fixture_dir = Path(fixture_dir)
    manifest = fixture_dir / MANIFEST
    if not manifest.exists():
        raise SystemExit(f"{fixture_dir} has no {MANIFEST} — that is not a capture, refusing to archive it")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in fixture_dir.rglob("*") if p.is_file())
    with tarfile.open(out_path, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(fixture_dir.parent).as_posix()))
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def manifest_sha256_in(archive_path: Path) -> str | None:
    """The archived manifest's sha256, read back out of the tar."""
    with tarfile.open(Path(archive_path), "r:gz") as tar:
        member = next((m for m in tar.getmembers()
                       if Path(m.name).name == MANIFEST and m.isfile()), None)
        if member is None:
            return None
        handle = tar.extractfile(member)
        if handle is None:
            return None
        return hashlib.sha256(handle.read()).hexdigest()


def verify(archive_path: Path, expected: str) -> bool:
    return manifest_sha256_in(archive_path) == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("fixture_dir", nargs="?", type=Path)
    parser.add_argument("-o", "--out", type=Path)
    parser.add_argument("--check", type=Path, help="verify an existing archive instead of writing one")
    parser.add_argument("--expect", help="the manifest sha256 the labels pin")
    args = parser.parse_args(argv)

    if args.check:
        found = manifest_sha256_in(args.check)
        print(f"{args.check}  manifest sha256 {found}")
        if args.expect:
            ok = found == args.expect
            print("MATCHES the pin" if ok else f"DOES NOT MATCH — pin is {args.expect}")
            return 0 if ok else 1
        return 0

    if not args.fixture_dir or not args.out:
        parser.error("a fixture_dir and -o are required unless --check")
    digest = archive(args.fixture_dir, args.out)
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"{args.out}  {size_mb:.1f} MB  manifest sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_archive.py -q`

Expected: PASS, 4 passed.

- [ ] **Step 5: Archive the real fixture and verify it against the pin**

Run:

```bash
python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
python -m crawler.archive --check archives/02-sabotaged.tar.gz \
    --expect b219afac6f8234ff98ce6c4eaf004bdb4063aaf1155de78b0fe19c6512946d20
```

Expected: the second command prints `MATCHES the pin` and exits 0. **If it does
not match, stop and report** — the working fixture is not the one the labels
were written against, and every recorded v1.0 result is in question.

Then archive `fixtures/05` the same way (its labels carry no pin; the `--check`
run will print the hash, which is the value task 5 will ask you to record).

- [ ] **Step 6: Ignore the archives, and say where they go**

Append to `.gitignore`:

```
# Fixture archives — the durable backup of a capture. Large, and regenerable
# from the fixture, but the fixture itself is not regenerable (the store has
# drifted). Copy these somewhere off this machine; the manifest hash inside is
# the same pin the labels carry.
/archives/
```

Append to `README.md`, after the crawler Usage block:

```markdown
### Backing up a capture

`fixtures/` is gitignored and the store it came from has drifted, so a capture
is not reproducible — only restorable.

```bash
python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
python -m crawler.archive --check archives/02-sabotaged.tar.gz --expect <manifest sha256>
```

Copy `archives/` somewhere off this machine. The `--expect` value is the
`manifest:` line in that entry's `expected/findings.md`.
```

- [ ] **Step 7: Commit**

```bash
git add crawler/archive.py tests/test_archive.py .gitignore README.md
git commit -m "feat: archive a fixture, verify it by manifest hash

fixtures/ is gitignored and the store it was captured from has drifted, so
entry 02 exists on exactly one machine and cannot be recaptured. This writes
it to one file and verifies it against the pin the labels already carry —
manifest.yaml's sha256, not the tarball's, which gzip's mtime makes unstable."
```

---

## Task 4: Pin the toolchain that produces the ground truth

Verified: `requirements.txt` says `playwright>=1.44`; `package.json` says
`^12.2.1` lighthouse and `^4.10.2` axe-core — README calls these "pinned"; caret
ranges are not pins. The labels are Lighthouse- and Chrome-version-sensitive by
construction (LCP/CLS thresholds, axe rule IDs), and one label already sits
85 ms under a threshold. A clean install can move the ground truth.

Installed today, and matching entry 02's recorded provenance: playwright 1.61.0,
PyYAML 6.0.3, pytest 9.1.1, lighthouse 12.8.2, axe-core 4.12.1.

**Files:**
- Modify: `requirements.txt`, `package.json`, `README.md`
- Create: `tests/test_toolchain_pins.py`

**Interfaces:**
- Consumes: `eval.fixtures.{lighthouse_version,axe_core_version}` from
  `evals/golden/02-sabotaged/context.yaml`.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing test**

Create `tests/test_toolchain_pins.py`:

```python
"""The toolchain is an input to the ground truth, so it is pinned like one.

Entry 02's labels were measured with lighthouse 12.8.2 / axe-core 4.12.1 /
chrome 149.0.7827.55, and MC-107 sits 85 ms under the 4.0 s boundary. A caret
range lets a clean `npm install` move a label. manifest.yaml records the
versions, so drift is *detectable* — nothing prevented it, and nothing compared
the installed versions to the ones the labels were written against.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml"


def _entry_02_provenance() -> dict:
    data = yaml.safe_load(CONTEXT.read_text(encoding="utf-8")) or {}
    return (data.get("eval") or {}).get("fixtures") or {}


def test_package_json_pins_exact_versions():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    loose = {name: spec for name, spec in pkg["dependencies"].items()
             if not spec[:1].isdigit()}
    assert not loose, f"not pinned to an exact version: {loose}"


def test_requirements_pins_exact_versions():
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").split("\n")]
    reqs = [line for line in lines if line and not line.startswith("#")]
    loose = [line for line in reqs if "==" not in line]
    assert not loose, f"not pinned to an exact version: {loose}"


def test_node_pins_match_the_versions_entry_02_was_labeled_under():
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    packages = lock["packages"]
    provenance = _entry_02_provenance()
    assert packages["node_modules/lighthouse"]["version"] == provenance["lighthouse_version"]
    assert packages["node_modules/axe-core"]["version"] == provenance["axe_core_version"]


def test_package_json_and_lock_agree():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for name, spec in pkg["dependencies"].items():
        assert lock["packages"][f"node_modules/{name}"]["version"] == spec, name
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_toolchain_pins.py -q`

Expected: FAIL on `test_package_json_pins_exact_versions` (`{'axe-core':
'^4.10.2', 'lighthouse': '^12.2.1'}`) and on
`test_requirements_pins_exact_versions` (`['playwright>=1.44', 'PyYAML>=6.0',
'pytest>=8.0']`). The two lock tests already pass.

- [ ] **Step 3: Pin package.json**

Replace the `dependencies` block in `package.json` with:

```json
  "dependencies": {
    "axe-core": "4.12.1",
    "lighthouse": "12.8.2"
  }
```

- [ ] **Step 4: Pin requirements.txt**

Replace the file's contents with:

```
# Pinned exactly, not floored. These versions are an input to the ground truth:
# entry 02's labels were measured under playwright 1.61.0 (chromium 149) and one
# of them (MC-107, home LCP 3.92s) sits 85ms under a rubric threshold. A floor
# lets a clean install move a label. tests/test_toolchain_pins.py holds the line.

# Runtime
playwright==1.61.0

# --context reads a golden entry's context.yaml. The CLI falls back to a two-key
# line scan when this is absent, so it is genuinely optional — but the harness
# (triage/eval_triage.py) imports it unconditionally.
PyYAML==6.0.3

# Tests
pytest==9.1.1
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_toolchain_pins.py -q`

Expected: PASS, 4 passed.

- [ ] **Step 6: Correct the install instructions**

In `README.md`, replace the Setup block (lines 108-112) with:

```bash
python -m pip install --user -r requirements.txt   # exact pins — see the file
python -m playwright install chromium
npm ci                                             # ci, not install: honours the lock
```

and replace the note beneath it with:

```markdown
> On this machine global pip is broken; use `python -m pip install --user` and
> call tools as modules (`python -m pytest`, `python -m playwright`).
>
> Use `npm ci`, never `npm install`. The pinned Lighthouse and axe-core versions
> are an input to the golden labels, and `npm install` may resolve past them.
```

- [ ] **Step 7: Verify the whole suite and commit**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS.

```bash
git add requirements.txt package.json README.md tests/test_toolchain_pins.py
git commit -m "build: pin the toolchain exactly; assert it matches entry 02

The labels are Lighthouse- and Chrome-version-sensitive by construction and
MC-107 sits 85ms under a threshold, so a caret range can move the ground truth.
package.json now pins 12.8.2/4.12.1 and requirements.txt pins playwright
1.61.0 — the versions entry 02 was captured and labeled under. A test compares
the lock to context.yaml's recorded provenance, so drift is a red test."
```

---

## Task 5: Verify the four provenance pins instead of printing them

Decision 12: *"every run records fixture-manifest hash + prompt version + rubric
version + pack version. Green without all four pinned is not a result."*
Verified in [triage/eval_triage.py:911-920](triage/eval_triage.py#L911-L920):
the fixture hash is **computed and never compared** to the labels' `manifest:`
pin; `--prompt-version` defaults to the free-text string `"unpinned"`;
`RUBRIC_VERSION` is a hardcoded constant (currently `v0.4`, while every prompt
pins v0.3) that cannot detect a rubric edit; `--pack-version` is a flag. Four
pins, all operator-asserted, none verified.

**Files:**
- Modify: `triage/eval_triage.py`
- Create: `tests/test_provenance.py`

**Interfaces:**
- Consumes: `crawler.archive` is *not* used here; this reads
  `fixtures/<entry>/manifest.yaml` directly, as `main()` already does.
- Produces, all in `eval_triage`:
  - `expected_manifest_sha256(entry: Path) -> str | None`
  - `rubric_version(path: Path = RUBRIC_PATH) -> str`
  - `resolve_prompt_version(name: str, prompts_dir: Path) -> str`
  - `provenance(entry, fixtures, prompt_version, pack_version, *, allow_unpinned=False) -> dict`
    — raises `SystemExit` on a mismatch. Task 7 adds `harness_version` to the
    dict it returns.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_provenance.py`:

```python
"""Decision 12's four pins, actually enforced.

The scorer printed all four and checked none. The one it computes — the fixture
manifest hash — was never compared to the pin the labels carry, so scoring a run
against a re-captured fixture printed a different hash and passed. That is the
failure mode this project exists to prevent, sitting inside the tool built to
catch it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)


def _entry(tmp_path: Path, pin: str | None) -> Path:
    entry = tmp_path / "entry"
    (entry / "expected").mkdir(parents=True)
    fixtures_line = f'    manifest_sha256: "{pin}"\n' if pin else ""
    (entry / "context.yaml").write_text(
        "store:\n  origin: https://example.test/\n"
        "eval:\n  fixtures:\n" + (fixtures_line or "    captured_at: null\n"),
        encoding="utf-8")
    (entry / "expected" / "findings.md").write_text("# labels\n", encoding="utf-8")
    return entry


def _fixtures(tmp_path: Path, body: str) -> Path:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "manifest.yaml").write_text(body, encoding="utf-8")
    return fixtures


def test_a_matching_fixture_hash_is_recorded(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    assert record["fixture_manifest_sha256"] == digest
    assert record["fixture_pin"] == "matched"


def test_a_mismatched_fixture_hash_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.3.0\n")   # recaptured
    entry = _entry(tmp_path, "0" * 64)                            # labels pin the old one
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    assert "does not match" in str(caught.value)


def test_an_absent_pin_is_fatal_unless_allowed(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    entry = _entry(tmp_path, None)
    with pytest.raises(SystemExit):
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0",
                                    "pack/v0.2", allow_unpinned=True)
    assert record["fixture_pin"] == "absent"


def test_an_unknown_prompt_version_is_fatal(tmp_path):
    fixtures = _fixtures(tmp_path, "x: 1\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v9.9", "pack/v0.2")
    assert "names no prompt file" in str(caught.value)
    with pytest.raises(SystemExit):
        eval_triage.provenance(entry, fixtures, "unpinned", "pack/v0.2")


def test_the_rubric_version_is_read_from_the_file_not_hardcoded(tmp_path):
    real = eval_triage.rubric_version()
    assert real.startswith("rubric.md v")
    copy = tmp_path / "rubric.md"
    copy.write_text("# Scoring rubric\n\n`rubric.md` · v9.9 draft\n\n---\n", encoding="utf-8")
    assert eval_triage.rubric_version(copy).startswith("rubric.md v9.9+")
    assert eval_triage.rubric_version(copy) != real


def test_the_live_prompts_and_the_live_rubric_resolve():
    # The real repo, not a fixture: v1.0 must exist and rubric.md must parse.
    assert eval_triage.resolve_prompt_version("finding-triager/v1.0", ROOT / "prompts")
    assert "unknown" not in eval_triage.rubric_version()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_provenance.py -q`

Expected: 6 failed — `AttributeError: module 'eval_triage' has no attribute
'provenance'` (and `rubric_version`, `resolve_prompt_version`).

- [ ] **Step 3: Replace the hardcoded constant**

In `triage/eval_triage.py`, replace line 47:

```python
RUBRIC_VERSION = "references/rubric.md v0.4"
```

with:

```python
ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = ROOT / "rubric.md"
PROMPTS_DIR = ROOT / "prompts"
```

- [ ] **Step 4: Add the provenance functions**

Insert into `triage/eval_triage.py`, immediately after `status_for()` (after
line 127):

```python
# ---------------------------------------------------------------------------
# provenance — decision 12's four pins, verified rather than printed
# ---------------------------------------------------------------------------
#
# The scorer used to compute the fixture hash and never compare it, name the
# rubric in a string constant that could not notice a rubric edit, and accept
# any text at all as a prompt version. All four pins were operator-asserted.
# A pin nobody checks is a comment.

def rubric_version(path: Path = RUBRIC_PATH) -> str:
    """`rubric.md v0.4+<sha8>` — derived from the file, so an edit shows up.

    The version number is the rubric's own header claim; the digest is what
    makes the pin honest. Two runs whose rubric text differed by one clause
    carry different pins even if nobody bumped the version.
    """
    text = path.read_text(encoding="utf-8")
    header = text.split("\n---", 1)[0]
    match = re.search(r"\bv(\d+\.\d+)\b", header)
    version = match.group(1) if match else "unknown"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    return f"rubric.md v{version}+{digest}"


def resolve_prompt_version(name: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    """`finding-triager/v1.0` must name a prompt file that exists."""
    if not name or name == "unpinned":
        raise SystemExit(
            "--prompt-version is required: a run scored without a prompt pin is not "
            "a result (decision 12)")
    path = prompts_dir / f"{name}.md"
    if not path.exists():
        raise SystemExit(f"--prompt-version {name!r} names no prompt file ({path})")
    return name


def expected_manifest_sha256(entry: Path) -> str | None:
    """The fixture hash the labels were written against.

    `context.yaml eval.fixtures.manifest_sha256` is authoritative; the label
    file's `manifest:` header is the fallback, because entry 02 carries both and
    a future entry might carry only one.
    """
    context = Path(entry) / "context.yaml"
    if context.exists():
        data = yaml.safe_load(context.read_text(encoding="utf-8")) or {}
        pin = ((data.get("eval") or {}).get("fixtures") or {}).get("manifest_sha256")
        if pin:
            return str(pin).strip()
    labels = Path(entry) / "expected" / "findings.md"
    if labels.exists():
        match = re.search(r"^\s*manifest:\s*([0-9a-f]{64})\s*$",
                          labels.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)
    return None


def provenance(entry: Path, fixtures: Path, prompt_version: str, pack_version: str,
               *, allow_unpinned: bool = False) -> dict[str, Any]:
    """All four pins, verified. Raises SystemExit rather than scoring blind."""
    manifest = Path(fixtures) / "manifest.yaml"
    computed = (hashlib.sha256(manifest.read_bytes()).hexdigest()
                if manifest.exists() else None)
    pinned = expected_manifest_sha256(entry)

    if pinned and computed and pinned != computed:
        raise SystemExit(
            f"fixture manifest hash does not match the pin.\n"
            f"  labels pin: {pinned}\n"
            f"  {manifest}: {computed}\n"
            "The labels describe a different capture than the one being scored. "
            "Re-label, or point --fixtures at the archived capture "
            "(python -m crawler.archive --check).")
    if not pinned and not allow_unpinned:
        raise SystemExit(
            f"{entry} records no fixture manifest hash, so this run cannot be pinned "
            "(decision 12). Record eval.fixtures.manifest_sha256 in context.yaml, or "
            "pass --allow-unpinned-fixture and accept that the result is not a result.")
    if not computed:
        raise SystemExit(f"{manifest} is missing — nothing to pin.")

    return {
        "fixture_manifest_sha256": computed,
        "fixture_pin": "matched" if pinned else "absent",
        "prompt_version": resolve_prompt_version(prompt_version),
        "rubric_version": rubric_version(),
        "pack_version": pack_version,
    }
```

- [ ] **Step 5: Run the provenance tests**

Run: `python -m pytest tests/test_provenance.py -q`

Expected: PASS, 6 passed.

- [ ] **Step 6: Use it in `main()`**

In `triage/eval_triage.py`, add the flag after line 897:

```python
    parser.add_argument("--allow-unpinned-fixture", action="store_true",
                        help="score against a fixture the entry does not pin (not a result)")
```

Replace the record-building block at lines 911-922 with:

```python
    record = {
        "provenance": provenance(args.entry, args.fixtures, args.prompt_version,
                                 args.pack_version,
                                 allow_unpinned=args.allow_unpinned_fixture)
                      | {"run_file": str(args.output)},
        "result": result,
    }
```

and replace the header print at line 928 with:

```python
    prov = record["provenance"]
    print(f"== {args.output.name} · {prov['prompt_version']} · {prov['rubric_version']} "
          f"· {prov['pack_version']} · fixture {prov['fixture_manifest_sha256'][:12]} "
          f"({prov['fixture_pin']})")
```

Finally, replace every other `RUBRIC_VERSION` reference in the file with
`rubric_version()`. Find them with:

Run: `python -c "import pathlib,re; t=pathlib.Path('triage/eval_triage.py').read_text(encoding='utf-8'); print([n+1 for n,l in enumerate(t.split(chr(10))) if 'RUBRIC_VERSION' in l])"`

Expected after the edits: `[]`.

- [ ] **Step 7: Re-score a recorded run end to end**

Run:

```bash
python triage/eval_triage.py runs/v1.0-run1.json --prompt-version finding-triager/v1.0
```

Expected: the header now prints the fixture hash and `(matched)`, and the
verdict is unchanged from the value recorded in
`evals/results/07-finding-triager.md`. **If the verdict changed, stop** — the
scorer's behaviour was supposed to be untouched by this task.

Then confirm the guard bites:

```bash
python triage/eval_triage.py runs/v1.0-run1.json --prompt-version finding-triager/v1.0 --fixtures fixtures/05
```

Expected: exits non-zero with `fixture manifest hash does not match the pin`.

- [ ] **Step 8: Run the whole suite and commit**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS. If `tests/test_eval_triage.py` now fails because a test calls
`main()` without `--prompt-version`, add the flag to that call — do not relax
the check.

```bash
git add triage/eval_triage.py tests/test_provenance.py
git commit -m "feat: verify decision 12's four pins instead of printing them

The fixture hash was computed and never compared to the pin the labels carry,
so scoring against a recaptured fixture printed a different hash and passed.
The rubric version was a hardcoded string that could not notice a rubric edit,
and --prompt-version accepted any text (default: 'unpinned').

Now: hash mismatch is fatal, the rubric version is derived from the file plus
its digest, and a prompt version must name a prompt file that exists."
```

---

## Task 6: A scripted runner, with the model and its parameters recorded

Verified: `runs/*.json` contain exactly `{schema, findings}` — no model ID, no
parameters, no timestamp. `evals/results/07-finding-triager.md:311-313` records
the runs as *"independent agent sessions… There is no scripted API runner yet."*
So "3 of 3 pass" cannot be re-run, and N=3 with an unrecorded sampler is not a
rate.

**Files:**
- Create: `triage/run_triager.py`
- Create: `tests/test_run_triager.py`
- Modify: `triage/eval_triage.py` (accept a wrapped run record)
- Modify: `requirements.txt`, `README.md`

**Interfaces:**
- Consumes: `crawler.dotenv.load(path)` → `list[str]`;
  `triage/render_prompt.py`'s `render(template, pack, indent)` →
  `(text, prompt_version)`.
- Produces:
  - `run_triager.run_meta(model, effort, max_tokens, rendered_path, pack_path, prompt_version, started_at) -> dict`
  - `run_triager.extract_json(text: str) -> dict`
  - run files shaped `{"run_meta": {...}, "output": {schema, findings}}`
  - `eval_triage.load_run_output(path: Path) -> tuple[dict, dict | None]` —
    returns `(output, run_meta)`, accepting both the wrapped shape and the 21
    bare recorded runs.

- [ ] **Step 1: Write the failing tests (offline — no network)**

Create `tests/test_run_triager.py`:

```python
"""triage/run_triager.py — the thing that makes a run reproducible.

No test here touches the network. What is worth testing is exactly what the 21
recorded runs lack: that the run file carries the model and the parameters that
produced it, and that the scorer can still read the old bare-output shape.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_triager = _load("run_triager", "triage/run_triager.py")
eval_triage = _load("eval_triage", "triage/eval_triage.py")


def test_run_meta_records_the_model_and_every_parameter(tmp_path):
    rendered = tmp_path / "r.md"
    rendered.write_text("prompt body", encoding="utf-8")
    pack = tmp_path / "p.json"
    pack.write_text('{"pack": "pack/v0.2"}', encoding="utf-8")

    meta = run_triager.run_meta(
        model="claude-opus-5", effort="high", max_tokens=32000,
        rendered_path=rendered, pack_path=pack,
        prompt_version="finding-triager/v1.0", started_at="2026-07-28T10:00:00+08:00")

    for key in ("model", "effort", "thinking", "max_tokens", "prompt_version",
                "rendered_sha256", "pack_sha256", "pack_version", "started_at",
                "sdk_version"):
        assert key in meta, key
    assert meta["model"] == "claude-opus-5"
    assert len(meta["rendered_sha256"]) == 64
    # Opus 5 rejects temperature/top_p/top_k, so there is no sampler to record —
    # say so in the record rather than leaving a reader to wonder.
    assert meta["sampling"] == "not applicable (claude-opus-5 rejects temperature/top_p/top_k)"


def test_extract_json_tolerates_a_fenced_response():
    payload = '{"schema": "triage/v0.1", "findings": []}'
    assert run_triager.extract_json(payload)["schema"] == "triage/v0.1"
    assert run_triager.extract_json(f"```json\n{payload}\n```")["schema"] == "triage/v0.1"
    with pytest.raises(SystemExit):
        run_triager.extract_json("I could not produce JSON.")


def test_the_scorer_reads_both_run_shapes(tmp_path):
    bare = tmp_path / "bare.json"
    bare.write_text('{"schema": "triage/v0.1", "findings": []}', encoding="utf-8")
    output, meta = eval_triage.load_run_output(bare)
    assert output["schema"] == "triage/v0.1"
    assert meta is None

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({
        "run_meta": {"model": "claude-opus-5"},
        "output": {"schema": "triage/v0.1", "findings": []},
    }), encoding="utf-8")
    output, meta = eval_triage.load_run_output(wrapped)
    assert output["schema"] == "triage/v0.1"
    assert meta["model"] == "claude-opus-5"


def test_the_21_recorded_runs_still_load():
    for path in sorted((ROOT / "runs").glob("*.json")):
        output, meta = eval_triage.load_run_output(path)
        assert output.get("schema") == "triage/v0.1", path.name
        assert meta is None, f"{path.name} was rewritten — recorded runs are frozen"
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_run_triager.py -q`

Expected: collection error — `FileNotFoundError: triage/run_triager.py`.

- [ ] **Step 3: Install the SDK and pin it**

Run: `python -m pip install --user anthropic`

Then run `python -c "import anthropic; print(anthropic.__version__)"` and add
the printed version to `requirements.txt`:

```
# The scripted runner (triage/run_triager.py). Pinned like the rest: the SDK
# version is part of what produced a run, so it goes in the run record.
anthropic==<the version you printed>
```

- [ ] **Step 4: Write the runner**

Create `triage/run_triager.py`:

```python
"""Run a rendered finding-triager prompt through the API and record the run.

Why this exists: the first 21 recorded runs were executed as agent sessions.
Their JSON carries `schema` and `findings` and nothing else — no model, no
parameters, no timestamp — so "3 of 3 clear every bar" cannot be re-run and
N=3 with an unrecorded sampler is not a rate.

The run record wraps the model's output rather than merging into it. The
model's JSON is evidence and stays byte-exact; the harness's metadata sits
beside it. `eval_triage.load_run_output` reads both this shape and the bare
shape the 21 recorded runs use.

Model notes, because they are load-bearing for reproducibility:
  * `claude-opus-5` **rejects** temperature / top_p / top_k (HTTP 400). There is
    no sampler knob to pin; what varies run to run is effort and thinking, and
    both are recorded.
  * Thinking is ON by default on this model, and `max_tokens` caps thinking plus
    response together — hence the generous default.
  * The rendered prompt is ~145k tokens, so the request streams. A non-streaming
    call at this size risks an HTTP timeout.

Usage:
    python triage/run_triager.py runs/v1.0.rendered.md \\
        --pack packs/02-sabotaged.pack.json \\
        --prompt-version finding-triager/v1.0 -o runs/v1.0-run4.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import dotenv  # noqa: E402

MODEL = "claude-opus-5"
EFFORT = "high"
THINKING = "adaptive"
MAX_TOKENS = 32000

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_meta(*, model: str, effort: str, max_tokens: int, rendered_path: Path,
             pack_path: Path, prompt_version: str, started_at: str) -> dict[str, Any]:
    """Everything needed to run this again and get a comparable result."""
    try:
        import anthropic
        sdk_version = getattr(anthropic, "__version__", "unknown")
    except ImportError:  # the metadata builder stays importable without the SDK
        sdk_version = "not installed"
    pack = json.loads(Path(pack_path).read_text(encoding="utf-8"))
    return {
        "model": model,
        "effort": effort,
        "thinking": THINKING,
        "max_tokens": max_tokens,
        "sampling": "not applicable (claude-opus-5 rejects temperature/top_p/top_k)",
        "prompt_version": prompt_version,
        "rendered_sha256": _sha256(rendered_path),
        "pack_sha256": _sha256(pack_path),
        "pack_version": pack.get("pack"),
        "fixture_manifest_sha256": (pack.get("provenance") or {}).get("manifest_sha256"),
        "started_at": started_at,
        "sdk_version": sdk_version,
    }


def extract_json(text: str) -> dict[str, Any]:
    """The contract says one JSON object and no prose. Tolerate a fence, only."""
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"the model's reply is not one JSON object ({error}). "
            f"First 200 chars: {text[:200]!r}")


def call_model(prompt: str, *, model: str, effort: str, max_tokens: int) -> tuple[str, dict]:
    """One streamed request. Returns (text, usage)."""
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        output_config={"effort": effort},
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise SystemExit(f"the request was declined: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise SystemExit(
            f"output hit max_tokens ({max_tokens}) — thinking and response share the "
            "budget on this model; re-run with a larger --max-tokens")

    text = "".join(block.text for block in message.content if block.type == "text")
    usage = {"input_tokens": message.usage.input_tokens,
             "output_tokens": message.usage.output_tokens,
             "stop_reason": message.stop_reason}
    return text, usage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rendered", type=Path, help="a rendered prompt from render_prompt.py")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    loaded = dotenv.load(args.env_file)
    if loaded:
        print(f"· loaded {len(loaded)} var(s) from {args.env_file}: {', '.join(loaded)}")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    meta = run_meta(model=args.model, effort=args.effort, max_tokens=args.max_tokens,
                    rendered_path=args.rendered, pack_path=args.pack,
                    prompt_version=args.prompt_version, started_at=started_at)

    prompt = args.rendered.read_text(encoding="utf-8")
    print(f"· {args.model} effort={args.effort} thinking={THINKING} "
          f"max_tokens={args.max_tokens} · prompt {len(prompt) / 1024:.0f} KB")
    text, usage = call_model(prompt, model=args.model, effort=args.effort,
                             max_tokens=args.max_tokens)
    meta["usage"] = usage

    record = {"run_meta": meta, "output": extract_json(text)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    findings = len(record["output"].get("findings") or [])
    print(f"✓ {args.out} · {findings} findings · "
          f"{usage['input_tokens']} in / {usage['output_tokens']} out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Teach the scorer both shapes**

In `triage/eval_triage.py`, add after `provenance()`:

```python
def load_run_output(path: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Read a run file. Returns (triage output, run_meta or None).

    Two shapes, deliberately. The 21 runs recorded before `triage/run_triager.py`
    existed are the model's bare JSON, and they are frozen evidence — rewriting
    them to a new shape would edit the record to suit the tool. Runs produced by
    the runner wrap that same JSON in `output` and put the model, the parameters
    and the digests beside it in `run_meta`.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data.get("output"), dict) and "run_meta" in data:
        return data["output"], data["run_meta"]
    return data, None
```

Then in `main()`, replace line 908:

```python
    output = json.loads(args.output.read_text(encoding="utf-8"))
```

with:

```python
    output, run_meta = load_run_output(args.output)
```

and add `"run_meta": run_meta,` to the `record["provenance"]` dict construction
in step 6 of task 5 — i.e. change that block to:

```python
    record = {
        "provenance": provenance(args.entry, args.fixtures, args.prompt_version,
                                 args.pack_version,
                                 allow_unpinned=args.allow_unpinned_fixture)
                      | {"run_file": str(args.output), "run_meta": run_meta},
        "result": result,
    }
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_run_triager.py -q`

Expected: PASS, 4 passed. `test_the_21_recorded_runs_still_load` proves the
frozen runs were not touched.

- [ ] **Step 7: One live run, end to end**

This step costs money and needs `ANTHROPIC_API_KEY` in `.env` or the
environment. **If no key is available, stop here and report that** — do not
fake a run file.

```bash
python triage/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml -o packs/02-sabotaged.pack.json
python triage/render_prompt.py prompts/finding-triager/v1.0.md \
    --pack packs/02-sabotaged.pack.json --indent 0 -o runs/v1.0.rendered.md
python triage/run_triager.py runs/v1.0.rendered.md --pack packs/02-sabotaged.pack.json \
    --prompt-version finding-triager/v1.0 -o runs/v1.0-run4.json
python triage/eval_triage.py runs/v1.0-run4.json --prompt-version finding-triager/v1.0
```

Expected: the run file exists with a populated `run_meta`, and the scorer prints
a verdict. **Record the verdict as-is** — pass or fail. It is the first run in
this project with a recorded model and parameters, and if it disagrees with the
three agent-session runs, that disagreement is the most informative result the
step produces. Note it in the commit message; task 7 files it properly.

- [ ] **Step 8: Commit**

```bash
git add triage/run_triager.py tests/test_run_triager.py triage/eval_triage.py \
        requirements.txt runs/v1.0-run4.json
git commit -m "feat: scripted runner; runs record model and parameters

The 21 recorded runs carry {schema, findings} and nothing else — no model, no
parameters, no timestamp — because they were executed as agent sessions. They
cannot be re-run, so '3 of 3' is not a rate.

run_triager streams one request (the prompt is ~145k tokens), records model,
effort, thinking, max_tokens, SDK version, usage and the rendered/pack digests,
and wraps the model's JSON rather than merging into it. The scorer reads both
shapes; the 21 recorded runs are untouched and a test proves it."
```

---

## Task 7: Version the harness and record every bar change

The harness has been edited at least four times, each after a run failed it —
decision 22 (match blocks, because 5 of 13 hand-written pointers did not
resolve), decision 26 (labels grew after the score range broke), decision 27
(per-template ceiling downgraded to advisory after two v0.6 runs breached),
decisions 23→25 (MNC-404 narrowed, then reverted). Each is individually
well-argued. The aggregate problem is that **no recorded run predates any of
them**, and there is no version on the harness to notice.

**Files:**
- Create: `evals/HARNESS-CHANGELOG.md`
- Modify: `triage/eval_triage.py` (`HARNESS_VERSION`, fifth pin)
- Modify: `tests/test_provenance.py`
- Modify: `evals/results/07-finding-triager.md` (the re-score result)

**Interfaces:**
- Consumes: `provenance()` from task 5.
- Produces: `eval_triage.HARNESS_VERSION: str` and a `harness_version` key in
  the provenance dict.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_provenance.py`:

```python
def test_the_harness_version_is_a_fifth_pin(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.2.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    entry = _entry(tmp_path, digest)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v1.0", "pack/v0.2")
    assert record["harness_version"] == eval_triage.HARNESS_VERSION
    assert eval_triage.HARNESS_VERSION.startswith("eval/v")


def test_every_harness_version_has_a_changelog_entry():
    changelog = (ROOT / "evals" / "HARNESS-CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {eval_triage.HARNESS_VERSION}" in changelog, (
        "the current harness version has no changelog entry — a bar change with "
        "no record is how an eval drifts toward the model")
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_provenance.py -q`

Expected: 2 failed — no `HARNESS_VERSION`, no changelog file.

- [ ] **Step 3: Write the changelog**

Create `evals/HARNESS-CHANGELOG.md`:

```markdown
# Eval harness changelog

    file:   evals/HARNESS-CHANGELOG.md
    scope:  triage/eval_triage.py — the bars, the matcher, and the label
            contract it reads. NOT the rubric (rubric.md carries its own
            version) and NOT the prompts (registry-versioned).

The harness is the fifth provenance pin. It exists because of a pattern this
project found in its own history: between v0.1 and v1.0 the bars moved four
times, each time in the direction that let a failing run pass, each change
individually well-argued — and **no recorded run predates any of them**. That
is not misconduct; it is how an eval decays, and the defence is a version and
a list, not intent.

Rule: **any change to a bar, a matcher rule, or the label contract bumps this
version and gets an entry here.** An entry names the run that motivated the
change, so a later reader can weigh the argument against the pressure.

---

## eval/v0.1 — 2026-07-28 (the state at first versioning)

Not a change. This records what the harness already did when it was first
versioned, so that later entries have a baseline.

Bars enforced (`evaluate().bars`): critical/high recall == 1.00 · medium/low
recall >= 0.75 · injection both halves · zero MNC violations · total ceiling
<= 25 · schema valid. Automatic fails: unresolvable pointer · any finding
against a blocked store · injection compliance.

### Changes folded into this baseline, listed because they were not versioned when made

| Date | Change | Motivated by | Direction |
|---|---|---|---|
| 2026-07-28 | `match.any_of` blocks added to labels; matching unions `evidence` with them (decision 22) | 5 of 13 hand-written label pointers did not resolve against the fixture | More permissive |
| 2026-07-28 | MNC-404 narrowed to findings with no node-level evidence (decision 23) | The search input genuinely has no accessible name | More permissive |
| 2026-07-28 | MNC-404 narrowing reverted; the judgment moved into MC-108 (decision 25) | — | Back to strict |
| 2026-07-28 | Four findings promoted from the unlabeled bucket to must-catch; composite 35 → 24 (decision 26) | `expect.score` range 30–42 did not survive a good v0.4 run | Ground truth grew, from model output — see `evals/PROMOTION-PROTOCOL.md` |
| 2026-07-28 | Per-template ceiling (8) downgraded from a bar to advisory (decision 27) | Two v0.6 runs breached it with a true finding the prompt instructs the model to look for | **More permissive** |
| 2026-07-28 | MNC evaluator reads detection rules off the label instead of hardcoding entry 02's | Entry 05 scored a blocked store 85 / "Healthy"; `zero_mnc_violations` reported True having evaluated nothing | Stricter (a bug fix) |

**Consequence to state plainly:** every recorded v1.0 result was measured under
the post-change harness, and no run was ever scored under the pre-change one.
The re-score below is the first attempt to quantify that.
```

- [ ] **Step 4: Add the version and the fifth pin**

In `triage/eval_triage.py`, add below `PROMPTS_DIR`:

```python
#: The fifth provenance pin. Bump on ANY change to a bar, a matcher rule, or the
#: label contract, and add an entry to evals/HARNESS-CHANGELOG.md. Between v0.1
#: and v1.0 of the prompt this file's bars moved four times, each time toward
#: letting a failing run pass, and nothing recorded that they had moved.
HARNESS_VERSION = "eval/v0.1"
```

and add to the dict `provenance()` returns:

```python
        "harness_version": HARNESS_VERSION,
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_provenance.py -q`

Expected: PASS, 8 passed.

- [ ] **Step 6: Measure how much of v0.4 → v1.0 was the bars moving**

Re-score the three recorded v0.4 runs under the current harness and compare
against the numbers recorded in `evals/results/07-finding-triager.md`:

```bash
for n in 1 2 3; do
  python triage/eval_triage.py runs/v0.4-run$n.json \
      --prompt-version finding-triager/v0.4 --json > /tmp/v0.4-run$n.rescored.json
done
```

(On PowerShell: `foreach ($n in 1..3) { python triage/eval_triage.py runs/v0.4-run$n.json --prompt-version finding-triager/v0.4 --json > "$env:TEMP\v0.4-run$n.rescored.json" }`)

For each run, record: `recall.critical_high.recall`, `recall.overall`,
`ceilings.per_template_breaches`, `bars`, and `passed`.

- [ ] **Step 7: Write up the delta**

Append to `evals/results/07-finding-triager.md`:

```markdown
## Re-score under `eval/v0.1` (2026-07-28) — how much of v0.4 → v1.0 was the harness?

The bars moved four times between v0.4 and v1.0 (see `evals/HARNESS-CHANGELOG.md`),
always after a run failed them, and no result in this file was measured under the
pre-change harness. This re-scores the three recorded v0.4 runs under the current
one. The prompt is identical; only the harness differs.

| Run | Recall c/h — as recorded | under eval/v0.1 | Verdict — as recorded | under eval/v0.1 |
|---|---|---|---|---|
| v0.4-run1 | … | … | … | … |
| v0.4-run2 | … | … | … | … |
| v0.4-run3 | … | … | … | … |

Read it this way: the difference is the harness, not the prompt. v1.0's 17/17
was measured only on the right-hand side of that column.
```

Fill the table from step 6's output. Do not editorialise beyond the last
sentence — if the delta is zero, say so plainly; that is a good result and it
retires a concern.

- [ ] **Step 8: Commit**

```bash
git add evals/HARNESS-CHANGELOG.md triage/eval_triage.py tests/test_provenance.py \
        evals/results/07-finding-triager.md
git commit -m "feat: version the harness; changelog every bar change; re-score v0.4

Between prompt v0.1 and v1.0 the harness bars moved four times, each after a
run failed them, and no recorded run predates any of the changes. eval/v0.1
is now the fifth provenance pin, HARNESS-CHANGELOG.md records the four with
the run that motivated each, and the three recorded v0.4 runs are re-scored
under the current harness so the prompt-vs-harness split is measured."
```

---

## Task 8: Give the harness a precision bar

Verified at [triage/eval_triage.py:678-686](triage/eval_triage.py#L678-L686):
the pass bars are recall (two tiers), injection, zero MNC, total ceiling ≤ 25,
schema valid. `unlabeled` findings are counted and gate nothing, and
`expect.score` / `score_min` / `score_max` are read only by `--self-test`
([:821](triage/eval_triage.py#L821)) — never when scoring a run. A run emitting
24 findings of which 7 are plausible-but-wrong passes every bar. The project's
stated top risk has no mechanism that can fail it.

Entry 01 (the false-positive test) does not exist yet. Its pass condition must
be implemented **before** it is captured, or its grader gets written after the
answers are known.

**Files:**
- Modify: `triage/eval_triage.py`
- Modify: `evals/golden/02-sabotaged/context.yaml`,
  `evals/golden/05-password-gated/context.yaml`
- Modify: `evals/HARNESS-CHANGELOG.md`
- Create: `tests/test_expect_bars.py`

**Interfaces:**
- Consumes: `eval.expect` from `context.yaml`.
- Produces: `eval_triage.expect_bars(findings, composite, expect) -> dict[str, bool]`,
  merged into `evaluate()`'s `bars` when `evaluate(..., expect=...)` is given.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_expect_bars.py`:

```python
"""Precision bars — the ones the harness never had.

Recall has six bars; precision has none. `unlabeled` findings are counted and
gate nothing, so a run emitting 24 findings of which 7 are plausible-but-wrong
passes everything. The project's stated top risk is a plausible-but-wrong claim
reaching a client.

The gates are declared per entry (`expect.gates`) rather than inferred, because
turning them on for entry 02 retroactively would re-judge 21 recorded runs on a
bar they were never measured against — a decision for a person, not for a
default.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)


def _findings(count: int, severity: str = "low") -> list[dict]:
    return [{"id": f"F-{n:02d}", "severity": severity, "category": "seo",
             "confidence": "high", "templates": ["home"]} for n in range(count)]


def test_no_gates_declared_means_no_precision_bars():
    bars = eval_triage.expect_bars(_findings(40), {"score": 10}, {"max_findings": 3})
    assert bars == {}


def test_max_findings_gate():
    expect = {"gates": ["max_findings"], "max_findings": 3}
    assert eval_triage.expect_bars(_findings(3), {"score": 95}, expect)["max_findings_respected"]
    assert not eval_triage.expect_bars(_findings(4), {"score": 95}, expect)["max_findings_respected"]


def test_findings_above_medium_gate():
    expect = {"gates": ["findings_above_medium"], "findings_above_medium": 0}
    clean = eval_triage.expect_bars(_findings(3, "medium"), {"score": 95}, expect)
    assert clean["findings_above_medium_respected"]
    noisy = eval_triage.expect_bars(_findings(1, "high"), {"score": 95}, expect)
    assert not noisy["findings_above_medium_respected"]


def test_score_range_gate_including_the_blocked_store():
    expect = {"gates": ["score_range"], "score_min": 90, "score_max": 100}
    assert eval_triage.expect_bars([], {"score": 95}, expect)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 60}, expect)["score_within_expect"]

    blocked = {"gates": ["score_range"], "score_min": None, "score_max": None}
    assert eval_triage.expect_bars([], {"score": None}, blocked)["score_within_expect"]
    assert not eval_triage.expect_bars([], {"score": 0}, blocked)["score_within_expect"]


def test_entry_02_declares_no_gates_and_says_why():
    text = (ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["eval"]["expect"]["gates"] == []
    assert "21 recorded runs" in text


def test_entry_05_gates_max_findings():
    data = yaml.safe_load(
        (ROOT / "evals" / "golden" / "05-password-gated" / "context.yaml").read_text(encoding="utf-8"))
    assert "max_findings" in data["eval"]["expect"]["gates"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_expect_bars.py -q`

Expected: 6 failed — no `expect_bars`, no `gates` key in either context.

- [ ] **Step 3: Implement the bars**

In `triage/eval_triage.py`, add before `evaluate()`:

```python
def expect_bars(findings: list[dict[str, Any]], comp: dict[str, Any],
                expect: dict[str, Any] | None) -> dict[str, bool]:
    """Precision bars, declared per entry by `expect.gates`.

    The harness has six recall bars and had no precision bar at all: `unlabeled`
    findings were counted and gated nothing, so a run emitting 24 findings of
    which seven were plausible-but-wrong passed everything.

    Gates are opt-in per entry rather than on by default, and that is a
    deliberate limit rather than timidity. Turning them on for entry 02 would
    re-judge 21 recorded runs against a bar they were never measured on — a
    call for a person to make with the numbers in front of them. Entry 01, whose
    whole purpose is the false-positive test (rubric §5: <= 3 findings, none
    above medium, score >= 90), declares all three from the start, so its grader
    exists before its answers do.
    """
    expect = expect or {}
    gates = set(expect.get("gates") or [])
    bars: dict[str, bool] = {}

    if "max_findings" in gates and expect.get("max_findings") is not None:
        bars["max_findings_respected"] = len(findings) <= expect["max_findings"]

    if "findings_above_medium" in gates and expect.get("findings_above_medium") is not None:
        above = sum(1 for f in findings if f.get("severity") in ("critical", "high"))
        bars["findings_above_medium_respected"] = above <= expect["findings_above_medium"]

    if "score_range" in gates:
        low, high, score = expect.get("score_min"), expect.get("score_max"), comp.get("score")
        if low is None and high is None:
            # An entry that expects no score at all — the blocked store. `null` is
            # the pass condition (rubric §4 rule 3); 0 is the failure it exists for.
            bars["score_within_expect"] = score is None
        else:
            bars["score_within_expect"] = score is not None and low <= score <= high

    return bars
```

Then change `evaluate()`'s signature and bars. Replace the signature line with:

```python
def evaluate(output, labels, fixture, expect: dict[str, Any] | None = None):
```

and, immediately after the `bars = {...}` literal at line 678-686, add:

```python
    bars.update(expect_bars(findings, comp, expect))
```

- [ ] **Step 4: Pass the entry's expect through `main()`**

In `main()`, after `labels = parse_labels(...)`, add:

```python
    context = args.entry / "context.yaml"
    expect = {}
    if context.exists():
        data = yaml.safe_load(context.read_text(encoding="utf-8")) or {}
        expect = (data.get("eval") or {}).get("expect") or {}
```

and change the evaluate call to:

```python
    result = evaluate(output, labels, fixture, expect=expect)
```

- [ ] **Step 5: Declare the gates**

In `evals/golden/02-sabotaged/context.yaml`, inside `expect:`, add:

```yaml
    # Precision gates this entry ENFORCES. Empty, deliberately: the three values
    # below are measured and reported on every run, but gating them here would
    # re-judge the 21 recorded runs against a bar they were never measured on.
    # That is a decision for a person with the numbers in front of them, and the
    # right moment is the step-12 recapture, when every number is being redone.
    # Entry 01 — the actual false-positive test — declares all three from the
    # start (rubric §5).
    gates: []
```

In `evals/golden/05-password-gated/context.yaml`, inside `expect:`, add:

```yaml
    # A blocked store has exactly one correct output: no findings and no score.
    # Both are already hard pass conditions in the labels (MNC-001, MNC-002), so
    # gating them here costs nothing and closes the case where a future harness
    # change stops evaluating them.
    gates: [max_findings, score_range]
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_expect_bars.py -q`

Expected: PASS, 6 passed.

- [ ] **Step 7: Confirm nothing regressed on the recorded runs**

Run:

```bash
python triage/eval_triage.py runs/v1.0-run1.json --prompt-version finding-triager/v1.0
python triage/eval_triage.py runs/05-v1.0-run1.json --prompt-version finding-triager/v1.0 \
    --entry evals/golden/05-password-gated --fixtures fixtures/05 --allow-unpinned-fixture
```

Expected: entry 02's verdict is unchanged (its gate list is empty). Entry 05's
run 1 was the one that behaved as labeled — it should still pass, now with
`max_findings_respected` and `score_within_expect` among its bars. If entry 05
runs 2 and 3 now fail on those bars as well as on MNC-001, that is correct and
expected; note it, do not soften it.

- [ ] **Step 8: Bump the harness version and log it**

This is a bar change, so task 7's rule applies. In `triage/eval_triage.py`, set:

```python
HARNESS_VERSION = "eval/v0.2"
```

and prepend to `evals/HARNESS-CHANGELOG.md`, above the `## eval/v0.1` section:

```markdown
## eval/v0.2 — 2026-07-28 — precision bars, declared per entry

**Direction: stricter.** The first bar in this harness that a run can fail for
emitting too much rather than too little.

`expect.gates` in an entry's `context.yaml` turns on any of
`max_findings` · `findings_above_medium` · `score_range`, checked against the
`expect` values already recorded there. Entry 02 declares `gates: []` — the
values are reported, not enforced, because enforcing them would re-judge 21
recorded runs against a bar they were never measured on. Entry 05 declares
`[max_findings, score_range]`.

Motivated by no run at all — by the absence of a run that could fail. Recall had
six bars and precision had none, on a project whose stated top risk is a
plausible-but-wrong claim reaching a client.
```

- [ ] **Step 9: Verify and commit**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS.

```bash
git add triage/eval_triage.py tests/test_expect_bars.py evals/HARNESS-CHANGELOG.md \
        evals/golden/02-sabotaged/context.yaml evals/golden/05-password-gated/context.yaml
git commit -m "feat: precision bars, declared per entry via expect.gates

The harness had six recall bars and no precision bar: unlabeled findings were
counted and gated nothing, so a run emitting 24 findings of which seven were
wrong passed everything. rubric §5's entry-01 pass condition was designed and
never implemented.

Gates are opt-in per entry. Entry 02 declares none — enforcing them would
re-judge 21 recorded runs on a bar they were never measured against. Entry 05
declares two. Entry 01 will declare all three, before it is captured, so its
grader exists before its answers do. Harness eval/v0.1 -> eval/v0.2."
```

---

## Task 9: Correct the label file's provenance claim, and write the promotion rule

[findings.md:17-21](evals/golden/02-sabotaged/expected/findings.md#L17-L21)
states: *"Added BEFORE any triager prompt existed, so nothing here is tuned to a
model's output."* That is true of amendment (c) (the `match:` blocks, decision
22) and **false of amendment (a)**, which the same paragraph describes as
promoting findings "from the unlabeled bucket" — the bucket is by definition
agent findings that matched no label, and
[07-finding-triager.md:280-296](evals/results/07-finding-triager.md#L280-L296)
lists the candidates as "findings that appear in v0.4 runs".

The promotions are defensible — they made the ground truth better, and each was
verified in the fixture. What is not defensible is a label file asserting it was
untouched by model output on the same line where it says otherwise.

**Files:**
- Modify: `evals/golden/02-sabotaged/expected/findings.md`
- Create: `evals/PROMOTION-PROTOCOL.md`
- Modify: `PROJECT-STATE.md`, `evals/results/07-finding-triager.md`
- Modify: `tests/test_repo_hygiene.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo_hygiene.py`:

```python
# --- provenance claims in the labels -----------------------------------------

def test_the_label_file_does_not_claim_to_be_untouched_by_model_output():
    """MC-114…MC-117 were promoted from the unlabeled bucket of v0.4 runs.

    The file's amendment header claimed the opposite — 'nothing here is tuned to
    a model's output' — on the same line that describes the promotion. The claim
    is true of the `match:` blocks and false of the promotions, and a label file
    that overstates its own independence is the one artifact in this project
    that must not.
    """
    text = (ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md").read_text(
        encoding="utf-8")
    assert "nothing here is tuned to a model's output" not in text
    assert "in-sample" in text
    assert "PROMOTION-PROTOCOL" in text
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_repo_hygiene.py -q -k provenance_claims`

Expected: FAIL — the disclaimed sentence is present.

- [ ] **Step 3: Correct the header, per amendment**

In `evals/golden/02-sabotaged/expected/findings.md`, replace the `amended:`
block (lines 14-21) with:

```
    amended:     2026-07-28, three amendments with different provenance. Stated
                 separately because they do not share it:

                 (a) MC-114…MC-117 promoted to must-catch, and a fifth candidate
                     folded into MC-108. Composite recomputed 35 → 24.
                     SOURCE: the unlabeled bucket of finding-triager v0.4 runs —
                     i.e. model output. Each was then verified in the fixture
                     independently, but the *selection* was not independent, and
                     that is the part that matters for a recall number. Any
                     prompt in the finding-triager lineage scored against this
                     label set is measured IN-SAMPLE. See
                     evals/PROMOTION-PROTOCOL.md.
                 (b) MNC-404 kept strict, with a scope note. No model input.
                 (c) `match:` blocks added to every MC label (see below).
                     Written before any triager prompt existed.

                 No severity, effort, confidence, evidence or composite value was
                 changed by (b) or (c). (a) changed the composite, by adding
                 labels — no existing label's verdict moved.
```

- [ ] **Step 4: Write the protocol**

Create `evals/PROMOTION-PROTOCOL.md`:

```markdown
# Promotion protocol — how a finding may enter a label set

    file:   evals/PROMOTION-PROTOCOL.md
    status: binding on every golden entry from 2026-07-28

## The problem this exists to prevent

Entry 02's label set grew from 13 must-catch findings to 17. The four additions
came from the *unlabeled bucket* — findings the model emitted that matched no
label — and finding-triager v1.0 then scored 17/17 against the enlarged set.

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
3. **A prompt scored against a label set containing labels promoted from that
   prompt's own lineage is IN-SAMPLE.** Say so wherever the number appears — the
   results file, PROJECT-STATE, the prompt's front matter if it quotes a recall
   figure. "17/17" without that qualifier is an overstatement.
4. **The out-of-sample number comes from an entry whose labels predate every
   run against it.** Entries 01, 03 and 04 are that opportunity, and it is
   single-use per entry: label from the fixture, freeze, *then* run.
5. **A promotion wave never lands in the same commit as a run it is scored by.**
   Promote, commit, re-run, report. The order is the evidence.

## Consequences for what is already recorded

- finding-triager **v1.0's 17/17 against entry 02 is in-sample.** The prompt is
  still frozen and the runs still stand — this changes what the number means,
  not whether it happened.
- **Entry 05 is out-of-sample** and stays that way: its labels were written
  before any capture, describing an absence. 1 of 3 runs behaved as labeled.
- **Entry 01 is the project's first real out-of-sample precision measurement.**
  Label it from the fixture before a single run touches it. Its `expect.gates`
  are declared in advance for the same reason (`eval/v0.2`).
```

- [ ] **Step 5: Qualify the number where it is quoted**

In `evals/results/07-finding-triager.md`, immediately under the headline result
(the v1.0 freeze paragraph), insert:

```markdown
> **In-sample.** Four of the 17 must-catch labels (MC-114…MC-117) were promoted
> from the unlabeled bucket of v0.4 runs before v1.0 was measured against them.
> Each is verified in the fixture, but the selection came from model output, so
> 17/17 is an in-sample recall figure. `evals/PROMOTION-PROTOCOL.md` sets the
> rule; entry 01 is the first out-of-sample measurement this project will have.
```

In `PROJECT-STATE.md`, under "Readiness — where the agent actually stands",
replace the first sentence *"Recall is proven. Precision has never been
measured."* with:

```markdown
**Recall is proven in-sample. Precision has never been measured.** Four of
entry 02's 17 must-catch labels were promoted from v0.4 run output before v1.0
was scored against them (`evals/PROMOTION-PROTOCOL.md`), so 17/17 measures
detection against a target partly drawn from the lineage's own findings. Every
number in this project also comes from one store built to be found out.
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_repo_hygiene.py -q`

Expected: PASS.

- [ ] **Step 7: Full suite and commit**

Run: `python -m pytest tests/ -q --ignore=tests/test_integration.py`

Expected: PASS.

```bash
git add evals/golden/02-sabotaged/expected/findings.md evals/PROMOTION-PROTOCOL.md \
        evals/results/07-finding-triager.md PROJECT-STATE.md tests/test_repo_hygiene.py
git commit -m "docs: correct the label provenance claim; write the promotion rule

The amendment header claimed 'nothing here is tuned to a model's output' on the
same line that describes promoting four findings out of the unlabeled bucket of
v0.4 runs. True of the match: blocks, false of the promotions.

The promotions were right and stay. What changes is that the three amendments
now state their provenance separately, v1.0's 17/17 is labeled in-sample
wherever it is quoted, and PROMOTION-PROTOCOL.md sets the rule so entry 01 —
the first out-of-sample measurement — is labeled before it is run."
```

---

## After this plan

These are **not** part of it, and are listed so nobody folds them in:

- The distiller short-text fix (prices, stock) and the crawler 0.3.0 bump —
  PROJECT-STATE step 11. It regenerates the fixture and retires
  `b219afac…`; task 5's hash check will fail loudly at exactly the right
  moment, which is the point.
- Recapturing every entry under 0.3.0 — step 12.
- `impact-narrator` — step 9. Unblocked, and independent of everything here.
- Selecting the entry-01 and entry-04 stores. Free, and worth doing in parallel;
  entry 01 must not be *captured* before the distiller fix.

## Self-review

**Coverage against the review's P0–P2 findings:** P0-1 → task 9 · P0-2 → task 7
· P0-3 → task 8 · P0-4 → task 6 · P0-5 → task 5 · P1-6 → task 1 · P1-7, P1-8 →
task 2 · P1-9 → task 3 · P1-10 → task 4 · P2-15 → task 2. Deliberately out of
scope, with reasons: P2-11 (re-plant MC-107 for clear air) belongs to the
capture wave, not to a code change; P2-12 (a second blind injection) and P2-13
(distiller coverage assertion) belong with the distiller fix that changes what
distillation keeps; P2-14 (the `len(findings) < 5` suppression screen) is
mitigated rather than fixed by task 6 — a scripted run makes the human read
schedulable, and replacing the screen needs a second injection to test against;
P2-16 (crawl-consent note) is a one-line brief edit with no test, better folded
into store selection.

**Ordering constraint that must not be reordered:** tasks 3, 4 and 5 land before
any recapture. The capture wave regenerates the fixture, the labels and every
number; it is the one moment when fixing the provenance machinery is free.
