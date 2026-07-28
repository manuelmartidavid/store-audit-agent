"""Store Audit Agent crawler.

Produces the deterministic evidence base for one store, per specs/crawler.md v0.1.

The package is importable without Playwright installed: everything that touches a
browser lives behind lazy imports so the pure layers (distillation, pointers,
fingerprint scoring) stay unit-testable on a bare interpreter.
"""

__version__ = "0.2.0"

SCHEMA_CRAWL = "crawl/v0.1"
SCHEMA_MANIFEST = "manifest/v0.1"

__all__ = ["__version__", "SCHEMA_CRAWL", "SCHEMA_MANIFEST"]
