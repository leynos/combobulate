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
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from verifier_probe_loader import load_structural_digest, load_verifier_free_probe

is_structural_digest = load_structural_digest().is_structural_digest

FIXTURES = Path(__file__).resolve().parents[2] / 'tools/verifier-fixtures'


def _module() -> ModuleType:
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
    """Copy the fixture and its pins into a freshly recreated workspace."""

    def test_staging_places_the_fixture_and_the_pins(self) -> None:
        """The container builds ``probe/`` with the pins beside it."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'

            module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertTrue((workspace / 'probe/Cargo.toml').is_file(), 'the fixture must be staged as `probe/`')
            self.assertTrue((workspace / 'Containerfile').is_file(), 'the container recipe must be written')
            for name in module.STAGING_FILES:
                self.assertTrue((workspace / name).is_file(), f'the pinned {name} must be copied')

    def test_restaging_removes_a_stale_destination_file(self) -> None:
        """A file deleted from the repository must not survive in the workspace."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'
            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            stale_marker = workspace / 'probe/target/marker'
            stale_marker.parent.mkdir(parents=True)
            stale_marker.write_text('stale', encoding='utf-8')
            unknown = workspace / 'probe/unknown.toml'
            unknown.write_text('stale = true', encoding='utf-8')

            module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertFalse(stale_marker.exists(), 'stale build output must be removed')
            self.assertFalse(unknown.exists(), 'an unknown fixture file must be removed')

    def test_staging_is_idempotent(self) -> None:
        """A rerun must recreate the workspace rather than fail."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'

            module._stage_verifier_free_workspace(workspace, boundary=boundary)
            module._stage_verifier_free_workspace(workspace, boundary=boundary)

            self.assertTrue((workspace / 'probe/Cargo.toml').is_file(), 'a second staging run must succeed')

    def test_staging_copies_no_evidence_record(self) -> None:
        """A stale record inside the build must not ride along."""
        module = _module()
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            workspace = boundary / 'workspace'

            module._stage_verifier_free_workspace(workspace, boundary=boundary)

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
    """Check each branch of ``run_verifier_free`` with real staging and digesting."""

    def setUp(self) -> None:
        """Build a small real fixture tree and replace only the process boundary."""
        self.module = _module()
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.module.ROOT = self.directory
        self.module.FIXTURES = self.directory / 'fixtures'
        fixture = self.module.FIXTURES / 'verus-wiring-probe'
        (fixture / 'nested').mkdir(parents=True)
        (fixture / 'Cargo.toml').write_text(
            '[package]\nname = "probe"\nversion = "0.1.0"\n', encoding='utf-8'
        )
        (fixture / 'nested/input.toml').write_text('value = 1\n', encoding='utf-8')
        for name in self.module.STAGING_FILES:
            target = self.directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = '0.0.0\n' if target.name == 'VERSION' else ''
            target.write_text(content, encoding='utf-8')
        (self.directory / 'rust-toolchain.toml').write_text(
            '[toolchain]\nchannel = "nightly-2026-11-06"\n', encoding='utf-8'
        )
        self.module.ensure_base_image = Mock()
        self.module.container_run_command = Mock(return_value=['podman', 'run'])
        self.module.os = SimpleNamespace(environ={})

    def _run_to_success(self) -> None:
        """Capture a successful build and run, then execute the orchestrator."""
        self.module._capture = Mock(side_effect=[{'exit_code': 0}, {'exit_code': 0}])

        self.module.run_verifier_free()

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
        self._run_to_success()

        record = json.loads((self.module.FIXTURES / 'verus-wiring-probe/verifier-free.json').read_text())
        self.assertEqual(record['status'], 'pass', 'the record must report the passing status')
        self.assertEqual(
            set(record['source_digests']),
            {str(path.relative_to(self.module.ROOT)) for path in self.module.staged_sources()},
            'the record must bind every staged source under its repository-relative key',
        )
        workspace = self.module.ROOT / 'target/epm1-verifier-free-workspace'
        staged = self.module.staged_inputs(workspace)
        for key, digest in record['source_digests'].items():
            self.assertTrue(
                is_structural_digest(digest),
                f'{key} must carry a versioned structural SHA-256 value',
            )
            self.assertEqual(
                digest,
                self.module.structural_digest(staged[key]),
                f'{key} must bind the staged copy the container built',
            )
        self.assertEqual(self.module._capture.call_count, 2, 'the build and the run must both be captured')

    def test_deleting_a_source_between_runs_removes_it_from_the_stage_and_record(self) -> None:
        """A deleted source must not stay available to Cargo or the record."""
        fixture = self.module.FIXTURES / 'verus-wiring-probe'
        obsolete = fixture / 'obsolete.toml'
        obsolete.write_text('value = 1\n', encoding='utf-8')
        self.module.STAGING_FILES = ('rust-toolchain.toml',)
        self.module._capture = Mock(side_effect=[{'exit_code': 0}] * 4)
        workspace = self.module.ROOT / 'target/epm1-verifier-free-workspace'
        key = str(obsolete.relative_to(self.module.ROOT))

        self.module.run_verifier_free()

        first = json.loads((fixture / 'verifier-free.json').read_text())
        self.assertTrue((workspace / 'probe/obsolete.toml').is_file(), 'the first run must stage the input')
        self.assertIn(key, first['source_digests'], 'the first record must bind the extra input')

        obsolete.unlink()
        self.module.run_verifier_free()

        second = json.loads((fixture / 'verifier-free.json').read_text())
        self.assertFalse(
            (workspace / 'probe/obsolete.toml').exists(),
            'a source deleted before the second run must not survive staging',
        )
        self.assertNotIn(key, second['source_digests'], 'the second record must not bind a deleted source')

    def test_a_source_change_after_staging_does_not_move_the_recorded_digest(self) -> None:
        """The record must bind the staged copy, not a source changed after copying."""
        fixture = self.module.FIXTURES / 'verus-wiring-probe'
        source = fixture / 'nested/input.toml'
        staged = self.module.ROOT / 'target/epm1-verifier-free-workspace/probe/nested/input.toml'
        original_digest = self.module.structural_digest(source)
        real_stage = self.module._stage_verifier_free_workspace

        def stage_then_mutate(
            directory: Path, *, boundary: Path | None = None
        ) -> None:
            """Stage first, then change the source behind the staged copy."""
            real_stage(directory, boundary=boundary)
            source.write_text('value = 2\n', encoding='utf-8')
            (self.module.ROOT / 'rust-toolchain.toml').write_text(
                '[toolchain]\nchannel = "nightly-1999-01-01"\n', encoding='utf-8'
            )

        with patch.object(
            self.module, '_stage_verifier_free_workspace', stage_then_mutate
        ):
            self._run_to_success()

        record = json.loads((fixture / 'verifier-free.json').read_text())
        key = str(source.relative_to(self.module.ROOT))
        self.assertEqual(
            record['source_digests'][key],
            self.module.structural_digest(staged),
            'the recorded digest must describe the staged copy',
        )
        self.assertEqual(
            record['source_digests'][key],
            original_digest,
            'the recorded digest must describe the bytes the container builds',
        )
        self.assertNotEqual(
            record['source_digests'][key],
            self.module.structural_digest(source),
            'a source changed after staging must not satisfy the record',
        )
        self.assertEqual(
            self.module.container_run_command.call_args.args[3],
            'nightly-2026-11-06',
            'the channel must come from the staged toolchain',
        )

    def test_a_directory_symlink_in_the_staged_tree_fails_before_image_preparation(
        self,
    ) -> None:
        """A swapped directory changes the input set before any image is built."""
        outside = self.directory / 'outside'
        outside.mkdir()
        real_stage = self.module._stage_verifier_free_workspace

        def stage_then_link(
            directory: Path, *, boundary: Path | None = None
        ) -> None:
            """Replace a staged input directory with a link to an empty tree."""
            real_stage(directory, boundary=boundary)
            nested = directory / 'probe/nested'
            shutil.rmtree(nested)
            nested.symlink_to(outside, target_is_directory=True)

        with patch.object(
            self.module, '_stage_verifier_free_workspace', stage_then_link
        ), patch.object(self.module, '_capture') as capture:
            with self.assertRaisesRegex(
                RuntimeError, 'does not match the recorded inputs'
            ):
                self.module.run_verifier_free()

        self.module.ensure_base_image.assert_not_called()
        capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()