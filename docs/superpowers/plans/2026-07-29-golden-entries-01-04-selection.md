# Golden entries 01 and 04 — store selection: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two selected golden-entry stores as `context.yaml` files, and the selection criteria as a re-runnable screen, so the 0.3.0 capture wave has both entries ready and can detect if either store changed under us.

**Architecture:** Three deliverables. (1) A behaviour-preserving extraction of `measure.py`'s measurement loop into a reusable `sample_url()`, because the screen needs the samples and not the CLI's exit-code semantics. (2) `planting/screen_candidate.py`, which composes that sampler with a `<head>` probe, `crawler.fingerprint` and `crawler.robots` into hard gates plus a non-gating hygiene report. (3) Two `context.yaml` files and a walker test that checks every golden entry as a set.

**Tech Stack:** Python 3, pytest, stdlib `urllib`/`re` for the probe, existing `crawler.*` modules, Playwright + Lighthouse via `crawler.lighthouse` (already wired).

## Global Constraints

- **Source of truth:** `docs/superpowers/specs/2026-07-29-golden-entries-01-04-selection-design.md`. D1–D6 below refer to its decisions.
- **No capture, no labels.** This plan creates no fixture and no `expected/findings.md`. `eval.fixtures.captured_at` and `manifest_sha256` stay `null` in both new files.
- **Entry 01 store:** `https://theme-dawn-demo.myshopify.com/` — shopify, apparel, CA, CAD, public.
- **Entry 04 store:** `https://www.forestwholefoods.co.uk/` — woocommerce, food-bev, GB, GBP, public.
- **Entry 01 gates:** `gates: [score_range, findings_above_medium]` with `score_min: 90`, `score_max: 100`, `findings_above_medium: 0`. `max_findings: 3` is **set but NOT in `gates`** (D4).
- **Entry 04 gates:** `gates: []` until labeled (D2 closing paragraph).
- **Valid gate names** are exactly `{max_findings, findings_above_medium, score_range}` — `triage/eval_triage.py:632`.
- **`throttling: "mobile-4g-slow"`** in both files. `_schema/context.yaml` requires it identical across all five entries.
- **Boundary discipline:** rubric §1 gives boundary values the LOWER level. LCP exactly 4000 ms is `medium` (passes); CLS exactly 0.25 is `medium` (passes). Gates use strict `>`.
- **`portfolio_safe: false`** on both. The schema permits `true` only with written permission from the owner, which we do not have for either store.
- **Baseline:** 466 tests collected, all green, before this plan starts. `python -m pytest tests/ -q`.
- **Git litter:** the device bridge cannot unlink; if a git command reports "Another git process seems to be running", move `.git/*.lock` into `_to_delete/gitlocks/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `planting/measure.py` *(modify)* | Gains `SampleRun` + `sample_url()`. `main()` becomes arg-parsing, summary and exit codes over that function. No behaviour change. |
| `planting/screen_candidate.py` *(create)* | Golden-entry candidate screen. Pure parsing/verdict layer + a thin network/CLI shell. |
| `tests/test_measure.py` *(modify)* | Gains coverage for the extracted seam. |
| `tests/test_screen_candidate.py` *(create)* | The screen's pure layer: head parsing, noindex, permalinks, perf gates. |
| `evals/golden/01-clean-theme/context.yaml` *(create)* | Entry 01 per D1/D4. |
| `evals/golden/04-woocommerce/context.yaml` *(create)* | Entry 04 per D2/D3. |
| `tests/test_golden_entries.py` *(create)* | Walks every `evals/golden/NN-*/context.yaml` and checks them as a set. Covers entries 03/04/05 automatically as they land. |
| `PROJECT-STATE.md` *(modify)* | Step 10 done; steps 11–12 gain D3 and D6. |

---

### Task 1: Extract `sample_url()` from `measure.main()`

A pure refactor. The screen needs the samples; `main()` needs an exit code. Today the loop that produces samples is welded to the CLI's printing and return values, so there is no way to ask for the numbers without also asking for the process semantics.

**Files:**
- Modify: `planting/measure.py:245-390` (the body of `main()`)
- Test: `tests/test_measure.py`

**Interfaces:**
- Consumes: existing `Sample`, `_extract`, `_origin`, `_is_gate_url`, `Session`, `lighthouse`
- Produces:
  ```python
  @dataclass
  class SampleRun:
      samples: list[Sample]
      failed: int
      gate_leak: bool
      blocked: str | None      # gate kind when blocked at the gate, else None

  def sample_url(url: str, *, runs: int = 1, password: str | None = None,
                 debug_port: int = 9223, node_root: Path | None = None,
                 echo: bool = True) -> SampleRun
  ```

- [ ] **Step 1: Write the failing test**

Add to `tests/test_measure.py`:

```python
# --- sample_url seam --------------------------------------------------------
#
# The browser path cannot run here (no store, no Chrome). What IS pinned is the
# seam itself: that the reusable entry point exists with the shape
# screen_candidate.py codes against, and that SampleRun reports an all-failed
# run honestly rather than as an empty success.

def test_sample_run_reports_no_samples_as_not_ok():
    run = measure.SampleRun(samples=[], failed=3, gate_leak=False, blocked=None)
    assert run.samples == []
    assert run.failed == 3
    assert run.blocked is None


def test_sample_run_carries_the_gate_block_reason():
    run = measure.SampleRun(samples=[], failed=0, gate_leak=False, blocked="password_required")
    assert run.blocked == "password_required"


def test_sample_url_is_callable_with_the_documented_keywords():
    import inspect
    sig = inspect.signature(measure.sample_url)
    assert list(sig.parameters) == [
        "url", "runs", "password", "debug_port", "node_root", "echo",
    ]
    for name in ("runs", "password", "debug_port", "node_root", "echo"):
        assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_measure.py -q -k "sample_run or sample_url"`
Expected: FAIL — `AttributeError: module 'measure' has no attribute 'SampleRun'`

- [ ] **Step 3: Implement the extraction**

In `planting/measure.py`, add after the `Sample` dataclass (around line 78):

```python
@dataclass
class SampleRun:
    """The outcome of sampling one URL N times.

    Separated from `main()` so a caller can have the numbers without also
    inheriting the CLI's exit-code semantics. `screen_candidate.py` needs
    "did LCP stay under 4.0s" — the opposite assertion direction from
    `--expect-cls-min`, which exists to confirm a planted defect EXCEEDS a
    threshold. One measurement path, two verdict layers.
    """

    samples: list["Sample"]
    failed: int
    gate_leak: bool
    blocked: str | None = None
