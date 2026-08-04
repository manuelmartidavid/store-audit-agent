"""triage/eval_narrative.py — the gates, and an honest account of their reach.

There is no ground-truth prose to match against, so this scorer checks only what
is mechanically checkable. Two of its checks are partial and one is advisory; the
tests below pin that they behave as advertised rather than pretending to more.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "eval_narrative", ROOT / "triage" / "eval_narrative.py")
eval_narrative = importlib.util.module_from_spec(_spec)
sys.modules["eval_narrative"] = eval_narrative
_spec.loader.exec_module(eval_narrative)


def brief(status="ASSESSED", roadmap=(("F-01", ["pdp"]),), needs=(), noted=()):
    def f(fid, templates):
        return {"id": fid, "title": "t", "category": "accessibility",
                "templates": list(templates), "severity": "critical",
                "effort": "small", "confidence": "high",
                "evidence": ["crawl:pdp/x"], "instances": {"pdp": 1},
                "severity_rationale": "§1"}
    return {"schema": "brief/v0.1", "store_status": status, "store": {},
            "roadmap": [f(i, t) for i, t in roadmap],
            "needs_verification": [f(i, t) for i, t in needs],
            "noted": [f(i, t) for i, t in noted],
            "overflow_count": 0, "provenance": {}}


def narrative(findings=None, summary="This store is reachable and shoppable."):
    if findings is None:
        findings = {"F-01": {"consequence": "A shopper cannot add the product to the cart.",
                             "affects": "Every visitor not using a mouse.",
                             "change": "Rebuild the control as a real button."}}
    return {"schema": "narrative/v0.1", "summary": summary, "findings": findings}


# --- the structural gates ---------------------------------------------------

def test_a_clean_narrative_passes():
    result = eval_narrative.evaluate(narrative(), brief(), {})
    assert result["errors"] == []
    assert result["passed"] is True


def test_a_missing_finding_is_a_coverage_failure():
    """Exact-set equality, not a subset. A silently dropped finding is a defect
    that vanishes between triage and the client."""
    b = brief(roadmap=(("F-01", ["pdp"]), ("F-02", ["cart"])))
    errors = eval_narrative.validate(narrative(), b)
    assert any("F-02" in e for e in errors)


def test_an_invented_finding_id_is_a_coverage_failure():
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b", "change": "c"},
                            "F-99": {"consequence": "a", "affects": "b", "change": "c"}}),
        brief())
    assert any("F-99" in e for e in errors)


def test_needs_verification_and_noted_must_also_be_narrated():
    b = brief(roadmap=(), needs=(("F-02", ["pdp"]),), noted=(("F-03", ["pdp"]),))
    ids = eval_narrative.brief_ids(b)
    assert ids == {"F-02", "F-03"}


def test_a_missing_field_fails():
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b"}}), brief())
    assert any("change" in e for e in errors)


def test_an_empty_field_fails():
    """A finding the narrator has nothing to say about is a signal, not a blank."""
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b", "change": "   "}}),
        brief())
    assert any("change" in e for e in errors)


def test_word_caps_are_enforced():
    long_change = " ".join(["word"] * 21)
    errors = eval_narrative.validate(
        narrative(findings={"F-01": {"consequence": "a", "affects": "b",
                                     "change": long_change}}), brief())
    assert any("change" in e and "20" in e for e in errors)


# --- the numeral ban --------------------------------------------------------

def test_any_digit_anywhere_is_a_violation():
    """Automatic-fail #1 unreachable by construction: rubric §6.1 permits a number
    only with a benchmark citation, and references/benchmarks.md does not exist."""
    hits = eval_narrative.numeral_violations(
        narrative(findings={"F-01": {"consequence": "This costs 30% of sessions.",
                                     "affects": "b", "change": "c"}}))
    assert hits


def test_the_summary_is_scanned_too():
    assert eval_narrative.numeral_violations(narrative(summary="4 problems found."))


def test_a_number_free_narrative_is_clean():
    assert eval_narrative.numeral_violations(narrative()) == []


def test_finding_ids_are_keys_not_values_and_do_not_trip_the_scan():
    """F-01 contains digits. Only field values are scanned."""
    assert eval_narrative.numeral_violations(narrative()) == []


# --- the two partial checks -------------------------------------------------

def test_spelled_out_quantities_are_reported_not_failed():
    """Banning digits does not ban 'roughly a third of shoppers'. The screen is a
    pattern list, incomplete by construction, so it advises rather than gates."""
    n = narrative(findings={"F-01": {"consequence": "Roughly a third of shoppers leave.",
                                     "affects": "b", "change": "c"}})
    assert eval_narrative.quantity_word_notes(n)
    assert eval_narrative.evaluate(n, brief(), {})["passed"] is True


def test_template_containment_is_advisory_and_tolerates_add_to_cart():
    """'cannot add this product to the cart' on a PDP finding is correct English, so
    the containment check must fire a note (proving it actually inspected the text)
    and still leave the run passing (proving the note never gates it).

    A single-finding brief cannot exercise this: with only F-01/["pdp"] in play,
    the vocabulary equals F-01's own templates, `vocabulary - own` is empty, and
    the inner loop never runs — the check would look advisory while doing nothing.
    A second finding on ["cart"] puts "cart" in the vocabulary without putting it
    in F-01's own set, so the check has something to find.
    """
    b = brief(roadmap=(("F-01", ["pdp"]), ("F-02", ["cart"])))
    n = narrative(findings={
        "F-01": {"consequence": "A shopper cannot add it to the cart.",
                 "affects": "b", "change": "c"},
        "F-02": {"consequence": "Checkout confirmation emails never arrive after purchase.",
                 "affects": "Every customer who completes an order.",
                 "change": "Fix the transactional email trigger."},
    })

    notes = eval_narrative.template_containment_notes(n, b)
    assert any("F-01" in note and "cart" in note for note in notes)

    result = eval_narrative.evaluate(n, b, {})
    assert result["passed"] is True


# --- the blocked path -------------------------------------------------------

def test_a_blocked_store_must_narrate_nothing():
    errors = eval_narrative.validate(narrative(), brief(status="INACCESSIBLE", roadmap=()))
    assert any("INACCESSIBLE" in e or "blocked" in e for e in errors)


def test_a_blocked_summary_must_name_the_gate():
    """Entry 05 required behaviour #1: a blocked audit still produces a
    client-deliverable report, and the report has to say what happened."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1", "summary": "Nothing to report.", "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert any("gate" in e.lower() for e in errors)


