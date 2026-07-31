# Freeze checklist — capturing a golden fixture

    created:  2026-07-30. `PROJECT-STATE.md` had called the freshness gate "on the
              freeze checklist and not optional" since 2026-07-27, but no such
              checklist existed — the gate lived only as prose. This is its home.
    scope:    one golden entry, from pre-capture screen to a fixture the labels
              can be written against. Sits beside `PROMOTION-PROTOCOL.md` (what a
              result is worth) and `HARNESS-CHANGELOG.md` (when a bar moved).
    read with: `specs/crawler.md` §3 and §10 · `PROJECT-STATE.md` "Gotchas and
              traps" · `evals/golden/02-sabotaged/sabotage-spec.md` "Capture
              procedure" (which this expands, and does not replace).

**Why a checklist and not judgment.** Every item below exists because skipping it
has already cost this project a wrong number, a retracted figure, or a fixture that
had to be thrown away. Three of them were discovered *by* a bad capture. None is
here on principle.

**What is automated and what is not.** Only two steps enforce themselves — the
password scan (fatal, destructive) and the fixture-hash pin (fatal at eval time).
Everything else is a manual check that will pass silently if you do not perform it.
The freshness gate in particular **has no implementation**; `planting/inspect_lcp.py`
can show you the stamp, but nothing gates on it.

---

## A — Before the capture

### A1. Re-run the candidate screen, if the store is not ours ▢

Design D5: entries 01 and 04 are stores we do not own, so the criteria that
selected them must be re-verified immediately before capture. A failing hard gate
is a **re-selection trigger**, not a warning.

```bash
python -m planting.screen_candidate --entry 01        # or 04
```

Exit codes: `0` every hard gate passed and was evaluated · `2` a hard gate failed
(re-selection trigger) · `3` incomplete — no gate failed but lcp/cls were never
evaluated (`--skip-perf`), so `0` would misreport what ran · `1` operational
failure.

- **A gate count is a property of the screen, not the store, and dates with the
  code.** Entry 01 has read 9, 15 and 16 hard gates across three commits. Do not
  compare today's count to a figure recorded earlier; compare the verdicts.
- **Entry 04 has not been screened since the `platform` gate and the exit-3
  change.** Expect 10 head gates and exit 3.
- Confirm the report's `resolver:` note is present — see A3.

### A2. Confirm the store state the entry depends on ▢

Reading the live store, not local files. When live behaviour contradicts local
files, **read the live state; do not theorize.**

- **Pinned targets still resolve.** Entry 02 pins `pdp`; entry 04 pins `cart` at
  `/basket/`. A pinned URL that 404s is how the entry-04 cart bug was found.
- **The intended product is where discovery will find it.** Recaptures #1 and #2
  both resolved the PDP to a clean-control product because `/collections/tin`'s
  membership raced the storefront cache — silently breaking four planted defects.
  This is what decision 15's pins exist for; verify the pin covers what matters.
- **Planted defects are still planted.** Hero slides in particular: slide 1 carries
  the P-01 asset, slides 2–3 must be their baseline images. A drifted slide changes
  the LCP element.

### A3. Apply the IPv4 preference ▢

This machine's router advertises IPv6 with no upstream transit, so a dual-stack
host costs `urllib` ~60s per fetch (measured 63.81s against 0.16s).

> **That 0.16s does not mean the store is fast.** It measured a 416-byte text file
> over `urllib` — it proves the route was fixed, not that pages render quickly.
> Entry 04's screen with IPv4 preferred still read home LCP 19.2–19.9s and pdp
> 20.5–23.5s. Fix the route *and* measure the pages; they are different claims.

```
netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 60 4     # elevated shell
```

- `planting/screen_candidate.py` already prefers IPv4 in-process, so **A1 is safe
  without this.** Chromium does Happy Eyeballs, so captures were never badly
  affected — but it pays up to ~300ms of head start per connection.
