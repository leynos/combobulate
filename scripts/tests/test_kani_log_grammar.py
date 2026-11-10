"""Hold the Kani grammar's pure surfaces to the refusal each one exists for.

Three parts of the parser are pure enough to test without a log: the manifest
types, which refuse an entry the decision could only guess at; the reader's
structural errors, which name the construct the cursor wanted; and the split
between a counterexample and an ``unsupported`` verdict, which turns on which
evidence Kani printed rather than on how bad the run looked.

Each assertion names the *reason* a refusal gives rather than merely that one
happened. That is the whole point of these surfaces: every caller collapses a
refusal to one reason code, so the sentence is the only part of a refusal a
record's author can act on.

Examples
--------
>>> refused_manifest({'harnesses': []})
'the harness manifest declares no harnesses'
>>> refusal_text(lambda: Harness('h::k', 'control'))
"control 'h::k' names no property it is expected to fail"
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kani_corpus_fixtures as corpus
import kani_decision_fixtures as facts
from docs_validation.kani_log import (
    CLAIM, CONTROL, FailedCheck, Harness, Manifest, manifest_from_document,
)
from kani_log_text_fixtures import EXPECTED, RESULTS, SUMMARY, TIME, VERIFICATION, lines_of, refused


def refusal_text(build) -> str:
    """Return the message a constructor or parser refused with, or an empty string."""
    try:
        build()
    except ValueError as error:
        return str(error)
    return ''


def refused_manifest(document) -> str:
    """Return the bare reason ``manifest_from_document`` refuses a document with."""
    return refusal_text(lambda: manifest_from_document(document))


class ManifestDocuments(unittest.TestCase):
    """Refuse every document shape the decision could only guess at.

    A committed manifest is read from JSON a record binds, so a malformed one is
    not an internal inconsistency but an artefact defect. Each refusal therefore
    has to say which entry is wrong and in what way.
    """

    def test_a_document_without_a_harnesses_array_is_refused(self):
        """Require the missing array to be named, whether it is absent or another type."""
        for document in ({}, {'harnesses': {}}, {'harnesses': None}):
            with self.subTest(document=document):
                self.assertEqual(refused_manifest(document), 'the harness manifest has no harnesses array',
                                 'a document with no harnesses array must say so')

    def test_an_entry_without_a_name_and_role_is_refused(self):
        """Name the offending entry so a manifest author can find it.

        The repr is the only locator a malformed entry has: it may have no name
        at all, which is exactly the case being refused.
        """
        for entry in ('x', {'role': 'claim'}, {'name': 'h::x'}, {'name': 'h::x', 'role': 3}):
            with self.subTest(entry=entry):
                self.assertEqual(refused_manifest({'harnesses': [entry]}),
                                 f'harness manifest entry {entry!r} does not name a harness and a role',
                                 'an entry without a string name and role must be named by its repr')

    def test_a_malformed_covers_list_is_refused_and_names_the_harness(self):
        """Require covers to be a list of strings, with the harness named."""
        for covers in ('a cover', [1], ['ok', None]):
            with self.subTest(covers=covers):
                self.assertEqual(refused_manifest({'harnesses': [{'name': 'h::x', 'role': CLAIM,
                                                                  'covers': covers}]}),
                                 "harness 'h::x' has a malformed covers list",
                                 'a covers value that is not a list of strings must be refused')

    def test_a_malformed_expected_failure_is_refused(self):
        """Require the expected check to be a string when it is stated at all.

        ``None`` is admitted: it is how a claim, which fails nothing on purpose,
        omits the field.
        """
        self.assertEqual(refused_manifest({'harnesses': [{'name': 'h::k', 'role': CONTROL,
                                                          'expected_failure': 1}]}),
                         "harness 'h::k' has a malformed expected_failure",
                         'a non-string expected_failure must be refused')
        self.assertEqual(manifest_from_document({'harnesses': [{'name': 'h::x', 'role': CLAIM}]}).names(),
                         ('h::x',), 'a claim with no expected failure must still be admitted')

    def test_an_empty_manifest_is_refused(self):
        """Refuse a manifest declaring nothing, which would decide every run verified."""
        self.assertEqual(refused_manifest({'harnesses': []}),
                         'the harness manifest declares no harnesses',
                         'an empty manifest must not stand in for a claim set')

    def test_a_duplicated_harness_is_refused(self):
        """Refuse one harness declared twice, which would double its covers and controls."""
        self.assertEqual(refused_manifest({'harnesses': [{'name': 'h::x', 'role': CLAIM},
                                                         {'name': 'h::x', 'role': CLAIM}]}),
                         'the harness manifest declares a harness twice',
                         'a manifest naming one harness twice must be refused')


class ManifestEntries(unittest.TestCase):
    """Refuse an entry whose role and flags contradict each other.

    These are construction-time refusals rather than document ones, so a test
    fixture cannot build an entry the JSON reader would have refused either.
    """

    def test_an_unknown_role_is_refused(self):
        """Require the role to be one of the two the decision reads."""
        self.assertIn("has unknown role 'witness'",
                      refusal_text(lambda: Harness('h::x', 'witness')),
                      'a role outside claim and control must be refused by name')

    def test_a_control_may_not_be_should_panic(self):
        """Refuse the flag VO-11b reserves for a claim, on a control."""
        self.assertIn("control 'h::k' declares should_panic",
                      refusal_text(lambda: Harness('h::k', CONTROL, (), 'assertion.1', True)),
                      'a should_panic control has no meaning a decision could read')

    def test_a_control_must_name_what_it_fails(self):
        """Refuse a control with nothing to fail, which could only ever be rejected otherwise."""
        self.assertIn("control 'h::k' names no property it is expected to fail",
                      refusal_text(lambda: Harness('h::k', CONTROL)),
                      'a control with no expected failure must be refused')

    def test_a_should_panic_claim_may_not_declare_covers(self):
        """Refuse covers on a claim whose success is a panic, since no cover could be reached."""
        self.assertIn("claim 'h::c' is should_panic, so its covers would be unreachable",
                      refusal_text(lambda: Harness('h::c', CLAIM, ('a witness',), None, True)),
                      'a should_panic claim declaring a cover must be refused')


class ManifestSelections(unittest.TestCase):
    """Refuse a selection that names a harness the manifest does not carry, or names one twice."""

    def setUp(self) -> None:
        """Build one manifest with a claim and a control."""
        self.manifest = Manifest((Harness('h::a', CLAIM), Harness('h::k', CONTROL, (), 'assertion.1')))

    def test_a_selection_narrows_to_the_named_harnesses_in_order(self):
        """Require the narrowed manifest to follow the selection, not the manifest, order."""
        self.assertEqual(self.manifest.select(('h::k',)).names(), ('h::k',),
                         'the selection order is the narrowed manifest order')

    def test_a_selection_naming_an_unknown_harness_is_refused(self):
        """Require the unknown names to be listed, so a record's author can fix them."""
        self.assertIn("does not declare ['h::b']",
                      refusal_text(lambda: self.manifest.select(('h::a', 'h::b'))),
                      'a selection naming a harness the manifest lacks must be refused')

    def test_a_selection_naming_a_harness_twice_is_refused(self):
        """Refuse a duplicate, which would otherwise pad the claim set with one harness."""
        self.assertIn('names a harness twice',
                      refusal_text(lambda: self.manifest.select(('h::a', 'h::a'))),
                      'a selection naming one harness twice must be refused')


