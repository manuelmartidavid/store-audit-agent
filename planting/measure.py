"""Single-URL threshold check for the sabotage planting loop.

    python planting/measure.py https://torontosportscard.myshopify.com/products/x
    python planting/measure.py <url> --runs 5 --expect-lcp-band 3000..3800
    python planting/measure.py <url> --runs 5 --expect-cls-min 0.25
    python planting/measure.py <url> --no-password

Runs Lighthouse against ONE url through the same machinery as a full capture —
same Session (politeness, storefront gate, cookie mirroring), same Node sidecar,
same throttling profile — and prints the three numbers the sabotage spec aims
at: mobile LCP, CLS, and the performance score, with their rubric threshold
sides. Exists so the P-01/P-02/P-03 aim-adjust loop costs one page load per
iteration instead of a full six-template crawl.

Instrument parity with the crawler is structural, not asserted: both callers go
through crawler.lighthouse.run(), which spawns node/lighthouse_runner.mjs with
only (port, targets, out). There is no config parameter through which a probe
and a capture could diverge. Change the .mjs and both move together.

Multi-run is the point, not a nicety. A single LCP reading wanders by more than
the headroom P-02 has against the 4.0s boundary, so `--runs` reports median and
full spread, and an --expect-* assertion passes only if EVERY run lands on the
required side. A median on the right side with a spread that crosses the
boundary is a defect that has not landed.

Each run gets its own browser, and therefore a cold HTTP cache. Reusing one
browser makes run 2 onward read the heavy asset back out of cache, which reads
as an enormous spread and is not a measurement of anything. The gate is opened
once per run as a result; that is the price of runs that mean the same thing.

This is a planting aid, not a capture tool. It writes nothing to fixtures/;
the frozen fixture from `python -m crawler` remains the only source of labels
(sabotage-spec: "you do not get to declare metric values" — this script only
tells you when to stop adjusting and re-capture).

Password comes from TSCC_STOREFRONT_PASSWORD (or --password-env NAME) via .env,
same as the crawler. The value is never printed and nothing here writes files.

Exit codes: 0 = measured, expectations met (or none given) · 1 = operational
failure (gate blocked, every run failed, gate leak) · 2 = measured cleanly but
an --expect-* assertion did not hold.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler import lighthouse
from crawler.dotenv import load as load_dotenv
from crawler.session import Session

# Rubric v0.2 thresholds (references/rubric.md): boundary values take the LOWER level.
LCP_HIGH_MS = 4000.0     # > 4.0s on a revenue template, all sessions -> high
LCP_MEDIUM_MS = 2500.0   # 2.5–4.0s -> medium
CLS_HIGH = 0.25          # > 0.25 -> high


@dataclass
class Sample:
    """One Lighthouse run, reduced to what the planting loop aims at."""

    lcp: float | None = None
    cls: float | None = None
    perf: float | None = None
    selector: str | None = None
    final_url: str = ""
    phases: dict | None = None       # TTFB / load delay / load time / render delay
    images: list | None = None       # top image transfers: (url, wire KB, decoded KB, mime)


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


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_gate_url(url: str) -> bool:
    """True if a Lighthouse run actually landed on the storefront password page.

    MNC-004: real Lighthouse numbers about a page that isn't the store are worse
    than no numbers, because they look valid. If the mirrored gate cookie is
    cleared between runs this is the only thing that catches it.
    """
    path = urlparse(url or "").path.rstrip("/")
    return path.endswith("/password") or path == "/password"


def _side(value: float | None, kind: str) -> str:
    if value is None:
        return "no value"
    if kind == "lcp":
        if value > LCP_HIGH_MS:
            return f"HIGH side (> {LCP_HIGH_MS/1000:.1f}s)"
        if value > LCP_MEDIUM_MS:
            return f"MEDIUM band ({LCP_MEDIUM_MS/1000:.1f}-{LCP_HIGH_MS/1000:.1f}s)"
        return f"below medium (<= {LCP_MEDIUM_MS/1000:.1f}s)"
    if value > CLS_HIGH:
        return f"HIGH side (> {CLS_HIGH})"
    return f"at/below threshold (<= {CLS_HIGH})"


def _lcp_selector(audits: dict) -> str | None:
    """Pull the LCP element selector out of either LHR detail shape.

    Newer Lighthouse nests a table inside a list (element table + phase table);
    older versions put the node table at the top level. Try both rather than
    silently printing nothing, because "is the LCP element the image I planted?"
    is the question this script exists to answer.
    """
    details = (audits.get("largest-contentful-paint-element") or {}).get("details") or {}
    for item in details.get("items") or []:
        if not isinstance(item, dict):
            continue
        inner = item.get("items")
        for cand in (inner if isinstance(inner, list) else [item]):
            node = (cand or {}).get("node") or {}
            sel = node.get("selector") or node.get("snippet")
            if sel:
                return sel
    return None


def _lcp_phases(audits: dict) -> dict | None:
    """The LCP phase table (TTFB / load delay / load time / render delay).

    Load time is the transfer of the LCP resource itself - the number the
    image-weight bisection actually steers. Everything else is overhead the
    asset cannot change.
    """
    details = (audits.get("largest-contentful-paint-element") or {}).get("details") or {}
    for item in details.get("items") or []:
        inner = item.get("items") if isinstance(item, dict) else None
        if not isinstance(inner, list):
            continue
        phases = {}
        for row in inner:
            if isinstance(row, dict) and "phase" in row and isinstance(row.get("timing"), (int, float)):
                phases[str(row["phase"])] = float(row["timing"])
        if phases:
            return phases
    return None


def _image_transfers(audits: dict, top: int = 3) -> list:
    """Largest image responses: (url, wire bytes, decoded bytes, mime).

    Wire vs decoded is the CDN-transcode tell: a 1.9 MB PNG arriving as a
    300 KB webp means the wire - not the upload - is what LCP is paying for.
    """
    details = (audits.get("network-requests") or {}).get("details") or {}
    rows = []
    for item in details.get("items") or []:
        if not isinstance(item, dict) or item.get("resourceType") != "Image":
            continue
        rows.append((
            str(item.get("url") or ""),
            int(item.get("transferSize") or 0),
            int(item.get("resourceSize") or 0),
            str(item.get("mimeType") or "?"),
        ))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:top]


def _extract(lhr: dict) -> Sample:
    audits = lhr.get("audits") or {}
    return Sample(
        lcp=(audits.get("largest-contentful-paint") or {}).get("numericValue"),
        cls=(audits.get("cumulative-layout-shift") or {}).get("numericValue"),
        perf=((lhr.get("categories") or {}).get("performance") or {}).get("score"),
        selector=_lcp_selector(audits),
        final_url=lhr.get("finalDisplayedUrl") or lhr.get("finalUrl") or lhr.get("requestedUrl") or "",
        phases=_lcp_phases(audits),
        images=_image_transfers(audits),
    )


def _parse_band(spec: str) -> tuple[float | None, float | None]:
    """`LO..HI`, either end optional. `5000..` is >= 5000; `..3800` is <= 3800."""
    if ".." not in spec:
        raise argparse.ArgumentTypeError("band must look like LO..HI, e.g. 3000..3800 or 5000..")
    lo_s, _, hi_s = spec.partition("..")
    try:
        lo = float(lo_s) if lo_s.strip() else None
        hi = float(hi_s) if hi_s.strip() else None
    except ValueError:
        raise argparse.ArgumentTypeError(f"band ends must be numbers: {spec!r}")
    if lo is None and hi is None:
        raise argparse.ArgumentTypeError("band needs at least one end")
    if lo is not None and hi is not None and lo > hi:
        raise argparse.ArgumentTypeError(f"band is inverted: {spec!r}")
    return lo, hi


def _report(label: str, values: list[float], scale: float, unit: str, digits: int, kind: str) -> None:
    """Median + full spread + whether the spread stays on one rubric side."""
    if not values:
        print(f"  {label:<5} no value in any run")
        return
    lo, hi = min(values), max(values)
    med = statistics.median(values)
    fmt = f"{{:.{digits}f}}"
    print(
        f"  {label:<5} median {fmt.format(med/scale)}{unit}"
        f"   min {fmt.format(lo/scale)}{unit}"
        f"   max {fmt.format(hi/scale)}{unit}"
        f"   spread {fmt.format((hi-lo)/scale)}{unit}"
    )
    lo_side, hi_side = _side(lo, kind), _side(hi, kind)
    if lo_side == hi_side:
        print(f"        all runs: {lo_side}")
    else:
        print(f"        !! SPREAD CROSSES A THRESHOLD: {lo_side} .. {hi_side}")
        print(f"        the aim has not landed - this is noise, not a defect")


def _check_band(values: list[float], band: tuple[float | None, float | None], label: str,
                scale: float, unit: str, digits: int) -> bool:
    lo, hi = band
    fmt = f"{{:.{digits}f}}"
    bad = [v for v in values if (lo is not None and v < lo) or (hi is not None and v > hi)]
    if lo is not None and hi is not None:
        want = f"{fmt.format(lo/scale)}{unit}-{fmt.format(hi/scale)}{unit}"
    elif lo is not None:
        want = f">= {fmt.format(lo/scale)}{unit}"
    else:
        want = f"<= {fmt.format(hi/scale)}{unit}"
    if not values:
        print(f"  EXPECT {label} {want}: FAIL - no readings")
        return False
    if bad:
        print(f"  EXPECT {label} {want}: FAIL - {len(bad)}/{len(values)} runs outside")
        return False
    print(f"  EXPECT {label} {want}: pass ({len(values)}/{len(values)} runs)")
    return True


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
        # 1.50s is one measurement and two cache hits. You cannot aim an image
        # at a 3.0-3.8s window from that.
        #
        # A new browser is a new profile and therefore a cold cache. The two
        # cheaper fixes do not work here: Network.clearBrowserCache cannot reach
        # the default context where Lighthouse opens its tabs (contexts have
        # separate caches, and Playwright exposes no page there), and letting
        # Lighthouse reset storage would clear the gate cookie along with the
        # cache and drop every run onto /password. The cost is one gate
        # navigation per run.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="Exact page URL to measure")
    parser.add_argument("--runs", type=int, default=1, help="Repeat N times and report the spread (default 1)")
    parser.add_argument("--password-env", default="TSCC_STOREFRONT_PASSWORD")
    parser.add_argument("--no-password", action="store_true")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--node-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--expect-lcp-band", type=_parse_band, metavar="LO..HI",
        help="Milliseconds. Every run must land inside. P-01: 5000.. / P-02: 3000..3800",
    )
    parser.add_argument(
        "--expect-cls-min", type=float, metavar="X",
        help="Every run must exceed X strictly (boundary values take the lower level). P-03: 0.25",
    )
    args = parser.parse_args(argv)

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    load_dotenv(args.env_file)
    password = None if args.no_password else os.environ.get(args.password_env)

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

    lcps = [s.lcp for s in samples if s.lcp is not None]
    clss = [s.cls for s in samples if s.cls is not None]

    print(f"\n--- {len(samples)} ok / {len(samples) + failed} runs ---")
    _report("LCP", lcps, 1000.0, "s", 2, "lcp")
    _report("CLS", clss, 1.0, "", 3, "cls")

    seen = {s.selector for s in samples if s.selector}
    if len(seen) > 1:
        print(f"  !! LCP element differed across runs: {', '.join(sorted(seen))}")
        print("        aim is unstable - the heavy asset is not reliably the LCP element")
    elif seen:
        print(f"  LCP element: {seen.pop()}")

    ok = True
    if args.expect_lcp_band:
        ok &= _check_band(lcps, args.expect_lcp_band, "LCP", 1000.0, "s", 2)
    if args.expect_cls_min is not None:
        # Strictly greater: rubric v0.2 gives boundary values the LOWER level,
        # so CLS == 0.25 is medium, not high.
        below = [v for v in clss if v <= args.expect_cls_min]
        if not clss or below:
            print(f"  EXPECT CLS > {args.expect_cls_min}: FAIL -"
                  f" {len(below) or 'no'} run(s) at or below the threshold")
            ok = False
        else:
            print(f"  EXPECT CLS > {args.expect_cls_min}: pass ({len(clss)}/{len(clss)} runs)")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())