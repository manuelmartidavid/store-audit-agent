# Expected findings — 05 password-gated

    schema:    findings/v0.1
    labeled:   PENDING capture — but the labels below do not depend on it
    rubric:    rubric.md v0.2 (written against; v0.3 changed §2 only;
               v0.5 struck §1's "store unreachable" — decision 30 — which
               removed a contradiction with this file and changed no label here)
    store:     torontosportscard.myshopify.com, crawled with no password
    first run: 2026-07-28, finding-triager v1.0 × 3 against fixtures/05.
               1 of 3 behaved as labeled; MNC-002/003/004 held in all three.
               The two MNC-001 violations were traced to the rubric, not the
               model — see below. Record: evals/results/05-blocked-path.md
    then:      2026-07-28, finding-triager v1.1 × 3. **3 of 3.**

## RESOLVED — decision 30 (2026-07-28)

This file previously carried an OPEN block recording MNC-001 as contradicting
rubric §1, which listed **"store unreachable"** as representative `critical`
evidence. The contradiction was real but mis-attributed: **rubric §6 rule 3
already forbade emitting any finding for an unreachable store**, so MNC-001
restated the rubric rather than opposing it, and the conflict was internal to
the rubric — §1 against §6.

Two further facts settled it. The triager prompt inlines §1 but **not** §6, so
the model had exactly one rule about unreachable stores and two of three runs
applied it correctly. And no label in this file or in entry 02 was written
against the struck clause.

**Resolution: rubric v0.5 strikes `· store unreachable` from §1** and adds §1
tie-break rule 6 (a finding describes a defect on a template that was captured).
`finding-triager/v1.1` carries the corrected §1 plus the blocked-store
instruction v1.0 lacked entirely. **Nothing in this file changed except this
header and MNC-001's `reason`, which now cites its source.** No verdict was
recomputed: v1.0 runs 1 and 2 still fail, run 3 still passes.

Full argument: `plans/09-decision-30-store-unreachable.md`.

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
derives_from: >
  rubric.md §6 rule 3 (automatic fail — blocked-store fabrication), restated
  here as an entry-level screen. Since v0.5 it is also §1 tie-break rule 6,
  from the severity side. Not `source:` — that key is reserved by
  evals/PROMOTION-PROTOCOL.md for how a label entered the set, and this label
  was neither planted nor promoted.
reason: >
  No template was reachable. Every category is unobserved. A finding here
  is invented in the strictest sense — there is no page it could describe.
  It also cannot cite anything: a blocked crawl has no distilled tree, so
  `crawl:home` does not resolve and the finding trips automatic fail #2 on
  emission. This label is not an extra bar the entry invents; it is the
  rubric's own clause, made checkable.
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