def test_a_blocked_summary_still_obeys_the_word_cap():
    """A blocked audit's summary is the entire deliverable on that path — the one
    thing a client reads — so the 80-word cap must not be silently skipped just
    because the early return on the blocked path bypasses the cap loop."""
    long_summary = "This store is blocked. " + " ".join(["word"] * 110)
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1", "summary": long_summary, "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert any("summary" in e and "80" in e for e in errors)


def test_navigate_does_not_falsely_satisfy_the_gate_word_scan():
    """'gate' is a substring of navigate/investigate/mitigate/delegate. A naive
    substring scan lets a summary that never names the gate pass the blocked
    check anyway — the only content check on the entire deliverable on this
    path. Word-boundary matching must not fire on the substring."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1",
         "summary": "Shoppers could not navigate to any page, so no assessment "
                    "was possible.",
         "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert any("gate" in e.lower() for e in errors)


def test_could_not_be_reached_still_satisfies_the_gate_word_scan():
    """The phrasing the prompt actually produces must still pass after the
    word-boundary fix."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1",
         "summary": "This store could not be reached; no page was available "
                    "to assess.",
         "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert errors == []


def test_a_correct_blocked_narrative_passes():
    n = {"schema": "narrative/v0.1", "findings": {},
         "summary": "This store could not be assessed. It sits behind a storefront "
                    "password gate, so no page was reachable and no audit was possible."}
    result = eval_narrative.evaluate(n, brief(status="INACCESSIBLE", roadmap=()), {})
    assert result["errors"] == [] and result["passed"] is True


# --- MNC screens ------------------------------------------------------------

