"""Runs a whole crawl in order: gate, discovery, captures, Lighthouse, output files.

Invariant: this layer only records what happened, never what it means. A
div-based add-to-cart button leaves here as a div with its attributes.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from . import SCHEMA_CRAWL, __version__
from .axe import Axe
from .config import EXPECTED_FETCHES_PER_CAPTURE, TEMPLATES, THROTTLING_PROFILE
from .discovery import (
    ALL_LINKS_SELECTOR,
    CART_LINK_SELECTOR,
    NAV_SELECTOR,
    pick_cart,
    pick_collection,
    pick_product,
    pinned_target,
    profile_for,
    random_404_path,
    same_origin,
    static_targets,
)
from .distill import distill
from .fingerprint import (
    Signals,
    build as build_fingerprint,
    detect_platform,
    empty as empty_fingerprint,
)
from .lighthouse import run as run_lighthouse, version as lighthouse_version
from .manifest import Manifest
from .redaction import assert_absent
from .robots import Robots
from .session import Session


@dataclass
class Options:
    """Everything one crawl run needs to know."""

    origin: str
    out_dir: Path
    password_env: str | None = None
    run_lighthouse: bool = True
    run_axe: bool = True
    headless: bool = True
    debug_port: int = 9222
    seed: int | None = None
    node_root: Path = field(default_factory=Path.cwd)
    verify_idempotence: bool = True
    pinned: dict = field(default_factory=dict)  # eval-only: template -> exact URL


@dataclass
class Result:
    """What one crawl run produced."""

    crawl: dict[str, Any]
    manifest: Manifest
    manifest_sha256: str | None = None
    lighthouse_count: int = 0
    axe_count: int = 0
    fetches: int = 0


def _now() -> str:
    """The current local time as an ISO-8601 string."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _blank_template(url: str | None = None, status: str = "absent") -> dict[str, Any]:
    """An empty template entry, with all five keys always present."""
    return {
        "url": url,
        "status": status,
        "http_status": None,
        "distilled": None,
        "dropped": None,
    }


