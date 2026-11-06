"""Exercise the cardinality gate's build selection and bounded execution.

Preparation lets Cargo choose its output directory, so the record it writes has
to name the executable Cargo reported for this build rather than a path derived
from the default layout. These cases drive the selector with Cargo-shaped JSON
and a private target directory, which is the condition an inherited
``CARGO_TARGET_DIR`` produces.

Execution is bounded by GNU ``timeout``. How a bounded child's ending is
classified lives with its own cases in ``test_cardinality_ui_deadline``.
"""

from __future__ import annotations

import json
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


def artifact(executable: str, name: str = 'cardinality_ui') -> str:
    """Render the one Cargo message field the selector reads.

    ``--message-format=json`` emits one object per line with a ``reason``, a
    ``target`` table, and — for a test target that produced a binary — an
    ``executable``. The selector must key on both the reason and the target
    name, so the fixture carries only those fields it is entitled to inspect.
    """
    return json.dumps(
        {'reason': 'compiler-artifact', 'target': {'name': name}, 'executable': executable}
    )


class ArtifactSelectionTests(unittest.TestCase):
    """Select the executable from Cargo's own message stream."""

    def test_selects_the_reported_executable(self) -> None:
        """A single artifact names the exact binary the build produced."""
        selected = cardinality_ui_gate._artifact_executable(
            artifact('/tmp/private-target/debug/deps/cardinality_ui-abc123')
        )
        self.assertEqual(selected, '/tmp/private-target/debug/deps/cardinality_ui-abc123')

    def test_ignores_artifacts_for_other_targets(self) -> None:
        """Another target in the same build must not displace the gate binary."""
        stream = '\n'.join(
            [
                artifact('/tmp/target/deps/some_helper', name='some_helper'),
                artifact('/tmp/target/deps/cardinality_ui-abc123'),
            ]
        )
        self.assertEqual(
            cardinality_ui_gate._artifact_executable(stream),
            '/tmp/target/deps/cardinality_ui-abc123',
        )

    def test_ignores_human_readable_progress_and_other_reasons(self) -> None:
        """Non-JSON lines and unrelated messages are skipped, not fatal."""
        stream = '\n'.join(
            [
                '   Compiling combobulate v0.1.0',
                json.dumps({'reason': 'build-finished', 'success': True}),
                artifact('/tmp/target/deps/cardinality_ui-def456'),
            ]
        )
        self.assertEqual(
            cardinality_ui_gate._artifact_executable(stream),
            '/tmp/target/deps/cardinality_ui-def456',
        )

    def test_reports_absent_when_no_artifact_names_the_executable(self) -> None:
        """A build that only compiled dependencies names no binary to run."""
        stream = '\n'.join(
            [
                json.dumps({'reason': 'compiler-artifact', 'target': {'name': 'trybuild'}}),
                json.dumps({'reason': 'build-finished', 'success': True}),
            ]
        )
        self.assertIsNone(cardinality_ui_gate._artifact_executable(stream))


