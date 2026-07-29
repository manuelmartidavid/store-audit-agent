# Golden entries 01 and 04 — store selection (design)

    file:    docs/superpowers/specs/2026-07-29-golden-entries-01-04-selection-design.md
    status:  design, approved 2026-07-29. Not yet implemented.
    scope:   step 10 of PROJECT-STATE "Next steps". Selection only — no capture,
             no labels. Creates two context.yaml files and two crawler
             obligations that land in the 0.3.0 capture wave.
    reads:   rubric.md v0.5 §1 §4 §5 · specs/crawler.md §3 §10 ·
             evals/golden/_schema/context.yaml · evals/PROMOTION-PROTOCOL.md
    writes:  evals/golden/01-clean-theme/context.yaml (new)
             evals/golden/04-woocommerce/context.yaml (new)
             planting/screen_candidate.py (new)

---

## Why this step, and why now

PROJECT-STATE's sequencing note says selection is free and capture is not, and
therefore that both remaining stores should be **selected now and captured once**,
in the 0.3.0 wave, rather than captured twice around the distiller fix.

Entry 01 is the larger of the two. Rubric §5's false-positive pass condition —
`≤ 3 findings, none above medium, score ≥ 90` — has never run, and readiness
blocker #1 is that the entry does not exist. Every number this project has comes
from one store built to be found out; on a sabotaged store almost anything you
find is real, so precision has never been measured at all. Entry 01 is the first
measurement that could come out badly.

Two facts discovered during selection changed the shape of both entries, and are
recorded first because the rest follows from them.

**1. Shopify theme demos are structurally not "clean" in the rubric's sense.**
Of nine probed, four are `noindex` sitewide and four more exceed LCP 4.0s on
`mobile-4g-slow`. The `noindex` is not bad luck: demo stores are deliberately
deindexed so they do not compete with real merchant stores in search. Any of
those four would emit a *correct* `critical` and fail §5 on a defect that is
genuinely there. One candidate survived.

**2. The crawler cannot yet reach a WooCommerce store politely or completely.**
Discovery is hardcoded to Shopify URL conventions, and `robots.txt`
`Crawl-delay` is not parsed at all. Both entries 02 and 05 are stores we own, so
the second has never bound. Entry 04 is the first entry on a store we do not
own, and brief §5 calls conduct non-negotiable in exactly that case.

---

## What the screen measured

All figures 2026-07-29, `planting/measure.py` (Lighthouse 12.8.2, Chrome
149.0.7827.55, `mobile-4g-slow`, cold cache per run) and a single polite `<head>`
GET per URL. Nothing was captured; no fixture exists for either store.

### Entry 01 candidates — nine in, one out

| Demo | `meta robots` | home LCP | CLS | perf | verdict |
|---|---|---|---|---|---|
| **theme-dawn-demo** | none | **2.42s** | 0.000 | 0.92 | **selected** |
| theme-craft-demo | none | 4.95s | 0.034 | 0.74 | `high` → out |
| theme-sense-demo | none | 4.56s | 0.001 | 0.75 | `high` → out |
| theme-studio-demo | none | 4.88s | 0.160 | 0.72 | `high` → out |
| impulse-theme-fashion | none | 6.03s | 0.128 | 0.54 | `high` → out |
| theme-refresh-demo | `noindex` | not measured | | | `critical` → out |
| prestige-theme-allure | `noindex` | not measured | | | `critical` → out |
| broadcast-theme-main | `noindex, nofollow` | not measured | | | `critical` → out |
| chantilly (Symmetry) | `noindex` | not measured | | | `critical` → out |

The four `noindex` candidates were not measured for performance: one
disqualifier is sufficient, and measuring further would have implied the
screen weighs disqualifiers against each other. It does not — each is a hard
gate.

### Dawn, per revenue template

| Template | LCP median | range | spread | CLS | band |
|---|---|---|---|---|---|
| home (3 runs) | 2.42s | 2.22–2.43 | 0.21s | 0.000 | below medium |
| collection (2 runs) | 2.52s | 2.12–2.93 | 0.80s | 0.000 | **straddles 2.5s** |
| pdp (2 runs) | 2.87s | 2.57–3.18 | 0.61s | 0.000 | medium |

