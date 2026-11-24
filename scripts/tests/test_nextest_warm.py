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

    def test_tmp_sits_under_the_reported_target_directory(self) -> None:
        """A redirected target directory moves the warm-up with it."""
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'fake-cargo'
            payload = json.dumps({'target_directory': '/redirected/target'})
            fake.write_text(f"#!/bin/sh\nprintf '%s' '{payload}'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {'CARGO': str(fake)}):
                self.assertEqual(
                    nextest_warm.target_tmpdir(), Path('/redirected/target/tmp')
                )

    def test_a_failing_cargo_is_reported(self) -> None:
        """Without metadata the warm-up cannot find the tests' directory."""
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'fake-cargo'
            fake.write_text('#!/bin/sh\nexit 1\n')
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {'CARGO': str(fake)}):
                with self.assertRaises(RuntimeError):
                    nextest_warm.target_tmpdir()


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
