"""Qualify the shipped kernel's Verus verdicts without running a solver.

The kernel driver admits a positive root only on its exact pinned count and a
mutant only on a located postcondition failure at that mutant's own clause.
These tests exercise those two rules and the portable-log rewriting, so a
changed summary, a disqualified error, or a host path in a committed log fails
here rather than silently weakening the record.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
RECORD = ROOT / 'tools/verifier-fixtures/verus-kernel/provenance.json'


def _load_driver() -> ModuleType:
    """Load ``verus_kernel.py`` with its solver and helper imports stubbed.

    The driver imports its siblings by bare name, so every stub is installed
    at once rather than one dependency at a time. Nothing here reaches a
    solver, a helper or the network.
    """
    stubs = {
        'cyclopts': _Cyclopts(),
        'captured_command': _Namespace(run_captured=None),
    }
    with patch.dict('sys.modules', stubs):
        record = _load('kernel_record', SCRIPTS / 'kernel_record.py')
        stubs['kernel_record'] = record
        verdicts = _load('verus_kernel_verdicts', SCRIPTS / 'verus_kernel_verdicts.py')
        stubs['verus_kernel_verdicts'] = verdicts
        spec = importlib.util.spec_from_file_location(
            'verus_kernel', SCRIPTS / 'verus_kernel.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _load_verdicts() -> ModuleType:
    """Load ``verus_kernel_verdicts.py``, which imports nothing but the stdlib."""
    return _load('verus_kernel_verdicts', SCRIPTS / 'verus_kernel_verdicts.py')


def _load(name: str, path: Path) -> ModuleType:
    """Execute ``path`` as ``name``, resolving imports from ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Namespace:
    """Minimal attribute holder for one stubbed import."""

    def __init__(self, **attributes: object) -> None:
        """Expose each keyword as an attribute, so a stub can name what it fakes."""
        self.__dict__.update(attributes)


class _Cyclopts:
    """Cyclopts stand-in whose ``App`` accepts parameters and a default."""

    def App(self, **_: object) -> _Namespace:
        """Return an app whose ``default`` decorator is the identity."""
        return _Namespace(default=lambda function: function)

    @staticmethod
    def Parameter(**attributes: object) -> _Namespace:
        """Accept the environment-first annotations the driver declares."""
        return _Namespace(**attributes)


SUMMARY = 'verification results:: 19 verified, 0 errors\n'


