# Store Audit Agent — project state

    updated:  2026-07-30 (crawler 0.3.0 merged · decision 31 · IPv6 route
              diagnosed · this file trimmed to what the next steps need)
    history:  `docs/PROJECT-HISTORY.md` holds the full 1,395-line narrative this
              file was trimmed from on 2026-07-30. Nothing was deleted, only
              moved. Go there for the *why* behind a settled decision, the
              recapture blow-by-blow, or the prompt lineage.
    note:     decision 30 was argued and verified on 2026-07-28; its commits
              landed 2026-07-29 00:02 across the midnight boundary. The 28th is
              the decision date.
    supersedes: phase-numbering in 02-store-audit-brief.md (workflow detached from
                numbered phases by explicit decision; gates kept, sequence dropped)
    for Claude: treat this file as ground truth for decisions. Do not re-open
                settled decisions unless the user does. Do not invent facts about
                projects 01 or 03–08 — their details are not recorded here. Where
                this file and `docs/PROJECT-HISTORY.md` disagree, this file wins.

## What this project is

Given a store URL, produce a scored, prioritized audit report (performance, SEO,
accessibility, conversion) with effort estimates and commercial reasoning.
Shopify-first, diagnose-only in v1, public pages only. Full brief:
`02-store-audit-brief.md`.

Governing design rule: **scripts measure, the model judges, the human sends.**
The score is computed by script from model-assigned enums, never generated.
Top project risk: **fabricated impact claims.** Every quantified claim must cite
`references/benchmarks.md` or be stated directionally with no number.

---

## Where we are

- **Crawler `0.3.0`**, steps 1–13 done and merged to `main`. **622 passed, 1
  skipped.** The full suite runs **~8–16 min** on this machine — three runs on
  2026-07-30 took 15m31s, 13m34s and 8m08s, so treat the spread as browser-
  integration variance and budget the upper end. A single figure here would be
  over-precise.
- **Entry 02 is the only exact ground truth**: `fixtures/02-sabotaged` frozen at
  manifest `b219afac…`, 17 must-catch labels, composite **24** / band Critical,
  18 recorded runs.
- **`finding-triager` v1.0 frozen** at 17/17 recall on entry 02 — **in-sample**,
  because four labels were promoted from v0.4 run output before v1.0 was scored
  against them. **v1.1 exists** (decision 30) and **has never run against entry
  02**; it does not inherit v1.0's 17/17.
- **Recall is proven in-sample. Precision has never been measured.** Every number
  in this project comes from one store built to be found out — on a sabotaged
  store almost anything you find is real. Not ready for a client deliverable;
  ready for **shadow runs** — point it at a real store, read the output, send
  nothing.

### Next steps, in order

**14. Recapture everything under 0.3.0, in one pass.** The wave everything else
waits on, and it is Marti's: it needs live stores, `TSCC_STOREFRONT_PASSWORD`, and
`planting/screen_candidate.py` re-run immediately before each capture (D5).

> **Follow `docs/RUNBOOK-capture-wave.md`** — the ordered, copy-pasteable version
> of everything below, including the machine fixes that come first.
> `evals/FREEZE-CHECKLIST.md` holds the reasoning behind each step; the runbook
> holds the sequence. The runbook defers to the checklist on any conflict.

- `02-sabotaged` — recapture → re-freeze → **re-label**. Price and stock become
  detectable under 0.3.0, so the presence checklist gains back two items and the
  label set likely grows past 17. This retires `b219afac…`; the fixture-hash pin
  firing on the next eval run **is** the intended signal, not a failure.
- `05` (blocked path), `makerlab` (confirm as entry 03 — currently stale at
  0.1.0), and fresh captures of `01` and `04`.
- **Follow `evals/FREEZE-CHECKLIST.md`.** It is the wave's procedure, written
  2026-07-30. The freshness gate in particular is not optional and has no
  implementation — see *Storefront documents cache hard*.
- **Measure pack size**: `triage/pack_evidence.py --stats` on the new entry-02
  pack, recorded beside the old 522 KB. The price/stock clause's token cost is
  unknown and can only be measured from a live capture.
- **Before starting:** apply the machine-wide IPv6 preference fix, and do it
  *before* the wave rather than partway through, so every capture in it is
  comparable. See *IPv6 is advertised but has no transit*.

**15. Re-run and re-measure v1.0** against the new entry-02 fixture; restore the
two presence-checklist items in a v1.1. Then run entry 01 — the project's first
real **precision** measurement.

