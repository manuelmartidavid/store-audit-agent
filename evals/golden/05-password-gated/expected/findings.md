# Expected findings — 05 password-gated

    schema:    findings/v0.1
    labeled:   PENDING capture — but the labels below do not depend on it
    rubric:    references/rubric.md v0.2 (written against; v0.3 changed §2 only)
    store:     torontosportscard.myshopify.com, crawled with no password
    first run: 2026-07-28, finding-triager v1.0 × 3 against fixtures/05.
               1 of 3 behaved as labeled. MNC-002/003/004 held in all three;
               MNC-001 was violated by two — see the note below, which is an
               OPEN CONTRADICTION and not a settled verdict.
               Record: evals/results/05-blocked-path.md

## OPEN — MNC-001 contradicts rubric §1

MNC-001 requires an empty findings array. Rubric §1 lists **"store unreachable"**
verbatim as representative `critical` evidence, and the triager prompt inlines §1
because the rubric *is* its bounded vocabulary. So the prompt instructs the model
to do what this file forbids, and two of three runs obeyed the prompt.

Nothing below has been changed in response. The resolution is a rubric decision
(strike or reword the "store unreachable" row so a finding always describes a
page somebody looked at, leaving the gate to the report's `null` / INACCESSIBLE
state per §4 rule 3) and a rubric change invalidates every label written against
v0.3. Do not resolve it by inference; the argument on both sides is written up in
evals/results/05-blocked-path.md.

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
  rule: score_is_null_and_status_is_INACCESSIBLE   # rubric v0.4 §4 rule 3
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
2. Composite is `null`, status is **INACCESSIBLE**, band is **Inaccessible**
   (rubric v0.4 §4 rule 3; was band **Not assessed** under v0.3).
3. Findings array is empty.
4. The report is still produced — a blocked audit is a deliverable, not an
   error. A client who gets a crash instead of "we couldn't reach your store,
   here's what we need from you" has received nothing.

Point 4 is the one most likely to be missed, because "handle the failure" and
"produce a useful artifact about the failure" are different jobs and only the
first one looks like correctness.
