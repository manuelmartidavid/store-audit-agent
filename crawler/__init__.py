"""Store Audit Agent crawler — collects the evidence base for one store.

Importable without Playwright: browser code sits behind lazy imports so the
pure parts stay testable on their own.
"""

__version__ = "0.2.0"

SCHEMA_CRAWL = "crawl/v0.1"
SCHEMA_MANIFEST = "manifest/v0.1"

__all__ = ["__version__", "SCHEMA_CRAWL", "SCHEMA_MANIFEST"]