class PositiveQualificationTests(unittest.TestCase):
    """Admit the positive root only on the exact pinned, whole-crate count."""

    def setUp(self) -> None:
        """Load the driver once per test."""
        self.driver = _load_verdicts()

    def test_the_pinned_count_qualifies(self) -> None:
        """The recorded count with no suffix must be accepted."""
        verdict = self.driver._qualify_positive(SUMMARY, 0)

        self.assertEqual(verdict, {'kind': 'positive', 'verified': 19})

    def test_a_different_count_is_rejected(self) -> None:
        """Any count other than the pin must request a reviewed update."""
        for count in (18, 20, 119):
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
        failing = 'verification results:: 19 verified, 1 errors\n'
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
        self.verdicts = _load_verdicts()
        self.driver = _load_driver()

    def _diagnostic(self, clause: str) -> str:
        """Return a located failure naming the line that writes ``clause``."""
        source = self.driver.MUTANT_ROOT
        lines = source.read_text(encoding='utf-8').splitlines()
        line = next(
            index
            for index, text in enumerate(lines, start=1)
            if text.strip().startswith(f'{clause}(')
        )
        return (
            'error: postcondition not satisfied\n'
            f'  --> {source}:{line}:13\n'
            'verification results:: 0 verified, 1 errors\n'
        )

    def _qualify(self, log: str, exit_code: int, name: str, clauses: list[str]) -> dict:
        """Qualify ``log`` against the mutant root the driver compiles."""
        return self.verdicts._qualify_mutant(
            log, exit_code, name, clauses, self.driver.MUTANT_ROOT
        )

    def test_the_intended_clause_qualifies(self) -> None:
        """Each mutant's own clause line must produce a rejection verdict."""
        for name, clause in self.driver.MUTANTS.items():
            with self.subTest(mutant=name):
                clauses = [clause]
                verdict = self._qualify(self._diagnostic(clause), 1, name, clauses)
                self.assertEqual(verdict['kind'], 'mutant')
                self.assertEqual(verdict['clauses'], clauses)

    def test_a_neighbouring_clause_is_rejected(self) -> None:
        """A failure at a clause the mutant does not owe must not qualify."""
        name = 'mutant_late'
        intended = self.driver.MUTANTS[name]
        wrong = next(clause for clause in ('k1', 'k2', 'k3', 'k5') if clause != intended)
        with self.assertRaisesRegex(RuntimeError, 'not the intended'):
            self._qualify(self._diagnostic(wrong), 1, name, [intended])

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
        """Load the verdict rules once per test."""
        self.driver = _load_verdicts()

    def test_a_loop_invariant_failure_qualifies(self) -> None:
        """An invariant failure with a non-zero error count is the verdict."""
        log = (
            'error: invariant not satisfied at loop head\n'
            'verification results:: 14 verified, 1 errors\n'
        )
        verdict = self.driver._qualify_body(log, 1)

        self.assertEqual(verdict['clause'], 'loop-invariant')

    def test_a_verified_body_is_rejected(self) -> None:
        """A body that verifies is not a rejected mutant."""
        with self.assertRaisesRegex(RuntimeError, 'must not verify'):
            self.driver._qualify_body(SUMMARY, 0)

    def test_a_postcondition_only_failure_is_rejected(self) -> None:
        """Some other obligation must not stand in for the loop invariant."""
        log = (
            'error: postcondition not satisfied\n'
            '  --> scratch.rs:10:5\n'
            'verification results:: 0 verified, 1 errors\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'must fail a loop invariant'):
            self.driver._qualify_body(log, 1)


class RecordTests(unittest.TestCase):
    """Keep the committed record reproducible and free of host paths."""

    def setUp(self) -> None:
        """Load the driver and its record module once per test."""
        self.driver = _load_driver()
        self.record = _load('kernel_record', SCRIPTS / 'kernel_record.py')

    def _record(self) -> dict:
        """Read the committed record, which every assertion here inspects."""
        return json.loads(RECORD.read_text(encoding='utf-8'))

    def test_portable_text_removes_both_roots(self) -> None:
        """Both the repository root and the home directory must be rewritten."""
        text = f'{ROOT}/crates and {Path.home()}/cache'

        rewritten = self.record.portable_text(text)

        self.assertEqual(rewritten, '<repo>/crates and ~/cache')

    def test_the_committed_record_carries_no_host_path(self) -> None:
        """A committed observation must not publish a worktree or account name."""
        text = RECORD.read_text(encoding='utf-8')

        self.assertNotIn(str(ROOT), text)
        self.assertNotIn(str(Path.home()), text)

    def test_every_committed_log_matches_its_digest(self) -> None:
        """A digest must bind the exact bytes a reader can check."""
        for observation in self._record()['observations']:
            with self.subTest(candidate=observation['candidate']):
                log = ROOT / observation['log']
                digest = hashlib.sha256(log.read_bytes()).hexdigest()
                self.assertEqual(digest, observation['sha256'])

    def test_the_record_binds_the_verdict_rules_it_was_decided_by(self) -> None:
        """Splitting the rules out must not leave them outside the record.

        The digests bind the scripts that produced these observations. A driver
        whose rules moved to a sibling module still has to name that module, or
        a reader could re-run the recorded commands against different rules.
        """
        digests = self._record()['source_digests']

        self.assertIn('scripts/verus_kernel.py', digests)
        self.assertIn('scripts/verus_kernel_verdicts.py', digests)

    def test_the_record_binds_the_digest_rule_it_was_computed_by(self) -> None:
        """The structural digest is a rule too, so its source must be bound."""
        self.assertIn('scripts/kernel_record.py', self._record()['source_digests'])

    def test_the_record_hands_admission_to_the_proof_profile(self) -> None:
        """The observations must name PF05 as the admitting component."""
        admission = self._record()['admission']

        self.assertIn('PF05.proof@2.3.5', admission)

    def test_every_mutant_is_recorded_once(self) -> None:
        """One observation per mutant, plus the positive root and the wrap copy."""
        candidates = [
            observation['candidate']
            for observation in self._record()['observations']
        ]

        self.assertEqual(candidates.count('positive'), 1)
        self.assertEqual(candidates.count('wrap'), 1)
        for name in self.driver.MUTANTS:
            self.assertEqual(candidates.count(name), 1, name)


class InvocationTests(unittest.TestCase):
    """Build the helper argv both the positive and mutant runs share."""

    def setUp(self) -> None:
        """Load the driver once per test."""
        self.driver = _load_driver()

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
        driver = _load_verdicts()
        match = driver._SUMMARY.search(
            'verification results:: 1 verified, 0 errors (partial verification with `--verify-*`)\n'
        )

        self.assertIsNotNone(match)
        self.assertIn('partial verification', match['suffix'])

    def test_the_location_pattern_reads_a_verus_diagnostic(self) -> None:
        """A diagnostic's file, line and column must all be recoverable."""
        driver = _load_verdicts()
        match = driver._LOCATION.search('  --> /tmp/root.rs:42:13\n')

        self.assertIsNotNone(match)
        self.assertEqual((match['path'], match['line'], match['column']),
                         ('/tmp/root.rs', '42', '13'))

    def test_the_clause_pattern_reads_a_clause_call(self) -> None:
        """A clause line is whatever `k1` to `k5` call it starts with."""
        driver = _load_verdicts()
        match = driver._CLAUSE.match('        k4(lhs@, rhs@, old(out)@, final(out)@, r),')

        self.assertIsNotNone(match)
        self.assertEqual(match['clause'], 'k4')


if __name__ == '__main__':
    unittest.main()