- **Carries decision 31's deferred obligation:** clarify rubric §1 so loss of
  assistive-technology navigation reads as a subset-of-sessions impact rather than
  hygiene. It rides here because §1 is inlined verbatim by every prompt, so it
  needs the prompt version and re-label this step is cutting anyway. Label
  exposure audited as zero. **Do not let the re-label pass without it** — that is
  the whole cost argument for deferring it.

**16. `report-composer`.** Renders rubric §5's "N additional minor items" from the
brief's `overflow_count`, plus two obligations recorded during step 9: rendering
the `noted` bucket (`specs/narrator-io.md` §2.3), and computing the score from
`triage.scoring.composite()`. It does **not** rank or truncate — roadmap rank and
both ceilings are `triage/build_brief.py`, which hands it `overflow_count` already
computed.

**17. End-to-end on a real store**; test decision 3's kill criterion (>30% editing
cost) for the first time.

**18. Cost and latency at portfolio scale.** Exercise the Console-API backend
(`--via api`, never yet run), then measure N runs across several stores. **The cost
model is N=1**: 315,094 in / 18,808 out, 3m34s, $3.62 notional, `claude-opus-5`
(`runs/v1.0-cli-run1.json`). Entry 05's runs are a blocked store — 26 KB prompt, 22
output tokens each — and must not be averaged in.

### What blocks a real deliverable, in order

1. **Entry 01 has never run.** Rubric §5's false-positive pass condition
   (≤3 findings, none above `medium`, score ≥90) is untested.
2. **No composer.** No client artifact exists, so decision 3's kill criterion is
   untested for want of anything to edit.
3. **One theme, one vertical.** `tsc-theme-v3` is hand-built; only `collectibles`
   exercises the material-facts table.

---

## Current state of the artifacts

### Golden entries

| entry | store | status |
|---|---|---|
| 01 clean theme | `theme-dawn-demo.myshopify.com` | selected, **not captured**. Gates `[score_range, findings_above_medium]`; finding count left **ungated** with `max_findings: 3` printed, because the screen found real defects on Dawn and §5's `≤3` would fail on true positives while the two false-positive bars hold. |
| 02 sabotaged | TSCC (`torontosportscard.myshopify.com`), aov 85 CAD | **frozen & labeled.** 13 planted defects + 4 promoted = 17 MC, 4 MNC. |
| 03 app-heavy | `makerlab-electronics-ph.myshopify.com` | captured but **stale at 0.1.0** — its `apps[]` names 1 app where 0.2.0+ yields 7. Recapture before use. |
| 04 WooCommerce | `www.forestwholefoods.co.uk`, aov **null** (fabrication trap) | selected, **not captured**. Gates `[]` until labeled — declaring one now would invent a precision expectation for a store nobody has measured. |
| 05 password-gated | TSCC, no password | captured & labeled. The only entry labelable pre-crawl; it describes an absence. Traps: no platform/vertical inference from a Shopify-branded gate; no findings from the `/password` page itself; a blocked audit must still produce a client-deliverable report. |

Entries 02 and 05 are the same store, crawled with and without the password.
**Entries 01 and 04 are not owned**, so the screen re-runs before each capture and
`crawler/archive.py` at capture is the only recoverable copy.

Entry 04 was chosen over Nalgene, which disallows `/cart/` in `robots.txt` — that
would drop a revenue template and conflate *reduced because WooCommerce* with
*reduced because robots*, the two things this entry must keep separable.

### Fixtures on disk

Gitignored; the manifest hash is the commitment. `02` (pre-sabotage baseline,
0.1.0) · `02-sabotaged` (frozen, `b219afac…`) · `05` (`12899ce7…`, recorded
`self-derived`) · `makerlab` (stale).

### Prompts and runs

`finding-triager` v0.1–v0.6, **v1.0 frozen**, **v1.1** (decision 30) ·
`impact-narrator` **v0.1**, measured (entry 02 3/3, entry 05 1/1, zero numerals,
zero MNC violations, editing cost ≈5% at N=1 against the >30% kill line) ·
`report-composer` **none**.

**25 run records on disk, and they are not interchangeable.** 4 carry a recorded
model (1 entry 02, 3 entry 05); 21 are agent sessions that cannot be re-run. 19 are
usable as narrator input — the entry-02 ones, which carry findings; the other 6 hold
empty arrays.

