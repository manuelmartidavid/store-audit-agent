# Crawler interface spec

    file:     specs/crawler.md · v0.1
    rubric:   references/rubric.md v0.4
    status:   interface frozen on acceptance; implementation free to change

This document specifies the contract, not the implementation. Anything that reads
`crawl.json` — the eval matcher, the triager prompt, the report renderer — codes
against this file. The crawler may be rewritten freely underneath it.

Design rule that governs everything below: **format for the model, adapt for the
harness.** Every structure here passes through a context window before it passes
through a diff. Where the two masters conflict, the model wins and the harness
normalizes.

---

## 1. Scope

The crawler produces the complete deterministic evidence base for one store:

```
fixtures/
├── crawl.json          ← this spec
├── lighthouse.json     ← standard LHR array, one entry per template (§7)
├── axe.json            ← standard axe-core results array, one per template (§7)
└── manifest.yaml       ← provenance (§8)
```

It does not interpret. A `div`-based add-to-cart button is recorded as a `div`
with its attributes; deciding that this is a critical accessibility finding is
the triager's job. If a proposed crawler feature involves an opinion, it is
mis-scoped.

## 2. Session model

One browser context per store, shared across all template visits and all
Lighthouse runs.

1. Navigate to origin.
2. If redirected to `/password`: read the password from the env var named by
   `store.password_env`. If set, POST the form, confirm the session cookie, and
   proceed — this is a site-wide gate, not authenticated testing (ruling recorded
   in sabotage-spec). If null or rejected, emit a **blocked crawl** (§6) and stop.
3. Crawl templates (§3), then run Lighthouse and axe in the same context (§7).

The password value never appears in any output file, log line, or error message.
`manifest.yaml` records only `gate: password_supplied | none | blocked`.

## 3. Template discovery

Fixed target set, discovered in order, first match wins:

| Template | Discovery | Fallback |
|---|---|---|
| home | `/` | — |
| collection | first link matching `/collections/{handle}` from home nav, excluding `/collections/all` | `/collections/all` |
| pdp | first product link within the chosen collection | first `/products/{handle}` sitewide |
| cart | `/cart` | — |
| search | `/search?q=a` | — |
| 404 | `/{random-40-hex}` | — |

Rules:

- **One page per template.** The agent audits templates, not pages; sampling more
  adds tokens, not signal. The chosen URL is recorded so labeling looks at the
  same page the crawler saw.
- **Bounded by construction:** max 6 fetches for discovery + 6 template captures
  + gate handling. A 40,000-product catalog costs the same as a 40-product one —
  adversarial case 4 is satisfied structurally rather than by a timeout.
- A template that 404s or redirects off-origin is recorded as `absent`, not
  guessed at.
- `robots.txt` is fetched first and respected. Disallowed templates are recorded
  as `blocked_by_robots` — a fact for the report, not a gap to route around.
- Politeness: ≥1s between fetches, one concurrent request, identifying
  user-agent. Non-negotiable for stores we don't own (brief §5 conduct).

### Pinned targets (eval-harness override)

Discovery reads the live store, so "first product in the collection" is a
merchandising fact — and on a cached storefront it can differ between two
requests seconds apart, which makes a golden fixture non-reproducible. A golden
entry may therefore **pin** a template's URL: `context.yaml eval.fixtures.targets`
(or CLI `--pin template=url`) sets `collection`/`pdp` to exact URLs, bypassing
discovery. Pins are eval-only — read by the crawler, never rendered, never
reaching a prompt (same rule as the rest of the `eval:` block). Default
behaviour is unchanged: with no pin, discovery runs exactly as before. A
cross-origin pin is a config error, not a silent miss.

## 4. crawl.json shape