Nothing crosses 4.0s; CLS is 0.000 on all three. Home's max run sits **70 ms**
under the 2.5s `medium` boundary and collection's spread crosses it outright —
the same jitter-fragile shape entry 02 recorded at 85 ms under 4.0s, and it goes
in the labels the same way (see D4).

### Dawn, head metadata

| Template | `<title>` | meta description |
|---|---|---|
| home | `theme-dawn-demo` | **absent** |
| collection | `Bags – theme-dawn-demo` | **absent** |
| pdp | `Small Convertible Flex Bag – theme-dawn-demo` | present (Shopify-derived) |
| cart | `Your Shopping Cart – theme-dawn-demo` | **absent** |
| search | `Search: 13 results found for "a" – theme-dawn-demo` | **absent** |

Titles are descriptive and distinct per template, so entry 02's shared-title
defect shape (S-01) does **not** apply — only home's title is the raw store
handle. `platform: shopify`, `Shopify.country = CA`, currency CAD.

### Entry 04 candidates

| | forestwholefoods.co.uk | nalgene.com | offermanwoodshop.com |
|---|---|---|---|
| WooCommerce signals | plugin asset, body class | plugin asset, body class | plugin asset, body class |
| `/shop/` | ✓ | ✓ | — |
| `/product-category/{slug}` | ✓ | ✓ | ✓ |
| `/product/{slug}` on home | ✓ | ✓ | — (not disqualifying) |
| `robots.txt` blocks a template | no | **`/cart/`** | not screened |
| `Crawl-delay` | **10** | **10** | not screened |
| meta robots | `index, follow` | `index, follow` | none |
| currency / market | GBP / GB | USD / US | USD / US |

Offerman exposes no `/product/` link on its home document, which the first pass
recorded as a disqualifier and which is **not** one: discovery finds the PDP from
the *collection* page, not from home (`specs/crawler.md` §3). Recorded because a
screen that disqualifies wrongly is worse than one that disqualifies loosely.

---

## Decisions taken

### D1 — entry 01 is `theme-dawn-demo.myshopify.com`

A store we do not own, chosen over a dev store we could build, in full knowledge
of the cost recorded in D5.

It is the only one of nine that passes every hard gate, and it passes them by
margin rather than by luck: CLS 0.000 on three revenue templates, perf 0.92, a
100 KB webp LCP image, and no `noindex` anywhere. That is Shopify's reference
theme behaving the way its README claims. For a **precision** test that matters
more than realism: on a store this well built, a finding the agent emits is much
more likely to be a false positive than on a real merchant's store, which is the
one thing this entry exists to isolate.

*Rejected:* a fresh stock-theme dev store we own — reproducible and
re-capturable, and it would have let us fill in the store-level SEO that Dawn
leaves blank, but it is a second hand-built store and the project already has
one; the Theme Store demo is portfolio-safe and needs no setup.
*Rejected:* the TSCC pre-sabotage baseline named as a fallback in
`sabotage-spec.md:32` — same store, theme and vertical as entry 02, which is
most of what PROMOTION-PROTOCOL means by out-of-sample.

### D2 — entry 04 is `www.forestwholefoods.co.uk`

WooCommerce on default permalinks, UK organic-food SMB.

Nalgene is equally clean on permalinks but its `robots.txt` disallows `/cart/`.
Our crawler respects robots, so cart would return `blocked_by_robots` and a
revenue template would drop out of the audit — conflating *reduced because
WooCommerce* with *reduced because robots*, which are the two things this entry
should keep separable. Forest Whole Foods blocks nothing we need, so all six
templates are reachable and the reduced path is exercised by platform difference
alone. It is also the better ICP match: the brief targets low-traffic SMB
stores, and Nalgene is a large brand.

**Entry 04 declares `gates: []` until it is labeled**, and that is not
inconsistent with D4. Entry 01 can declare gates before capture because rubric
§5 supplies its bar in advance; entry 04 has no pre-existing bar, so declaring
one now would mean *inventing* a precision expectation for a store nobody has
measured — the store-shopping failure in reverse. Its gates are set when its
labels are written, from the fixture.