### Layout (decision 28: one repo, layers as directories)

    crawler/   evidence production (crawl, distill, pointers, fingerprint, robots, …)
    triage/    pack_evidence · eval_triage · render_prompt · run_triager · build_brief
    planting/  measure · inspect_lcp · make_hero_p01 · fit_image · screen_candidate
    prompts/   finding-triager/ · impact-narrator/
    specs/     crawler.md · triager-io.md · narrator-io.md
    evals/     golden/ labels · results/ records · HARNESS-CHANGELOG · PROMOTION-PROTOCOL
    fixtures/  gitignored
    tests/     one suite, root-relative

There **is** a real seam for later — evidence production vs everything downstream —
already contracted in `specs/`. Its two blockers: `rubric.md` (it is both the
bounded vocabulary and the labeling guide, so neither side can own it) and
`crawler.pointers` (the harness must not get a second spelling of the matcher — a
matcher that resolves differently from the pointer builder yields **wrong recall,
not an error**). Resolve those and the split becomes safe. Not before.

---

## Decisions — settled, do not re-open

1. **Lighthouse: local (Playwright + Node API), not PSI.** PSI cannot reach
   password-gated stores and CrUX has no data for low-traffic SMB stores. Node API
   over CLI because the password cookie must carry across template runs in one
   browser session.
2. **Success metric: tiered recall + precision ceilings.** 100% recall on
   ground-truth critical/high, ≥75% on medium/low. Recall = finding detected
   (matched by evidence pointer); **severity agreement is a separate metric — never
   collapse them.** Ceilings ≤8/template, ≤25 total, overflow truncated by roadmap
   rank and reported as a count.
3. **Kill criterion: editing-cost test.** If >~30% of the narrative needs rewriting
   before a client could receive it, the translation layer failed. Runtime is a
   separate gate. (Replaced a detection-based criterion, which tested the wrong
   thing — writing, not detection, is what eats the 3–5h.)
4. **Report: HTML** single file with print stylesheet. ReportLab in reserve.
5. **TSCC is golden entries 02 AND 05**, confirmed live behind its password gate,
   and disposable. No Shopify Partner dev store needed.
6. **Score is a health bar, not a grade.** Weights critical 15 / high 6 / medium 2
   / low 1. Category cap 25. Bands: 85+ Healthy · 65–84 Minor drag · 45–64 Material
   friction · 25–44 Significant work · <25 Critical.
7. **A blocked store scores `null`, status `INACCESSIBLE`, never 0.** Zero is a
   verdict about a store nobody saw — fabrication by arithmetic.
8. **Storefront password entry ≠ authenticated testing.** A site-wide gate, not a
   customer session. Password lives in `TSCC_STOREFRONT_PASSWORD`; committed files
   hold only the variable name. **Grep every fixture capture for the password value
   — it must appear nowhere.**
9. **Evidence pointers are semantic paths, not opaque IDs.**
   `lighthouse:audits/<id>` · `axe:<rule-id>` · `crawl:<template>/<semantic-path>`.
   Pointers pass through the triager's context window, and models emit
   plausible-but-wrong opaque IDs, manufacturing automatic-fail conditions.
   **Near-miss pointers are matcher bugs, not model misses — normalize, don't fail.**
10. **Golden labels are written from frozen fixtures, not from intent.** You aim a
    planted defect at a threshold side; the measured fixture decides the label.
11. **AOV semantics:** a declared AOV in `context.yaml` is legitimate input (entry
    02 tests correct quantification *with* a number). A null AOV forbids all
    numbers — that trap lives in entry 04.
12. **Eval provenance: five pins**, all verified rather than printed — see
    *Provenance* below. (The decision as originally recorded names three; five is
    what the code enforces.)
13. **Apps are fingerprinted by the extension-path convention, not a domain list.**
    `/extensions/<uuid>/<handle>-<build>/` is parsed and the handle reported
    verbatim, never title-cased. A domain list named 1 app where 7 were present.
    The uuid segment must look like a uuid; off-convention names nothing, because
    **a wrong app name is worse than a missing one.**
14. **The effort floor covers any third-party app, paid or free.** The floor is not
    about the invoice: uninstalling is a decision about a capability the merchant
    may rely on, and the crawl never observes price.
15. **Golden entries may pin template URLs** (`context.yaml eval.fixtures.targets`,
    or `--pin`). Discovery that reads live merchandising is not reproducible. Entry
    02 pins `pdp`; collection stays discovered, because its defects are
    template-level.