- **Apply it before the wave, not partway through**, so every capture in one wave
  is comparable. Entry 02's home LCP sits 85ms under the 4.0s boundary, so a
  recaptured LCP coming in **lower** is this fix landing, not a regression.

### A4. The freshness gate — MANUAL, and not optional ▢

A rendered storefront document once froze for **4+ hours**. Theme pushes, in-editor
saves, an unpublish/republish (15 minutes offline), UA changes and query params all
failed to invalidate it; the cache entry survived its own theme being unpublished.
Only `?preview_theme_id=<live id>` bypassed it, and logged-in admin views hid the
problem entirely.

**A capture can therefore silently freeze the past** — and a fixture of a stale
snapshot labels a defect out of existence with no error anywhere in the pipeline.

Assert the `compiled_assets/styles.css ?v=` stamp is current on **every revenue
template** (home, collection, pdp, cart) before capturing:

```bash
python -m planting.inspect_lcp <template-url> --password-env TSCC_STOREFRONT_PASSWORD
```

- Note the `{% stylesheet %}` compile itself can lag ~4h behind a push, so a stale
  stamp does not always mean a stale document — but it always means **stop and
  find out which.**
- **There is no code enforcing this.** If you skip it, everything downstream still
  reports success.

---

## B — The capture

### B1. Capture ▢

```bash
python -m crawler --context evals/golden/<entry>/context.yaml --out fixtures/<name>/
```

- Entry 05 is the same store with `--no-password`.
- `--seed N` makes the random 404 path reproducible.
- `--pin TEMPLATE=URL` overrides discovery; prefer the entry's `context.yaml`
  `eval.fixtures.targets` so the pin is recorded rather than typed.
- **Budget the wait.** At entry 04's declared `Crawl-delay: 10`, one capture spends
  ~2.5 minutes in delays alone. That is arithmetic, not a hang.

### B2. Read the crawl's own verdict before trusting it ▢

- `status: complete`, and the template count you expected (6/6 for a reachable
  store; 0/6 `blocked` for entry 05).
- `crawler_version` is the version you meant to capture under. This is the field
  that makes fixtures from either side of a capture-output change
  distinguishable — it is why 0.3.0 exists.
- `fingerprint.platform` matches the entry's declared platform, with evidence.
  **`unknown` on a reachable store is a failure**, not a shrug.
- **Discovery resolved to the pages you intended** — especially the PDP. Re-read
  A2's second bullet; this is the single most expensive mistake in this project's
  history.
- `fetch_interval_s` and `crawl_delay_declared` in `manifest.yaml` explain a slow
  capture from the fixture alone.
- Lighthouse ran on the templates you need. 5/6 is normal if a 404 probe served
  503; know which one is missing and why.

### B3. Secret hygiene — automatic, but verify it ran ▢

`crawler/crawl.py` calls `redaction.assert_absent`, which is **fatal and
destructive**: a hit deletes the offending files so they cannot be committed. It
checks six encodings, not just the literal — plain, two URL-quotings, backslash-
escaped quotes, base64, and `unicode_escape` (because a JSON encoder may
`\u`-escape non-ASCII).

Independently grep the whole fixtures directory for the password value — spec §10
acceptance test 2 requires it, and a check you performed yourself is worth more
than one you assume ran.

---

## C — Freeze

### C1. Archive it ▢

`fixtures/` is gitignored, so **a lost capture is a lost golden entry**, and the
archive is the only recoverable copy for the two stores we do not own.

```bash
python -m crawler.archive fixtures/<name> -o archives/<name>.tar.gz
python -m crawler.archive --check archives/<name>.tar.gz --expect <manifest sha256>
```

Verification is by `manifest.yaml`'s sha256, **not** the tarball's — gzip stores an
mtime, so a tarball hash is unstable across identical inputs.

### C2. Record provenance in `context.yaml` ▢

The `eval.fixtures` block. Inputs are frozen (brief §5) so that "my code
regressed" is distinguishable from "Lighthouse changed its scoring curve".

