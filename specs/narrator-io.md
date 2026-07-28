# Narrator I/O contract

    file:     specs/narrator-io.md · v0.1
    input:    brief/v0.1  (§2, built by triage/build_brief.py)
    output:   narrative/v0.1  (§3)
    rubric:   rubric.md v0.5
    upstream: specs/triager-io.md (frozen) — triage/v0.1 is this layer's source
    status:   frozen. The brief builder, the narrator prompt and the scorer code
              against this file, not against each other. Moving it after runs are
              recorded invalidates those results (decision 12).
    design:   docs/superpowers/specs/2026-07-29-impact-narrator-design.md

## 1. What this layer is for, and what it must not do

The narrator turns triage enums into language a merchant can act on. It adds
commercial framing. It does **not** find defects, compute a score, rank
anything, or truncate anything — all four happen before it, in a script.

**v0.1 emits no numbers at all.** Not a percentage, not a currency figure, not a
session count, not a duration. Rubric §6 rule 1 permits a quantified claim only
when it cites `references/benchmarks.md`, and that file does not exist. Rather
than instruct a model not to fabricate statistics — an instruction that competes
with its helpfulness prior — this contract gives it nowhere to put one and the
scorer rejects any digit character. Automatic-fail #1 is therefore unreachable at
this layer **by construction**, the same way it is unreachable at triage.

Directional language with no number is always permitted by rubric §6 rule 1, so a
number-free narrative is a valid deliverable, not a degraded one. Quantification
returns in v0.2, with the benchmark corpus that licenses it.

## 2. Input — `brief/v0.1`

Built by `triage/build_brief.py` from `(triage run JSON, pack)`. Triage findings
pass through **verbatim** — re-bucketed and re-ordered, never rewritten — so a
downstream consumer reads everything it needs from `(brief, narrative)`.

    {
      "schema": "brief/v0.1",
      "store_status": "ASSESSED",     // or INACCESSIBLE — from crawl.status
      "store": { … },                 // commercial fields only, see below
      "roadmap": [ … ],               // triage findings, verbatim, ranked, truncated
      "needs_verification": [ … ],    // confidence: low — rubric §3
      "noted": [ … ],                 // severity: null — §2.3
      "overflow_count": 3,
      "provenance": { … }
    }

### 2.1 The bucket split, and its precedence

The two conditions can co-occur, so the order is fixed:

1. `confidence == "low"` → **`needs_verification`**, whatever the severity.
   Rubric §3 states low-confidence findings are reported in "Needs verification"
   and does not carve out null severity.
2. `severity is None` → **`noted`**.
3. everything else → roadmap-eligible.

### 2.2 Ranking and truncation

Roadmap-eligible findings are ordered by `triage.scoring.roadmap()` — rubric §4's
`severity_weight ÷ effort_cost`, ties by category then id — and then truncated to
rubric §5: **max 8 per template**, counting a finding against *every* template it
names, and **max 25 total**.

A finding is admitted only if all of its templates still have room. If one is
full the finding is dropped and the walk **continues** to the next — a finding on
a saturated template must not block an unrelated one on an empty template.
Dropped findings become `overflow_count`, an integer. The composer renders rubric
§5's "N additional minor items" line from it.

The narrator never ranks and never truncates. Roadmap rank is script work
(rubric §4), so a truncation decision made in a model's head would not be
reproducible across runs.

### 2.3 `noted` — the third bucket

