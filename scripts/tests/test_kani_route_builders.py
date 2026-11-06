"""Guard the Kani route builders without installing or running Kani.

Each route changes how one harness subject reaches the driver: the helper needs
every harness argument wrapped as ``--extra-arg``, while the direct route passes
them bare. A capture is still executed, so the tests inject the support
module's capture boundary and assert the exact vector it receives rather than
spawning a verifier.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from verifier_probe_loader import ROOT, load_kani_probe

# Only the in-place tests fabricate a prefix directly; they never build one
# through ``kani_prefix``, so they need no toolchain record beside the path.
INSTALLATION = Path('/opt/kani')
DIRECTORY = Path('/repo/tools/verifier-fixtures/kani-corpus')
SCRATCH = Path('/repo/target/epm1-native-workspace')
OUTPUT = Path('/repo/tools/verifier-fixtures/kani-corpus/observations')
ENVIRONMENT = {'PATH': '/usr/bin'}
TOOLCHAIN = 'nightly-2025-11-21-x86_64-unknown-linux-gnu'

SUBJECT = {'id': 'verified', 'arguments': ['--harness', 'verification::verified'], 'expected_exit': 0}


def _staged_installation(directory: Path, toolchain: str = TOOLCHAIN) -> Path:
    """Return a stand-in release that records the toolchain it was built from.

    ``_kani_environment`` reads the SDK toolchain from the installation rather
    than assuming the constant, so the stand-in has to carry that record. The
    record is a parameter so a test can stage a release that bundles a
    different nightly.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'rust-toolchain-version').write_text(f'{toolchain}\n')
    return directory


def _kani():
    """Return the private ``kani_probe`` module with the real support helpers.

    The CLI imports these builders by name, so the module itself is loaded
    directly rather than reached through the CLI namespace.

    Examples
    --------
    The module owns the route builders rather than the CLI surface::

        _kani()._kani_arguments(SUBJECT, 'direct')  # ['--harness', ...]
    """
    return load_kani_probe()


class PrefixTests(unittest.TestCase):
    """Keep each route's prefix and environment distinct."""

    def setUp(self) -> None:
        """Provide a release directory that records its bundled toolchain."""
        self._temporary = tempfile.TemporaryDirectory()
        self.installation = _staged_installation(Path(self._temporary.name) / 'kani')

    def tearDown(self) -> None:
        """Remove the stand-in installation."""
        self._temporary.cleanup()

    def test_helper_route_names_the_installation_and_working_directory(self) -> None:
        """The helper must be told which release to use and where to build."""
        prefix, environment = _kani().kani_prefix(
            'helper', 'prover-tools', self.installation, DIRECTORY, ENVIRONMENT
        )

        self.assertEqual(
            prefix[:3],
            ['prover-tools', 'kani', 'exec'],
            'the helper route must call kani exec',
        )
        self.assertIn(
            '--installation',
            prefix,
            'the helper must be given the pinned installation',
        )
        self.assertEqual(
            prefix[prefix.index('--installation') + 1],
            str(self.installation),
            'the installation path must follow its flag',
        )
        self.assertEqual(
            prefix[prefix.index('--cwd') + 1],
            str(DIRECTORY),
            'the fixture directory must be the working directory',
        )
        self.assertIs(
            environment,
            ENVIRONMENT,
            'the helper route must not rewrite the caller environment',
        )

    def test_direct_route_runs_the_installation_driver(self) -> None:
        """The direct route must bypass the helper and use the SDK driver."""
        prefix, _ = _kani().kani_prefix(
            'direct', 'prover-tools', self.installation, DIRECTORY, ENVIRONMENT
        )

        self.assertEqual(
            prefix,
            [str(self.installation / 'bin/kani-driver'), 'kani'],
            'the direct route must run the installed driver',
        )

    def test_direct_route_selects_the_matching_sdk_environment(self) -> None:
        """The helper rejects ancestor backend keys, so the direct route sets its own."""
        _, environment = _kani().kani_prefix(
            'direct', 'prover-tools', self.installation, DIRECTORY, ENVIRONMENT
        )

        self.assertEqual(
            environment['CARGO_PROFILE_DEV_CODEGEN_BACKEND'],
            'llvm',
            'the direct route must select the LLVM backend',
        )
        self.assertEqual(
            environment['RUSTFLAGS'],
            '-D warnings',
            'the direct route must deny warnings',
        )
        self.assertIn(
            str(self.installation / 'toolchain/bin'),
            environment['PATH'],
            'the SDK toolchain must lead PATH',
        )
        self.assertEqual(
            environment['PATH'].split(':')[-1],
            '/usr/bin',
            'the caller PATH must be retained after the SDK',
        )

    def test_an_unknown_route_is_rejected_by_name(self) -> None:
        """A typo must fail rather than silently select a route."""
        with self.assertRaisesRegex(ValueError, 'helper or direct'):
            _kani().kani_prefix('expected', 'prover-tools', self.installation, DIRECTORY, ENVIRONMENT)

    def test_a_release_bundling_another_nightly_is_rejected(self) -> None:
        """A pin bump that lands a different nightly must fail, not be recorded.

        ``tools/kani/VERSION`` names a release, and the release carries its own
        toolchain. Continuing here would compile the harnesses with an SDK the
        constant does not describe.
        """
        other = _staged_installation(
            Path(self._temporary.name) / 'other', 'nightly-2026-01-01-x86_64-unknown-linux-gnu'
        )

        with self.assertRaisesRegex(RuntimeError, 'not nightly-2025-11-21'):
            _kani().kani_prefix('direct', 'prover-tools', other, DIRECTORY, ENVIRONMENT)

    def test_a_release_without_a_toolchain_record_is_rejected(self) -> None:
        """Reporting the constant would restore the claim the check exists to avoid."""
        bare = Path(self._temporary.name) / 'bare'
        bare.mkdir()

        with self.assertRaisesRegex(RuntimeError, 'records no toolchain'):
            _kani().kani_prefix('direct', 'prover-tools', bare, DIRECTORY, ENVIRONMENT)