- `manifest_sha256` — the pin the labels are scored against. **A mismatch is fatal
  at eval time, and `--allow-unpinned-fixture` cannot suppress one.**
- `captured_at`, `lighthouse_version`, `axe_core_version`, `chrome_version`
- `throttling` — must match every other entry
- `theme_id` — name alone is ambiguous when two themes share source
- `targets` — the pins actually used

### C3. Re-derive the pack, and measure it ▢

```bash
python -m triage.pack_evidence fixtures/<name> --stats
```

Record the size beside the previous figure. The 0.3.0 price/stock clause's cost in
tokens is **still unmeasured** and can only be measured here, from a live capture.
Note the token estimate was once 2.16x low — `triage/token_estimate.py` now carries
a ratio calibrated on a real measurement.

---

## D — Label, and only then measure

### D1. Label from the frozen fixture, never from intent ▢

Decision 10, and the discipline that has held up under the most pressure.

- The spec records *intent*; the labels record **what is actually there.**
  P-01/P-02 inverted against intent, S-02 was dropped, P-04 became an MNC — every
  time, the frozen measurement overrode the plan.
- **Record *why* a label diverges from intent, in the label.** Decision 31 is the
  most recent instance, and the reason it was diagnosable at all.
- Verify each planted defect is present in the fixture **before** writing
  `expected/findings.md`.
- Boundary-straddling metrics are fragile ground truth. Where clear air on one side
  of a threshold was not achievable, **record the fragility so a future flip is not
  read as a regression** (entry 02's home LCP is 85ms under 4.0s and jitters ±0.2s).
- Add `match.any_of` spellings derived from the fixture where a hand-written
  pointer does not resolve. It only ever narrows — decision 22.

### D2. Then re-run the evals, with all five pins ▢

Not before. A run whose fixture pin does not match is not a result.

Two separate tools, and it matters which is which — **`run_triager` invokes the
model; `eval_triage` scores the output and is where the pins live.**

```bash
# 1. render the prompt, 2. run the model against it
python -m triage.run_triager <rendered-prompt> --pack <pack.json> \
    --prompt-version v1.1 -o runs/<name>.json [--via api|claude-cli]

# 3. score it — this is the step that verifies provenance
python -m triage.eval_triage runs/<name>.json \
    --entry evals/golden/<entry> --fixtures fixtures/<name> \
    --pack <pack.json> --pack-version pack/v0.2 --prompt-version v1.1
```

- **`--pack-version` has no default on `eval_triage`** and omitting it is a fatal
  `SystemExit` naming the flag. It is *not* a `run_triager` flag.
- `--pack` on `eval_triage` is what upgrades the pack pin from `asserted` to
  `matched`. On `run_triager` it is required.
- `run_triager --via claude-cli` cannot control `max_tokens` or thinking and
  prepends ~1.7k tokens of harness context; only `effort` and the resolved model
  compare across backends. **Tools must stay disabled on that path** — with them
  on, the model could read the fixture directly and the measurement is void.

Pins: fixture (`matched`/`absent`/`self-derived`) · prompt (`exists`) · rubric
(`v0.5+<sha8>`, from the file's bytes) · pack (`matched` with `--pack`, else
`asserted`) · harness (`eval/v0.2+<sha8>`).

Read the result against `PROMOTION-PROTOCOL.md` before calling it a measurement —
in particular, a prompt changed in response to the failure it is then tested
against is **fix verification, not measurement.**

---

## Known gaps in this checklist

Recorded rather than papered over, in keeping with the rest of the project.

- **A4 has no implementation.** The freshness gate is the highest-consequence item
  here and the only one that is pure prose. Automating it — assert the
  `compiled_assets` stamp on each revenue template before the capture proceeds —
  is a real crawler change and has not been scoped.
- **A2 is judgment, not a procedure.** "The intended product is where discovery
  will find it" cannot be reduced to a command without knowing the entry's intent.
- **B2's checks are a read, not a gate.** Nothing fails a capture whose PDP
  resolved to the wrong product; `validate_crawl` checks shape, not intent.