```jsonc
{
  "schema": "crawl/v0.1",
  "origin": "https://torontosportscard.myshopify.com",
  "status": "complete",          // complete | partial | blocked
  "gate": "password_supplied",   // none | password_supplied | blocked
  "fingerprint": {               // pattern-matching only, per boundary table
    "platform": "shopify",       // shopify | woocommerce | custom | unknown
    "evidence": ["cdn.shopify.com asset URLs", "Shopify.theme JSON"],
    "theme": { "name": "Dawn", "version": "12.0.0" },   // null if not detected
    "apps": [                    // detected, never causally attributed (MNC-002)
      { "name": "Judge.me", "evidence": "script src pattern" },
      { "name": "restockrocket-1", "evidence": "theme app extension asset path" }
    ]
  },
  "templates": {
    "pdp": {
      "url": "https://…/products/example-card",
      "status": "captured",      // captured | absent | blocked_by_robots | error
      "http_status": 200,
      "distilled": { /* §5 */ },
      "dropped": {               // absence must be distinguishable from omission
        "script_bodies": 14,
        "style_blocks": 3,
        "svg_internals": 22,
        "comment_nodes": 9
      }
    }
    // …one entry per template in §3, always all six keys present
  }
}
```

`status: partial` means at least one template captured and at least one errored.
`blocked` means zero templates captured — the §6 shape applies.

### fingerprint.apps

Two detection paths, and `evidence` says which one fired:

| `evidence` | Means |
|---|---|
| `script src pattern` | a URL matched a known vendor domain; `name` is that vendor's display name |
| `theme app extension asset path` | a URL matched `/extensions/<uuid>/<handle>-<build>/`; `name` is the handle **verbatim**, build counter stripped |
| `script src pattern + theme app extension asset path` | both, folded to one entry under the vendor display name |

Extension handles are not prettified. `al-bulk-discount-manager` is what the
store serves; rendering it as "AL Bulk Discount Manager" would be a guess at a
product name that nothing in the capture supports. A path that does not match
the convention — including one whose uuid segment is not a uuid — names nothing.
The domain list alone can only ever recognise apps somebody hardcoded, which on
an app-heavy store means reporting one app out of seven.

## 5. Distillation

Raw DOM is ~500KB of markup per store, mostly script bodies and SVG paths no
finding will ever cite. The triager reasons over the distilled tree; distillation
is therefore part of the prompt architecture, and its rules are conservative:
**when in doubt, keep.**

**Kept, in document order:**

- `head`: title, meta (name/property/content), link (rel/href), canonical
- Landmarks: header, nav, main, footer, aside, and any `role` attribute
- Headings h1–h6 with text
- Interactive elements: a, button, input, select, textarea, form, and any
  element carrying a click-related attribute or `tabindex` — with **all**
  attributes and visible text. This clause is what catches C-01's div-button.
- img / source / video / iframe with all attributes; for img additionally the
  rendered dimensions vs intrinsic dimensions when obtainable
- Structured data: JSON-LD blocks verbatim, microdata attributes
- Text nodes over 20 chars, whitespace-collapsed — this is what V-01/V-02/V-03
  and the X-01 injection ride in on; drop it and the model-only findings are
  undetectable by construction
- Script/link *references*: src/href + async/defer/type. Never bodies.

**Dropped, with counts recorded in `dropped`:** script bodies, style blocks, SVG
internals (the svg element itself is kept with role/aria attributes), comments,
data-URI payloads over 1KB.

**Shape.** Distilled nodes are a recursive structure:

```jsonc
{
  "tag": "button",
  "attrs": { "type": "submit", "name": "add" },
  "text": "Add to cart",            // own text, not descendants'
  "children": [ /* same shape */ ]
}
```

Depth is unbounded but breadth is not: sibling runs of identical tag+class
collapse after 5 instances into `{"repeat": {"count": 47, "sample": {…}}}` —
a collection grid contributes five product cards and a count, not fifty cards.
The count is signal (catalog behaviour); the remaining 45 cards are not.

## 6. Blocked crawl shape

A blocked store still yields a valid, complete fixture:

```jsonc
{
  "schema": "crawl/v0.1",
  "origin": "https://…",
  "status": "blocked",
  "gate": "blocked",
  "block": {
    "kind": "password_page",     // password_page | bot_challenge | http_error | dns
    "evidence": "302 → /password; form[action='/password']",
    "final_url": "https://…/password"
  },
  "fingerprint": { "platform": "unknown", "evidence": [], "theme": null, "apps": [] },
  "templates": { /* all six present, all status: "blocked" */ }
}
```

