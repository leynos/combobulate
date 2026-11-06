"""Reject a corpus that names no observable output, through one error type.

Every rejection is a ``RuntimeError`` from ``require_captured_output``. A
missing or unreadable log is an operating-system failure underneath, but it is
reported at the same boundary and with the original error chained, so a caller
cannot accidentally see a bare ``FileNotFoundError`` the documented contract
does not mention.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verifier_probe_loader import load_probe_provenance


class CapturedOutputBoundaryTests(unittest.TestCase):
    """Check the documented boundary of ``require_captured_output``."""

    def observation(self, log: Path, exit_code: int = 0, expected: int = 0) -> dict:
        """Return one captured record rooted at an absolute log path."""
        return {
            'id': 'subject',
            'log': str(log),
            'exit_code': exit_code,
            'expected_exit': expected,
        }

    def test_a_missing_log_is_reported_with_its_cause(self) -> None:
        """A record whose log was never written must not qualify a corpus."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'never-written.log'

            with self.assertRaisesRegex(RuntimeError, 'could not be read') as raised:
                module.require_captured_output([self.observation(missing)])

        self.assertIsInstance(
            raised.exception.__cause__,
            OSError,
            'the operating-system error must be chained, not discarded',
        )

    def test_an_unreachable_log_path_is_reported_with_its_cause(self) -> None:
        """A path below a regular file is unreadable, not merely absent.

        Permission bits cannot be used here: the suite may run as root, where
        they do not deny access. A path through a non-directory component
        raises the same ``OSError`` family on any account.
        """
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / 'not-a-directory'
            blocker.write_text('occupied', encoding='utf-8')

            with self.assertRaisesRegex(RuntimeError, 'could not be read') as raised:
                module.require_captured_output([self.observation(blocker / 'child.log')])

        self.assertIsInstance(
            raised.exception.__cause__,
            OSError,
            'the traversal failure must be chained as the documented boundary error',
        )

    def test_an_empty_log_is_reported_by_name(self) -> None:
        """An empty capture proves nothing, however the command exited."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / 'empty.log'
            empty.write_text('', encoding='utf-8')

            with self.assertRaisesRegex(RuntimeError, 'is empty'):
                module.require_captured_output([self.observation(empty)])

    def test_no_observations_cannot_qualify_a_corpus(self) -> None:
        """An empty observation list is a missing capture, not a vacuous pass."""
        module = load_probe_provenance()

        with self.assertRaisesRegex(RuntimeError, 'missing verifier output'):
            module.require_captured_output([])

    def test_a_status_mismatch_is_reported_with_the_log(self) -> None:
        """Captured output that disagrees with its expectation is not a verdict."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'failed.log'
            log.write_text('error: proof did not hold', encoding='utf-8')

            with self.assertRaisesRegex(RuntimeError, 'expected 0'):
                module.require_captured_output(
                    [self.observation(log, exit_code=1, expected=0)]
                )

    def test_a_complete_matching_capture_passes(self) -> None:
        """The accept path must stay reachable, or the guard proves nothing."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'passed.log'
            log.write_text('verification results:: verified', encoding='utf-8')

            module.require_captured_output([self.observation(log)])


if __name__ == '__main__':
    unittest.main()
