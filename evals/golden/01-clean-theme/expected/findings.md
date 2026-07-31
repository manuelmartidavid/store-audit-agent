# Expected findings — 01 clean theme

    schema:      findings/v0.1
    labeled:     2026-07-31, from fixtures/01 (crawler 0.3.0)
    manifest:    93e3d64b2afd61db16574f1b3c62b4d890e78c6607f92389737e735f1a382d9f
    captured_at: 2026-07-31T12:24:59+08:00
    crawler:     0.3.0 · lighthouse 12.8.2 · axe-core 4.12.1 · chrome 149.0.7827.55
    rubric:      rubric.md v0.7
    store:       theme-dawn-demo.myshopify.com — Shopify's Dawn reference theme demo.
                 NOT OURS. Shopify can reconfigure it at any time; these labels
                 describe one capture, not a stable store.
    provenance:  Written from the fixture before any triager run against it.
                 **No label here was selected from model output**, so unlike entry
                 02 a recall number measured against this file is OUT of sample.
                 That is the point of this entry — see PROMOTION-PROTOCOL.md.

## What this entry is for

**This is the false-positive test.** Entry 02 asks "does the agent find what is
there"; this one asks "does it stay quiet about what is not". A clean store is
the harder input, because a model rewarded for finding things has every incentive
to find something.

The bar (rubric §5, declared in `context.yaml` **before** capture, so the grader
existed before the answers): **score ≥ 90**, **nothing above `medium`**. Both are
gated. `max_findings: 3` is measured and printed but deliberately NOT gated — the
store carries four real defects, so a correct audit emits four findings and a
volume gate would fail it for being right (design D4).

## The trap this entry actually carries

It was not planted. It was found in the capture, and it is worth more than
anything that could have been planted:

**axe reports 74 `color-contrast` violations across all six templates, `serious`
impact, tagged `wcag2aa` / `wcag143`. Every one of them is an artifact.**

    all 74 nodes    contrast ratio  1.01
    all 74 nodes    foreground #fdfdfd on background #ffffff

A real contrast problem varies — different colour pairs, different ratios,
clustered on whatever component is mis-themed. One ratio and one colour pair
across headings, product prices, links, form labels and footer text, on six
different templates, is not a design defect. It is a measurement.

The mechanism is Dawn's scroll-reveal animation. Elements carry
`scroll-trigger animate--slide-in` and start near `opacity: 0`; axe resolves the
computed foreground by blending it into the background, so foreground ≈
background and the ratio collapses to ~1. Twenty-one of the 74 name an animation
class in their own target; the rest inherit opacity from an animated ancestor,
which is why the class is not on every node.

The corroborating argument: this is Shopify's own reference theme. A theme that
shipped invisible text on every template would not survive as the platform
default.

**A run that reports contrast as a finding here has been fooled by a scanner, and
that is the single most important thing this entry measures.** See MNC-201.

## Composite (script-computed from the must-catch set)

    score: 93   band: Healthy (85–100)

    seo            4   (MC-201 2 + MC-203 2)
    performance    2   (MC-202 2)
    accessibility  1   (MC-204 1)
    conversion     0
    Σ penalties    7  → 100 − 7 = 93

Nothing above `medium`, so `findings_above_medium: 0` holds. No category cap
binds — the closest is `seo` at 4 against a cap of 25, which is the answer to the
open rubric §4 question entry 02 raised: **the caps do not bind on a clean
store**, so entry 02's binding caps are a property of that store rather than
evidence the weights are wrong.

---

## Must-catch

### MC-201 — No meta description on four templates · home, collection, cart, search
```yaml
category: seo
severity: medium            # "missing meta descriptions" is medium by name (§1)
effort: small
confidence: high
evidence:
  - lighthouse:audits/meta-description
instances: {home: 1, collection: 1, cart: 1, search: 1}
dedup: one finding across four templates (§1 rollup)
notes: >
  Lighthouse scores `meta-description` 0 on home, collection, cart and search.
  The pdp is the only template that carries one, and it is Shopify's stock
  demo-store text ("This is a demonstration store…"), auto-filled rather than
  written. The 404 also lacks one; it is not counted here because 404 has no
  Lighthouse run and the template is non-revenue.
  Collection is a revenue template, which is what keeps this at `medium` rather
  than dropping to `low` — but it affects discovery rather than any session in
  progress, so it does not reach `high`.
match:
  any_of:
    - "lighthouse:audits/meta-description"
  templates_any_of: ["home", "collection", "cart", "search"]
```

### MC-202 — PDP mobile LCP 3.16s · pdp
```yaml
category: performance
severity: medium            # LCP 2.5–4.0s (§1); boundary values take the lower level
effort: small
confidence: high
evidence: lighthouse:audits/largest-contentful-paint   # 3160 ms
notes: >
  The only template on this store outside the `good` LCP band. home 2.4s,
  collection 1.8s, cart 2.1s, search 2.0s — all comfortably under 2.5s.
fragile: >
  3.16s sits mid-band, 840 ms under the 4.0s line and 660 ms over the 2.5s line,
  so it is the least boundary-fragile perf label in the golden set. A recapture
  would have to move it a long way to change the verdict. Recorded because entry
  02's MC-107 is the opposite case and the contrast is instructive.
match:
  any_of:
    - "lighthouse:audits/largest-contentful-paint"
  templates_any_of: [pdp]
```

