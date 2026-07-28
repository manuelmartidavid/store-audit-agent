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


# --- stale-path lint ---------------------------------------------------------
#
# Two paths in this repo name things that do not exist. `scripts/` was split by
# concern (decision 28) and `references/rubric.md` never existed — the file is
# `rubric.md` at the root. Both are still cited, and a documented command that
# fails is worse than no documentation: it reads as reproducible and is not.
#
# Frozen artifacts are exempt BY DESIGN, not by oversight. A prompt version's
# bytes are one of decision 12's four provenance pins; editing v1.0's front
# matter to correct a path would invalidate the 21 recorded runs to fix a
# cosmetic error. The alias is recorded in rubric.md's header instead.
_STALE = {
    "scripts/": "split by concern into crawler/ triage/ planting/ (decision 28)",
    "references/rubric.md": "the file is rubric.md at the repo root",
}

# Not just frozen artifacts (prompts/, runs/, _live-check/) — plans/ is exempt
# too, but for a different reason: a plan is a dated proposal, not
# documentation of how to run the system today. The stale spellings inside a
# plan's fenced code blocks are the thing the plan is fixing (this file's own
# plan, 08-measurement-hardening, quotes them as the subject matter under
# repair); marking them line by line would corrupt text later tasks copy
# verbatim.
#
# .superpowers/ is exempt for the identical reason as plans/: task briefs are
# dated proposals that quote the stale paths as the subject matter being
# fixed (this task's own brief describes the "Verified stale" paths), and
# task reports are historical records of a prior task, not live docs.
_EXEMPT = ("prompts/", "runs/", "_live-check/", "plans/", ".superpowers/")


def _live_docs() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("node_modules/", ".git/")) or rel.startswith(_EXEMPT):
            continue
        out.append(path)
    return sorted(out)


@pytest.mark.parametrize("path", _live_docs(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_live_doc_contains_a_known_stale_path_spelling(path: Path):
    """Grep for the literal spellings in `_STALE`. Nothing more.

    This is a denylist of two strings, not a path resolver: it says nothing
    about whether any *other* path a document names actually exists. A dead
    reference to a file that was never on this list passes here silently, and
    one already has. Making it a general resolution check is a different test
    with a real false-positive surface (prose, globs, paths in other repos),
    and is not what this one is.
    """
    text = path.read_text(encoding="utf-8")
    hits = []
    for stale, why in _STALE.items():
        for number, line in enumerate(text.split("\n"), start=1):
            if stale in line and "STALE-OK" not in line:
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number} names {stale!r} — {why}")
    assert not hits, "\n".join(hits)


# --- provenance claims in the labels -----------------------------------------

def test_the_label_file_does_not_claim_to_be_untouched_by_model_output():
    """MC-114…MC-117 were promoted from the unlabeled bucket of v0.4 runs.

    The file's amendment header claimed the opposite — 'nothing here is tuned to
    a model's output' — on the same line that describes the promotion. The claim
    is true of the `match:` blocks and false of the promotions, and a label file
    that overstates its own independence is the one artifact in this project
    that must not.
    """
    text = (ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md").read_text(
        encoding="utf-8")

    # The claim was wrapped across two lines in the indented header block, so a
    # raw substring search never matched it and would have passed against the
    # uncorrected file. Collapse whitespace first or this test asserts nothing.
    flat = " ".join(text.split())
    assert "nothing here is tuned to a model's output" not in flat
    assert "in-sample" in text
    assert "PROMOTION-PROTOCOL" in text


def test_every_citation_of_the_promotion_protocol_resolves():
    """Two documents cited this path before the file existed; it exists now.

    Task 2 wrote the README's triager row and the harness changelog's row 4
    against a file task 9 would create. A forward reference is only a forward
    reference until the file lands — after that it is either a live link or a
    dead one, and nothing else in the suite would notice the difference. This
    checks the spelling both ends agree on, not merely that some file exists.
    """
    cited = "evals/PROMOTION-PROTOCOL.md"
    assert (ROOT / cited).is_file(), f"{cited} does not exist"

    citing = [ROOT / "README.md", ROOT / "evals" / "HARNESS-CHANGELOG.md"]
    missing = [p.relative_to(ROOT).as_posix() for p in citing
               if cited not in p.read_text(encoding="utf-8")]
    assert not missing, f"expected these to cite {cited!r}: {missing}"