class ReaderPositions(unittest.TestCase):
    """Require the reader's structural errors to name the construct it wanted.

    Each case removes or corrupts exactly one construct and asserts the
    sentence, because the sentence is what tells a log's producer which part of
    their capture the grammar could not account for.
    """

    def test_a_log_that_ends_mid_block_says_where_it_ended(self):
        """Require the truncation to name the harness whose block never closed."""
        lines = lines_of('verified')
        end = next(index for index, line in enumerate(lines) if line.startswith(TIME))
        self.assertIn('truncated inside the block for', refused('\n'.join(lines[:end])),
                      'a block cut before its verification time must be refused as truncated')

    def test_a_summary_without_a_count_line_has_no_summary(self):
        """Require a block that lists checks but no count to be refused for its summary."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line == SUMMARY)
        end = next(position for position in range(index, len(lines)) if lines[position].startswith(' ** '))
        self.assertIn('has no summary', refused('\n'.join(lines[:end] + lines[end + 1:])),
                      'a block with no count line must be refused for its missing summary')

    def test_a_second_summary_count_is_refused_by_name(self):
        """Refuse two failure counts in one block, which the format prints once."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(' ** '))
        lines.insert(index + 1, lines[index])
        self.assertIn('has two failure counts', refused('\n'.join(lines)),
                      'a block printing its failure count twice must be refused')

    def test_a_second_verification_result_is_refused(self):
        """Refuse a block that states its verdict twice, where the last would silently win."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(VERIFICATION))
        lines.insert(index + 1, lines[index])
        self.assertIn('reports two verification results', refused('\n'.join(lines)),
                      'a block with two verdicts must be refused rather than believe the last')

    def test_a_failure_without_its_source_location_is_refused(self):
        """Require the `` File:`` line, which carries the one fact a record cannot invent."""
        lines = lines_of('counterexample')
        index = next(index for index, line in enumerate(lines) if line.startswith(' File: '))
        self.assertIn('without a source location', refused('\n'.join(lines[:index] + lines[index + 1:])),
                      'a failure with no location must be refused as unexplained')

    def test_a_check_listed_that_the_count_denies_is_refused(self):
        """Require the count and the listed checks to agree in both directions.

        The count is what a record's author reads, and the list is what the
        parser reads; a log disagreeing with itself must not be resolved by
        preferring either.
        """
        lines = lines_of('verified')
        start = next(index for index, line in enumerate(lines) if line.startswith('Check '))
        end = start + 1
        while end < len(lines) and lines[end].startswith('\t - '):
            end += 1
        self.assertIn('counts 2 checks but lists 1',
                      refused('\n'.join(lines[:start] + lines[end:])),
                      'a count that disagrees with the listed checks must be refused')

    def test_a_log_without_a_manual_summary_is_truncated(self):
        """Require the run's final count line, which is what makes a cut tail detectable."""
        lines = [line for line in lines_of('verified') if not line.startswith('Manual Harness Summary:')]
        self.assertIn('has no manual harness summary', refused('\n'.join(lines)),
                      'a run with no manual summary must be refused as truncated')

    def test_a_second_manual_summary_is_refused_at_its_line(self):
        """Refuse two summaries, naming the line the second one started on."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith('Manual Harness Summary:'))
        lines.insert(index + 1, lines[index])
        self.assertIn(f'line {index + 2}:', refused('\n'.join(lines)),
                      'the second summary must be refused at its own 1-based line')

    def test_a_garbage_line_after_the_summary_is_refused_at_its_own_line(self):
        """Require the block to refuse an unexplained line once both counts are present.

        The block skips the solver's transcript only *before* it has a verdict,
        a results list, and a summary count. Once the summary has supplied both
        counts, an unexplained line is structure the grammar cannot account
        for, and a condition that ignored either fact would accept it.
        """
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(' ** '))
        lines.insert(index + 1, 'decisive chatter from a future release')
        self.assertEqual(
            refused('\n'.join(lines)),
            f"line {index + 2}: unrecognised summary line for 'harnesses::verified': "
            "'decisive chatter from a future release'",
            'chatter after the summary must be refused, not skipped')

    def test_a_garbage_line_after_the_verdict_is_refused_in_the_block(self):
        """Require the block's own skip condition to stop once a verdict is recorded.

        The transcript skip is keyed on the block having no verdict, no results
        and no failure count. Inserting an unexplained line between the verdict
        and the verification time leaves ``failed_count`` unset, so a condition
        that dropped the verdict term would swallow it and accept the block.
        """
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(VERIFICATION))
        lines.insert(index + 1, 'decisive chatter from a future release')
        self.assertEqual(
            refused('\n'.join(lines)),
            f"line {index + 2}: unrecognised line in the block for 'harnesses::verified': "
            "'decisive chatter from a future release'",
            'an unexplained line after the verdict must be refused by the block')

    def test_build_chatter_inside_a_block_is_skipped_before_the_summary(self):
        """Require the pre-summary transcript skip, which is why the block parses at all.

        CBMC's own output sits between the harness header and ``RESULTS:``. Those
        lines belong to the solver rather than to Kani, so they are skipped by
        position; a block whose transcript was not pre-ambled would be refused
        for the very chatter every real log carries.
        """
        lines = lines_of('verified')
        start = next(index for index, line in enumerate(lines) if line.startswith('Checking harness '))
        lines.insert(start + 1, 'cbmc transcript line no release promises')
        self.assertIsNone(refused('\n'.join(lines)),
                          'solver chatter before a block reports must not be refused')

    def test_the_reachable_warning_inside_a_block_is_skipped(self):
        """Require Kani's reachability warning to be accepted as report preamble.

        The warning is printed per reachable construct, sometimes inside a
        block's preamble. Refusing it would make a run that merely mentions an
        unsupported construct unreadable.
        """
        lines = lines_of('verified')
        start = next(index for index, line in enumerate(lines) if line.startswith('Checking harness '))
        warning = next(line for line in lines_of('unsupported')
                       if line.startswith('** WARNING: A Rust construct'))
        lines.insert(start + 1, warning)
        self.assertIsNone(refused('\n'.join(lines)),
                          'the reachability warning must be accepted inside a block')

    def test_the_post_run_failure_line_is_skipped(self):
        """Require CBMC's own ``failed`` line to be accepted rather than refused.

        The timeout log prints it after the solver gave up. It is the one
        prefix no noise rule covers, so the block names it explicitly; a refusal
        here would reject every timed-out run.
        """
        lines = lines_of('verified')
        start = next(index for index, line in enumerate(lines) if line.startswith('Checking harness '))
        lines.insert(start + 1, 'CBMC failed')
        self.assertIsNone(refused('\n'.join(lines)),
                          'CBMC\'s own failure line must be skipped, not refused')


class UnsupportedEvidence(unittest.TestCase):
    """Separate an unsupported verdict from a counterexample by the evidence Kani printed.

    VO-11b makes the distinction load-bearing: a counterexample means the claim
    is false, while ``unsupported`` means Kani could not model the code. The
    three shapes that say ``unsupported`` differ in strength, so each has its
    own case here rather than being left to the corpus, which reaches only the
    first.
    """

    def test_a_failed_unsupported_construct_check_is_unsupported(self):
        """Require the unambiguous shape: Kani's own ``unsupported_construct`` check failed."""
        decision = facts.decision_for((facts.HarnessFact('h::c', CLAIM, facts.UNSUPPORTED_CHECK),))
        self.assertEqual(decision.outcome, 'unsupported',
                         'a failed unsupported_construct check must decide unsupported')

    def test_a_failed_assertion_naming_the_construct_is_unsupported(self):
        """Require Kani's wording, when the claim's own assertion carries it.

        This is the corpus's ``unsupported`` log shape. It is reached only when
        the failure is not counted as a counterexample — a ``should_panic``
        claim whose verdict carries Kani's note — since a plain failed assertion
        outranks it. The case states that boundary rather than hiding it.
        """
        excused = facts.HarnessFact('h::c', CLAIM, facts.UNSUPPORTED_ASSERTION,
                                    should_panic=True, note=True)
        self.assertEqual(facts.decision_for((excused,)).outcome, 'unsupported',
                         'an excused assertion naming an unsupported construct is unsupported')
        plain = facts.HarnessFact('h::c', CLAIM, facts.UNSUPPORTED_ASSERTION)
        self.assertEqual(facts.decision_for((plain,)).outcome, 'counterexample',
                         'a standing failed assertion outranks the wording it carries')

    def test_the_wording_is_matched_without_case(self):
        """Require the marker to match Kani's sentence whatever case it is printed in.

        The sentence is prose, and a release that capitalizes its warning must
        not silently turn an unsupported verdict into a counterexample. The
        fact is excused as a panic so the counterexample branch does not decide
        first; this test is about the wording alone.
        """
        seen = facts.HarnessFact('h::c', CLAIM, facts.UNSUPPORTED_ASSERTION,
                                 should_panic=True, note=True)
        for text in ('TerminatorKind::InlineAsm is not currently supported by Kani.',
                     'TERMINATORKIND::INLINEASM IS NOT CURRENTLY SUPPORTED BY KANI.'):
            with self.subTest(text=text):
                log, manifest = facts.build((seen,))
                log.blocks[0].failures = [FailedCheck(text, 'src/harnesses.rs', 7)]
                self.assertEqual(facts.decide(log, manifest).outcome, 'unsupported',
                                 'the marker must be matched case-insensitively')

    def test_a_pre_flight_warning_alone_proves_nothing(self):
        """Require the construct list to count only when this harness was left undecided.

        The corpus's ``list`` log names ``InlineAsm`` for a crate whose other
        harnesses verify, so treating the warning alone as an unsupported verdict
        would deny every run the crate ever produced.
        """
        decided = facts.HarnessFact('h::c', CLAIM, facts.SUCCESS)
        self.assertEqual(facts.decision_for((decided,), unsupported_constructs=('InlineAsm',)).outcome,
                         'verified', 'a construct warning beside a decided harness proves nothing')
        undecided = facts.HarnessFact('h::c', CLAIM, facts.UNDETERMINED)
        self.assertEqual(facts.decision_for((undecided,), unsupported_constructs=('InlineAsm',)).outcome,
                         'unsupported', 'the warning decides an otherwise unknown harness')

    def test_an_inventory_log_decides_a_tool_error_that_names_its_format(self):
        """Require a list run to be refused by format, not silenced."""
        decision = facts.decision_for((facts.HarnessFact('h::c', CLAIM, facts.SUCCESS),), log_format='inventory')
        self.assertEqual(decision.outcome, 'tool-error',
                         'an inventory carries no verdicts and must decide a tool error')
        self.assertIn("'inventory'", decision.reason,
                      'the tool error must name the format the log actually was')


class CorpusCoverage(unittest.TestCase):
    """Require the corpus expectations to name the classes these unit cases construct."""

    def test_the_recorded_reasons_are_the_ones_the_parser_gives(self):
        """Compare every refused corpus entry with the reason the parser reports."""
        for name, expectation in EXPECTED['logs'].items():
            if 'refused' not in expectation:
                continue
            with self.subTest(log=name):
                self.assertIn(expectation['refused'], refused(corpus.log_text(name)),
                              'the recorded reason must be the one the parser gives')


if __name__ == '__main__':
    unittest.main()
