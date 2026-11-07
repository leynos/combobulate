"""Kill the parser and reader mutants the corpus sweep left alive (VO-11a).

A mutation census over :mod:`docs_validation.kani_log` left survivors whose
mutations change what the parser *reports* rather than whether it parses. The
corpus is a set of real logs, so a mutant that only changes a fallback value, a
``None``-safe default, or an error's rendered text still parses every committed
log and still fails every corpus assertion. Each case here drives the one input
the mutant needs and asserts the fact the mutant destroys.

Five families are equivalents rather than untested, and this module records why
instead of silencing them. In
:func:`~docs_validation.kani_log.shell.tracked_paths` a mutation of
``subprocess.run(check=False)`` is unobservable: the function reads
``returncode`` on the next line and returns the same empty set whether the
command failed or raised. In
:meth:`~docs_validation.kani_log.reader.Reader.require_complete` the
``OTHER_STATUS.get(kind, '')`` default and its ``'XXXX'`` and omitted-argument
variants are unobservable for the same reason one level down: the value is
compared with ``item.status``, which is drawn from ``CHECK_STATUSES`` and so can
never be the empty string, ``'XXXX'``, or ``None``. The same method's
``failed_count is None or total_count is None`` cannot become ``and``, and
:meth:`~docs_validation.kani_log.reader.Reader.failed_check`'s two ``None``
defaults cannot become ``''``, because each pair is assigned together: a
summary sets both counts or neither, and a `` File:`` line sets both the path
and the line, so the two members of each guard always move as one. Finally
:func:`~docs_validation.kani_log.parse`'s ``is_list`` is only ever read for its
truthiness, and ``False`` and ``None`` are equally false.

Several mutants leave the reader stalled rather than wrong: dropping the call
that consumes a ``Check`` line, a ``Manual Harness Summary``, a harness header,
a cover line, or the cursor increment makes the enclosing loop re-read the line
it just matched. A stall is a real defect — an unbounded loop in a gate — but
the case that shows it has to bound itself, so every case here derives from
:class:`BoundedParserCase`, which raises a failure after five seconds instead of
hanging.

Examples
--------
>>> error_text(lambda: take_from([]))[:18]
'structural error: '
"""
from __future__ import annotations

import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docs_validation.kani_log import KaniLogError, parse, unwinding_checks_enabled
from docs_validation.kani_log.reader import Reader
from kani_log_text_fixtures import lines_of, refused


def error_text(action) -> str:
    """Return the rendered text of the ``KaniLogError`` an action raises."""
    try:
        action()
    except KaniLogError as error:
        return str(error)
    raise AssertionError('the action was expected to raise KaniLogError')


def take_from(lines: list[str]) -> str:
    """Consume one line from a fresh reader, exercising the exhausted branch when empty."""
    return Reader(lines).take()


class BoundedParserCase(unittest.TestCase):
    """Fail a case rather than wait when a mutant leaves the parser re-reading a line.

    Several mutants drop the call that consumes a matched line, and the reader's
    ``while not self.exhausted`` loop then never advances. Without a bound the
    whole suite would hang and report nothing, so every case here carries an
    alarm: a stall surfaces as the failure it is, on the case that caused it.
    """

    def setUp(self):
        self._previous_alarm = signal.signal(signal.SIGALRM, self._stalled)
        signal.setitimer(signal.ITIMER_REAL, 5)

    def tearDown(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self._previous_alarm)

    @staticmethod
    def _stalled(signum, frame):
        raise AssertionError('the parser did not terminate; it is stuck on a line it matched')


class ReaderRefusals(BoundedParserCase):
    """Require the reader's own refusals to carry their sentence, not just their type."""

    def test_an_exhausted_take_names_the_line_it_wanted(self):
        """Require the empty-log refusal to say where the missing output was needed.

        ``str()`` on the error is what a producer sees; the ``f'structural
        error: {reason}'`` prefix and the reason are the whole message, so a
        mutant that replaced the message with ``None`` would still refuse.
        """
        self.assertIn('structural error: line 1: the log ends where more output was required',
                      error_text(lambda: take_from([])),
                      'an exhausted take must name its position and the required output')

    def test_take_returns_the_line_it_consumed(self):
        """Require the consumed line to be the value returned, since every caller reads it."""
        self.assertEqual(take_from(['first', 'second']), 'first',
                         'take must return the line it consumed rather than None')


