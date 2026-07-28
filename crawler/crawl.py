"""Crawl orchestration — the shape of a run, spec §2–§8.

This module owns the order of operations and nothing else: the gate, then
discovery, then captures, then Lighthouse, then the four output files. Every
judgement it makes is a recording judgement — *what happened*, never *what it
means*. A div-based add-to-cart button leaves here as a div with its attributes.
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
from .config import TEMPLATES, THROTTLING_PROFILE
from .discovery import (
    ALL_LINKS_SELECTOR,
    NAV_SELECTOR,
    PRODUCT_LINK_SELECTOR,
    pick_collection,
    pick_product,
    pinned_target,
    random_404_path,
    same_origin,
    static_targets,
)
from .distill import distill
from .fingerprint import Signals, build as build_fingerprint, empty as empty_fingerprint
from .lighthouse import run as run_lighthouse, version as lighthouse_version
from .manifest import Manifest
from .redaction import assert_absent
from .robots import Robots
from .session import Session


@dataclass
class Options:
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
    crawl: dict[str, Any]
    manifest: Manifest
    manifest_sha256: str | None = None
    lighthouse_count: int = 0
    axe_count: int = 0
    fetches: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _blank_template(url: str | None = None, status: str = "absent") -> dict[str, Any]:
    """Always all five keys. Absence must be distinguishable from omission."""
    return {
        "url": url,
        "status": status,
        "http_status": None,
        "distilled": None,
        "dropped": None,
    }


def crawl(options: Options, *, log=print) -> Result:
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
            # Carry the gate session into the context Lighthouse audits in.
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
    # A store that was not observed reports platform "unknown" even when the page
    # that blocked us is recognisably Shopify (MNC-003, enforced here rather than
    # in the prompt — the cheapest place to enforce anything).
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
    """robots.txt is fetched first and respected (spec §3)."""
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
    static = static_targets(origin)

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
    capture("home", static["home"])

    # collection: first /collections/{handle} in the home nav, else sitewide,
    # else /collections/all (spec §3 table).
    collection_url = pinned_target(pinned, "collection", origin)
    if collection_url:
        log(f"· collection: pinned {collection_url}")
    elif templates["home"]["status"] == "captured":
        collection_url = pick_collection(session.query_links(NAV_SELECTOR), origin)
        if not collection_url:
            collection_url = pick_collection(session.query_links(ALL_LINKS_SELECTOR), origin)
    collection_url = collection_url or urljoin(origin + "/", "/collections/all")
    capture("collection", collection_url)

    # pdp: first product link within the chosen collection, else sitewide.
    pdp_url = pinned_target(pinned, "pdp", origin)
    if pdp_url:
        log(f"· pdp: pinned {pdp_url}")
    else:
        if templates["collection"]["status"] == "captured":
            pdp_url = pick_product(session.query_links(PRODUCT_LINK_SELECTOR), origin)
        if not pdp_url:
            pdp_url = _product_sitewide(session, origin, collection_url, robots, log=log)
    if pdp_url:
        capture("pdp", pdp_url)
    else:
        log("· pdp: no product link found — absent")
        templates["pdp"] = _blank_template(status="absent")

    capture("cart", static["cart"])
    capture("search", static["search"])
    capture("404", urljoin(origin + "/", random_404_path(rng)))


def _product_sitewide(
    session: Session, origin: str, already: str, robots: Robots, *, log
) -> str | None:
    """Fallback product discovery: one extra fetch of /collections/all, no more."""
    fallback = urljoin(origin + "/", "/collections/all")
    if fallback.rstrip("/") == already.rstrip("/") or not robots.allows(fallback):
        return None
    visit = session.goto(fallback)
    if visit.error or (visit.http_status or 500) >= 400:
        return None
    return pick_product(session.query_links(PRODUCT_LINK_SELECTOR), origin)


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
    if not robots.allows(url):
        # A fact for the report, not a gap to route around.
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
        # Acceptance test §10.6, run inline: the same page distilled twice must
        # be byte-identical. Cheap, and it fails at capture time rather than
        # after a fixture has been frozen and labeled.
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
    if not same_origin(final_url, origin):
        return "absent"  # redirected off-origin — recorded, not guessed at
    if template == "404":
        # Whatever the store serves for an unknown path *is* the 404 template.
        # A 200 here is a soft-404 and it is the triager's to interpret.
        # A 5xx is not: it is the platform's error interstitial (observed live:
        # Shopify's "Something went wrong" throttle page on a 503), and
        # capturing it would plant the wrong page as the negative control —
        # Lighthouse and axe would then measure a page that isn't the store.
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
    statuses = [entry["status"] for entry in templates.values()]
    captured = statuses.count("captured")
    if captured == 0:
        return "blocked"
    if "error" in statuses:
        return "partial"
    return "complete"


def _lh_status(template, templates, lighthouse, requested: bool) -> str:
    if templates[template]["status"] != "captured":
        return "skipped"
    if not requested:
        return "skipped"
    if lighthouse is None:
        return "skipped"
    return lighthouse.status.get(template, "failed")


# --- output -----------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def _node_count(node: dict[str, Any] | None) -> int:
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
    out = options.out_dir
    out.mkdir(parents=True, exist_ok=True)

    (out / "crawl.json").write_text(_canonical_json(result.crawl) + "\n", encoding="utf-8", newline="\n")

    lhrs = lighthouse.lhrs if lighthouse else []
    (out / "lighthouse.json").write_text(_canonical_json(lhrs) + "\n", encoding="utf-8", newline="\n")

    ordered_axe = [axe_results[t] for t in TEMPLATES if t in axe_results]
    (out / "axe.json").write_text(_canonical_json(ordered_axe) + "\n", encoding="utf-8", newline="\n")

    result.manifest_sha256 = result.manifest.write(out / "manifest.yaml")

    # "The password value never appears in any output file" — verified, not asserted.
    assert_absent(out, password)
    log(f"✓ {out} · manifest sha256 {result.manifest_sha256[:12]}")