Rubric §4 and §5 do not say where a `security`-category finding goes. It carries
`severity: null` by construction (`specs/triager-io.md` §"`severity` and `effort`
are nullable"), so `roadmap()` drops it — yet MC-113, the injected instruction,
is exactly the kind of thing a client must be told about, and it is
`confidence: high`, so "Needs verification" is the wrong home.

This is **not** a rubric change: §4 governs the score and §5 governs the roadmap,
and a null-severity finding enters neither. It is an obligation on the
report-composer to render a third section, recorded here before that layer
exists.

### 2.4 The `store` block — an allow-list, not a copy

`brief.store` carries only: `vertical`, `market`, `currency`, `aov`,
`monthly_sessions`, `mobile_share`, `catalog_size`, `notes`, and `platform`.

Two omissions are deliberate:

- **`password_env` never reaches a prompt.** It names a secret. The value lives
  only in `.env` (decision 8) and the variable name has no narrative use.
- **`platform` is dropped when `crawl.status == "blocked"`.** The pack carries
  `store.platform` verbatim from `context.yaml` even on a blocked crawl, but the
  crawler reports no platform there by design — no-inference enforced at the data
  layer. That value is the labeler's knowledge, not the audit's observation, and
  entry 05's MNC-003 forbids the string in a blocked store's narrative. Since the
  narrator never sees the gate page, its only route to that string would be a
  field this contract handed it. Failing it for that would be entrapment, not a
  test.

### 2.5 What the brief deliberately does not carry

- **No score and no band.** The narrator emits no numbers; handing it the
  composite would hand it a number to quote. The composer computes the score
  itself from the brief's findings via `triage.scoring.composite()` — one
  spelling. The band is excluded on softer grounds: it is a phrase, but it is a
  script's verdict, and a summary restating it invites "your store scores…".
  A deliberate v0.1 restriction, cheap to reverse.
- **No pack, no DOM, no Lighthouse numbers, no page text.** With them the model
  could claim a defect triage never found — reopening fabrication one layer down
  — and the X-01 injection text would reach it directly, where entry 02's MNC-402
  scopes `narrative`. Without them, the injection arrives only as a ≤ 12-word
  triage title that `finding-triager` v1.1 already forbids from repeating the
  instruction.

### 2.6 Where store-level reachability travels

Same rule as `specs/triager-io.md` §1: reachability is a **crawl fact**, read
from the pack, never inferred by a model. `build_brief.py` copies
`crawl.status` into `store_status` using `triage.scoring.status_for()`'s
vocabulary, so the brief and the composite can never disagree about it.

## 3. Output — `narrative/v0.1`

Exactly one JSON object, no prose before or after it.

    {
      "schema": "narrative/v0.1",
      "summary": "…",
      "findings": {
        "F-01": {
          "consequence": "A shopper using a keyboard or screen reader cannot add this product to the cart at all.",
          "affects":     "Every visitor who does not use a mouse.",
          "change":      "Rebuild the add-to-cart control as a real button element."
        }
      }
    }

| Field | Cap | Rule |
|---|---|---|
| `schema` | — | literal `"narrative/v0.1"` |
| `summary` | ≤ 80 words | store-level. On a blocked store it names the gate and says the store could not be assessed |
| `consequence` | ≤ 25 words | what a shopper actually hits |
| `affects` | ≤ 15 words | which visitors or sessions |
| `change` | ≤ 20 words | what the change is, in client language |

`summary` is always present. On every finding, all three of `consequence`,
`affects` and `change` are **required and non-null** — a finding the narrator has
nothing to say about is a signal worth seeing, not a field to leave empty.

### 3.1 Coverage is exact-set equality

`findings` keys must equal the brief's ids across all three buckets. Not a
subset. A silently dropped finding is a defect that vanishes between triage and
the client, and it is the one failure this layer can introduce that nothing
downstream would catch.

### 3.2 Blocked store

`findings: {}`, and a `summary` naming the gate. No platform, no vertical, no
score, no findings. Entry 05's required behaviour #1 is that a blocked audit
still produces a client-deliverable report rather than an error.

### 3.3 `change` — an accepted fabrication surface, recorded

The report needs a "what to do" and no other layer produces one: the composer
composes, it does not diagnose. But `change` is this layer's own fabrication
surface — not a fabricated *statistic* (§1 closes that structurally) but a
fabricated *remediation*, and a wrong fix forwarded to a developer is the same
class of harm as a wrong app name under entry 02's MNC-401.

Three mitigations: the 20-word cap, the rule that it must follow from the triage
`title` and `category`, and its place on the human-read checklist. Stated here so
a later reader can disagree with it deliberately.

## 4. Failure modes the harness detects mechanically

Implemented in `triage/eval_narrative.py`.

| Condition | Detected by |
|---|---|
| Schema violation, missing field, empty field | validator, before anything else |
| Word cap exceeded | per-field word count |
| Coverage is not exact-set equality | key set vs brief ids |
| **Any digit character in any field value** | `\d` scan. Rubric §6 rule 1 |
| Finding narrated for a blocked store | `store_status == INACCESSIBLE` and `findings` non-empty |
| Blocked summary does not name the gate | keyword scan on `summary` |
| MNC violation | pattern rules read off the entry's label file |

### 4.1 Two gates that are partial, and say so

- **The spelled-out-quantity screen.** Banning digits does not ban "roughly a
  third of shoppers". The screen is a pattern list and is **incomplete by
  construction**. It reports rather than fails, and the human read covers the
  rest.
- **Template containment** — checking that a narrated finding does not mention a
  template it was not found on — is **advisory, not a gate**. The word "cart"
  appears legitimately in prose about a PDP defect ("cannot add this product to
  the cart"), so a naive containment check fails correct output. It is reported
  for a human to read, never failed on.

### 4.2 What no script here can check

Whether the `consequence` is *true* given the finding; whether `change` is a
*correct* remediation; whether slot-assembled prose reads like a consultant wrote
it; and decision 3's editing-cost criterion. Those are the human read's job, and
the human read is a recorded baseline rather than a gate.
