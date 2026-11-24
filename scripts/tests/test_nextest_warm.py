"""Check the nextest warm-up scripts act on the same build the tests do.

The warm-up only helps when it fills the directory the test will use, with the
environment the test will use. These cases exercise that behaviour through the
script's functions and a fake Cargo, not the text of the nextest configuration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import nextest_warm


class FixtureEnvironmentTests(unittest.TestCase):
    """A fixture build must not depend on how the suite was invoked."""

    def test_selectors_are_removed_and_the_target_is_private(self) -> None:
        """The scrubbed names vanish and the fixture gets its own target."""
        inherited = {
            'RUSTFLAGS': '-D warnings',
            'CARGO_ENCODED_RUSTFLAGS': 'x',
            'CARGO_BUILD_TARGET': 'y',
            'KEPT': 'yes',
        }
        with patch.dict(os.environ, inherited, clear=False):
            environment = nextest_warm.fixture_environment(Path('/private/target'))
        for name in nextest_warm.FIXTURE_SCRUBBED_VARIABLES:
            self.assertNotIn(name, environment)
        self.assertEqual(environment['CARGO_TARGET_DIR'], '/private/target')
        self.assertEqual(environment['KEPT'], 'yes')


class GateEnvironmentTests(unittest.TestCase):
    """The gate must not inherit the root package's manifest directory."""

    def test_manifest_directory_is_removed(self) -> None:
        """Trybuild would copy the root package's manifest if it saw this."""
        with patch.dict(os.environ, {'CARGO_MANIFEST_DIR': '/root', 'KEPT': '1'}):
            environment = nextest_warm.gate_environment()
        self.assertNotIn('CARGO_MANIFEST_DIR', environment)
        self.assertEqual(environment['KEPT'], '1')


class TargetTmpdirTests(unittest.TestCase):
    """The warm-up follows Cargo's resolved target directory."""

    @staticmethod
    def fake_cargo(directory: str, script: str) -> str:
        """Write an executable stand-in for Cargo and return its path."""
        fake = Path(directory) / 'fake-cargo'
        fake.write_text(script)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return str(fake)

    def test_an_explicit_target_directory_wins(self) -> None:
        """Cargo honours ``CARGO_TARGET_DIR``, so the warm-up does too."""
        environment = {
            'CARGO_TARGET_DIR': '/explicit',
            'LLVM_PROFILE_FILE': '/coverage/x-%p.profraw',
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(nextest_warm.target_tmpdir(), Path('/explicit/tmp'))

    def test_coverage_runs_are_found_through_the_profile_directory(self) -> None:
        """``cargo llvm-cov`` builds in the directory it writes profiles to."""
        environment = {'LLVM_PROFILE_FILE': '/work/target/llvm-cov-target/x-%p.profraw'}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                nextest_warm.target_tmpdir(),
                Path('/work/target/llvm-cov-target/tmp'),
            )

    def test_a_plain_run_asks_cargo_for_the_workspace_target(self) -> None:
        """With no hint in the environment, Cargo's own answer is used."""
        with tempfile.TemporaryDirectory() as directory:
            payload = json.dumps({'target_directory': '/workspace/target'})
            fake = self.fake_cargo(directory, f"#!/bin/sh\nprintf '%s' '{payload}'\n")
            with patch.dict(os.environ, {'CARGO': fake}, clear=True):
                self.assertEqual(
                    nextest_warm.target_tmpdir(), Path('/workspace/target/tmp')
                )

    def test_an_explicit_build_target_skips_the_warm_up(self) -> None:
        """The triple moves the directory in a way the warm-up does not model."""
        with patch.dict(os.environ, {'CARGO_BUILD_TARGET': 'x86_64-unknown-linux-gnu'}):
            self.assertIsNone(nextest_warm.target_tmpdir())

    def test_a_failing_cargo_is_reported(self) -> None:
        """Without a hint or metadata the tests' directory cannot be found."""
        with tempfile.TemporaryDirectory() as directory:
            fake = self.fake_cargo(directory, '#!/bin/sh\nexit 1\n')
            with patch.dict(os.environ, {'CARGO': fake}, clear=True):
                with self.assertRaises(RuntimeError):
                    nextest_warm.target_tmpdir()


