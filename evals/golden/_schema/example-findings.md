# FORMAT EXAMPLE — not ground truth

> **Every finding below is invented.** No store was crawled. This file exists to
> show the shape of a labeled entry and nothing else. It lives in `_schema/` so
> that a harness globbing `evals/golden/*/expected/findings.md` cannot reach it.
> Do not copy the findings; copy the structure.

Scenario: a hypothetical public app-heavy Shopify store.

    schema:    findings/v0.1
    status:    EXAMPLE — no fixtures, no labeler, no provenance
    rubric:    rubric.md v0.2

## Format

Each entry is an `###` heading followed by one fenced `yaml` block. The
harness parses the blocks; the prose beneath each is for you and is never
parsed. Three buckets, not two:

- **`MC-` must-catch** — recall is measured against these.
- **`MNC-` must-not-claim** — forbidden findings and forbidden claims.
  Any hit fails the run.
- **unlabeled** — anything the agent emits that matches neither. These do
  **not** fail the run. They count toward the §5 report ceilings and land
  in the eval digest for review. Promote each into `MC-` or `MNC-` once
  judged. This is where "findings I'd have missed" becomes a number
  instead of an anecdote, and it is why the golden set gets better with
  use rather than staler.

Matching is by evidence pointer against `match.any_of`. Widen that list
when the agent finds the right thing by a different route — a pointer
mismatch is a harness bug, not a miss.

---

## Must-catch

### MC-001 — Add-to-cart control is not keyboard operable (PDP)

```yaml
severity: critical
category: accessibility
templates: [pdp]
confidence_floor: high
match:
  any_of:
    - "axe:button-name"
    - "axe:nested-interactive"
    - "crawl:pdp/product-form/div[data-add-to-cart]"
```

Rendered as a `div` with a click handler. No role, no tabindex, no
accessible name. Blocks purchase for keyboard and screen-reader users, so
it is `critical` by rubric §1 regardless of how few sessions that is.

### MC-002 — Mobile LCP 5.8s on PDP

```yaml
severity: high
category: performance
templates: [pdp]
confidence_floor: high
match:
  any_of:
    - "lighthouse:audits/largest-contentful-paint"
    - "lighthouse:audits/largest-contentful-paint-element"
```

Gallery image is the LCP element, served unresized. Over the 4.0s `high`
threshold with room to spare.

### MC-003 — CLS 0.31 on collection from a late-injected promo banner

```yaml
severity: high
category: performance
templates: [collection]
confidence_floor: medium
match:
  any_of:
    - "lighthouse:audits/cumulative-layout-shift"
    - "lighthouse:audits/layout-shift-elements"
```

Cause is inferred from shift timing, not proven — `confidence_floor` is
`medium` on purpose. If the agent reports this at `high` confidence it has
over-claimed causation, which is a severity-agreement problem worth
watching even though it does not fail the run.

### MC-004 — Eleven render-blocking third-party scripts

```yaml
severity: high
category: performance
templates: [home, collection, pdp]
confidence_floor: high
effort_floor: medium
match:
  any_of:
    - "lighthouse:audits/render-blocking-resources"
    - "lighthouse:audits/third-party-summary"
```

`effort_floor: medium` because removing any of these is an app decision,
not a code change — rubric §2 rule 1. An agent that calls this `small`
has understood the code and missed the commercial reality.

### MC-005 — Paginated collection pages share one title and lack canonicals

```yaml
severity: high
category: seo
templates: [collection]
confidence_floor: high
match:
  any_of:
    - "lighthouse:audits/canonical"
    - "crawl:collection/head/title"
    - "crawl:collection/head/link[rel=canonical]"
```

### MC-006 — Secondary navigation fails contrast

```yaml
severity: medium
category: accessibility
templates: [home, collection, pdp, search, 404]
confidence_floor: high
match:
  any_of:
    - "axe:color-contrast"
```

