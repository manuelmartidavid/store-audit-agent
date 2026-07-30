"""Drives the browser for one store: navigation, the password gate, and capture (spec §2).

Chromium is launched with a remote-debugging port so the Lighthouse sidecar can
attach to the same browser.

Invariant: never format the storefront password into a string here. It must not
reach any output file, log line, or error message.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .config import (
    MAX_DATA_URI_BYTES,
    MAX_TEXT_CHARS,
    MAX_TRANSIENT_RETRIES,
    MIN_FETCH_INTERVAL_S,
    NAV_TIMEOUT_MS,
    RETRY_BACKOFF_S,
    SETTLE_TIMEOUT_MS,
    TRANSIENT_RETRY_STATUSES,
    USER_AGENT,
)
from .fingerprint import Signals

_JS_DIR = Path(__file__).parent / "js"


def _js(name: str) -> str:
    """Read one of the browser-side scripts from js/."""
    return (_JS_DIR / name).read_text(encoding="utf-8")


@dataclass
class Visit:
    """The outcome of one navigation."""

    url: str            # final URL after redirects
    requested: str
    http_status: int | None
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True if the navigation completed with a response."""
        return self.error is None and self.http_status is not None


@dataclass
class GateResult:
    """What happened when we tried to get past the storefront gate."""

    gate: str                     # none | password_supplied | blocked
    kind: str | None = None         # password_page | bot_challenge | http_error | dns
    evidence: str | None = None
    final_url: str | None = None