class ArgumentWrappingTests(unittest.TestCase):
    """Wrap harness arguments only where the helper requires it."""

    def test_helper_wraps_each_argument_as_an_extra_argument(self) -> None:
        """The helper accepts harness flags only through ``--extra-arg``."""
        arguments = _kani()._kani_arguments(SUBJECT, 'helper')

        self.assertEqual(
            arguments,
            ['--extra-arg=--harness', '--extra-arg=verification::verified'],
            'every harness argument must be wrapped for the helper route',
        )

    def test_direct_passes_the_arguments_unchanged(self) -> None:
        """The direct route must not double-wrap arguments the driver accepts."""
        arguments = _kani()._kani_arguments(SUBJECT, 'direct')

        self.assertEqual(arguments, SUBJECT['arguments'], 'the direct route must pass the arguments bare')


class ObservationSelectionTests(unittest.TestCase):
    """Select subjects by identity and bound only the ones that hang."""

    def setUp(self) -> None:
        """Capture every command the builders would execute."""
        self.module = _kani()
        self.captured: list[list[str]] = []
        self.module._capture = Mock(side_effect=self._record)

    def _record(self, command, directory, output, environment) -> dict:
        """Stand in for the support capture, recording the vector it was given."""
        self.captured.append(command)
        return {'command': command, 'cwd': str(directory), 'exit_code': 0, 'sha256': 'x', 'log': str(output)}

    def definitions(self) -> dict:
        """Return two subjects, the second of which needs an external timeout."""
        return {
            'runs': [
                SUBJECT,
                {
                    'id': 'multiplication_timeout',
                    'arguments': ['--harness', 'verification::multiplication_timeout'],
                    'expected_exit': 0,
                    'external_timeout': True,
                },
            ]
        }

    def test_only_the_named_subject_is_captured(self) -> None:
        """An ``only`` selection must not run the rest of the corpus."""
        observations = self.module._kani_observations(
            self.definitions(), ['kani'], 'direct', DIRECTORY, OUTPUT, ENVIRONMENT, 'verified'
        )

        self.assertEqual([item['id'] for item in observations], ['verified'], 'the selection must capture one subject')
        self.assertEqual(len(self.captured), 1, 'an unselected subject must not be executed')

    def test_missing_selection_captures_every_subject(self) -> None:
        """The default route must run the whole corpus."""
        observations = self.module._kani_observations(
            self.definitions(), ['kani'], 'direct', DIRECTORY, OUTPUT, ENVIRONMENT, None
        )

        self.assertEqual(
            [item['id'] for item in observations],
            ['verified', 'multiplication_timeout'],
            'every defined subject must be captured when nothing is selected',
        )

    def test_only_the_timeout_subject_is_bounded_externally(self) -> None:
        """An ordinary subject must not pay for a timeout wrapper it does not need."""
        self.module._kani_observations(
            self.definitions(), ['kani'], 'direct', DIRECTORY, OUTPUT, ENVIRONMENT, None
        )

        self.assertEqual(self.captured[0][0], 'kani', 'an ordinary subject must run unwrapped')
        self.assertEqual(
            self.captured[1][:3],
            ['timeout', '--signal=TERM', '8s'],
            'the timeout subject must be bounded by timeout',
        )

    def test_each_subject_writes_its_own_log(self) -> None:
        """Two subjects sharing a log would make one digest cover both."""
        self.module._kani_observations(
            self.definitions(), ['kani'], 'direct', DIRECTORY, OUTPUT, ENVIRONMENT, None
        )

        logs = [call.args[2] for call in self.module._capture.call_args_list]

        self.assertEqual(len(set(logs)), len(logs), 'each subject must own its observation log')
        self.assertTrue(all(log.parent == OUTPUT for log in logs), 'every log must be written to the output directory')


