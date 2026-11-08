"""Exercise verifier-free staging and orchestration with injected dependencies.

The real probes need a rootless container, a pinned base image, and a runner
without compiler admission. These tests replace the process and filesystem
boundaries with fakes, so the success and failure branches of the orchestrator
are checked deterministically and without podman.

Examples
--------
The staging set is derived from the fixture tree rather than listed twice::

    [path.name for path in staged_sources() if path.name == 'Cargo.toml']
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from verifier_probe_loader import load_structural_digest, load_verifier_free_probe

is_structural_digest = load_structural_digest().is_structural_digest

FIXTURES = Path(__file__).resolve().parents[2] / 'tools/verifier-fixtures'


def _module():
    """Return the verifier-free module loaded with the probe helper stubbed.

    Examples
    --------
    The module is private to the probe scripts, so it is loaded by path::

        _module().STAGING_FILES  # ('.cargo/config.toml', ...)
    """
    return load_verifier_free_probe()


class StagedSourcesTests(unittest.TestCase):
    """Bind the observation to exactly the files the build consumes."""

    def test_every_staged_file_is_a_real_repository_path(self) -> None:
        """A misspelt path would digest nothing and bind nothing."""
        module = _module()

        missing = [str(path) for path in module.staged_sources() if not path.is_file()]

        self.assertEqual(missing, [], 'every staged source must exist in the repository')

    def test_evidence_records_are_excluded_from_the_staged_set(self) -> None:
        """A record that hashed itself could never be committed."""
        module = _module()
        names = {path.name for path in module.staged_sources()}

        for ignored in ('provenance.json', 'verifier-free.json', 'verifier-free-hosted.json'):
            self.assertNotIn(ignored, names, f'{ignored} must not be staged')

    def test_build_output_is_excluded_from_the_staged_set(self) -> None:
        """A Cargo target directory is output, not a build input."""
        module = _module()

        staged = module.staged_sources()

        self.assertFalse(
            any(
                'target' in path.relative_to(FIXTURES / 'verus-wiring-probe').parts
                for path in staged
                if path.is_relative_to(FIXTURES)
            ),
            'build output must stay out of the staged set',
        )

    def test_root_toolchain_and_linker_pins_are_staged(self) -> None:
        """The container build must use the same compiler and linker as the host."""
        module = _module()
        staged = module.staged_sources()

        for name in module.STAGING_FILES:
            self.assertIn(
                Path(module.ROOT) / name,
                staged,
                f'the pinned {name} must be staged beside the fixture',
            )


class StagingTests(unittest.TestCase):
    """Copy the fixture and its pins into the scratch workspace."""

    def test_staging_places_the_fixture_and_the_pins(self) -> None:
        """The container builds ``probe/`` with the pins beside it."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'workspace'

            module._stage_verifier_free_workspace(workspace)

            self.assertTrue((workspace / 'probe/Cargo.toml').is_file(), 'the fixture must be staged as `probe/`')
            self.assertTrue((workspace / 'Containerfile').is_file(), 'the container recipe must be written')
            for name in module.STAGING_FILES:
                self.assertTrue((workspace / name).is_file(), f'the pinned {name} must be copied')

    def test_staging_is_idempotent(self) -> None:
        """A rerun must refresh the copied files rather than fail."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'workspace'

            module._stage_verifier_free_workspace(workspace)
            module._stage_verifier_free_workspace(workspace)

            self.assertTrue((workspace / 'probe/Cargo.toml').is_file(), 'a second staging run must succeed')

    def test_staging_copies_no_evidence_record(self) -> None:
        """A stale record inside the build must not ride along."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'workspace'

            module._stage_verifier_free_workspace(workspace)

            staged = workspace / 'probe'
            self.assertFalse((staged / 'provenance.json').exists(), 'provenance must not be staged')
            self.assertFalse((staged / 'target').exists(), 'build output must not be staged')