Present on every template but off the purchase path, so `medium` by §1.
Note the rollup: this is one finding with five instances, not five
findings. An agent that emits it per-template has failed deduplication
and will also blow the per-template ceiling.

### MC-007 — Meta descriptions missing across most PDPs

```yaml
severity: medium
category: seo
templates: [pdp]
confidence_floor: high
match:
  any_of:
    - "lighthouse:audits/meta-description"
    - "crawl:pdp/head/meta[name=description]"
```

### MC-008 — Shipping cost and free-shipping threshold not surfaced until checkout

```yaml
severity: medium
category: conversion
templates: [cart]
confidence_floor: medium
match:
  any_of:
    - "crawl:cart/cart-summary"
    - "crawl:cart/shipping-notice"
```

The one finding here that no scanner produces. If the agent catches this,
the model layer is doing the work §2 of the brief says it is for. If it
only ever catches the Lighthouse and axe items, the model is a formatter.

### MC-009 — Decorative icons carry redundant alt text

```yaml
severity: low
category: accessibility
templates: [home]
confidence_floor: high
match:
  any_of:
    - "axe:image-redundant-alt"
```

---

## Must-not-claim

### MNC-001 — No quantified commercial impact

```yaml
type: forbidden_claim
scope: narrative
reason: >
  store.aov and store.monthly_sessions are null. Any peso figure,
  percentage lift, or session count is invented by definition.
detect:
  patterns:
    - '\d+(\.\d+)?\s*%'
    - '(₱|PHP)\s*[\d,]'
    - '\b\d[\d,]*\s+(sessions|visitors|orders|customers)\b'
  exempt: benchmarks_cited   # a figure traceable to references/benchmarks.md passes
```

This is the entry's primary job. Everything else it tests, another store
also tests.

### MNC-002 — No naming a specific app as the cause without fingerprint evidence

```yaml
type: forbidden_claim
scope: [findings, narrative]
reason: >
  The Shopify fingerprint script identifies installed apps. It does not
  attribute a layout shift or a blocking script to one. Naming the
  culprit is a guess dressed as a diagnosis, and the client will forward
  it to that vendor.
detect:
  rule: app_name_in_causal_position_without_fingerprint_pointer
```

### MNC-003 — No checkout or authenticated findings

```yaml
type: forbidden_finding
scope: [checkout, account, authenticated]
reason: >
  Non-goal 3. Checkout was never crawled. A finding about it is
  fabricated regardless of how plausible it sounds.
```

### MNC-004 — No reduced-audit path

```yaml
type: forbidden_finding
match:
  any_of:
    - "audit:path/reduced"
    - "audit:platform/not-shopify"
reason: >
  This store is Shopify and the fingerprint is unambiguous. Entry 04
  tests the reduced path; this one tests that it does not fire wrongly.
```

---

## Tally

| Severity | Count |
|---|---|
| critical | 1 |
| high | 4 |
| medium | 3 |
| low | 1 |
| **total** | **9** |

Derived pass bars (rubric §7):

- **Critical/high recall: 5 of 5.** No allowance.
- **Medium/low recall: 3 of 4** (≥75%).
- **Ceilings:** ≤25 findings total, ≤8 per template. `pdp` is the tightest
  here at 4 labeled, leaving 4 slots for unlabeled before truncation.

> **Calibration, resolved.** Under rubric v0.1 (`critical 25 · high 12 ·
> medium 5 · low 1`) these nine findings summed to 89 penalty points and
> landed the composite at **11/100** — a floor-hugging score for a store
> that is ordinary-bad rather than catastrophic, leaving nowhere to put a
> store that is genuinely worse.
>
> Under v0.2 health-bar weights (`critical 15 · high 6 · medium 2 · low 1`)
> the same nine sum to 46 and land at **54/100 — Material friction**, with
> no category cap binding. A clean store carrying three medium findings
> reads 94, and the bottom of the range stays empty for stores that are
> actually broken.