class BlockBoundaries(BoundedParserCase):
    """Require each block-ending condition to be refused for its own reason."""

    def test_a_block_listing_covers_but_no_cover_count_is_refused(self):
        """Require the cover count when covers are listed, so deleting it is structural.

        ``verified`` lists a cover and its count; removing the `` ** N of M
        cover properties satisfied`` line leaves ``covered_total`` at its
        default and must be refused rather than silently dropping the witness.
        """
        lines = lines_of('verified')
        index = next(position for position, line in enumerate(lines)
                     if 'cover properties satisfied' in line)
        self.assertIn('lists 1 covers but has no cover count',
                      refused('\n'.join(lines[:index] + lines[index + 1:])),
                      'a block that lists covers but no cover count must be refused')

    def test_an_other_count_naming_a_check_that_is_not_listed_is_refused(self):
        """Require the count to be compared against the checks, not just defaulted.

        The verified log counts one unreachable result and lists the check that
        carries it. Promoting that check to ``SUCCESS`` leaves the count
        claiming a result the list no longer shows, which must fail closed
        rather than pass because zero is tolerated.
        """
        lines = lines_of('verified')
        for index, line in enumerate(lines):
            if line.startswith('\t - ') and 'UNREACHABLE' in line:
                lines[index] = line.replace('UNREACHABLE', 'SUCCESS')
                break
        else:
            raise AssertionError('the verified log must list an unreachable check')
        self.assertIn('counts 1 unreachable results but lists 0', refused('\n'.join(lines)),
                      'an other-count naming an unlisted result must be refused')


class ErrorRendering(unittest.TestCase):
    """Require the structural prefix, which is the only marker a log reader sees."""

    def test_the_structural_prefix_is_part_of_the_message(self):
        """Require ``structural error:`` in ``str(error)``, not only in ``reason``."""
        self.assertEqual(str(KaniLogError('why')),
                         'structural error: why',
                         'the rendered error must carry the structural prefix and its reason')


class BlockProgress(BoundedParserCase):
    """Require every matched line inside a block to be consumed.

    Three of the reader's branches match a line and then delegate to a method
    that consumes it: ``results`` reads the ``Check`` lines, ``manual`` the
    summary, and ``block`` the ``Manual Harness Summary``. A mutant that drops
    the consuming call leaves the enclosing ``while`` re-reading the line for
    ever, so the parser never returns. ``BoundedParserCase`` bounds each case.
    """

    def test_a_results_block_does_not_stall_on_its_first_check(self):
        """Require the ``Check`` line to be consumed, since ``results`` matches it by hand.

        ``results`` inspects ``CHECK.match(line)`` itself rather than delegating
        to a method that takes the line, so the append is the only effect of
        the branch. Without it the block never advances and the parse never
        ends.
        """
        log = parse('\n'.join(lines_of('counterexample')))
        self.assertEqual(log.blocks[0].name, 'harnesses::counterexample',
                         'a log with checks must parse without stalling on the first one')

    def test_a_manual_summary_is_consumed_rather_than_re_read(self):
        """Require ``Reader.manual`` to be called, since the summary is what it consumes.

        The ``Manual Harness Summary:`` branch matches the line outside the
        method, so a mutant that skipped the call would leave the cursor on the
        same line and the reachability loop would spin.
        """
        log = parse('\n'.join(lines_of('verified')))
        self.assertEqual((log.manual.verified, log.manual.total), (1, 1),
                         'the manual summary must be read, not re-read, so the parse terminates')

    def test_a_harness_header_is_consumed_rather_than_re_read(self):
        """Require ``Reader.block`` to be called, since it consumes the header it is given.

        ``block`` raises when the header it was handed was not the line it
        started on, so a mutant that discarded the returned block also never
        advances the reader past the ``Checking harness`` line.
        """
        log = parse('\n'.join(lines_of('counterexample')))
        self.assertEqual(tuple(log.harnesses), ('harnesses::counterexample',),
                         'every harness header must be consumed exactly once')


class CursorAdvance(BoundedParserCase):
    """Require ``take`` to step the cursor by one rather than reset it."""

    def test_each_take_returns_the_line_after_the_one_before(self):
        """Require the increment, which a mutant replaces with an assignment.

        ``self._index = 1`` reads the same as ``+= 1`` for the first two calls
        and differently from the third: the cursor pins itself at one, so the
        second line comes back for ever. Three calls are the shortest input
        that tells them apart.
        """
        reader = Reader(['a', 'b', 'c'])
        self.assertEqual((reader.take(), reader.take(), reader.take()), ('a', 'b', 'c'),
                         'each take must advance the cursor by one line')