```

Then replace the body of `main()` from `origin = _origin(args.url)` through the end of the per-run `for` loop with a call, and move the loop verbatim into the new function:

```python
def sample_url(url: str, *, runs: int = 1, password: str | None = None,
               debug_port: int = 9223, node_root: Path | None = None,
               echo: bool = True) -> SampleRun:
    """Measure one URL `runs` times, one cold browser per run.

    `echo` prints the instrument banner and per-run block exactly as the CLI
    always has; a caller wanting only the numbers passes False. Everything
    about HOW the measurement is taken — one browser per run, re-mirroring the
    gate cookie, refusing to measure a /password landing — is unchanged and
    stays the single implementation.
    """
    node_root = node_root or Path(__file__).resolve().parents[1]
    origin = _origin(url)
    samples: list[Sample] = []
    failed = 0
    gate_leak = False
    announced = False

    for i in range(runs):
        # ONE BROWSER PER RUN. The sidecar audits with disableStorageReset so the
        # mirrored gate cookie survives (spec section 7) - and a browser kept
        # across runs therefore keeps its HTTP cache too. Run 1 pays for the
        # assets, every run after it reads them back warm, and the result looks
        # like variance while being nothing of the sort: 13.38s then 1.50s then
        # 1.50s is one measurement and two cache hits.
        #
        # A new browser is a new profile and therefore a cold cache. The two
        # cheaper fixes do not work here: Network.clearBrowserCache cannot reach
        # the default context where Lighthouse opens its tabs, and letting
        # Lighthouse reset storage would clear the gate cookie along with the
        # cache and drop every run onto /password.
        with Session(origin, debug_port=debug_port) as session:
            gate = session.open_gate(password)
            if gate.gate == "blocked":
                if echo:
                    print(f"blocked at the gate: {gate.kind} - nothing measured", file=sys.stderr)
                return SampleRun(samples=[], failed=failed, gate_leak=False, blocked=gate.kind)

            if echo and not announced:
                print(f"instrument: lighthouse {lighthouse.version(node_root) or '?'}"
                      f" | {session.browser_version or 'chromium ?'}"
                      f" | sidecar crawler/node/lighthouse_runner.mjs"
                      f" | gate {gate.gate} | runs {runs} | cold cache per run")
                print(f"target: {url}\n")
                announced = True

            # Re-mirror every run. Lighthouse resets origin storage before a
            # navigation run, which can clear the storefront_digest cookie the
            # crawl context established - and then the run silently audits
            # /password instead of the store (MNC-004). Idempotent, and free on
            # a public store, which mirrors zero cookies.
            mirrored = session.mirror_session_to_default()
            if gate.gate == "password_supplied" and not mirrored:
                if echo:
                    print(f"run {i+1}: no cookies mirrored to the default context -"
                          f" the gate cookie is gone, refusing to measure", file=sys.stderr)
                gate_leak = True
                break

            result = lighthouse.run(node_root, debug_port, [("probe", url)])
            if result.status.get("probe") != "ok" or not result.lhrs:
                err = (result.errors or {}).get("probe") or (result.errors or {}).get("*", "unknown")
                if echo:
                    print(f"run {i+1}: lighthouse failed - {err}", file=sys.stderr)
                failed += 1
                continue

            sample = _extract(result.lhrs[0])

            if _is_gate_url(sample.final_url):
                if echo:
                    print(f"run {i+1}: landed on the storefront password page -"
                          f" these numbers describe the gate, not the store (MNC-004)", file=sys.stderr)
                gate_leak = True
                break

            samples.append(sample)
            if echo:
                _echo_run(i + 1, runs, sample)

    return SampleRun(samples=samples, failed=failed, gate_leak=gate_leak, blocked=None)


def _echo_run(index: int, total: int, sample: Sample) -> None:
    """The per-run block, lifted verbatim out of the old loop."""
    print(f"run {index}/{total}")
    print(f"  perf  {sample.perf}")
    if sample.lcp is not None:
        print(f"  LCP   {sample.lcp/1000:.2f}s -> {_side(sample.lcp, 'lcp')}")
    else:
        print("  LCP   n/a")
    if sample.cls is not None:
        print(f"  CLS   {sample.cls:.3f} -> {_side(sample.cls, 'cls')}")
    else:
        print("  CLS   n/a")
    if sample.selector:
        print(f"  LCP element: {sample.selector}")
    if sample.phases:
        parts = " · ".join(f"{k} {v/1000:.2f}s" for k, v in sample.phases.items())
        print(f"  LCP phases: {parts}")
    for url, wire, decoded, mime in sample.images or []:
        tail = url.rsplit("/", 1)[-1].split("?")[0][:48]
        note = f" (decoded {decoded/1024:.0f} KB)" if decoded and abs(decoded - wire) > 10240 else ""
        print(f"  img {wire/1024:7.0f} KB wire  {mime:<12} {tail}{note}")
```

And `main()` keeps everything from `if gate_leak:` onward, now reading from the returned object:

```python
    run = sample_url(args.url, runs=args.runs, password=password,
                     debug_port=args.debug_port, node_root=args.node_root, echo=True)
    if run.blocked:
        return 1
    if run.gate_leak:
        return 1
    samples, failed = run.samples, run.failed
    if not samples:
        print("every run failed - nothing measured", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_measure.py -q`
Expected: PASS, all tests including the pre-existing ones.

- [ ] **Step 5: Verify parity against the live store**

The extraction moved browser code that no unit test reaches, so it gets checked the way `tests/test_measure.py`'s own docstring says that path is checked — by hand.

Run: `python -m planting.measure --no-password --runs 1 "https://theme-dawn-demo.myshopify.com/"`
Expected: the same output shape as before the refactor — an `instrument:` banner, a `target:` line, a `run 1/1` block with `perf`, `LCP`, `CLS`, `LCP element`, `LCP phases` and image lines, then a `--- 1 ok / 1 runs ---` summary. LCP should land near 2.2–2.5s and CLS at 0.000. Exit code 0.

If the numbers differ wildly from the screen recorded in the spec, that is a store change, not a refactor bug — note it and continue; Task 5 records it.

- [ ] **Step 6: Commit**

```bash
git add planting/measure.py tests/test_measure.py
git commit -m "refactor(measure): extract sample_url() from main()

The screen needs the samples without the CLI's exit-code semantics, and
--expect-cls-min asserts a value EXCEEDS a threshold (it exists to confirm a
planted defect landed) which is the opposite direction from screening. One
measurement path, two verdict layers.

Behaviour-preserving: the per-run block moved verbatim into _echo_run and the
loop into sample_url. Verified by hand against theme-dawn-demo, since no unit
test reaches the browser path.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The screen's pure layer — head parsing and the indexable gate

**Files:**
- Create: `planting/screen_candidate.py`
- Test: `tests/test_screen_candidate.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet
- Produces:
  ```python
  @dataclass(frozen=True)
  class HeadFacts:
      http_status: int
      title: str | None
      description: str | None
      robots: str | None
      password_form: bool

  @dataclass(frozen=True)
  class Gate:
      name: str
      passed: bool
      detail: str

  def parse_head(html: str, http_status: int) -> HeadFacts
  def is_noindex(robots: str | None) -> bool
  def indexable_gate(template: str, facts: HeadFacts) -> Gate
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_screen_candidate.py`:

```python
"""The candidate screen's pure layer — no network, no browser.

Entries 01 and 04 are stores we do not own, so the criteria that selected them
have to be re-runnable before capture (design 2026-07-29 D5). These pin the
parsing and the verdicts; the network and browser paths are exercised by
running the tool, the same split tests/test_measure.py uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planting"))

import screen_candidate as sc  # noqa: E402


# --- parse_head -------------------------------------------------------------

HEAD = """<!doctype html><html><head>
<title>  Bags &ndash; theme-dawn-demo </title>
<meta name="description" content="Organic almonds and cashews">
<meta name="robots" content="noindex, nofollow">
<meta property="og:title" content="ignored">
</head><body></body></html>"""


def test_parse_head_reads_title_description_and_robots():
    facts = sc.parse_head(HEAD, 200)
    assert facts.title == "Bags &ndash; theme-dawn-demo"
    assert facts.description == "Organic almonds and cashews"
    assert facts.robots == "noindex, nofollow"
    assert facts.http_status == 200


def test_parse_head_reports_absent_fields_as_none_not_empty_string():
    facts = sc.parse_head("<html><head><title>x</title></head></html>", 200)
    assert facts.description is None
    assert facts.robots is None


def test_parse_head_treats_an_empty_description_as_absent():
    # broadcast-theme-main serves content="" — an empty description is a missing
    # one, and letting "" through would report hygiene the store does not have.
    facts = sc.parse_head('<head><meta name="description" content=""></head>', 200)
    assert facts.description is None


def test_parse_head_accepts_single_quoted_attributes():
    facts = sc.parse_head("<head><meta name='robots' content='noindex'></head>", 200)
    assert facts.robots == "noindex"


def test_parse_head_detects_a_storefront_password_form():
    html = '<head></head><body><form action="/password"><input type="password" name="p"></form></body>'
    assert sc.parse_head(html, 200).password_form is True


def test_parse_head_does_not_flag_an_ordinary_page_as_gated():
    assert sc.parse_head(HEAD, 200).password_form is False


# --- is_noindex -------------------------------------------------------------

@pytest.mark.parametrize("value", ["noindex", "NOINDEX", "noindex, nofollow",
                                   "  none  ", "index, noindex"])
def test_is_noindex_true(value):
    assert sc.is_noindex(value) is True


@pytest.mark.parametrize("value", [None, "", "index, follow",
                                   "index, follow, max-image-preview:large"])
def test_is_noindex_false(value):
    assert sc.is_noindex(value) is False


def test_is_noindex_treats_none_directive_as_noindex():
    # `none` is shorthand for `noindex, nofollow` and is easy to miss.
    assert sc.is_noindex("none") is True


# --- indexable_gate ---------------------------------------------------------

def test_indexable_gate_fails_on_noindex_and_says_it_is_a_critical():
    facts = sc.parse_head('<head><meta name="robots" content="noindex"></head>', 200)
    gate = sc.indexable_gate("home", facts)
    assert gate.passed is False
    assert gate.name == "indexable:home"
    assert "critical" in gate.detail.lower()


def test_indexable_gate_passes_when_no_robots_meta_present():
    gate = sc.indexable_gate("home", sc.parse_head("<head></head>", 200))
    assert gate.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screen_candidate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_candidate'`

- [ ] **Step 3: Write the implementation**

Create `planting/screen_candidate.py`:

```python
"""Golden-entry candidate screen — is this store still fit to be an eval entry?

    python -m planting.screen_candidate --entry 01
    python -m planting.screen_candidate --entry 04 --runs 3

Entries 01 and 04 are stores we do NOT own (design 2026-07-29, D5). Shopify can
reconfigure the Dawn demo, and Forest Whole Foods can change its theme, between
selection and capture day — and the failure mode is silent. A `noindex`
appearing on entry 01 turns the project's only false-positive test into a store
that correctly emits a `critical`, and nothing downstream would report that as
a selection problem rather than an agent problem.

So the selection criteria live here as code and are re-run immediately before
capture. A failing hard gate is a RE-SELECTION TRIGGER, not a defect to label
around.

HARD GATES — any failure disqualifies the candidate:

    reachable    HTTP 200, and no storefront password form
    indexable    no `meta robots: noindex` on any revenue template  -> a critical
    lcp          LCP <= 4.0s on home/collection/pdp                 -> a high
    cls          CLS <= 0.25 on home/collection/pdp                 -> a high
    platform     crawler.fingerprint agrees with the declared platform
    permalinks   WooCommerce only: default /shop|/product-category|/product

RECORDED, never disqualifying:

    robots       which templates robots.txt allows, and any Crawl-delay
    hygiene      title and meta-description presence per template

The hygiene block is deliberately NOT a gate. The defects it finds are real and
belong in the entry's labels — the person writing `expected/findings.md` needs
to know what the store already had before the agent said anything. Screening
them out would mean hunting for a store that flatters the agent, which is the
store-shopping failure this project has warned about twice.

Boundary discipline follows rubric §1: boundary values take the LOWER level, so
LCP exactly 4000 ms and CLS exactly 0.25 both PASS. Gates compare strictly.

This writes nothing. It builds no fixture and no labels.

Exit codes match measure.py: 0 = every hard gate passed · 1 = operational
failure · 2 = a hard gate failed (re-selection trigger).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- head parsing -----------------------------------------------------------

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"' r"|([\w:-]+)\s*=\s*'([^']*)'")
_PASSWORD_INPUT = re.compile(r'<input[^>]+type\s*=\s*["\']password["\']', re.I)