class InPlaceConstructionTests(unittest.TestCase):
    """Run one completed harness against the scratch kernel/facade workspace."""

    def setUp(self) -> None:
        """Capture every command the builders would execute."""
        self.module = _kani()
        self.captured: list[list[str]] = []
        self.module._capture = Mock(side_effect=self._record)

    def _record(self, command, directory, output, environment) -> dict:
        """Stand in for the support capture, recording the vector it was given."""
        self.captured.append(command)
        return {'command': command, 'cwd': str(directory), 'exit_code': 0, 'sha256': 'x', 'log': str(output)}

    def test_helper_route_swaps_only_the_working_directory(self) -> None:
        """The scratch workspace replaces ``--cwd``; the rest of the prefix stays."""
        prefix = ['prover-tools', 'kani', 'exec', '--installation', str(INSTALLATION), '--cwd', str(DIRECTORY)]

        observation = self.module._kani_in_place_observation(
            prefix, 'helper', SCRATCH, OUTPUT, ENVIRONMENT
        )

        command = self.captured[0]
        self.assertEqual(
            command[: len(prefix) - 1],
            prefix[:-1],
            'the helper prefix must be preserved',
        )
        self.assertEqual(
            command[len(prefix) - 1],
            str(SCRATCH),
            'the working directory must become the scratch workspace',
        )
        self.assertEqual(
            observation['id'],
            'in_place',
            'the observation must be identifiable',
        )
        self.assertEqual(
            observation['expected_exit'],
            0,
            'the in-place run must be expected to succeed',
        )

    def test_helper_route_wraps_the_selected_harness(self) -> None:
        """The in-place run must select one harness through the helper's wrapper."""
        prefix = ['prover-tools', 'kani', 'exec', '--installation', str(INSTALLATION), '--cwd', str(DIRECTORY)]

        self.module._kani_in_place_observation(prefix, 'helper', SCRATCH, OUTPUT, ENVIRONMENT)

        self.assertEqual(
            self.captured[0][-4:],
            [
                '--extra-arg=--harness',
                '--extra-arg=verification::target_facts',
                '--extra-arg=--exact',
                '--extra-arg=--verbose',
            ],
            'the helper must receive the harness selection wrapped',
        )

    def test_direct_route_passes_the_harness_selection_bare(self) -> None:
        """The direct route keeps the caller's prefix and its plain arguments."""
        prefix = [str(INSTALLATION / 'bin/kani-driver'), 'kani']

        self.module._kani_in_place_observation(prefix, 'direct', SCRATCH, OUTPUT, ENVIRONMENT)

        self.assertEqual(
            self.captured[0],
            [*prefix, '--harness', 'verification::target_facts', '--exact', '--verbose'],
            'the direct route must neither rewrite the prefix nor wrap its arguments',
        )

    def test_the_in_place_run_builds_in_the_scratch_workspace(self) -> None:
        """The harness must be compiled against the scratch workspace."""
        prefix = ['prover-tools', 'kani', 'exec', '--installation', str(INSTALLATION), '--cwd', str(DIRECTORY)]

        self.module._kani_in_place_observation(prefix, 'helper', SCRATCH, OUTPUT, ENVIRONMENT)

        self.assertEqual(
            self.module._capture.call_args.args[1],
            SCRATCH,
            'the capture must run in the scratch workspace, not the fixture directory',
        )


if __name__ == '__main__':
    unittest.main()
