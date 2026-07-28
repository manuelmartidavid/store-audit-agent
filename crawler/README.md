# Crawler

Deterministic evidence base for one store, implementing `specs/crawler.md` v0.1.

This is the implementation behind a frozen interface. Anything that reads
`crawl.json` codes against the spec, not against this directory — the crawler may
be rewritten freely underneath it. What ships here is one such implementation:
Python for the crawl and the pure layers (distillation, pointers, fingerprint),
with a Node sidecar for Lighthouse because §7 requires the Node API against the
shared browser, which the CLI cannot do.

## Install

```bash
pip install -r requirements.txt        # playwright, pyyaml, pytest
python -m playwright install chromium
npm install                            # lighthouse + axe-core, pinned in package.json
```

## Run

```bash
# By origin
python -m crawler --origin https://example.myshopify.com --out fixtures/

# By golden entry — reads store.source and store.password_env from context.yaml
python -m crawler --context evals/golden/02-sabotaged/context.yaml --out fixtures/02/

# The same store without its password is the blocked case (entry 05)
python -m crawler --context evals/golden/02-sabotaged/context.yaml --no-password --out fixtures/05/
```

The storefront password is read from the env var named by `store.password_env`
(e.g. `TSCC_STOREFRONT_PASSWORD`), never passed on the command line. It never
appears in any output byte — `crawler/redaction.py` greps the written fixtures
for it and deletes them if it finds a leak, before the run can report success.

Useful flags: `--no-lighthouse`, `--no-axe`, `--seed N` (reproducible 404 path),
`--headed` (watch it run), `--node-root DIR` (where `node_modules/` lives).

## Output

Four files in `--out`, per §1:

| File | What |
|---|---|
| `crawl.json` | distilled DOM per template, fingerprint, gate/block state (§4–§6) |
| `lighthouse.json` | standard LHR array, one per captured template (§7) |
| `axe.json` | standard axe-core results, one per captured template (§7) |
| `manifest.yaml` | provenance: tool versions, throttling, per-template status (§8) |

## Layout

```
crawler/
  crawl.py         orchestration — the order of operations, and nothing else
  session.py       Playwright: politeness, the storefront gate, capture
  distill.py       §5 distillation — pure, deterministic, byte-reproducible
  pointers.py      §9 evidence-pointer grammar + the normalized matcher
  fingerprint.py   §4 platform/theme/app detection — pattern-matching only
  discovery.py     §3 template discovery — pure selection over hrefs
  robots.py        §3 robots.txt — fetched first, respected
  axe.py           axe-core injected during the capture visit
  lighthouse.py    driver for the Node sidecar
  schema.py        §4/§6 conformance check, shared with every consumer
  redaction.py     §2 secret hygiene, enforced against written bytes
  manifest.py      §8 manifest emission + hash
  node/lighthouse_runner.mjs   Lighthouse via the Node API, shared browser
  js/dom_walk.js   raw DOM serializer (policy-free) + dropped counts
  js/signals.js    fingerprint signal collection
```

## Tests

```bash
python -m pytest tests/ -q                     # unit + browser integration
CRAWLER_TEST_LIGHTHOUSE=1 python -m pytest tests/ -q   # + the Lighthouse sidecar (~1 min)
```

The pure layers are tested on a bare interpreter via `tests/rawtree.py`, a
Python mirror of the DOM walker. The integration tests drive a real Chromium
against `tests/store_fixture.py`, a local storefront that reproduces the golden
entry 02 defects (div add-to-cart, noindex collection, 50-card grid, injected
instruction) and can be toggled into every branch — password gate, robots
disallow, non-Shopify platform. The live acceptance tests of §10 remain the
acceptance bar; these prove the machinery underneath them.
```
