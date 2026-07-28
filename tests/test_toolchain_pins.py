"""The toolchain is an input to the ground truth, so it is pinned like one.

Entry 02's labels were measured with lighthouse 12.8.2 / axe-core 4.12.1 /
chrome 149.0.7827.55, and MC-107 sits 85 ms under the 4.0 s boundary. A caret
range lets a clean `npm install` move a label. manifest.yaml records the
versions, so drift is *detectable* — nothing prevented it, and nothing compared
the installed versions to the ones the labels were written against.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = ROOT / "evals" / "golden" / "02-sabotaged" / "context.yaml"

# npm's exact form is MAJOR.MINOR.PATCH, optionally followed by a
# prerelease (-foo) and/or build (+bar) suffix. A leading ^, ~, >, <, =, v,
# a space, an x/X/* wildcard, or a || alternation all mean "range, not
# pin" -- and a range is exactly what let a clean `npm install` drift
# lighthouse/axe-core past the versions entry 02 was labeled under.
_NPM_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

# A pinned requirements.txt line is exactly one `name==version`: no other
# comparison operator (>=, <=, >, <, ~=, !=) and no comma-separated
# alternatives sharing the line, either of which would let a floor back in
# right next to the `==` that's supposed to rule it out.
_REQ_EXACT_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _entry_02_provenance() -> dict:
    data = yaml.safe_load(CONTEXT.read_text(encoding="utf-8")) or {}
    return (data.get("eval") or {}).get("fixtures") or {}


def test_package_json_pins_exact_versions():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    deps = pkg["dependencies"]
    # An empty dependency set would make the loop below vacuously pass --
    # that's a green test that isn't actually checking anything.
    assert deps, "package.json has no dependencies to check pins against"
    loose = {name: spec for name, spec in deps.items()
             if not _NPM_EXACT_VERSION.fullmatch(spec)}
    assert not loose, f"not pinned to an exact version: {loose}"


def test_requirements_pins_exact_versions():
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").split("\n")]
    reqs = [line for line in lines if line and not line.startswith("#")]
    # Same vacuous-pass hazard as above: reducing the file to comments
    # should not read as "everything is pinned".
    assert reqs, "requirements.txt has no requirement lines to check pins against"
    loose = [line for line in reqs if not _REQ_EXACT_LINE.fullmatch(line)]
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