Note `platform: "unknown"` even though the password page is recognizably Shopify.
The fingerprint reports what was *observed of the store*, and the store was not
observed. This is entry 05's MNC-003 enforced at the data layer instead of the
prompt layer — the cheapest place to enforce anything.

## 7. Lighthouse and axe integration

- Lighthouse runs via the Node API against the shared authenticated context —
  not the CLI, which cannot carry the session cookie. Standard LHR JSON,
  unmodified, one run per captured template. Throttling profile comes from
  `manifest.yaml` and must match across all golden entries.
- axe-core injected into the same pages, standard results JSON, raw violations
  only — no severity mapping, that is the rubric's job via the triager.
- A Lighthouse failure on one template marks that template's entry
  `"lighthouse": "failed"` in the manifest and continues. Partial evidence is
  recorded as partial (adversarial case 5), never interpolated.

## 8. manifest.yaml

```yaml
schema: manifest/v0.1
captured_at: 2026-07-24T14:00:00+08:00
origin: https://…
gate: password_supplied
crawler_version: 0.1.0
lighthouse_version: PENDING
axe_core_version: PENDING
chrome_version: PENDING
throttling: mobile-4g-slow
templates:
  pdp: { crawl: captured, lighthouse: ok, axe: ok }
  # …
```

Every eval run records this manifest's hash alongside prompt and rubric versions.
A green run without all three pinned is not a result.

---

## 9. Evidence pointer grammar

The join key between fixtures, hand labels, and triager output. Three namespaces:

```
lighthouse:audits/<audit-id>              e.g. lighthouse:audits/largest-contentful-paint
axe:<rule-id>                             e.g. axe:button-name
crawl:<template>/<semantic-path>          e.g. crawl:pdp/product-form/button[add-to-cart]
```

The first two are verbatim tool vocabulary — models know these IDs from training,
which makes them cheap to emit correctly. The third is constructed:

```
<semantic-path> ::= <segment> ( "/" <segment> )*
<segment>       ::= <name> ( "[" <qualifier> "]" )?
```

- `<name>` is, in priority order: the element's `id` · its `role` · a Shopify
  section/block name if present in attrs · the tag name.
- `<qualifier>` disambiguates siblings: a distinctive attr value, a text slug
  (kebab-case, ≤4 words), or 1-based index as last resort.
- Paths are **shallow by intent** — anchored at the nearest landmark or named
  section, not the document root. `pdp/product-form/div[add-to-cart]`, not a
  twelve-segment tag chain.

**Why semantic, not crawler-assigned IDs:** these pointers pass through the
triager's context window as evidence it must emit. An opaque `node-4f2a` forces
blind lookup-table work, and the characteristic model failure there is emitting a
*plausible* ID rather than a correct one — manufacturing automatic-fail #2 out of
the format itself. A semantic path is something a model constructs correctly from
the DOM it is actually reading.

**Matching is normalized, not exact.** The harness resolves pointers case-
insensitively, ignores index qualifiers when the un-indexed path is unambiguous,
and matches on suffix when the anchor differs. `match.any_of` in the labels
absorbs remaining variation. A correct finding with a near-miss pointer is a
matcher bug, not a model miss — tune the matcher, don't fail the run.

---

## 10. Acceptance tests (crawler only, live targets)

Per brief §5, the crawler is tested against live targets; prompts and scoring are
tested only against fixtures. Minimum set:

1. TSCC without password → §6 blocked shape, `kind: password_page`
2. TSCC with password → six captured templates, gate recorded, no password in
   any output byte (grep the entire fixtures dir for the value)
3. Any public Shopify store → fingerprint yields `shopify` with evidence
4. Non-Shopify site → fingerprint yields `woocommerce`/`custom`, crawl still
   completes (feeds the reduced path, entry 04)
5. `robots.txt` disallowing `/collections` → collection recorded
   `blocked_by_robots`, crawl continues
6. Distillation idempotence: crawl → distill → the same page distilled twice
   yields byte-identical JSON (determinism is the whole point of fixtures)
```