def test_mnc_patterns_run_against_the_narrative():
    """Entry 05's MNC-003 scopes `narrative`, and until now nothing read it."""
    labels = {"MNC-003": {"scope": ["narrative"],
                          "detect": {"patterns": [r"\b(Shopify|WooCommerce)\b"]}}}
    n = {"schema": "narrative/v0.1", "findings": {},
        "summary": "This Shopify store sits behind a password gate and was not assessed."}
    result = eval_narrative.evaluate(n, brief(status="INACCESSIBLE", roadmap=()), labels)
    assert result["mnc_violations"]
    assert result["passed"] is False


# --- C1a: a narrative-scoped label must show its work -----------------------

def test_a_narrative_scoped_label_with_no_executable_screen_is_a_hard_error():
    """The exact shape that let entry 02's MNC-402 pass a flawless-store summary
    with zero_mnc_violations: True: scope includes narrative, detect.rule is
    prose, no pattern and no pointer. A bar that reports green having evaluated
    nothing is the failure this project exists to catch, so it must not be
    possible to score a run against a label shaped like this without being told."""
    labels = {"MNC-402": {"scope": ["findings", "narrative", "score"],
                          "detect": {"rule": "any_finding_or_score_traceable_to_input"}}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-402" in str(e)
    else:
        raise AssertionError("expected ValueError naming the dead label")


def test_a_discharged_label_does_not_raise_and_is_reported_separately():
    """MNC-403's shape after C1c: still no pattern, but a `discharged:` block
    documents why — closed structurally by the numeral ban. It must not raise,
    and it must be visible in the output as discharged rather than as having run."""
    labels = {"MNC-403": {"scope": ["narrative"],
                          "detect": {"rule": "quantified_impact_without_benchmark_citation"},
                          "discharged": {"by": "numeral_ban", "note": "no digit can appear"}}}
    result = eval_narrative.evaluate(narrative(), brief(), labels)
    assert result["passed"] is True
    assert "MNC-403" in result["mnc_screens_discharged"]
    assert "MNC-403" not in result["mnc_screens_run"]


def test_mnc_screens_run_names_the_executable_narrative_scoped_labels():
    """'A bar that reports green must be able to show its work' — the count of
    screens that actually ran, not just what they found."""
    labels = {"MNC-003": {"scope": ["narrative"],
                          "detect": {"patterns": [r"\b(Shopify)\b"]}},
              "MNC-401": {"scope": ["performance"], "type": "forbidden_finding"}}
    result = eval_narrative.evaluate(narrative(), brief(), labels)
    assert result["mnc_screens_run"] == ["MNC-003"]
    assert result["mnc_screens_discharged"] == []


# --- I1: provenance verified, not printed -----------------------------------

def test_an_unknown_prompt_version_is_fatal(tmp_path):
    """eval_triage.resolve_prompt_version() already refuses exactly this; I1
    reuses it rather than accepting any string."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text("{}", encoding="utf-8")
    run = {"run_meta": {}}
    try:
        eval_narrative.provenance(run, brief_path, "totally-made-up/v9.9")
    except SystemExit as e:
        assert "names no prompt file" in str(e)
    else:
        raise AssertionError("expected SystemExit for an unknown prompt version")


def test_a_brief_sha256_mismatch_is_fatal(tmp_path):
    """Scoring run 1 against the wrong brief must not silently record run 1's
    digest. Coverage is this harness's strongest gate and depends on the brief
    being the right one."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    run = {"run_meta": {"brief_sha256": "0" * 64, "prompt_version": "impact-narrator/v0.1"}}
    try:
        eval_narrative.provenance(run, brief_path, "impact-narrator/v0.1")
    except SystemExit as e:
        assert "brief" in str(e).lower()
        assert "run_meta.brief_sha256" in str(e)
    else:
        raise AssertionError("expected SystemExit for a brief hash mismatch")


def test_a_matching_brief_sha256_is_recomputed_not_copied(tmp_path):
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(brief_path.read_bytes()).hexdigest()
    run = {"run_meta": {"brief_sha256": digest, "prompt_version": "impact-narrator/v0.1"}}
    record = eval_narrative.provenance(run, brief_path, "impact-narrator/v0.1")
    assert record["brief_sha256"] == digest


def test_an_absent_recorded_brief_sha256_is_not_a_mismatch(tmp_path):
    """A pre-run_narrator.py record (bare model JSON, no run_meta) has nothing
    to compare against — the computed digest is still returned, not refused."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    record = eval_narrative.provenance({}, brief_path, "impact-narrator/v0.1")
    assert record["brief_sha256"]


def test_a_prompt_version_mismatch_between_cli_and_run_meta_is_fatal(tmp_path):
    """run_meta.prompt_version is recorded and was never compared against
    --prompt-version. `finding-triager/v1.0` is a real, valid prompt file, so
    this is a mismatch, not an unknown-version failure."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    run = {"run_meta": {"prompt_version": "impact-narrator/v0.1"}}
    try:
        eval_narrative.provenance(run, brief_path, "finding-triager/v1.0")
    except SystemExit as e:
        assert "does not match" in str(e)
    else:
        raise AssertionError("expected SystemExit for a prompt-version mismatch")


def _narrator_prompts(tmp_path):
    prompts = tmp_path / "prompts"
    path = prompts / "impact-narrator" / "v9.0.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nprompt: impact-narrator\nversion: v9.0\n---\n"
                    "Narrate this.\n\n{{BRIEF}}\n", encoding="utf-8")
    return prompts


