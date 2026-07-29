"""Why is *that* the LCP element? — planting diagnostic.

    python planting/inspect_lcp.py https://torontosportscard.myshopify.com/
    python planting/inspect_lcp.py <url> --selector img.product-page__featured-img

measure.py tells you which element won LCP. When it isn't the one you planted,
the question is always: is it in the DOM, is it displayed, did it load, and is
something else simply bigger. This answers all four in one page load, at the
same 412x823 viewport the Lighthouse sidecar uses and through the same gated
Session.

Geometry and load state only - it measures nothing and labels nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.dotenv import load as load_dotenv
from crawler.session import Session

# What lighthouse_runner.mjs emulates. Geometry only — no device scale factor,
# which does not affect layout.
MOBILE_W, MOBILE_H = 412, 823

DEFAULT_SELECTOR = "img.hero-carousel__slide-img"

PROBE = r"""
(selector) => {
  const vw = window.innerWidth, vh = window.innerHeight;

  // LCP considers the element's visible area, clipped to the viewport.
  const painted = (el) => {
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    return { area: Math.round(w * h), rect: {
      x: Math.round(r.x), y: Math.round(r.y),
      w: Math.round(r.width), h: Math.round(r.height) } };
  };

  const label = (el) => el.tagName.toLowerCase() +
    (el.id ? "#" + el.id : "") +
    (el.className && typeof el.className === "string"
      ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "");

  // --- the element under suspicion -----------------------------------------
  const el = document.querySelector(selector);
  let target = null;
  if (el) {
    const cs = getComputedStyle(el);
    const p = painted(el);
    const chain = [];
    for (let a = el.parentElement; a && chain.length < 8; a = a.parentElement) {
      const acs = getComputedStyle(a);
      if (acs.display === "none" || acs.visibility === "hidden" || acs.opacity === "0" ||
          acs.overflow === "hidden") {
        chain.push({ el: label(a), display: acs.display, visibility: acs.visibility,
                     opacity: acs.opacity, overflow: acs.overflow });
      }
    }
    target = {
      selector, found: true, label: label(el),
      display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
      objectFit: cs.objectFit,
      rect: p.rect, paintedArea: p.area,
      inViewport: p.area > 0,
      // naturalWidth 0 with complete=true means the fetch failed. That is the
      // single most common reason a planted image never becomes LCP.
      naturalWidth: el.naturalWidth === undefined ? null : el.naturalWidth,
      naturalHeight: el.naturalHeight === undefined ? null : el.naturalHeight,
      complete: el.complete === undefined ? null : el.complete,
      attrSrc: (el.getAttribute && el.getAttribute("src")) || null,
      currentSrc: el.currentSrc || null,
      srcset: (el.getAttribute && el.getAttribute("srcset")) || null,
      hidingAncestors: chain,
    };
  } else {
    target = { selector, found: false };
  }

  // --- what is actually biggest --------------------------------------------
  const rows = [];
  for (const node of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(node);
    if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
    const tag = node.tagName.toLowerCase();
    const isImg = tag === "img";
    const isText = !isImg && node.children.length === 0 &&
                   (node.textContent || "").trim().length > 0;
    if (!isImg && !isText) continue;
    if (isImg && !node.naturalWidth) {
      const p0 = painted(node);
      rows.push({ el: label(node), kind: "img (NOT LOADED)", area: 0, rect: p0.rect });
      continue;
    }
    const p = painted(node);
    if (p.area <= 0) continue;
    rows.push({ el: label(node), kind: isImg ? "img" : "text", area: p.area, rect: p.rect });
  }
  rows.sort((a, b) => b.area - a.area);
  return { viewport: { vw, vh }, target, candidates: rows.slice(0, 8) };
}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--selector", default=DEFAULT_SELECTOR)
    ap.add_argument("--password-env", default="TSCC_STOREFRONT_PASSWORD")
    ap.add_argument("--no-password", action="store_true")
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    ap.add_argument("--settle-ms", type=int, default=3000,
                    help="Wait after load so a slow image has a chance to arrive")
    ap.add_argument("--css-grep", default="hero-carousel__slide-image",
                    help="Report every live CSS rule whose text contains this")
    ap.add_argument("--dump-text", metavar="SELECTOR", default=None,
                    help="Print innerText of every match for SELECTOR and exit "
                         "(e.g. .product-page__description). Diagnostic: shows what "
                         "text actually reached the rendered page.")
    ap.add_argument("--browser-ua", action="store_true",
                    help="DIAGNOSTIC: identify as a plain browser instead of the "
                         "crawler UA. If the page differs between the two, the "
                         "storefront serves bots from a cache. Never capture with this.")
    args = ap.parse_args(argv)

    load_dotenv(args.env_file)
    password = None if args.no_password else os.environ.get(args.password_env)
    p = urlparse(args.url)
    origin = f"{p.scheme}://{p.netloc}"

    if args.browser_ua:
        # The Session hardcodes the polite crawler UA from config. For this one
        # experiment we want the page a human gets. Patch the symbol session.py
        # actually reads; the politeness throttle and the gate stay intact.
        import crawler.session as _sessmod
        _sessmod.USER_AGENT = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/126.0.0.0 Mobile Safari/537.36")
        print("!! diagnostic run: browser UA, not the crawler UA - do not label from this\n")

    with Session(origin) as session:
        gate = session.open_gate(password)
        if gate.gate == "blocked":
            print(f"blocked at the gate: {gate.kind}", file=sys.stderr)
            return 1
        session.page.set_viewport_size({"width": MOBILE_W, "height": MOBILE_H})
        visit = session.goto(args.url)
        if not visit.ok:
            print(f"navigation failed: {visit}", file=sys.stderr)
            return 1
        session.page.wait_for_timeout(args.settle_ms)

        if args.dump_text:
            texts = session.page.evaluate(
                "(sel) => [...document.querySelectorAll(sel)].map(e => e.innerText)",
                args.dump_text,
            )
            print(f"=== innerText of {args.dump_text!r} ({len(texts)} match) ===")
            for i, t in enumerate(texts, 1):
                print(f"--- match {i} ---")
                print(t)
            return 0

        data = session.page.evaluate(PROBE, args.selector)

        # Which theme actually served this HTML? When the local source, the
        # code editor and the rendered page disagree, this settles it - a
        # preview cookie, a stale edge cache and a stuck compile all look the
        # same from outside.
        provenance = session.page.evaluate(
            "() => ({"
            " theme: (window.Shopify && window.Shopify.theme) ? window.Shopify.theme : null,"
            " shop: (window.Shopify && window.Shopify.shop) || null,"
            " designMode: !!(window.Shopify && window.Shopify.designMode),"
            " compiled: [...document.querySelectorAll('link[rel=stylesheet]')]"
            "   .map(l => l.href).filter(h => h.includes('compiled_assets')),"
            " finalUrl: location.href"
            "})"
        )

        # Where does the rule actually come from? Reading cssRules throws for
        # cross-origin sheets and Shopify serves theme CSS from its CDN, so the
        # page can't introspect its own styles. Fetch the sheets through the
        # session instead - same gate, same cookies, no CORS.
        sheets = session.page.evaluate(
            "() => ({"
            " links: [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href),"
            " inline: [...document.querySelectorAll('style')].map(s => s.textContent || '')"
            "})"
        )
        css_hits = []
        for i, text in enumerate(sheets["inline"]):
            if args.css_grep in text:
                css_hits.append((f"<style> block #{i+1} (inline in the document)", text))
        for href in sheets["links"]:
            try:
                status, text = session.fetch_text(href)
            except Exception as exc:  # noqa: BLE001 - diagnostic, never fatal
                css_hits.append((f"{href} (fetch failed: {exc})", ""))
                continue
            if text and args.css_grep in text:
                css_hits.append((f"{href} (HTTP {status})", text))

    t = data["target"]
    print(f"viewport {data['viewport']['vw']}x{data['viewport']['vh']}  (sidecar emulation)")

    print("\n=== which theme rendered this page ===")
    print(f"  final url : {provenance['finalUrl']}")
    print(f"  shop      : {provenance['shop']}")
    print(f"  designMode: {provenance['designMode']}")
    theme = provenance["theme"]
    if not theme:
        print("  Shopify.theme is absent - cannot identify the theme from the page")
    else:
        for key in ("id", "name", "role", "handle", "theme_store_id", "schema_name", "schema_version"):
            if key in theme:
                print(f"  theme.{key:<14} {theme[key]}")
        extra = {k: v for k, v in theme.items()
                 if k not in ("id", "name", "role", "handle", "theme_store_id",
                              "schema_name", "schema_version")}
        if extra:
            print(f"  theme.(other)      {json.dumps(extra)[:160]}")
    for href in provenance["compiled"]:
        print(f"  compiled  : {href}")
    print(f"\n=== {args.selector} ===")
    if not t.get("found"):
        print("  NOT IN THE DOM — the element never rendered. Check the Liquid, not the CSS.")
    else:
        print(f"  display {t['display']} · visibility {t['visibility']} · opacity {t['opacity']}"
              f" · object-fit {t['objectFit']}")
        print(f"  rect x={t['rect']['x']} y={t['rect']['y']} w={t['rect']['w']} h={t['rect']['h']}")
        print(f"  painted area in viewport: {t['paintedArea']} px^2"
              f"{'' if t['inViewport'] else '   <-- ZERO: outside the viewport or collapsed'}")
        print(f"  natural {t['naturalWidth']}x{t['naturalHeight']} · complete={t['complete']}")
        if t["naturalWidth"] == 0 and t["complete"]:
            print("  !! THE IMAGE FAILED TO LOAD. A broken img paints nothing and can never"
                  " be the LCP element, however large its box is.")
        print(f"  src attr : {(t['attrSrc'] or '(none)')[:120]}")
        print(f"  currentSrc: {(t['currentSrc'] or '(none)')[:120]}")
        print(f"  srcset   : {(t['srcset'] or '(none)')[:80]}")
        if t["hidingAncestors"]:
            print("  ancestors that clip or hide:")
            for a in t["hidingAncestors"]:
                print(f"    {a['el']}  display={a['display']} visibility={a['visibility']}"
                      f" opacity={a['opacity']} overflow={a['overflow']}")

    print("\n=== every stylesheet the page references ===")
    for href in sheets["links"]:
        print(f"  {href[:150]}")
    print(f"  (+ {len(sheets['inline'])} inline <style> blocks)")

    print("\n=== critical.css: is the pushed override actually served? ===")
    crit = [h for h in sheets["links"] if "critical" in h]
    if not crit:
        print("  the page references NO critical.css link at all")
    for href in crit:
        try:
            status, text = session.fetch_text(href)
        except Exception as exc:  # noqa: BLE001
            print(f"  {href[:130]}\n    fetch failed: {exc}")
            continue
        marker = "compiled-asset bypass" in (text or "")
        override = "hero-carousel__content-grid .hero-carousel__slide-image" in (text or "")
        print(f"  {href[:130]}")
        print(f"    HTTP {status} · {len(text or '')} bytes")
        print(f"    bypass comment present : {marker}")
        print(f"    override rule present  : {override}")
        if status is None or not text:
            print("    -> fetch FAILED - no verdict about the served content from this")
        elif not override:
            print("    -> the served file is genuinely the old one (stale asset)")

    print(f"\n=== live CSS rules containing {args.css_grep!r} ===")
    if not css_hits:
        print("  no stylesheet on the live page contains it at all")
    for source, text in css_hits:
        print(f"  from {source[:130]}")
        start = 0
        while True:
            i = text.find(args.css_grep, start)
            if i < 0:
                break
            lo, hi = max(0, i - 90), min(len(text), i + 160)
            snippet = " ".join(text[lo:hi].split())
            print(f"    ...{snippet}...")
            start = i + 1

    print("\n=== largest painted elements in the viewport (LCP candidates) ===")
    for i, row in enumerate(data["candidates"], 1):
        mark = " <-- LCP should be this" if i == 1 else ""
        print(f"  {i}. {row['area']:>8} px^2  {row['kind']:<16} {row['el'][:60]}"
              f"  y={row['rect']['y']}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
