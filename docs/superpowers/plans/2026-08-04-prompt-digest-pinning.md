# Prompt Digest Pinning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the prompt-version provenance pin to the prompt file's bytes, so an in-place edit to a frozen prompt is detected and refuses to score — closing the last of the five pins that could drift silently.

**Architecture:** `resolve_prompt_version` returns `name+sha8` (the `rubric_version()` pattern) and verifies front matter agrees with the filename. `eval_triage.provenance()` re-renders the template with the pack and requires the hash to equal the run's recorded `rendered_sha256` → `prompt_pin: "matched"`, or exits. `eval_narrative` gets the identical treatment through `{{BRIEF}}`. Old runs without `run_meta` and evals without `--pack` degrade to `"exists"`.

**Tech Stack:** Python 3, pytest, no new dependencies. Spec: `docs/superpowers/specs/2026-08-04-prompt-digest-pinning-design.md`.

## Global Constraints

- Run all tools as `python -m ...` (global pip is broken on this machine; pytest is `python -m pytest`).
- The four-word pin vocabulary is unchanged: `matched` / `self-derived` / `asserted` / `exists` (+ `absent`). No new status words.
- No machine-readable registry/sidecar of prompt digests — the pin is computed from the file, never stored beside it.
- Every `SystemExit` message follows the project style: what was compared, both values, then what the operator should do.
- The suite must be green at every commit. Full suite takes ~7–16 min; run the targeted test files per task and the full suite once in Task 4.
- `tests/test_provenance.py` loads `eval_triage` via `importlib` (see its lines 21–24); executing it puts the repo root on `sys.path`, so `from triage import render_prompt` works *after* that block.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

**Verified facts the implementer should not re-derive:**
- All 11 live prompt files (`prompts/finding-triager/v0.1–v1.3.md`, `prompts/impact-narrator/v0.1.md`) have front matter whose `prompt:`/`version:` agree with their path — the front-matter check will not break any live prompt.
- `run_narrator.py:68` reuses `model_runner.run_meta` (renames `pack_sha256`→`brief_sha256`), so narrator runs DO carry `rendered_sha256`.
- `rendered_sha256` is a hash of **file bytes**; `render_prompt.main` writes with `write_text(text, encoding="utf-8")`, which translates `\n` to `\r\n` on Windows. Hence every recompute must accept both LF and CRLF spellings.
- `render_prompt.render(template, data_path, indent, placeholder)` returns `(text, version)` and is deterministic; default `indent=None` uses compact separators.

---

### Task 1: `resolve_prompt_version` returns name+digest; narrator comparison made suffix-tolerant

**Files:**
- Modify: `triage/eval_triage.py:144-153` (`resolve_prompt_version`), plus one import near line 40
- Modify: `triage/eval_narrative.py:320-321` (prompt-version comparison)
- Test: `tests/test_provenance.py`

**Interfaces:**
- Produces: `resolve_prompt_version(name, prompts_dir=PROMPTS_DIR) -> str` returning `"{name}+{sha256[:8]}"`, raising `SystemExit` on: empty/`"unpinned"` name, missing file, or front matter disagreeing with `name`. Later tasks split the bare name back out with `.split("+", 1)[0]`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_provenance.py` (after the existing `test_an_unknown_prompt_version_is_fatal`). Also add the import and helper the later tasks share, directly under the `importlib` block at the top of the file:

```python
from triage import render_prompt  # noqa: E402  (eval_triage's exec put ROOT on sys.path)
```

```python
def _prompt_dir(tmp_path: Path, name: str = "finding-triager/v9.0",
                body: str = "Triage this store.\n\n{{PACK}}\n") -> Path:
    """A prompts/ tree holding one template whose front matter matches `name`."""
    prompts = tmp_path / "prompts"
    family, version = name.split("/")
    path = prompts / family / f"{version}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nprompt: {family}\nversion: {version}\n---\n{body}",
                    encoding="utf-8")
    return prompts


def test_the_prompt_pin_carries_a_digest_of_the_file_bytes(tmp_path):
    prompts = _prompt_dir(tmp_path)
    resolved = eval_triage.resolve_prompt_version("finding-triager/v9.0", prompts)
    name, _, digest = resolved.partition("+")
    assert name == "finding-triager/v9.0"
    assert len(digest) == 8 and int(digest, 16) >= 0