16. **The distiller keeps control-like elements.** `is_click_attr` recognises
    `data-*` behaviour hooks; `keep()`/`_text_for` retain button-classed divs. A
    JS-wired div-button reaches the triager as a crawl pointer — axe cannot see it,
    so the pointer is the only evidence.
17. **S-02 dropped from entry 02** — Shopify derives the PDP meta description from
    the X-01 injection body, so a "missing meta" gap cannot coexist with the
    injection on one product. X-01 wins; S-02 moves to a later entry.
18. **P-01/P-02 remain a boundary pair.** The frozen fixture measured home 3915ms
    `medium`, pdp 10504ms `high` — straddling 4.0s as designed. Recorded as
    **jitter-fragile**: home reads 3.9–4.2s across captures, and 3.92s is 85ms
    under the line.
19. **Git init, fixtures ignored.** The commitment is the manifest hash recorded in
    `expected/findings.md` and `context.yaml`, not the capture bytes.
20. **Single-pass triage, model-side rollup.** The pack fits; rollup is a semantic
    judgment ("same defect") and a script would need a sameness key the crawl does
    not provide. The script validates ceilings, `instances` **keys** and duplicate
    matches instead.
21. **`severity_rationale` kept** (≤20 words, rubric clause only) — it is what makes
    a severity disagreement diagnosable rather than merely countable. It earned its
    keep at decision 31. The validator flags a rationale carrying a number without
    a clause.
22. **`expected/findings.md` carries `match:` blocks.** Five of thirteen
    hand-written pointers did not resolve against the fixture, and scoring a model
    against an unresolvable target fails correct findings for reasons unrelated to
    detection. `match.any_of` carries fixture-derived spellings and only ever
    narrows. No verdict, severity or composite value changed.
23. ~~MNC-404 narrowed to findings with no node-level evidence.~~ Reverted by
    decision 25.
24. **pack/v0.2 — every distilled node carries its own `@` pointer.** Supersedes
    crawler spec §9's reasoning *on measurement*: §9 argues a model constructs
    semantic paths correctly from the DOM it reads, and across nine runs it did
    not. §9's argument against *opaque* ids is untouched — `@` is the semantic path
    itself, precomputed by the same function the harness resolves with, so grammar
    drift is impossible by construction. Cost +126 KB (pack 396 → 522 KB).
    Unresolvable pointers went 2–5 per run to **zero**, and MC-112 went from
    unreachable to matched every run. Highest-leverage change in the whole loop.
25. **MNC-404 stays strict; the judgment moved into the labels.** The one real
    defect it was catching — a search input with no accessible name — is now covered
    by MC-108, so a run that finds it matches a label and is exempt. The gate stays
    blunt.
26. **Four findings promoted to must-catch** (MC-114 no `<h1>` on home · MC-115 meta
    descriptions absent on four templates · MC-116 no `main` landmark · MC-117
    sixteen home CTAs and category cards on `href="#"`), each verified in the
    fixture independent of model output. Composite recomputed **35 → 24**, band
    Critical, `expect` range 18–34.
27. **The per-template ceiling gates the report-composer, not the triager.** Rubric
    §5 caps findings per template *"in the ranked roadmap"* — a report behaviour the
    triager cannot perform. The 17-label ground truth puts 8 must-catch findings on
    the PDP, exactly the cap, so enforcing it at triage makes perfect recall
    structurally impossible. Total ceiling stays hard. **This is the loop's one
    relaxed bar, flagged rather than buried.**
28. **One repo, layers as directories.** See *Layout* above.
29. **Blocked stores report `INACCESSIBLE`** (rubric v0.4). `score` stays **null** —
    the only value that cannot be rendered as a grade, sorted into a league table
    or averaged across a portfolio. `status` is a first-class field emitted for
    every store, derived in `status_for()` so it cannot drift from the score.
    **Presentation only:** v0.4 did not touch §1/§2/§3, the sections the prompt
    inlines, so every prompt through v1.0 stays frozen and valid and no label
    verdict changed.
30. **"store unreachable" leaves rubric §1** (v0.5). It contradicted §6 rule 3,
    which already made emitting any finding for an unreachable store an automatic
    fail — so the conflict was **internal to the rubric**, and the labels were never
    what had to move. §1's *rule* column still covers a cart that 403s on a
    reachable store; the right-hand column is representative evidence, not an
    enumeration. Added §1 tie-break rule 6: a finding describes a defect on a
    template that **was captured**. Reachability is measured, so asking the triager
    to re-report it turns a measurement into a judgment — and it is the one finding
    class that can never cite anything. **v0.5 edits §1, which every prompt inlines
    verbatim**, and is narrow only because no label was written against the struck
    clause. That kind of narrowness is luck, checked for; a future §1 edit should
    expect to pay.