class SummaryLocation(BoundedParserCase):
    """Require a failed check's location to be read from the line beneath it."""

    def test_a_failure_without_its_location_line_is_refused_by_name(self):
        """Require the unlocated-failure refusal to name the message it could not place.

        Deleting the `` File:`` line leaves both ``path`` and ``line`` unset, so
        the refusal is reachable from the corpus. The refusal text is the only
        evidence of *which* failure lost its location, so a mutant that
        reported ``None`` there would name nothing.
        """
        lines = lines_of('counterexample')
        index = next(position for position, line in enumerate(lines) if line.startswith(' File: '))
        reason = refused('\n'.join(lines[:index] + lines[index + 1:]))
        self.assertIn('without a source location', reason,
                      'a failure whose location line was deleted must be refused')
        self.assertIn('placeholder message', reason,
                      'the refusal must name the failure it could not place')


class UnsupportedEntries(BoundedParserCase):
    """Require the pre-flight list to continue past a blank line between entries."""

    def test_an_entry_after_a_blank_line_is_still_collected(self):
        """Require ``continue`` rather than ``break`` on the blank-line branch.

        Kani separates the pre-flight list from its build chatter with a blank
        line, and a producer may blank a line between two entries. Stopping at
        the blank discards every entry after it, which silently shrinks the
        constructs a record must account for.
        """
        lines = lines_of('unsupported')
        index = next(position for position, line in enumerate(lines)
                     if line.startswith('             - '))
        text = '\n'.join(lines[:index + 1] + ['', '             - core::ptr::read (1)']
                         + lines[index + 1:])
        self.assertEqual(parse(text).unsupported_constructs,
                         ('TerminatorKind::InlineAsm', 'core::ptr::read'),
                         'an unsupported entry after a blank line must still be collected')


class ReportedDescription(BoundedParserCase):
    """Require a check's description to be reported as the log printed it."""

    def test_a_description_that_opens_with_x_keeps_its_first_letter(self):
        """Require ``strip('"')`` to remove only quotes, not a set of characters.

        ``str.strip`` takes a character *set*, so a mutant that widened the
        argument to ``'XX"XX'`` strips both quotes and every leading or
        trailing ``X``. A description legitimately beginning with ``X`` would
        then be reported one character short of what the log said.
        """
        lines = lines_of('counterexample')
        index = next(position for position, line in enumerate(lines)
                     if line.startswith('\t - Description: '))
        lines[index] = lines[index].replace('\t - Description: ', '\t - Description: X', 1)
        description = parse('\n'.join(lines)).blocks[0].properties[0].description
        self.assertTrue(description.startswith('X"'),
                        'a description opening with X must keep its first letter')


class ResultsMarker(BoundedParserCase):
    """Require the block to remember that it listed results.

    ``has_results`` is what tells the reader that an unexplained line arrived
    *after* the checks rather than during the solver's own transcript. Before
    ``RESULTS:`` an unrecognised line is CBMC chatter to skip; after it, the
    same line means the report is broken and must be refused. A mutant that
    clears the marker collapses those two states into one.
    """

    def test_a_stray_line_after_the_results_is_refused(self):
        """Require the marker to survive, since it is the only evidence of the boundary.

        The stray line is placed between the last ``Check`` and the
        ``SUMMARY:``, so no other branch can claim it: it is not a check, not a
        verdict, not a summary, and not build chatter. With the marker set the
        block refuses it; with the marker cleared the line is silently skipped
        as though the solver had printed it.
        """
        lines = lines_of('verified')
        index = next(position for position, line in enumerate(lines)
                     if line.startswith('SUMMARY:'))
        strayed = '\n'.join(lines[:index] + ['Wait, that is not a report line'] + lines[index:])
        self.assertIn('unrecognised line in the block', refused(strayed) or '',
                      'a line the report cannot explain must be refused, not skipped')


class SolverCommands(BoundedParserCase):
    """Require the echoed CBMC command to be kept, since the unwinding rule reads it."""

    def test_an_unwind_bound_is_read_from_the_kept_command(self):
        """Require the command text itself, not a placeholder that reads as "no bound".

        ``unwinding_checks_enabled`` compares flags against this string. An
        empty string or ``None`` is indistinguishable from a command that
        genuinely carried no ``--unwind``, so a block whose proof does unwind
        would be reported as one that never asked CBMC to check it.
        """
        block = parse('\n'.join(lines_of('insufficient_unwind'))).blocks[0]
        self.assertIs(unwinding_checks_enabled(block), True,
                      'a solver command carrying an unwind bound must report checks enabled')


if __name__ == '__main__':
    unittest.main()
