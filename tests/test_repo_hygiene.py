"""The repo's own plumbing — the checks that fail silently when they rot.

A collection error is the worst kind of red: pytest reports one error and runs
nothing, so a suite that "has no failures" can be a suite that never ran. This
module imports every sibling test module by path, so a broken import is one
failed test among many rather than a stopped suite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

_MODULES = sorted(p for p in TESTS.glob("test_*.py") if p.name != Path(__file__).name)


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.stem)
def test_every_test_module_imports(path: Path):
    spec = importlib.util.spec_from_file_location(f"_hygiene_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
