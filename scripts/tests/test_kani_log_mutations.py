"""Require every structurally broken Kani log to be refused structurally (VO-11a).

A refusal is only useful if it is the *right* refusal. A record that bound a
digest would otherwise be rejected for the digest alone, and a log the parser
merely choked on would look like evidence of tampering rather than evidence of
a gap in the grammar. So every mutant here is a real log with one edit — a cut
tail, a deleted report line, a raised count, a duplicated or interleaved block,
an altered banner — and every assertion demands a structural reason.

The mutants are generated rather than handwritten so the sweep is exhaustive
over the lines and cut points a producer could actually differ in; where the
line set is large, Hypothesis samples it and the report names the log and the
edit, so a failure reproduces.

Examples
--------
>>> 'no harness results' in refused(harness_banner_only())
True
>>> 'reported twice' in refused(duplicated_first_block())
True
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis import given, settings, strategies as st

import kani_corpus_fixtures as corpus
from docs_validation.kani_log import BANNER, SUPPORTED_VERSIONS, HarnessBlock, parse, unwinding_checks_enabled
from kani_log_text_fixtures import (
    COMPLETE, EXPECTED, HARNESS_START, LIST_WRITTEN, MANUAL, REPORT_PREFIXES, RESULTS, TIME,
    VERIFICATION, bump_first_number, harness_block, insert_block, lines_of, refused,
)


def harness_banner_only() -> str:
    """Return a log holding nothing but its banner."""
    return f'{lines_of("verified")[0]}\n'


def duplicated_first_block() -> str:
    """Return the first log with its first harness block repeated in place."""
    lines = lines_of('verified')
    start = next(index for index, line in enumerate(lines) if line.startswith(HARNESS_START))
    return '\n'.join(lines[:start] + harness_block('verified') + lines[start:])


class TruncationMutations(unittest.TestCase):
    """Refuse every log cut before the run's final completion line."""

    def test_no_cut_before_completion_parses(self):
        """Walk every cut point of every verification log and require a refusal.

        An inventory log is excluded deliberately: its whole content is the
        banner and the list it was asked to write, so every prefix that keeps
        both is a real, complete inventory rather than a truncated run.
        """
        for name in corpus.log_names():
            lines = lines_of(name)
            complete = [index for index, line in enumerate(lines) if line.startswith(COMPLETE)]
            if not complete:
                continue
            for cut in range(1, complete[-1] + 1):
                with self.subTest(log=name, cut=cut):
                    reason = refused('\n'.join(lines[:cut]))
                    self.assertIsNotNone(reason, f'{name} cut at {cut} must be refused')

    def test_an_inventory_truncated_after_its_banner_is_refused(self):
        """Refuse a list run cut before it wrote its results."""
        lines = lines_of('list')
        written = next(index for index, line in enumerate(lines) if line.startswith(LIST_WRITTEN))
        for cut in range(1, written + 1):
            with self.subTest(cut=cut):
                self.assertIsNotNone(refused('\n'.join(lines[:cut])),
                                     f'the inventory cut at {cut} must be refused')

    def test_an_inventory_truncated_after_writing_its_results_is_still_valid(self):
        """Accept the inventory once it has named the file it wrote, and say so.

        This is the one truncation the corpus tolerates, and the reason is
        structural rather than lenient: everything after the written-results
        line is Cargo chatter, so cutting there loses no fact.
        """
        lines = lines_of('list')
        written = next(index for index, line in enumerate(lines) if line.startswith(LIST_WRITTEN))
        self.assertEqual(parse('\n'.join(lines[:written + 1])).format, 'inventory',
                         'the inventory must be complete as soon as it names its output')

    @given(data=st.data())
    @settings(max_examples=60, deadline=None)
    def test_a_generated_prefix_is_refused_or_is_a_shorter_valid_log(self, data):
        """Refuse any prefix that stops before the last completion line.

        The final lines of a regular log are the manual summary and the counts;
        a prefix that stops after them is the same log with its trailing chatter
        dropped, which is not a structural break. Every earlier prefix is.
        """
        frames = data.draw(st.sampled_from(['counterexample', 'verified', 'unsatisfied_cover',
                                            'insufficient_unwind', 'vacuous_assumption']))
        lines = lines_of(frames)
        complete = [index for index, line in enumerate(lines) if line.startswith(COMPLETE)]
        cut = data.draw(st.integers(min_value=1, max_value=complete[-1]))
        reason = refused('\n'.join(lines[:cut]))
        self.assertIsNotNone(reason, f'{frames} cut at {cut} must be refused structurally')

    def test_a_total_loss_of_content_is_refused(self):
        """Refuse a log that keeps only its banner."""
        reason = refused(harness_banner_only())
        self.assertIn('no harness results', reason, 'a banner alone must not be a verification run')