def test_editing_a_prompt_in_place_moves_its_pin(tmp_path):
    """The 'just fix a typo' edit the handoff warns about, made visible."""
    prompts = _prompt_dir(tmp_path)
    before = eval_triage.resolve_prompt_version("finding-triager/v9.0", prompts)
    path = prompts / "finding-triager" / "v9.0.md"
    path.write_text(path.read_text(encoding="utf-8") + "\ntypo fix\n", encoding="utf-8")
    after = eval_triage.resolve_prompt_version("finding-triager/v9.0", prompts)
    assert before != after
    assert before.split("+")[0] == after.split("+")[0]


def test_a_file_whose_front_matter_disagrees_with_its_name_is_fatal(tmp_path):
    """v1.2.md copied to v1.3.md without editing the header must not resolve."""
    prompts = _prompt_dir(tmp_path)
    copy = prompts / "finding-triager" / "v9.1.md"
    copy.write_text((prompts / "finding-triager" / "v9.0.md").read_text(encoding="utf-8"),
                    encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        eval_triage.resolve_prompt_version("finding-triager/v9.1", prompts)
    assert "front matter" in str(caught.value)


def test_every_live_prompt_resolves_and_self_identifies():
    templates = sorted((ROOT / "prompts").glob("*/v*.md"))
    assert templates, "no live prompts found — glob is wrong"
    for path in templates:
        name = f"{path.parent.name}/{path.stem}"
        resolved = eval_triage.resolve_prompt_version(name, ROOT / "prompts")
        assert resolved.startswith(name + "+")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/test_provenance.py -v -k "digest or moves_its_pin or front_matter or self_identifies"`
Expected: FAIL — resolved value has no `+` suffix (assertions on `partition`/`startswith`), and the front-matter test gets no `SystemExit`.

- [ ] **Step 3: Implement.** In `triage/eval_triage.py`, add the import next to `from triage import mnc` (line 40):

```python
from triage import render_prompt  # noqa: E402
```

Replace `resolve_prompt_version` (lines 144–153) with:

```python
def resolve_prompt_version(name: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    """Resolve a prompt version to `name+sha8` of the file's bytes.

    Existence is the floor. The digest binds the pin to the bytes — the rubric
    pattern — so editing a frozen prompt in place moves every pin recorded
    after it. The front-matter check catches a file copied to a new version
    name whose header still declares the old one.
    """
    if not name or name == "unpinned":
        raise SystemExit(
            "--prompt-version is required: a run scored without a prompt pin is not "
            "a result (decision 12)")
    path = prompts_dir / f"{name}.md"
    if not path.exists():
        raise SystemExit(f"--prompt-version {name!r} names no prompt file ({path})")
    declared = render_prompt.prompt_version(path.read_text(encoding="utf-8"))
    if declared != name:
        raise SystemExit(
            f"--prompt-version {name!r} names a file whose front matter declares "
            f"{declared!r} ({path}).\n"
            "The filename and the front matter must agree before either can be a "
            "pin — fix whichever one is wrong.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    return f"{name}+{digest}"
```

In `triage/eval_narrative.py`, the comparison at line 321 breaks the moment resolve gains the suffix (`run_meta.prompt_version` records the bare name). Change:

```python
    recorded_prompt_version = run_meta.get("prompt_version")
    if recorded_prompt_version and recorded_prompt_version != resolved_prompt:
```

to:

```python
    recorded_prompt_version = run_meta.get("prompt_version")
    if recorded_prompt_version and recorded_prompt_version != resolved_prompt.split("+", 1)[0]:
```

- [ ] **Step 4: Run both test files to verify everything passes** (the narrator tests at `tests/test_eval_narrative.py:292-339` are the regression guard for the split fix)

Run: `python -m pytest tests/test_provenance.py tests/test_eval_narrative.py -v`
Expected: PASS, no failures. If `test_the_live_prompts_and_the_live_rubric_resolve` fails, the front-matter check regressed — do not weaken the test.

- [ ] **Step 5: Commit**

```bash
git add triage/eval_triage.py triage/eval_narrative.py tests/test_provenance.py
git commit -m "feat(evals): the prompt pin carries a digest of the file's bytes"
```

---

### Task 2: the `matched` check — `eval_triage.provenance()` re-renders and compares

**Files:**
- Modify: `triage/eval_triage.py` — new module function `_rendered_digests`; `provenance()` (lines 193–261); `main()` (argparse near line 1044, call site lines 1074–1079)
- Test: `tests/test_provenance.py` (new tests; rewrite `test_the_prompt_pin_says_existence_and_not_more` at line 229)

**Interfaces:**
- Consumes: `resolve_prompt_version(name, prompts_dir)` from Task 1.
- Produces:
  - `_rendered_digests(template: Path, data_path: Path, placeholder: str, indent: int | None = None) -> set[str]` — the sha256 hex digests of the LF and CRLF spellings of one render. Task 3 calls it with `placeholder="BRIEF"`.
  - `provenance(entry, fixtures, prompt_version, pack_version, *, allow_unpinned=False, pack_path=None, run_meta=None, render_indent=None, prompts_dir=PROMPTS_DIR) -> dict` — the dict's `prompt_version` now carries `+sha8` and `prompt_pin` is `"matched"` or `"exists"`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_provenance.py` (uses `_prompt_dir` from Task 1):

```python
def _pack_file(tmp_path: Path) -> Path:
    pack = tmp_path / "pack.json"
    pack.write_text('{"pack": "pack/v0.2", "evidence": []}', encoding="utf-8")
    return pack


def _run_meta_for(prompts: Path, name: str, pack: Path, *, crlf: bool = False) -> dict:
    """What run_triager would have recorded for this template + pack."""
    family, version = name.split("/")
    text, _ = render_prompt.render(prompts / family / f"{version}.md", pack, None, "PACK")
    if crlf:
        text = text.replace("\n", "\r\n")
    return {
        "prompt_version": name,
        "rendered_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "pack_sha256": hashlib.sha256(pack.read_bytes()).hexdigest(),
    }


def _pinned_entry_and_fixtures(tmp_path):
    fixtures = _fixtures(tmp_path, "crawler_version: 0.3.0\n")
    digest = hashlib.sha256((fixtures / "manifest.yaml").read_bytes()).hexdigest()
    return _entry(tmp_path, digest), fixtures


def test_a_faithful_re_render_pins_the_prompt_as_matched(tmp_path):
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    prompts = _prompt_dir(tmp_path)
    pack = _pack_file(tmp_path)
    meta = _run_meta_for(prompts, "finding-triager/v9.0", pack)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v9.0",
                                    "pack/v0.2", pack_path=pack, run_meta=meta,
                                    prompts_dir=prompts)
    assert record["prompt_pin"] == "matched"
    assert record["prompt_version"].startswith("finding-triager/v9.0+")


def test_a_typo_fix_after_the_run_refuses_to_score(tmp_path):
    """The b219afac shape of failure, prompt edition — reproduced directly."""
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    prompts = _prompt_dir(tmp_path)
    pack = _pack_file(tmp_path)
    meta = _run_meta_for(prompts, "finding-triager/v9.0", pack)
    path = prompts / "finding-triager" / "v9.0.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Triage", "Assess"),
                    encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v9.0", "pack/v0.2",
                               pack_path=pack, run_meta=meta, prompts_dir=prompts)
    assert "does not reproduce" in str(caught.value)


def test_a_crlf_rendered_run_still_matches(tmp_path):
    """rendered_sha256 hashes file bytes, and write_text picks the platform
    newline — both spellings of one render are the same prompt."""
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    prompts = _prompt_dir(tmp_path)
    pack = _pack_file(tmp_path)
    meta = _run_meta_for(prompts, "finding-triager/v9.0", pack, crlf=True)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v9.0",
                                    "pack/v0.2", pack_path=pack, run_meta=meta,
                                    prompts_dir=prompts)
    assert record["prompt_pin"] == "matched"


def test_the_wrong_pack_is_named_as_the_wrong_pack(tmp_path):
    """When the pack on disk isn't the one the run saw, the message must blame
    the pack, not the prompt."""
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    prompts = _prompt_dir(tmp_path)
    pack = _pack_file(tmp_path)
    meta = _run_meta_for(prompts, "finding-triager/v9.0", pack)
    pack.write_text('{"pack": "pack/v0.2", "evidence": ["changed"]}', encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v9.0", "pack/v0.2",
                               pack_path=pack, run_meta=meta, prompts_dir=prompts)
    assert "pack" in str(caught.value)
    assert "run_meta.pack_sha256" in str(caught.value)


def test_asserting_the_wrong_version_against_a_run_record_is_fatal(tmp_path):
    """eval_narrative already refuses this; eval_triage never compared at all."""
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    meta = {"prompt_version": "finding-triager/v1.0"}
    with pytest.raises(SystemExit) as caught:
        eval_triage.provenance(entry, fixtures, "finding-triager/v1.1", "pack/v0.2",
                               run_meta=meta)
    assert "does not match the run's record" in str(caught.value)
```

Replace `test_the_prompt_pin_says_existence_and_not_more` (line 229, whole test including docstring) with:

```python
def test_exists_is_the_honest_ceiling_without_run_meta_or_pack(tmp_path):
    """`matched` needs both the run's rendered_sha256 and the pack to re-render
    with. An old bare-JSON run, or an eval without --pack, can claim existence
    and nothing more — saying `matched` there would be the overstatement this
    key exists to stop.
    """
    entry, fixtures = _pinned_entry_and_fixtures(tmp_path)
    prompts = _prompt_dir(tmp_path)
    pack = _pack_file(tmp_path)
    # old run: no run_meta at all, pack present
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v9.0",
                                    "pack/v0.2", pack_path=pack, run_meta=None,
                                    prompts_dir=prompts)
    assert record["prompt_pin"] == "exists"
    # new run, but no pack on disk to re-render with
    meta = _run_meta_for(prompts, "finding-triager/v9.0", pack)
    record = eval_triage.provenance(entry, fixtures, "finding-triager/v9.0",
                                    "pack/v0.2", run_meta=meta, prompts_dir=prompts)
    assert record["prompt_pin"] == "exists"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/test_provenance.py -v -k "matched or typo_fix or crlf or wrong_pack or wrong_version or honest_ceiling"`
Expected: FAIL with `TypeError: provenance() got an unexpected keyword argument 'run_meta'` (and `prompts_dir`).

- [ ] **Step 3: Implement.** In `triage/eval_triage.py`, add below `resolve_prompt_version`:

```python
def _rendered_digests(template: Path, data_path: Path, placeholder: str,
                      indent: int | None = None) -> set[str]:
    """Every byte-hash one render could legitimately carry.

    `rendered_sha256` was taken over file bytes, and `write_text` picks the
    platform's newline — so the LF and CRLF spellings of one render are the
    same prompt.
    """
    text, _ = render_prompt.render(template, data_path, indent, placeholder)
    return {hashlib.sha256(variant.encode("utf-8")).hexdigest()
            for variant in (text, text.replace("\n", "\r\n"))}
```

Change `provenance()`'s signature (line 193) to:

```python
def provenance(entry: Path, fixtures: Path, prompt_version: str, pack_version: str,
               *, allow_unpinned: bool = False, pack_path: Path | None = None,
               run_meta: dict[str, Any] | None = None,
               render_indent: int | None = None,
               prompts_dir: Path = PROMPTS_DIR) -> dict[str, Any]:
```

Insert after the `fixture_pin` block (line 249) and before the `return`:

```python
    resolved_prompt = resolve_prompt_version(prompt_version, prompts_dir)
    prompt_name = resolved_prompt.split("+", 1)[0]
    meta = run_meta or {}

    recorded_name = meta.get("prompt_version")
    if recorded_name and recorded_name != prompt_name:
        raise SystemExit(
            f"--prompt-version does not match the run's record.\n"
            f"  --prompt-version: {prompt_name}\n"
            f"  run_meta.prompt_version: {recorded_name}\n"
            "The run was not produced by the prompt version being asserted here.")

    # The strong check: the template on disk, rendered with the pack on disk,
    # must hash to what the model actually saw. Needs both halves — old
    # bare-JSON runs and pack-less evals stay scoreable at "exists".
    prompt_pin = "exists"
    recorded_rendered = meta.get("rendered_sha256")
    if recorded_rendered and pack_path is not None:
        recorded_pack = meta.get("pack_sha256")
        computed_pack = hashlib.sha256(Path(pack_path).read_bytes()).hexdigest()
        if recorded_pack and recorded_pack != computed_pack:
            raise SystemExit(
                f"pack bytes do not match the run's pin.\n"
                f"  run_meta.pack_sha256: {recorded_pack}\n"
                f"  {pack_path}: {computed_pack}\n"
                "The pack on disk is not the pack this run saw, so the prompt "
                "cannot be verified against it. Point --pack at the pack the "
                "run was rendered from.")
        template = prompts_dir / f"{prompt_name}.md"
        if recorded_rendered in _rendered_digests(template, pack_path, "PACK",
                                                  render_indent):
            prompt_pin = "matched"
        else:
            raise SystemExit(
                f"the prompt on disk does not reproduce what this run saw.\n"
                f"  run_meta.rendered_sha256: {recorded_rendered}\n"
                f"  re-render of {template}: no match\n"
                "The template was edited in place after the run, or the rendered "
                "file was edited before it. If the run was rendered with a "
                "non-default --indent, pass the same value as --render-indent.")
```

And change the two prompt lines of the returned dict (lines 254–255) to:

```python
        "prompt_version": resolved_prompt,
        "prompt_pin": prompt_pin,
```

In `main()`: add the flag next to `--pack` (line 1044):

```python
    parser.add_argument("--render-indent", type=int, default=None,
                        help="the --indent the run's prompt was rendered with, if any "
                             "(needed to re-derive rendered_sha256 for the prompt pin)")
```

and thread both through the call site (lines 1075–1078):

```python
        "provenance": provenance(args.entry, args.fixtures, args.prompt_version,
                                 args.pack_version,
                                 allow_unpinned=args.allow_unpinned_fixture,
                                 pack_path=args.pack, run_meta=run_meta,
                                 render_indent=args.render_indent)
```

(`run_meta` is already in scope from `load_run_output` at line 1071; the record's `| {"run_file": ..., "run_meta": run_meta}` merge stays as is.)

- [ ] **Step 4: Run the file, then the CLI smoke checks**

Run: `python -m pytest tests/test_provenance.py -v`
Expected: PASS, including all pre-existing tests (they call `provenance` without the new kwargs and hit live prompts through the defaults).

Run: `python -m triage.eval_triage --self-test`
Expected: exits 0 with the usual `24 (Critical)` self-test output — proves `main()` still parses and the new flag doesn't disturb `--self-test`.

- [ ] **Step 5: Commit**

```bash
git add triage/eval_triage.py tests/test_provenance.py
git commit -m "feat(evals): prompt_pin says matched only when a re-render reproduces the run"
```

---

### Task 3: the narrator gets the same `matched` check through `{{BRIEF}}`

**Files:**
- Modify: `triage/eval_narrative.py` — `provenance()` (lines 299–335) and `main()` (argparse near line 346, call site line 356)
- Test: `tests/test_eval_narrative.py` (new tests near the existing I1 block, lines 276–339)

**Interfaces:**
- Consumes: `eval_triage.resolve_prompt_version(name, prompts_dir)` and `eval_triage._rendered_digests(template, data_path, placeholder, indent)` from Tasks 1–2.
- Produces: `eval_narrative.provenance(run, brief_path, prompt_version, *, render_indent=None, prompts_dir=eval_triage.PROMPTS_DIR) -> dict` whose record gains `"prompt_pin"` (`"matched"` / `"exists"`).

- [ ] **Step 1: Write the failing tests.** Add to `tests/test_eval_narrative.py` after `test_a_prompt_version_mismatch_between_cli_and_run_meta_is_fatal` (line 339), following that block's local-import style:

```python
def _narrator_prompts(tmp_path):
    prompts = tmp_path / "prompts"
    path = prompts / "impact-narrator" / "v9.0.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nprompt: impact-narrator\nversion: v9.0\n---\n"
                    "Narrate this.\n\n{{BRIEF}}\n", encoding="utf-8")
    return prompts


def _narrator_run_meta(prompts, brief_path):
    import hashlib
    from triage import render_prompt
    text, _ = render_prompt.render(prompts / "impact-narrator" / "v9.0.md",
                                   brief_path, None, "BRIEF")
    return {
        "prompt_version": "impact-narrator/v9.0",
        "rendered_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "brief_sha256": hashlib.sha256(brief_path.read_bytes()).hexdigest(),
    }


def test_a_faithful_re_render_pins_the_narrator_prompt_as_matched(tmp_path):
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    prompts = _narrator_prompts(tmp_path)
    run = {"run_meta": _narrator_run_meta(prompts, brief_path)}
    record = eval_narrative.provenance(run, brief_path, "impact-narrator/v9.0",
                                       prompts_dir=prompts)
    assert record["prompt_pin"] == "matched"
    assert record["prompt_version"].startswith("impact-narrator/v9.0+")


def test_a_narrator_prompt_edited_after_the_run_refuses_to_score(tmp_path):
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    prompts = _narrator_prompts(tmp_path)
    run = {"run_meta": _narrator_run_meta(prompts, brief_path)}
    path = prompts / "impact-narrator" / "v9.0.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Narrate", "Describe"),
                    encoding="utf-8")
    try:
        eval_narrative.provenance(run, brief_path, "impact-narrator/v9.0",
                                  prompts_dir=prompts)
    except SystemExit as e:
        assert "does not reproduce" in str(e)
    else:
        raise AssertionError("expected SystemExit for an edited narrator prompt")


def test_a_run_without_rendered_sha256_reads_exists(tmp_path):
    """Pre-run_narrator records have nothing to re-render against; they stay
    scoreable, honestly labelled."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    record = eval_narrative.provenance({}, brief_path, "impact-narrator/v0.1")
    assert record["prompt_pin"] == "exists"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/test_eval_narrative.py -v -k "narrator_prompt or rendered_sha256_reads_exists"`
Expected: FAIL — `provenance() got an unexpected keyword argument 'prompts_dir'`, and no `prompt_pin` key.

- [ ] **Step 3: Implement.** In `triage/eval_narrative.py`, change `provenance()` (line 299) to:

```python
def provenance(run: dict[str, Any], brief_path: Path, prompt_version: str, *,
               render_indent: int | None = None,
               prompts_dir: Path = eval_triage.PROMPTS_DIR) -> dict[str, Any]:
    """Verify the run's pins and return them.

    Recomputes the brief's hash from the file passed on the command line,
    checks the prompt version against what the run recorded, and — when the
    run carries rendered_sha256 — requires the template on disk to re-render
    to exactly what the model saw. Exits on any mismatch.
    """
    resolved_prompt = eval_triage.resolve_prompt_version(prompt_version, prompts_dir)
    prompt_name = resolved_prompt.split("+", 1)[0]
```

Keep the brief-hash block (lines 307–318) unchanged. Update the version comparison (Task 1 left it as `resolved_prompt.split("+", 1)[0]`) to use the local name:

```python
    recorded_prompt_version = run_meta.get("prompt_version")
    if recorded_prompt_version and recorded_prompt_version != prompt_name:
```

Then insert before the `return`:

```python
    # The strong check. The brief was already verified against the run's own
    # brief_sha256 above, so a mismatch here can only be the template.
    prompt_pin = "exists"
    recorded_rendered = run_meta.get("rendered_sha256")
    if recorded_rendered:
        template = prompts_dir / f"{prompt_name}.md"
        if recorded_rendered in eval_triage._rendered_digests(
                template, brief_path, "BRIEF", render_indent):
            prompt_pin = "matched"
        else:
            raise SystemExit(
                f"the prompt on disk does not reproduce what this run saw.\n"
                f"  run_meta.rendered_sha256: {recorded_rendered}\n"
                f"  re-render of {template}: no match\n"
                "The template was edited in place after the run, or the rendered "
                "file was edited before it. If the run was rendered with a "
                "non-default --indent, pass the same value as --render-indent.")
```

And add `"prompt_pin": prompt_pin,` to the returned dict, directly under `"prompt_version": resolved_prompt,`.

In `main()`: add after the `--prompt-version` argument (line 346):

```python
    parser.add_argument("--render-indent", type=int, default=None,
                        help="the --indent the run's prompt was rendered with, if any "
                             "(needed to re-derive rendered_sha256 for the prompt pin)")
```

and change the call at line 356 to:

```python
    result["provenance"] = provenance(run, args.brief, args.prompt_version,
                                      render_indent=args.render_indent)
```

- [ ] **Step 4: Run the whole narrator test file**

Run: `python -m pytest tests/test_eval_narrative.py -v`
Expected: PASS — including the pre-existing I1 tests, whose runs carry no `rendered_sha256` and therefore land on `exists`.

- [ ] **Step 5: Commit**

```bash
git add triage/eval_narrative.py tests/test_eval_narrative.py
git commit -m "feat(evals): the narrator's prompt pin gets the same re-render check"
```

---

### Task 4: full suite, then record the decision

**Files:**
- Modify: `PROJECT-STATE.md` (append decision 43 after decision 42, which ends at line 618)
- Modify: `docs/HANDOFF-2026-07-31.md` (§8 open-item bullet, lines 306–313)

**Interfaces:**
- Consumes: everything above, landed and green.

- [ ] **Step 1: Run the full suite** (budget ~7–16 min; do not interrupt)

Run: `python -m pytest`
Expected: everything passes except the 1 standing skip — the count should be 643 pre-existing plus the new tests from Tasks 1–3, 0 failures. If anything unrelated fails, stop and investigate before touching docs; do not record a decision over a red suite (§6 of the handoff is the cautionary tale).

- [ ] **Step 2: Append decision 43 to `PROJECT-STATE.md`** (same numbered format as decisions 41–42, two-space indent for the body):

```markdown
43. **The prompt pin is bound to its bytes** (2026-08-04). Closes the one §8
    item that was "the b219afac shape of failure with a different noun".
    `resolve_prompt_version` now returns `name+sha8` of the template's bytes
    (the `rubric_version` pattern) and refuses a file whose front matter
    disagrees with its filename. Stronger, when the evidence allows it:
    `eval_triage.provenance` re-renders the template with the pack and
    requires the result to hash to the run's `rendered_sha256` (LF or CRLF —
    the hash is over file bytes and the newline is the platform's), recording
    `prompt_pin: matched` — or refusing to score, with `pack_sha256`
    disambiguating whether the pack or the template moved. `eval_narrative`
    does the same through `{{BRIEF}}`. Old bare-JSON runs and pack-less evals
    degrade to `exists`, not to silence; the pin vocabulary is unchanged.
    `--render-indent` on both eval CLIs is the escape hatch for a run rendered
    with a non-default `--indent`. Design:
    `docs/superpowers/specs/2026-08-04-prompt-digest-pinning-design.md`.
```

- [ ] **Step 3: Annotate the handoff's §8 bullet** (the same strikethrough-plus-RESOLVED convention decision 41's bullet got). Replace the bullet at `docs/HANDOFF-2026-07-31.md:306-313` ("**Prompt versions are pinned by name, with no digest.** ...") with:

```markdown
- ~~**Prompt versions are pinned by name, with no digest.**~~ — **RESOLVED**
  (decision 43). `resolve_prompt_version` binds the pin to the bytes, and
  `eval_triage` re-renders the template against the run's `rendered_sha256`,
  so a frozen prompt edited in place now refuses to score instead of silently
  changing what every run recorded against it was measured with.
```

- [ ] **Step 4: Commit**

```bash
git add PROJECT-STATE.md docs/HANDOFF-2026-07-31.md
git commit -m "docs: decision 43 — the prompt pin is bound to its bytes"
```

---

## Self-review notes (already applied)

- **Spec coverage:** spec §1 → Task 1; §2 → Task 2; §3 (name cross-check) → Task 2's `recorded_name` block and its test; §4 → Tasks 1 (split fix) and 3; Testing section → every named case has a concrete test above (digest moves, matched, typo-fix refusal, old-run degrade, no-pack degrade, CRLF, front matter, narrator suffix tolerance + matched, live prompts); Out-of-scope §→ Task 4 docs only, no `run_meta` changes anywhere.
- **Ordering constraint:** the `eval_narrative.py` one-line split fix MUST land in Task 1's commit — resolve's `+sha8` suffix breaks three existing narrator tests otherwise, and the suite must be green at every commit.
- **Type consistency:** `_rendered_digests(template, data_path, placeholder, indent)` is defined in Task 2 and consumed with the same argument order in Task 3; `provenance` kwargs are keyword-only in both modules.