### D3 — `path_under_test: reduced` means platform-generic discovery, not fewer pages

Settled during design, and it is the decision with build cost attached.

Discovery today is hardcoded to `/collections/{handle}`, `/products/{handle}`
and `/search?q=a`, with `/collections/all` as the fallback for both collection
and pdp. Pointed at a WooCommerce store it yields home, cart and 404 captured
and **collection, pdp and search `absent`** — no product page at all, which
guts the conversion axis, the one a merchant actually pays for.

So the crawler gains a discovery table selected by the fingerprint that already
runs:

| Template | Shopify (unchanged) | WooCommerce |
|---|---|---|
| collection | `/collections/{handle}` | `/shop` or `/product-category/{slug}` |
| pdp | `/products/{handle}` | `/product/{slug}` |
| search | `/search?q=a` | `/?s=a` |
| home · cart · 404 | unchanged | unchanged |

"Reduced" then means **fewer platform-specific signals** — no theme identity, no
Shopify app-extension fingerprinting, no Shopify CDN transcoding — not fewer
pages.

*Rejected:* accepting three `absent` templates and calling that the test. It
would measure honesty-under-partial-evidence, which is real but is already
entry 05's job, and would leave the conversion axis untested on the only
non-Shopify entry.
*Rejected:* pinning collection and pdp via decision 15 and accepting `search`
as absent. Costs nothing, but a pinned entry proves the pin works, not that
discovery does — and entry 04 exists to exercise the non-Shopify path.

### D4 — entry 01 gates severity and score; the finding **count** stays advisory

```yaml
expect:
  score_min: 90              # rubric §5
  score_max: 100
  findings_above_medium: 0   # rubric §5
  max_findings: 3            # rubric §5's claim — measured and printed, NOT gated
  categories_required: []
  gates: [score_range, findings_above_medium]
```

The screen already shows Dawn carrying genuine defects: meta description absent
on all four non-PDP templates probed (MC-115's shape, `medium` — 404 was not
probed, so the real instance count is four or five), home's title being the raw
store handle, and a PDP LCP sitting in the `medium` band. A correct audit of
Dawn plausibly emits 3–5 findings. Checked against §5's three conditions
separately: `score ≥ 90` survives (five mediums = 10 penalty = 90) and
`none above medium` survives; **only the count is at risk, and it is at risk
from true positives.**

Those three conditions are not equally load-bearing. "None above medium" and
"score ≥ 90" are false-positive bars — they fail when the agent invents
severity. "≤ 3" is a volume bar, and a store with four real medium defects
fails it by being audited correctly. Gating it would make entry 01 report a
precision failure that is actually a store fact.

`max_findings: 3` is therefore **set but not gated**, so every run prints §5's
claim beside the actual and the recalibration argument accumulates evidence
instead of anecdote. The file will carry that reasoning in full: `eval_triage.py`
treats a declared gate with a missing value as fatal precisely because step 8
found silently-inert declarations twice, and an unexplained ungated value is the
same failure one step further out.

*Rejected:* gating all three as §5 literally specifies — most faithful, and it
would force the rubric question with numbers in hand, but it spends the
project's first out-of-sample measurement on a probably-failing run whose
failure says nothing about the agent.
*Rejected:* capturing first and setting the bar afterwards. That is the
store-shopping shape step 8 warned about; entry 01's grader must exist before
its answers do.

### D5 — neither store is owned, so the screen is re-run at capture

The cost of D1 and D2 is that Shopify and Forest Whole Foods can both change
their sites between today and capture day. A `noindex` appearing on Dawn would
silently turn entry 01 from a precision test into a `critical`-emitting one, and
nothing in the pipeline would flag it as a selection problem rather than an
agent problem.

So the criteria ship as `planting/screen_candidate.py`, re-run immediately
before capture, and its output is recorded in the entry's result file. A gate
that fails at capture time is a **re-selection trigger**, not a defect to label
around.

Two further consequences, stated rather than left implicit:

