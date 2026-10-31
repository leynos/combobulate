"""Keep recorded verifier provenance free of host-specific paths.

A committed command that names ``/home/<user>`` publishes the account name and
the worktree layout, and it cannot be reproduced on another machine. The probe
still executes the real argument vector; only the recorded copy is rewritten.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import (
    ROOT,
    load_probe_provenance,
    load_verifier_probe_support,
)


class PortableArgumentTests(unittest.TestCase):
    """Rewrite only the copy that reaches the committed record."""

    def test_repository_root_becomes_a_placeholder(self) -> None:
        """A worktree path must not reach the committed record."""
        support = load_verifier_probe_support()

        recorded = support.portable_argument(str(ROOT / 'tools/verifier-fixtures'))

        self.assertEqual(
            recorded,
            '<repo>/tools/verifier-fixtures',
            'the repository root must be replaced by the placeholder',
        )

    def test_home_directory_becomes_a_tilde(self) -> None:
        """The account name must not reach the committed record."""
        support = load_verifier_probe_support()
        home = Path('/home/probe')
        argument = '/home/probe/.kani/kani-0.67.0/bin/kani-driver'

        with patch.object(Path, 'home', return_value=home):
            recorded = support.portable_argument(argument)

        self.assertEqual(
            recorded,
            '~/.kani/kani-0.67.0/bin/kani-driver',
            'the home directory must be replaced by a tilde',
        )

    def test_other_arguments_are_unchanged(self) -> None:
        """Ordinary flags and values must be recorded exactly."""
        support = load_verifier_probe_support()

        self.assertEqual(
            support.portable_argument('--harness'),
            '--harness',
            'an argument outside the home and repository must stay unchanged',
        )


class CaptureRecordTests(unittest.TestCase):
    """Execute the real vector while recording the portable copy."""

    def test_capture_runs_the_real_argv_and_records_the_portable_copy(self) -> None:
        """The evidence must not publish the path the probe actually used."""
        support = load_verifier_probe_support()
        support.CommandSpec = Mock(side_effect=lambda argv, **kwargs: argv)
        support.run_command = Mock(
            return_value=SimpleNamespace(exit_code=0, stdout='out', stderr='')
        )
        real = [str(ROOT / 'tools/kani'), 'kani', '--version']

        with tempfile.TemporaryDirectory() as directory:
            record = support.capture(real, ROOT, Path(directory) / 'probe.log', {})

        self.assertEqual(
            record['command'],
            ['<repo>/tools/kani', 'kani', '--version'],
            'the record must replace the repository root',
        )
        self.assertEqual(
            support.run_command.call_args.args[0],
            tuple(real),
            'the probe must still execute the real argument vector',
        )


class VerusProvenanceTests(unittest.TestCase):
    """Record the solver without its per-user cache path."""

    def test_solver_path_is_recorded_portably(self) -> None:
        """A uv cache path must not reach the committed record."""
        module = load_probe_provenance()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            solver = home / '.cache/uv/archive-v0/bin/z3'
            solver.parent.mkdir(parents=True)
            solver.write_text('solver')
            record_path = home / 'provenance.json'

            with patch.object(Path, 'home', return_value=home):
                module.write_verus_provenance(
                    record_path,
                    '0.2026.09.06.8dea4a2',
                    solver,
                    'Z3 version 4.16.0 - 64 bit',
                    [],
                )

            record = json.loads(record_path.read_text(encoding='utf-8'))

        self.assertEqual(
            record['z3'],
            '~/.cache/uv/archive-v0/bin/z3',
            'the solver path must be recorded relative to the home directory',
        )