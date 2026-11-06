"""Classify how the cardinality gate's bounded child ended.

Execution runs under GNU ``timeout``, and a child that ignores ``SIGTERM`` is
killed after the grace period. A stray ``SIGKILL`` produces the same status as
an enforced escalation, so the announcement ``timeout`` writes to standard
error is what distinguishes a deadline the recipe enforced from a kill it did
not cause. These cases pin that classification, and the shape of the bounded
invocation, without running a real build.

The preparation half of the gate lives in ``test_cardinality_ui_gate``.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cardinality_ui_gate


class RunClassificationTests(unittest.TestCase):
    """Report a deadline the recipe enforced, and only that deadline."""

    def run_with(self, completed: subprocess.CompletedProcess) -> tuple[int, str]:
        """Run the recorded binary with a stubbed child and captured diagnostics."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            binary = Path(temporary_directory) / 'cardinality_ui'
            binary.write_text('#!/bin/sh\n')
            record = Path(temporary_directory) / 'record'
            record.write_text(f'{binary}\n')
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
                patch.object(cardinality_ui_gate.sys, 'stderr') as diagnostics,
            ):
                status = cardinality_ui_gate.run()
            return status, ''.join(call.args[0] for call in diagnostics.write.call_args_list)

    def test_a_sigterm_defeat_reports_the_deadline(self) -> None:
        """Status 124 is GNU timeout's own report that the deadline expired."""
        status, diagnostics = self.run_with(
            subprocess.CompletedProcess(
                args=[],
                returncode=124,
                stdout='',
                stderr='timeout: sending signal TERM to command ‘cardinality_ui’\n',
            )
        )
        self.assertEqual(status, 124)
        self.assertIn('exceeded its 600s deadline', diagnostics)

    def test_an_announced_kill_reports_the_escalation(self) -> None:
        """A trapped SIGTERM ends through SIGKILL, which is still a deadline.

        ``timeout`` re-raises the signal on itself rather than exiting with it,
        so ``subprocess`` reports the child as ``-9`` and this module reports
        the shell equivalent. The assertion checks both halves of the contract.
        """
        status, diagnostics = self.run_with(
            subprocess.CompletedProcess(
                args=[],
                returncode=-9,
                stdout='',
                stderr=(
                    'timeout: sending signal TERM to command ‘cardinality_ui’\n'
                    'timeout: sending signal KILL to command ‘cardinality_ui’\n'
                ),
            )
        )
        self.assertEqual(status, 137)
        self.assertIn('ignored SIGTERM', diagnostics)

    def test_an_unannounced_kill_is_not_a_deadline(self) -> None:
        """A stray SIGKILL must surface its status, not a guessed cause."""
        status, diagnostics = self.run_with(
            subprocess.CompletedProcess(args=[], returncode=-9, stdout='', stderr='')
        )
        self.assertEqual(status, 137)
        self.assertNotIn('deadline', diagnostics)
        self.assertNotIn('ignored SIGTERM', diagnostics)

    def test_an_ordered_exit_status_is_propagated_unchanged(self) -> None:
        """An ordinary failing child must not be rewritten as a signal death."""
        status, diagnostics = self.run_with(
            subprocess.CompletedProcess(args=[], returncode=101, stdout='', stderr='')
        )
        self.assertEqual(status, 101)
        self.assertEqual(diagnostics, '')

    def test_the_run_bounds_the_child_and_scrubs_the_manifest_variable(self) -> None:
        """The child runs under timeout with trybuild's variable removed."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            binary = Path(temporary_directory) / 'cardinality_ui'
            binary.write_text('#!/bin/sh\n')
            record = Path(temporary_directory) / 'record'
            record.write_text(f'{binary}\n')
            captured: dict[str, object] = {}

            def run_child(arguments, **options):
                """Capture the bounded invocation and report a clean exit."""
                captured['arguments'] = arguments
                captured['options'] = options
                return subprocess.CompletedProcess(
                    args=arguments, returncode=0, stdout='', stderr=''
                )

            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', run_child),
                patch.dict(os.environ, {'CARGO_MANIFEST_DIR': '/root/package'}, clear=True),
            ):
                self.assertEqual(cardinality_ui_gate.run(), 0)

            self.assertEqual(
                captured['arguments'][:5],
                ['timeout', '--verbose', '--signal=TERM', '--kill-after=2s', '600'],
            )
            self.assertEqual(captured['arguments'][5], str(binary))
            self.assertNotIn('CARGO_MANIFEST_DIR', captured['options']['env'])
            self.assertEqual(
                captured['options']['cwd'],
                cardinality_ui_gate.GATE_DIRECTORY,
                'trybuild needs the gate package as its working directory',
            )


if __name__ == '__main__':
    unittest.main()
