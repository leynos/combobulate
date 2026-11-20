"""Qualify the shipped kernel's Verus verdicts without running a solver.

The kernel driver admits a positive root only on its exact pinned count and a
mutant only on a located postcondition failure at that mutant's own clause.
These tests exercise those two rules and the portable-log rewriting, so a
changed summary, a disqualified error, or a host path in a committed log fails
here rather than silently weakening the record.

The loader that stubs the driver's module-scope imports lives in
:mod:`verus_kernel_fixtures`, so this file states what each rule must decide.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from verus_kernel_fixtures import (
    RECORD,
    ROOT,
    SUMMARY,
    load,
    load_driver,
    load_verdicts,
)
from verus_kernel_fixtures import SCRIPTS

SUMMARY = 'verification results:: 20 verified, 0 errors\n'


class PositiveQualificationTests(unittest.TestCase):
    """Admit the positive root only on the exact pinned, whole-crate count."""

    def setUp(self) -> None:
        """Load the driver once per test."""
        self.driver = load_verdicts()

    def test_the_pinned_count_qualifies(self) -> None:
        """The recorded count with no suffix must be accepted."""
        verdict = self.driver._qualify_positive(SUMMARY, 0)

        self.assertEqual(verdict, {'kind': 'positive', 'verified': 20})

    def test_a_different_count_is_rejected(self) -> None:
        """Any count other than the pin must request a reviewed update."""
        for count in (19, 21, 119):
            summary = f'verification results:: {count} verified, 0 errors\n'
            with self.assertRaisesRegex(RuntimeError, 'update the pin'):
                self.driver._qualify_positive(summary, 0)

    def test_a_partial_suffix_is_rejected(self) -> None:
        """A selection-sized verification must not stand in for the crate."""
        partial = SUMMARY.replace('\n', ' (partial verification with `--verify-*`)\n')
        with self.assertRaisesRegex(RuntimeError, 'not a selection'):
            self.driver._qualify_positive(partial, 0)

    def test_reported_errors_are_rejected(self) -> None:
        """A non-zero error count must fail even at the pinned total."""
        failing = 'verification results:: 20 verified, 1 errors\n'
        with self.assertRaisesRegex(RuntimeError, 'did not verify'):
            self.driver._qualify_positive(failing, 1)

    def test_a_missing_summary_is_rejected(self) -> None:
        """A log with no summary at all is not evidence."""
        with self.assertRaisesRegex(RuntimeError, 'no verification summary'):
            self.driver._qualify_positive('recording prover fixture\n', 0)


class MutantQualificationTests(unittest.TestCase):
    """Admit a mutant only on a postcondition failure at its own clause."""

    def setUp(self) -> None:
        """Load the verdict rules once per test."""
        self.verdicts = load_verdicts()
        self.driver = load_driver()

    def _diagnostic(self, clause: str, name: str = 'mutant_err') -> str:
        """Return a failure naming ``clause`` inside the mutant called ``name``.

        The clause line is searched from the named mutant's own signature, so a
        helper cannot accidentally report another wrapper's line and let a
        region check pass for the wrong reason.
        """
        source = self.driver.MUTANT_ROOT
        return self._located(clause, name, source)

    def _located(self, clause: str, name: str, source: Path) -> str:
        """Return a Verus log naming ``clause`` of ``name`` in ``source``."""
        return (
            'error: postcondition not satisfied\n'
            f'  --> {source}:{self._clause_line(clause, name, source)}:13\n'
            'verification results:: 0 verified, 1 errors\n'
        )

    def _clause_line(self, clause: str, name: str, source: Path) -> int:
        """Return the line that states ``clause`` inside ``name``'s region."""
        lines = source.read_text(encoding='utf-8').splitlines()
        first = next(
            index
            for index, text in enumerate(lines, start=1)
            if text.startswith(f'pub fn {name}(')
        )
        return next(
            index
            for index, text in enumerate(lines[first:], start=first + 1)
            if text.strip().startswith(f'{clause}(')
        )

    def _diagnostic_at(self, path: Path, line: int, subject: str = 'this postcondition') -> str:
        """Return Verus's ``error:`` line naming ``subject`` at ``path:line``.

        The text is byte-for-byte what Verus prints, because a rule that matches
        diagnostics by wording must be exercised with the wording it matches.
        """
        return (
            f'error: postcondition not satisfied\n'
            f'  --> {path}:{line}:13\n'
            f'   |\n'
            f'{line} |           k1(lhs@, rhs@, old(out)@, final(out)@, r),\n'
            f'   |           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ failed {subject}\n'
        )

    def _qualify(self, log: str, exit_code: int, name: str, clauses: list[str]) -> dict:
        """Qualify ``log`` against the mutant root the driver compiles."""
        request = self.verdicts.MutantRequest(name, clauses, self.driver.MUTANT_ROOT)
        return self.verdicts._qualify_mutant(log, exit_code, request)

    def test_the_intended_clause_qualifies(self) -> None:
        """Each mutant's own clause line must produce a rejection verdict."""
        for name, clause in self.driver.MUTANTS.items():
            with self.subTest(mutant=name):
                clauses = [clause]
                verdict = self._qualify(self._diagnostic(clause, name), 1, name, clauses)
                self.assertEqual(verdict['kind'], 'mutant')
                self.assertEqual(verdict['clauses'], clauses)

    def test_a_neighbouring_clause_is_rejected(self) -> None:
        """A failure at a clause the mutant does not owe must not qualify.

        The failure is located inside the requested mutant's own region, so
        the rejection turns on the clause rather than on the region.
        """
        name = 'mutant_late'
        intended = self.driver.MUTANTS[name]
        wrong = next(clause for clause in ('k1', 'k2', 'k3', 'k5') if clause != intended)
        with self.assertRaisesRegex(RuntimeError, 'not the intended'):
            self._qualify(self._diagnostic(wrong, name), 1, name, [intended])

    def test_an_unlocated_diagnostic_is_rejected(self) -> None:
        """A failure naming no clause line must not be a rejection."""
        for log in (
            'error: postcondition not satisfied\n'
            'verification results:: 0 verified, 1 errors\n',
            'error: postcondition not satisfied\n'
            f'  --> {self.driver.MUTANT_ROOT}.other:40:13\n'
            'verification results:: 0 verified, 1 errors\n',
        ):
            with self.assertRaisesRegex(RuntimeError, 'own region'):
                self._qualify(log, 1, 'mutant_err', ['k2'])

    def test_another_mutants_clause_line_is_rejected(self) -> None:
        """A failure outside this mutant's region must not qualify it.

        Every wrapper states the same five clauses, so a checker that matched
        the clause text anywhere in the file would accept `mutant_late`'s `k4`
        line for `mutant_err`. The distinguishing fact is the enclosing
        function, which the region check must require.
        """
        foreign = self._diagnostic('k4', 'mutant_late')
        with self.assertRaisesRegex(RuntimeError, 'own region'):
            self._qualify(foreign, 1, 'mutant_err', ['k4'])

    def test_a_failure_outside_the_region_among_others_is_rejected(self) -> None:
        """A located failure elsewhere must disqualify a log that also names ours.

        The requested mutant fails at its own clause, so a rule that only asks
        whether the intended clause appears accepts the log. The run also
        reported a failure in another wrapper, which means the mutant was not
        the only obligation that broke and the record would attribute a
        confounded run to this mutant.
        """
        name = 'mutant_late'
        intended = self.driver.MUTANTS[name]
        own = self._diagnostic(intended, name)
        foreign = self._diagnostic_at(
            self.driver.MUTANT_ROOT,
            self._clause_line('k2', 'mutant_err', self.driver.MUTANT_ROOT),
        )
        log = (own + foreign).replace(
            'verification results:: 0 verified, 1 errors\n',
            'error: aborting due to 2 previous errors\n'
            'verification results:: 0 verified, 2 errors\n',
        )
        with self.assertRaisesRegex(RuntimeError, 'outside its own region'):
            self._qualify(log, 1, name, [intended])

    def test_an_unlocated_failure_among_others_is_rejected(self) -> None:
        """A second failure naming no location must disqualify the run.

        Verus can report an obligation it could not locate. Such a failure
        could belong to any line in the crate, so it cannot be attributed to
        the mutant whose region happens to contain the other diagnostic.
        """
        name = 'mutant_late'
        intended = self.driver.MUTANTS[name]
        log = (
            self._diagnostic(intended, name)
            + 'error: postcondition not satisfied\n'
            'verification results:: 0 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'outside its own region'):
            self._qualify(log, 1, name, [intended])

    def test_a_same_named_file_at_another_path_is_rejected(self) -> None:
        """A diagnostic in another ``elementwise_add_mutants.rs`` is not ours.

        Both tiers compare only the file name today, so a copy of the mutant
        root under a scratch directory would satisfy the path rule. The region
        is in that copy, not in the file the driver compiled.
        """
        source = self.driver.MUTANT_ROOT
        line = self._clause_line('k2', 'mutant_err', source)
        elsewhere = source.with_name(source.name).parent / 'target' / source.name
        log = (
            self._diagnostic_at(elsewhere, line)
            + 'verification results:: 0 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'own region'):
            self._qualify(log, 1, 'mutant_err', ['k2'])

    def test_a_disqualifying_error_is_rejected(self) -> None:
        """A type, syntax or unsupported-feature error must fail the run."""
        log = (
            'error: postcondition not satisfied\n'
            'error: unsupported feature\n'
            'verification results:: 0 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'disqualifying error'):
            self._qualify(log, 1, 'mutant_err', ['k2'])

    def test_a_zero_exit_is_rejected(self) -> None:
        """A mutant that verifies is not rejected, whatever the log says."""
        with self.assertRaisesRegex(RuntimeError, 'expected exit 1'):
            self._qualify(self._diagnostic('k2'), 0, 'mutant_err', ['k2'])


class BodyMutantTests(unittest.TestCase):
    """Require the wrapping body to fail a loop invariant, not something else."""

    def setUp(self) -> None:
        """Load the verdict rules and the body they qualify once per test."""
        self.driver = load_driver()
        self.invariant = self._invariant_line()

    def _invariant_line(self) -> int:
        """Return the line of the scan loop's invariant in the shipped body."""
        lines = self.driver.PRODUCTION.read_text(encoding='utf-8').splitlines()
        return next(
            index
            for index, text in enumerate(lines, start=1)
            if 'invariant' in text
        )

    def _assertion_line(self) -> int:
        """Return the line of the scan pass's own assertion."""
        lines = self.driver.PRODUCTION.read_text(encoding='utf-8').splitlines()
        return next(
            index
            for index, text in enumerate(lines, start=1)
            if 'assert(!in_range_at' in text
        )

    def test_a_loop_invariant_failure_qualifies(self) -> None:
        """An invariant failure with a non-zero error count is the verdict."""
        log = (
            'error: invariant not satisfied at loop head\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: assertion failed\n'
            f'  --> {self.driver.WRAP_BODY}:{self._assertion_line()}:29\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        verdict = self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

        self.assertEqual(verdict['clause'], 'loop-invariant')

    def test_a_verified_body_is_rejected(self) -> None:
        """A body that verifies is not a rejected mutant."""
        with self.assertRaisesRegex(RuntimeError, 'must not verify'):
            self.driver._qualify_body(SUMMARY, 0, self.driver.WRAP_BODY)

    def test_a_postcondition_only_failure_is_rejected(self) -> None:
        """Some other obligation must not stand in for the loop invariant."""
        log = (
            'error: postcondition not satisfied\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'verification results:: 0 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must fail a loop invariant'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_a_duplicated_invariant_with_one_location_is_rejected(self) -> None:
        """One located failure must not account for two reported failures.

        Verus can report the same obligation twice, once with a location and
        once without. Comparing error text alone treats the second as
        explained; it is a separate diagnostic that could have failed anywhere.
        """
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: invariant not satisfied at end of loop body\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must all be located in the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_a_same_named_body_at_another_path_is_rejected(self) -> None:
        """A failure located in a copy of the body is not evidence about it."""
        elsewhere = Path('/tmp/another-checkout/elementwise_add.rs')
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {elsewhere}:{self.invariant}:13\n'
            'verification results:: 14 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must name a line of the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_an_assertion_outside_the_body_is_rejected(self) -> None:
        """An admitted assertion is only evidence when the body raised it."""
        log = (
            'error: invariant not satisfied at end of loop body\n'
            f'  --> {self.driver.WRAP_BODY}:{self.invariant}:13\n'
            'error: assertion failed\n'
            '  --> wrap.rs:9:5\n'
            'verification results:: 14 verified, 2 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must all be located in the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)

    def test_the_committed_wrap_log_is_the_verdict_it_records(self) -> None:
        """The recorded body mutant must still be the run its log describes.

        The log is the transcript of a real run, so it is the strongest
        available check that the rule admits the observation it was written
        for rather than only the shapes its unit tests construct. It is
        committed with the repository root rewritten to ``<repo>``, so it also
        exercises the marker restoration a fresh log does not need.
        """
        driver = load_driver()
        log = (ROOT / 'tools/verifier-fixtures/verus-kernel/wrap.log').read_text(
            encoding='utf-8'
        )

        verdict = driver._qualify_body(log, 1, driver.WRAP_BODY)

        self.assertEqual(verdict['clause'], 'loop-invariant')

    def test_an_unlocated_invariant_is_rejected(self) -> None:
        """An invariant error with no location is not evidence about the body."""
        log = (
            'error: invariant not satisfied at loop head\n'
            'verification results:: 14 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must name a line of the body'):
            self.driver._qualify_body(log, 1, self.driver.WRAP_BODY)


class InvocationTests(unittest.TestCase):
    """Build the helper argv both the positive and mutant runs share."""

    def setUp(self) -> None:
        """Load the driver once per test."""
        self.driver = load_driver()

    def test_the_helper_prefix_is_split_from_the_pin(self) -> None:
        """A quoted helper command must reach the helper as separate arguments."""
        invocation = self.driver._Invocation(
            'uv tool run --from "git+https://example.invalid/repo@abc" prover-tools',
            ROOT / '.verus/sample/verus',
        )

        argv = invocation.command(Path('/tmp/root.rs'), '--extra-arg=--verify-root')

        self.assertEqual(argv[:6], ['uv', 'tool', 'run', '--from',
                                    'git+https://example.invalid/repo@abc', 'prover-tools'])
        self.assertIn('--repo-root', argv)
        self.assertEqual(argv[-1], '--extra-arg=--verify-root')

    def test_the_pinned_compiler_flags_are_always_forwarded(self) -> None:
        """Every root must compile as a 2024 library, whatever the selection."""
        invocation = self.driver._Invocation('prover-tools', Path('/opt/verus'))

        argv = invocation.command(Path('/tmp/root.rs'))

        for flag in ('--extra-arg=--crate-type=lib', '--extra-arg=--edition=2024'):
            self.assertIn(flag, argv)


class SummaryPatternTests(unittest.TestCase):
    """Keep the summary pattern able to see a partial-verification suffix."""

    def test_the_suffix_is_captured_rather_than_dropped(self) -> None:
        """A pattern that stopped at the count could not reject a selection."""
        driver = load_verdicts()
        match = driver._SUMMARY.search(
            'verification results:: 1 verified, 0 errors (partial verification with `--verify-*`)\n'
        )

        self.assertIsNotNone(match)
        self.assertIn('partial verification', match['suffix'])

    def test_the_location_pattern_reads_a_verus_diagnostic(self) -> None:
        """A diagnostic's file, line and column must all be recoverable."""
        diagnostic = load('verus_kernel_diagnostic', SCRIPTS / 'verus_kernel_diagnostic.py')
        match = diagnostic._LOCATION.search('  --> /tmp/root.rs:42:13\n')

        self.assertIsNotNone(match)
        self.assertEqual((match['path'], match['line'], match['column']),
                         ('/tmp/root.rs', '42', '13'))

    def test_the_clause_pattern_reads_a_clause_call(self) -> None:
        """A clause line is whatever `k1` to `k5` call it starts with."""
        driver = load_verdicts()
        match = driver._CLAUSE.match('        k4(lhs@, rhs@, old(out)@, final(out)@, r),')

        self.assertIsNotNone(match)
        self.assertEqual(match['clause'], 'k4')


if __name__ == '__main__':
    unittest.main()