class LineDeletionMutations(unittest.TestCase):
    """Refuse every deletion of a line that carries report structure."""

    def test_deleting_any_report_line_is_refused(self):
        """Delete each structural line in turn and require a structural refusal."""
        for name in corpus.log_names():
            lines = lines_of(name)
            for index, line in enumerate(lines):
                if not line.startswith(REPORT_PREFIXES):
                    continue
                with self.subTest(log=name, line=index, text=line[:40]):
                    reason = refused('\n'.join(lines[:index] + lines[index + 1:]))
                    self.assertIsNotNone(
                        reason, f'{name} without line {index} ({line[:40]!r}) must be refused')

    def test_deleting_a_count_line_is_refused(self):
        """Delete each summary count and require the refusal to name the count."""
        for name in ('verified', 'unsatisfied_cover', 'counterexample'):
            lines = lines_of(name)
            for index, line in enumerate(lines):
                if not line.startswith(' ** '):
                    continue
                with self.subTest(log=name, line=line):
                    reason = refused('\n'.join(lines[:index] + lines[index + 1:]))
                    expected = 'no cover count' if 'cover properties' in line else 'no summary'
                    self.assertIn(expected, reason,
                                  f'{name} without {line!r} must be refused for its missing count')

    @given(data=st.data())
    @settings(max_examples=40, deadline=None)
    def test_a_deleted_check_entry_is_refused(self, data):
        """Delete one ``Check N:`` line and its fields, which the counts then contradict."""
        name = data.draw(st.sampled_from(['verified', 'counterexample', 'insufficient_unwind']))
        lines = lines_of(name)
        starts = [index for index, line in enumerate(lines) if line.startswith('Check ')]
        start = data.draw(st.sampled_from(starts))
        end = start + 1
        while end < len(lines) and lines[end].startswith('\t - '):
            end += 1
        reason = refused('\n'.join(lines[:start] + lines[end:]))
        self.assertIn('counts', reason,
                      f'{name} without the check at {start} must be refused for its counts')


class SummaryCountMutations(unittest.TestCase):
    """Refuse a log whose printed counts disagree with the checks it lists."""

    def test_altering_any_count_is_refused(self):
        """Raise the first number of every summary and completion line by one."""
        for name in corpus.log_names():
            lines = lines_of(name)
            for index, line in enumerate(lines):
                if not line.startswith((' ** ', COMPLETE)):
                    continue
                altered = list(lines)
                altered[index] = bump_first_number(line)
                with self.subTest(log=name, line=line):
                    self.assertIsNotNone(refused('\n'.join(altered)),
                                         f'{name} with {line!r} altered must be refused')

    def test_a_disagreeing_manual_summary_is_refused(self):
        """Change the run's total and require the reconciliation to notice."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(COMPLETE))
        lines[index] = bump_first_number(lines[index])
        self.assertIn('manual summary claims', refused('\n'.join(lines)),
                      'a manual summary that disagrees with the blocks must be refused')

    def test_a_failure_named_without_a_block_is_refused(self):
        """Name a failing harness that reported success, which the summary cannot do."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(MANUAL))
        lines.insert(index + 1, 'Verification failed for - harnesses::verified')
        self.assertIsNotNone(refused('\n'.join(lines)),
                             'a summary naming a failure the blocks deny must be refused')