31. **MC-116 keeps `medium`; the gap is in §1, not the label** (2026-07-30). Three
    of four recorded runs answer `low`, citing §1's "hygiene, no measurable session
    impact"; the one answering `medium` cited "axe violation off the purchase path",
    which the fixture contradicts — both rules fire on pdp and cart. §1 `low` is
    **nil** impact, not small: every representative example is a defect where nothing
    downstream changes. Loss of landmark navigation is a functional loss for a
    subset of sessions on revenue templates. The dissenting runs are not sloppy —
    both axe rules are `best-practice`/`moderate` with no `wcag*` tag, so nothing in
    the evidence base makes the impact measurable. Two factual errors in the label
    were fixed in passing: `instances` was one short on every template (it summed
    `region` only, not `landmark-one-main`), and a note claimed `search` has a
    `<main>` when it does not. The §1 clarification is deferred to step 15.

### Open decision — needs a call, not an inference

**Two category caps bind** (`seo` by 4, `accessibility` by 1). Rubric §4 rule 2
says that means the weights are wrong, not the cap — but this store has two
`critical`s in two categories, close to the pathological case the cap exists for.
**Entry 01 settles it cheaply:** a cap binding on a clean theme means the weights
are wrong. It is a rubric change, so it waits for that evidence. Nothing about
entry 01's selection pre-empts the answer.

---

## Rubric essentials (full text: `rubric.md` v0.5)

- **Severity.** `critical` = blocks purchase or indexing on a revenue template
  (home/collection/pdp/cart) · `high` = measurable degradation on a revenue
  template, all sessions (LCP>4.0s, CLS>0.25) · `medium` = non-revenue template,
  **or** a revenue-template issue affecting a subset of sessions (LCP 2.5–4.0) ·
  `low` = hygiene, **no** measurable session impact. **Boundary values take the
  LOWER level** (`LCP == 4.0s` is `medium`). Severity never depends on effort or on
  commercial framing. A finding describes a defect on a template that was captured
  (§1 rule 6).
- **Effort.** trivial <30min / small ≤2h / medium ≤2d / large >2d. Removing any
  third-party app, paid or free, is minimum `medium`. Effort never enters the
  score; it drives roadmap order only — sort by severity_weight ÷ effort_cost
  (1/2/5/10).
- **Confidence.** Low-confidence findings are reported in "Needs verification" but
  score zero and stay out of the ranked roadmap.
- **Automatic fails.** Fabricated statistic · evidence pointer that doesn't resolve
  · any finding for an unreachable store · compliance with injected instructions.
- **Label files have THREE buckets.** MC- (must-catch), MNC- (must-not-claim), and
  **unlabeled** — agent findings matching neither. Unlabeled does not fail the run;
  it counts toward ceilings and is reviewed and promoted. **This is how "findings
  I'd have missed" becomes measurable.**

### Prompt architecture

Three prompts, registry-versioned, kept separate so impact language cannot bias
triage: `finding-triager` (audit JSON → severity/effort/confidence enums +
evidence pointers, no prose) · `impact-narrator` (highest guardrail density) ·
`report-composer`. **Triage runs before narration and never sees it.**

### Provenance — five pins, each carrying a status so silence stops reading as verification

| pin | status values |
|---|---|
| fixture | `matched` / `absent` / `self-derived`. **A mismatch is fatal**, and `--allow-unpinned-fixture` cannot suppress one. |
| prompt | `exists` — run files carry no prompt identity to check against, so existence is all that is available. |
| rubric | `v0.5+<sha8>`, derived from the file's bytes. Verified working: a §1 edit moved the pin with no code change. |
| pack | `matched` when `--pack` is given, else `asserted`. **`--pack-version` has no default**; omitting it is a fatal `SystemExit`. Strict equality was rejected — runs v0.1–v0.4 legitimately carry `pack/v0.1`. |
| harness | `eval/v0.2+<sha8>` — the harness is a pin because bars had moved six times with nothing recording it. |

---

## Gotchas and traps — the things that come back as bugs

Kept at full length deliberately. Each has already cost this project a wrong
number, a lost hour, or a retracted figure.

### Environment and host

