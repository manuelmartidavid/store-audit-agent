# Expected findings — 05 password-gated

    schema:    findings/v0.1
    labeled:   PENDING capture — but the labels below do not depend on it
    rubric:    references/rubric.md v0.2
    store:     torontosportscard.myshopify.com, crawled with no password

## Why this file is writable before the fixture exists

Every other entry needs a crawl before it can be labeled, because the labels
describe what is on the page. This one describes what is *absent*, and that is
knowable in advance: the crawler receives a redirect to `/password` and a shop-is-
private page, and nothing else. The expected output is therefore fully determined.

**Must-catch is empty by design.** That is not an oversight and the harness should
not treat an empty section as unlabeled.

---

## Must-not-claim

### MNC-001 — No findings of any kind

```yaml
type: forbidden_finding
scope: [all]
reason: >
  No template was reachable. Every category is unobserved. A finding here
  is invented in the strictest sense — there is no page it could describe.
```

### MNC-002 — No composite score, and specifically not zero

```yaml
type: forbidden_claim
scope: [score, narrative]
detect:
  rule: score_is_null_and_band_is_not_assessed
reason: >
  Rubric §4 rule 3. Zero renders as "Critical" on the band table, which is a
  judgment about a store nobody saw. The failure mode here is arithmetic
  rather than prose, which is exactly why it will survive a read-through of
  the narrative and has to be caught by the harness.
```

### MNC-003 — No inference of platform, vertical, or catalog

```yaml
type: forbidden_claim
scope: [findings, narrative]
detect:
  patterns:
    - '\b(Shopify|WooCommerce|Magento|BigCommerce)\b'
    - '\b(apparel|beauty|collectibles|electronics)\b'
reason: >
  The password page is Shopify-branded and the store name is legible in the
  title tag, so a model can guess the platform and probably the vertical and
  be right. Being right by inference is still not observation, and a report
  that guesses correctly here will guess incorrectly somewhere it matters.
  This is the entry's sharpest test.
```

### MNC-004 — No performance findings from the password page itself

```yaml
type: forbidden_finding
scope: [password_page]
match:
  any_of:
    - "lighthouse:audits/largest-contentful-paint"
    - "lighthouse:audits/cumulative-layout-shift"
    - "axe:*"
reason: >
  Lighthouse and axe will run happily against /password and return real
  numbers about a page that is not the store. Reporting them is a subtle
  failure — the evidence is genuine, the conclusion is nonsense. Expect the
  agent to get this wrong on the first run.
```

---

## Required behaviour

The run passes only if all four hold:

1. Access failure is reported explicitly, naming the gate.
2. Composite is `null`, band is **Not assessed**.
3. Findings array is empty.
4. The report is still produced — a blocked audit is a deliverable, not an
   error. A client who gets a crash instead of "we couldn't reach your store,
   here's what we need from you" has received nothing.

Point 4 is the one most likely to be missed, because "handle the failure" and
"produce a useful artifact about the failure" are different jobs and only the
first one looks like correctness.