class Session:
    """A polite, single-threaded browsing session against one origin."""

    def __init__(
        self,
        origin: str,
        *,
        headless: bool = True,
        debug_port: int | None = None,
        nav_timeout_ms: int = NAV_TIMEOUT_MS,
        min_interval_s: float = MIN_FETCH_INTERVAL_S,
    ) -> None:
        self.origin = origin.rstrip("/")
        self.headless = headless
        self.debug_port = debug_port
        self.nav_timeout_ms = nav_timeout_ms
        self.min_interval_s = min_interval_s

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_fetch = 0.0
        self.fetch_count = 0
        self.browser_version: str | None = None

    # --- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Session":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def start(self) -> None:
        """Launch the browser and open the crawl's page."""
        from playwright.sync_api import sync_playwright  # lazy, so pure code imports without it

        self._playwright = sync_playwright().start()
        args = ["--disable-dev-shm-usage"]
        if self.debug_port:
            args.append(f"--remote-debugging-port={self.debug_port}")
        self._browser = self._playwright.chromium.launch(headless=self.headless, args=args)
        self.browser_version = self._browser.version
        # The crawl gets its own isolated context; Lighthouse uses the browser's
        # default one, with a separate cookie jar.
        # Invariant: keep these two contexts apart — a shared persistent
        # context deadlocks Lighthouse's second run. Cookies are copied over by
        # mirror_session_to_default() instead.
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            ignore_https_errors=False,
        )
        self._context.set_default_navigation_timeout(self.nav_timeout_ms)
        self._page = self._context.new_page()

    def close(self) -> None:
        """Shut the browser down, ignoring anything that fails on the way out."""
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = self._browser = self._context = self._page = None

    @property
    def page(self):
        """The active page. Raises if the session hasn't been started."""
        if self._page is None:
            raise RuntimeError("Session.start() has not been called")
        return self._page

    # --- conduct -----------------------------------------------------------

    def _throttle(self) -> None:
        """Wait so there's at least a second between fetches (spec §3)."""
        elapsed = time.monotonic() - self._last_fetch
        if self._last_fetch and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_fetch = time.monotonic()

    def honour_crawl_delay(self, delay_s: float | None) -> float:
        """Raise the fetch interval to a declared `Crawl-delay`. Returns the effective one.

        Invariant: only ever raises. Our floor is conduct we owe every store
        (brief §5); a store asking for less than it does not get less.
        """
        # Truthiness, not `is not None`, is fine here even though manifest.py
        # was corrected away from it in this same wave: a declared `0` and a
        # missing declaration both fail `> self.min_interval_s` against our
        # >=1s floor, so the two cases are indistinguishable to this
        # comparison — unlike the manifest's null-vs-zero rendering, which
        # they are not indistinguishable to.
        if delay_s and float(delay_s) > self.min_interval_s:
            self.min_interval_s = float(delay_s)
        return self.min_interval_s

    def goto(self, url: str, *, retries: int = MAX_TRANSIENT_RETRIES) -> Visit:
        """Navigate to `url`, retrying 429 and 5xx responses with backoff.

        A 4xx comes back on the first try — the page really is missing.
        """
        visit = self._goto_once(url)
        attempt = 0
        while (
            attempt < retries
            and visit.http_status in TRANSIENT_RETRY_STATUSES
        ):
            time.sleep(RETRY_BACKOFF_S * (attempt + 1))
            attempt += 1
            visit = self._goto_once(url)
        return visit

    def _goto_once(self, url: str) -> Visit:
        """One navigation attempt, recorded as a Visit."""
        self._throttle()
        self.fetch_count += 1
        try:
            response = self.page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:  # a failed navigation is data, not a crash
            return Visit(url=url, requested=url, http_status=None, error=_clean(exc))

        # Give lazy-loaded content a moment, but don't wait on a hung network.
        try:
            self.page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
        except Exception:
            pass

        headers = {}
        status = None
        if response is not None:
            status = response.status
            try:
                headers = {k.lower(): v for k, v in response.headers.items()}
            except Exception:
                headers = {}
        return Visit(url=self.page.url, requested=url, http_status=status, headers=headers)

    def fetch_text(self, url: str) -> tuple[int | None, str]:
        """Fetch a non-HTML file such as robots.txt through the same context."""
        self._throttle()
        try:
            response = self._context.request.get(url, timeout=self.nav_timeout_ms)
            return response.status, response.text()
        except Exception:
            return None, ""

    # --- the gate (spec §2) ------------------------------------------------

    def is_password_page(self) -> bool:
        """True if the current page is the storefront password gate."""
        path = urlparse(self.page.url).path.rstrip("/")
        if path.endswith("/password") or path == "/password":
            return True
        try:
            return self.page.locator("form[action*='/password'] input[type='password']").count() > 0
        except Exception:
            return False

    def open_gate(self, password: str | None) -> GateResult:
        """Open the origin and get past the storefront password page if there is one."""
        visit = self.goto(self.origin + "/")
        if visit.error:
            kind = "dns" if "ERR_NAME_NOT_RESOLVED" in (visit.error or "") else "http_error"
            return GateResult(gate="blocked", kind=kind, evidence=visit.error, final_url=self.origin)

        if visit.http_status is not None and visit.http_status >= 400:
            if visit.http_status in (403, 429) or self._looks_like_challenge():
                return GateResult(
                    gate="blocked",
                    kind="bot_challenge",
                    evidence=f"HTTP {visit.http_status} on origin; challenge markers present",
                    final_url=visit.url,
                )
            return GateResult(
                gate="blocked",
                kind="http_error",
                evidence=f"HTTP {visit.http_status} on origin",
                final_url=visit.url,
            )

        if not self.is_password_page():
            return GateResult(gate="none", final_url=visit.url)

        evidence = self._gate_evidence(visit)
        if not password:
            return GateResult(
                gate="blocked", kind="password_page", evidence=evidence, final_url=visit.url
            )

        if self._submit_password(password):
            return GateResult(gate="password_supplied", final_url=self.page.url)
        # Rejected. Evidence describes the gate, never the password we tried.
        return GateResult(
            gate="blocked",
            kind="password_page",
            evidence=evidence + "; password rejected",
            final_url=self.page.url,
        )

    def _gate_evidence(self, visit: Visit) -> str:
        """A short description of how we know this is a password gate."""
        parts = []
        if visit.requested.rstrip("/") != visit.url.rstrip("/"):
            parts.append(f"redirect {visit.requested} → {urlparse(visit.url).path}")
        try:
            if self.page.locator("form[action*='/password']").count():
                parts.append("form[action='/password']")
        except Exception:
            pass
        return "; ".join(parts) or "storefront password page served at origin"

    def _looks_like_challenge(self) -> bool:
        """True if the page looks like a bot check rather than the store."""
        try:
            body = (self.page.content() or "").lower()
        except Exception:
            return False
        return any(m in body for m in ("cf-challenge", "just a moment", "captcha", "cf-browser-verification"))

    def _submit_password(self, password: str) -> bool:
        """Submit the gate form and check where we landed. Never logs the password."""
        try:
            field_ = self.page.locator(
                "form[action*='/password'] input[type='password'], input[name='password']"
            ).first
            field_.fill(password, timeout=self.nav_timeout_ms)
            self._throttle()
            self.fetch_count += 1
            with self.page.expect_navigation(wait_until="domcontentloaded", timeout=self.nav_timeout_ms):
                field_.press("Enter")
        except Exception:
            return False

        # Check where we ended up rather than assuming the POST worked.
        if self.is_password_page():
            return False
        try:
            if any(c.get("name") == "storefront_digest" for c in self._context.cookies()):
                return True
        except Exception:
            pass
        return True  # non-Shopify gates don't set that cookie, and we're through

    # --- capture -----------------------------------------------------------

    def walk_dom(self) -> tuple[dict[str, Any], dict[str, int]]:
        """Turn the current page into a raw tree plus counts of what was dropped."""
        result = self.page.evaluate(_js("dom_walk.js"), [MAX_DATA_URI_BYTES, MAX_TEXT_CHARS])
        return result["raw"], result["dropped"]

    def collect_signals(self, visit: Visit) -> Signals:
        """Gather the fingerprinting signals from the current page."""
        try:
            raw = self.page.evaluate(_js("signals.js"))
        except Exception:
            raw = {}
        cookies: list[str] = []
        try:
            cookies = [c.get("name", "") for c in self._context.cookies()]
        except Exception:
            pass
        return Signals(
            urls=[urljoin(visit.url, u) for u in raw.get("urls", [])],
            inline_scripts=raw.get("inline_scripts", []),
            meta=raw.get("meta", {}) or {},
            headers=visit.headers,
            cookies=cookies,
            shopify_global=bool(raw.get("shopify_global")),
            shopify_theme=raw.get("shopify_theme"),
            body_classes=raw.get("body_classes", []) or [],
        )

    def mirror_session_to_default(self) -> int:
        """Copy the crawl's cookies into the browser's default context.

        This is what lets Lighthouse see the store behind the gate instead of
        the password page. Returns how many cookies were copied; a public store
        has none, which is fine.
        """
        try:
            cookies = self._context.cookies()
        except Exception:
            return 0
        if not cookies:
            return 0

        params: list[dict[str, Any]] = []
        for cookie in cookies:
            name = cookie.get("name")
            if not name:
                continue
            entry: dict[str, Any] = {
                "name": name,
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            expires = cookie.get("expires")
            if expires and expires > 0:
                entry["expires"] = expires
            if cookie.get("httpOnly"):
                entry["httpOnly"] = True
            if cookie.get("secure"):
                entry["secure"] = True
            same_site = cookie.get("sameSite")
            if same_site in ("Strict", "Lax", "None"):
                entry["sameSite"] = same_site
            params.append(entry)

        try:
            cdp = self._browser.new_browser_cdp_session()
            cdp.send("Storage.setCookies", {"cookies": params})
            cdp.detach()
        except Exception:
            return 0
        return len(params)

    def query_links(self, selector: str) -> list[str]:
        """Absolute hrefs matching a selector, in document order."""
        try:
            hrefs = self.page.eval_on_selector_all(
                selector,
                "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
            )
        except Exception:
            return []
        return [urljoin(self.page.url, h) for h in hrefs]


def _clean(exc: Exception) -> str:
    """A one-line error message, capped in length."""
    return str(exc).strip().splitlines()[0][:300] if str(exc).strip() else exc.__class__.__name__