def crawl(options: Options, *, log=print) -> Result:
    """Crawl one store end to end and write its fixture files."""
    origin = options.origin.rstrip("/")
    password = os.environ.get(options.password_env) if options.password_env else None
    if options.password_env and not password:
        log(f"! {options.password_env} is not set — crawling as an ungated visitor")

    rng = random.Random(options.seed) if options.seed is not None else None
    axe = Axe(options.node_root) if options.run_axe else None

    templates: dict[str, dict[str, Any]] = {t: _blank_template() for t in TEMPLATES}
    signals = Signals()
    axe_results: dict[str, dict[str, Any]] = {}
    axe_status: dict[str, str] = {}
    observed = False
    block: dict[str, Any] | None = None
    gate = "none"

    session = Session(
        origin,
        headless=options.headless,
        debug_port=options.debug_port if options.run_lighthouse else None,
    )
    session.start()
    try:
        robots = _fetch_robots(session, origin, log=log)
        interval = session.honour_crawl_delay(robots.crawl_delay_s)
        if robots.crawl_delay_s is not None:
            projected = interval * EXPECTED_FETCHES_PER_CAPTURE
            log(f"· robots.txt: Crawl-delay {robots.crawl_delay_s:g}s → {interval:g}s between "
                f"fetches (~{projected / 60:.0f} min of waiting across this capture)")

        gate_result = session.open_gate(password)
        gate = gate_result.gate
        if gate == "blocked":
            log(f"✗ blocked: {gate_result.kind}")
            block = {
                "kind": gate_result.kind,
                "evidence": gate_result.evidence,
                "final_url": gate_result.final_url,
            }
            for template in TEMPLATES:
                templates[template] = _blank_template(status="blocked")
        else:
            log(f"· gate: {gate}")
            observed = True
            _crawl_templates(
                session,
                origin,
                robots,
                axe,
                rng,
                templates,
                signals,
                axe_results,
                axe_status,
                verify_idempotence=options.verify_idempotence,
                pinned=options.pinned,
                log=log,
            )

        captured = [t for t in TEMPLATES if templates[t]["status"] == "captured"]
        lighthouse = None
        if options.run_lighthouse and captured:
            # Carry the gate cookies into the context Lighthouse audits in.
            mirrored = session.mirror_session_to_default()
            log(f"· lighthouse: {len(captured)} template(s) (session cookies mirrored: {mirrored})")
            lighthouse = run_lighthouse(
                options.node_root,
                options.debug_port,
                [(t, templates[t]["url"]) for t in captured],
            )
            if lighthouse.errors:
                for template, message in lighthouse.errors.items():
                    log(f"  ! lighthouse {template}: {message}")
        fetches = session.fetch_count
        chrome_version = session.browser_version
        interval = session.min_interval_s
        declared = robots.crawl_delay_s
    finally:
        session.close()

    status = _overall_status(templates)
    crawl_json: dict[str, Any] = {
        "schema": SCHEMA_CRAWL,
        "origin": origin,
        "status": status,
        "gate": gate,
    }
    if block is not None:
        crawl_json["block"] = block
    # Invariant: a store we never got into reports platform "unknown", even
    # when the page that blocked us was obviously Shopify (MNC-003).
    crawl_json["fingerprint"] = build_fingerprint(signals, observed=observed) if observed else empty_fingerprint()
    crawl_json["templates"] = {t: templates[t] for t in TEMPLATES}

    manifest = Manifest(
        captured_at=_now(),
        origin=origin,
        gate=gate,
        crawler_version=__version__,
        lighthouse_version=(lighthouse.version if lighthouse else lighthouse_version(options.node_root)),
        axe_core_version=(axe.version if axe else None),
        chrome_version=chrome_version,
        throttling=THROTTLING_PROFILE,
        fetch_interval_s=interval,
        crawl_delay_declared=declared,
        templates={
            t: {
                "crawl": templates[t]["status"],
                "lighthouse": _lh_status(t, templates, lighthouse, options.run_lighthouse),
                "axe": axe_status.get(t, "skipped"),
            }
            for t in TEMPLATES
        },
    )

    result = Result(
        crawl=crawl_json,
        manifest=manifest,
        lighthouse_count=len(lighthouse.lhrs) if lighthouse else 0,
        axe_count=len(axe_results),
        fetches=fetches,
    )
    _write(options, result, lighthouse, axe_results, templates, password, log=log)
    return result


# --- steps ------------------------------------------------------------------

def _fetch_robots(session: Session, origin: str, *, log) -> Robots:
    """Fetch robots.txt before anything else, treating failures as permissive."""
    status, body = session.fetch_text(urljoin(origin + "/", "/robots.txt"))
    if status is None:
        log("· robots.txt: unreachable — treating as permissive")
        return Robots.permissive("error")
    if status >= 400 or not body.strip():
        log(f"· robots.txt: HTTP {status} — treating as permissive")
        return Robots.permissive("absent", status)
    log(f"· robots.txt: HTTP {status}, {len(body.splitlines())} lines")
    return Robots.parse(body, status)