- `crawler/archive.py` runs at capture for both entries. For an unowned store
  the archive is the only recoverable copy; the manifest sha256 is the
  commitment, and there is no re-capturing an identical fixture.
- `aov: null` on both, honestly rather than as a contrivance — there is no AOV
  to know for a store we do not own. Entry 04 carries the labeled fabrication
  trap (`_schema/context.yaml`: "Entries for stores you don't own should keep
  aov null deliberately"); entry 01 inherits the same constraint without being
  the entry that tests it.

### D6 — `Crawl-delay` becomes a crawler obligation

`crawler/robots.py` parses allow/disallow only; `crawler/session.py` sleeps a
fixed `min_interval_s`. Forest Whole Foods declares `Crawl-delay: 10`, as does
Nalgene — it is normal for WordPress stores behind a caching plugin.

Every prior entry was a store we own, so the gap has never bound. It binds now:
brief §5 conduct is non-negotiable for stores we do not own, and ignoring a
declared delay is the clearest possible violation of it. `robots.py` parses the
directive, `session.py` honours `max(min_interval_s, crawl_delay)`, and the
effective value is recorded in `manifest.yaml` so a slow capture is explicable
rather than alarming.

Practical consequence worth knowing before someone thinks the crawler has hung:
at 10s across ~14 fetches, an entry-04 capture takes roughly three minutes of
wall clock in delays alone.

---

## Deliverables, in build order

Selection first, then the two crawler obligations it created — which land with
the 0.3.0 distiller fix, because all three change capture behaviour and the wave
is meant to be one bump.

1. `evals/golden/01-clean-theme/context.yaml` — D1 store block, D4 expect block,
   the screen output of 2026-07-29 recorded as `eval.fixtures` provenance with
   `captured_at: null`
2. `evals/golden/04-woocommerce/context.yaml` — D2 store block, `aov: null`,
   `path_under_test: reduced`, `expect.gates` deferred to labeling with the
   reason stated
3. `planting/screen_candidate.py` + tests — the D5 screen, wrapping
   `planting/measure.py` and `crawler.fingerprint`/`crawler.robots` rather than
   re-implementing either
4. **(0.3.0 wave)** D3 platform-generic discovery: fingerprint-selected URL
   table in `crawler/discovery.py`, Shopify behaviour unchanged, `specs/crawler.md`
   §3 updated, tests including the acceptance test §10 case 4 already names
5. **(0.3.0 wave)** D6 `Crawl-delay`: `robots.py` parse, `session.py` honour,
   `manifest.yaml` record, tests
6. PROJECT-STATE update — step 10 done, steps 11–12 gain D3 and D6

Items 4–6 are named here so the wave's scope is honest, but they are
implementation, not selection. If the plan that follows splits them out, that is
the right split.

---

## Open, recorded rather than solved

- **No labels exist for either entry, and none are implied above.** Both
  `expected/findings.md` files are written from the frozen fixture after
  capture (decision 10). The Dawn defects named in D4 are screen observations,
  not labels — the fixture decides, including whether collection's LCP lands
  medium or below.
- **Entry 04's MNC set** — including the null-AOV fabrication trap and a
  `platform: woocommerce` no-inference trap mirroring entry 05's MNC-003 — is
  label work for the capture wave.
- **Open decision #2 (category caps binding on `seo` and `accessibility`)**
  stays open. Entry 01 was nominated as its cheap settler and cannot settle it
  until entry 01 runs.
- **Entry 01 shares entry 02's market.** Dawn's demo is CA/CAD, so it adds a
  second theme and a second vertical but not a second benchmark set. Entry 04
  supplies GB. Recorded because "one theme, one vertical" is readiness blocker
  #4 and this only half-closes it.
- **Dawn's home LCP is 70 ms under a band boundary and collection straddles
  one.** Entry 02's learning applies verbatim: record the fragility in the
  label so a future flip reads as jitter, not regression.
- **`aov: null` on entry 01 was not chosen for its own sake.** It follows from
  not owning the store. If entry 01 ever needs to test quantification, that
  requires a store whose AOV we can legitimately declare — which entry 02
  already is.
