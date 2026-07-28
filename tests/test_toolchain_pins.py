"""The toolchain is an input to the ground truth, so it is pinned like one.

Entry 02's labels were measured with lighthouse 12.8.2 / axe-core 4.12.1 /
chrome 149.0.7827.55, and MC-107 sits 85 ms under the 4.0 s boundary. A caret
range lets a clean `npm install` move a label. manifest.yaml records the
versions, so drift is *detectable* — nothing prevented it, and nothing compared
the installed versions to the ones the labels were written against.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml"


def _entry_02_provenance() -> dict:
    data = yaml.safe_load(CONTEXT.read_text(encoding="utf-8")) or {}
    return (data.get("eval") or {}).get("fixtures") or {}


def test_package_json_pins_exact_versions():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    loose = {name: spec for name, spec in pkg["dependencies"].items()
             if not spec[:1].isdigit()}
    assert not loose, f"not pinned to an exact version: {loose}"


def test_requirements_pins_exact_versions():
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").split("\n")]
    reqs = [line for line in lines if line and not line.startswith("#")]
    loose = [line for line in reqs if "==" not in line]
    assert not loose, f"not pinned to an exact version: {loose}"


def test_node_pins_match_the_versions_entry_02_was_labeled_under():
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    packages = lock["packages"]
    provenance = _entry_02_provenance()
    assert packages["node_modules/lighthouse"]["version"] == provenance["lighthouse_version"]
    assert packages["node_modules/axe-core"]["version"] == provenance["axe_core_version"]


def test_package_json_and_lock_agree():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for name, spec in pkg["dependencies"].items():
        assert lock["packages"][f"node_modules/{name}"]["version"] == spec, name