def _crawl_templates(
    session: Session,
    origin: str,
    robots: Robots,
    axe: Axe | None,
    rng: random.Random | None,
    templates: dict[str, dict[str, Any]],
    signals: Signals,
    axe_results: dict[str, dict[str, Any]],
    axe_status: dict[str, str],
    *,
    verify_idempotence: bool,
    pinned: dict,
    log,
) -> None:
    """Find and capture each of the six templates in order."""

    def capture(template: str, url: str) -> None:
        templates[template] = _capture(
            session,
            template,
            url,
            robots,
            axe,
            signals,
            axe_results,
            axe_status,
            verify_idempotence=verify_idempotence,
            log=log,
        )

    # home ------------------------------------------------------------------
    capture("home", urljoin(origin + "/", "/"))

    # Which URL table the remaining templates live under. Read off the home
    # page's own signals, so it is the same verdict the fixture will record.
    # A store we could not reach yields "unknown", which maps to the Shopify
    # table — the behaviour every capture before 0.3.0 had.
    platform, _ = detect_platform(signals)
    profile = profile_for(platform)
    log(f"· platform: {platform} → {profile.name} discovery")
    static = static_targets(origin, profile)

    # Links are read while home is still the current page — by the time the cart
    # is captured the browser is three navigations away.
    nav_links = session.query_links(NAV_SELECTOR) if templates["home"]["status"] == "captured" else []
    all_links = session.query_links(ALL_LINKS_SELECTOR) if templates["home"]["status"] == "captured" else []
    cart_links = session.query_links(CART_LINK_SELECTOR) if templates["home"]["status"] == "captured" else []

    # collection: first matching link in the home nav, then anywhere on the
    # page, then the profile's fallback.
    collection_url = pinned_target(pinned, "collection", origin)
    if collection_url:
        log(f"· collection: pinned {collection_url}")
    else:
        collection_url = pick_collection(nav_links, origin, profile) or pick_collection(
            all_links, origin, profile
        )
    collection_url = collection_url or urljoin(origin + "/", profile.collection_fallback)
    capture("collection", collection_url)

    # pdp: first product link in the chosen collection, else anywhere on the site.
    pdp_url = pinned_target(pinned, "pdp", origin)
    if pdp_url:
        log(f"· pdp: pinned {pdp_url}")
    else:
        if templates["collection"]["status"] == "captured":
            pdp_url = pick_product(session.query_links(profile.product_link_selector), origin, profile)
        if not pdp_url:
            pdp_url = _product_sitewide(session, origin, collection_url, robots, profile, log=log)
    if pdp_url:
        capture("pdp", pdp_url)
    else:
        log("· pdp: no product link found — absent")
        templates["pdp"] = _blank_template(status="absent")

    # cart: a store may rename the slug, so read its own cart link first.
    cart_url = pinned_target(pinned, "cart", origin)
    if cart_url:
        log(f"· cart: pinned {cart_url}")
    elif profile.discover_cart:
        cart_url = pick_cart(cart_links, origin, profile)
        if cart_url:
            log(f"· cart: discovered {cart_url}")
    capture("cart", cart_url or static["cart"])

    capture("search", static["search"])
    capture("404", urljoin(origin + "/", random_404_path(rng)))


def _product_sitewide(
    session: Session, origin: str, already: str, robots: Robots, profile, *, log
) -> str | None:
    """Last-resort product search: one extra fetch of the profile's catalog page."""
    fallback = urljoin(origin + "/", profile.sitewide_product_page)
    if fallback.rstrip("/") == already.rstrip("/") or not robots.allows(fallback):
        return None
    visit = session.goto(fallback)
    if visit.error or (visit.http_status or 500) >= 400:
        return None
    return pick_product(session.query_links(profile.product_link_selector), origin, profile)


def _capture(
    session: Session,
    template: str,
    url: str,
    robots: Robots,
    axe: Axe | None,
    signals: Signals,
    axe_results: dict[str, dict[str, Any]],
    axe_status: dict[str, str],
    *,
    verify_idempotence: bool,
    log,
) -> dict[str, Any]:
    """Visit one template's URL and record everything captured there."""
    if not robots.allows(url):
        # Invariant: a robots block is recorded as a fact. Never route around
        # it.
        log(f"· {template}: blocked_by_robots")
        axe_status[template] = "skipped"
        return _blank_template(url, "blocked_by_robots")

    visit = session.goto(url)
    entry = _blank_template(url, "error")
    entry["http_status"] = visit.http_status

    if visit.error:
        log(f"· {template}: error ({visit.error})")
        axe_status[template] = "skipped"
        return entry

    entry["url"] = visit.url
    status = _template_status(template, visit.http_status, visit.url, session.origin)
    entry["status"] = status
    if status != "captured":
        log(f"· {template}: {status} (HTTP {visit.http_status})")
        axe_status[template] = "skipped"
        return entry

    raw, dropped = session.walk_dom()
    distilled = distill(raw)
    if verify_idempotence:
        # Distilling the same page twice must give identical bytes. Checked here
        # so it fails during capture, not after a fixture has been frozen.
        second = distill(raw)
        if _canonical_json(distilled) != _canonical_json(second):
            raise RuntimeError(f"distillation is not deterministic for {template} ({visit.url})")

    entry["distilled"] = distilled
    entry["dropped"] = dropped
    signals.merge(session.collect_signals(visit))

    if axe is not None:
        if not axe.available:
            axe_status[template] = "skipped"
        else:
            result = axe.run(session.page)
            if result is None:
                axe_status[template] = "failed"
                log(f"  ! axe failed on {template}")
            else:
                axe_results[template] = result
                axe_status[template] = "ok"
    else:
        axe_status[template] = "skipped"

    log(f"· {template}: captured (HTTP {visit.http_status}, {_node_count(distilled)} nodes)")
    return entry


