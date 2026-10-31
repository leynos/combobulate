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


def _recorded_arguments(node: object) -> list[str]:
    """Return every argument of every ``command`` array in a decoded record.

    Records differ in shape: the Verus probe nests its observations, while the
    verifier-free record carries one command at the top level. Walking the
    decoded JSON finds both without teaching this test each schema.

    Examples
    --------
    A nested observation is reached through its parent::

        _recorded_arguments({'observations': [{'command': ['prover-tools']}]})
        # ['prover-tools']
    """
    if isinstance(node, dict):
        arguments: list[str] = []
        for key, value in node.items():
            if key == 'command' and isinstance(value, list):
                arguments.extend(item for item in value if isinstance(item, str))
            else:
                arguments.extend(_recorded_arguments(value))
        return arguments
    if isinstance(node, list):
        return [item for child in node for item in _recorded_arguments(child)]
    return []


def _committed_records() -> list[tuple[Path, list[str]]]:
    """Return each committed verifier record with the arguments it publishes."""
    fixtures = ROOT / 'tools/verifier-fixtures'
    return [
        (path, _recorded_arguments(json.loads(path.read_text(encoding='utf-8'))))
        for path in sorted(fixtures.rglob('*.json'))
    ]


def _publishes_host_detail(argument: str) -> bool:
    """Report whether an argument names this worktree or an account home.

    Account homes are detected by their POSIX and macOS roots. Container paths
    such as ``/usr/local/bin`` remain legitimate, so the check is limited to
    roots that encode who and where the probe ran.
    """
    roots = ('/home/', '/Users/')
    return str(ROOT) in argument or any(root in argument for root in roots)


class CommittedRecordTests(unittest.TestCase):
    """Keep every committed record portable, whoever captured it.

    ``portable_argument`` governs new captures. A record captured before that
    rule still carries the runner's account path, and because the digest binds
    the captured log rather than the metadata, such a record is rewritten in
    place instead of being recaptured.
    """

    def test_records_are_discovered(self) -> None:
        """The scan must reach the committed records, not an empty directory."""
        records = _committed_records()

        self.assertIn(
            ROOT / 'tools/verifier-fixtures/verus-wiring-probe/verifier-free-hosted.json',
            [path for path, _ in records],
            'the hosted verifier-free record must be covered by the portability scan',
        )
        self.assertTrue(
            any(arguments for _, arguments in records),
            'the portability scan must find at least one recorded command',
        )

    def test_committed_commands_publish_no_host_paths(self) -> None:
        """No committed command may reveal the account or worktree that ran it."""
        offenders = [
            f'{path.relative_to(ROOT)}: {argument}'
            for path, arguments in _committed_records()
            for argument in arguments
            if _publishes_host_detail(argument)
        ]

        self.assertEqual(
            offenders,
            [],
            'recorded commands must replace host roots with `<repo>` and `~`',
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