def recording_executable(directory: str, name: str, status: int) -> Path:
    """Write an executable that logs its arguments and environment, then exits.

    The log line holds the working directory, the target directory and
    manifest-directory variables, whether ``RUSTFLAGS`` was inherited, and the
    arguments, so a test can state what the child was given.
    """
    log = Path(directory) / f'{name}.log'
    script = Path(directory) / name
    script.write_text(
        '#!/bin/sh\n'
        f'printf "%s|%s|%s|%s|%s\\n" "$PWD" "${{CARGO_TARGET_DIR-unset}}" '
        f'"${{CARGO_MANIFEST_DIR-unset}}" "${{RUSTFLAGS-unset}}" "$*" >> {log}\n'
        f'exit {status}\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def recorded_lines(directory: str, name: str) -> list[list[str]]:
    """Return each logged invocation of a ``recording_executable`` as fields."""
    log = Path(directory) / f'{name}.log'
    return [line.split('|') for line in log.read_text().splitlines()]


class WarmUpBehaviourTests(unittest.TestCase):
    """Each warm-up gives its child the build the tests will find, and judges nothing."""

    def test_fixtures_build_privately_and_a_failing_fixture_is_not_fatal(self) -> None:
        """Both fixtures build in their own directories; the absence build may fail."""
        with tempfile.TemporaryDirectory() as directory:
            cargo = recording_executable(directory, 'cargo', status=101)
            environment = {
                'CARGO': str(cargo),
                'CARGO_TARGET_DIR': f'{directory}/target',
                'RUSTFLAGS': '-D warnings',
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(nextest_warm.main(['fixtures']), 0)
            calls = recorded_lines(directory, 'cargo')
        self.assertEqual(len(calls), 2)
        targets = [call[1] for call in calls]
        self.assertEqual(
            targets,
            [
                f'{directory}/target/tmp/polars-surface-absent',
                f'{directory}/target/tmp/native-consumer',
            ],
        )
        for call in calls:
            self.assertEqual(call[3], 'unset', 'RUSTFLAGS must not reach a fixture')
            self.assertIn('--frozen build --locked --offline', call[4])

    def test_the_gate_runs_from_its_own_directory_without_the_manifest_variable(
        self,
    ) -> None:
        """The recorded binary starts where the root test starts it."""
        with tempfile.TemporaryDirectory() as directory:
            binary = recording_executable(directory, 'gate', status=1)
            with (
                patch.dict(os.environ, {'CARGO_MANIFEST_DIR': '/root'}, clear=True),
                patch.object(
                    nextest_warm.cardinality_ui_gate,
                    'recorded_binary',
                    return_value=binary,
                ),
            ):
                self.assertEqual(nextest_warm.main(['gate']), 0)
            (call,) = recorded_lines(directory, 'gate')
        self.assertEqual(
            Path(call[0]).resolve(),
            nextest_warm.cardinality_ui_gate.GATE_DIRECTORY.resolve(),
        )
        self.assertEqual(call[2], 'unset')

    def test_the_workspace_read_is_offline_and_a_failure_is_not_fatal(self) -> None:
        """A failing resolution is left for the tests that read it to report."""
        with tempfile.TemporaryDirectory() as directory:
            cargo = recording_executable(directory, 'cargo', status=1)
            with patch.dict(os.environ, {'CARGO': str(cargo)}, clear=True):
                self.assertEqual(nextest_warm.main(['workspace']), 0)
            (call,) = recorded_lines(directory, 'cargo')
        self.assertTrue(call[4].startswith('--frozen tree'))


class MainTests(unittest.TestCase):
    """The command line accepts exactly one known warm-up."""

    def test_unknown_commands_are_rejected(self) -> None:
        """A typo in the nextest configuration fails loudly."""
        self.assertEqual(nextest_warm.main(['nope']), 2)
        self.assertEqual(nextest_warm.main([]), 2)

    def test_a_missing_prerequisite_stops_the_run(self) -> None:
        """No recorded gate binary is a failure the user can act on."""
        with patch.object(
            nextest_warm.cardinality_ui_gate,
            'recorded_binary',
            side_effect=RuntimeError('not prepared'),
        ):
            self.assertEqual(nextest_warm.main(['gate']), 1)


if __name__ == '__main__':
    unittest.main()