class BaseImageTests(unittest.TestCase):
    """Reuse a cached image and report a failed pull rather than proceeding."""

    def test_a_cached_image_is_not_pulled_again(self) -> None:
        """A pull costs time and network on every hosted run."""
        module = _module()
        module.run_command = Mock(return_value=SimpleNamespace(exit_code=0))
        module._capture = Mock()

        module.ensure_base_image(Path('/tmp/observations'), {})

        module._capture.assert_not_called()

    def test_a_failed_pull_is_reported_by_name(self) -> None:
        """Proceeding without the image would fail later and less clearly."""
        module = _module()
        module.run_command = Mock(return_value=SimpleNamespace(exit_code=1))
        module._capture = Mock(return_value={'exit_code': 1})

        with self.assertRaisesRegex(RuntimeError, 'base could not be fetched'):
            module.ensure_base_image(Path('/tmp/observations'), {})

    def test_a_successful_pull_is_captured_as_evidence(self) -> None:
        """The pull log belongs beside the build log it explains."""
        module = _module()
        module.run_command = Mock(return_value=SimpleNamespace(exit_code=1))
        module._capture = Mock(return_value={'exit_code': 0})

        module.ensure_base_image(Path('/tmp/observations'), {})

        destination = module._capture.call_args.args[2]
        self.assertEqual(destination.name, 'container-pull.log', 'the pull must write its own log')


class OrchestrationTests(unittest.TestCase):
    """Check each failure branch of ``run_verifier_free`` before it runs podman."""

    def setUp(self) -> None:
        """Replace every process and record boundary with a fake."""
        self.module = _module()
        self.directory = Path(tempfile.mkdtemp())
        self.module.ROOT = self.directory
        self.module.FIXTURES = self.directory / 'fixtures'
        (self.module.FIXTURES / 'verus-wiring-probe').mkdir(parents=True)
        for name in self.module.STAGING_FILES:
            target = self.directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('', encoding='utf-8')
        (self.directory / 'rust-toolchain.toml').write_text(
            '[toolchain]\nchannel = "nightly-2026-08-27"\n', encoding='utf-8'
        )
        self.module.staged_sources = Mock(return_value=[])
        self.module._stage_verifier_free_workspace = Mock()
        self.module.ensure_base_image = Mock()
        self.module.container_run_command = Mock(return_value=['podman', 'run'])
        self.module.os = SimpleNamespace(environ={})

    def tearDown(self) -> None:
        """Remove the scratch tree."""
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_host_wrapper_is_recorded_as_inconclusive_and_refused(self) -> None:
        """Removing admission would defeat the isolation being measured."""
        self.module.os.environ['RUSTC_WRAPPER'] = 'build-limits-rustc'

        with self.assertRaisesRegex(RuntimeError, 'without a host-side compiler wrapper'):
            self.module.run_verifier_free()

        record = json.loads((self.module.FIXTURES / 'verus-wiring-probe/verifier-free.json').read_text())
        self.assertEqual(record['status'], 'inconclusive', 'the refusal must be recorded')
        self.module.ensure_base_image.assert_not_called()

    def test_a_failed_container_build_is_reported(self) -> None:
        """A build failure must name itself rather than the later run."""
        self.module._capture = Mock(return_value={'exit_code': 1})

        with self.assertRaisesRegex(RuntimeError, 'could not be prepared'):
            self.module.run_verifier_free()

        self.module._capture.assert_called_once()
        self.assertIn('podman', self.module._capture.call_args.args[0], 'the build must go through podman')

    def test_a_failed_container_run_is_reported(self) -> None:
        """A compiler failure inside the container must not be recorded as a pass."""
        self.module._capture = Mock(side_effect=[{'exit_code': 0}, {'exit_code': 2}])

        with self.assertRaisesRegex(RuntimeError, 'failed in the verifier-free container'):
            self.module.run_verifier_free()

        self.assertFalse(
            (self.module.FIXTURES / 'verus-wiring-probe/verifier-free.json').exists(),
            'a failed run must not leave a passing record',
        )

    def test_a_successful_run_records_status_and_source_digests(self) -> None:
        """The passing record must bind the staged inputs it actually built."""
        self.module.staged_sources = Mock(return_value=[self.directory / 'rust-toolchain.toml'])
        self.module._capture = Mock(side_effect=[{'exit_code': 0}, {'exit_code': 0}])

        self.module.run_verifier_free()

        record = json.loads((self.module.FIXTURES / 'verus-wiring-probe/verifier-free.json').read_text())
        self.assertEqual(record['status'], 'pass', 'the record must report the passing status')
        self.assertEqual(
            list(record['source_digests']),
            ['rust-toolchain.toml'],
            'the record must bind every staged source',
        )
        self.assertTrue(
            is_structural_digest(record['source_digests']['rust-toolchain.toml']),
            'each digest must be a versioned structural SHA-256 value',
        )
        self.assertEqual(
            self.module._capture.call_count,
            2,
            'the build and the run must both be captured',
        )


if __name__ == '__main__':
    unittest.main()