### MC-203 — Home `<title>` is the bare store handle · home
```yaml
category: seo
severity: medium            # revenue-template issue, affects discovery not sessions
effort: trivial             # one theme setting
confidence: high
evidence: crawl:home/html/head/title[theme-dawn-demo]
observed: "theme-dawn-demo"
notes: >
  Home's `<title>` is the raw store handle with no descriptive text — no product
  category, no proposition, not even a human-readable store name. Every other
  template composes a real title ("Bags – theme-dawn-demo", "Small Convertible
  Flex Bag – theme-dawn-demo"), so this is specific to home rather than a
  site-wide pattern.
  **`medium`, not `high`, and the distinction matters.** §1's `high` row covers a
  title that is *missing or duplicated across a template*. This one is present
  and unique — it is uninformative, which is a weaker claim. Entry 02's MC-103 is
  `high` because that title is duplicated across every collection page; nothing
  here is duplicated. A run answering `high` is a one-level disagreement, not a
  miss.
match:
  any_of:
    - "crawl:home/html/head/title[theme-dawn-demo]"
  templates_any_of: [home]
  title_any_of: ["title", "handle"]
```

### MC-204 — Heading order skips a level on the search results page · search
```yaml
category: accessibility
severity: low               # hygiene on a non-revenue template, no session impact
effort: trivial
confidence: high
evidence: axe:heading-order
instances: {search: 1}
notes: >
  One `h3.card__heading` inside a search-result card where the preceding level is
  `h1`. axe rates it `moderate` with no `wcag*` tag.
  **`low` is correct here and rubric §1 rule 7 does not lift it.** Rule 7 raises
  findings that REMOVE an access mode; a heading level skipped once on a
  non-revenue template makes heading navigation slightly less orderly, not
  unavailable — the mode-noisier side of rule 7's line, which the rule assigns to
  `low`. Compare entry 02's MC-116, where no `main` landmark exists at all on any
  template: that is the mode-removed side, and it is `medium`.
match:
  any_of:
    - "axe:heading-order"
  templates_any_of: [search]
```

---

## Must-not-claim

### MNC-201 — No contrast finding: the 74 violations are an animation artifact
```yaml
type: forbidden_finding
scope: [accessibility]
detect:
  rule: contrast_finding_derived_from_opacity_blended_scroll_reveal_nodes
match:
  any_of:
    - "axe:color-contrast"
    - "lighthouse:audits/color-contrast"
reason: >
  All 74 nodes report contrast 1.01 with foreground #fdfdfd on background
  #ffffff — one ratio, one colour pair, across six templates and every kind of
  element. That is a measurement artifact of Dawn's `animate--slide-in`
  scroll-reveal, which starts elements near `opacity: 0`; axe blends the
  foreground into the background and the ratio collapses to ~1. It is not a
  design defect, and Shopify's reference theme does not ship invisible text.
  **This is the entry's primary false-positive test.** Both scanners report it,
  it is tagged `wcag2aa`/`wcag143` and rated `serious`, and it is wrong. A run
  that emits it has deferred to a scanner over the evidence.
  Scoped to `accessibility` and pinned to the two contrast pointers rather than
  to any finding mentioning colour: a finding about, say, a genuinely low-contrast
  brand colour that cited different evidence would not be caught by this, and
  should not be.
```

### MNC-202 — No finding that the store is unfinished, demo or fake
```yaml
type: forbidden_claim
scope: [findings, narrative]
detect:
  rule: claim_the_store_is_not_a_real_business
  patterns:
    - '\bdemonstration store\b'
    - '\bdemo store\b'
    - '\bplaceholder (?:content|product|catalog)'
    - '\bnot a real (?:store|business|shop)\b'
    - '\bfake (?:store|product|catalog)\b'
    - '\btest store\b'
reason: >
  The pdp's meta description is Shopify's stock text and says outright that this
  is a demonstration store, so the fact is sitting in the evidence base waiting
  to be repeated. It is true and it is not a defect. An audit's job is the
  store's technical and commercial health; "this shop is not real" is not a
  finding, has no severity under §1, and would be actively wrong in a client
  deliverable.
  This is the shape of false positive a clean store invites: with little to
  report, a model looks for something to say.
```

---

## Known non-defects — checked, deliberately not labelled

Not screened by MNC rules, because each is defensible enough that failing a run
for reporting it would be too strict. Recorded so a future labeler does not have
to re-derive them, and so the unlabeled bucket can be read correctly.

- **Cart carries two `<h1>`s** — `h1.title--primary` "Your cart" and
  `h1.cart__empty-text` "Your cart is empty". Dawn renders both and hides one by
  cart state; the crawler visited an empty cart, so both are in the DOM. Only one
  is ever visible or announced, and axe emits nothing (`page-has-heading-one`
  checks for ≥ 1, not exactly 1). The distilled tree cannot express CSS
  visibility, so this cannot be resolved from the fixture alone.
- **Home's `<h1>` has no text** — it is `h1.header__heading` wrapping the logo
  link, Dawn's standard header pattern, with the accessible name carried by the
  logo image. axe does not fire `page-has-heading-one` on home, so the evidence
  base agrees it is present.
- **`search` is `noindex`** — Lighthouse scores `is-crawlable` 0 on search.
  Shopify sets this on search-results pages by design, and entry 02's search
  behaves identically. Non-revenue template, intentional platform behaviour.
- **`dom-size` 0.5 and `render-blocking-insight` 0 on every template** — Dawn
  ships a large DOM (933–1840 elements) and render-blocking CSS. Real, uniform
  across the theme, and not a defect of this store's configuration.

## Unlabeled bucket (not a failure)

Agent findings matching neither MC nor MNC are NOT failures. They count toward
the §5 ceilings, are reviewed, and if valid are promoted in a later revision. On
a clean store this bucket is the interesting one: it is where "the agent found a
real defect the labeler missed" and "the agent invented something" both land, and
telling those apart is the work.

## Ceilings (precision bar, §5)

    max 8 findings/template · max 25 total
    4 must-catch findings total, 0 above medium.
    No template carries more than two: home has MC-201 and MC-203.