- **IPv6 is advertised but has no transit** (diagnosed 2026-07-30). The router hands
  out a global prefix (`2001:4450:…`) and answers on IPv6, but hop 2 returns
  unreachable — no upstream route. Host config is clean (correct global address,
  correct default route, gateway pings in 1ms); it is **router/ISP-side**.
  Consequence: **`urllib` has no Happy Eyeballs**, so it blocks the full ~60s
  connect timeout on the dead AAAA before falling back to IPv4. Measured **63.81s**
  on entry 04's `robots.txt` against **0.16s** once IPv4 is preferred. **This is
  what produced entry 04's retracted "LCP 19–23s" figures — the store answers in
  under a second.**
  - `planting/screen_candidate.py` calls `prefer_ipv4()` at the top of `main` and
    prints a `resolver:` note. It **reorders, never filters** — dropping `AF_INET6`
    would make a genuinely IPv6-only host unreachable, trading a host quirk for a
    capability loss.
  - **Chromium does Happy Eyeballs** (~300ms failover) and runs as a separate
    process, so `measure.py` and the capture path are unaffected and deliberately
    left alone: forcing a family there would change capture conduct to work around
    a host quirk.
  - **Machine-wide fix, NOT yet applied** (needs an elevated shell):
    `netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 60 4`. Revert with
    `netsh interface ipv6 reset prefixpolicies`. Do **not** disable IPv6 via the
    `DisabledComponents` registry value; do not disable the adapter binding.
  - **Every Shopify host is dual-stack too**, so the ~300ms Chromium head start
    touched entry 02's captures. Home LCP 3.92s sits 85ms under the 4.0s boundary,
    so **a recaptured LCP coming in lower is the fix landing, not a regression.**
- **The device file-bridge cache serves stale staged copies.** Verify staged content
  (grep for a known token) before trusting it, or copy to a fresh filename.
- **Git through the bridge leaves lock/temp litter and cannot delete.** Move `.lock`
  files into `_to_delete/gitlocks/` or the next git command fails with "Another git
  process seems to be running". Deletions go to `_to_delete/`.
- **The Windows console is cp1252.** `run_triager.py` once crashed *after* calling
  the model and writing its record, because it could not encode a `✓` — a completed,
  paid-for run exiting non-zero on its own report. stdout/stderr now reconfigure to
  UTF-8 with `errors="replace"`.
- **The suite's size is machine-dependent.** The repo-hygiene lint walks untracked
  and generated trees, so it collects a case for `.pytest_cache/README.md` — a file
  pytest generated while collecting. A suite whose size depends on whether it has
  been run before cannot be pinned.

### Store mechanics that sit between the plant and the measurement

- **Storefront documents cache hard.** A rendered page froze for **4+ hours**: theme
  pushes, in-editor saves, an unpublish/republish (15 min offline), UA changes and
  query params all failed to invalidate it, and the cache entry survived its own
  theme being unpublished. Only `?preview_theme_id=<live id>` bypassed, and
  logged-in admin views hid it. **A capture can silently freeze the past** — a
  fixture of a stale snapshot would label a defect out of existence with no error
  anywhere. The **freshness gate** (assert `compiled_assets/styles.css ?v=` is
  current on every revenue template before capturing) is step A4 of
  `evals/FREEZE-CHECKLIST.md` and is **not optional**. It is also **not
  implemented** — `planting/inspect_lcp.py` shows the stamp, nothing gates on it —
  so skipping it still reports success everywhere downstream. Note the
  `{% stylesheet %}` compile can itself lag ~4h behind a push, so a stale stamp
  does not always mean a stale document; it always means stop and find out which.
- **Shopify transcodes PNG masters to lossy webp (~108 KB on the wire at any upload
  weight) but ships JPEG masters verbatim.** An "oversized PNG hero" is not heavy on
  the wire, so a heavy-image performance defect **must** be a JPEG. CDN behaviour
  sits between the plant and the measurement — **always verify at the wire, not at
  the upload.**
- **Shopify auto-generates a product's meta description from its body.** So a body
  injection also lands in `<meta name=description>`, and a "missing meta
  description" defect cannot coexist with it on one product. One defect per
  observable field; check for platform-derived fields before assuming independence.
- **Discovery that reads the live store is not reproducible.** "First product in the
  collection" raced the storefront cache between two requests seconds apart, twice,
  resolving the PDP to a clean-control product and quietly breaking four planted
  defects. Hence decision 15's pins. Any capture step depending on live
  merchandising is a reproducibility bug waiting to happen.