class HarnessBlockMutations(unittest.TestCase):
    """Refuse duplicated, interleaved, and unaccounted harness blocks."""

    def test_a_duplicated_block_is_refused(self):
        """Repeat a complete block in place and require a refusal."""
        self.assertIn('reported twice', refused(duplicated_first_block()),
                      'a harness reported twice must be refused')

    def test_an_interleaved_block_is_refused(self):
        """Start a second harness inside the first and require a refusal."""
        for anchor in (HARNESS_START, RESULTS, ' ** '):
            with self.subTest(anchor=anchor):
                lines = insert_block(lines_of('counterexample'), harness_block('verified'), anchor)
                self.assertIsNotNone(refused('\n'.join(lines)),
                                     f'a block inserted after {anchor!r} must be refused')

    def test_a_block_without_its_verdict_is_refused(self):
        """Remove the verdict line and require the block to be refused.

        The summary is still being read when the verdict goes missing, so the
        refusal names the line that could not be accounted for; either reason
        proves the block is incomplete, and both are structural.
        """
        lines = [line for line in lines_of('verified') if not line.startswith(VERIFICATION)]
        self.assertIsNotNone(refused('\n'.join(lines)), 'a block with no verdict must be refused')

    def test_a_block_without_its_verification_time_is_refused(self):
        """Remove the verification time, which is the block's only end marker."""
        lines = [line for line in lines_of('verified') if not line.startswith(TIME)]
        self.assertIn('no verification time', refused('\n'.join(lines)),
                      'a block with no verification time must be refused as truncated')

    def test_a_block_with_two_verdicts_is_refused(self):
        """Repeat the verdict line and require a refusal."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(VERIFICATION))
        lines.insert(index + 1, lines[index])
        self.assertIn('two verification results', refused('\n'.join(lines)),
                      'a block with two verdicts must be refused')

    def test_an_unrecognised_report_line_is_refused(self):
        """Insert a line inside a block that the grammar does not account for."""
        lines = lines_of('counterexample')
        index = next(index for index, line in enumerate(lines) if line == RESULTS)
        lines.insert(index + 1, 'Check 99: harnesses::counterexample.assertion.99')
        self.assertIsNotNone(refused('\n'.join(lines)), 'a bare check header must be refused')

    def test_a_check_with_an_unknown_status_is_refused(self):
        """Replace a check's status with one the grammar does not admit."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines)
                     if line.startswith('\t - Status: SUCCESS'))
        lines[index] = '\t - Status: MAYBE'
        self.assertIn('unknown status', refused('\n'.join(lines)),
                      'a status outside the grammar must be refused')


class RefusalPositions(unittest.TestCase):
    """Require a structural refusal to name the line that broke the grammar.

    The reason code a record's author receives is ``tool-error``; the line
    number is the only part of the refusal that says *where* to look. A cursor
    one line out is still a refusal, so nothing but an explicit position
    assertion holds it.
    """

    def test_an_unrecognised_line_is_refused_at_its_own_line(self):
        """Require a 1-based line number, pointing at the line the cursor stopped on."""
        lines = lines_of('verified')
        index = next(index for index, line in enumerate(lines) if line.startswith(' ** '))
        lines.insert(index + 1, 'not a summary line')
        self.assertIn(f'line {index + 2}:', refused('\n'.join(lines)),
                      'the refusal must name the 1-based line it could not read')

    def test_a_check_with_missing_fields_names_every_one(self):
        """Require the refusal to list each missing field, not a placeholder list.

        The three fields are named in ``CHECK_FIELDS`` order, so a record's
        author sees exactly what Kani omitted rather than a joint pronoun.
        """
        lines = lines_of('counterexample')
        index = next(index for index, line in enumerate(lines) if line == RESULTS)
        lines.insert(index + 1, 'Check 99: harnesses::counterexample.assertion.99')
        self.assertIn("is missing Status, Description, Location", refused('\n'.join(lines)),
                      'the refusal must name every missing check field')

    def test_a_truncated_block_names_the_harness_not_a_line(self):
        """Require a truncated block to be reported by harness, since no line is at fault.

        The corpus's killed run stops inside ``multiplication_timeout``, which
        is the block whose report never ended; naming any other harness would
        send a record's author to the wrong one.
        """
        reason = refused('\n'.join(lines_of('truncated')))
        self.assertIn("the block for 'harnesses::multiplication_timeout'", reason,
                      'a truncated block must name the harness whose report ended early')


