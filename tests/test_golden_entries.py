"""Every golden entry's context.yaml, checked as a set.

The entries are checked individually all over this suite; nothing checks them
against EACH OTHER, and the schema has cross-entry rules — `throttling` "must be
identical across all five entries" is one, and it is enforced nowhere.

The rest are the silent failures: a typo in `gates:` passes vacuously (the same
class eval_triage.py:660 raises on), a declared gate with no value was a silent
no-op until step 8, and `id` drifting from the directory prefix would send a
run's provenance to the wrong entry.

Parametrized over the directory glob, so entries 03 and any later ones are
covered the moment they land rather than when somebody remembers to add them.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"

_spec = importlib.util.spec_from_file_location("eval_triage", ROOT / "triage" / "eval_triage.py")
eval_triage = importlib.util.module_from_spec(_spec)
sys.modules["eval_triage"] = eval_triage
_spec.loader.exec_module(eval_triage)

ENTRIES = sorted(GOLDEN.glob("[0-9][0-9]-*/context.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_the_glob_found_the_entries():
    # A walker that silently matches nothing is the vacuous pass it exists to
    # prevent. Entries 01, 02, 04 and 05 exist as of 2026-07-29; the schema
    # expects a fifth (entry 03) eventually. `>=` rather than `==` is
    # deliberate: it still fails hard on the zero-match case a broken glob or a
    # renamed directory convention would produce, but it does not need editing
    # every time a new entry lands — the whole point of walking the glob
    # instead of a hardcoded list.
    assert len(ENTRIES) >= 4, [p.parent.name for p in ENTRIES]


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_has_both_blocks(path: Path):
    data = _load(path)
    assert "store" in data, "the block rendered into the prompt"
    assert "eval" in data, "the harness-only block"


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_eval_id_matches_the_directory_prefix(path: Path):
    prefix = path.parent.name.split("-")[0]
    assert _load(path)["eval"]["id"] == prefix


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_gates_are_known_names(path: Path):
    gates = set(_load(path)["eval"]["expect"].get("gates") or [])
    unknown = gates - eval_triage._KNOWN_GATES
    assert not unknown, f"{sorted(unknown)} is not a gate; known: {sorted(eval_triage._KNOWN_GATES)}"


# ---------------------------------------------------------------------------
# test_declared_gates_have_values — flattened over (entry, gate) rather than
# looped per entry.
#
# The brief's version parametrizes over ENTRIES and loops `for gate in
# expect.get("gates") or []` inside the test body. Entries 02 and 04 both
# declare `gates: []` (deliberately — see their context.yaml comments), so for
# 2 of the 4 current entries that loop body executes zero times and the test
# reports a pass having checked nothing. That is exactly the failure class
# this whole file exists to catch, one level in: a green run that measured
# nothing. Flattening to one test id per (entry, gate) pair makes that
# structurally impossible — an entry with no declared gates simply contributes
# no test id, instead of contributing a test id that always passes.
# `test_some_entry_declares_a_gate` guards the flattened list itself against
# going empty (e.g. if every entry's gates were ever emptied at once).
# ---------------------------------------------------------------------------

_DECLARED_GATES = [
    (p, gate)
    for p in ENTRIES
    for gate in (_load(p)["eval"]["expect"].get("gates") or [])
]


def test_some_entry_declares_a_gate():
    # Guards _DECLARED_GATES against silently covering nothing, the same way
    # test_the_glob_found_the_entries guards ENTRIES.
    assert _DECLARED_GATES, "no entry declares any gate — the check below would be vacuous"


@pytest.mark.parametrize("path,gate", _DECLARED_GATES,
                          ids=[f"{p.parent.name}:{g}" for p, g in _DECLARED_GATES])
def test_declared_gates_have_values(path: Path, gate: str):
    """A gate with no value is a green run that measured nothing."""
    expect = _load(path)["eval"]["expect"]
    if gate == "score_range":
        # Mirrors eval_triage.py's own check exactly (expect_bars, the
        # score_range branch): both KEYS must be present, but null is a real
        # value on each side independently — no bound on that side, and both
        # null together is the blocked-store pass condition (entry 05:
        # score_min and score_max are both null on purpose, gates on
        # score_range, and must pass this test). Asserting `is not None`
        # instead of key-presence would fail entry 05's legitimate case.
        assert "score_min" in expect, "score_range declared but score_min key is absent"
        assert "score_max" in expect, "score_range declared but score_max key is absent"
    else:
        assert expect.get(gate) is not None, f"{gate} declared with no value"


# ---------------------------------------------------------------------------
# test_password_env_names_a_variable_and_never_holds_a_value
#
# Unlike the gates loop above, a null `password_env` is not an unexercised
# check — it IS the check passing: "never holds a value" is satisfied by
# absence. So the per-entry parametrization stays as the brief wrote it. What
# it does need is a guard that the regex branch (the one line that would catch
# an actual committed secret) is not permanently dead: as of 2026-07-29 only
# entry 02 has a non-null password_env. test_some_entry_declares_a_password_env
# makes that explicit instead of leaving it an accident of which entries
# happen to be public.
# ---------------------------------------------------------------------------

def test_some_entry_declares_a_password_env():
    assert any(_load(p)["store"].get("password_env") is not None for p in ENTRIES), (
        "no entry sets password_env — the regex assertion below is never exercised")


@pytest.mark.parametrize("path", ENTRIES, ids=lambda p: p.parent.name)
def test_password_env_names_a_variable_and_never_holds_a_value(path: Path):
    """`password_env` is a NAME. A value here would commit a secret."""
    value = _load(path)["store"].get("password_env")
    if value is not None:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", value), f"{value!r} is not an env var name"


def test_throttling_is_identical_across_every_entry():
    """_schema/context.yaml: "must be identical across all five entries"."""
    profiles = {p.parent.name: (_load(p)["eval"]["fixtures"] or {}).get("throttling")
                for p in ENTRIES}
    assert len(set(profiles.values())) == 1, profiles