class RecordedBinaryTests(unittest.TestCase):
    """Read the path a completed preparation recorded."""

    def test_reads_the_recorded_absolute_path(self) -> None:
        """The record holds one absolute path, which is returned unchanged."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            record.write_text('/private/target/deps/cardinality_ui-abc\n')
            with patch.object(cardinality_ui_gate, 'RECORD', record):
                self.assertEqual(
                    cardinality_ui_gate.recorded_binary(),
                    Path('/private/target/deps/cardinality_ui-abc'),
                )

    def test_treats_a_missing_record_as_preparation_that_did_not_run(self) -> None:
        """A cold checkout has no record, and that is reported as such."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'absent'
            with patch.object(cardinality_ui_gate, 'RECORD', record):
                with self.assertRaisesRegex(RuntimeError, 'unreadable'):
                    cardinality_ui_gate.recorded_binary()

    def test_treats_an_empty_record_as_absent(self) -> None:
        """A truncated preparation must not be handed an empty executable path."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            record.write_text('\n')
            with patch.object(cardinality_ui_gate, 'RECORD', record):
                with self.assertRaisesRegex(RuntimeError, 'empty'):
                    cardinality_ui_gate.recorded_binary()


class PrepareTests(unittest.TestCase):
    """Bind a preparation to the executable its own build reported."""

    def test_records_the_path_reported_by_a_redirected_build(self) -> None:
        """An inherited target directory still yields the executable that was built."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            record = root / 'record'
            redirected = root / 'elsewhere/debug/deps/cardinality_ui-abc'
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='\n'.join(
                    [
                        artifact(str(redirected)),
                        json.dumps({'reason': 'build-finished', 'success': True}),
                    ]
                ),
                stderr='',
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
            ):
                prepared = cardinality_ui_gate.prepare()
            self.assertEqual(prepared, redirected)
            self.assertEqual(record.read_text(), f'{redirected}\n')

    def test_a_failed_build_is_reported_and_records_nothing(self) -> None:
        """A failing Cargo leaves no record, so the run stage cannot use a stale one."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            completed = subprocess.CompletedProcess(
                args=[], returncode=101, stdout='', stderr='error: could not compile'
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
            ):
                with self.assertRaisesRegex(RuntimeError, 'could not be built'):
                    cardinality_ui_gate.prepare()
            self.assertFalse(record.exists(), 'a failed build must not leave a record')

    def test_a_build_without_an_executable_is_reported(self) -> None:
        """A successful build that names no binary is a contract failure."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({'reason': 'build-finished', 'success': True}),
                stderr='',
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
            ):
                with self.assertRaisesRegex(RuntimeError, 'no executable'):
                    cardinality_ui_gate.prepare()

    def test_a_failed_build_withdraws_the_previous_record(self) -> None:
        """A record from an earlier preparation must not survive a failed rebuild.

        Starting from no record proves only that preparation writes nothing on
        failure. What a later ``run`` would actually pick up is the record the
        previous successful preparation left, so the case starts from one and
        requires it to be gone.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            record.write_text('/stale/target/debug/deps/cardinality_ui-old\n')
            completed = subprocess.CompletedProcess(
                args=[], returncode=101, stdout='', stderr='error: could not compile'
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
            ):
                with self.assertRaisesRegex(RuntimeError, 'could not be built'):
                    cardinality_ui_gate.prepare()

            self.assertFalse(
                record.exists(),
                'a failed rebuild must withdraw the record it replaced',
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                self.assertRaisesRegex(RuntimeError, 'unreadable'),
            ):
                cardinality_ui_gate.recorded_binary()

    def test_a_build_without_an_executable_withdraws_the_previous_record(self) -> None:
        """A successful Cargo run that names no binary is still a failed preparation.

        This is the harder half of the same contract: Cargo exits zero, so only
        the missing artifact distinguishes it from a real preparation. The
        record it replaced has to go either way.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            record.write_text('/stale/target/debug/deps/cardinality_ui-old\n')
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps({'reason': 'build-finished', 'success': True}),
                stderr='',
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', return_value=completed),
            ):
                with self.assertRaisesRegex(RuntimeError, 'no executable'):
                    cardinality_ui_gate.prepare()

            self.assertFalse(
                record.exists(),
                'a build that named no binary must withdraw the record it replaced',
            )
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                self.assertRaisesRegex(RuntimeError, 'unreadable'),
            ):
                cardinality_ui_gate.recorded_binary()

    def test_preparation_clears_the_redirecting_variables(self) -> None:
        """A parent target directory must not change where Cargo writes output."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / 'record'
            captured: dict[str, object] = {}

            def record_invocation(arguments, **options):
                """Capture the Cargo invocation and report a successful build."""
                captured['arguments'] = arguments
                captured['options'] = options
                return subprocess.CompletedProcess(
                    args=arguments,
                    returncode=0,
                    stdout=artifact('/private/target/deps/cardinality_ui-abc'),
                    stderr='',
                )

            environment = {
                'PATH': os.environ.get('PATH', ''),
                'CARGO_TARGET_DIR': '/left/over/from/the/caller',
                'RUSTFLAGS': '--cfg caller',
                'DEV_RUST_FLAGS': '-D warnings',
            }
            with (
                patch.object(cardinality_ui_gate, 'RECORD', record),
                patch.object(cardinality_ui_gate.subprocess, 'run', record_invocation),
                patch.dict(os.environ, environment, clear=True),
            ):
                cardinality_ui_gate.prepare()

            child_environment = captured['options']['env']
            self.assertNotIn('CARGO_TARGET_DIR', child_environment)
            self.assertEqual(
                child_environment['RUSTFLAGS'],
                '--cfg caller -D warnings',
                'the recipe must compose the caller flags with the development flags',
            )
            self.assertIn('--message-format=json', captured['arguments'])
            self.assertIn('--no-run', captured['arguments'])


class EntrypointTests(unittest.TestCase):
    """Dispatch preparation and execution, and reject anything else."""

    def test_unknown_subcommands_are_usage_errors(self) -> None:
        """An unrecognized argument must not silently prepare or run the gate."""
        self.assertEqual(cardinality_ui_gate.main(['build']), 2)

    def test_a_preparation_failure_exits_non_zero(self) -> None:
        """A failed run is reported rather than reported as success."""
        with patch.object(
            cardinality_ui_gate, 'run', side_effect=RuntimeError('no record')
        ):
            self.assertEqual(cardinality_ui_gate.main(['run']), 1)


if __name__ == '__main__':
    unittest.main()