- **`robots.txt` is first-match-in-file-order** (`urllib.robotparser`), and
  Shopify's leads with `Allow: /` — so its `Disallow: /cart/` evaluates to
  *allowed*. The screen's `robots_allows:{template}` gate therefore detects nothing
  on a Shopify entry, structurally rather than by luck.
- **WooCommerce lets a store rename the cart slug.** Entry 04 serves its cart at
  `/basket/` and 404s on `/cart/` — a UK store using the British term. Discovery
  reads the store's own cart link now, rejecting `add-to-cart` hrefs and the
  profile's own product paths (WooCommerce's loop button for variable, grouped and
  external products carries class `add_to_cart_button` but links to the product
  permalink).

### Detection blind spots

- **Div-buttons are invisible to everything.** A `<div>` styled as a button and
  wired by external JS (`getElementById`) has no inline interactive attribute, so
  axe does not flag it **and** distillation dropped it. Fixed (decision 16), but the
  lesson generalizes: **the crawler must keep anything that *presents* as a
  control.** Any element-detection rule keyed on tag names alone has this blind spot.
- **Rendered prices and stock state used to be dropped** — `$149.99` is 7 chars,
  under the 20-char prose floor, and a price span is not interactive. Fixed in
  0.3.0. **Two residual gaps recorded in spec §5, not closed:** a bare
  `<span>In stock</span>` with no class hook and no number is still dropped, and so
  is a genuine stock badge whose only hook is a `badge` class — `"badge"` was
  removed from `_VALUE_CLASS_SUBSTRINGS` because this repo's own fixture theme
  emits `.badge--new`, `.badge--hot`, `.badge--preorder`, `.badge--limited` and a
  filter-count badge, none of which are purchase-decision facts.
- **`_MONEY_RE` is compiled without `re.I` on purpose.** Case-insensitive ISO-4217
  matching caught ordinary copy — "**Try** 10 days risk-free", "**cop** 10" —
  because TRY and COP are real currency codes.
- **`urllib.robotparser` parses integer `Crawl-delay` only**, so a fractional
  declaration reads as absent. Below the 1s floor that changes nothing; above it, a
  fraction is silently lost. (`manifest.py` renders the declared value with an
  `is not None` check, not truthiness, so a declared `0` records as `0` rather than
  `null` — the evidence layer records what was declared.)
- **`detect_platform` runs twice over different signal sets** — home-page-only in
  `crawl.py` to pick the discovery URL table, fully-merged at the end for the
  fixture — and **the two can disagree.** Shopify evidence wins outright over
  WooCommerce's, so a home-only `woocommerce` verdict flips to `shopify` the moment
  a later template loads a Shopify asset. Separately, `_WOO_URL_MARKERS` includes
  the generic `/wp-content/themes/`, so any WordPress store qualifies on template
  evidence alone. Ships as designed — an unrecognised platform falls back to the
  Shopify table, so no frozen fixture can regress — and `crawl.py` logs the
  divergence, but **the log line has no test**; no test in this suite asserts log
  content.
- **A large declared `Crawl-delay` is honoured in full, however long that takes.**
  `Crawl-delay: 600` makes one capture spend ~2.3 hours waiting. No cap, because a
  cap would under-honour what the store asked; declining a store outright is the
  operator's call, not the crawler's. At entry 04's declared 10s, one capture spends
  ~2.5 minutes waiting — worth knowing before it reads as a hang.

### Measurement discipline

- **`planting/measure.py` needs one browser per run** (cold cache) or repeat runs
  read the asset from cache and "variance" is an illusion.
- **Boundary-straddling metrics are fragile ground truth.** Prefer planting metrics
  with clear air on one side of a threshold; when that is not achievable, **record
  the fragility in the label so a future flip is not read as a regression.**
- **The fixture decides, repeatedly.** P-01/P-02 inverted vs intent, then re-formed
  as a pair at 3.92s; P-04 became an MNC; S-02 was dropped. Every time, the frozen
  measurement overrode the plan — and it was non-trivial to hold to that ourselves.
  **Record *why* a label diverges from intent, in the label.** Decision 31 is the
  most recent instance.
- **A gate count is a property of the screen, not of the store, and dates with the
  code.** Entry 01's screen has read 9, 15 and 16 hard gates across three commits.
  Entry 04's last screen (9 of 9 head gates, exit 0) predates both the `platform`
  gate and the exit-3 change; **expect 10 head gates and exit 3** when it re-runs.
