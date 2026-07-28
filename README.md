# Store Audit Agent

An agent that audits a Shopify (or other) storefront and produces a ranked,
evidence-backed report a client could act on: what's wrong, how severe, how much
effort to fix, and how confident we are — without inventing a single number.

The project is built the other way round from most agent work. The scoring
rubric and a hand-labeled **golden set** come first; the agent is measured
against them. The guiding rule is that a plausible-but-wrong claim is worse than
a miss, so the whole design pushes judgement onto evidence that can be checked
and treats fabrication — an invented statistic, an unresolvable evidence pointer,
a score for a store nobody saw — as an automatic failure.

> **Status.** The **crawler** — the deterministic evidence base under everything
> else — is complete and tested. The reasoning layers it feeds (triager,
> narrator, report renderer) and the eval harness are specified but not yet
> implemented. See [Implementation status](#implementation-status).

---

## How it fits together

```
   store URL ─┐
              ▼
        ┌───────────┐   crawl.json / lighthouse.json / axe.json / manifest.yaml
        │  crawler  │──────────────────────────────────────────────┐
        └───────────┘   deterministic, no interpretation            │
                                                                     ▼
        ┌──────────┐   ┌───────────┐   ┌─────────┐          ┌────────────────┐
        │ triager  │──▶│ narrator  │──▶│ report  │          │  eval harness  │
        │ (rubric) │   │ (impact)  │   │ render  │          │  vs golden set │
        └──────────┘   └───────────┘   └─────────┘          └────────────────┘
        severity/        directional      client              recall + severity
        effort/          impact, only     deliverable         agreement, scored
        confidence       cited numbers                        against hand labels
```

- **crawler** captures the store into fixtures and *does not interpret*. A
  `div`-based add-to-cart button is recorded as a `div` with its attributes;
  calling that an accessibility defect is a later job. If a crawler feature would
  require an opinion, it's mis-scoped.
- **triager** assigns each finding a severity / effort / confidence from a
  bounded vocabulary (`rubric.md`), using only the evidence in the fixtures.
- **narrator** adds commercial framing but may quote a number *only* if it traces
  to a cited benchmark; directional language with no number is always allowed.
- **report renderer** produces the ranked roadmap and composite health score.
- **eval harness** scores agent output against the golden set by evidence
  pointer — recall and severity agreement measured separately.

Everything downstream codes against `specs/crawler.md`, which is a frozen
interface: the crawler may be rewritten underneath it freely.

---

## Repository layout

```
specs/crawler.md          the crawler interface contract (frozen on acceptance)
rubric.md                 scoring vocabulary + labeling guide (severity/effort/confidence/score)

crawler/                  ◀ implemented — see crawler/README.md for internals
  __main__.py             CLI (python -m crawler)
  crawl.py                orchestration
  session.py              Playwright: politeness, storefront gate, capture
  distill.py              DOM distillation (pure, deterministic)
  pointers.py             evidence-pointer grammar + normalized matcher
  fingerprint.py          platform / theme / app detection (pattern-matching only)
  discovery.py robots.py  template discovery + robots.txt
  axe.py lighthouse.py    scanner integration
  schema.py               crawl.json conformance check (shared with consumers)
  redaction.py            secret hygiene, enforced against written bytes
  manifest.py dotenv.py   provenance + .env loading
  js/  node/              browser-side DOM walker; Lighthouse Node sidecar

evals/golden/             the hand-labeled evaluation set
  _schema/                the shape of a golden entry (context.yaml + findings.md)
  02-sabotaged/           TSCC with deliberately planted defects (exact ground truth)
  05-password-gated/      the same store with no password — the blocked-store case

triage/                   the eval loop — pack_evidence · render_prompt · eval_triage
planting/                 defect-planting tooling (measure · inspect_lcp · fit_image)
prompts/                  finding-triager v0.1 … v1.0, registry-versioned

tests/                    unit + browser-integration tests for the crawler
```

Each golden entry has two parts, and the split is load-bearing: `store:` in
`context.yaml` is serialized into the model's context; `eval:` is harness-only
and must **never** reach a prompt. That is what keeps the recall numbers from
measuring how well the model reads its own answer key.

---

## The crawler

Produces the complete deterministic evidence base for one store — four files:

| File | Contents |
|---|---|
| `crawl.json` | distilled DOM per template, platform fingerprint, gate/block state |
| `lighthouse.json` | standard LHR array, one entry per captured template |
| `axe.json` | standard axe-core results, one entry per captured template |
| `manifest.yaml` | provenance — tool versions, throttling profile, per-template status + a hash |

It visits one page per template (`home`, `collection`, `pdp`, `cart`, `search`,
`404`), so a 40,000-product catalog costs the same as a 40-product one. Design
details and internals are in [`crawler/README.md`](crawler/README.md).

### Setup

```bash
python -m pip install --user -r requirements.txt   # exact pins — see the file
python -m playwright install chromium
npm ci                                             # ci, not install: honours the lock
```

> On this machine global pip is broken; use `python -m pip install --user` and
> call tools as modules (`python -m pytest`, `python -m playwright`).
>
> Use `npm ci`, never `npm install`. The pinned Lighthouse and axe-core versions
> are an input to the golden labels, and `npm install` may resolve past them.

### The storefront password

TSCC (the golden store) is a permanently password-gated Shopify dev store.
Clearing that gate is a site-wide password, not authenticated testing, so the
crawler has a password-entry path. The password lives in a **gitignored `.env`**:

```
# .env  (never committed)
TSCC_STOREFRONT_PASSWORD=…
```

`context.yaml` holds only the *name* of the variable (`password_env`), never the
value. The crawler reads that name, loads the value from `.env`, and — before it
reports success — greps every output file for the value and deletes them if it
leaked. The password never appears in any output byte, log line, or error.

### Usage

```bash
# Gated capture of TSCC (golden entry 02) — reads origin + password_env from the context
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/02/

# The same store with no password — the blocked-store case (entry 05)
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/05/ --no-password

# Any store by URL
python -m crawler --origin https://someshop.myshopify.com --out fixtures/scratch/

# Fast structural pass (skip Lighthouse, ~30s instead of ~3 min)
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/02/ --no-lighthouse
```

Useful flags: `--no-lighthouse`, `--no-axe`, `--no-password`, `--seed N`
(reproducible 404 path), `--headed` (watch the browser), `--password-env NAME`
(override the variable name), `--env-file PATH`. Full list: `python -m crawler --help`.

A run prints a per-step log and a summary:

```
· loaded 1 var(s) from .env: TSCC_STOREFRONT_PASSWORD
· gate: password_supplied
· home: captured (HTTP 200, 142 nodes)
  …
✓ fixtures/02 · manifest sha256 a1b2c3d4e5f6
  status=complete gate=password_supplied platform=shopify captured=6/6 lighthouse=6 axe=6 fetches=9
```

It makes **real requests to the live store**, politely: ≥1s between fetches, one
request at a time, an identifying user-agent, and `robots.txt` respected. TSCC is
the disposable dev store the spec designates for this.

### Backing up a capture

`fixtures/` is gitignored and the store it came from has drifted, so a capture
is not reproducible — only restorable.

```bash
python -m crawler.archive fixtures/02-sabotaged -o archives/02-sabotaged.tar.gz
python -m crawler.archive --check archives/02-sabotaged.tar.gz --expect <manifest sha256>
```

Copy `archives/` somewhere off this machine. The `--expect` value is the
`manifest:` line in that entry's `expected/findings.md`.

### Running the triager

`triage/run_triager.py` calls the model directly (requires `ANTHROPIC_API_KEY`)
and writes a run file that records what produced it — model, effort, thinking,
max_tokens, the SDK version, token usage, and a digest of the exact rendered
prompt and pack fed in — instead of just the model's bare JSON:

```bash
python triage/pack_evidence.py fixtures/02-sabotaged \
    --context evals/golden/02-sabotaged/context.yaml -o packs/02-sabotaged.pack.json
python triage/render_prompt.py prompts/finding-triager/v1.0.md \
    --pack packs/02-sabotaged.pack.json --indent 0 -o runs/v1.0.rendered.md
python triage/run_triager.py runs/v1.0.rendered.md --pack packs/02-sabotaged.pack.json \
    --prompt-version finding-triager/v1.0 -o runs/v1.0-run4.json
python triage/eval_triage.py runs/v1.0-run4.json --prompt-version finding-triager/v1.0 \
    --pack-version pack/v0.2
```

`--pack-version` has no default: the recorded corpus spans `pack/v0.1` and
`pack/v0.2` (see `evals/results/07-finding-triager.md` for which runs carry
which), so any default would be wrong for some of it. A pack built just above
is `pack/v0.2` — pass `--pack packs/02-sabotaged.pack.json` too to verify the
claim against the pack file itself rather than merely asserting it.

`triage/eval_triage.py` reads both this wrapped shape and the bare `{schema,
findings}` shape the 21 recorded runs use — the frozen runs are read unchanged,
never rewritten.

---

## Tests

```bash
python -m pytest tests/ -q                              # unit + browser integration (~4 min)
CRAWLER_TEST_LIGHTHOUSE=1 python -m pytest tests/ -q    # also run the Lighthouse sidecar
```

The pure layers (distillation, pointers, fingerprinting, schema) run on a bare
interpreter via a Python mirror of the DOM walker. The integration tests drive a
real Chromium against a local storefront (`tests/store_fixture.py`) that
reproduces the golden entry 02 defects and can be toggled into every branch —
password gate, robots disallow, non-Shopify platform. The live acceptance tests
in `specs/crawler.md` §10 remain the acceptance bar; the suite proves the
machinery beneath them.

---

## Implementation status

| Component | State |
|---|---|
| Crawler (`crawler/`) | **Implemented and tested** — `specs/crawler.md` v0.1 |
| Scoring rubric (`rubric.md`) | v0.4; calibrated against entry 02, not yet frozen |
| Golden set (`evals/golden/`) | Entries 02 (17 MC / 4 MNC, frozen) & 05 (labeled); 01/03/04 not yet present |
| Triager (`prompts/finding-triager/`) | **v1.0 frozen** — 21 recorded runs: 18 against entry 02, in-sample; 3 against entry 05, out-of-sample (see `evals/PROMOTION-PROTOCOL.md`) |
| Narrator / report composer | Specified; **not yet implemented** |
| `references/benchmarks.md` | Referenced by the rubric; **not yet present**  <!-- STALE-OK --> |
| Eval harness (`triage/eval_triage.py`) | **Implemented** — matcher, tiered recall, composite, MNC screens |
| Scripted runner (`triage/run_triager.py`) | **Implemented, not yet run** — the 21 recorded runs to date were executed as interactive agent sessions and carry no model, parameters, or timestamp; this runner calls the API directly and records all three alongside the model's JSON |

The evidence-pointer matcher and `crawl.json` schema check that the harness will
need already ship inside the crawler (`crawler/pointers.py`, `crawler/schema.py`)
so downstream code can reuse them rather than reimplement the contract.