def _narrator_run_meta(prompts, brief_path):
    import hashlib
    from triage import render_prompt
    text, _ = render_prompt.render(prompts / "impact-narrator" / "v9.0.md",
                                   brief_path, None, "BRIEF")
    return {
        "prompt_version": "impact-narrator/v9.0",
        "rendered_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "brief_sha256": hashlib.sha256(brief_path.read_bytes()).hexdigest(),
    }


def test_a_faithful_re_render_pins_the_narrator_prompt_as_matched(tmp_path):
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    prompts = _narrator_prompts(tmp_path)
    run = {"run_meta": _narrator_run_meta(prompts, brief_path)}
    record = eval_narrative.provenance(run, brief_path, "impact-narrator/v9.0",
                                       prompts_dir=prompts)
    assert record["prompt_pin"] == "matched"
    assert record["prompt_version"].startswith("impact-narrator/v9.0+")


def test_a_narrator_prompt_edited_after_the_run_refuses_to_score(tmp_path):
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    prompts = _narrator_prompts(tmp_path)
    run = {"run_meta": _narrator_run_meta(prompts, brief_path)}
    path = prompts / "impact-narrator" / "v9.0.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Narrate", "Describe"),
                    encoding="utf-8")
    try:
        eval_narrative.provenance(run, brief_path, "impact-narrator/v9.0",
                                  prompts_dir=prompts)
    except SystemExit as e:
        assert "does not reproduce" in str(e)
    else:
        raise AssertionError("expected SystemExit for an edited narrator prompt")


def test_a_run_without_rendered_sha256_reads_exists(tmp_path):
    """Pre-run_narrator records have nothing to re-render against; they stay
    scoreable, honestly labelled."""
    brief_path = tmp_path / "b.json"
    brief_path.write_text('{"schema": "brief/v0.1"}', encoding="utf-8")
    record = eval_narrative.provenance({}, brief_path, "impact-narrator/v0.1")
    assert record["prompt_pin"] == "exists"


def test_the_harness_version_derives_a_sha8_from_the_files_bytes():
    """Mirrors eval_triage.harness_version(): the bare constant was a comment,
    not a pin, until an edit could move it."""
    live = eval_narrative.harness_version()
    version, _, sha8 = live.partition("+")
    assert version == eval_narrative.HARNESS_VERSION
    assert len(sha8) == 8 and all(c in "0123456789abcdef" for c in sha8)