#: `none` is shorthand for `noindex, nofollow`. Easy to miss, same consequence.
_NOINDEX_TOKENS = {"noindex", "none"}


@dataclass(frozen=True)
class HeadFacts:
    """What one template's document says about itself."""

    http_status: int
    title: str | None
    description: str | None
    robots: str | None
    password_form: bool


@dataclass(frozen=True)
class Gate:
    """One screen verdict. `passed is False` disqualifies the candidate."""

    name: str
    passed: bool
    detail: str


def _attrs(tag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR.finditer(tag):
        key = (m.group(1) or m.group(3) or "").lower()
        out[key] = m.group(2) if m.group(2) is not None else (m.group(4) or "")
    return out


def parse_head(html: str, http_status: int) -> HeadFacts:
    """Read the head facts a screen decision depends on.

    Regex rather than a parser because this reads four known fields out of a
    document we do not otherwise trust, and adding a parser dependency to a
    pre-capture probe buys nothing. An empty `content=""` is reported as absent:
    broadcast-theme-main serves exactly that, and treating it as present would
    report hygiene the store does not have.
    """
    title_match = _TITLE.search(html)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None

    description = robots = None
    for tag in _META.finditer(html):
        attrs = _attrs(tag.group(0))
        name = (attrs.get("name") or "").lower()
        content = (attrs.get("content") or "").strip()
        if name == "description":
            description = content or None
        elif name == "robots":
            robots = content or None

    return HeadFacts(
        http_status=http_status,
        title=title or None,
        description=description,
        robots=robots,
        password_form=bool(_PASSWORD_INPUT.search(html)),
    )


def is_noindex(robots: str | None) -> bool:
    """True when a robots directive keeps the page out of the index."""
    if not robots:
        return False
    tokens = {t.strip().lower() for t in robots.split(",")}
    return bool(tokens & _NOINDEX_TOKENS)


def indexable_gate(template: str, facts: HeadFacts) -> Gate:
    """A `noindex` on a revenue template is a correct `critical` (rubric §1).

    Four of the nine theme demos screened on 2026-07-29 failed here. It is not
    bad luck: demo stores are deliberately deindexed so they do not compete
    with real merchant stores in search.
    """
    if is_noindex(facts.robots):
        return Gate(
            name=f"indexable:{template}",
            passed=False,
            detail=(f"meta robots={facts.robots!r} — the audit would correctly emit a "
                    f"critical (blocks indexing of a revenue template, rubric §1)"),
        )
    return Gate(name=f"indexable:{template}", passed=True,
                detail=f"meta robots={facts.robots!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screen_candidate.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add planting/screen_candidate.py tests/test_screen_candidate.py
git commit -m "feat(screen): head parsing and the indexable gate

Four of nine theme demos screened on 2026-07-29 are noindex sitewide, which is
a correct critical rather than bad luck — demo stores are deliberately
deindexed. That gate is the one that decided entry 01.

Empty content=\"\" is reported absent: broadcast-theme-main serves exactly that.
'none' counts as noindex; it is shorthand for noindex,nofollow.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Permalink and performance gates

**Files:**
- Modify: `planting/screen_candidate.py`
- Test: `tests/test_screen_candidate.py`

**Interfaces:**
- Consumes: `Gate` and `HeadFacts` from Task 2; `measure.Sample` and `measure.SampleRun` from Task 1
- Produces:
  ```python
  def permalink_gate(html: str, host: str, platform: str) -> Gate
  def perf_gates(template: str, run: "SampleRun") -> list[Gate]
  ```

- [ ] **Step 1: Write the failing test**

Append to `tests/test_screen_candidate.py`:

```python
# --- permalink_gate ---------------------------------------------------------

WOO_DEFAULT = """<body>
<a href="/shop/">Shop</a>
<a href="https://ex.test/product-category/bakery/">Bakery</a>
<a href="https://ex.test/product/organic-almonds/">Almonds</a>
<a href="/cart/">Cart</a>
</body>"""

WOO_CUSTOM = """<body>
<a href="/store/">Store</a>
<a href="/store/bakery/">Bakery</a>
<a href="/store/bakery/organic-almonds/">Almonds</a>
</body>"""


def test_permalink_gate_passes_on_default_woocommerce_urls():
    gate = sc.permalink_gate(WOO_DEFAULT, "ex.test", "woocommerce")
    assert gate.passed is True


def test_permalink_gate_fails_on_customised_permalinks():
    gate = sc.permalink_gate(WOO_CUSTOM, "ex.test", "woocommerce")
    assert gate.passed is False
    assert "discovery" in gate.detail.lower()


def test_permalink_gate_accepts_product_category_without_a_shop_root():
    # offermanwoodshop.com exposes /product-category/ but no /shop/ — discovery
    # needs ONE default collection URL, not both.
    html = '<a href="/product-category/hearth/">Hearth</a>'
    assert sc.permalink_gate(html, "ex.test", "woocommerce").passed is True


def test_permalink_gate_does_not_require_product_links_on_home():
    # Discovery finds the PDP from the COLLECTION page, not from home
    # (specs/crawler.md §3). The first screening pass got this wrong and
    # disqualified offermanwoodshop for it.
    html = '<a href="/shop/">Shop</a>'
    assert sc.permalink_gate(html, "ex.test", "woocommerce").passed is True


def test_permalink_gate_is_not_applicable_to_shopify():
    gate = sc.permalink_gate("<body></body>", "ex.test", "shopify")
    assert gate.passed is True
    assert "n/a" in gate.detail.lower()


# --- perf_gates -------------------------------------------------------------

def _run(*pairs):
    samples = [measure_Sample(lcp=lcp, cls=cls) for lcp, cls in pairs]
    return sc.SampleRunLike(samples=samples, failed=0, gate_leak=False, blocked=None)


def test_perf_gates_pass_below_the_thresholds():
    gates = sc.perf_gates("home", _run((2420.0, 0.0), (2430.0, 0.0)))
    assert all(g.passed for g in gates)


def test_perf_gates_fail_when_any_run_exceeds_lcp_4s():
    # EVERY run must hold. A median under the line with one run over it is the
    # "aim has not landed" case measure.py already refuses to call a pass.
    gates = sc.perf_gates("home", _run((3900.0, 0.0), (4950.0, 0.0)))
    lcp = next(g for g in gates if g.name.startswith("lcp"))
    assert lcp.passed is False
    assert "high" in lcp.detail.lower()


def test_perf_gates_pass_at_exactly_the_boundary():
    # rubric §1: boundary values take the LOWER level. 4000ms is medium.
    gates = sc.perf_gates("home", _run((4000.0, 0.25)))
    assert all(g.passed for g in gates)


def test_perf_gates_fail_on_cls_above_the_threshold():
    gates = sc.perf_gates("pdp", _run((2000.0, 0.31)))
    cls = next(g for g in gates if g.name.startswith("cls"))
    assert cls.passed is False


def test_perf_gates_fail_when_nothing_was_measured():
    # An empty sample list is an operational failure, not a silent pass — the
    # exact shape eval_triage's vacuous-gate bug took.
    gates = sc.perf_gates("home", sc.SampleRunLike(samples=[], failed=3,
                                                   gate_leak=False, blocked=None))
    assert all(g.passed is False for g in gates)
```

Add this helper near the top of the test file, under the imports:

```python
# measure.Sample carries fields the perf gates never read. Building one here
# keeps these tests independent of that dataclass's full shape.
class measure_Sample:  # noqa: N801 - a stand-in, named for what it stands in for
    def __init__(self, lcp: float | None, cls: float | None):
        self.lcp = lcp
        self.cls = cls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screen_candidate.py -q -k "permalink or perf"`
Expected: FAIL — `AttributeError: module 'screen_candidate' has no attribute 'permalink_gate'`

- [ ] **Step 3: Write the implementation**

Append to `planting/screen_candidate.py`:

```python
# --- permalinks -------------------------------------------------------------

from typing import Protocol  # noqa: E402  (kept beside the code that needs it)
from urllib.parse import urlparse  # noqa: E402

_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_WOO_COLLECTION = re.compile(r"^/(shop|product-category/[^/]+)/?$", re.I)


class SampleRunLike(Protocol):
    """The slice of `measure.SampleRun` the perf gates read.

    Declared structurally so this module does not import the browser stack to
    make a verdict about numbers. `measure.SampleRun` satisfies it.
    """

    samples: list
    failed: int
    gate_leak: bool
    blocked: str | None


def permalink_gate(html: str, host: str, platform: str) -> Gate:
    """WooCommerce entries must use DEFAULT permalinks, or discovery cannot find them.

    The 0.3.0 discovery table (design D3) keys on `/shop`,
    `/product-category/{slug}` and `/product/{slug}`. A store on customised
    permalinks (`/store/{cat}/{product}`) is a hard disqualifier for this entry
    — not a defect in the store, and not something to route around with a pin,
    because entry 04 exists to exercise the non-Shopify discovery path.

    Only ONE default collection URL is required. `offermanwoodshop.com` exposes
    `/product-category/` and no `/shop/`, and discovery needs either. Product
    links are NOT required on home: discovery reaches the PDP from the
    collection page (specs/crawler.md §3).
    """
    if platform != "woocommerce":
        return Gate(name="permalinks", passed=True,
                    detail=f"n/a — platform is {platform}")

    paths = []
    for href in _HREF.findall(html):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != host:
            continue
        paths.append(parsed.path or href)

    collections = sorted({p for p in paths if _WOO_COLLECTION.match(p)})
    if collections:
        return Gate(name="permalinks", passed=True,
                    detail=f"default collection URL present: {collections[0]}")
    return Gate(
        name="permalinks",
        passed=False,
        detail=("no /shop or /product-category/{slug} link on home — discovery "
                "cannot reach a collection, so this store needs customised "
                "permalink support that entry 04 is not the place to build"),
    )


# --- performance ------------------------------------------------------------

#: Imported lazily inside the function so the pure layer stays importable on a
#: bare interpreter, the way crawler/__init__.py keeps Playwright behind lazy
#: imports.
def _thresholds() -> tuple[float, float]:
    import measure
    return measure.LCP_HIGH_MS, measure.CLS_HIGH


def perf_gates(template: str, run: SampleRunLike) -> list[Gate]:
    """LCP and CLS must stay off the `high` side on EVERY run.

    Every run, not the median: a median under the line with one run over it is
    exactly what measure.py already refuses to call a pass ("the aim has not
    landed - this is noise, not a defect"). Screening inherits that discipline
    because a fixture is captured once, and it can be captured on the bad run.

    An empty sample list fails both gates. A gate that passes having evaluated
    nothing is the vacuous-pass shape step 8 found twice in this repo.
    """
    lcp_high, cls_high = _thresholds()
    lcps = [s.lcp for s in run.samples if getattr(s, "lcp", None) is not None]
    clss = [s.cls for s in run.samples if getattr(s, "cls", None) is not None]

    gates: list[Gate] = []

    if not lcps:
        gates.append(Gate(f"lcp:{template}", False,
                          "nothing measured — treated as a failure, not a pass"))
    else:
        over = [v for v in lcps if v > lcp_high]
        gates.append(Gate(
            f"lcp:{template}", not over,
            (f"{min(lcps)/1000:.2f}–{max(lcps)/1000:.2f}s over {len(lcps)} run(s)"
             + (f"; {len(over)} on the HIGH side (> {lcp_high/1000:.1f}s)" if over else ""))))

    if not clss:
        gates.append(Gate(f"cls:{template}", False,
                          "nothing measured — treated as a failure, not a pass"))
    else:
        over = [v for v in clss if v > cls_high]
        gates.append(Gate(
            f"cls:{template}", not over,
            (f"{min(clss):.3f}–{max(clss):.3f} over {len(clss)} run(s)"
             + (f"; {len(over)} above {cls_high}" if over else ""))))

    return gates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screen_candidate.py -q`
Expected: PASS, 23 tests.

- [ ] **Step 5: Commit**

```bash
git add planting/screen_candidate.py tests/test_screen_candidate.py
git commit -m "feat(screen): permalink and performance gates

Perf gates require EVERY run to hold, not the median — measure.py already
refuses to call a straddling spread a pass, and a fixture is captured once, on
a run that could be the bad one. An empty sample list fails rather than passes
vacuously.

permalink_gate needs only ONE default collection URL and does not require
product links on home: discovery reaches the PDP from the collection page
(specs/crawler.md §3). The first screening pass got that wrong.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Wire the CLI and run it against both stores

**Files:**
- Modify: `planting/screen_candidate.py`
- Test: manual run against both live stores

**Interfaces:**
- Consumes: `parse_head`, `indexable_gate`, `permalink_gate`, `perf_gates`, `measure.sample_url`, `crawler.robots.Robots`
- Produces: `main(argv: list[str] | None = None) -> int`, and `ENTRIES: dict[str, dict]` naming the two selected stores

- [ ] **Step 1: Add the entry table and CLI**

Append to `planting/screen_candidate.py`:

```python
# --- the selected entries ---------------------------------------------------

#: The stores selected on 2026-07-29 (design D1, D2). Keyed by eval id so the
#: screen can be re-run as `--entry 01` without anyone retyping a URL, and so
#: the URLs live in exactly one place alongside the gates that chose them.
ENTRIES: dict[str, dict] = {
    "01": {
        "origin": "https://theme-dawn-demo.myshopify.com",
        "platform": "shopify",
        "templates": {
            "home": "/",
            "collection": "/collections/bags",
            "pdp": "/products/small-convertible-flex-bag-cappuccino",
            "cart": "/cart",
            "search": "/search?q=a",
        },
    },
    "04": {
        "origin": "https://www.forestwholefoods.co.uk",
        "platform": "woocommerce",
        "templates": {
            "home": "/",
            "collection": "/shop/",
            "pdp": "/product/organic-almonds/",
            "cart": "/cart/",
            "search": "/?s=a",
        },
    },
}

#: Gates run on revenue templates only (rubric §1: home/collection/pdp/cart).
#: cart is not measured for LCP — it is behind an empty-cart redirect on many
#: stores and its LCP says more about that than about the theme.
_PERF_TEMPLATES = ("home", "collection", "pdp")


def _fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    """One polite GET. Identifying UA, matching specs/crawler.md §3 conduct."""
    import gzip
    import urllib.error
    import urllib.request

    from crawler.config import ROBOTS_UA

    req = urllib.request.Request(
        url, headers={"User-Agent": ROBOTS_UA, "Accept-Encoding": "gzip",
                      "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entry", choices=sorted(ENTRIES), required=True)
    parser.add_argument("--runs", type=int, default=2,
                        help="Lighthouse runs per revenue template (default 2)")
    parser.add_argument("--skip-perf", action="store_true",
                        help="Head and permalink gates only — no browser")
    parser.add_argument("--debug-port", type=int, default=9223)
    args = parser.parse_args(argv)

    entry = ENTRIES[args.entry]
    origin, platform = entry["origin"], entry["platform"]
    print(f"screening entry {args.entry}: {origin}  (declared platform: {platform})\n")

    gates: list[Gate] = []
    hygiene: list[str] = []
    home_html = ""

    # --- head probe, one polite GET per template ---------------------------
    for i, (template, path) in enumerate(entry["templates"].items()):
        if i:
            time.sleep(1.5)
        url = origin + path
        status, html = _fetch(url)
        if template == "home":
            home_html = html
        if status != 200 or not html:
            gates.append(Gate(f"reachable:{template}", False, f"HTTP {status}"))
            continue
        facts = parse_head(html, status)
        gates.append(Gate(f"reachable:{template}", not facts.password_form,
                          f"HTTP {status}"
                          + (" — storefront password form present" if facts.password_form else "")))
        gates.append(indexable_gate(template, facts))
        hygiene.append(f"  {template:<11} title={facts.title!r}"
                       f"  description={'present' if facts.description else 'ABSENT'}")

    gates.append(permalink_gate(home_html, urlparse(origin).netloc, platform))

    # --- robots, recorded not gated ----------------------------------------
    status, body = _fetch(origin + "/robots.txt")
    notes: list[str] = []
    if status == 200 and body:
        from crawler.robots import Robots
        robots = Robots.parse(body)
        blocked = [t for t, p in entry["templates"].items() if not robots.allows(origin + p)]
        notes.append(f"robots.txt blocks: {blocked or 'nothing probed'}")
        delay = re.search(r"(?im)^\s*crawl-delay\s*:\s*([\d.]+)", body)
        if delay:
            notes.append(f"robots.txt declares Crawl-delay: {delay.group(1)}"
                         f" — conduct requires honouring it (design D6)")
    else:
        notes.append(f"robots.txt: HTTP {status}")

    # --- performance --------------------------------------------------------
    if not args.skip_perf:
        import measure
        for template in _PERF_TEMPLATES:
            path = entry["templates"].get(template)
            if not path:
                continue
            run = measure.sample_url(origin + path, runs=args.runs,
                                     password=None, debug_port=args.debug_port,
                                     echo=False)
            if run.blocked:
                print(f"blocked at the gate on {template}: {run.blocked}", file=sys.stderr)
                return 1
            gates.extend(perf_gates(template, run))

    # --- report -------------------------------------------------------------
    print("gates")
    for gate in gates:
        print(f"  [{'PASS' if gate.passed else 'FAIL'}] {gate.name:<20} {gate.detail}")
    print("\nseo hygiene (recorded, NOT a gate — these become labels)")
    for line in hygiene:
        print(line)
    print("\nnotes")
    for note in notes:
        print(f"  {note}")

    failed = [g for g in gates if not g.passed]
    if failed:
        print(f"\nRE-SELECTION TRIGGER — {len(failed)} hard gate(s) failed: "
              f"{', '.join(g.name for g in failed)}")
        return 2
    print(f"\nall {len(gates)} hard gates passed — entry {args.entry} is fit to capture")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
```

Add `import sys` to the module's top-level imports (it is used in `main`).

- [ ] **Step 2: Run the head-only screen for both entries**

Run: `python -m planting.screen_candidate --entry 01 --skip-perf`
Expected: exit 0. Every `reachable:*` and `indexable:*` gate PASS, `permalinks` PASS (`n/a — platform is shopify`). Hygiene shows `home title='theme-dawn-demo' description=ABSENT`, `pdp description=present`.

Run: `python -m planting.screen_candidate --entry 04 --skip-perf`
Expected: exit 0. All gates PASS. Notes report `Crawl-delay: 10`.

- [ ] **Step 3: Run the full screen for entry 01**

Run: `python -m planting.screen_candidate --entry 01 --runs 2`
Expected: exit 0, with `lcp:home`, `lcp:collection`, `lcp:pdp`, and three `cls:*` gates all PASS. LCP should land in the 2.1–3.2s range recorded in the spec.

If a gate FAILS, **stop and report** — that is a re-selection trigger and it means the store changed since 2026-07-29. Do not adjust the gate to fit.

- [ ] **Step 4: Run the full screen for entry 04**

Run: `python -m planting.screen_candidate --entry 04 --runs 2`
Expected: exit 0 or 2 — entry 04's performance has **not** been measured before, so this is its first reading. A `high` LCP on a real merchant store is normal and is **not** a disqualifier for entry 04, because entry 04 is not the false-positive test — only entry 01 carries rubric §5's bar.

Record the numbers. If entry 04 fails a perf gate, note it and continue; Task 6 records that its perf gates are advisory. Do not change the selection.

- [ ] **Step 5: Commit**

```bash
git add planting/screen_candidate.py
git commit -m "feat(screen): CLI, entry table, robots and hygiene reporting

--entry 01|04 re-runs the exact criteria that selected each store, so a store
changing under us before capture is a loud re-selection trigger rather than a
silent relabelling. Writes nothing.

SEO hygiene is reported and deliberately NOT gated: those defects are real and
belong in the entry's labels. Gating them would mean hunting for a store that
flatters the agent.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Entry 01 `context.yaml`

**Files:**
- Create: `evals/golden/01-clean-theme/context.yaml`
- Test: covered by Task 7's walker

**Interfaces:**
- Consumes: nothing
- Produces: a golden entry directory `evals/golden/01-clean-theme/`

- [ ] **Step 1: Write the file**

```yaml
# Golden entry 01 — clean theme demo (the false-positive test)
#
# Store: Shopify's Dawn reference-theme demo. Selected 2026-07-29 as the sole
# survivor of a nine-candidate screen — design
# docs/superpowers/specs/2026-07-29-golden-entries-01-04-selection-design.md.
# Four candidates were noindex sitewide (a correct `critical`) and four more
# exceeded LCP 4.0s on mobile-4g-slow (a correct `high`).
#
# WE DO NOT OWN THIS STORE. Shopify can reconfigure it between now and capture.
# Re-run `python -m planting.screen_candidate --entry 01` immediately before
# capturing; a failing gate is a re-selection trigger, not a defect to label
# around. crawler/archive.py runs at capture — for an unowned store the archive
# is the only recoverable copy.

store:
  platform: shopify
  vertical: apparel          # inferred from the Mlouye sample catalog (bags,
                             # footwear). Not stated by the store.
  market: CA                 # Shopify.country = CA, observed 2026-07-29
  currency: CAD              # observed 2026-07-29
  password_env: null         # public, no gate

  # Null because we do not own the store, not as a contrivance. There is no AOV
  # to know. Entry 02 is the entry that tests correct quantification WITH a
  # declared number; entry 04 carries the labeled fabrication trap.
  aov: null
  monthly_sessions: null
  mobile_share: null

  # Not set. The screen saw "13 results found for a", which is a lower bound on
  # a search, not a catalog count. A wrong band in the prompt is worse than an
  # absent one.
  catalog_size: null

  notes: >
    Reference storefront for Shopify's Dawn theme, merchandised with a sample
    catalog of designer handbags and footwear. Not a trading business: the
    product pages state that it is a demonstration store.

eval:
  id: "01"
  path_under_test: full_shopify
  access: public

  fixtures:
    # NOT YET CAPTURED. Filled in by the 0.3.0 capture wave (PROJECT-STATE
    # step 12). The screen below is a pre-check, not a capture.
    captured_at: null
    source: "https://theme-dawn-demo.myshopify.com/"
    crawler_version: null
    lighthouse_version: null
    axe_core_version: null
    manifest_sha256: null
    throttling: "mobile-4g-slow"     # identical across all five entries
    templates_captured: []

    # Pinned because we do not own the store: its merchandising can change, and
    # "first product in the collection" raced the cache on entry 02 badly enough
    # to need decision 15. Same reasoning, stronger case.
    targets:
      collection: "https://theme-dawn-demo.myshopify.com/collections/bags"
      pdp: "https://theme-dawn-demo.myshopify.com/products/small-convertible-flex-bag-cappuccino"

  expect:
    # Rubric §5's false-positive pass condition, declared BEFORE capture so this
    # entry's grader exists before its answers do (step 8's rule; entry 02's
    # gates were left empty precisely because its answers already existed).
    score: null                 # no labels yet — set when findings.md is written
    score_min: 90               # rubric §5
    score_max: 100
    band: "Healthy"             # 85+ per rubric §4
    status: "ASSESSED"
    findings_above_medium: 0    # rubric §5
    categories_required: []     # a clean store owes no category a finding

    # SET BUT DELIBERATELY NOT GATED — design D4.
    #
    # The 2026-07-29 screen already found real defects on this store: no meta
    # description on home/collection/cart/search, home's <title> being the raw
    # store handle `theme-dawn-demo`, and a PDP LCP in the `medium` band. A
    # CORRECT audit plausibly emits 3-5 findings.
    #
    # Of §5's three conditions, `score >= 90` and `none above medium` are
    # false-positive bars — they fail when the agent invents severity. `<= 3` is
    # a volume bar, and a store with four real medium defects fails it by being
    # audited correctly. Gating it would make this entry report a precision
    # failure that is actually a store fact.
    #
    # So it is measured and printed on every run, and the gap between 3 and the
    # actual is the evidence for whether §5's ceiling needs recalibrating.
    # Do not move this into `gates` without that argument.
    max_findings: 3

    gates: [score_range, findings_above_medium]

  # Shopify's own public marketing asset, but the schema permits `true` only
  # with written permission from the owner, and we have none.
  portfolio_safe: false
```

- [ ] **Step 2: Verify it parses and its gates validate**

Run:
```bash
python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('evals/golden/01-clean-theme/context.yaml').read_text(encoding='utf-8'))
e = d['eval']['expect']
print('gates:', e['gates'])
print('score_min/max:', e['score_min'], e['score_max'])
print('above_medium:', e['findings_above_medium'])
print('max_findings (ungated):', e['max_findings'])
assert set(e['gates']) == {'score_range', 'findings_above_medium'}
assert e['score_min'] is not None and e['score_max'] is not None
assert e['findings_above_medium'] is not None
print('OK')
"
```
Expected: prints the values and `OK`.

- [ ] **Step 3: Commit**

```bash
git add evals/golden/01-clean-theme/context.yaml
git commit -m "feat(evals): golden entry 01 — Dawn theme demo

Sole survivor of a nine-candidate screen (design D1). The project's first
out-of-sample precision measurement, and the first run of rubric §5's
false-positive pass condition.

Gates score_range and findings_above_medium, declared before capture so the
grader exists before the answers. max_findings is set to §5's 3 but left
UNGATED: the screen already found real defects (no meta description on four
templates, home title = raw store handle, PDP LCP in the medium band), so a
correct audit plausibly emits 3-5 findings and the count would fail on true
positives while the two false-positive bars hold.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Entry 04 `context.yaml`

**Files:**
- Create: `evals/golden/04-woocommerce/context.yaml`
- Test: covered by Task 7's walker

**Interfaces:**
- Consumes: nothing
- Produces: a golden entry directory `evals/golden/04-woocommerce/`

- [ ] **Step 1: Write the file**

```yaml
# Golden entry 04 — WooCommerce, reduced path, null-AOV trap
#
# Store: Forest Whole Foods, a UK organic wholefoods SMB on WooCommerce with
# DEFAULT permalinks. Selected 2026-07-29 — design
# docs/superpowers/specs/2026-07-29-golden-entries-01-04-selection-design.md.
#
# Nalgene was the alternative and was rejected: its robots.txt disallows /cart/,
# so a revenue template would drop out and conflate "reduced because
# WooCommerce" with "reduced because robots" — the two things this entry has to
# keep separable.
#
# BLOCKED ON TWO CRAWLER CHANGES, both in the 0.3.0 wave:
#   D3  platform-generic discovery. Today discovery is hardcoded to Shopify URL
#       conventions, so this store yields collection, pdp and search `absent`.
#   D6  robots.txt Crawl-delay. This store declares 10s; robots.py parses
#       allow/disallow only. Every prior entry is a store we own, so this has
#       never bound — brief §5 conduct is non-negotiable for one we do not.
#
# WE DO NOT OWN THIS STORE. Same re-screen obligation as entry 01:
# `python -m planting.screen_candidate --entry 04` immediately before capture.

store:
  platform: woocommerce
  vertical: food-bev
  market: GB
  currency: GBP              # observed 2026-07-29
  password_env: null         # public, no gate

  # THE TRAP, and it is honest rather than contrived: we do not own this store,
  # so there is no AOV to know. A null here forbids the narrator every number
  # (schema: "Entries for stores you don't own should keep aov null
  # deliberately — that is the fabrication trap, not an accident of incomplete
  # labeling"). Entry 02 tests the positive case with aov 85 CAD.
  aov: null
  monthly_sessions: null
  mobile_share: null
  catalog_size: null

  notes: >
    UK retailer of organic wholefoods — nuts, seeds, dried fruit, flours and
    store-cupboard staples — selling to domestic consumers. Independent
    business, not a marketplace seller.

eval:
  id: "04"
  path_under_test: reduced
  access: public

  fixtures:
    # NOT YET CAPTURED, and not capturable until D3 and D6 land.
    captured_at: null
    source: "https://www.forestwholefoods.co.uk/"
    crawler_version: null      # will be >= 0.3.0 — D3 and D6 are prerequisites
    lighthouse_version: null
    axe_core_version: null
    manifest_sha256: null
    throttling: "mobile-4g-slow"     # identical across all five entries
    templates_captured: []

    # Pinned for the same reason as entry 01: an unowned store's merchandising
    # is not ours to hold still. `/shop/` is the default WooCommerce collection
    # root and is stable in a way "first category in the nav" is not.
    targets:
      collection: "https://www.forestwholefoods.co.uk/shop/"
      pdp: "https://www.forestwholefoods.co.uk/product/organic-almonds/"

  expect:
    # EMPTY UNTIL LABELED, and that is not inconsistent with entry 01.
    #
    # Entry 01 can declare gates before capture because rubric §5 supplies its
    # bar in advance. Entry 04 has no pre-existing bar, so declaring one now
    # would mean inventing a precision expectation for a store nobody has
    # measured — the store-shopping failure in reverse. Set these when
    # expected/findings.md is written, from the fixture.
    score: null
    score_min: null
    score_max: null
    band: null
    status: "ASSESSED"        # public and reachable; INACCESSIBLE only if blocked
    max_findings: 25          # rubric §5 global ceiling
    findings_above_medium: null
    categories_required: []
    gates: []

  portfolio_safe: false        # a real merchant's store, and not ours to publish
```

- [ ] **Step 2: Verify it parses**

Run:
```bash
python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('evals/golden/04-woocommerce/context.yaml').read_text(encoding='utf-8'))
assert d['store']['platform'] == 'woocommerce'
assert d['store']['aov'] is None, 'the null-AOV trap must stay null'
assert d['eval']['path_under_test'] == 'reduced'
assert d['eval']['expect']['gates'] == []
print('OK', d['eval']['fixtures']['source'])
"
```
Expected: `OK https://www.forestwholefoods.co.uk/`

- [ ] **Step 3: Commit**

```bash
git add evals/golden/04-woocommerce/context.yaml
git commit -m "feat(evals): golden entry 04 — Forest Whole Foods (WooCommerce)

UK organic wholefoods SMB on default WooCommerce permalinks. Nalgene rejected
for disallowing /cart/ in robots.txt, which would conflate 'reduced because
WooCommerce' with 'reduced because robots'.

aov: null is the fabrication trap and is honest here — we do not own the store,
so there is no AOV to know.

Blocked on two 0.3.0 crawler changes recorded in the file: platform-generic
discovery (D3) and robots Crawl-delay (D6).

gates: [] until labeled — entry 01 can declare gates pre-capture because §5
supplies its bar; entry 04 has no pre-existing bar, so declaring one would
invent a precision expectation for an unmeasured store.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Golden-entry walker test

No test checks the golden entries as a set today. The failures it catches are all silent ones: a gate name typo passes vacuously, a declared gate with no value was a silent no-op until step 8 fixed it in the scorer, and the schema's "throttling must be identical across all five entries" is enforced nowhere.

**Files:**
- Create: `tests/test_golden_entries.py`

**Interfaces:**
- Consumes: `triage/eval_triage.py`'s `_KNOWN_GATES`
- Produces: nothing importable

- [ ] **Step 1: Write the failing test**

Create `tests/test_golden_entries.py`:

```python
"""Every golden entry's context.yaml, checked as a set.

The entries are checked individually all over this suite; nothing checks them
against EACH OTHER, and the schema has cross-entry rules — `throttling` "must be
identical across all five entries" is one, and it is enforced nowhere.

The rest are the silent failures: a typo in `gates:` passes vacuously (the same
class eval_triage.py:660 raises on), a declared gate with no value was a silent
no-op until step 8, and `id` drifting from the directory prefix would send a
run's provenance to the wrong entry.

Parametrized over the directory glob, so entries 03 and any later ones are
covered the moment they land rather than when somebody remembers to add them.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)

ENTRIES = sorted(GOLDEN.glob("[0-9][0-9]-*/context.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_the_glob_found_the_entries():
    # A walker that silently matches nothing is the vacuous pass it exists to
    # prevent. Entries 01, 02, 04 and 05 exist as of 2026-07-29.
    assert len(ENTRIES) >= 4, [p.parent.name for p in ENTRIES]


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_has_both_blocks(path: Path):
    data = _load(path)
    assert "store" in data, "the block rendered into the prompt"
    assert "eval" in data, "the harness-only block"


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_eval_id_matches_the_directory_prefix(path: Path):
    prefix = path.parent.name.split("-")[0]
    assert _load(path)["eval"]["id"] == prefix


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_gates_are_known_names(path: Path):
    gates = set(_load(path)["eval"]["expect"].get("gates") or [])
    unknown = gates - eval_triage._KNOWN_GATES
    assert not unknown, f"{sorted(unknown)} is not a gate; known: {sorted(eval_triage._KNOWN_GATES)}"


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_declared_gates_have_values(path: Path):
    """A gate with no value is a green run that measured nothing."""
    expect = _load(path)["eval"]["expect"]
    for gate in expect.get("gates") or []:
        if gate == "score_range":
            assert expect.get("score_min") is not None, "score_range needs score_min"
            assert expect.get("score_max") is not None, "score_range needs score_max"
        else:
            assert expect.get(gate) is not None, f"{gate} declared with no value"


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_password_env_names_a_variable_and_never_holds_a_value(path: Path):
    """`password_env` is a NAME. A value here would commit a secret."""
    value = _load(path)["store"].get("password_env")
    if value is not None:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", value), f"{value!r} is not an env var name"


def test_throttling_is_identical_across_every_entry():
    """_schema/context.yaml: "must be identical across all five entries"."""
    profiles = {p.parent.name: (_load(p)["eval"]["fixtures"] or {}).get("throttling")
                for p in ENTRIES}
    assert len(set(profiles.values())) == 1, profiles
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_golden_entries.py -q`
Expected: PASS. If `test_throttling_is_identical_across_every_entry` fails, **do not change the new files to match** — read the failure: it names which entry disagrees, and entries 02 and 05 both already declare `mobile-4g-slow`.

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Collected count should be **466 + the new tests** (roughly 500); a *lower* number than 466 means something regressed at collection.

- [ ] **Step 4: Commit**

```bash
git add tests/test_golden_entries.py
git commit -m "test: walk every golden entry's context.yaml as a set

Nothing checked the entries against each other. The schema's 'throttling must
be identical across all five entries' was enforced nowhere, a gate-name typo
passes vacuously, and a declared gate with no value was a silent no-op until
step 8 fixed it in the scorer.

Parametrized over the directory glob, so entry 03 and later ones are covered
when they land rather than when somebody remembers.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: PROJECT-STATE update

**Files:**
- Modify: `PROJECT-STATE.md` — the header block, "Next steps" items 10–12, and the "Open questions" section

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: Update the header block**

Replace the `updated:` line with:

```
    updated:  2026-07-29 (v1.0 frozen · repo consolidated · entry 05 first-run ·
              step 8 measurement hardening · pushed to a private GitHub remote ·
              step 8 merged to main · decision 30 → rubric v0.5, prompt v1.1 ·
              step 9 impact-narrator · step 10 entries 01/04 selected)
```

- [ ] **Step 2: Replace "Next steps" item 10**

Replace the existing item 10 with:

```markdown
10. ~~**Select the entry-01 store and the entry-04 store.**~~ **Done 2026-07-29.**
    Design: `docs/superpowers/specs/2026-07-29-golden-entries-01-04-selection-design.md`.

    - **Entry 01 = `theme-dawn-demo.myshopify.com`** (Shopify's Dawn reference
      theme demo), `evals/golden/01-clean-theme/`. Sole survivor of a
      nine-candidate screen: four demos are `noindex` sitewide — a correct
      `critical`, and structural rather than unlucky, since demo stores are
      deliberately deindexed — and four more exceed LCP 4.0s on
      `mobile-4g-slow`. Dawn measured LCP 2.42s home / 2.52s collection /
      2.87s pdp, CLS 0.000 throughout, perf 0.92.
    - **Entry 04 = `www.forestwholefoods.co.uk`** (UK organic wholefoods SMB on
      WooCommerce, default permalinks), `evals/golden/04-woocommerce/`. Nalgene
      rejected for disallowing `/cart/` in robots.txt.
    - **Entry 01 gates `[score_range, findings_above_medium]` and leaves the
      finding count ungated.** The screen found real defects on Dawn — no meta
      description on four templates, home `<title>` = the raw store handle, PDP
      LCP in the `medium` band — so a correct audit plausibly emits 3-5
      findings and rubric §5's `≤ 3` would fail on **true positives** while the
      two false-positive bars hold. `max_findings: 3` is set and printed so the
      recalibration argument accumulates evidence.
    - **Neither store is owned**, so `planting/screen_candidate.py` re-runs the
      selection criteria immediately before capture; a failing gate is a
      re-selection trigger. `crawler/archive.py` at capture is the only
      recoverable copy for both.
```

- [ ] **Step 3: Add the two crawler obligations to items 11–12**

Under "### Then — one capture wave", insert before the existing item 11:

```markdown
11. **Platform-generic discovery** (selection design D3). Discovery is hardcoded
    to `/collections/{handle}`, `/products/{handle}` and `/search?q=a`; pointed
    at a WooCommerce store it returns collection, pdp and search `absent` — no
    product page, which guts the conversion axis. Add a fingerprint-selected URL
    table: `/shop` or `/product-category/{slug}` → collection, `/product/{slug}`
    → pdp, `/?s=a` → search. Shopify behaviour unchanged. `path_under_test:
    reduced` therefore means *fewer platform-specific signals*, not fewer pages.
    Satisfies `specs/crawler.md` §10 acceptance test 4.
12. **`robots.txt` `Crawl-delay`** (selection design D6). `crawler/robots.py`
    parses allow/disallow only and `session.py` sleeps a fixed `min_interval_s`.
    Forest Whole Foods declares `Crawl-delay: 10`, as does Nalgene — normal for
    WordPress behind a caching plugin. Every prior entry is a store we own, so
    this has never bound; brief §5 conduct is non-negotiable for one we do not.
    `session.py` honours `max(min_interval_s, crawl_delay)` and `manifest.yaml`
    records the effective value. At 10s over ~14 fetches an entry-04 capture
    takes ~3 minutes in delays alone — worth knowing before it reads as a hang.
```

Then renumber the existing items 11 → 13, 12 → 14, 13 → 15, and the "Then — the deliverable" items 14 → 16, 15 → 17, 16 → 18. Update the two cross-references inside them: item 12's old text ("Fix the distiller short-text gap") is now item 13, and the "Sequencing note" above refers to "item 3" of the readiness list, which is unchanged.

- [ ] **Step 4: Note entry 01 against open decision #2**

In "### Open decisions — need a call, not an inference", append to item 2:

```markdown
   **Entry 01 now exists as a selection (2026-07-29) but not as a capture**, so
   this stays open until the 0.3.0 wave runs it. Nothing about the selection
   pre-empts the answer.
```

- [ ] **Step 5: Verify the stale-path lint still passes**

`tests/test_repo_hygiene.py` lints live docs for stale path spellings. `PROJECT-STATE.md` is a live doc.

Run: `python -m pytest tests/test_repo_hygiene.py -q`
Expected: PASS (48 tests, plus any new ones).

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest tests/ -q`
Expected: PASS.

```bash
git add PROJECT-STATE.md
git commit -m "docs: PROJECT-STATE — step 10 done, capture wave gains D3 and D6

Entry 01 = theme-dawn-demo (sole survivor of nine; four are noindex sitewide,
four more exceed LCP 4.0s). Entry 04 = forestwholefoods.co.uk.

Two crawler obligations added to the capture wave, both surfaced by selection
rather than by design review: platform-generic discovery (a Woo store currently
yields collection, pdp and search absent) and robots Crawl-delay (never bound
before because every prior entry is a store we own).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
|---|---|
| D1 entry 01 = Dawn | 5 |
| D2 entry 04 = Forest Whole Foods, `gates: []` rationale | 6 |
| D3 platform-generic discovery | 8 (registered into the wave — build is step 11, not this plan) |
| D4 gate severity + score, count advisory | 5 |
| D5 unowned → re-screen at capture, archive, `aov: null` | 2, 3, 4, 5, 6 |
| D6 `Crawl-delay` | 8 (registered — build is step 12, not this plan) |
| Deliverable 1 (entry 01 context.yaml) | 5 |
| Deliverable 2 (entry 04 context.yaml) | 6 |
| Deliverable 3 (`screen_candidate.py` + tests) | 1, 2, 3, 4 |
| Deliverable 6 (PROJECT-STATE) | 8 |

Deliverables 4 and 5 of the spec are explicitly out of scope for this plan, per the handoff decision recorded at its top; Task 8 registers them so they cannot be lost.

**Gap found and closed:** the spec's build order did not include a golden-entry walker test. Task 7 adds it — the schema's cross-entry `throttling` rule was enforced nowhere, and it is the one check that gets cheaper the more entries exist.

**Type consistency check:** `SampleRun` (Task 1) is consumed structurally by `perf_gates` via the `SampleRunLike` Protocol (Task 3) — field names `samples`, `failed`, `gate_leak`, `blocked` match in both. `Gate` and `HeadFacts` (Task 2) are used unchanged in Tasks 3 and 4. `measure.sample_url`'s keyword-only parameters in Task 1's test match the call in Task 4's `main()` (`runs`, `password`, `debug_port`, `echo`). `ENTRIES` keys `"01"`/`"04"` match the `--entry` choices and the directory prefixes in Tasks 5 and 6.

**Known soft spot, stated rather than hidden:** Task 1 moves browser code no unit test reaches. Step 5 of that task is a hand-run parity check against the live store, which is the same split `tests/test_measure.py` already documents for that path. If that is not acceptable, the alternative is a mock-Session test, which would pin the mock rather than the behaviour.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-29-golden-entries-01-04-selection.md`.