- **The token estimate was 2.16x low** at a 4-chars-per-token prose rule, which is
  wrong on dense JSON. `triage/token_estimate.py` now carries a calibrated ratio.
- **Recall rates can fall because the denominator grew.** The v0.4 re-score reads
  `1.00 (6/6) → 0.875 (7/8)`: the runs detect one *more* label than before. Read
  the fraction, not the rate.
- **In-sample results must be labeled as such.** `evals/PROMOTION-PROTOCOL.md` rule
  3. v1.1's 3/3 on entry 05 is fix verification, not measurement — the prompt was
  changed in response to the failure it was then tested against, and MNC-002/003/004
  pass **by construction** on an empty array.

### Known follow-ups, none blocking

- **`--self-test` crashes with `StopIteration` on entry 05** (a blocked store has no
  synthetic findings) and never validates gate declarations — the natural place to
  catch a typo in `expect.gates` before a run.
- **`evals/golden/_schema/context.yaml` is stale.** All four golden entries carry
  keys it does not declare (`manifest_sha256`, `targets`, `score`, `band`, `status`,
  `gates`), and it is the first file a future labeler reads.
- **Entry 05 declares no `status` key** — the entry whose whole point is
  `status: INACCESSIBLE`.
- **`README.md`'s archive instruction cites the label header as the pin source;**
  `context.yaml` is authoritative, and entry 05 has no such header.
- **Off-Shopify app hosts are still domain-list-only.** `fixtures/makerlab` shows
  synctrack, good-apps, zaapi and identixweb, none in `APP_SIGNATURES`. Several are
  now named through their extension handles instead. Growing the hardcoded list is
  the thing decision 13 exists to avoid — **leave it.**
- **A WooCommerce bounded-fetch path is untested:** `_product_sitewide`'s
  `already == fallback` dedupe branch is unreachable in the fixture, because both
  `/shop` and `/product-category/nuts/` serve the same product links.
- **Three dangling references, found while trimming this file (2026-07-30).** All
  pre-existing; the stale-path lint cannot see them because it is a denylist of two
  literal spellings, not a resolver — its own docstring predicted exactly this.
  - **`references/benchmarks.md` does not exist**, and there is no `references/`
    directory. This file names it as the citation source for every quantified
    claim, and `prompts/impact-narrator/v0.1.md` cites it too. **Deliberate in
    effect, not a hole:** `tests/test_eval_narrative.py:102` records that the
    narrator bans *all* digits precisely because the file is absent, which makes
    automatic-fail #1 unreachable by construction. So the numeral ban — not the
    benchmark file — is what actually enforces the project's top-risk control. If
    benchmarks.md is ever written, that ban is the thing to revisit. **Still
    outstanding**; left alone deliberately, because the ban works.
  - ~~`02-store-audit-brief.md` does not exist~~ — **addressed 2026-07-30, as an
    explicitly-labelled RECONSTRUCTION.** The original was in the phase-0 zip,
    never unpacked, and is not recoverable. The new file rebuilds only what the
    repo's own citations pin — §5 (conduct is a floor · inputs are frozen · the
    crawler is tested live and everything downstream against fixtures), §6 case 3
    (injection, two-part pass condition), and non-goal 3 (no authenticated
    testing, and the ruling that a storefront gate is not a customer session).
    **§1–§4, §7+, and non-goals 1–2 are marked NOT RECOVERED rather than
    invented**, and the file disclaims authority beyond those citations. If the
    original ever surfaces it replaces the reconstruction wholesale.
  - ~~There is no "freeze checklist" document~~ — **written 2026-07-30:
    `evals/FREEZE-CHECKLIST.md`**, beside `PROMOTION-PROTOCOL.md`. Covers the
    capture wave end to end (screen → store-state verification → IPv4 preference →
    freshness gate → capture → verdict read → secret hygiene → archive →
    provenance → pack → label → measure), with each item tied to the incident that
    motivates it. **It records its own gaps:** the freshness gate is still the
    highest-consequence item and the only one that is pure prose, because
    automating it is an unscoped crawler change.

---

## Working conventions with Claude on this project

Technical-peer register, argue-before-hardening at one-way doors, unilateral calls
flagged explicitly. Assigned persona: experienced AI prompt engineer with
full-stack/DevOps/cloud background. **Fabrication discipline applies to Claude
itself:** no invented recall of other projects, no plausible-fiction labels in the
golden path, product facts verified against current docs rather than memory.
