"""Read Verus run output the way the wiring probe does, from plain logs.

The probe qualifies a candidate on the summary line's exact counts and on the
mutant's located failure. These tests feed it constructed logs, so no Verus
installation is needed, and a count that is merely close cannot qualify.
"""

import tempfile
import unittest
from pathlib import Path

import verus_probe

POSITIVE = 'verification results:: 1 verified, 0 errors\n'
NEGATIVE = (
    'error: postcondition not satisfied\n'
    '  --> {path}:{line}:5\n'
    'verification results:: 0 verified, 1 errors\n'
)
MUTANT_SOURCE = """\
/// The seeded mutant.
pub fn mutant(value: u8) -> (result: u8)
    ensures result == value + 1,
{ value + 2 }
"""


class SummaryTests(unittest.TestCase):
    """The summary line must record the exact counts, not merely mention them."""

    def test_exact_counts_match(self) -> None:
        """A line with the requested counts is accepted."""
        self.assertTrue(verus_probe._reports_summary(POSITIVE, 1, 0))

    def test_other_counts_are_rejected(self) -> None:
        """One error or a different verified count must not pass as clean."""
        for log in ('verification results:: 1 verified, 1 errors\n',
                    'verification results:: 2 verified, 0 errors\n', ''):
            with self.subTest(log=log):
                self.assertFalse(verus_probe._reports_summary(log, 1, 0))


class QualificationTests(unittest.TestCase):
    """A candidate qualifies on its logs, exit codes and located mutant."""

    def _candidate(self, directory: Path, mutant_exit: int = 1) -> list[dict]:
        """Write a macro candidate's logs and return its observations."""
        source = directory / 'macro.rs'
        source.write_text(MUTANT_SOURCE, encoding='utf-8')
        (directory / 'macro-capability.log').write_text(POSITIVE, encoding='utf-8')
        (directory / 'macro-mutant.log').write_text(
            NEGATIVE.format(path=source, line=3), encoding='utf-8')
        return [{'candidate': 'macro', 'function': 'capability', 'exit_code': 0},
                {'candidate': 'macro', 'function': 'mutant', 'exit_code': mutant_exit}]

    def test_a_clean_capability_and_located_mutant_qualify(self) -> None:
        """The capability verifies and the mutant fails at its declaration."""
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            observations = self._candidate(directory)
            self.assertEqual(
                verus_probe._qualified_candidates(directory, observations, directory),
                ['macro'])

    def test_a_mutant_that_verifies_does_not_qualify(self) -> None:
        """A mutant that exits zero means the proof checks nothing."""
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            observations = self._candidate(directory, mutant_exit=0)
            self.assertEqual(
                verus_probe._qualified_candidates(directory, observations, directory), [])

    def test_a_missing_function_does_not_qualify(self) -> None:
        """A candidate that never ran its mutant is not qualified by default."""
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            observations = self._candidate(directory)[:1]
            self.assertEqual(
                verus_probe._qualified_candidates(directory, observations, directory), [])


class CommandTests(unittest.TestCase):
    """The commands select the one function each run is about."""

    def test_single_root_runs_through_the_shared_helper(self) -> None:
        """The single-root candidate goes through ``prover-tools verus run``."""
        command = verus_probe._verus_command(
            Path('/verus'), 'single-root', Path('/fx'), 'mutant', 'prover-tools --x')
        self.assertEqual(command[:4], ['prover-tools', '--x', 'verus', 'run'])
        self.assertIn('--extra-arg=--verify-function=mutant', command)

    def test_crate_candidates_use_cargo_verus_focus(self) -> None:
        """Crate candidates run through cargo-verus with a function selection."""
        command = verus_probe._verus_command(
            Path('/verus'), 'attributes', Path('/fx'), 'capability', 'unused')
        self.assertEqual(command[:3], ['/verus/cargo-verus', 'verus', 'focus'])
        self.assertIn('verus', command[command.index('--features') + 1:][:1])
        self.assertEqual(command[-1], '--verify-function=capability')


if __name__ == '__main__':
    unittest.main()