# --- classification ---------------------------------------------------------

def _template_status(template: str, http_status: int | None, final_url: str, origin: str) -> str:
    """Decide whether a visit counts as captured, absent, or an error."""
    if not same_origin(final_url, origin):
        return "absent"  # redirected off-origin
    if template == "404":
        # Whatever the store serves for an unknown path is the 404 template, so
        # a 200 here is a soft-404 for the triager to interpret.
        # Invariant: a 5xx is the platform's own error page, not the store's
        # 404. Capturing it would make Lighthouse and axe measure the wrong
        # page.
        if http_status is None or http_status >= 500:
            return "error"
        return "captured"
    if http_status is None:
        return "error"
    if 400 <= http_status < 500:
        return "absent"
    if http_status >= 500:
        return "error"
    return "captured"


def _overall_status(templates: dict[str, dict[str, Any]]) -> str:
    """Roll the per-template statuses up into complete, partial, or blocked."""
    statuses = [entry["status"] for entry in templates.values()]
    captured = statuses.count("captured")
    if captured == 0:
        return "blocked"
    if "error" in statuses:
        return "partial"
    return "complete"


def _lh_status(template, templates, lighthouse, requested: bool) -> str:
    """The Lighthouse status to record for one template."""
    if templates[template]["status"] != "captured":
        return "skipped"
    if not requested:
        return "skipped"
    if lighthouse is None:
        return "skipped"
    return lighthouse.status.get(template, "failed")


# --- output -----------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    """JSON in the one formatting every output file uses."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def _node_count(node: dict[str, Any] | None) -> int:
    """How many nodes are in a distilled tree."""
    if not node:
        return 0
    total = 1
    if "repeat" in node:
        return _node_count(node["repeat"].get("sample"))
    for child in node.get("children") or []:
        total += _node_count(child)
    return total


def _write(
    options: Options,
    result: Result,
    lighthouse,
    axe_results: dict[str, dict[str, Any]],
    templates: dict[str, dict[str, Any]],
    password: str | None,
    *,
    log,
) -> None:
    """Write the four fixture files and check nothing leaked the password."""
    out = options.out_dir
    out.mkdir(parents=True, exist_ok=True)

    (out / "crawl.json").write_text(_canonical_json(result.crawl) + "\n", encoding="utf-8", newline="\n")

    lhrs = lighthouse.lhrs if lighthouse else []
    (out / "lighthouse.json").write_text(_canonical_json(lhrs) + "\n", encoding="utf-8", newline="\n")

    ordered_axe = [axe_results[t] for t in TEMPLATES if t in axe_results]
    (out / "axe.json").write_text(_canonical_json(ordered_axe) + "\n", encoding="utf-8", newline="\n")

    result.manifest_sha256 = result.manifest.write(out / "manifest.yaml")

    # Check the written bytes rather than trusting that nothing wrote it.
    assert_absent(out, password)
    log(f"✓ {out} · manifest sha256 {result.manifest_sha256[:12]}")