class BannerMutations(unittest.TestCase):
    """Refuse a log whose banner does not name a release this grammar was read from."""

    def test_altering_the_version_is_refused(self):
        """Require the refusal for a different Kani release."""
        for name in corpus.log_names():
            lines = lines_of(name)
            header = BANNER.match(lines[0])
            other = header['version'][:-1] + '9'
            lines[0] = lines[0].replace(header['version'], other)
            with self.subTest(log=name, version=other):
                reason = refused('\n'.join(lines))
                self.assertIn('from Kani', reason,
                              f'{name} from {other} must be refused as unsupported')

    def test_a_missing_banner_is_refused(self):
        """Require the refusal when the release cannot be named at all."""
        for mutated, label in (
            (lines_of('verified')[1:], 'dropped'),
            ([f'Kani Rust Verifier {next(iter(SUPPORTED_VERSIONS))}'] + lines_of('verified')[1:], 'no kind'),
            (['Kani Rust Verifier (cargo plugin)'] + lines_of('verified')[1:], 'no version'),
        ):
            with self.subTest(banner=label):
                self.assertIsNotNone(refused('\n'.join(mutated)),
                                     f'a banner with {label} must be refused')

    def test_the_supported_set_names_only_releases_the_corpus_proves(self):
        """Hold the supported set to the banner every committed log carries."""
        banners = {corpus.parse_log(name).banner_version for name in corpus.log_names()
                   if 'refused' not in EXPECTED['logs'][name]}
        self.assertEqual(banners, set(SUPPORTED_VERSIONS),
                         'the parser must support exactly the releases the corpus exercised')


class UnwindingCapability(unittest.TestCase):
    """Derive the unwinding flag from CBMC's own command, not from a failure."""

    def test_a_bounded_run_enables_unwinding_checks(self):
        """A run given an unwinding bound must report the checks as enabled."""
        block = corpus.parse_log('insufficient_unwind').blocks[0]
        self.assertIs(unwinding_checks_enabled(block), True,
                      'a run given --unwind must generate unwinding assertions')

    def test_an_unbounded_run_leaves_them_disabled(self):
        """A run given no bound must report the checks as unavailable."""
        block = corpus.parse_log('verified').blocks[0]
        self.assertIs(unwinding_checks_enabled(block), False,
                      'a run given no unwinding bound must not claim the check ran')

    def test_a_block_without_a_solver_command_says_nothing(self):
        """A block that echoed no solver command must return None rather than guess."""
        self.assertIsNone(unwinding_checks_enabled(HarnessBlock(name='h::x')),
                          'a block with no echoed command must report the capability unknown')

    def test_an_explicit_disable_wins_over_a_bound(self):
        """A command that disables the assertions must report them unavailable."""
        block = HarnessBlock(name='h::x',
                             solver_command='[Kani] Running: `cbmc --unwind 2 --no-unwinding-assertions`')
        self.assertIs(unwinding_checks_enabled(block), False,
                      'an explicit --no-unwinding-assertions must win over --unwind')


if __name__ == '__main__':
    unittest.main()
