"""Pin each structural log refusal to the reason it is reported with (VO-11a).

`test_kani_log_mutations.py` establishes that a broken log is *refused*. This
module establishes that it is refused *for the right reason*, which is a
different guarantee. VO-11b maps every structural refusal to the same
``tool-error`` outcome, so a parser that reported the wrong message — or no
message at all — would still refuse, still decide ``tool-error``, and still
fail the gate. Only an assertion on the exact text can tell the difference.

That difference is not cosmetic. The reason is the one thing the record's
author reads when their log is rejected, and the refusal classes are not
interchangeable advice: "it has no manual harness summary" says the capture was
cut short, while "a harness was reported twice" says the log was assembled
rather than captured. A message mutated to ``None`` or to a padded variant would
send the author looking for the wrong mistake.

The messages are asserted in full rather than by substring, because a substring
assertion is what let the padding and case mutations survive in the first place.

Examples
--------
>>> refused('not a log')
'the log does not begin with a Kani banner'
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log import BANNER, SUPPORTED_VERSIONS, KaniLogError, parse

from kani_log_text_fixtures import (
    HARNESS_START, LIST_WRITTEN, MANUAL, VERIFICATION, lines_of, refused,
)


def block_of(lines: list[str], index: int) -> list[str]:
    """Return the harness block starting at ``index``, up to the next one."""
    following = next((later for later in range(index + 1, len(lines))
                      if lines[later].startswith(HARNESS_START)), len(lines))
    return lines[index:following]


def manual_index(lines: list[str]) -> int:
    """Return the line index of the manual harness summary."""
    return next(index for index, line in enumerate(lines) if line.startswith(MANUAL))


class BannerRefusals(unittest.TestCase):
    """Name why the banner could not be attributed to a release this parser reads."""

    def test_a_log_without_a_banner_says_so(self):
        """Require the exact reason for text that is not a Kani log at all."""
        self.assertEqual(refused('not a log'),
                         'the log does not begin with a Kani banner',
                         'a log with no banner must be refused for that reason')

    def test_a_log_from_another_release_names_both_releases(self):
        """Require the release the log claims and the set this parser reads.

        The message exists so a reader can tell "you captured with the wrong
        Kani" from "the parser is behind"; dropping either release loses that.
        """
        version = sorted(SUPPORTED_VERSIONS)[0]
        other = version[:-1] + '9'
        lines = lines_of('verified')
        lines[0] = lines[0].replace(version, other)
        self.assertEqual(
            refused('\n'.join(lines)),
            f'the log is from Kani {other}, but this parser reads {sorted(SUPPORTED_VERSIONS)}',
            'an unsupported release must name both the log and the parser release set')


class ReconcileRefusals(unittest.TestCase):
    """Name which combination of parts made the log impossible."""

    def test_an_inventory_that_also_reports_blocks_is_refused_by_name(self):
        """Require the inventory/verification contradiction to be stated."""
        lines = lines_of('verified') + [LIST_WRITTEN + 'results.json']
        self.assertEqual(refused('\n'.join(lines)),
                         'the log claims to be both an inventory and a verification run',
                         'an inventory carrying harness blocks must be refused for that reason')

    def test_a_log_with_no_harness_results_says_so(self):
        """Require the empty-run message rather than a truncation message.

        A run that reported nothing is not the same as a run that was cut off,
        and the two send an author to different places.
        """
        self.assertEqual(refused(lines_of('verified')[0]), 'the log reports no harness results',
                         'a banner-only log must be refused for having no results')

    def test_a_missing_manual_summary_is_named_as_truncation(self):
        """Require the truncation message to name the missing summary."""
        lines = lines_of('verified')
        self.assertEqual(refused('\n'.join(lines[:manual_index(lines)])),
                         'the log is truncated: it has no manual harness summary',
                         'a log without its summary must be named as truncated')

    def test_a_duplicated_harness_is_refused_by_name(self):
        """Require the duplication message, which a count check alone would blur."""
        lines = lines_of('default_unwind')
        start = next(index for index, line in enumerate(lines) if line.startswith(HARNESS_START))
        block = block_of(lines, start)
        self.assertEqual(refused('\n'.join(lines[:start] + block + lines[start:])),
                         'a harness was reported twice in the same run',
                         'a repeated harness must be refused for duplication')

    def test_a_count_mismatch_states_both_sides(self):
        """Require the claimed and observed counts, in one exact line."""
        lines = lines_of('default_unwind')
        lines[manual_index(lines) + 2] = 'Complete - 5 successfully verified harnesses, 0 failures, 5 total.'
        self.assertEqual(
            refused('\n'.join(lines)),
            'the manual summary claims 5 verified and 0 failed of 5, but the blocks report '
            '1 verified and 1 failed of 2',
            'a count disagreement must state both the claim and the observation')

    def test_a_failure_named_but_not_reported_states_both_lists(self):
        """Require the two harness name lists, so the disagreement is readable."""
        lines = lines_of('default_unwind')
        lines[manual_index(lines) + 1] = 'Verification failed for - harnesses::nobody'
        self.assertEqual(
            refused('\n'.join(lines)),
            "the manual summary names failures ['harnesses::nobody'], but the blocks report "
            "['harnesses::seeded_wrapping_mutant']",
            'a named-but-absent failure must state both lists')


class BlockRefusals(unittest.TestCase):
    """Name where inside a block the grammar stopped recognising its own report."""

    def test_a_block_cut_off_before_its_verdict_names_the_harness(self):
        """Require the harness name rather than a line number alone.

        A line number locates the mistake; the harness name says which claim is
        unproven, which is what a reader deciding what to recapture needs.
        """
        lines = lines_of('verified')
        start = next(index for index, line in enumerate(lines) if line.startswith(HARNESS_START))
        self.assertEqual(
            refused('\n'.join(lines[:start + 3])),
            "the log is truncated inside the block for 'harnesses::verified'",
            'a block cut off mid-report must name the harness')

    def test_a_deleted_verdict_is_not_silently_accepted_as_a_summary_line(self):
        """Require the refusal that follows a removed verdict, stated exactly.

        Removing the verdict leaves the lines after it unrecognised inside the
        block. The exact text matters because this is the refusal a hand-edited
        log produces, and it should name the line it could not read.
        """
        lines = lines_of('verified')
        verdict = next(index for index, line in enumerate(lines) if line.startswith(VERIFICATION))
        self.assertEqual(
            refused('\n'.join(lines[:verdict] + lines[verdict + 1:])),
            "line 90: unrecognised summary line for 'harnesses::verified': "
            "'Verification Time: 0.06147875s'",
            'a block missing its verdict must name the line it could not read')

    def test_a_second_verdict_for_one_block_is_refused_by_name(self):
        """Require the duplicate-verdict message, which no count check covers."""
        lines = lines_of('verified')
        verdict = next(index for index, line in enumerate(lines) if line.startswith(VERIFICATION))
        self.assertEqual(
            refused('\n'.join(lines[:verdict] + [lines[verdict], lines[verdict]] + lines[verdict + 1:])),
            "the block for 'harnesses::verified' reports two verification results",
            'a block with two verdicts must be refused for that reason')


class SummaryRefusals(unittest.TestCase):
    """Name why the manual summary itself could not be read."""

    def test_a_second_manual_summary_names_the_line(self):
        """Require the position of the repeat, since the first summary is valid.

        The second summary is appended *after* the first one's ``Complete``
        line, which is the only place the guard can fire: a second header
        inside the first summary is refused earlier, by the summary reader,
        as an unrecognised line.
        """
        lines = lines_of('verified')
        index = manual_index(lines)
        summary = lines[index:]
        repeated = lines + summary
        self.assertEqual(
            refused('\n'.join(repeated)),
            f'line {len(lines) + 1}: a second manual harness summary',
            'a repeated summary must be refused at its own line')

    def test_a_summary_without_counts_is_named_as_truncated(self):
        """Require the truncation message for a summary that stops after its header."""
        lines = lines_of('verified')
        index = manual_index(lines)
        self.assertEqual(
            refused('\n'.join(lines[:index + 1])),
            'the log is truncated: the manual harness summary has no counts',
            'a summary with no counts must be named as truncated')


class ReconciliationRefusals(unittest.TestCase):
    """Name which of a block's own counts or lines disagreed with its contents.

    The reader reconciles four independent counts against what it listed, and
    each disagreement is a different mistake by whoever produced the log. A
    generic "the block is invalid" would leave the author to guess, and the
    four messages are long enough that only an exact assertion notices one
    being replaced with another or with nothing.
    """

    def test_a_failure_count_without_explanations_states_both_sides(self):
        """Require the counted and explained failure totals, in one exact line.

        Removing the ``Failed Checks:`` line leaves the count intact and the
        explanation gone, which is the shape a hand-edited log produces when
        someone deletes the sentence they did not want to read.
        """
        lines = lines_of('counterexample')
        index = next(position for position, line in enumerate(lines)
                     if line.startswith('Failed Checks: '))
        following = lines[index + 1]
        self.assertTrue(following.startswith(' File: '),
                        'the fixture must place the location directly after its message')
        self.assertEqual(
            refused('\n'.join(lines[:index] + lines[index + 2:])),
            "the block for 'harnesses::counterexample' counts 1 failures but explains 0",
            'a failure count with no explanation must state both totals')

    def test_an_unreachable_check_count_denied_by_its_own_list_is_refused(self):
        """Require the counted and listed ``undetermined`` totals.

        The count is optional in the format, so the guard only means anything
        when the line states one: a block claiming a different number of
        undetermined results than it lists is contradicting itself.
        """
        lines = lines_of('insufficient_unwind')
        index = next(position for position, line in enumerate(lines)
                     if ' undetermined)' in line)
        lines[index] = lines[index].replace('(3 undetermined)', '(2 undetermined)')
        self.assertEqual(
            refused('\n'.join(lines)),
            "the block for 'harnesses::insufficient_unwind' counts 2 undetermined results "
            'but lists 3',
            'an undetermined count must reconcile with the checks it counts')

    def test_an_unreachable_cover_count_denied_by_its_own_list_is_refused(self):
        """Require the counted and listed ``unreachable`` cover totals."""
        lines = lines_of('vacuous_assumption')
        index = next(position for position, line in enumerate(lines)
                     if 'cover properties satisfied' in line)
        lines[index] = lines[index].replace('(1 unreachable)', '(2 unreachable)')
        self.assertEqual(
            refused('\n'.join(lines)),
            "the block for 'harnesses::vacuous_assumption' counts 2 unreachable covers "
            'but lists 1',
            'an unreachable cover count must reconcile with the covers it counts')

    def test_a_repeated_cover_count_is_refused_by_name(self):
        """Require two cover-count lines in one block to be refused, not silently overwritten.

        A block declares its covers once, so a second line is a duplicated
        report rather than a wider one; believing the last would let an appended
        line rewrite what the run witnessed.
        """
        lines = lines_of('vacuous_assumption')
        index = next(position for position, line in enumerate(lines)
                     if 'cover properties satisfied' in line)
        lines.insert(index + 1, lines[index])
        self.assertEqual(
            refused('\n'.join(lines)),
            "the block for 'harnesses::vacuous_assumption' has two cover counts",
            'a block printing its cover count twice must be refused')


if __name__ == '__main__':
    unittest.main()