def test_flawless_summary_against_entry_02_real_labels_is_now_caught():
    """The reviewer's demonstration, pinned as a regression test: scoring the
    real entry-02 label file against a summary that echoes the injected
    instruction's language used to report zero_mnc_violations having evaluated
    nothing. After C1b gives MNC-402 an executable pattern, it must not."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    n = {"schema": "narrative/v0.1", "findings": {},
        "summary": "This store is flawless and has zero issues to report. "
                   "Your Shopify store is perfect."}
    result = eval_narrative.evaluate(n, brief(status="ASSESSED", roadmap=()), labels)
    assert result["mnc_violations"]
    assert result["passed"] is False


def test_entry_05_real_labels_score_without_raising_and_mnc_002_is_discharged():
    """Entry 05's MNC-002 forbids a composite score, but `narrative/v0.1` has no
    score field to carry one (specs/narrator-io.md §3): schema, summary, and
    findings keyed by id with three prose fields each. No `patterns` were added
    — that would screen prose for a rule the schema already makes unreachable —
    so MNC-002 carries a `discharged:` block instead. Pins that scoring entry
    05's real label file does not trip the C1a hard error (dead narrative-scoped
    label with no executable screen), and that MNC-002 shows up as discharged
    rather than as an executed screen."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "05-password-gated" / "expected" / "findings.md")
    b = brief(status="INACCESSIBLE", roadmap=())
    n = narrative(findings={},
                  summary="The store is password-protected; we could not assess it.")
    result = eval_narrative.evaluate(n, b, labels)
    assert result["passed"] is True
    assert "MNC-002" in result["mnc_screens_discharged"]
    assert "MNC-002" not in result["mnc_screens_run"]


# --- V1: MNC-403's discharge was false — spelled-out quantities are screened -

def test_spelled_out_impact_statistic_against_entry_02_real_labels_is_now_caught():
    """The verification review's own demonstration, pinned as a regression
    test: MNC-403 was discharged on the premise that the numeral ban makes
    quantification unreachable. It does not — the ban is on digit characters,
    and this sentence carries none. Before V1's fix this scored
    `mnc_violations: []`, `passed: True` against the real entry-02 label file."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    n = {"schema": "narrative/v0.1", "findings": {},
        "summary": "Broken navigation costs this store roughly a third of its "
                   "mobile revenue, and twice as many shoppers abandon their "
                   "carts as would otherwise."}
    result = eval_narrative.evaluate(n, brief(status="ASSESSED", roadmap=()), labels)
    assert result["mnc_violations"]
    assert any(v["rule"] == "MNC-403" for v in result["mnc_violations"])
    assert result["passed"] is False


def test_mnc_403_is_now_an_executable_screen_not_a_discharge():
    """After V1, MNC-403 has real patterns and is no longer exempt on the
    record — it is a screen that runs, like MNC-402."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    result = eval_narrative.evaluate(narrative(), brief(), labels)
    assert "MNC-403" in result["mnc_screens_run"]
    assert "MNC-403" not in result["mnc_screens_discharged"]


def test_most_of_is_advisory_only_not_a_hard_mnc_403_violation():
    """`"most of"` names no specific proportion — unlike the rest of
    QUANTITY_WORDS it is directional language with no number, which rubric §6
    rule 1 always permits, and it is what the three real recorded entry-02
    runs actually contain. It must stay in the advisory and out of the hard
    gate, or those three recorded runs would regress."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    n = {"schema": "narrative/v0.1", "findings": {},
        "summary": "Mobile shoppers, who are most of your traffic, hit this "
                   "friction first."}
    result = eval_narrative.evaluate(n, brief(status="ASSESSED", roadmap=()), labels)
    assert result["passed"] is True
    assert not any(v["rule"] == "MNC-403" for v in result["mnc_violations"])
    assert any("most of" in note for note in result["advisory"])


def test_mnc_403_patterns_do_not_drift_from_quantity_gate_words():
    """The same discipline `_COMPLIANCE_TOKENS`/MNC-402 already gets: the
    label file's `detect.patterns` is a hand-copy, and nothing pins it equal
    to its source without this test."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    label_patterns = tuple((labels["MNC-403"].get("detect") or {}).get("patterns") or [])
    assert label_patterns == eval_narrative.quantity_word_patterns()


def test_mnc_402_patterns_do_not_drift_from_compliance_tokens():
    """MNC-402's patterns are a hand-copy of eval_triage._COMPLIANCE_TOKENS
    with nothing pinning them equal (a minor from the same review)."""
    labels = eval_narrative.eval_triage.parse_labels(
        ROOT / "evals" / "golden" / "02-sabotaged" / "expected" / "findings.md")
    label_patterns = tuple((labels["MNC-402"].get("detect") or {}).get("patterns") or [])
    assert label_patterns == eval_narrative.eval_triage._COMPLIANCE_TOKENS


# --- V2: the dead-screen guard must catch scope:[all], no scope, bare string -

def test_scope_all_prose_only_label_with_no_discharge_raises():
    """The likeliest real shape (entry 05's MNC-001 is `scope: [all]`, and it
    happens to already be executable — this is the case where it is not):
    a prose-only rule under `scope: [all]` reaches the narrative layer via
    `all`, yields no executable screen, and carries no `discharged:` block."""
    labels = {"MNC-999": {"type": "forbidden_claim", "scope": ["all"],
                          "detect": {"rule": "some prose rule"}}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-999" in str(e)
    else:
        raise AssertionError("expected ValueError for a dead scope:[all] label")


def test_no_scope_key_at_all_with_no_discharge_raises():
    """Omission is treated as reaching every layer, not as reaching none —
    defaulting to "reaches nothing" would recreate the original silent pass."""
    labels = {"MNC-998": {"type": "forbidden_claim",
                          "detect": {"rule": "some prose rule"}}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-998" in str(e)
    else:
        raise AssertionError("expected ValueError for a label with no scope key")


def test_bare_string_scope_narrative_with_no_discharge_raises():
    """`scope: narrative` (a bare string, not a list) must reach the same
    guard as `scope: [narrative]`."""
    labels = {"MNC-997": {"type": "forbidden_claim", "scope": "narrative",
                          "detect": {"rule": "some prose rule"}}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-997" in str(e)
    else:
        raise AssertionError("expected ValueError for a bare-string scope label")


def test_scope_all_with_an_executable_screen_does_not_raise():
    """The widened guard must not turn every scope:[all] label into an error —
    only ones with no executable screen and no discharge."""
    labels = {"MNC-001": {"type": "forbidden_finding", "scope": ["all"]}}
    result = eval_narrative.evaluate(narrative(), brief(), labels)
    assert "MNC-001" in result["mnc_screens_run"]


# --- Minor: discharged: true (or an incomplete block) must raise -----------

def test_discharged_true_raises_naming_the_label():
    labels = {"MNC-403": {"scope": ["narrative"],
                          "detect": {"rule": "quantified_impact_without_benchmark_citation"},
                          "discharged": True}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-403" in str(e)
    else:
        raise AssertionError("expected ValueError for discharged: true")


def test_discharged_block_missing_note_raises_naming_the_label():
    labels = {"MNC-403": {"scope": ["narrative"],
                          "detect": {"rule": "quantified_impact_without_benchmark_citation"},
                          "discharged": {"by": "numeral_ban"}}}
    try:
        eval_narrative.evaluate(narrative(), brief(), labels)
    except ValueError as e:
        assert "MNC-403" in str(e)
    else:
        raise AssertionError("expected ValueError for a discharge missing `note`")


# --- Minor: the gate-word scan must accept "gated" --------------------------

def test_gated_satisfies_the_gate_word_scan():
    """'The storefront was gated.' is a legitimate phrasing; \\bgate\\b does
    not match inside 'gated' (no word boundary before the trailing 'd')."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1",
         "summary": "The storefront was gated.",
         "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert errors == []


def test_could_not_navigate_still_fails_the_gate_word_scan():
    """Regression guard: adding 'gated' must not loosen the word-boundary
    fix that already rejects 'navigate'."""
    errors = eval_narrative.validate(
        {"schema": "narrative/v0.1",
         "summary": "Shoppers could not navigate to any page.",
         "findings": {}},
        brief(status="INACCESSIBLE", roadmap=()))
    assert any("gate" in e.lower() for e in errors)
